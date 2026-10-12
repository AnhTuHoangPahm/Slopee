-- Web3 (SRS 9 bảng 10, BR-10): chính sách thời hạn theo nhóm hàng. SDD 010_category_policies.sql -> 0015.
-- CHECK ép khoảng 1 giờ..30 ngày (kiểm tra) và 7..90 ngày (tranh chấp) giống contract (MIN/MAX_*).
-- Dữ liệu mẫu theo SRS (giá trị ĐỀ XUẤT, nhóm chốt lại trước tuần 3). SRS ghi gieo ở bootstrap.sh (SDD 7.6 đã được đính chính), nhưng bootstrap chưa chạm MySQL
-- và nhóm GENERAL là bắt buộc (danh mục chưa ánh xạ dùng GENERAL), nên gieo ở đây bằng INSERT IGNORE (idempotent, không đè giá trị Admin đã sửa).
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
