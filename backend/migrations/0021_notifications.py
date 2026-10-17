"""Web3 tuần 5 (UC-03 bước 3, SDD 5.2 NotificationPort, SDD 5.5 DeliveryTimeoutReminder): bảng thông báo cho người dùng.

Slopee chưa có bảng thông báo (SDD 7.3 chỉ ghi "bảng thông báo của Slopee"), nên tạo mới. `UNIQUE(user_id, order_id, kind)` vừa
chống gửi trùng (Indexer chạy lại cùng sự kiện, tác vụ nhắc chạy lặp) vừa là cờ "đã nhắc" của DeliveryTimeoutReminder.
`user_id` lấy kiểu/charset/collation từ `users.id` để khóa ngoại không lỗi errno 150 (Q-06). Xóa người dùng thì thông báo
đi theo (thông báo không phải hồ sơ tiền). `order_id` KHÔNG có khóa ngoại để thông báo tồn tại độc lập với vòng đời đơn. Idempotent.
"""
from dbschema import column_like, require_innodb


def upgrade(cursor):
    require_innodb(cursor, 'users')
    user_id = column_like(cursor, 'users', 'id')
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS notifications (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id {user_id} NOT NULL,
            order_id VARCHAR(36) NOT NULL,
            kind VARCHAR(40) NOT NULL COMMENT 'ORDER_DELIVERED, DELIVERY_TIMEOUT',
            message VARCHAR(500) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            read_at TIMESTAMP NULL DEFAULT NULL,
            UNIQUE KEY uk_notification (user_id, order_id, kind),
            INDEX idx_notification_user (user_id, created_at),
            CONSTRAINT fk_notification_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
