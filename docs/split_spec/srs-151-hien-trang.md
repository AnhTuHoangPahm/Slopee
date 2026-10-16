<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 15.1. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 15.1. Hiện trạng so với giả định của tài liệu này

| Chủ đề | Giả định ban đầu | Thực tế trong Slopee | Xử lý |
|---|---|---|---|
| Xác thực | Có phiên đăng nhập | Không có phiên hay token. Đăng nhập chỉ trả JSON người dùng, frontend lưu ở `localStorage`, backend tin `userId` do client gửi. | Giai đoạn 0 (15.3) |
| Khóa chính | `INT` | `VARCHAR(36)` UUID cho `users`, `orders`, `shops` | Mục 9 |
| Trạng thái đơn | Viết hoa | `pending, paid, shipped, cancelled, received` | Mục 5.1 |
| Shipper | Có vai trò và vận đơn | `users.role` chỉ có `admin, seller, user`; không có vận đơn | Mục 9 (bảng 0, 15) |
| Nhóm hàng | Có mã nhóm | `categories(id, name)` | Mục 9 (bảng 11) |
| Merchant của đơn | Một đơn một Merchant | `orders` không có merchant; một đơn có thể gồm nhiều shop | Nạp gom, tách đơn theo shop (BR-11) |
| Tiền | VND số nguyên | `DECIMAL(11,2)` hiển thị bằng ký hiệu \$ (USD), tính bằng `float`; số dư giả lập; tiền bán hàng cộng ngay cho người bán | Chuyển toàn bộ sang VND số nguyên (P0-07) |
| Migration | Tệp SQL đánh số | `init_db.py` tách `schema.sql` bằng dấu chấm phẩy; có route HTTP `/api/shops/migrate` | Bộ chạy migration riêng (15.3) |
