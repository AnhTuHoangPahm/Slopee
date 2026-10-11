-- P0-07: 4 cột tiền -> DECIMAL(15,0) (VND số nguyên).
-- LƯU Ý: dữ liệu cũ (USD, 2 chữ số lẻ) sẽ bị làm tròn; DB demo nên tạo lại bằng init_db.py.
-- P0-04 sẽ đưa file này vào runner schema_migrations; trước đó chạy tay: mysql slopee_db < 0001_money_to_vnd.sql
ALTER TABLE paymentMethods MODIFY balance DECIMAL(15,0) NOT NULL DEFAULT 0 COMMENT 'Số dư (VND)';
ALTER TABLE products MODIFY unitPrice DECIMAL(15,0) NOT NULL;
ALTER TABLE orders MODIFY totalAmount DECIMAL(15,0) NOT NULL DEFAULT 0;
ALTER TABLE orderLines MODIFY unitPrice DECIMAL(15,0) NOT NULL;
