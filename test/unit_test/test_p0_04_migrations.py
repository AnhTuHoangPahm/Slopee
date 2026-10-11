"""P0-04: bỏ /api/shops/migrate, bộ chạy migration có số thứ tự (A-07), dọn schema trùng reviews/reviewImages (S-13)."""
import os
import re

import pytest

import dbschema
import migrate

BACKEND = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
SCHEMA = os.path.join(BACKEND, 'schema.sql')


# ------------------------------------------------------------------ route công khai đã bị xóa
def test_migrate_http_route_is_gone(app, client):
    assert not [r for r in app.url_map.iter_rules() if 'migrate' in r.rule]
    for prefix in ('/api/shop', '/api/shops'):
        assert client.get(f'{prefix}/migrate').status_code in (404, 405)


def test_no_route_source_mentions_migrate_or_alter_table():
    routes_dir = os.path.join(BACKEND, 'routes')
    for name in os.listdir(routes_dir):
        if name.endswith('.py'):
            src = open(os.path.join(routes_dir, name), encoding='utf-8').read()
            assert 'ALTER TABLE' not in src.upper() and '/migrate' not in src, name


# ------------------------------------------------------------------ bộ tách SQL
def test_split_sql_ignores_semicolons_in_comments_and_strings():
    sql = "-- c1; c2\nALTER TABLE a ADD x int; /* y; z */ UPDATE b SET s='a;b''c'; # n;\nSELECT `a;b`"
    assert migrate.split_sql(sql) == ["ALTER TABLE a ADD x int", "UPDATE b SET s='a;b''c'", "SELECT `a;b`"]


def test_split_sql_handles_empty_and_trailing():
    assert migrate.split_sql("") == [] and migrate.split_sql(" ;; \n-- only comment") == []


# ------------------------------------------------------------------ discover / chạy
@pytest.fixture
def mig_dir():
    import tempfile
    d = tempfile.mkdtemp()
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def test_discover_sorts_numerically_and_ignores_other_files(mig_dir):
    for n in ('0010_c.sql', '0002_b.py', '0001_a.sql', 'README.md', 'notes.sql', '_helpers.py'):
        open(os.path.join(mig_dir, n), 'w').write('')
    assert [m.name for m in migrate.discover(mig_dir)] == ['0001_a.sql', '0002_b.py', '0010_c.sql']


def _setup_runner(cur, applied=()):
    cur.on("GET_LOCK", [{"got": 1}])
    cur.on("FROM schema_migrations", [{"version": v} for v in applied])


def test_runner_applies_pending_in_order_and_records(fake_conn, mig_dir):
    open(os.path.join(mig_dir, '0001_a.sql'), 'w').write("-- c; c\nCREATE TABLE a (x int);\nCREATE TABLE b (y int);")
    open(os.path.join(mig_dir, '0002_b.sql'), 'w').write("CREATE TABLE c (z int);")
    _setup_runner(fake_conn)
    done = migrate.migrate(fake_conn.conn, mig_dir, log=lambda *_: None)
    assert done == ['0001_a.sql', '0002_b.sql']
    created = [s for s, _ in fake_conn.calls if s.startswith('CREATE TABLE') and 'schema_migrations' not in s]
    assert created == ["CREATE TABLE a (x int)", "CREATE TABLE b (y int)", "CREATE TABLE c (z int)"]
    recorded = [p for s, p in fake_conn.calls if 'INSERT INTO schema_migrations' in s]
    assert recorded == [('0001_a.sql',), ('0002_b.sql',)]
    assert any('RELEASE_LOCK' in s for s, _ in fake_conn.calls)


def test_runner_skips_applied_and_is_idempotent(fake_conn, mig_dir):
    open(os.path.join(mig_dir, '0001_a.sql'), 'w').write("CREATE TABLE a (x int);")
    _setup_runner(fake_conn, applied=['0001_a.sql'])
    assert migrate.migrate(fake_conn.conn, mig_dir, log=lambda *_: None) == []
    assert not [1 for s, _ in fake_conn.calls if s == "CREATE TABLE a (x int)"]


def test_failed_migration_is_not_recorded_and_stops_the_run(fake_conn, mig_dir):
    open(os.path.join(mig_dir, '0001_bad.sql'), 'w').write("BROKEN STATEMENT;")
    open(os.path.join(mig_dir, '0002_next.sql'), 'w').write("CREATE TABLE n (x int);")
    _setup_runner(fake_conn)

    def boom(sql, params):
        raise RuntimeError("syntax error")
    fake_conn.on("BROKEN", boom)
    with pytest.raises(RuntimeError):
        migrate.migrate(fake_conn.conn, mig_dir, log=lambda *_: None)
    assert not fake_conn.executed("INSERT INTO schema_migrations")
    assert not [1 for s, _ in fake_conn.calls if s == "CREATE TABLE n (x int)"]
    assert any('RELEASE_LOCK' in s for s, _ in fake_conn.calls)  # nhả khóa kể cả khi lỗi


def test_runner_refuses_when_lock_not_acquired(fake_conn, mig_dir):
    fake_conn.on("GET_LOCK", [{"got": 0}])
    with pytest.raises(migrate.MigrationError):
        migrate.migrate(fake_conn.conn, mig_dir, log=lambda *_: None)


def test_python_migration_receives_cursor(fake_conn, mig_dir):
    open(os.path.join(mig_dir, '0001_py.py'), 'w').write("def upgrade(cursor):\n    cursor.execute('SELECT 42')\n")
    _setup_runner(fake_conn)
    assert migrate.migrate(fake_conn.conn, mig_dir, log=lambda *_: None) == ['0001_py.py']
    assert fake_conn.executed('SELECT 42')


def test_mark_applied_records_without_running(fake_conn, mig_dir):
    open(os.path.join(mig_dir, '0001_a.sql'), 'w').write("DROP DATABASE x;")
    assert migrate.mark_applied(fake_conn.conn, directory=mig_dir) == ['0001_a.sql']
    assert fake_conn.executed("INSERT IGNORE INTO schema_migrations") and not fake_conn.executed("DROP DATABASE")
    with pytest.raises(migrate.MigrationError):
        migrate.mark_applied(fake_conn.conn, ['nope.sql'], directory=mig_dir)


def test_real_migrations_directory_is_well_formed():
    found = migrate.discover()
    names = [m.name for m in found]
    assert '0001_money_to_vnd.sql' in names and '0004_auth_attempts.sql' in names
    assert len({m.number for m in found if m.name.startswith('000')}) == len([m for m in found if m.name.startswith('000')])
    for m in found:
        if m.kind == 'sql':
            stmts = migrate.split_sql(open(m.path, encoding='utf-8').read())
            assert stmts and all(s.split()[0].upper() in ('ALTER', 'CREATE', 'UPDATE', 'INSERT', 'DROP') for s in stmts), m.name


# ------------------------------------------------------------------ dbschema (migration 0002/0003)
def test_ensure_foreign_key_noop_when_already_correct(fake_conn):
    fake_conn.on("information_schema.TABLES", [{"name": "cartItems"}])
    fake_conn.on("KEY_COLUMN_USAGE", [{"name": "fk_x", "delete_rule": "CASCADE"}])
    assert dbschema.ensure_foreign_key(fake_conn, 'cartItems', 'productId', 'products', 'id', 'fk_new', 'CASCADE') is False
    assert not [1 for s, _ in fake_conn.calls if s.startswith('ALTER')]


def test_ensure_foreign_key_replaces_wrong_rule(fake_conn):
    fake_conn.on("information_schema.TABLES", [{"name": "cartItems"}])
    fake_conn.on("KEY_COLUMN_USAGE", [{"name": "cartitems_ibfk_2", "delete_rule": "RESTRICT"}])
    assert dbschema.ensure_foreign_key(fake_conn, 'cartItems', 'productId', 'products', 'id', 'fk_new', 'CASCADE') is True
    alters = [s for s, _ in fake_conn.calls if s.startswith('ALTER')]
    assert "DROP FOREIGN KEY `cartitems_ibfk_2`" in alters[0]
    assert "ADD CONSTRAINT `fk_new`" in alters[1] and "ON DELETE CASCADE" in alters[1]


def test_migrations_use_current_database_not_hardcoded_schema():
    for name in os.listdir(os.path.join(BACKEND, 'migrations')):
        src = open(os.path.join(BACKEND, 'migrations', name), encoding='utf-8').read()
        assert 'slopee_db' not in src, name
    assert 'slopee_db' not in open(os.path.join(BACKEND, 'dbschema.py'), encoding='utf-8').read()


# ------------------------------------------------------------------ schema.sql gộp (S-13)
def _schema():
    return open(SCHEMA, encoding='utf-8').read()


@pytest.mark.parametrize("table", ["reviews", "reviewImages", "authAttempts"])
def test_each_table_declared_exactly_once(table):
    assert len(re.findall(rf"CREATE TABLE IF NOT EXISTS {table}\b", _schema())) == 1


def test_schema_statements_are_all_creates_and_splittable():
    stmts = migrate.split_sql(_schema())
    assert len(stmts) >= 15 and all(s.startswith('CREATE TABLE') for s in stmts)


def test_reviews_keeps_unique_review_per_user_product():
    block = re.search(r"CREATE TABLE IF NOT EXISTS reviews \((.*?)\n\);", _schema(), re.S).group(1)
    assert re.search(r"UNIQUE.*\(userId,\s*productId\)", block, re.I) and "NOT NULL" in block


def test_review_images_get_uuid_from_backend(client, fake_db, auth_headers):
    """S-13: INSERT reviewImages phải cấp id (VARCHAR(36), không tự tăng) -> hết lỗi 1364 ở MySQL strict."""
    cur = fake_db('backend.routes.reviews')
    cur.on("FROM orders o", [{"status": "paid"}])
    cur.on("FROM reviews WHERE", [])
    r = client.post('/api/reviews/p1', headers=auth_headers,
                    json={"rating": 5, "comment": "Great", "images": ["https://img.io/a.png", "https://img.io/b.png"]})
    assert r.status_code == 201
    inserts = cur.executed("INSERT INTO reviewImages")
    assert len(inserts) == 2
    for sql, params in inserts:
        assert "(id, reviewId, imageUrl)" in sql and len(params) == 3 and len(params[0]) == 36
    assert inserts[0][1][0] != inserts[1][1][0]


def test_schema_declares_composite_baseline_for_new_installs():
    s = _schema()
    assert re.search(r"cartItems.*?on delete cascade", s, re.S | re.I)
    assert re.search(r"productId varchar\(15\) NULL", s)  # orderLines.productId cho phép NULL (SET NULL)
