"""Web3 (SRS 9, bảng 1-2): ví đã liên kết (BR-07) và nonce liên kết ví dùng một lần (UC-00).

SDD `001_wallets.sql` -> `0006_wallets.py` (bù +5, xem PROGRESS.md quyết định 4).
`user_id` lấy kiểu/charset/collation từ `users.id` (đọc information_schema) để khóa ngoại không lỗi errno 150.
Địa chỉ ví lưu CHỮ THƯỜNG; UNIQUE(address) bảo đảm một ví chỉ thuộc một tài khoản. Idempotent.
"""
from dbschema import column_like, require_innodb


def upgrade(cursor):
    require_innodb(cursor, 'users')
    user_id = column_like(cursor, 'users', 'id')
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS user_wallets (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id {user_id} NOT NULL,
            address CHAR(42) NOT NULL COMMENT 'chữ thường để so khớp',
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_wallet_address (address),
            INDEX idx_wallet_user (user_id, is_active),
            CONSTRAINT fk_wallet_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallet_nonces (
            nonce CHAR(32) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP NULL DEFAULT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
