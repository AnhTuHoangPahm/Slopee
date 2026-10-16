<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, mục 6. Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 6. GIẢ ĐỊNH TIN CẬY & MÔ HÌNH ĐE DỌA

Hệ thống giảm bớt chứ không loại bỏ hoàn toàn nhu cầu tin cậy vào sàn. Các giả định được nêu rõ như sau:

| Kịch bản | Mức ảnh hưởng | Biện pháp trong MVP / Phase 2 |
|---|---|---|
| Sàn và Merchant thông đồng để lấy tiền Buyer | Chỉ thực hiện được khi đơn ở trạng thái `DISPUTED`, mà trạng thái này chỉ do Buyer kích hoạt. Ngoài ra, sau khi hết thời hạn tranh chấp của đơn (7-90 ngày tùy nhóm hàng), sàn có thể xử đơn phương. | Ghi nhận như giả định tin cậy. Phase 2: Trọng tài là multisig hoặc bên thứ ba độc lập. |
| Sàn và Buyer thông đồng để hoàn tiền bất hợp lý | Cần Buyer khiếu nại và hai bên ký; Merchant mất hàng và tiền. | Lưu vết quyết định và bằng chứng (`docHash`); kiểm toán sau. |
| Shipper xác nhận giao hàng sai sự thật | Kích hoạt đồng hồ kiểm tra khi Buyer chưa nhận hàng; Buyer có thể bỏ lỡ cửa sổ khiếu nại. | Thông báo cho Buyer khi giao; thời gian kiểm tra tối thiểu 1 giờ; Phase 2: xác nhận giao hàng có chữ ký của Buyer hoặc oracle vận đơn. |
| Lộ khóa vận hành của sàn | Kẻ tấn công ký báo giá, xác nhận giao hàng hoặc phán quyết. | Tách khóa theo vai trò; nạp từ môi trường; phí trong báo giá bị chặn bởi trần on-chain do Admin đặt nên khóa ký báo giá bị lộ cũng không nâng được phí; Phase 2: KMS/HSM, multisig, giới hạn tần suất. |
| Buyer nạp tiền nhưng đơn bị Merchant hủy phía sàn | Tiền bị khóa đến khi hết 14 ngày. | Buyer hoặc Admin gọi hủy sau Delivery Timeout; Phase 2: cho phép Merchant chủ động hoàn tiền. |
