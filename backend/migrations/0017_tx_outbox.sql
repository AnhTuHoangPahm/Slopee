-- Web3 (SRS 9 bảng 12): nhật ký giao dịch relayer đã gửi (hàng đợi một luồng, truy vết khi demo). SDD 012_tx_outbox.sql -> 0017.
-- kind: DELIVER, RELEASE, RESOLVE. order_id là orders.id (không FK để nhật ký tồn tại độc lập với vòng đời đơn).
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
