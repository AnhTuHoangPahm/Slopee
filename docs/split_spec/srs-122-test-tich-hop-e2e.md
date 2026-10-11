<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 12.2. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 12.2. Kiểm thử tích hợp và end-to-end

| Mã | Kịch bản | Tiêu chí |
|---|---|---|
| I-01 | Liên kết ví: thành công; nonce dùng lại; nonce hết hạn; chữ ký sai; ví đã thuộc tài khoản khác | AC-01 |
| I-02 | Báo giá: giá VND quy đổi đúng, chữ ký Python được contract chấp nhận; hết hạn thì `EXPIRED` | AC-01, 02 |
| I-03 | Indexer: xử lý trùng sự kiện, khởi động lại giữa chừng, replay từ đầu, sự kiện lệch dữ liệu sàn | AC-08 |
| I-04 | Chính sách nhóm hàng: sản phẩm thuộc từng nhóm nhận đúng `inspectionDuration` và `disputeTimeout` trong báo giá; đơn nhiều nhóm lấy giá trị lớn nhất; đổi chính sách không ảnh hưởng đơn đã tạo; indexer cảnh báo khi giá trị on-chain lệch bảng chính sách | AC-12 |
| I-05 | Đồng hồ: sau `evm_increaseTime`, báo giá ký bằng `now_chain` được contract chấp nhận; Anvil chạy `--block-time 2`; `server_time` khớp `now_chain` | AC-02 |
| I-06 | Đồng bộ ngược: mỗi chuyển trạng thái Web3 cập nhật đúng `orders.status` cũ trong cùng giao dịch; `PUT /api/payments/orders/:id` từ chối đơn Web3; replay đặt lại cả hai bảng và khớp 100% với chuỗi | AC-08 |
| A-01 | Mọi endpoint yêu cầu xác thực: không có token hoặc token hết hạn thì 401 | Mục 15 |
| A-02 | Sai vai trò: user hoặc seller gọi API admin thì 403; shipper chỉ thấy đơn được gán | Mục 15 |
| A-03 | Truy cập đơn, giỏ, phương thức thanh toán, shop hay sản phẩm của người khác thì 403 hoặc 404 | Mục 15 |
| A-04 | Đăng ký với `role = admin` hoặc `shipper` bị từ chối; chỉ chấp nhận `user` và `seller` | Mục 15 |
| A-05 | Hai yêu cầu thanh toán song song cùng mua hết tồn kho: đúng một yêu cầu thành công, tồn kho không âm | Mục 15 |
| A-06 | Nhập sai PIN hoặc mật khẩu quá 5 lần thì bị khóa tạm thời | Mục 15 |
| A-07 | Route migration qua HTTP không còn tồn tại; không có endpoint nào cấp số dư giả lập cho người dùng | Mục 15 |
| I-07 | Giỏ 3 shop: tạo đúng 3 đơn và một lô; `total_amount_raw` bằng tổng số token làm tròn lên của từng shop; cấp lại báo giá cả lô; hết hạn thì cả lô `EXPIRED` và hoàn tồn kho; Indexer xử lý 3 `OrderCreated` cùng giao dịch và xóa đúng các mặt hàng khỏi giỏ | AC-14 |
| F-01 | Hàm định dạng VND: số nguyên, làm tròn, giá trị 0, số lớn; không còn ký hiệu \$ ở các trang | P0-07 |
| F-02 | Máy trạng thái nạp tiền (CHECK_NETWORK đến WAITING_INDEXER) viết thành hàm thuần (reducer): đủ allowance thì bỏ APPROVING, người dùng từ chối (4001), báo giá hết hạn, revert, quá 30 giây chờ Indexer | AC-14 |
| F-03 | Ánh xạ lỗi contract và API sang thông báo tiếng Việt, gồm `Invalid batch size`, `FEE_CAP_CHANGED` | AC-02, 13 |
| F-04 | Client API: gắn `Authorization`; gặp 401 thì xóa token và chuyển về đăng nhập; route guard chặn sai vai trò | Mục 15 |
| F-05 | `usePolling`: dừng khi rời trang, không chồng lệnh gọi, dừng khi đạt trạng thái cuối | AC-14 |
| F-06 | Đồng hồ đếm ngược kiểm tra dùng `server_time`, không dùng đồng hồ máy khách | AC-04 |
| E-01 | Luồng thành công: liên kết ví → đặt hàng → ký quỹ → giao hàng → mở khóa sớm | AC-01, 03, 04 |
| E-02 | Luồng hết hạn kiểm tra (tua thời gian Anvil) | AC-04 |
| E-03 | Luồng tranh chấp: khiếu nại → đề xuất → hai bên ký → nộp → hoàn tiền (và biến thể giải ngân) | AC-05, 06 |
| E-04 | Luồng timeout giao hàng và timeout tranh chấp | AC-07 |
| E-05 | Quét kiểm tra khóa: không có private key người dùng trong mã nguồn, CSDL, log | AC-09 |
| E-06 | Đối soát số dư contract sau mỗi kịch bản trên | AC-10 |
| E-07 | Giỏ 3 shop: đúng 2 lần xác nhận ví; shop A mở khóa sớm, shop B khiếu nại và hoàn tiền, shop C hết hạn tự giải ngân; đối soát khớp | AC-14 |
