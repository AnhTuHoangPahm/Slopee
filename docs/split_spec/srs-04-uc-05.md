<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, UC-05 (mục 4). Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# UC-05: Buyer khiếu nại (BR-03, BR-04)

- **Tiền điều kiện:** đơn `DELIVERED` và `block.timestamp < deliveredAt + inspectionDuration`.
- **Luồng chính:** Buyer bấm "Yêu cầu trả hàng / Khiếu nại", nhập lý do và đường dẫn bằng chứng (lưu ở sàn) → `raiseDispute(orderId)` → trạng thái `DISPUTED`, ghi `disputedAt`, phát `OrderDisputed`. Tiền bị đóng băng.
- **Luồng lỗi:** gọi sau hạn kiểm tra hoặc không phải Buyer → revert.
