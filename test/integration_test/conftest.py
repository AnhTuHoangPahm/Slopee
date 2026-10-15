import os

import pytest


@pytest.fixture(scope='module', autouse=True)
def _private_database_for_w3_modules(request, mysql_db):
    """Mỗi module test_w3_* chạy trên DATABASE RIÊNG (tạo mới từ schema.sql, xóa sau khi xong).

    Các test này ghi nhiều dữ liệu dùng chung (ví theo địa chỉ Anvil cố định, id on-chain, platform_settings...);
    dùng chung DB của phiên sẽ làm lệch các test cũ (ví dụ test migration so sánh cả AUTO_INCREMENT)."""
    name = request.module.__name__.split('.')[-1]
    if not name.startswith('test_w3_'):
        yield
        return
    import pymysql
    import init_db
    host, user, password = os.environ.get('DB_HOST', 'localhost'), os.environ.get('DB_USER', 'root'), os.environ.get('DB_PASSWORD', '')
    private = f"{mysql_db}_{name[len('test_'):]}"[:60]
    os.environ['DB_NAME'] = private
    try:
        init_db.init_database()
        yield
    finally:
        conn = pymysql.connect(host=host, user=user, password=password)
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{private}`")
        conn.commit()
        conn.close()
        os.environ['DB_NAME'] = mysql_db
