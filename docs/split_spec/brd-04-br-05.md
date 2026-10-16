<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, BR-05 (mục 4). Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# BR-05: Thoát hiểm khi Sự cố (Timeout & Emergency Exit)

- **Quá hạn giao hàng (Delivery Timeout):** Quá 14 ngày kể từ khi nạp tiền mà Shipper chưa xác nhận giao hàng → Buyer (hoặc Admin) được gọi lệnh hủy đơn và nhận lại 100% tiền.
- **Kẹt tranh chấp (Dispute Timeout):** Quá thời hạn tranh chấp của đơn (`disputeTimeout`, quy định theo nhóm hàng tại BR-10, từ 7 đến 90 ngày, mặc định 30 ngày) kể từ lúc khiếu nại mà không đạt được thỏa thuận 2 chữ ký → Trọng tài sàn được quyền xử đơn phương: hoàn tiền cho Buyer hoặc giải ngân cho Merchant, để tiền không bị giam vĩnh viễn.
- **Người nhận từ chối nhận ETH:** Nếu ví nhận là contract từ chối nhận tiền, khoản tiền được ghi vào sổ chờ rút (pull-payment) để người nhận tự rút sau; không làm kẹt đơn hàng.
