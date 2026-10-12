"""Web3 (SRS 9, bảng 2b): lô thanh toán = một lần nạp gom, tối đa 5 đơn con (BR-11).

Trạng thái của lô được SUY RA từ các đơn con (nạp gom là nguyên tử) nên bảng không có cột status.
`total_amount_raw` là chuỗi số nguyên (đơn vị nhỏ nhất của token), tổng các `order_web3.amount_raw` đã làm tròn lên từng shop.
SDD `002_checkout_groups.sql` -> `0007`. Idempotent.
"""
from dbschema import column_like, require_innodb


def upgrade(cursor):
    require_innodb(cursor, 'users')
    user_id = column_like(cursor, 'users', 'id')
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS checkout_groups (
            group_id VARCHAR(36) PRIMARY KEY,
            buyer_user_id {user_id} NOT NULL,
            token_address CHAR(42) DEFAULT NULL,
            total_amount_raw VARCHAR(78) NOT NULL COMMENT 'tổng amount_raw của các đơn con',
            order_count TINYINT UNSIGNED NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT chk_cg_count CHECK (order_count BETWEEN 1 AND 5),
            CONSTRAINT fk_cg_buyer FOREIGN KEY (buyer_user_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
