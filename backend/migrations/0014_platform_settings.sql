-- Web3 (SRS 9 bảng 9): tham số vận hành do Admin đổi không cần khởi động lại (SDD 12.2). SDD 009_platform_settings.sql -> 0014.
-- Gieo 4 khóa: PLATFORM_FEE_BPS = 300 (SRS 2), QUOTE_TTL_SECONDS = 900 (15 phút, UC-01),
-- FX_VND_PER_TOKEN = 25000 (1 token = 25.000 VND, nhóm chốt, dùng cho UC-01) và DISPUTE_SIG_TTL_SECONDS = 604800 (7 ngày, nhóm chốt, dùng cho UC-06).
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
