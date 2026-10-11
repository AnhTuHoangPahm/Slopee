import pytest
from flask import Flask
import sys
import os

# P0-01: auth_utils yêu cầu SECRET_KEY; test dùng khoá dev.
os.environ.setdefault('SLOPEE_ENV', 'test')
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
# Add root folder (Slopee) to path so 'from backend.routes...' works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
# Add backend folder to path so 'from routes...' inside backend works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))
from backend.routes.auth import auth_bp
from backend.routes.carts import carts_bp
from backend.routes.products import products_bp
from backend.routes.shops import shops_bp
from backend.routes.payments import payments_bp
from backend.routes.admin import admin_bp
from backend.routes.reviews import reviews_bp

@pytest.fixture
def app():
    """Create a minimal Flask app to provide the application context and routing."""
    app = Flask(__name__)
    from json_provider import SlopeeJSONProvider
    app.json = SlopeeJSONProvider(app)  # giống app.py: Decimal -> số
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(carts_bp, url_prefix='/api/cart')
    app.register_blueprint(products_bp, url_prefix='/api/products')
    app.register_blueprint(shops_bp, url_prefix='/api/shop')
    app.register_blueprint(payments_bp, url_prefix='/api/checkout')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(reviews_bp, url_prefix='/api/reviews')
    return app

@pytest.fixture
def client(app):
    """Provides a simulated browser client to make POST requests without a real server running."""
    return app.test_client()

@pytest.fixture
def mock_db_cursor(mocker):
    """Reusable fixture that patches the DB connection globally and returns a fake cursor."""
    # Note: We can patch it at the app level, but since get_db_connection is imported everywhere, 
    # we should patch the specific module where it's used. Since we don't know which route will be called
    # we can patch multiple, or just let individual tests patch their specific route.
    # Actually, a better global mock is to patch the database library directly, or patch all routes.
    # Let's keep it simple for now and just return the MagicMock components.
    pass


@pytest.fixture
def make_auth_headers():
    """Tạo header Authorization hợp lệ cho một user_id/role bất kỳ."""
    from auth_utils import issue_token

    def _make(user_id='fake-user-id', role='user'):
        return {'Authorization': f'Bearer {issue_token(user_id, role)}'}
    return _make


@pytest.fixture
def auth_headers(make_auth_headers):
    return make_auth_headers('fake-user-id', 'user')


@pytest.fixture
def seller_headers(make_auth_headers):
    return make_auth_headers('fake-seller-id', 'seller')


# ---------------------------------------------------------------------------
# MySQL thật (P0-08): dùng cho integration test / race condition.
# Kết nối qua DB_HOST / DB_USER / DB_PASSWORD (cùng biến env mà các route dùng).
# Mỗi phiên test tạo một database riêng (slopee_test_<pid>) từ schema.sql rồi xóa đi.
# Không kết nối được MySQL -> test bị skip (CI chạy với MySQL service, xem .github/workflows/tests.yml).
# ---------------------------------------------------------------------------
@pytest.fixture(scope='session')
def mysql_db():
    import pymysql
    host = os.environ.get('DB_HOST', 'localhost')
    user = os.environ.get('DB_USER', 'root')
    password = os.environ.get('DB_PASSWORD', '')
    db_name = f"slopee_test_{os.getpid()}"
    try:
        admin = pymysql.connect(host=host, user=user, password=password, connect_timeout=3)
    except pymysql.err.OperationalError as e:
        pytest.skip(f"MySQL service not available: {e}")
    admin.close()

    old_name = os.environ.get('DB_NAME')
    os.environ['DB_NAME'] = db_name
    import init_db
    init_db.init_database()
    yield db_name

    conn = pymysql.connect(host=host, user=user, password=password)
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
    conn.commit()
    conn.close()
    if old_name is None:
        os.environ.pop('DB_NAME', None)
    else:
        os.environ['DB_NAME'] = old_name


@pytest.fixture
def db_conn(mysql_db):
    """Kết nối trực tiếp tới DB test để seed dữ liệu / kiểm tra kết quả."""
    import pymysql
    conn = pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=mysql_db,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# FakeCursor: cursor giả trả dữ liệu theo NỘI DUNG câu SQL thay vì theo thứ tự gọi fetchone().
# Test không còn vỡ mỗi khi route thêm/bớt một câu truy vấn; vẫn kiểm được SQL + tham số đã chạy.
#   cur.on("FROM credentials", [{"passPhraseHash": "h"}])      # câu SQL chứa chuỗi này -> trả các dòng này
#   cur.on("UPDATE products", rowcount=0)                      # giả lập UPDATE không khớp dòng nào
#   cur.executed("INSERT INTO orders")                         # -> [(sql, params), ...] đã chạy
# Quy tắc khai báo SAU có ưu tiên cao hơn quy tắc khai báo trước. Không khớp quy tắc nào -> 0 dòng, rowcount 1.
# ---------------------------------------------------------------------------
class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rules = []
        self.calls = []
        self._rows = []
        self.rowcount = 1

    def on(self, fragment, rows=None, rowcount=None):
        self.rules.insert(0, (fragment, rows if rows is not None else [], rowcount))
        return self

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        self._rows, self.rowcount = [], 1
        for fragment, rows, rowcount in self.rules:
            if fragment in sql:
                self._rows = rows(sql, params) if callable(rows) else list(rows)
                if rowcount is not None:
                    self.rowcount = rowcount
                break
        return len(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def executed(self, fragment):
        return [c for c in self.calls if fragment in c[0]]


@pytest.fixture
def fake_db(mocker):
    """fake_db('backend.routes.payments') -> FakeCursor đã gắn vào get_db_connection của module đó."""
    def _make(module):
        conn = mocker.MagicMock()
        cur = FakeCursor(conn)
        conn.cursor.return_value.__enter__.return_value = cur
        mocker.patch(f'{module}.get_db_connection', return_value=conn)
        return cur
    return _make


@pytest.fixture
def fake_conn(mocker):
    """FakeCursor không gắn vào module nào (dùng cho migrate.py nhận conn trực tiếp). cur.conn là kết nối giả."""
    conn = mocker.MagicMock()
    cur = FakeCursor(conn)
    conn.cursor.return_value.__enter__.return_value = cur
    return cur


class AttemptsStore:
    """Giả lập bảng authAttempts trong bộ nhớ (stateful) trên một FakeCursor, để test chuỗi nhiều request
    (sai 5 lần -> khóa -> hết khóa) mà không cần MySQL. Xem throttle.py."""

    def __init__(self, cur):
        self.rows = {}   # (scope, subject) -> [failedCount, lockedUntil]
        cur.on("FROM authAttempts", self._select)
        cur.on("INSERT IGNORE INTO authAttempts", self._insert)
        cur.on("UPDATE authAttempts SET", self._update)
        cur.on("DELETE FROM authAttempts", self._delete)

    def _select(self, sql, params):
        row = self.rows.get(tuple(params))
        return [{"failedCount": row[0], "lockedUntil": row[1]}] if row else []

    def _insert(self, sql, params):
        self.rows.setdefault(tuple(params), [0, 0])
        return []

    def _update(self, sql, params):
        failed, locked_until, scope, subject = params
        self.rows[(scope, subject)] = [failed, locked_until]
        return []

    def _delete(self, sql, params):
        self.rows.pop(tuple(params), None)
        return []

    def get(self, scope, subject):
        return self.rows.get((scope, subject))


@pytest.fixture
def attempts_store():
    return AttemptsStore
