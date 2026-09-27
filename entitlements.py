"""
GHL custom-field provisioning for client entitlement data. Entitlement
contacts live on the agency's own GHL location (one contact per client) —
see the spec's Client entitlement table. This module only ensures the
fields exist; entitlement contact lookup/update helpers are a later phase.
"""
from ghl_api import get_custom_fields, create_custom_field

# Verbatim from the spec's Client entitlement table.
ENTITLEMENT_FIELD_DEFS = [
    {"name": "subscribed_zipcodes", "dataType": "TEXTBOX_LIST", "fieldKey": "contact.subscribed_zipcodes"},
    {"name": "zip_quota", "dataType": "NUMERICAL", "fieldKey": "contact.zip_quota"},
    {"name": "sub_account_location_id", "dataType": "TEXT", "fieldKey": "contact.sub_account_location_id"},
    {"name": "sub_account_api_key", "dataType": "TEXT", "fieldKey": "contact.sub_account_api_key"},
]


def ensure_entitlement_fields(location_id, api_key):
    """Ensures all four entitlement custom fields exist on `location_id`,
    creating any that are missing. Idempotent — safe to call on every app
    startup. Returns {field name: field id} for all four fields."""
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
        created = create_custom_field(
            location_id, field_def['name'], field_def['dataType'],
            model="contact", api_key=api_key,
        )
        result[field_def['name']] = created['id']
    return result
