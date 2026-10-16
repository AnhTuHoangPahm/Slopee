"""Web3 (SRS 9 bảng 4): báo giá EIP-712 đã phát hành (BR-06). `quote_json` gồm đủ trường OrderQuote (có buyer và feeBps).
`order_id` khớp kiểu/charset/collation của `order_web3.order_id`. SDD `004_order_quotes.sql` -> `0009`. Idempotent."""
from dbschema import column_like, require_innodb


def upgrade(cursor):
    require_innodb(cursor, 'order_web3')
    order_id = column_like(cursor, 'order_web3', 'order_id')
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS order_quotes (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            order_id {order_id} NOT NULL,
            quote_json JSON NOT NULL COMMENT 'các trường OrderQuote, gồm buyer và feeBps',
            signature VARCHAR(132) NOT NULL,
            deadline BIGINT UNSIGNED NOT NULL COMMENT 'giây, theo now_chain',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_quote_order (order_id),
            CONSTRAINT fk_quote_order FOREIGN KEY (order_id) REFERENCES order_web3(order_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
