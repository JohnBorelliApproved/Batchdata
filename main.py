import json
import os
import logging
from flask import Flask, request, jsonify, render_template
from batchdata_api import search_properties
from ghl_api import get_contacts_by_tag, upsert_contact, get_tags
from config import AGENCY_LOCATION_ID, AGENCY_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_LOG_DIR = os.path.join(os.path.dirname(__file__), 'webhook_logs')
os.makedirs(WEBHOOK_LOG_DIR, exist_ok=True)

# In-memory job state — keyed by job_id, values: pending | complete | error
# Resets on server restart; fine for single-worker use
job_store = {}

app = Flask(__name__)

@app.route('/')
def home():
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
        contacts = get_contacts_by_tag(tag, source_location_id)
        
        for contact in contacts:
            # Remove fields that shouldn't be copied to the new location
            contact.pop('id', None)
            contact.pop('locationId', None)
            contact.pop('lastUpdated', None)
            contact.pop('dateAdded', None)

            # Set the new location id
            contact['locationId'] = location_id

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


def _build_contacts_from_property(prop):
    """Returns a list of GHL contact dicts, one per owner on the property."""
    owner = prop.get('owner', {})
    address = prop.get('address', {})
    names = owner.get('names', [])
    emails = owner.get('emails', [])
    phones = owner.get('phoneNumbers', [])

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

        if index < len(phones):
            raw_phone = phones[index].get('number', '')
            # Only set phone if it looks like an actual number (digits, spaces, dashes, parens, plus)
            if raw_phone and all(c in '0123456789 ()-+.' for c in raw_phone):
                contact['phone'] = raw_phone

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

    properties = data.get('results', {}).get('properties', [])
    created = 0
    errors = 0

    for prop in properties:
        for contact in _build_contacts_from_property(prop):
            try:
                upsert_contact(contact, api_key=AGENCY_API_KEY)
                created += 1
            except Exception as e:
                logger.error(f"Failed to upsert contact {contact.get('firstName')} {contact.get('lastName')}: {e}")
                errors += 1

    logger.info(f"BatchData webhook processed. job_id={job_id} created={created} errors={errors}")
    job_store[job_id] = {"status": "complete", "created": created, "errors": errors}
    return jsonify({"status": "processed", "created": created, "errors": errors})


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
