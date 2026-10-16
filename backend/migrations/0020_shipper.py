"""Web3 (SRS 9 bảng 0 và 15, SDD 7.3 #6): vai trò Shipper và bảng gán đơn cho Shipper.

1) Thêm giá trị `shipper` vào CUỐI ENUM `users.role` (chỉ đổi metadata, không viết lại dữ liệu). Đăng ký công khai vẫn chỉ
   cho `user`/`seller` (P0-02); Shipper chỉ tạo bằng CLI/Admin. MODIFY lặp lại trên ENUM đã đúng là vô hại (idempotent).
2) `shipper_assignments`: mỗi đơn gán đúng một Shipper; `order_id`/`shipper_user_id` khớp kiểu cột cha.
SDD `015_shipper.sql` -> `0020_shipper.py`. Idempotent."""
from dbschema import column_like, require_innodb


def upgrade(cursor):
    require_innodb(cursor, 'users')
    require_innodb(cursor, 'order_web3')
    cursor.execute("ALTER TABLE users MODIFY role ENUM('admin','seller','user','shipper') NOT NULL")
    order_id = column_like(cursor, 'order_web3', 'order_id')
    user_id = column_like(cursor, 'users', 'id')
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS shipper_assignments (
            order_id {order_id} NOT NULL PRIMARY KEY,
            shipper_user_id {user_id} NOT NULL,
            assigned_by VARCHAR(36) DEFAULT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_shipper (shipper_user_id),
            CONSTRAINT fk_sa_order FOREIGN KEY (order_id) REFERENCES order_web3(order_id),
            CONSTRAINT fk_sa_shipper FOREIGN KEY (shipper_user_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
