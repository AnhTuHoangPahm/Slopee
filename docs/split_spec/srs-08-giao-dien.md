<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 8. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 8. YÊU CẦU GIAO DIỆN TỐI THIỂU

| Vai trò | Màn hình / chức năng bắt buộc |
|---|---|
| Buyer | Kết nối và liên kết ví; thanh toán Web3 (hiển thị giá VND, số token từng shop và tổng, tỷ giá, hạn báo giá, hai bước approve tổng và nạp gom); sau khi nạp, danh sách đơn con theo shop, mỗi đơn có đồng hồ đếm ngược kiểm tra riêng; nút "Đã nhận hàng", "Khiếu nại"; màn hình ký phán quyết; nút hủy khi quá hạn giao hàng. |
| Merchant | Liên kết ví nhận tiền; danh sách đơn Web3 và trạng thái; xem và ký đề xuất phán quyết; rút khoản chờ rút (nếu có). |
| Shipper | Danh sách đơn `LOCKED` được giao; nút "Xác nhận phát hàng thành công". |
| Mọi vai trò | Đăng nhập nhận token, các route được bảo vệ theo vai trò (`user`, `seller`, `shipper`, `admin`), tự chuyển về đăng nhập khi gặp 401; mọi số tiền hiển thị bằng VND qua một hàm định dạng duy nhất, không còn ký hiệu \$. |
| Admin | Danh sách khiếu nại; tạo đề xuất phán quyết; theo dõi trạng thái chữ ký; cấu hình phí, tham số và chính sách theo nhóm hàng, gán danh mục cho nhóm chính sách; bảng đối soát; danh sách cảnh báo bất thường từ indexer. |

**Ràng buộc kỹ thuật frontend.** Giữ stack hiện có của Slopee: React 19, JavaScript (không TypeScript), React Router 7, Vite, Vitest và Playwright. Chỉ thêm một thư viện chạy là `ethers` v6. Mọi lời gọi API đi qua một client chung (đọc địa chỉ máy chủ từ `VITE_API_BASE`, gắn header `Authorization`, xử lý 401), thay cho việc mỗi tệp `api/*.js` hardcode `http://localhost:5000`. Trạng thái đơn lấy bằng polling 2-3 giây qua một hook `usePolling` tự viết. Các trang hiện có phải đổi: `Checkout.jsx` (thêm thanh toán Web3 và nạp gom), `Cart.jsx`, `MyOrders.jsx` (đơn con theo shop, huy hiệu tranh chấp), `Navbar.jsx` (nút ví), `SellerDashboard.jsx` (giá VND số nguyên, ví nhận tiền), `AdminDashboard.jsx`; trang mới gồm liên kết ví, Shipper, ký phán quyết.
