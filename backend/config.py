import os

from auth_utils import get_secret_key


def is_development():
    """P0-06: chỉ bật debug khi SLOPEE_ENV=development (mặc định/production -> tắt)."""
    return os.environ.get('SLOPEE_ENV', '').lower() == 'development'


class Config:
    # Database configuration
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_NAME = os.environ.get('DB_NAME', 'slopee_db')

    # P0-01: SECRET_KEY bắt buộc lấy từ biến môi trường (không còn giá trị mặc định).
    # Khi chạy local đặt SLOPEE_ENV=development để dùng khoá dev (xem auth_utils.get_secret_key).
    SECRET_KEY = get_secret_key()
    AUTH_TOKEN_TTL_SECONDS = int(os.environ.get('AUTH_TOKEN_TTL_SECONDS', 3600))

    # P0-06: debug (Werkzeug debugger cho phép chạy mã tùy ý) chỉ bật ở môi trường development.
    DEBUG = is_development()
