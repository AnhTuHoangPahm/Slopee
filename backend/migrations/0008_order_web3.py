"""Web3 (SRS 9 bảng 3, SDD 7.2): `order_web3`, quan hệ 1-1 với `orders` của Slopee (không sửa `orders`).

Migration PHÒNG VỆ (Q-06): `order_id`, `buyer_user_id`, `merchant_user_id`, `checkout_group_id` lấy kiểu + charset + collation
từ cột cha (information_schema); bảng cha không phải InnoDB thì dừng và báo rõ. Khóa ngoại dùng ON DELETE RESTRICT
(đơn và tiền ký quỹ là hồ sơ kế toán; xóa người dùng có đơn Web3 phải trả 409 user_has_orders, xem PROGRESS.md quyết định 3).

Quyền ghi (SDD 7.1): thông tin báo giá do QuoteService; `status` từ LOCKED trở đi, `delivered_at`, `disputed_at`, `closed_at`,
`chain_created_at`, `deposit_tx_hash`, `anomaly_flag` CHỈ do Indexer (BR-09). `amount_raw` là chuỗi, không bao giờ FLOAT.
CHECK cần MySQL >= 8.0.16. SDD `003_order_web3.sql` -> `0008`. Idempotent.
"""
from dbschema import column_like, require_innodb


def upgrade(cursor):
    for table in ('orders', 'users', 'checkout_groups'):
        require_innodb(cursor, table)
    order_id = column_like(cursor, 'orders', 'id')
    user_id = column_like(cursor, 'users', 'id')
    group_id = column_like(cursor, 'checkout_groups', 'group_id')
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS order_web3 (
            order_id {order_id} NOT NULL PRIMARY KEY COMMENT '= orders.id',
            onchain_order_id BIGINT UNSIGNED NOT NULL UNIQUE COMMENT 'cấp từ onchain_id_seq, nhỏ hơn 2^53',
            buyer_user_id {user_id} NOT NULL,
            merchant_user_id {user_id} NOT NULL COMMENT '= shops.sellerId',
            shop_id VARCHAR(36) NOT NULL,
            checkout_group_id {group_id} NOT NULL COMMENT 'lô thanh toán chứa đơn này',
            buyer_wallet CHAR(42) NOT NULL,
            merchant_wallet CHAR(42) NOT NULL,
            token_address CHAR(42) DEFAULT NULL COMMENT 'NULL = ETH gốc, có địa chỉ = ERC-20',
            token_symbol VARCHAR(16) NOT NULL DEFAULT 'mUSD',
            amount_raw VARCHAR(78) NOT NULL COMMENT 'đơn vị nhỏ nhất, lưu chuỗi',
            price_vnd BIGINT UNSIGNED NOT NULL COMMENT 'từ orders.totalAmount (VND số nguyên)',
            fx_vnd_per_token DECIMAL(18,4) NOT NULL COMMENT 'tỷ giá đã chốt trong báo giá',
            payment_method VARCHAR(20) NOT NULL DEFAULT 'CRYPTO_ESCROW',
            status ENUM('PENDING_PAYMENT','EXPIRED','LOCKED','DELIVERED','DISPUTED','COMPLETED','REFUNDED')
                   NOT NULL DEFAULT 'PENDING_PAYMENT',
            policy_code VARCHAR(32) NOT NULL DEFAULT 'GENERAL',
            fee_bps INT UNSIGNED NOT NULL COMMENT 'phí chốt trong báo giá',
            inspection_duration INT UNSIGNED NOT NULL COMMENT 'giây, chốt trong báo giá',
            dispute_timeout INT UNSIGNED NOT NULL COMMENT 'giây, 7-90 ngày, chốt trong báo giá',
            doc_hash CHAR(66) NOT NULL,
            deposit_tx_hash CHAR(66) DEFAULT NULL,
            chain_created_at BIGINT UNSIGNED DEFAULT NULL COMMENT 'giây UTC theo thời gian block',
            delivered_at BIGINT UNSIGNED DEFAULT NULL,
            disputed_at BIGINT UNSIGNED DEFAULT NULL,
            closed_at BIGINT UNSIGNED DEFAULT NULL,
            anomaly_flag TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'indexer phát hiện sai lệch',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_buyer (buyer_wallet),
            INDEX idx_merchant (merchant_wallet),
            INDEX idx_status (status),
            INDEX idx_group (checkout_group_id),
            CONSTRAINT chk_onchain_id CHECK (onchain_order_id < 9007199254740992),
            CONSTRAINT chk_fee CHECK (fee_bps <= 1000),
            CONSTRAINT fk_order_web3_group FOREIGN KEY (checkout_group_id) REFERENCES checkout_groups(group_id),
            CONSTRAINT fk_order_web3_parent FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT,
            CONSTRAINT fk_order_web3_buyer FOREIGN KEY (buyer_user_id) REFERENCES users(id) ON DELETE RESTRICT,
            CONSTRAINT fk_order_web3_merchant FOREIGN KEY (merchant_user_id) REFERENCES users(id) ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
