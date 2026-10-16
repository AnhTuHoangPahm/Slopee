"""Bộ chạy migration CSDL có đánh số (P0-04, S-07). KHÔNG có route HTTP.

Dùng:
    python migrate.py            # = up: áp dụng các migration chưa chạy
    python migrate.py status     # liệt kê đã áp dụng / đang chờ
    python migrate.py mark-applied 0001_money_to_vnd.sql   # đánh dấu đã áp dụng thủ công (DB cũ)
    flask --app app migrate [up|status]

Quy ước:
- Tệp trong migrations/ tên `<số>_<mô_tả>.sql` hoặc `.py`, chạy theo (số, tên). Mỗi tệp chạy đúng một lần,
  tên tệp được ghi vào bảng schema_migrations.
- .sql: nhiều câu lệnh, tách bằng dấu `;` NGOÀI chuỗi/chú thích (chú thích `--`, `#`, `/* */` được bỏ qua an toàn).
- .py: định nghĩa `upgrade(cursor)` (dùng dbschema.py để kiểm tra đã áp dụng chưa).
- DDL của MySQL tự commit nên migration không rollback được: hãy viết migration idempotent. Lỗi giữa chừng thì
  runner dừng và KHÔNG ghi tệp đó vào schema_migrations, sửa rồi chạy lại.
- Có khóa GET_LOCK để hai tiến trình không migrate cùng lúc.
- schema.sql là schema đầy đủ mới nhất cho DB tạo mới: mọi migration thêm vào phải được phản ánh trong schema.sql,
  và init_db.py đánh dấu các migration hiện có là đã áp dụng (baseline) thay vì chạy lại.
"""
import importlib.util
import os
import re
import sys

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')
LOCK_NAME = 'slopee_schema_migrations'
LOCK_TIMEOUT_SECONDS = 10
_FILE_RE = re.compile(r'^(\d+)_[\w\-]+\.(sql|py)$')


class MigrationError(Exception):
    pass


def split_sql(script):
    """Tách script SQL thành các câu lệnh, bỏ chú thích, tôn trọng chuỗi '...' "..." và `...`."""
    statements, buf = [], []
    i, n = 0, len(script)
    quote = None
    while i < n:
        c = script[i]
        nxt = script[i + 1] if i + 1 < n else ''
        if quote:
            buf.append(c)
            if c == '\\' and quote != '`' and i + 1 < n:   # ký tự thoát: \'
                buf.append(nxt)
                i += 2
                continue
            if c == quote:
                if nxt == quote:                            # nháy đôi '' là một dấu nháy trong chuỗi
                    buf.append(nxt)
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if c in ("'", '"', '`'):
            quote = c
            buf.append(c)
        elif c == '#' or (c == '-' and nxt == '-' and (i + 2 >= n or script[i + 2] in ' \t\r\n')):
            while i < n and script[i] != '\n':              # chú thích dòng
                i += 1
            continue
        elif c == '/' and nxt == '*':                       # chú thích khối
            end = script.find('*/', i + 2)
            i = n if end == -1 else end + 2
            buf.append(' ')
            continue
        elif c == ';':
            stmt = ''.join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(c)
        i += 1
    tail = ''.join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


class Migration:
    def __init__(self, name, path):
        self.name = name
        self.path = path
        m = _FILE_RE.match(name)
        self.number = int(m.group(1))
        self.kind = m.group(2)

    @property
    def sort_key(self):
        return (self.number, self.name)

    def __repr__(self):
        return f"Migration({self.name})"


def discover(directory=None):
    directory = directory or MIGRATIONS_DIR
    found = []
    for name in os.listdir(directory):
        if _FILE_RE.match(name):
            found.append(Migration(name, os.path.join(directory, name)))
    return sorted(found, key=lambda m: m.sort_key)


def ensure_table(cursor):
    cursor.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                   "version VARCHAR(255) NOT NULL PRIMARY KEY, "
                   "appliedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)")


def applied_versions(cursor):
    cursor.execute("SELECT version FROM schema_migrations")
    return {row['version'] for row in cursor.fetchall()}


def _run_one(cursor, migration):
    if migration.kind == 'sql':
        with open(migration.path, encoding='utf-8') as f:
            for stmt in split_sql(f.read()):
                cursor.execute(stmt)
    else:
        spec = importlib.util.spec_from_file_location(f"slopee_migration_{migration.number}", migration.path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, 'upgrade'):
            raise MigrationError(f"{migration.name}: thiếu hàm upgrade(cursor)")
        module.upgrade(cursor)


def pending(cursor, directory=None):
    ensure_table(cursor)
    done = applied_versions(cursor)
    return [m for m in discover(directory) if m.name not in done]


def migrate(conn, directory=None, log=print):
    """Áp dụng tuần tự các migration chưa chạy. Trả về danh sách tên đã áp dụng."""
    applied = []
    with conn.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, %s) AS got", (LOCK_NAME, LOCK_TIMEOUT_SECONDS))
        if not (cursor.fetchone() or {}).get('got'):
            raise MigrationError("Không lấy được khóa migration: có tiến trình khác đang migrate.")
        try:
            for m in pending(cursor, directory):
                log(f"-> applying {m.name}")
                _run_one(cursor, m)
                cursor.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (m.name,))
                conn.commit()
                applied.append(m.name)
            if not applied:
                log("Database is up to date.")
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
    return applied


def mark_applied(conn, names=None, directory=None):
    """Ghi các migration vào schema_migrations mà KHÔNG chạy. names=None -> tất cả hiện có (dùng cho DB mới
    tạo từ schema.sql đã gồm sẵn mọi thay đổi). Trả về danh sách tên vừa đánh dấu."""
    marked = []
    with conn.cursor() as cursor:
        ensure_table(cursor)
        known = {m.name for m in discover(directory)}
        targets = sorted(known) if names is None else list(names)
        for name in targets:
            if name not in known:
                raise MigrationError(f"Không có migration '{name}'")
            cursor.execute("INSERT IGNORE INTO schema_migrations (version) VALUES (%s)", (name,))
            marked.append(name)
    conn.commit()
    return marked


def status(conn, directory=None, log=print):
    with conn.cursor() as cursor:
        ensure_table(cursor)
        done = applied_versions(cursor)
    for m in discover(directory):
        log(f"[{'x' if m.name in done else ' '}] {m.name}")
    return done


def connect():
    import pymysql
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'slopee_db'),
        cursorclass=pymysql.cursors.DictCursor,
    )


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    action = argv[0] if argv else 'up'
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    conn = connect()
    try:
        if action == 'up':
            migrate(conn)
        elif action == 'status':
            status(conn)
        elif action == 'mark-applied':
            if len(argv) < 2:
                raise SystemExit("usage: migrate.py mark-applied <migration-file> [...]")
            for name in mark_applied(conn, argv[1:]):
                print(f"marked {name}")
        else:
            raise SystemExit(__doc__)
    except MigrationError as e:
        raise SystemExit(f"Migration failed: {e}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
