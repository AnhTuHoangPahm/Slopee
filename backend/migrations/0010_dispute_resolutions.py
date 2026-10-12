"""Web3 (SRS 9 bảng 5): đề xuất phán quyết tranh chấp (BR-04). `deadline` phải nhỏ hơn disputedAt + disputeTimeout (backend ép,
contract ép lần nữa). `nonce` đọc từ disputeNonces(orderId). PROPOSED..SUBMITTED do DisputeService, EXECUTED do Indexer (SDD 7.1).
SDD `005_dispute_resolutions.sql` -> `0010`. Idempotent."""
from dbschema import column_like, require_innodb


def upgrade(cursor):
    require_innodb(cursor, 'order_web3')
    order_id = column_like(cursor, 'order_web3', 'order_id')
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS dispute_resolutions (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            order_id {order_id} NOT NULL,
            payout_to CHAR(42) NOT NULL,
            amount_raw VARCHAR(78) NOT NULL,
            nonce BIGINT UNSIGNED NOT NULL COMMENT 'đọc từ disputeNonces(orderId)',
            deadline BIGINT UNSIGNED NOT NULL COMMENT 'giây, nhỏ hơn disputedAt + disputeTimeout',
            status ENUM('PROPOSED','READY','SUBMITTED','EXECUTED','EXPIRED','CANCELLED') NOT NULL DEFAULT 'PROPOSED',
            reason_note TEXT COMMENT 'ghi chú thẩm định, đường dẫn bằng chứng',
            created_by_admin VARCHAR(36) NOT NULL,
            submitted_tx_hash CHAR(66) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_dr_order (order_id),
            CONSTRAINT fk_dr_order FOREIGN KEY (order_id) REFERENCES order_web3(order_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
