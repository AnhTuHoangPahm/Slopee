-- Web3 (SRS 9 bảng 13, SDD 7.3 #3): bộ đếm onchain_order_id đơn điệu, bắt đầu từ 100001, nhỏ hơn 2^53 rất nhiều (R-03).
-- Backend cấp ID bằng INSERT vào bảng này rồi LAST_INSERT_ID(). SDD 013_onchain_id_seq.sql -> 0018.
CREATE TABLE IF NOT EXISTS onchain_id_seq (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB AUTO_INCREMENT=100001 DEFAULT CHARSET=utf8mb4;
