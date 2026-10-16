-- Web3 (SRS 9 bảng 6): chữ ký off-chain EIP-712 của từng bên. UNIQUE(resolution_id, party): mỗi bên một chữ ký cho một đề xuất.
-- SDD 006_dispute_signatures.sql -> 0011. Không lưu khóa riêng, chỉ lưu chữ ký công khai (BR-01).
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
