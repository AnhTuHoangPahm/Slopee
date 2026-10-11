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
