<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 15.3. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 15.3. Giai đoạn 0: yêu cầu bắt buộc trước khi tích hợp

| Mã | Yêu cầu | Xử lý lỗi | Kiểm thử |
|---|---|---|---|
| P0-01 | Lớp xác thực: đăng nhập trả token ký có hạn (`itsdangerous`, `SECRET_KEY` bắt buộc từ môi trường, hết hạn theo `AUTH_TOKEN_TTL_SECONDS`); frontend gửi qua header `Authorization`; decorator `require_auth(roles)` đặt người dùng hiện tại; mọi `userId` trong thân hoặc đường dẫn bị bỏ và lấy từ token. Rủi ro XSS đối với token ở bộ nhớ trình duyệt được chấp nhận ở mức đồ án. | S-01, S-12 | A-01, A-02 |
| P0-02 | Đăng ký chỉ nhận `user` và `seller`; `admin` tạo bằng lệnh cài đặt với mật khẩu đặt khi cài; `shipper` do Admin cấp; bảo vệ toàn bộ `admin_bp` bằng vai trò admin; bỏ cấp số dư giả lập cho người dùng (chỉ seed hoặc Admin). | S-02, S-03, S-04, S-10 | A-02, A-04, A-07 |
| P0-03 | Kiểm quyền sở hữu: đơn thuộc người mua, giỏ hàng thuộc chủ giỏ, phương thức thanh toán thuộc chủ, shop và sản phẩm thuộc người bán; cập nhật đơn kiểm trạng thái hợp lệ và từ chối đơn Web3. | S-05, S-06, S-11 | A-03, I-06 |
| P0-04 | Loại bỏ `/api/shops/migrate`; thay bằng bộ chạy migration số thứ tự ghi `schema_migrations`, không dùng HTTP; gộp khai báo trùng của `reviews` và `reviewImages`, giữ `UNIQUE(userId, productId)` và dùng `reviewImages.id` tự tăng (hoặc UUID sinh ở backend). | S-07, S-13 | A-07 |
| P0-05 | Thanh toán an toàn: giao dịch với `SELECT ... FOR UPDATE`; `UPDATE ... WHERE inStock >= :qty`; tính tiền bằng số nguyên VND hoặc `Decimal`, không dùng `float`; kiểm tra PIN chưa thiết lập trả 401 thay vì lỗi 500; giới hạn số lần thử đăng nhập và PIN (khóa tạm sau 5 lần). | S-08, S-09 | A-05, A-06 |
| P0-06 | Cấu hình: tắt `debug` theo môi trường; lỗi chung cho client, chi tiết vào nhật ký; kiểm tra `request.json` và đầu vào. | S-10, S-14 | A-01 |
| P0-07 | Chuyển Slopee sang VND: đổi bốn cột tiền (`products.unitPrice`, `orderLines.unitPrice`, `orders.totalAmount`, `paymentMethods.balance`) sang `DECIMAL(15,0)` (dữ liệu cũ nhân với `FX_VND_PER_TOKEN`); thay mọi ký hiệu `$` và `toFixed(2)` ở frontend (Navbar, Home, ProductView, Cart, Checkout, MyOrders, SellerDashboard) bằng một hàm định dạng VND duy nhất (`Intl.NumberFormat` với `vi-VN` và `VND`); ô nhập giá của người bán chỉ nhận số nguyên không âm; thông báo của backend và số dư giả lập ban đầu đổi sang VND. | Đơn vị tiền | I-02, I-07 |
| P0-08 | Chuyển bộ kiểm thử sẵn có theo mục 12.3: cập nhật các test cũ theo token và VND, chạy các đường tiền, tồn kho và phân quyền trên MySQL thật trong CI, thêm client API chung và route guard ở frontend kèm F-01, F-04. | Chất lượng | A-01 đến A-07, F-01, F-04 |

P0-01 và P0-02 phải xong trước UC-00 (tuần 3) và nên bắt đầu ngay tuần 1 bởi thành viên B vì mọi API Web3 phụ thuộc vào đó; P0-03 đến P0-06 chia cho thành viên A sau M1, P0-07 và P0-08 chia cho \[B\] và \[F\] trong tuần 1-2 (xem mục 11). Các test A-01 đến A-07 chạy trong CI hiện có của Slopee (pytest, GitHub Actions).
