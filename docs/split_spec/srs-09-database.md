<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 9. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 9. THIẾT KẾ CƠ SỞ DỮ LIỆU MYSQL CHO MODULE BLOCKCHAIN

```sql
-- Quy ước: khóa người dùng và đơn là VARCHAR(36) (UUID) cho khớp bảng users và orders của Slopee.
-- Charset và collation của các cột tham chiếu phải khớp cột cha (migration 001 đọc từ information_schema).
-- Tệp migration không dùng dấu chấm phẩy trong chú thích (init_db tách câu lệnh theo dấu chấm phẩy).

-- Bảng 0: thêm vai trò shipper vào cuối ENUM (thao tác chỉ đổi metadata)
ALTER TABLE users MODIFY role ENUM('admin','seller','user','shipper') NOT NULL;

-- Bảng 0b: Chuyển các cột tiền của Slopee sang VND số nguyên (P0-07)
-- Dữ liệu cũ tính theo USD phải nhân với tỷ giá trước khi đổi kiểu
ALTER TABLE products MODIFY unitPrice DECIMAL(15,0) NOT NULL;
ALTER TABLE orderLines MODIFY unitPrice DECIMAL(15,0) NOT NULL;
ALTER TABLE orders MODIFY totalAmount DECIMAL(15,0) NOT NULL DEFAULT 0;
ALTER TABLE paymentMethods MODIFY balance DECIMAL(15,0) DEFAULT 0;

-- Bảng 1: Ví đã liên kết với tài khoản (BR-07)
CREATE TABLE IF NOT EXISTS user_wallets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    address CHAR(42) NOT NULL,                 -- lưu dạng chữ thường để so khớp
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_wallet_address (address),
    INDEX idx_wallet_user (user_id, is_active),
    CONSTRAINT fk_wallet_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 2: Nonce liên kết ví (dùng một lần)
CREATE TABLE IF NOT EXISTS wallet_nonces (
    nonce CHAR(32) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP NULL DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 2b: Lô thanh toán (một lần nạp gom, tối đa 5 đơn con)
CREATE TABLE IF NOT EXISTS checkout_groups (
    group_id VARCHAR(36) PRIMARY KEY,
    buyer_user_id VARCHAR(36) NOT NULL,
    token_address CHAR(42) DEFAULT NULL,
    total_amount_raw VARCHAR(78) NOT NULL,         -- tổng amount_raw của các đơn con
    order_count TINYINT UNSIGNED NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_cg_count CHECK (order_count BETWEEN 1 AND 5),
    CONSTRAINT fk_cg_buyer FOREIGN KEY (buyer_user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 3: Đơn hàng Web3, quan hệ 1-1 với orders của Slopee (không sửa bảng orders)
CREATE TABLE IF NOT EXISTS order_web3 (
    order_id VARCHAR(36) NOT NULL PRIMARY KEY,         -- = orders.id
    onchain_order_id BIGINT UNSIGNED NOT NULL UNIQUE,  -- cấp từ onchain_id_seq, nhỏ hơn 2^53
    buyer_user_id VARCHAR(36) NOT NULL,
    merchant_user_id VARCHAR(36) NOT NULL,             -- = shops.sellerId
    shop_id VARCHAR(36) NOT NULL,
    checkout_group_id VARCHAR(36) NOT NULL,            -- lô thanh toán chứa đơn này
    buyer_wallet CHAR(42) NOT NULL,
    merchant_wallet CHAR(42) NOT NULL,
    token_address CHAR(42) DEFAULT NULL,               -- NULL = ETH gốc, có địa chỉ = ERC-20
    token_symbol VARCHAR(16) NOT NULL DEFAULT 'mUSD',
    amount_raw VARCHAR(78) NOT NULL,                   -- đơn vị nhỏ nhất, lưu chuỗi
    price_vnd BIGINT UNSIGNED NOT NULL,                -- từ orders.totalAmount, phải là số nguyên
    fx_vnd_per_token DECIMAL(18,4) NOT NULL,           -- tỷ giá đã chốt trong báo giá
    payment_method VARCHAR(20) NOT NULL DEFAULT 'CRYPTO_ESCROW',
    status ENUM('PENDING_PAYMENT','EXPIRED','LOCKED','DELIVERED','DISPUTED','COMPLETED','REFUNDED')
           NOT NULL DEFAULT 'PENDING_PAYMENT',
    policy_code VARCHAR(32) NOT NULL DEFAULT 'GENERAL',
    fee_bps INT UNSIGNED NOT NULL,                     -- phí chốt trong báo giá
    inspection_duration INT UNSIGNED NOT NULL,         -- giây, chốt trong báo giá
    dispute_timeout INT UNSIGNED NOT NULL,             -- giây, 7-90 ngày, chốt trong báo giá
    doc_hash CHAR(66) NOT NULL,
    deposit_tx_hash CHAR(66) DEFAULT NULL,
    chain_created_at BIGINT UNSIGNED DEFAULT NULL,     -- giây UTC theo thời gian block
    delivered_at BIGINT UNSIGNED DEFAULT NULL,
    disputed_at BIGINT UNSIGNED DEFAULT NULL,
    closed_at BIGINT UNSIGNED DEFAULT NULL,
    anomaly_flag TINYINT(1) NOT NULL DEFAULT 0,        -- indexer phát hiện sai lệch
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 4: Báo giá đã phát hành (BR-06)
CREATE TABLE IF NOT EXISTS order_quotes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    quote_json JSON NOT NULL,                      -- các trường OrderQuote, gồm buyer và feeBps
    signature VARCHAR(132) NOT NULL,
    deadline BIGINT UNSIGNED NOT NULL,             -- giây, theo now_chain
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_quote_order (order_id),
    CONSTRAINT fk_quote_order FOREIGN KEY (order_id) REFERENCES order_web3(order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 5: Đề xuất phán quyết tranh chấp (BR-04)
CREATE TABLE IF NOT EXISTS dispute_resolutions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    payout_to CHAR(42) NOT NULL,
    amount_raw VARCHAR(78) NOT NULL,
    nonce BIGINT UNSIGNED NOT NULL,                -- đọc từ disputeNonces(orderId)
    deadline BIGINT UNSIGNED NOT NULL,             -- giây, nhỏ hơn disputedAt + disputeTimeout
    status ENUM('PROPOSED','READY','SUBMITTED','EXECUTED','EXPIRED','CANCELLED') NOT NULL DEFAULT 'PROPOSED',
    reason_note TEXT,                              -- ghi chú thẩm định, đường dẫn bằng chứng
    created_by_admin VARCHAR(36) NOT NULL,
    submitted_tx_hash CHAR(66) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_dr_order (order_id),
    CONSTRAINT fk_dr_order FOREIGN KEY (order_id) REFERENCES order_web3(order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 6: Chữ ký off-chain EIP-712 của từng bên
CREATE TABLE IF NOT EXISTS dispute_signatures (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    resolution_id BIGINT NOT NULL,
    party ENUM('BUYER','MERCHANT','ARBITRATOR') NOT NULL,
    signer_address CHAR(42) NOT NULL,
    signature VARCHAR(132) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_res_party (resolution_id, party),
    CONSTRAINT fk_sig_res FOREIGN KEY (resolution_id) REFERENCES dispute_resolutions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 7: Nhật ký sự kiện on-chain (idempotent, chống trùng lặp)
CREATE TABLE IF NOT EXISTS chain_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tx_hash CHAR(66) NOT NULL,
    log_index INT UNSIGNED NOT NULL,
    event_name VARCHAR(50) NOT NULL,
    order_id BIGINT UNSIGNED DEFAULT NULL,         -- onchain_order_id, NULL với sự kiện không gắn đơn
    block_number BIGINT UNSIGNED NOT NULL,
    block_hash CHAR(66) NOT NULL,
    block_timestamp BIGINT UNSIGNED NOT NULL,      -- giây UTC, nguồn thời gian cho mọi mốc dẫn xuất
    payload_json JSON NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tx_log (tx_hash, log_index),
    INDEX idx_order (order_id),
    INDEX idx_block (block_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 8: Con trỏ của indexer (chạy lại an toàn sau khi khởi động lại)
CREATE TABLE IF NOT EXISTS indexer_cursor (
    name VARCHAR(50) PRIMARY KEY,                  -- ví dụ escrow
    last_block BIGINT UNSIGNED NOT NULL,
    last_block_hash CHAR(66) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 9: Tham số vận hành (FX_VND_PER_TOKEN, QUOTE_TTL_SECONDS, PLATFORM_FEE_BPS, ...)
CREATE TABLE IF NOT EXISTS platform_settings (
    setting_key VARCHAR(64) PRIMARY KEY,
    setting_value VARCHAR(255) NOT NULL,
    updated_by VARCHAR(36) DEFAULT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 10: Chính sách thời hạn theo nhóm hàng (BR-10)
CREATE TABLE IF NOT EXISTS category_policies (
    policy_code VARCHAR(32) PRIMARY KEY,           -- GENERAL, PERISHABLE, ELECTRONICS, CUSTOM_BULKY
    display_name VARCHAR(100) NOT NULL,
    inspection_duration INT UNSIGNED NOT NULL,     -- giây, 3600 (1 giờ) .. 2592000 (30 ngày)
    dispute_timeout INT UNSIGNED NOT NULL,         -- giây, 604800 (7 ngày) .. 7776000 (90 ngày)
    is_default TINYINT(1) NOT NULL DEFAULT 0,
    updated_by VARCHAR(36) DEFAULT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_inspection CHECK (inspection_duration BETWEEN 3600 AND 2592000),
    CONSTRAINT chk_dispute_timeout CHECK (dispute_timeout BETWEEN 604800 AND 7776000)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Dữ liệu mẫu (giá trị đề xuất, nhóm chốt lại trước tuần 3)
INSERT INTO category_policies (policy_code, display_name, inspection_duration, dispute_timeout, is_default) VALUES
 ('PERISHABLE',  'Thực phẩm, hàng dễ hỏng',               7200,    604800,  0),
 ('GENERAL',     'Hàng tiêu dùng thông thường',           259200,  2592000, 1),
 ('ELECTRONICS', 'Điện tử, đồ gia dụng giá trị cao',      604800,  3888000, 0),
 ('CUSTOM_BULKY','Hàng cồng kềnh, đặt theo yêu cầu',      1209600, 5184000, 0);

-- Bảng 11: Gán danh mục sản phẩm của Slopee vào nhóm chính sách (không sửa bảng categories)
CREATE TABLE IF NOT EXISTS category_policy_map (
    category_id INT UNSIGNED PRIMARY KEY,
    policy_code VARCHAR(32) NOT NULL,
    CONSTRAINT fk_cpm_category FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_cpm_policy FOREIGN KEY (policy_code) REFERENCES category_policies(policy_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 12: Nhật ký giao dịch relayer đã gửi
CREATE TABLE IF NOT EXISTS tx_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    kind VARCHAR(30) NOT NULL,                     -- DELIVER, RELEASE, RESOLVE
    order_id VARCHAR(36) DEFAULT NULL,
    tx_hash CHAR(66) DEFAULT NULL,
    status ENUM('PENDING','SENT','CONFIRMED','FAILED') NOT NULL DEFAULT 'PENDING',
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_outbox_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 13: Bộ đếm onchain_order_id đơn điệu
CREATE TABLE IF NOT EXISTS onchain_id_seq (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB AUTO_INCREMENT=100001 DEFAULT CHARSET=utf8mb4;

-- Bảng 14: Số dư chờ rút dẫn xuất từ PayoutDeferred và PendingClaimed
CREATE TABLE IF NOT EXISTS pending_balances (
    token_address CHAR(42) NOT NULL,               -- ETH dùng địa chỉ 0x00..00
    address CHAR(42) NOT NULL,
    amount_raw VARCHAR(78) NOT NULL DEFAULT '0',
    PRIMARY KEY (token_address, address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bảng 15: Gán đơn cho Shipper
CREATE TABLE IF NOT EXISTS shipper_assignments (
    order_id VARCHAR(36) NOT NULL PRIMARY KEY,
    shipper_user_id VARCHAR(36) NOT NULL,
    assigned_by VARCHAR(36) DEFAULT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_shipper (shipper_user_id),
    CONSTRAINT fk_sa_order FOREIGN KEY (order_id) REFERENCES order_web3(order_id),
    CONSTRAINT fk_sa_shipper FOREIGN KEY (shipper_user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Bảng `order_web3` thay cho việc mở rộng `orders`: bảng `orders` của Slopee giữ nguyên, chỉ được đồng bộ trạng thái (mục 5.1). Mọi mốc thời gian lấy từ thời gian block và lưu dạng giây UTC (`BIGINT`) để replay cho kết quả giống hệt. Giữ `onchain_order_id` nhỏ hơn 2^53 và truyền dạng chuỗi hoặc `BigInt` ở JavaScript.

## 9.1. Ánh xạ sự kiện on-chain sang cập nhật CSDL

| Sự kiện | Cập nhật |
|---|---|
| `OrderCreated` | Đối chiếu báo giá đã lưu (gồm `feeBps`); `order_web3.status = LOCKED`, `deposit_tx_hash`, `chain_created_at`. |
| `OrderDelivered` | `status = DELIVERED`, `delivered_at` theo tham số sự kiện. |
| `OrderDisputed` | `status = DISPUTED`, `disputed_at`. |
| `OrderCompleted` | `status = COMPLETED`, `closed_at`. |
| `OrderRefunded` | `status = REFUNDED`, `closed_at`. |
| `DisputeResolved`, `ArbitratorForceResolved` | Đặt đề xuất tương ứng `EXECUTED`; ghi lại cách giải quyết. |
| `PayoutDeferred`, `PendingClaimed` | Cập nhật sổ chờ rút hiển thị cho người nhận. |
| `FeeUpdated`, `FeeRecipientUpdated` | Chỉ lưu `chain_events`. |

Một lần nạp gom phát nhiều `OrderCreated` cùng `tx_hash` và khác `log_index`; Indexer xử lý từng sự kiện độc lập như trước. Mọi cập nhật trạng thái ở bảng trên được kèm cập nhật `orders.status` cũ trong cùng giao dịch CSDL theo bảng ánh xạ mục 5.1. Các cột thời gian lấy từ `block_timestamp`.
