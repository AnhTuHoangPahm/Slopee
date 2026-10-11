import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from auth_utils import get_secret_key


class Config:
    # Database configuration
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = int(os.environ.get('DB_PORT') or 3306)
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_NAME = os.environ.get('DB_NAME', 'slopee_db')

    # P0-01: SECRET_KEY bắt buộc lấy từ biến môi trường (không còn giá trị mặc định).
    # Khi chạy local đặt SLOPEE_ENV=development để dùng khoá dev (xem auth_utils.get_secret_key).
    SECRET_KEY = get_secret_key()
    AUTH_TOKEN_TTL_SECONDS = int(os.environ.get('AUTH_TOKEN_TTL_SECONDS', 3600))
