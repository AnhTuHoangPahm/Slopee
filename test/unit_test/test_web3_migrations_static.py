"""Kiểm tra TĨNH các migration Web3 0006..0020 (không cần MySQL): đặt tên, thứ tự, đối xứng với schema.sql, an toàn."""
import os
import re

import migrate

BACKEND = os.path.dirname(migrate.__file__)
MIGRATIONS = os.path.join(BACKEND, 'migrations')
EXPECTED = [
    '0006_wallets.py', '0007_checkout_groups.py', '0008_order_web3.py', '0009_order_quotes.py',
    '0010_dispute_resolutions.py', '0011_dispute_signatures.sql', '0012_chain_events.sql', '0013_indexer_cursor.sql',
    '0014_platform_settings.sql', '0015_category_policies.sql', '0016_category_policy_map.sql', '0017_tx_outbox.sql',
    '0018_onchain_id_seq.sql', '0019_pending_balances.sql', '0020_shipper.py',
]


def _web3():
    return [m for m in migrate.discover() if m.number >= 6]


def _read(m):
    return open(m.path, encoding='utf-8').read()


def test_web3_migrations_are_exactly_0006_to_0020_contiguous():
    found = _web3()
    assert [m.name for m in found] == EXPECTED
    assert [m.number for m in found] == list(range(6, 21))


def test_every_table_created_by_a_migration_is_in_schema_sql_exactly_once():
    schema = open(os.path.join(BACKEND, 'schema.sql'), encoding='utf-8').read()
    tables = []
    for m in _web3():
        tables += re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)', _read(m))
    assert len(tables) == 16 and len(set(tables)) == 16
    for t in tables:
        assert len(re.findall(rf'CREATE TABLE IF NOT EXISTS {t}\b', schema)) == 1, t


def test_sql_migrations_only_create_or_seed_idempotently():
    for m in _web3():
        if m.kind != 'sql':
            continue
        stmts = migrate.split_sql(_read(m))
        assert stmts, m.name
        for s in stmts:
            assert s.startswith(('CREATE TABLE IF NOT EXISTS', 'INSERT IGNORE INTO')), (m.name, s[:60])


def test_no_destructive_statements_and_no_hardcoded_schema_name():
    for m in _web3():
        body = _read(m)
        code = re.sub(r'--[^\n]*|#[^\n]*', '', body)
        assert not re.search(r'\b(DROP\s+(TABLE|DATABASE|COLUMN|INDEX)|TRUNCATE|DELETE\s+FROM)\b', code, re.I), m.name
        assert 'slopee_db' not in body and 'TABLE_SCHEMA = \'' not in body, m.name


def test_python_migrations_define_upgrade_and_use_defensive_helpers_for_foreign_keys():
    for m in _web3():
        if m.kind != 'py':
            continue
        body = _read(m)
        assert re.search(r'^def upgrade\(cursor\):', body, re.M), m.name
        if 'FOREIGN KEY' in body:                                  # mọi bảng có FK tới bảng Slopee phải kiểm InnoDB + khớp kiểu cột cha
            assert 'require_innodb' in body and 'column_like' in body, m.name


def test_foreign_keys_to_parents_never_cascade_deletes_of_money_records():
    """order_web3 (hồ sơ ký quỹ) phải RESTRICT khi xóa đơn/người dùng gốc (SDD 7.2); chỉ ví và bản ánh xạ danh mục được CASCADE."""
    body = _read(next(m for m in _web3() if m.name == '0008_order_web3.py'))
    for fk in ('fk_order_web3_parent', 'fk_order_web3_buyer', 'fk_order_web3_merchant'):
        assert re.search(rf'CONSTRAINT {fk} FOREIGN KEY[^\n]*ON DELETE RESTRICT', body), fk
    assert 'CASCADE' not in body
