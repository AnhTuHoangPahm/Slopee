-- Web3 (SRS 9 bảng 7): nhật ký sự kiện on-chain, chống trùng bằng UNIQUE(tx_hash, log_index) (AC-08, I-03).
-- block_timestamp là nguồn thời gian cho mọi mốc dẫn xuất và cho replay (R-04). SDD 007_chain_events.sql -> 0012.
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
