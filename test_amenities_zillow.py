"""
Manual test: load a saved BatchData sample property payload, then create a
GHL contact with the Property Amenities custom field and a Zillow-link note,
directly against a specific sub-account (bypassing the agency-scoped webhook
route).
"""
import json
from dotenv import load_dotenv
import os

from main import _build_zillow_url, _build_amenities, AMENITIES_CUSTOM_FIELD_NAME
from ghl_api import get_custom_fields, upsert_contact, create_note

load_dotenv()

TEST_LOCATION_ID = 'u9lXkl6hAFlBkHKLuJSU'
TEST_API_KEY = os.getenv('TEST_SUBACCOUNT_API_KEY')
SAMPLE_PAYLOAD_PATH = 'webhook_logs/webhook_2a07cc58-3edc-4c53-a125-394431f3a40b.json'


def load_sample_properties(path=SAMPLE_PAYLOAD_PATH):
    print(f'Loading saved BatchData sample payload from {path}...')
    with open(path) as f:
        data = json.load(f)
    properties = data.get('results', {}).get('properties', [])
    print(f'  Loaded {len(properties)} propert(y/ies).')
    return properties


def resolve_amenities_field_id():
    fields = get_custom_fields(TEST_LOCATION_ID, api_key=TEST_API_KEY)
    match = next((f for f in fields if f.get('name') == AMENITIES_CUSTOM_FIELD_NAME), None)
    if not match:
        raise RuntimeError(f"Custom field '{AMENITIES_CUSTOM_FIELD_NAME}' not found in location {TEST_LOCATION_ID}")
    print(f"  Found '{AMENITIES_CUSTOM_FIELD_NAME}' field: id={match['id']} fieldKey={match.get('fieldKey')}")
    return match['id']


if __name__ == '__main__':
    if not TEST_API_KEY:
        raise SystemExit('TEST_SUBACCOUNT_API_KEY not set in .env')

    print('Looking up Property Amenities custom field...')
    field_id = resolve_amenities_field_id()

    properties = load_sample_properties()
    if not properties:
        raise SystemExit('No properties found in sample payload.')

    prop = properties[0]
    amenities = _build_amenities(prop)
    zillow_url = _build_zillow_url(prop)
    print(f'\nAmenities:\n{amenities}')
    print(f'\nZillow URL: {zillow_url}')

    contact = {
        'locationId': TEST_LOCATION_ID,
        'firstName': 'Amenities',
        'lastName': 'Test',
        'email': 'amenities-zillow-test@example.com',
        'tags': ['batchdata-import-test'],
    }
    if amenities:
        contact['customFields'] = [{"id": field_id, "value": amenities}]

    print('\nUpserting test contact...')
    result = upsert_contact(contact, api_key=TEST_API_KEY)
    contact_id = result.get('contact', {}).get('id') or result.get('id')
    print(f'  Contact id: {contact_id}')

    print('Creating Zillow link note...')
    create_note(contact_id, f'<a href="{zillow_url}">Zillow Property Page</a>', api_key=TEST_API_KEY)
    print('\nDone. Check GHL contact in the sub-account for the custom field and note.')
