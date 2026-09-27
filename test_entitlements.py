"""
Offline tests for entitlement custom-field provisioning. No network —
ghl_api.get_custom_fields / create_custom_field are mocked.
Run: ./venv/bin/python test_entitlements.py
"""
from unittest.mock import patch

import entitlements


def test_ensure_entitlement_fields_creates_all_when_none_exist():
    with patch.object(entitlements, "get_custom_fields", return_value=[]) as mock_get, \
         patch.object(entitlements, "create_custom_field") as mock_create:
        mock_create.side_effect = [
            {"id": f"id-{i}", "fieldKey": defn["fieldKey"]}
            for i, defn in enumerate(entitlements.ENTITLEMENT_FIELD_DEFS)
        ]
        result = entitlements.ensure_entitlement_fields("agency_loc", "agency_key")

    mock_get.assert_called_once_with("agency_loc", api_key="agency_key")
    assert mock_create.call_count == len(entitlements.ENTITLEMENT_FIELD_DEFS)
    assert set(result) == {defn["name"] for defn in entitlements.ENTITLEMENT_FIELD_DEFS}
    assert all(result.values())  # every field got an id


def test_ensure_entitlement_fields_skips_ones_that_already_exist():
    existing = [
        {"id": "existing-1", "fieldKey": "contact.subscribed_zipcodes"},
        {"id": "existing-2", "fieldKey": "contact.zip_quota"},
    ]
    with patch.object(entitlements, "get_custom_fields", return_value=existing), \
         patch.object(entitlements, "create_custom_field") as mock_create:
        mock_create.side_effect = [
            {"id": "new-1", "fieldKey": "contact.sub_account_location_id"},
            {"id": "new-2", "fieldKey": "contact.sub_account_api_key"},
        ]
        result = entitlements.ensure_entitlement_fields("agency_loc", "agency_key")

    # Only the two missing fields get created.
    assert mock_create.call_count == 2
    created_names = {call.args[1] for call in mock_create.call_args_list}
    assert created_names == {"sub_account_location_id", "sub_account_api_key"}

    # All four are present in the result, existing ones keep their real id.
    assert result["subscribed_zipcodes"] == "existing-1"
    assert result["zip_quota"] == "existing-2"
    assert result["sub_account_location_id"] == "new-1"
    assert result["sub_account_api_key"] == "new-2"


def test_ensure_entitlement_fields_noop_second_call():
    # All four already exist -> no create calls at all.
    existing = [
        {"id": f"id-{defn['name']}", "fieldKey": defn["fieldKey"]}
        for defn in entitlements.ENTITLEMENT_FIELD_DEFS
    ]
    with patch.object(entitlements, "get_custom_fields", return_value=existing), \
         patch.object(entitlements, "create_custom_field") as mock_create:
        result = entitlements.ensure_entitlement_fields("agency_loc", "agency_key")

    mock_create.assert_not_called()
    assert result["subscribed_zipcodes"] == "id-subscribed_zipcodes"


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except Exception as e:
            failed += 1
            print(f'FAIL {t.__name__}: {e}')
    raise SystemExit(failed)
