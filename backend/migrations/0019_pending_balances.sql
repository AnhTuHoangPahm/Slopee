-- Web3 (SRS 9 bảng 14): số dư chờ rút DẪN XUẤT từ PayoutDeferred (+) và PendingClaimed (-) để hiện thị và đối soát (INV-01).
-- ETH dùng địa chỉ 0x00..00. amount_raw là chuỗi số nguyên. SDD 014_pending_balances.sql -> 0019.
CREATE TABLE IF NOT EXISTS pending_balances (
    token_address CHAR(42) NOT NULL COMMENT 'ETH dùng địa chỉ 0x00..00',
    address CHAR(42) NOT NULL,
    amount_raw VARCHAR(78) NOT NULL DEFAULT '0',
    PRIMARY KEY (token_address, address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
