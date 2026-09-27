"""
Offline tests for main.py's startup provisioning guard. No network —
entitlements.ensure_entitlement_fields is mocked. Verifies
SKIP_STARTUP_PROVISIONING actually prevents the live GHL call, since
main.py runs it unconditionally at import time and every other test file
that does `from main import ...` (e.g. test_property_fields.py) would
otherwise hit production GHL on every run.
Run: ./venv/bin/python test_main_startup.py
"""
import importlib
import os
from unittest.mock import patch

os.environ.setdefault("SKIP_STARTUP_PROVISIONING", "1")

import config
import entitlements
import main  # noqa: F401 — first import, establishes baseline module state


def test_startup_skips_provisioning_when_flag_set():
    with patch.dict(os.environ, {"SKIP_STARTUP_PROVISIONING": "1"}):
        importlib.reload(config)
        with patch.object(entitlements, "ensure_entitlement_fields") as mock_ensure:
            importlib.reload(main)
            mock_ensure.assert_not_called()
    importlib.reload(config)
    importlib.reload(main)


def test_startup_calls_provisioning_when_flag_unset():
    with patch.dict(os.environ, {"SKIP_STARTUP_PROVISIONING": ""}):
        importlib.reload(config)
        with patch.object(entitlements, "ensure_entitlement_fields") as mock_ensure:
            importlib.reload(main)
            mock_ensure.assert_called_once()
    importlib.reload(config)
    importlib.reload(main)


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
