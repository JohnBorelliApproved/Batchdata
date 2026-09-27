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
