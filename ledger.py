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
