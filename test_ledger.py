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
