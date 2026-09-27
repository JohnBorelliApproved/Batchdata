# Zip Ledger Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two foundational data-model pieces the zip-dedup redesign depends on: a local SQLite ledger (zip search state, delivered-property dedup, activity log) and the agency-location GHL custom fields that hold each client's entitlement data.

**Architecture:** A new `ledger.py` module owns all SQLite access — each function opens and closes its own short-lived connection (no shared/global connection), which is safe under Gunicorn's multi-worker deployment and trivial to test with a temp-file DB per test. A new `entitlements.py` module owns the GHL side: it ensures the four entitlement custom fields exist on the agency location, creating any that are missing, and is idempotent (safe to call every app startup). Both modules are pure additions — no existing route is modified in this plan.

**Tech Stack:** Python 3, stdlib `sqlite3`, existing `ghl_api.py` wrappers (`get_custom_fields`, `create_custom_field`), existing `config.py` env-var pattern.

**Spec:** `docs/superpowers/specs/2026-09-13-subscription-based-zip-dedup-redesign-design.md` — this plan implements the "Zip ledger" and "Client entitlement" parts of the Data Model & Storage section only. Everything else in that spec (self-serve UI, quota enforcement, daily cron, webhook fan-out delivery, reconciliation) is out of scope for this plan and will be planned separately once this foundation lands.

## Global Constraints

- Zip ledger schema, verbatim from the spec:
  ```
  zip_ledger(zipcode TEXT PRIMARY KEY, last_searched_at DATE, last_batchdata_request_id TEXT)
  delivered_properties(zipcode TEXT, property_key TEXT, delivered_at DATE, PRIMARY KEY (zipcode, property_key))
  activity_log(id INTEGER PRIMARY KEY, client_id TEXT, event_type TEXT, zipcode TEXT, detail TEXT, created_at DATETIME)
  ```
- Entitlement fields live on the **agency's own GHL location** (`AGENCY_LOCATION_ID`), not on sub-accounts — one contact record per client there (per spec's Client entitlement table).
- Entitlement field defs, verbatim from the spec's table:
  - `subscribed_zipcodes` — GHL `TEXTBOX_LIST` custom field
  - `zip_quota` — number custom field (GHL dataType `NUMERICAL`)
  - `sub_account_location_id` — text custom field (GHL dataType `TEXT`)
  - `sub_account_api_key` — text custom field (GHL dataType `TEXT`)
- The ledger is "backend bookkeeping only, never surfaced in GHL" (spec) — it must not go through `ghl_api.py` or any GHL call.
- Follow existing code style: `requests`-based GHL calls stay in `ghl_api.py`; new orchestration/helper modules import from it, mirroring how `main.py` already does.

## Review Focus

- **Re-running ledger init against an existing DB file must not wipe or error on already-populated tables** — `init_db` has to use `CREATE TABLE IF NOT EXISTS`, not drop-and-recreate, or every app restart would lose same-day dedup state. Covered in Task 2.
- **Marking the same zip searched twice in one day must not raise or duplicate rows** — `zip_ledger` is keyed by `zipcode` alone (not zipcode+date), so a second `mark_zip_searched` call for the same zip must overwrite `last_searched_at`/`last_batchdata_request_id`, not throw a `PRIMARY KEY` conflict. Covered in Task 3.
- **Marking the same property delivered twice for the same zip must not raise** — `delivered_properties` is keyed by `(zipcode, property_key)`; a duplicate `mark_property_delivered` call (e.g. a retried delivery) must be a safe no-op, not an `IntegrityError` that crashes a delivery loop. Covered in Task 4.
- **`ensure_entitlement_fields` must not create duplicate fields on a second call** — since it runs idempotently on every app startup (per this plan's Task 7), it must detect fields that already exist (by `fieldKey`) and skip creating them, or the agency location accumulates duplicate custom fields on every restart. Covered in Task 6.
- **A partially-created field set (e.g. 2 of 4 fields already exist from a prior partial run) must still complete correctly** — `ensure_entitlement_fields` must create only the missing ones and return ids for all four, not fail or skip the ones that need creating. Covered in Task 6.

---

## File Structure

- Create: `ledger.py` — SQLite schema + all zip_ledger / delivered_properties / activity_log access functions.
- Create: `entitlements.py` — GHL entitlement custom-field definitions + `ensure_entitlement_fields`.
- Create: `test_ledger.py` — offline unit tests for `ledger.py` (temp-file SQLite DB, no network).
- Create: `test_entitlements.py` — offline unit tests for `entitlements.py` (mocked `ghl_api` calls, no network).
- Modify: `config.py` — add `LEDGER_DB_PATH`.
- Modify: `main.py` — call `ledger.init_db()` and `entitlements.ensure_entitlement_fields()` once at startup.
- Modify: `.env.example` — document `LEDGER_DB_PATH`.
- Modify: `.gitignore` — ignore the SQLite DB file.
- Modify: `progress.md` — record this stage as done.

---

### Task 1: Config — add `LEDGER_DB_PATH`

**Files:**
- Modify: `config.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `config.LEDGER_DB_PATH` (str) — consumed by `ledger.py` in Task 2 as the default DB path.

- [ ] **Step 1: Add the env var to `config.py`**

Add this line after the existing `TEST_SUBACCOUNT_API_KEY` line:

```python
LEDGER_DB_PATH = os.getenv("LEDGER_DB_PATH", os.path.join(os.path.dirname(__file__), "ledger.db"))
```

- [ ] **Step 2: Document it in `.env.example`**

Append to `.env.example`:

```
# Path to the local SQLite ledger DB (zip search state, delivery dedup, activity log).
# Defaults to ledger.db next to the app if unset.
LEDGER_DB_PATH=
```

- [ ] **Step 3: Verify by import**

Run: `source venv/bin/activate && python3 -c "import config; print(config.LEDGER_DB_PATH)"`
Expected: prints an absolute path ending in `ledger.db`, no error.

- [ ] **Step 4: Commit**

```bash
git add config.py .env.example
git commit -m "Add LEDGER_DB_PATH config for the zip ledger"
```

---

### Task 2: `ledger.py` — schema + `init_db`

**Files:**
- Create: `ledger.py`
- Test: `test_ledger.py`

**Interfaces:**
- Consumes: `config.LEDGER_DB_PATH` (from Task 1).
- Produces: `ledger.init_db(db_path=None) -> None` — consumed by every other function in this file (each calls it implicitly is NOT required; connections assume tables already exist, so `init_db` must be called once before any other ledger function is used) and by `main.py` in Task 7.
- Produces: `ledger._connect(db_path=None) -> sqlite3.Connection` — internal helper, reused by Tasks 3-5.

- [ ] **Step 1: Write the failing test**

Create `test_ledger.py`:

```python
"""
Offline tests for the SQLite zip ledger. No network. Uses a temp-file DB
per test so tests never touch the real ledger.db or each other's state.
Run: ./venv/bin/python test_ledger.py
"""
import os
import sqlite3
import tempfile

import ledger


def _tmp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # init_db must be able to create it from scratch
    return path


def test_init_db_creates_all_tables():
    path = _tmp_db_path()
    try:
        ledger.init_db(path)
        conn = sqlite3.connect(path)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        conn.close()
        assert {"zip_ledger", "delivered_properties", "activity_log"} <= tables
    finally:
        os.remove(path)


def test_init_db_is_idempotent():
    path = _tmp_db_path()
    try:
        ledger.init_db(path)
        ledger.mark_zip_searched("90210", "req-1", db_path=path)
        ledger.init_db(path)  # must not wipe existing data
        assert ledger.get_last_searched_at("90210", db_path=path) is not None
    finally:
        os.remove(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python3 test_ledger.py`
Expected: fails with `ModuleNotFoundError: No module named 'ledger'` (or `AttributeError`, since `ledger.py` doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `ledger.py`:

```python
"""
Local SQLite ledger for the zip-dedup redesign — zip search state,
delivered-property dedup, and structured activity logging. Backend
bookkeeping only; never surfaced in GHL.

Each function opens and closes its own connection rather than sharing one,
so this is safe under Gunicorn's multi-worker deployment without needing a
connection pool.
"""
import sqlite3
from datetime import date, datetime

from config import LEDGER_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS zip_ledger (
    zipcode TEXT PRIMARY KEY,
    last_searched_at DATE,
    last_batchdata_request_id TEXT
);

CREATE TABLE IF NOT EXISTS delivered_properties (
    zipcode TEXT,
    property_key TEXT,
    delivered_at DATE,
    PRIMARY KEY (zipcode, property_key)
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY,
    client_id TEXT,
    event_type TEXT,
    zipcode TEXT,
    detail TEXT,
    created_at DATETIME
);
"""


def _connect(db_path=None):
    return sqlite3.connect(db_path or LEDGER_DB_PATH)


def init_db(db_path=None):
    """Creates the ledger tables if they don't already exist. Safe to call
    on every app startup — never drops or alters existing tables/data."""
    conn = _connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source venv/bin/activate && python3 test_ledger.py`
Expected: `test_init_db_creates_all_tables` passes; `test_init_db_is_idempotent` still fails (`mark_zip_searched`/`get_last_searched_at` don't exist yet) — that's expected, Task 3 adds them.

- [ ] **Step 5: Commit**

```bash
git add ledger.py test_ledger.py
git commit -m "Add SQLite ledger schema and init_db"
```

---

### Task 3: `ledger.py` — zip_ledger helpers

**Files:**
- Modify: `ledger.py`
- Test: `test_ledger.py`

**Interfaces:**
- Consumes: `ledger._connect` (Task 2).
- Produces: `ledger.get_last_searched_at(zipcode, db_path=None) -> str | None` (ISO date string) — consumed by the daily cron task in a later plan.
- Produces: `ledger.mark_zip_searched(zipcode, batchdata_request_id, db_path=None, searched_at=None) -> None` — consumed by the daily cron task and self-serve subscribe flow in a later plan.

- [ ] **Step 1: Write the failing test**

Add to `test_ledger.py`:

```python
def test_get_last_searched_at_returns_none_for_unknown_zip():
    path = _tmp_db_path()
    try:
        ledger.init_db(path)
        assert ledger.get_last_searched_at("00000", db_path=path) is None
    finally:
        os.remove(path)


def test_mark_zip_searched_then_get_last_searched_at():
    path = _tmp_db_path()
    try:
        ledger.init_db(path)
        ledger.mark_zip_searched("30301", "req-abc", db_path=path, searched_at="2026-09-27")
        assert ledger.get_last_searched_at("30301", db_path=path) == "2026-09-27"
    finally:
        os.remove(path)


def test_mark_zip_searched_twice_same_day_overwrites_not_errors():
    path = _tmp_db_path()
    try:
        ledger.init_db(path)
        ledger.mark_zip_searched("30301", "req-1", db_path=path, searched_at="2026-09-27")
        ledger.mark_zip_searched("30301", "req-2", db_path=path, searched_at="2026-09-27")
        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT last_batchdata_request_id FROM zip_ledger WHERE zipcode = ?", ("30301",)
        ).fetchone()
        conn.close()
        assert row == ("req-2",)
    finally:
        os.remove(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python3 test_ledger.py`
Expected: `AttributeError: module 'ledger' has no attribute 'get_last_searched_at'`.

- [ ] **Step 3: Write minimal implementation**

Add to `ledger.py`, after `init_db`:

```python
def get_last_searched_at(zipcode, db_path=None):
    """Returns the ISO date string this zip was last searched, or None if
    it's never been searched."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT last_searched_at FROM zip_ledger WHERE zipcode = ?", (zipcode,)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def mark_zip_searched(zipcode, batchdata_request_id, db_path=None, searched_at=None):
    """Records that `zipcode` was searched today (or `searched_at`, an ISO
    date string, if given — used by tests). Overwrites any prior row for
    this zip rather than erroring, since zip_ledger is keyed by zipcode
    alone."""
    searched_at = searched_at or date.today().isoformat()
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO zip_ledger (zipcode, last_searched_at, last_batchdata_request_id)
            VALUES (?, ?, ?)
            ON CONFLICT(zipcode) DO UPDATE SET
                last_searched_at = excluded.last_searched_at,
                last_batchdata_request_id = excluded.last_batchdata_request_id
            """,
            (zipcode, searched_at, batchdata_request_id),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source venv/bin/activate && python3 test_ledger.py`
Expected: all tests so far pass, including `test_init_db_is_idempotent` from Task 2.

- [ ] **Step 5: Commit**

```bash
git add ledger.py test_ledger.py
git commit -m "Add zip_ledger read/write helpers"
```

---

### Task 4: `ledger.py` — delivered_properties helpers

**Files:**
- Modify: `ledger.py`
- Test: `test_ledger.py`

**Interfaces:**
- Consumes: `ledger._connect` (Task 2).
- Produces: `ledger.is_property_delivered(zipcode, property_key, db_path=None) -> bool` — consumed by the daily cron task's cross-day dedup step in a later plan.
- Produces: `ledger.mark_property_delivered(zipcode, property_key, db_path=None, delivered_at=None) -> None` — consumed by the delivery step in a later plan.

- [ ] **Step 1: Write the failing test**

Add to `test_ledger.py`:

```python
def test_is_property_delivered_false_when_unseen():
    path = _tmp_db_path()
    try:
        ledger.init_db(path)
        assert ledger.is_property_delivered("30301", "prop-1", db_path=path) is False
    finally:
        os.remove(path)


def test_mark_property_delivered_then_is_property_delivered_true():
    path = _tmp_db_path()
    try:
        ledger.init_db(path)
        ledger.mark_property_delivered("30301", "prop-1", db_path=path)
        assert ledger.is_property_delivered("30301", "prop-1", db_path=path) is True
    finally:
        os.remove(path)


def test_mark_property_delivered_twice_does_not_raise():
    path = _tmp_db_path()
    try:
        ledger.init_db(path)
        ledger.mark_property_delivered("30301", "prop-1", db_path=path)
        ledger.mark_property_delivered("30301", "prop-1", db_path=path)  # must not raise
        assert ledger.is_property_delivered("30301", "prop-1", db_path=path) is True
    finally:
        os.remove(path)


def test_delivered_properties_scoped_by_zipcode():
    # Same property_key in a different zip is a separate row (e.g. a
    # duplicate-ish address hash shouldn't cross-contaminate zips).
    path = _tmp_db_path()
    try:
        ledger.init_db(path)
        ledger.mark_property_delivered("30301", "prop-1", db_path=path)
        assert ledger.is_property_delivered("90210", "prop-1", db_path=path) is False
    finally:
        os.remove(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python3 test_ledger.py`
Expected: `AttributeError: module 'ledger' has no attribute 'is_property_delivered'`.

- [ ] **Step 3: Write minimal implementation**

Add to `ledger.py`, after `mark_zip_searched`:

```python
def is_property_delivered(zipcode, property_key, db_path=None):
    """Returns True if this zipcode+property_key pair was already recorded
    as delivered (any day), for cross-day dedup."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM delivered_properties WHERE zipcode = ? AND property_key = ?",
            (zipcode, property_key),
        ).fetchone()
    finally:
        conn.close()
    return row is not None


def mark_property_delivered(zipcode, property_key, db_path=None, delivered_at=None):
    """Records that this zipcode+property_key pair has been delivered.
    Safe to call more than once for the same pair — a duplicate is a
    no-op, not an error, since delivered_properties is keyed by
    (zipcode, property_key)."""
    delivered_at = delivered_at or date.today().isoformat()
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO delivered_properties (zipcode, property_key, delivered_at)
            VALUES (?, ?, ?)
            ON CONFLICT(zipcode, property_key) DO NOTHING
            """,
            (zipcode, property_key, delivered_at),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source venv/bin/activate && python3 test_ledger.py`
Expected: all tests so far pass.

- [ ] **Step 5: Commit**

```bash
git add ledger.py test_ledger.py
git commit -m "Add delivered_properties dedup helpers"
```

---

### Task 5: `ledger.py` — activity_log helper

**Files:**
- Modify: `ledger.py`
- Test: `test_ledger.py`

**Interfaces:**
- Consumes: `ledger._connect` (Task 2).
- Produces: `ledger.log_activity(event_type, zipcode=None, client_id=None, detail=None, db_path=None, created_at=None) -> None` — consumed by every step of the daily cron and self-serve subscribe flow in later plans (per spec's Activity Logging section: zip search triggered/skipped, contacts delivered per client, quota rejections, reconciliation drift).

- [ ] **Step 1: Write the failing test**

Add to `test_ledger.py`:

```python
def test_log_activity_writes_a_row():
    path = _tmp_db_path()
    try:
        ledger.init_db(path)
        ledger.log_activity(
            "zip_search_triggered",
            zipcode="30301",
            client_id="client-1",
            detail="self-serve subscribe",
            db_path=path,
            created_at="2026-09-27T12:00:00",
        )
        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT client_id, event_type, zipcode, detail, created_at FROM activity_log"
        ).fetchone()
        conn.close()
        assert row == ("client-1", "zip_search_triggered", "30301", "self-serve subscribe", "2026-09-27T12:00:00")
    finally:
        os.remove(path)


def test_log_activity_allows_missing_optional_fields():
    path = _tmp_db_path()
    try:
        ledger.init_db(path)
        ledger.log_activity("reconciliation_drift", db_path=path)  # no zipcode/client_id/detail
        conn = sqlite3.connect(path)
        row = conn.execute("SELECT event_type FROM activity_log").fetchone()
        conn.close()
        assert row == ("reconciliation_drift",)
    finally:
        os.remove(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python3 test_ledger.py`
Expected: `AttributeError: module 'ledger' has no attribute 'log_activity'`.

- [ ] **Step 3: Write minimal implementation**

Add to `ledger.py`, after `mark_property_delivered`:

```python
def log_activity(event_type, zipcode=None, client_id=None, detail=None, db_path=None, created_at=None):
    """Appends one row to the activity log. `event_type` is a short string
    like "zip_search_triggered", "zip_search_skipped", "contacts_delivered",
    "quota_rejected", or "reconciliation_drift" (per the spec's Activity
    Logging section) — callers choose the value, this function doesn't
    validate it, since the reporting UI that would enforce a fixed set is
    a later phase."""
    created_at = created_at or datetime.now().isoformat()
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO activity_log (client_id, event_type, zipcode, detail, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (client_id, event_type, zipcode, detail, created_at),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source venv/bin/activate && python3 test_ledger.py`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ledger.py test_ledger.py
git commit -m "Add activity_log helper"
```

---

### Task 6: `entitlements.py` — ensure entitlement custom fields exist

**Files:**
- Create: `entitlements.py`
- Test: `test_entitlements.py`

**Interfaces:**
- Consumes: `ghl_api.get_custom_fields(location_id, api_key=None) -> list[dict]` (existing), `ghl_api.create_custom_field(location_id, name, data_type, model="contact", api_key=None) -> dict` (existing).
- Produces: `entitlements.ENTITLEMENT_FIELD_DEFS` (list of dicts with `name`, `dataType`, `fieldKey` keys) — the four fields from the spec's Client entitlement table.
- Produces: `entitlements.ensure_entitlement_fields(location_id, api_key) -> dict[str, str]` (field name -> field id) — consumed by `main.py` startup in Task 7, and by the self-serve entitlement lookup/update helpers in a later plan.

- [ ] **Step 1: Write the failing test**

Create `test_entitlements.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python3 test_entitlements.py`
Expected: `ModuleNotFoundError: No module named 'entitlements'`.

- [ ] **Step 3: Write minimal implementation**

Create `entitlements.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source venv/bin/activate && python3 test_entitlements.py`
Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add entitlements.py test_entitlements.py
git commit -m "Add entitlements.ensure_entitlement_fields"
```

---

### Task 7: Wire startup calls, ignore the DB file, update progress.md

**Files:**
- Modify: `main.py`
- Modify: `.gitignore`
- Modify: `progress.md`

**Interfaces:**
- Consumes: `ledger.init_db()` (Task 2), `entitlements.ensure_entitlement_fields(location_id, api_key)` (Task 6), `config.AGENCY_LOCATION_ID` / `config.AGENCY_API_KEY` (existing).

- [ ] **Step 1: Call both at app startup in `main.py`**

In `main.py`, add the imports near the existing ones (after the `from config import ...` line):

```python
import ledger
import entitlements
```

Then, right after the existing `os.makedirs(WEBHOOK_LOG_DIR, exist_ok=True)` line, add:

```python
ledger.init_db()
entitlements.ensure_entitlement_fields(AGENCY_LOCATION_ID, AGENCY_API_KEY)
```

- [ ] **Step 2: Ignore the local DB file**

Add to `.gitignore` (new line, anywhere in the file):

```
ledger.db
```

- [ ] **Step 3: Verify the app still starts cleanly**

Run: `source venv/bin/activate && python3 -c "import main"` (importing runs the module-level startup code without starting the server)
Expected: no exceptions. If `AGENCY_API_KEY`/`AGENCY_LOCATION_ID` aren't set in your local `.env`, this will raise from the GHL call — that's expected outside a configured environment; confirm instead by reading the code path, or run it against a real `.env` if you have one.

- [ ] **Step 4: Run the full test suite**

Run: `source venv/bin/activate && python3 test_ledger.py && python3 test_entitlements.py && python3 test_property_fields.py`
Expected: all pass, 0 failures.

- [ ] **Step 5: Update `progress.md`**

Add a new bullet under "Done" (or a new "Zip ledger foundation" subsection) noting: SQLite ledger (`ledger.py`, 3 tables, all offline-tested) and agency-location entitlement custom-field provisioning (`entitlements.py`, idempotent, offline-tested) are built and wired into app startup. Note that entitlement contact lookup/update, the self-serve UI, quota enforcement, and the daily cron are still not started — those are separate future plans per the spec's remaining sections.

- [ ] **Step 6: Commit**

```bash
git add main.py .gitignore progress.md
git commit -m "Wire ledger init and entitlement field provisioning into app startup"
```

---

## Self-Review Notes

- **Spec coverage:** Zip ledger schema (Task 2-5) and entitlement custom fields (Task 6) are both implemented verbatim from the spec's Data Model & Storage section. Everything else in the spec (self-serve flow, quota enforcement, daily cron, webhook fan-out, reconciliation, OAuth) is explicitly out of scope per the Spec line above and left for future plans — this is a foundation-only plan, matching the user's specific request to proceed with "zip ledger development."
- **Placeholder scan:** No TBD/TODO markers; every step has real code.
- **Type consistency:** `db_path` parameter name and default (`None` → falls back to `config.LEDGER_DB_PATH`) is consistent across all of `ledger.py`'s functions. `ensure_entitlement_fields` return shape (`dict[str, str]`, keyed by field `name`) is consistent between its docstring, its test assertions, and how Task 7 could later consume it.
- **Review Focus:** all 5 items above map to a task's tests (Tasks 2, 3, 4, 6).
