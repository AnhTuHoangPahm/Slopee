-- P0-07: 4 cột tiền chuyển sang DECIMAL(15,0) (VND số nguyên).
-- LƯU Ý: dữ liệu cũ (USD, 2 chữ số lẻ) sẽ bị làm tròn. DB demo nên tạo lại bằng init_db.py.
-- Chạy qua bộ chạy migration: python migrate.py (P0-04). Lệnh MODIFY idempotent.
ALTER TABLE paymentMethods MODIFY balance DECIMAL(15,0) NOT NULL DEFAULT 0 COMMENT 'Số dư (VND)';
ALTER TABLE products MODIFY unitPrice DECIMAL(15,0) NOT NULL;
ALTER TABLE orders MODIFY totalAmount DECIMAL(15,0) NOT NULL DEFAULT 0;
ALTER TABLE orderLines MODIFY unitPrice DECIMAL(15,0) NOT NULL;
