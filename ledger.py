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
