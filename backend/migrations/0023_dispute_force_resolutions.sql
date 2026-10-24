-- Web3 tuần 7 (UC-07, BR-05): nhật ký các lần Trọng tài xử đơn phương sau `disputeTimeout` (`arbitratorForceResolve`).
-- Đây là hành động DUY NHẤT dựa hoàn toàn vào niềm tin ở sàn (BRD mục 6), nên phải truy vết được: ai yêu cầu (Admin lấy từ token),
-- chọn bên nào, lý do, tiền bao nhiêu, giao dịch nào. Trạng thái đơn vẫn do Indexer ghi từ sự kiện `ArbitratorForceResolved` (BR-09);
-- bảng này chỉ là dấu vết ý định của sàn, không bao giờ đổi trạng thái đơn. Không có khóa ngoại (cùng quy ước `tx_outbox`):
-- nhật ký phải tồn tại độc lập với vòng đời đơn/người dùng. `outbox_id` trỏ tới `tx_outbox` (trạng thái gửi/biên nhận/lỗi).
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
