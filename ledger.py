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
