"""
Offline test: verify BatchData -> GHL custom-field mapping against saved
webhook payloads. No network. Run: ./venv/bin/python test_property_fields.py
"""
import json

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
    fields = {e['id']: e['value'] for e in _build_property_custom_fields(prop, FIELD_MAP)}

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
    assert result == [{'id': 'id::Bathrooms', 'value': 2}]


def test_translate_custom_fields_remaps_by_fieldkey():
    # Source location ids -> shared fieldKey
    src_id_to_key = {'src_amen': 'contact.local_ammenities', 'src_bath': 'contact.bathrooms'}
    # Destination location: different ids for the same fieldKeys, plus one extra
    dst_key_to_id = {'contact.local_ammenities': 'dst_amen', 'contact.bathrooms': 'dst_bath'}

    entries = [
        {'id': 'src_amen', 'value': 'Pool\nHOA'},
        {'id': 'src_bath', 'value': 2},
        {'id': 'src_unknown', 'value': 'x'},   # no fieldKey mapping -> dropped
        {'id': 'src_amen2', 'value': ''},       # empty value -> dropped
    ]
    out = _translate_custom_fields(entries, src_id_to_key, dst_key_to_id)
    assert out == [
        {'id': 'dst_amen', 'value': 'Pool\nHOA'},
        {'id': 'dst_bath', 'value': 2},
    ]


def test_translate_custom_fields_handles_none():
    assert _translate_custom_fields(None, {}, {}) == []


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
        except AssertionError as e:
            failed += 1
            print(f'FAIL {t.__name__}: {e}')
    raise SystemExit(failed)
