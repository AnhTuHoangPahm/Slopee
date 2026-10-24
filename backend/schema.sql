CREATE TABLE IF NOT EXISTS users (
	id varchar(36) PRIMARY KEY,
	role enum ('admin', 'seller', 'user', 'shipper') NOT NULL,
	name varchar(50) NOT NULL,
	email varchar(50) NOT NULL UNIQUE,
	phone char(10) NOT NULL UNIQUE,
	bio text,
    deletionRequestedAt timestamp NULL DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS credentials (
	userId varchar(36) NOT NULL,
	username varchar(25) NOT NULL PRIMARY KEY check (length(username) > 3),
	passwordHash varchar(256) NOT NULL,
	passwordSalt varchar(256) NOT NULL,
    passPhraseHash varchar(256) comment '6-digit pass phrase for payments',
    foreign key (userId) references users (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS shops (
    id varchar(36) PRIMARY KEY,
    sellerId varchar(36) NOT NULL UNIQUE,
    name varchar(100) NOT NULL,
    description text,
    avatarUrl varchar(500),
    createdAt timestamp default current_timestamp,
    foreign key (sellerId) references users (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS paymentMethods (
    id varchar(36) PRIMARY KEY,
    userId varchar(36) NOT NULL,
    methodType enum ('bank', 'credit_card', 'cash') NOT NULL,
    providerName varchar(100) comment 'e.g. Bank A, Bank B, Visa',
    accountNumber varchar(50),
    balance decimal(15,0) NOT NULL default 0 comment 'Số dư (VND)',
    foreign key (userId) references users (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS categories (
	id int unsigned auto_increment PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
	id varchar(15) PRIMARY KEY,
	categoryId int unsigned NOT NULL,
    shopId varchar(36) NOT NULL,      
    name varchar(255) NOT NULL,       
    description text,                 
    inStock int NOT NULL check (inStock >= 0),
    unitPrice DECIMAL(15, 0) NOT NULL check (unitPrice >=0),
    isActive boolean default true comment 'is product still for sale?',
	foreign key (categoryId) references categories (id),
    foreign key (shopId) references shops (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS productImages (
    id varchar(36) PRIMARY KEY,
    productId varchar(15) NOT NULL,
    imageUrl varchar(500) NOT NULL,
    isPrimary boolean default false,
    foreign key (productId) references products (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS productVariants (
    id varchar(36) PRIMARY KEY,
    productId varchar(15) NOT NULL,
    variantName varchar(100) NOT NULL,
    variantValue varchar(100) NOT NULL,
    foreign key (productId) references products (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS carts (
	id varchar(36) PRIMARY KEY,
	userId varchar(36) NOT NULL,
    createdAt timestamp NOT NULL DEFAULT current_timestamp,
    status enum ('active', 'ordered') NOT NULL default 'active',
	foreign key (userId) references users (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS cartItems (
	id varchar(36) primary key,
	cartId varchar(36) NOT NULL,
    productId varchar(15) NOT NULL,
    selectedVariants text,            
	quantity int NOT NULL check (quantity > 0),
	foreign key (cartId) references carts (id) on delete cascade,
	foreign key (productId) references products (id) on delete cascade
);

CREATE TABLE IF NOT EXISTS orders (
	id varchar(36) PRIMARY KEY,
	userId varchar(36) NOT NULL,
    paymentMethodId varchar(36),      
	created_at timestamp NOT NULL DEFAULT current_timestamp,
    status enum('pending', 'paid', 'shipped', 'cancelled', 'received') NOT NULL default 'pending',
    totalAmount decimal(15, 0) NOT NULL default 0,
    foreign key (userId) references users(id) on delete restrict,
    foreign key (paymentMethodId) references paymentMethods(id) on delete set null
);

CREATE TABLE IF NOT EXISTS orderLines (
	id varchar(36) PRIMARY KEY,
	orderId varchar(36),
	productId varchar(15) NULL,
    selectedVariants text,            
    unitPrice decimal(15, 0) NOT NULL,
	quantity int NOT NULL CHECK (quantity > 0),
    snapshotProductName varchar(255),
    snapshotShopName varchar(255),
    sellerPaymentMethodId varchar(36) NULL,
    sellerCredit decimal(15,0) NOT NULL DEFAULT 0 comment 'VND đã cộng cho người bán từ dòng này',
    FOREIGN KEY (orderId) REFERENCES orders (id) on delete cascade,
    FOREIGN KEY (productId) REFERENCES products (id) on delete set null,
    CONSTRAINT fk_orderlines_seller_pm FOREIGN KEY (sellerPaymentMethodId) REFERENCES paymentMethods (id) on delete set null
);

CREATE TABLE IF NOT EXISTS reviews (
    id varchar(36) PRIMARY KEY,
    userId varchar(36) NOT NULL,
    productId varchar(15) NOT NULL,
    rating int NOT NULL check (rating >= 1 AND rating <= 5),
    comment text NOT NULL,
    createdAt timestamp NOT NULL DEFAULT current_timestamp,
    FOREIGN KEY (userId) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (productId) REFERENCES products(id) ON DELETE CASCADE,
    CONSTRAINT uniqueReview UNIQUE(userId, productId)
);

CREATE TABLE IF NOT EXISTS reviewImages (
    id varchar(36) PRIMARY KEY,
    reviewId varchar(36) NOT NULL,
    imageUrl varchar(500) NOT NULL,
    FOREIGN KEY (reviewId) REFERENCES reviews(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS authAttempts (
    scope varchar(16) NOT NULL,
    subject varchar(80) NOT NULL,
    failedCount int NOT NULL DEFAULT 0,
    lockedUntil bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (scope, subject)
);

-- =====================================================================================================
-- WEB3 ESCROW (migration 0006 .. 0023). Giữ KHỚP với migrations/: test_web3_migrations.py so sánh DB tạo từ file này
-- với DB nâng cấp bằng migrate.py. Sửa một bên thì phải sửa bên kia. Phần trên dấu mốc này là schema Slopee cũ.
-- =====================================================================================================

CREATE TABLE IF NOT EXISTS user_wallets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id varchar(36) NOT NULL,
    address CHAR(42) NOT NULL COMMENT 'chữ thường để so khớp',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_wallet_address (address),
    INDEX idx_wallet_user (user_id, is_active),
    CONSTRAINT fk_wallet_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS wallet_nonces (
    nonce CHAR(32) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP NULL DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS checkout_groups (
    group_id VARCHAR(36) PRIMARY KEY,
    buyer_user_id varchar(36) NOT NULL,
    token_address CHAR(42) DEFAULT NULL,
    total_amount_raw VARCHAR(78) NOT NULL COMMENT 'tổng amount_raw của các đơn con',
    order_count TINYINT UNSIGNED NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_cg_count CHECK (order_count BETWEEN 1 AND 5),
    CONSTRAINT fk_cg_buyer FOREIGN KEY (buyer_user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS order_web3 (
    order_id varchar(36) NOT NULL PRIMARY KEY COMMENT '= orders.id',
    onchain_order_id BIGINT UNSIGNED NOT NULL UNIQUE COMMENT 'cấp từ onchain_id_seq, nhỏ hơn 2^53',
    buyer_user_id varchar(36) NOT NULL,
    merchant_user_id varchar(36) NOT NULL COMMENT '= shops.sellerId',
    shop_id VARCHAR(36) NOT NULL,
    checkout_group_id VARCHAR(36) NOT NULL COMMENT 'lô thanh toán chứa đơn này',
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS order_quotes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id varchar(36) NOT NULL,
    quote_json JSON NOT NULL COMMENT 'các trường OrderQuote, gồm buyer và feeBps',
    signature VARCHAR(132) NOT NULL,
    deadline BIGINT UNSIGNED NOT NULL COMMENT 'giây, theo now_chain',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_quote_order (order_id),
    CONSTRAINT fk_quote_order FOREIGN KEY (order_id) REFERENCES order_web3(order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS dispute_resolutions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id varchar(36) NOT NULL,
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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

CREATE TABLE IF NOT EXISTS chain_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tx_hash CHAR(66) NOT NULL,
    log_index INT UNSIGNED NOT NULL,
    event_name VARCHAR(50) NOT NULL,
    order_id BIGINT UNSIGNED DEFAULT NULL COMMENT 'onchain_order_id, NULL với sự kiện không gắn đơn',
    block_number BIGINT UNSIGNED NOT NULL,
    block_hash CHAR(66) NOT NULL,
    block_timestamp BIGINT UNSIGNED NOT NULL COMMENT 'giây UTC',
    payload_json JSON NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tx_log (tx_hash, log_index),
    INDEX idx_order (order_id),
    INDEX idx_block (block_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS indexer_cursor (
    name VARCHAR(50) PRIMARY KEY COMMENT 'ví dụ escrow',
    last_block BIGINT UNSIGNED NOT NULL,
    last_block_hash CHAR(66) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS platform_settings (
    setting_key VARCHAR(64) PRIMARY KEY,
    setting_value VARCHAR(255) NOT NULL,
    updated_by VARCHAR(36) DEFAULT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO platform_settings (setting_key, setting_value) VALUES ('PLATFORM_FEE_BPS', '300');
INSERT IGNORE INTO platform_settings (setting_key, setting_value) VALUES ('QUOTE_TTL_SECONDS', '900');
INSERT IGNORE INTO platform_settings (setting_key, setting_value) VALUES ('FX_VND_PER_TOKEN', '25000');
INSERT IGNORE INTO platform_settings (setting_key, setting_value) VALUES ('DISPUTE_SIG_TTL_SECONDS', '604800');

CREATE TABLE IF NOT EXISTS category_policies (
    policy_code VARCHAR(32) PRIMARY KEY COMMENT 'GENERAL, PERISHABLE, ELECTRONICS, CUSTOM_BULKY',
    display_name VARCHAR(100) NOT NULL,
    inspection_duration INT UNSIGNED NOT NULL COMMENT 'giây, 3600 (1 giờ) .. 2592000 (30 ngày)',
    dispute_timeout INT UNSIGNED NOT NULL COMMENT 'giây, 604800 (7 ngày) .. 7776000 (90 ngày)',
    is_default TINYINT(1) NOT NULL DEFAULT 0,
    updated_by VARCHAR(36) DEFAULT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_inspection CHECK (inspection_duration BETWEEN 3600 AND 2592000),
    CONSTRAINT chk_dispute_timeout CHECK (dispute_timeout BETWEEN 604800 AND 7776000)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO category_policies (policy_code, display_name, inspection_duration, dispute_timeout, is_default) VALUES
 ('PERISHABLE',  'Thực phẩm, hàng dễ hỏng',          7200,    604800,  0),
 ('GENERAL',     'Hàng tiêu dùng thông thường',      259200,  2592000, 1),
 ('ELECTRONICS', 'Điện tử, đồ gia dụng giá trị cao', 604800,  3888000, 0),
 ('CUSTOM_BULKY','Hàng cồng kềnh, đặt theo yêu cầu', 1209600, 5184000, 0);

CREATE TABLE IF NOT EXISTS category_policy_map (
    category_id INT UNSIGNED PRIMARY KEY,
    policy_code VARCHAR(32) NOT NULL,
    CONSTRAINT fk_cpm_category FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_cpm_policy FOREIGN KEY (policy_code) REFERENCES category_policies(policy_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS tx_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    kind VARCHAR(30) NOT NULL COMMENT 'DELIVER, RELEASE, RESOLVE',
    order_id VARCHAR(36) DEFAULT NULL,
    tx_hash CHAR(66) DEFAULT NULL,
    status ENUM('PENDING','SENT','CONFIRMED','FAILED') NOT NULL DEFAULT 'PENDING',
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_outbox_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS onchain_id_seq (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB AUTO_INCREMENT=100001 DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS pending_balances (
    token_address CHAR(42) NOT NULL COMMENT 'ETH dùng địa chỉ 0x00..00',
    address CHAR(42) NOT NULL,
    amount_raw VARCHAR(78) NOT NULL DEFAULT '0',
    PRIMARY KEY (token_address, address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS shipper_assignments (
    order_id varchar(36) NOT NULL PRIMARY KEY,
    shipper_user_id varchar(36) NOT NULL,
    assigned_by VARCHAR(36) DEFAULT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_shipper (shipper_user_id),
    CONSTRAINT fk_sa_order FOREIGN KEY (order_id) REFERENCES order_web3(order_id),
    CONSTRAINT fk_sa_shipper FOREIGN KEY (shipper_user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id varchar(36) NOT NULL,
    order_id VARCHAR(36) NOT NULL,
    kind VARCHAR(40) NOT NULL COMMENT 'ORDER_DELIVERED, DELIVERY_TIMEOUT',
    message VARCHAR(500) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP NULL DEFAULT NULL,
    UNIQUE KEY uk_notification (user_id, order_id, kind),
    INDEX idx_notification_user (user_id, created_at),
    CONSTRAINT fk_notification_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS dispute_notes (
    order_id varchar(36) NOT NULL PRIMARY KEY,
    buyer_user_id VARCHAR(36) NOT NULL COMMENT 'Buyer đã gửi (kiểm lúc ghi, lưu để truy vết)',
    reason TEXT NOT NULL,
    evidence_url VARCHAR(500) DEFAULT NULL COMMENT 'chỉ http/https',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_dispute_note_order FOREIGN KEY (order_id) REFERENCES order_web3(order_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS dispute_force_resolutions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    onchain_order_id BIGINT UNSIGNED NOT NULL,
    admin_user_id VARCHAR(36) NOT NULL COMMENT 'Admin yêu cầu (từ token)',
    payout_side ENUM('BUYER','MERCHANT') NOT NULL COMMENT 'BUYER = hoàn tiền, MERCHANT = giải ngân',
    payout_to CHAR(42) NOT NULL COMMENT 'địa chỉ chữ thường',
    amount_raw VARCHAR(78) NOT NULL,
    reason_note TEXT DEFAULT NULL,
    outbox_id BIGINT DEFAULT NULL COMMENT 'tx_outbox.id',
    tx_hash CHAR(66) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_force_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
