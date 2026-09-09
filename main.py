import json
import os
import re
import logging
import threading
from flask import Flask, request, jsonify, render_template, abort
from batchdata_api import search_properties
from ghl_api import get_contacts_by_tag, get_contact, upsert_contact, get_tags, get_custom_fields, create_note
from config import AGENCY_LOCATION_ID, AGENCY_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_LOG_DIR = os.path.join(os.path.dirname(__file__), 'webhook_logs')
os.makedirs(WEBHOOK_LOG_DIR, exist_ok=True)

# In-memory job state — keyed by job_id, values: pending | complete | error
# Resets on server restart; fine for single-worker use
job_store = {}

app = Flask(__name__)

GHL_FRAME_ANCESTOR = "https://app.gohighlevel.com"

@app.after_request
def set_frame_ancestors(response):
    # Only GHL is allowed to iframe this app
    response.headers['Content-Security-Policy'] = f"frame-ancestors {GHL_FRAME_ANCESTOR}"
    return response

@app.route('/')
def home():
    # GHL iframes send the parent dashboard as Referer on the initial load;
    # a direct browser visit has no referer (or a different one) and gets blocked.
    referrer = request.referrer or ""
    if not referrer.startswith(GHL_FRAME_ANCESTOR):
        abort(403)
    return render_template('index.html')

@app.route('/get-tags', methods=['GET'])
def get_tags_endpoint():
    try:
        tags = get_tags()
        return jsonify({"tags": tags})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/start-search', methods=['POST'])
def start_search():
    data = request.json
    zip_codes = data.get('zip_codes')
    city = data.get('city')
    state = data.get('state')

    if not (zip_codes or (city and state)):
        return jsonify({"error": "Please provide either zip_codes or city and state."}), 400

    try:
        job_id, batchdata_request_id = search_properties(zip_codes=zip_codes, city=city, state=state)
        job_store[job_id] = {"status": "pending", "batchdata_request_id": batchdata_request_id, "created": 0, "errors": 0}
        logger.info(f"BatchData search initiated. job_id={job_id} batchdata_request_id={batchdata_request_id}")
        return jsonify({"job_id": job_id, "batchdata_request_id": batchdata_request_id, "status": "pending", "message": "Search initiated. Results will be processed when BatchData completes."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/distribute-contacts', methods=['POST'])
def distribute_contacts():
    data = request.json
    location_id = data.get('location_id')
    tag = data.get('tag')
    source_location_id = data.get('source_location_id')
    sub_account_api_key = data.get('sub_account_api_key')

    if not (location_id and tag and source_location_id and sub_account_api_key):
        return jsonify({"error": "Please provide location_id, source_location_id, tag, and sub_account_api_key."}), 400

    try:
        # Get contacts from the source location using the agency's main API key
        contacts = get_contacts_by_tag(tag, source_location_id, api_key=AGENCY_API_KEY)
        
        # Fields returned by the search API that the upsert endpoint rejects
        _SEARCH_ONLY_FIELDS = {
            'id', 'locationId', 'lastUpdated', 'dateAdded', 'dateUpdated',
            'address', 'businessName', 'additionalEmails', 'additionalPhones',
            'firstNameLowerCase', 'lastNameLowerCase', 'contactName',
            'businessId', 'searchAfter', 'phoneLabel', 'followers',
            'validEmail', 'dndSettings',
        }

        # Custom field ids differ per location, so translate them via the shared
        # fieldKey (e.g. "contact.local_ammenities"). Built once for the batch.
        src_id_to_key = {
            f['id']: f['fieldKey']
            for f in get_custom_fields(source_location_id, api_key=AGENCY_API_KEY)
            if f.get('id') and f.get('fieldKey')
        }
        dst_key_to_id = {
            f['fieldKey']: f['id']
            for f in get_custom_fields(location_id, api_key=sub_account_api_key)
            if f.get('id') and f.get('fieldKey')
        }

        for contact in contacts:
            source_contact_id = contact.get('id')

            for field in _SEARCH_ONLY_FIELDS:
                contact.pop(field, None)

            # Set the new location id
            contact['locationId'] = location_id

            # The search response doesn't reliably hydrate customFields values, so
            # pull the full contact and remap each field to the destination's id.
            remapped = []
            if source_contact_id:
                full = get_contact(source_contact_id, api_key=AGENCY_API_KEY)
                remapped = _translate_custom_fields(
                    full.get('customFields'), src_id_to_key, dst_key_to_id
                )
            if remapped:
                contact['customFields'] = remapped
            else:
                contact.pop('customFields', None)

            # Upsert contact to the destination location using the provided sub-account API key
            upsert_contact(contact, api_key=sub_account_api_key)

        return jsonify({"message": f"{len(contacts)} contacts distributed successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/job-status/<job_id>', methods=['GET'])
def job_status(job_id):
    job = job_store.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"job_id": job_id, **job})


# GHL custom fields on the agency location that we populate from the BatchData
# payload. Keyed by the exact field name in GHL (resolved to an id at runtime so
# the same code works across sub-accounts). "Local Ammenities" is spelled that
# way in GHL — do not "fix" it here or the lookup silently misses.
AMENITIES_CUSTOM_FIELD_NAME = "Local Ammenities"
PROPERTY_CUSTOM_FIELD_NAMES = [
    AMENITIES_CUSTOM_FIELD_NAME,
    "Square Footage",
    "Bathrooms",
    "Floors",
    "Number of Rooms",
]


def _translate_custom_fields(entries, src_id_to_key, dst_key_to_id):
    """Rewrites a contact's customFields from source ids to destination ids.

    Entries whose field has no counterpart in the destination location (or no
    value) are dropped rather than sent with a foreign id.
    """
    translated = []
    for entry in entries or []:
        field_key = src_id_to_key.get(entry.get('id'))
        dest_id = dst_key_to_id.get(field_key)
        value = entry.get('value')
        if dest_id and value not in (None, ''):
            translated.append({"id": dest_id, "value": value})
    return translated


def _resolve_custom_field_ids(location_id, api_key, names):
    """Returns {field name: id} for the requested names present on `location_id`.

    Names with no matching GHL field are simply absent from the result.
    """
    fields = get_custom_fields(location_id, api_key=api_key)
    by_name = {f.get('name'): f.get('id') for f in fields if f.get('name') and f.get('id')}
    return {name: by_name[name] for name in names if name in by_name}


def _slugify_address_part(value):
    return re.sub(r'[^a-zA-Z0-9]+', '-', value.strip()).strip('-')


def _build_zillow_url(prop):
    """Builds a Zillow address-search URL from the property's address components."""
    address = prop.get('address', {})
    parts = [
        address.get('street', ''),
        address.get('city', ''),
        address.get('state', ''),
        address.get('zip', ''),
    ]
    slug = '-'.join(_slugify_address_part(p) for p in parts if p.strip())
    return f"https://www.zillow.com/homes/{slug}_rb/"


def _build_amenities(prop):
    """Returns a newline-joined "Local Ammenities" value for a property.

    Bed/bath/sqft/floors each have their own GHL field now, so this covers only
    the extra signals that don't: pool, HOA, lot size, year built, garage.
    Returns '' when none are present so the caller can omit the field entirely.
    """
    building = prop.get('building', {})
    lot = prop.get('lot', {})
    quick_lists = prop.get('quickLists', {})

    lines = []

    # BatchData sends `pool` as a free-text string like "Pool - Yes" (no poolCode
    # key), so any truthy value that isn't an explicit "no" means there's a pool.
    pool = str(building.get('pool') or '').strip()
    if pool and 'no' not in pool.lower():
        lines.append("Pool")
    if quick_lists.get('hasHoa'):
        lines.append("HOA")
    if lot.get('lotSizeAcres'):
        lines.append(f"{lot['lotSizeAcres']} acre lot")
    if building.get('yearBuilt'):
        lines.append(f"Built {building['yearBuilt']}")
    if building.get('garageParkingSpaceCount'):
        lines.append(f"{building['garageParkingSpaceCount']}-car garage")
    for feature in building.get('features', []) or []:
        lines.append(feature)

    return '\n'.join(lines)


def _build_property_custom_fields(prop, field_map):
    """Maps a BatchData property to GHL customFields entries.

    `field_map` is {field name: id}; only names present in it are emitted, so a
    missing GHL field just means that value is skipped, not an error.
    """
    building = prop.get('building', {})

    square_footage = (
        building.get('livingAreaSquareFeet')
        or building.get('totalBuildingAreaSquareFeet')
    )
    values_by_name = {
        AMENITIES_CUSTOM_FIELD_NAME: _build_amenities(prop) or None,
        # Field type is TEXT in GHL, so send a string.
        "Square Footage": str(square_footage) if square_footage else None,
        "Bathrooms": building.get('bathroomCount'),
        "Floors": building.get('storyCount'),
        # BatchData has no total room count for these records; bedroom count is
        # the client-agreed stand-in.
        "Number of Rooms": building.get('bedroomCount'),
    }

    custom_fields = []
    for name, value in values_by_name.items():
        field_id = field_map.get(name)
        if field_id and value not in (None, ''):
            custom_fields.append({"id": field_id, "value": value})
    return custom_fields


def _rank_phone_numbers(phone_entries):
    """Ranks a property's skip-traced phone numbers best-first.

    Skip trace returns a household pool of numbers, not one per owner, so we
    rank the whole list once instead of trusting array position. Preference:
    reachable first, then mobile over landline, then BatchData's confidence
    score. DNC numbers are kept here — filtering those for call compliance is
    a separate decision.
    """
    ranked = []
    for entry in phone_entries or []:
        raw_phone = (entry.get('number') or '').strip()
        digits = re.sub(r'\D', '', raw_phone)
        # US numbers are 10 digits, 11 with country code; allow a little slack.
        if not (10 <= len(digits) <= 15):
            continue
        sort_key = (
            0 if entry.get('reachable') else 1,
            0 if (entry.get('type') or '').lower() == 'mobile' else 1,
            -(entry.get('score') or 0),
        )
        ranked.append((sort_key, raw_phone))

    ranked.sort(key=lambda item: item[0])
    return [raw_phone for _sort_key, raw_phone in ranked]


def _build_contacts_from_property(prop, field_map=None):
    """Returns a list of GHL contact dicts, one per owner on the property."""
    owner = prop.get('owner', {})
    address = prop.get('address', {})
    names = owner.get('names', [])
    emails = owner.get('emails', [])
    ranked_phones = _rank_phone_numbers(owner.get('phoneNumbers', []))

    custom_fields = _build_property_custom_fields(prop, field_map or {})

    contacts = []
    for index, name in enumerate(names):
        contact = {
            'locationId': AGENCY_LOCATION_ID,
            'firstName': name.get('first', ''),
            'lastName': name.get('last', ''),
            'tags': ['batchdata-import'],
            'address1': address.get('street', ''),
            'city': address.get('city', ''),
            'state': address.get('state', ''),
            'postalCode': address.get('zip', ''),
        }

        if index < len(emails):
            contact['email'] = emails[index]

        if ranked_phones:
            # Give each owner a distinct number when the pool is deep enough;
            # otherwise fall back to the best one so the contact still has a
            # phone (a shared number may get merged by GHL's upsert dedupe).
            contact['phone'] = ranked_phones[index] if index < len(ranked_phones) else ranked_phones[0]

        if custom_fields:
            contact['customFields'] = custom_fields

        contacts.append(contact)

    return contacts


@app.route('/batchdata-webhook/<job_id>', methods=['POST'])
def batchdata_webhook(job_id):
    data = request.json
    logger.info(f"BatchData webhook received. job_id={job_id}")

    log_path = os.path.join(WEBHOOK_LOG_DIR, f"webhook_{job_id}.json")
    with open(log_path, 'w') as f:
        json.dump(data, f, indent=2)
    logger.info(f"Webhook payload saved to {log_path}")

    # BatchData drops the webhook (cURL 28) if we don't answer within 30s, and a
    # full result set is dozens of sequential GHL calls. Ack immediately, then
    # process on a background thread.
    job_store[job_id] = {"status": "processing", "created": 0, "errors": 0, "skipped_no_phone": 0}
    threading.Thread(target=_process_webhook, args=(job_id, data), daemon=True).start()
    return jsonify({"status": "accepted"}), 202


def _process_webhook(job_id, data):
    properties = data.get('results', {}).get('properties', [])
    created = 0
    errors = 0
    skipped_no_phone = 0

    field_map = {}
    try:
        field_map = _resolve_custom_field_ids(
            AGENCY_LOCATION_ID, AGENCY_API_KEY, PROPERTY_CUSTOM_FIELD_NAMES
        )
        missing = [n for n in PROPERTY_CUSTOM_FIELD_NAMES if n not in field_map]
        if missing:
            logger.warning(f"Custom fields not found on agency location, will be skipped: {missing}")
    except Exception as e:
        logger.warning(f"Failed to look up custom fields: {e}")

    for prop in properties:
        zillow_url = _build_zillow_url(prop)
        for contact in _build_contacts_from_property(prop, field_map):
            # Client requirement: only import contacts with a phone number.
            # Contacts with no phone (email-only or no contact info at all) are dropped.
            if 'phone' not in contact:
                logger.info(f"Skipping contact {contact.get('firstName')} {contact.get('lastName')}: no phone number from skip trace")
                skipped_no_phone += 1
                continue
            try:
                result = upsert_contact(contact, api_key=AGENCY_API_KEY)
                created += 1
                contact_id = result.get('contact', {}).get('id') or result.get('id')
                if contact_id:
                    # target=_blank so the link opens a new tab — the note is
                    # viewed inside the GHL iframe and must not navigate it away.
                    create_note(
                        contact_id,
                        f'<a href="{zillow_url}" target="_blank" rel="noopener">Zillow Property Page</a>',
                        api_key=AGENCY_API_KEY,
                    )
            except Exception as e:
                logger.error(f"Failed to upsert contact {contact.get('firstName')} {contact.get('lastName')}: {e}")
                errors += 1

    logger.info(f"BatchData webhook processed. job_id={job_id} created={created} errors={errors} skipped_no_phone={skipped_no_phone}")
    job_store[job_id] = {"status": "complete", "created": created, "errors": errors, "skipped_no_phone": skipped_no_phone}


@app.route('/batchdata-webhook-error/<job_id>', methods=['POST'])
def batchdata_webhook_error(job_id):
    data = request.json
    logger.error(f"BatchData error webhook received. job_id={job_id} data={data}")

    log_path = os.path.join(WEBHOOK_LOG_DIR, f"webhook_error_{job_id}.json")
    with open(log_path, 'w') as f:
        json.dump(data, f, indent=2)

    job_store[job_id] = {"status": "error", "created": 0, "errors": 0}
    return jsonify({"status": "received"})

if __name__ == '__main__':
    app.run(debug=True, port=5002)
