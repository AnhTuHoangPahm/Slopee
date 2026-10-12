"""Migration Web3 0006..0020 trên MySQL THẬT (tự skip nếu không có MySQL; CI chạy với MySQL service 8.0).

Kiểm: (1) DB mới từ schema.sql, (2) DB cũ nâng cấp bằng migrate.py cho ra CÙNG lược đồ, (3) idempotent,
(4) migration phòng vệ khi charset/collation của bảng cha khác mặc định (SDD Q-06, lỗi errno 150), (5) các ràng buộc thật sự chặn dữ liệu xấu.
"""
import os
import uuid

import pymysql
import pytest

import dbschema
import migrate

pytestmark = pytest.mark.mysql

MARKER = "-- WEB3 ESCROW (migration 0006 .. 0020)"
WEB3_NAMES = [
    '0006_wallets.py', '0007_checkout_groups.py', '0008_order_web3.py', '0009_order_quotes.py',
    '0010_dispute_resolutions.py', '0011_dispute_signatures.sql', '0012_chain_events.sql', '0013_indexer_cursor.sql',
    '0014_platform_settings.sql', '0015_category_policies.sql', '0016_category_policy_map.sql', '0017_tx_outbox.sql',
    '0018_onchain_id_seq.sql', '0019_pending_balances.sql', '0020_shipper.py',
]
WEB3_TABLES = [
    'user_wallets', 'wallet_nonces', 'checkout_groups', 'order_web3', 'order_quotes', 'dispute_resolutions',
    'dispute_signatures', 'chain_events', 'indexer_cursor', 'platform_settings', 'category_policies',
    'category_policy_map', 'tx_outbox', 'onchain_id_seq', 'pending_balances', 'shipper_assignments',
]
LEGACY_NAMES = ['0001_money_to_vnd.sql', '0002_product_fk_snapshots.py', '0003_reviews_dedupe.py',
                '0004_auth_attempts.sql', '0005_order_line_settlement.py']
ADDR_A, ADDR_B, ADDR_C = '0x' + 'a' * 40, '0x' + 'b' * 40, '0x' + 'c' * 40
HASH = '0x' + 'd' * 64


# ----------------------------------------------------------------------------------------------- helpers
def _params():
    return dict(host=os.environ.get('DB_HOST', 'localhost'), user=os.environ.get('DB_USER', 'root'),
                password=os.environ.get('DB_PASSWORD', ''))


def _connect(db=None):
    return pymysql.connect(**_params(), database=db, cursorclass=pymysql.cursors.DictCursor, autocommit=True)


def _legacy_sql():
    """Phần schema Slopee CŨ (trước dấu mốc Web3), với ENUM role chưa có 'shipper' (đúng DB trước tuần 2)."""
    path = os.path.join(os.path.dirname(migrate.__file__), 'schema.sql')
    text = open(path, encoding='utf-8').read()
    head = text.split(MARKER)[0]
    head = head.rsplit('\n-- ====', 1)[0]            # bỏ dòng gạch đầu của khối dấu mốc
    legacy = head.replace("'user', 'shipper'", "'user'")
    assert "'shipper'" not in legacy
    return legacy


@pytest.fixture
def legacy_db_factory():
    """Tạo DB 'cũ' (đã có 0001-0005, chưa có Web3) với collation mặc định tùy chọn; tự dọn."""
    created = []

    def make(collation=None):
        name = f"slopee_legacy_{os.getpid()}_{len(created)}"
        admin = _connect()
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {name}")
            extra = f" CHARACTER SET utf8mb4 COLLATE {collation}" if collation else ""
            cur.execute(f"CREATE DATABASE {name}{extra}")
        admin.close()
        created.append(name)
        conn = _connect(name)
        with conn.cursor() as cur:
            for stmt in migrate.split_sql(_legacy_sql()):
                cur.execute(stmt)
        migrate.mark_applied(conn, LEGACY_NAMES)
        return name, conn

    yield make
    admin = _connect()
    with admin.cursor() as cur:
        for name in created:
            cur.execute(f"DROP DATABASE IF EXISTS {name}")
    admin.close()


def _describe(db):
    """Ảnh chụp lược đồ các bảng Web3 (+ users.role) từ information_schema, để so sánh hai DB."""
    conn = _connect()
    snap = {}
    try:
        with conn.cursor() as cur:
            marks = ",".join(["%s"] * len(WEB3_TABLES))
            cur.execute(f"SELECT TABLE_NAME t, ENGINE e, TABLE_COLLATION c FROM information_schema.TABLES "
                        f"WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({marks}) ORDER BY 1", (db, *WEB3_TABLES))
            snap['tables'] = [tuple(r.values()) for r in cur.fetchall()]
            cur.execute(f"SELECT TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA, "
                        f"CHARACTER_SET_NAME, COLLATION_NAME, COLUMN_COMMENT FROM information_schema.COLUMNS "
                        f"WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({marks}) ORDER BY 1,3", (db, *WEB3_TABLES))
            snap['columns'] = [tuple(r.values()) for r in cur.fetchall()]
            cur.execute(f"SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME FROM information_schema.STATISTICS "
                        f"WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({marks}) ORDER BY 1,2,4", (db, *WEB3_TABLES))
            snap['indexes'] = [tuple(r.values()) for r in cur.fetchall()]
            cur.execute(f"SELECT k.TABLE_NAME, k.CONSTRAINT_NAME, k.COLUMN_NAME, k.REFERENCED_TABLE_NAME, k.REFERENCED_COLUMN_NAME, "
                        f"r.DELETE_RULE, r.UPDATE_RULE FROM information_schema.KEY_COLUMN_USAGE k "
                        f"JOIN information_schema.REFERENTIAL_CONSTRAINTS r ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA "
                        f"AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME AND r.TABLE_NAME=k.TABLE_NAME "
                        f"WHERE k.TABLE_SCHEMA=%s AND k.TABLE_NAME IN ({marks}) AND k.REFERENCED_TABLE_NAME IS NOT NULL ORDER BY 1,2,3",
                        (db, *WEB3_TABLES))
            snap['fks'] = [tuple(r.values()) for r in cur.fetchall()]
            cur.execute(f"SELECT tc.TABLE_NAME, cc.CONSTRAINT_NAME, cc.CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS cc "
                        f"JOIN information_schema.TABLE_CONSTRAINTS tc ON tc.CONSTRAINT_SCHEMA=cc.CONSTRAINT_SCHEMA "
                        f"AND tc.CONSTRAINT_NAME=cc.CONSTRAINT_NAME WHERE tc.TABLE_SCHEMA=%s AND tc.TABLE_NAME IN ({marks}) ORDER BY 1,2",
                        (db, *WEB3_TABLES))
            snap['checks'] = [tuple(r.values()) for r in cur.fetchall()]
            cur.execute("SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='users' "
                        "AND COLUMN_NAME='role'", (db,))
            snap['users.role'] = cur.fetchone()['COLUMN_TYPE']
            cur.execute("SELECT AUTO_INCREMENT a FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME='onchain_id_seq'", (db,))
            snap['seq_start'] = cur.fetchone()['a']
            cur.execute(f"SELECT setting_key, setting_value FROM `{db}`.platform_settings ORDER BY 1")
            snap['settings'] = [tuple(r.values()) for r in cur.fetchall()]
            cur.execute(f"SELECT policy_code, inspection_duration, dispute_timeout, is_default FROM `{db}`.category_policies ORDER BY 1")
            snap['policies'] = [tuple(r.values()) for r in cur.fetchall()]
    finally:
        conn.close()
    return snap


def _user(cur, role='user'):
    uid = str(uuid.uuid4())
    cur.execute("INSERT INTO users (id, role, name, email, phone) VALUES (%s,%s,%s,%s,%s)",
                (uid, role, f"{role}-{uid[:6]}", f"{uid[:12]}@t.io", uid.replace('-', '')[:10]))
    return uid


def _order(cur, uid):
    oid = str(uuid.uuid4())
    cur.execute("INSERT INTO orders (id, userId, status, totalAmount) VALUES (%s,%s,'pending',100000)", (oid, uid))
    return oid


def _group(cur, buyer, count=1):
    gid = str(uuid.uuid4())
    cur.execute("INSERT INTO checkout_groups (group_id, buyer_user_id, token_address, total_amount_raw, order_count) "
                "VALUES (%s,%s,NULL,'1000000',%s)", (gid, buyer, count))
    return gid


_seq = iter(range(100001, 10**9))


def _web3_order(cur, buyer, merchant, oid=None, group=None, onchain=None, fee=300, status='PENDING_PAYMENT'):
    oid = oid or _order(cur, buyer)
    group = group or _group(cur, buyer)
    cur.execute("INSERT INTO order_web3 (order_id, onchain_order_id, buyer_user_id, merchant_user_id, shop_id, checkout_group_id, "
                "buyer_wallet, merchant_wallet, amount_raw, price_vnd, fx_vnd_per_token, fee_bps, inspection_duration, "
                "dispute_timeout, doc_hash, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'1000000',100000,25000.0000,%s,259200,2592000,%s,%s)",
                (oid, onchain if onchain is not None else next(_seq), buyer, merchant, str(uuid.uuid4()), group,
                 ADDR_A, ADDR_B, fee, HASH, status))
    return oid


def _errno(exc_info):
    return exc_info.value.args[0]


# ------------------------------------------------------------------------------- (1) DB mới từ schema.sql
def test_fresh_database_has_all_web3_tables_and_marks_migrations_applied(db_conn):
    cur = db_conn.cursor()
    cur.execute("SELECT TABLE_NAME t FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()")
    have = {r['t'] for r in cur.fetchall()}
    assert set(WEB3_TABLES) <= have
    cur.execute("SELECT version FROM schema_migrations")
    assert set(WEB3_NAMES) <= {r['version'] for r in cur.fetchall()}, "init_db phải đánh dấu 0006..0020 đã áp dụng"
    cur.execute("SELECT COLUMN_TYPE c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='users' AND COLUMN_NAME='role'")
    assert cur.fetchone()['c'] == "enum('admin','seller','user','shipper')"


def test_seed_data_present_in_fresh_database(db_conn):
    cur = db_conn.cursor()
    cur.execute("SELECT setting_key k, setting_value v FROM platform_settings")
    assert {r['k']: r['v'] for r in cur.fetchall()} == {
        'PLATFORM_FEE_BPS': '300', 'QUOTE_TTL_SECONDS': '900',
        'FX_VND_PER_TOKEN': '25000', 'DISPUTE_SIG_TTL_SECONDS': '604800',
    }
    cur.execute("SELECT policy_code p, inspection_duration i, dispute_timeout d, is_default x FROM category_policies ORDER BY p")
    rows = {r['p']: (r['i'], r['d'], r['x']) for r in cur.fetchall()}
    assert rows == {'CUSTOM_BULKY': (1209600, 5184000, 0), 'ELECTRONICS': (604800, 3888000, 0),
                    'GENERAL': (259200, 2592000, 1), 'PERISHABLE': (7200, 604800, 0)}


# ------------------------------------------------------------------------- (2) nâng cấp == tạo mới (parity)
def test_upgrade_from_legacy_database_equals_fresh_schema(mysql_db, legacy_db_factory):
    name, conn = legacy_db_factory()
    applied = migrate.migrate(conn, log=lambda *_: None)
    assert applied == WEB3_NAMES, "chạy đúng 15 migration Web3, theo thứ tự số"
    assert _describe(name) == _describe(mysql_db), "lược đồ nâng cấp phải GIỐNG HỆT lược đồ của DB tạo mới từ schema.sql"


def test_migrate_is_idempotent_and_reapplying_every_file_is_harmless(legacy_db_factory):
    name, conn = legacy_db_factory()
    migrate.migrate(conn, log=lambda *_: None)
    assert migrate.migrate(conn, log=lambda *_: None) == []              # chạy lần hai: không có gì để làm
    with conn.cursor() as cur:
        cur.execute("UPDATE platform_settings SET setting_value='450' WHERE setting_key='PLATFORM_FEE_BPS'")
        cur.execute("UPDATE category_policies SET inspection_duration=7200 WHERE policy_code='GENERAL'")
        placeholders = ",".join(["%s"] * len(WEB3_NAMES))
        cur.execute(f"DELETE FROM schema_migrations WHERE version IN ({placeholders})", WEB3_NAMES)  # ép chạy lại cả 15 tệp
    assert migrate.migrate(conn, log=lambda *_: None) == WEB3_NAMES
    with conn.cursor() as cur:
        cur.execute("SELECT setting_value v FROM platform_settings WHERE setting_key='PLATFORM_FEE_BPS'")
        assert cur.fetchone()['v'] == '450', "chạy lại không được đè giá trị Admin đã sửa"
        cur.execute("SELECT inspection_duration i FROM category_policies WHERE policy_code='GENERAL'")
        assert cur.fetchone()['i'] == 7200


# ------------------------------------------------------------- (4) phòng vệ: charset/collation khác mặc định
def test_defensive_migration_matches_parent_collation_when_database_default_differs(legacy_db_factory):
    """DB cũ dùng utf8mb4_unicode_ci (khác mặc định 0900_ai_ci của bảng mới): nếu cột con không khớp cột cha,
    MySQL từ chối khóa ngoại (errno 3780/150). Migration phòng vệ đọc information_schema nên vẫn tạo được."""
    name, conn = legacy_db_factory(collation='utf8mb4_unicode_ci')
    with conn.cursor() as cur:
        cur.execute("SELECT COLLATION_NAME c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                    "AND TABLE_NAME='orders' AND COLUMN_NAME='id'")
        assert cur.fetchone()['c'] == 'utf8mb4_unicode_ci'                 # xác nhận tiền đề của tình huống
    assert migrate.migrate(conn, log=lambda *_: None) == WEB3_NAMES
    with conn.cursor() as cur:
        def collation(table, column):
            cur.execute("SELECT COLLATION_NAME x FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                        "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (table, column))
            return cur.fetchone()['x']
        # cột con tham chiếu bảng Slopee cũ phải mang collation của bảng cũ (unicode_ci), không phải mặc định 0900_ai_ci
        for table, column in [('order_web3', 'order_id'), ('order_web3', 'buyer_user_id'), ('order_web3', 'merchant_user_id'),
                              ('user_wallets', 'user_id'), ('checkout_groups', 'buyer_user_id'), ('order_quotes', 'order_id'),
                              ('dispute_resolutions', 'order_id'), ('shipper_assignments', 'order_id'),
                              ('shipper_assignments', 'shipper_user_id')]:
            assert collation(table, column) == 'utf8mb4_unicode_ci', (table, column)
        # cột tham chiếu bảng Web3 MỚI thì khớp cột cha mới (checkout_groups.group_id): quy tắc là "khớp cột cha"
        assert collation('order_web3', 'checkout_group_id') == collation('checkout_groups', 'group_id')
        # và khóa ngoại thật sự dùng được
        buyer, merchant = _user(cur), _user(cur, 'seller')
        _web3_order(cur, buyer, merchant)


def test_naive_ddl_would_fail_on_collation_mismatch_proving_the_defense_is_needed(legacy_db_factory):
    """Đối chứng: cùng DB unicode_ci, DDL "ngây thơ" (không chỉ định collation) làm khóa ngoại lỗi."""
    name, conn = legacy_db_factory(collation='utf8mb4_unicode_ci')
    with conn.cursor() as cur:
        with pytest.raises(pymysql.err.MySQLError) as e:
            cur.execute("CREATE TABLE naive_child (order_id varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL PRIMARY KEY, "
                        "CONSTRAINT fk_naive FOREIGN KEY (order_id) REFERENCES orders(id)) ENGINE=InnoDB")
        assert _errno(e) in (3780, 1215, 150)


def test_require_innodb_rejects_myisam_and_missing_tables(db_conn):
    cur = db_conn.cursor()
    cur.execute("CREATE TABLE t_myisam (id varchar(36) PRIMARY KEY) ENGINE=MyISAM")
    try:
        with pytest.raises(dbschema.SchemaError, match="MyISAM.*InnoDB"):
            dbschema.require_innodb(cur, 't_myisam')
        with pytest.raises(dbschema.SchemaError, match="chưa tồn tại"):
            dbschema.require_innodb(cur, 'khong_co_bang_nay')
        dbschema.require_innodb(cur, 'orders')                              # InnoDB: không ném lỗi
    finally:
        cur.execute("DROP TABLE IF EXISTS t_myisam")


def test_column_like_reports_type_charset_and_collation(db_conn):
    cur = db_conn.cursor()
    assert dbschema.column_like(cur, 'orders', 'id').startswith("varchar(36) CHARACTER SET utf8mb4 COLLATE ")
    assert dbschema.column_like(cur, 'categories', 'id') == "int unsigned"   # cột số: không kèm charset
    with pytest.raises(dbschema.SchemaError):
        dbschema.column_like(cur, 'orders', 'khong_co_cot')


def test_migration_stops_with_clear_error_when_parent_table_is_not_innodb(legacy_db_factory):
    name, conn = legacy_db_factory()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE orderLines")                                # khóa ngoại trỏ TỚI orders
        cur.execute("SELECT CONSTRAINT_NAME n FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() "
                    "AND TABLE_NAME='orders' AND CONSTRAINT_TYPE='FOREIGN KEY'")
        for row in cur.fetchall():                                          # khóa ngoại đi RA từ orders
            cur.execute(f"ALTER TABLE orders DROP FOREIGN KEY `{row['n']}`")
        cur.execute("ALTER TABLE orders ENGINE=MyISAM")
    # 0006/0007 (chỉ cần users) chạy được; 0008 phải DỪNG với thông báo rõ và KHÔNG được ghi vào schema_migrations
    with pytest.raises(dbschema.SchemaError, match="orders.*MyISAM"):
        migrate.migrate(conn, log=lambda *_: None)
    with conn.cursor() as cur:
        cur.execute("SELECT version v FROM schema_migrations")
        done = {r['v'] for r in cur.fetchall()}
    assert '0007_checkout_groups.py' in done and '0008_order_web3.py' not in done


# ------------------------------------------------------------------------------- (5) ràng buộc thật sự chặn
def test_fee_cap_and_onchain_id_checks(db_conn):
    cur = db_conn.cursor()
    buyer, merchant = _user(cur), _user(cur, 'seller')
    _web3_order(cur, buyer, merchant, fee=1000)                              # đúng trần: được
    with pytest.raises(pymysql.err.MySQLError) as e:
        _web3_order(cur, buyer, merchant, fee=1001)
    assert _errno(e) == 3819                                                  # chk_fee
    with pytest.raises(pymysql.err.MySQLError) as e:
        _web3_order(cur, buyer, merchant, onchain=2**53)                      # chk_onchain_id
    assert _errno(e) == 3819
    _web3_order(cur, buyer, merchant, onchain=2**53 - 1)                      # biên cuối còn an toàn cho JavaScript


def test_unique_onchain_order_id(db_conn):
    cur = db_conn.cursor()
    buyer, merchant = _user(cur), _user(cur, 'seller')
    _web3_order(cur, buyer, merchant, onchain=555_000_001)
    with pytest.raises(pymysql.err.IntegrityError) as e:
        _web3_order(cur, buyer, merchant, onchain=555_000_001)
    assert _errno(e) == 1062


def test_order_web3_is_one_to_one_with_orders_and_restrict_on_delete(db_conn):
    cur = db_conn.cursor()
    buyer, merchant = _user(cur), _user(cur, 'seller')
    oid = _web3_order(cur, buyer, merchant)
    with pytest.raises(pymysql.err.IntegrityError) as e:                      # PRIMARY KEY order_id: một đơn một dòng
        _web3_order(cur, buyer, merchant, oid=oid)
    assert _errno(e) == 1062
    with pytest.raises(pymysql.err.IntegrityError) as e:                      # ON DELETE RESTRICT: không xóa đơn gốc
        cur.execute("DELETE FROM orders WHERE id=%s", (oid,))
    assert _errno(e) == 1451
    with pytest.raises(pymysql.err.IntegrityError) as e:                      # ... cũng không xóa người mua/người bán
        cur.execute("DELETE FROM users WHERE id=%s", (buyer,))
    assert _errno(e) == 1451
    with pytest.raises(pymysql.err.IntegrityError) as e:
        cur.execute("DELETE FROM users WHERE id=%s", (merchant,))
    assert _errno(e) == 1451


def test_order_web3_rejects_unknown_parent_rows(db_conn):
    cur = db_conn.cursor()
    buyer, merchant = _user(cur), _user(cur, 'seller')
    with pytest.raises(pymysql.err.IntegrityError) as e:                      # orders.id không tồn tại
        _web3_order(cur, buyer, merchant, oid=str(uuid.uuid4()))
    assert _errno(e) == 1452
    with pytest.raises(pymysql.err.IntegrityError) as e:                      # lô thanh toán không tồn tại
        _web3_order(cur, buyer, merchant, group=str(uuid.uuid4()))
    assert _errno(e) == 1452


def test_status_enum_and_defaults(db_conn):
    cur = db_conn.cursor()
    buyer, merchant = _user(cur), _user(cur, 'seller')
    with pytest.raises(pymysql.err.MySQLError):
        _web3_order(cur, buyer, merchant, status='SHIPPED')                   # không thuộc ENUM
    oid = _web3_order(cur, buyer, merchant)
    cur.execute("SELECT status, policy_code, payment_method, token_symbol, anomaly_flag FROM order_web3 WHERE order_id=%s", (oid,))
    assert cur.fetchone() == {'status': 'PENDING_PAYMENT', 'policy_code': 'GENERAL', 'payment_method': 'CRYPTO_ESCROW',
                              'token_symbol': 'mUSD', 'anomaly_flag': 0}


def test_amount_raw_keeps_full_uint256_without_precision_loss(db_conn):
    cur = db_conn.cursor()
    buyer, merchant = _user(cur), _user(cur, 'seller')
    oid = _web3_order(cur, buyer, merchant)
    big = str(2**256 - 1)                                                     # 78 chữ số: gấp xa giới hạn DOUBLE/BIGINT
    assert len(big) == 78
    cur.execute("UPDATE order_web3 SET amount_raw=%s WHERE order_id=%s", (big, oid))
    cur.execute("SELECT amount_raw FROM order_web3 WHERE order_id=%s", (oid,))
    assert cur.fetchone()['amount_raw'] == big


def test_checkout_group_order_count_between_1_and_5(db_conn):
    cur = db_conn.cursor()
    buyer = _user(cur)
    for ok in (1, 5):
        _group(cur, buyer, ok)
    for bad in (0, 6):
        with pytest.raises(pymysql.err.MySQLError) as e:
            _group(cur, buyer, bad)
        assert _errno(e) in (3819, 1264)                                      # CHECK, hoặc TINYINT khi vượt khoảng


def test_user_wallets_unique_address_and_cascade_delete(db_conn):
    cur = db_conn.cursor()
    u1, u2 = _user(cur), _user(cur)
    cur.execute("INSERT INTO user_wallets (user_id, address) VALUES (%s,%s)", (u1, ADDR_A))
    with pytest.raises(pymysql.err.IntegrityError) as e:                      # một ví chỉ thuộc một tài khoản (BR-07)
        cur.execute("INSERT INTO user_wallets (user_id, address) VALUES (%s,%s)", (u2, ADDR_A))
    assert _errno(e) == 1062
    cur.execute("INSERT INTO user_wallets (user_id, address) VALUES (%s,%s)", (u1, ADDR_B))
    cur.execute("DELETE FROM users WHERE id=%s", (u1,))                       # CASCADE: xóa người dùng dọn ví
    cur.execute("SELECT COUNT(*) c FROM user_wallets WHERE user_id=%s", (u1,))
    assert cur.fetchone()['c'] == 0


def test_chain_events_unique_tx_hash_log_index_is_idempotency_guard(db_conn):
    cur = db_conn.cursor()
    sql = ("INSERT INTO chain_events (tx_hash, log_index, event_name, order_id, block_number, block_hash, block_timestamp, payload_json) "
           "VALUES (%s,%s,'OrderCreated',100001,5,%s,1700000000,'{}')")
    cur.execute(sql, (HASH, 0, HASH))
    cur.execute(sql, (HASH, 1, HASH))                                         # cùng tx, log khác: nạp gom phát nhiều OrderCreated
    with pytest.raises(pymysql.err.IntegrityError) as e:
        cur.execute(sql, (HASH, 0, HASH))                                     # xử lý lại cùng sự kiện: bị chặn
    assert _errno(e) == 1062
    with pytest.raises(pymysql.err.MySQLError):                               # payload phải là JSON hợp lệ
        cur.execute("INSERT INTO chain_events (tx_hash, log_index, event_name, block_number, block_hash, block_timestamp, payload_json) "
                    "VALUES (%s,9,'X',1,%s,1,'không phải json')", (HASH, HASH))


def test_dispute_resolution_flow_tables(db_conn):
    cur = db_conn.cursor()
    buyer, merchant = _user(cur), _user(cur, 'seller')
    oid = _web3_order(cur, buyer, merchant)
    cur.execute("INSERT INTO dispute_resolutions (order_id, payout_to, amount_raw, nonce, deadline, created_by_admin) "
                "VALUES (%s,%s,'1000000',0,1700000000,%s)", (oid, ADDR_A, buyer))
    rid = cur.lastrowid
    cur.execute("SELECT status FROM dispute_resolutions WHERE id=%s", (rid,))
    assert cur.fetchone()['status'] == 'PROPOSED'
    sig = "0x" + "e" * 130
    for party in ('BUYER', 'ARBITRATOR'):
        cur.execute("INSERT INTO dispute_signatures (resolution_id, party, signer_address, signature) VALUES (%s,%s,%s,%s)",
                    (rid, party, ADDR_C, sig))
    with pytest.raises(pymysql.err.IntegrityError) as e:                      # mỗi bên một chữ ký cho một đề xuất
        cur.execute("INSERT INTO dispute_signatures (resolution_id, party, signer_address, signature) VALUES (%s,'BUYER',%s,%s)",
                    (rid, ADDR_C, sig))
    assert _errno(e) == 1062
    with pytest.raises(pymysql.err.IntegrityError) as e:                      # đề xuất cho đơn không tồn tại
        cur.execute("INSERT INTO dispute_resolutions (order_id, payout_to, amount_raw, nonce, deadline, created_by_admin) "
                    "VALUES (%s,%s,'1',0,1,%s)", (str(uuid.uuid4()), ADDR_A, buyer))
    assert _errno(e) == 1452


def test_order_quotes_store_json_and_require_existing_order(db_conn):
    cur = db_conn.cursor()
    buyer, merchant = _user(cur), _user(cur, 'seller')
    oid = _web3_order(cur, buyer, merchant)
    cur.execute("INSERT INTO order_quotes (order_id, quote_json, signature, deadline) VALUES (%s,%s,%s,1700000900)",
                (oid, '{"feeBps": 300, "buyer": "%s"}' % ADDR_A, "0x" + "f" * 130))
    cur.execute("SELECT JSON_EXTRACT(quote_json,'$.feeBps') f FROM order_quotes WHERE order_id=%s", (oid,))
    assert int(cur.fetchone()['f']) == 300
    with pytest.raises(pymysql.err.IntegrityError) as e:
        cur.execute("INSERT INTO order_quotes (order_id, quote_json, signature, deadline) VALUES (%s,'{}','0x',1)", (str(uuid.uuid4()),))
    assert _errno(e) == 1452


def test_category_policy_checks_match_contract_bounds(db_conn):
    cur = db_conn.cursor()
    ins = "INSERT INTO category_policies (policy_code, display_name, inspection_duration, dispute_timeout) VALUES (%s,'x',%s,%s)"
    cur.execute(ins, ('LO_MIN', 3600, 604800))                                # biên dưới của cả hai
    cur.execute(ins, ('LO_MAX', 2592000, 7776000))                            # biên trên của cả hai
    for code, insp, tmo in (('B1', 3599, 604800), ('B2', 2592001, 604800), ('B3', 3600, 604799), ('B4', 3600, 7776001)):
        with pytest.raises(pymysql.err.MySQLError) as e:
            cur.execute(ins, (code, insp, tmo))
        assert _errno(e) == 3819


def test_category_policy_map_links_categories_to_policies(db_conn):
    cur = db_conn.cursor()
    cur.execute("INSERT INTO categories (name) VALUES ('Thực phẩm')")
    cat = cur.lastrowid
    cur.execute("INSERT INTO category_policy_map (category_id, policy_code) VALUES (%s,'PERISHABLE')", (cat,))
    with pytest.raises(pymysql.err.IntegrityError) as e:                      # nhóm chính sách không tồn tại
        cur.execute("INSERT INTO category_policy_map (category_id, policy_code) VALUES (%s,'KHONG_CO')", (cat + 1000,))
    assert _errno(e) == 1452
    with pytest.raises(pymysql.err.IntegrityError) as e:                      # không xóa được nhóm đang được gán
        cur.execute("DELETE FROM category_policies WHERE policy_code='PERISHABLE'")
    assert _errno(e) == 1451
    cur.execute("DELETE FROM categories WHERE id=%s", (cat,))                 # xóa danh mục: bản ánh xạ tự dọn (CASCADE)
    cur.execute("SELECT COUNT(*) c FROM category_policy_map WHERE category_id=%s", (cat,))
    assert cur.fetchone()['c'] == 0


def test_onchain_id_seq_starts_at_100001_and_is_monotonic(db_conn):
    cur = db_conn.cursor()
    ids = []
    for _ in range(3):
        cur.execute("INSERT INTO onchain_id_seq () VALUES ()")
        ids.append(cur.lastrowid)
    assert ids[0] >= 100001 and ids == sorted(ids) and len(set(ids)) == 3
    assert ids[-1] < 2**53


def test_pending_balances_primary_key_and_default(db_conn):
    cur = db_conn.cursor()
    zero = '0x' + '0' * 40
    cur.execute("INSERT INTO pending_balances (token_address, address) VALUES (%s,%s)", (zero, ADDR_A))
    cur.execute("SELECT amount_raw FROM pending_balances WHERE token_address=%s AND address=%s", (zero, ADDR_A))
    assert cur.fetchone()['amount_raw'] == '0'
    with pytest.raises(pymysql.err.IntegrityError) as e:
        cur.execute("INSERT INTO pending_balances (token_address, address) VALUES (%s,%s)", (zero, ADDR_A))
    assert _errno(e) == 1062


def test_shipper_role_and_assignment(db_conn):
    cur = db_conn.cursor()
    shipper = _user(cur, 'shipper')                                           # ENUM đã có 'shipper'
    buyer, merchant = _user(cur), _user(cur, 'seller')
    oid = _web3_order(cur, buyer, merchant)
    cur.execute("INSERT INTO shipper_assignments (order_id, shipper_user_id, assigned_by) VALUES (%s,%s,%s)", (oid, shipper, merchant))
    with pytest.raises(pymysql.err.IntegrityError) as e:                      # mỗi đơn đúng một Shipper
        cur.execute("INSERT INTO shipper_assignments (order_id, shipper_user_id) VALUES (%s,%s)", (oid, shipper))
    assert _errno(e) == 1062
    with pytest.raises(pymysql.err.IntegrityError) as e:                      # Shipper phải là người dùng có thật
        cur.execute("INSERT INTO shipper_assignments (order_id, shipper_user_id) VALUES (%s,%s)",
                    (_web3_order(cur, buyer, merchant), str(uuid.uuid4())))
    assert _errno(e) == 1452
    with pytest.raises(pymysql.err.MySQLError):                               # vai trò ngoài ENUM bị từ chối
        _user(cur, 'hacker')
