-- Web3 (SRS 9 bảng 8): con trỏ của Indexer, chạy lại an toàn sau khi khởi động lại. SDD 008_indexer_cursor.sql -> 0013.
-- bootstrap khởi tạo last_block = block triển khai - 1 (SDD 4.7); bảng chỉ do Indexer ghi.
CREATE TABLE IF NOT EXISTS indexer_cursor (
    name VARCHAR(50) PRIMARY KEY COMMENT 'ví dụ escrow',
    last_block BIGINT UNSIGNED NOT NULL,
    last_block_hash CHAR(66) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
