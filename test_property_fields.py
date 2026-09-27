"""
Offline test: verify BatchData -> GHL custom-field mapping against saved
webhook payloads. No network. Run: ./venv/bin/python test_property_fields.py
"""
import json
from unittest.mock import patch

import main
from main import (
    _build_amenities,
    _build_property_custom_fields,
    _build_zillow_url,
    _translate_custom_fields,
    PROPERTY_CUSTOM_FIELD_NAMES,
)

REAL_PAYLOAD = 'webhook_logs/webhook_a289838f-fb8e-4315-a0ca-3fcf95f61e92.json'
EMPTY_BUILDING_PAYLOAD = 'webhook_logs/webhook_6658f7d8-6c82-4371-84cf-fa716df4d155.json'

# Stand-in ids so we can assert on structure without hitting GHL.
FIELD_MAP = {name: f'id::{name}' for name in PROPERTY_CUSTOM_FIELD_NAMES}


def _load(path):
    with open(path) as f:
        return json.load(f)['results']['properties']


def test_full_property_maps_all_fields():
    prop = _load(REAL_PAYLOAD)[0]  # 50 Cedar Rd: 3bd/2ba, 1641 sqft, 1 story, HOA, 0.36ac, 1989
    fields = {e['id']: e['field_value'] for e in _build_property_custom_fields(prop, FIELD_MAP)}

    assert fields['id::Square Footage'] == '1641'
    assert fields['id::Bathrooms'] == 2
    assert fields['id::Floors'] == 1
    assert fields['id::Number of Rooms'] == 3
    assert 'HOA' in fields['id::Local Ammenities']
    assert '0.36 acre lot' in fields['id::Local Ammenities']
    # bed/bath/sqft have their own fields now — not repeated in the amenities blob
    assert 'bedroom' not in fields['id::Local Ammenities'].lower()


def test_pool_detected_from_freetext_string():
    # 2nd property has building.pool == "Pool - Yes" (string, no poolCode key)
    prop = _load(REAL_PAYLOAD)[1]
    assert 'Pool' in _build_amenities(prop)


def test_empty_building_yields_no_custom_fields():
    prop = _load(EMPTY_BUILDING_PAYLOAD)[0]
    assert _build_property_custom_fields(prop, FIELD_MAP) == []
    assert _build_amenities(prop) == ''


def test_missing_field_in_map_is_skipped_not_errored():
    prop = _load(REAL_PAYLOAD)[0]
    partial = {'Bathrooms': 'id::Bathrooms'}
    result = _build_property_custom_fields(prop, partial)
    assert result == [{'id': 'id::Bathrooms', 'field_value': 2}]


def test_translate_custom_fields_remaps_by_fieldkey():
    # Source location ids -> field metadata (as returned by get_custom_fields)
    src_id_to_key = {
        'src_amen': {'fieldKey': 'contact.local_ammenities'},
        'src_bath': {'fieldKey': 'contact.bathrooms'},
    }
    # Destination location: different ids for the same fieldKeys, plus one extra
    dst_key_to_id = {'contact.local_ammenities': 'dst_amen', 'contact.bathrooms': 'dst_bath'}

    # Input entries mimic a GET /contacts response, which uses the `value` key.
    entries = [
        {'id': 'src_amen', 'value': 'Pool\nHOA'},
        {'id': 'src_bath', 'value': 2},
        {'id': 'src_unknown', 'value': 'x'},   # no fieldKey mapping -> dropped
        {'id': 'src_amen2', 'value': ''},       # empty value -> dropped
    ]
    # No dest_id is missing for these fieldKeys, so the auto-create path
    # (which needs a real location/api key) is never hit — dummies are safe.
    out = _translate_custom_fields(entries, src_id_to_key, dst_key_to_id, 'dst_loc', 'dst_key')
    # Output is a write payload, which uses the `field_value` key.
    assert out == [
        {'id': 'dst_amen', 'field_value': 'Pool\nHOA'},
        {'id': 'dst_bath', 'field_value': 2},
    ]


def test_translate_custom_fields_handles_none():
    assert _translate_custom_fields(None, {}, {}, 'dst_loc', 'dst_key') == []


def test_translate_custom_fields_auto_creates_missing_field():
    # Source field has no counterpart in dst_key_to_id, so it must be created.
    src_id_to_field = {
        'src_new': {'fieldKey': 'contact.new_field', 'name': 'New Field', 'dataType': 'TEXT'},
    }
    dst_key_to_id = {}
    entries = [{'id': 'src_new', 'value': 'hello'}]

    with patch.object(main, 'create_custom_field') as mock_create:
        mock_create.return_value = {'id': 'dst_new', 'fieldKey': 'contact.new_field'}
        out = _translate_custom_fields(entries, src_id_to_field, dst_key_to_id, 'dst_loc', 'dst_key')

    mock_create.assert_called_once_with(
        'dst_loc', 'New Field', 'TEXT', model='contact', api_key='dst_key'
    )
    assert out == [{'id': 'dst_new', 'field_value': 'hello'}]
    # dst_key_to_id is mutated in place so a second entry for the same field
    # reuses the created id instead of creating it again.
    assert dst_key_to_id == {'contact.new_field': 'dst_new'}


def test_translate_custom_fields_skips_non_autocreatable_datatype():
    # SINGLE_OPTIONS needs its option list replicated, which we don't attempt.
    src_id_to_field = {
        'src_opt': {'fieldKey': 'contact.status', 'name': 'Status', 'dataType': 'SINGLE_OPTIONS'},
    }
    entries = [{'id': 'src_opt', 'value': 'Hot'}]

    with patch.object(main, 'create_custom_field') as mock_create:
        out = _translate_custom_fields(entries, src_id_to_field, {}, 'dst_loc', 'dst_key')

    mock_create.assert_not_called()
    assert out == []


def test_zillow_url_slug():
    prop = _load(REAL_PAYLOAD)[0]
    assert _build_zillow_url(prop) == 'https://www.zillow.com/homes/50-Cedar-Rd-Ocala-FL-34472_rb/'


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except Exception as e:
            # Catch everything, not just AssertionError — a signature mismatch
            # or other bug shouldn't crash the script and hide every test after it.
            failed += 1
            print(f'FAIL {t.__name__}: {e}')
    raise SystemExit(failed)
