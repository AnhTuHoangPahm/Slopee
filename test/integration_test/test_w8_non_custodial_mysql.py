"""Tuần 8 [A] E-05 / AC-09 trên MySQL THẬT: CSDL dựng từ schema.sql không có cột nào chứa khóa/seed, và bộ quét `--db` bắt được
một khóa riêng cắm vào CSDL thật (chứng minh bộ quét không "câm"). Tự skip nếu không có MySQL (xem fixture `mysql_db`)."""
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.mysql

_spec = importlib.util.spec_from_file_location('scan_no_user_keys', Path(__file__).resolve().parents[2] / 'scripts' / 'scan_no_user_keys.py')
scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan)


def test_fresh_database_has_no_key_columns_or_values(db_conn, mysql_db):
    r = scan.scan_database(db_conn, mysql_db)
    assert [f.line() for f in r.high] == []
    assert r.scanned['db tables'] >= 19            # đủ cả 19 bảng Web3 + bảng Slopee gốc, không phải CSDL rỗng


def test_scan_detects_planted_private_key_in_real_database(db_conn, mysql_db):
    cur = db_conn.cursor()
    cur.execute("CREATE TABLE w8_probe (id INT PRIMARY KEY, note TEXT)")
    try:
        cur.execute("INSERT INTO w8_probe VALUES (1, %s)", ('backup: 0x' + 'ab' * 32,))
        r = scan.scan_database(db_conn, mysql_db)
        assert any(f.rule == 'HEX64_IN_NON_HASH_COLUMN' and f.where == 'w8_probe.note' for f in r.high)
    finally:
        cur.execute("DROP TABLE w8_probe")


def test_wallet_linking_stores_only_public_address(db_conn):
    cur = db_conn.cursor()
    cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_wallets'")
    cols = {row['COLUMN_NAME'] for row in cur.fetchall()}
    assert 'address' in cols and not [c for c in cols if scan.column_is_bad(c)]
