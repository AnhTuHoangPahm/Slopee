<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, mục 8. Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 8. TIÊU CHÍ NGHIỆM THU (ACCEPTANCE CRITERIA)

| Mã | Tiêu chí | Liên quan |
|---|---|---|
| AC-01 | Buyer liên kết ví, đặt hàng, nhận báo giá, ký quỹ thành công; đơn chuyển `LOCKED` trong CSDL trong vòng 10 giây sau khi giao dịch được xác nhận. | BR-06, 07, 09 |
| AC-02 | Báo giá sai (sai người nạp, sai số tiền, hết hạn, mã đơn đã dùng) đều bị contract từ chối. | BR-06 |
| AC-03 | Shipper có quyền xác nhận giao hàng; người khác gọi sẽ bị từ chối. | BR-03 |
| AC-04 | Mở khóa sớm và giải ngân sau hết hạn chia đúng phí theo `feeBps` đã chốt trong báo giá; thay đổi phí sau đó không ảnh hưởng đơn cũ. | BR-02, 03 |
| AC-05 | Khiếu nại trong hạn đóng băng tiền; khiếu nại sau hạn bị từ chối. | BR-03 |
| AC-06 | Giải quyết tranh chấp thành công với 2 chữ ký của 2 bên khác nhau; thất bại khi chữ ký trùng bên, hết hạn, sai người nhận, sai số tiền hoặc có hạn không trước thời điểm Trọng tài được xử đơn phương. | BR-04, 05 |
| AC-07 | Delivery Timeout và Dispute Timeout hoạt động đúng với từng giá trị `disputeTimeout` (kiểm thử bằng tua nhanh thời gian trên Anvil hoặc `vm.warp`). | BR-05 |
| AC-08 | Xóa trạng thái, chạy lại indexer từ đầu, dữ liệu khớp 100% on-chain; xử lý trùng sự kiện không gây ghi đôi. | BR-09 |
| AC-09 | Không có private key người dùng trong CSDL, mã nguồn, nhật ký ứng dụng. | BR-01 |
| AC-10 | Số dư contract khớp tổng tiền các đơn đang mở (script đối soát). | G-01 |
| AC-11 | Toàn bộ test contract đạt, độ phủ dòng lệnh từ 90% trở lên; luồng demo chạy lặp lại 3 lần liên tiếp không lỗi. | G-06 |
| AC-12 | Mỗi nhóm hàng nhận đúng cửa sổ kiểm tra và thời hạn tranh chấp trong báo giá; hai đơn khác nhóm có thời hạn độc lập; đổi chính sách sau khi tạo đơn không ảnh hưởng đơn cũ; giá trị ngoài khoảng 7-90 ngày bị contract từ chối. | BR-05, BR-10 |
| AC-13 | Báo giá có `feeBps` vượt trần on-chain bị contract từ chối; sau khi Admin hạ trần, báo giá cũ có phí cao hơn bị từ chối và Buyer lấy được báo giá mới hợp lệ; báo giá có ví người nạp khác người gửi giao dịch bị từ chối; phí của đơn trên chuỗi đúng bằng phí trong báo giá. | BR-02, BR-06 |
| AC-14 | Giỏ hàng có ít nhất 3 shop thanh toán chỉ cần đúng 2 lần xác nhận ví và tạo đúng từng ấy đơn độc lập; thao tác trên đơn của một shop (mở khóa, khiếu nại, hoàn tiền) không đổi trạng thái hay số tiền của đơn shop khác; nạp gom có một báo giá không hợp lệ thì toàn bộ bị từ chối và không đơn nào được tạo; số dư contract luôn bằng tổng tiền các đơn đang mở. | BR-11, BR-06 |
