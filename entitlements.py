"""
GHL custom-field provisioning for client entitlement data. Entitlement
contacts live on the agency's own GHL location (one contact per client) —
see the spec's Client entitlement table. This module only ensures the
fields exist; entitlement contact lookup/update helpers are a later phase.
"""
import logging

from ghl_api import get_custom_fields, create_custom_field

logger = logging.getLogger(__name__)

# Based on the spec's Client entitlement table, with one deviation: the spec
# named TEXTBOX_LIST for subscribed_zipcodes, but GHL's TEXTBOX_LIST is a
# fixed set of named text-input slots (it requires a non-empty
# textBoxListOptions list up front), not a variable-length growable list —
# confirmed by a live 400 ("textBoxListOptions should not be empty") when
# provisioning against the real agency location. LARGE_TEXT holding a
# comma-separated zip list fits "however many zips a client subscribes to"
# without a slot cap, matching how sub_account_api_key etc. are plain TEXT.
ENTITLEMENT_FIELD_DEFS = [
    {"name": "subscribed_zipcodes", "dataType": "LARGE_TEXT", "fieldKey": "contact.subscribed_zipcodes"},
    {"name": "zip_quota", "dataType": "NUMERICAL", "fieldKey": "contact.zip_quota"},
    {"name": "sub_account_location_id", "dataType": "TEXT", "fieldKey": "contact.sub_account_location_id"},
    {"name": "sub_account_api_key", "dataType": "TEXT", "fieldKey": "contact.sub_account_api_key"},
]


def ensure_entitlement_fields(location_id, api_key):
    """Ensures all four entitlement custom fields exist on `location_id`,
    creating any that are missing. Idempotent — safe to call on every app
    startup. Returns {field name: field id} for fields that exist or were
    successfully created; a field whose creation fails (e.g. TEXTBOX_LIST
    needing extra config our bare name+dataType payload can't supply) is
    logged and omitted rather than aborting the rest."""
    existing_by_key = {
        f['fieldKey']: f['id']
        for f in get_custom_fields(location_id, api_key=api_key)
        if f.get('fieldKey')
    }

    result = {}
    for field_def in ENTITLEMENT_FIELD_DEFS:
        existing_id = existing_by_key.get(field_def['fieldKey'])
        if existing_id:
            result[field_def['name']] = existing_id
            continue
        try:
            created = create_custom_field(
                location_id, field_def['name'], field_def['dataType'],
                model="contact", api_key=api_key,
            )
            result[field_def['name']] = created['id']
        except Exception as e:
            logger.error(f"Failed to create entitlement field '{field_def['name']}': {e}")
    return result
