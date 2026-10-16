<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, mục 5. Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 5. VÒNG ĐỜI ĐƠN HÀNG (ORDER LIFECYCLE)

| Trạng thái | Ý nghĩa nghiệp vụ | Điều kiện chuyển | Nguồn |
|---|---|---|---|
| `PENDING_PAYMENT` | Đơn đã tạo, có báo giá, chờ Buyer ký quỹ. | Buyer nạp tiền → `LOCKED`; quá hạn báo giá → `EXPIRED` | Sàn |
| `EXPIRED` | Báo giá hết hạn, đơn không được thanh toán. | Trạng thái cuối (có thể tạo báo giá mới). | Sàn |
| `LOCKED` | Tiền đã khóa trong contract, chờ giao hàng. | Shipper xác nhận → `DELIVERED`; quá 14 ngày → `REFUNDED` | On-chain |
| `DELIVERED` | Đã giao hàng, đang trong cửa sổ kiểm tra. | Buyer xác nhận hoặc hết hạn → `COMPLETED`; Buyer khiếu nại → `DISPUTED` | On-chain |
| `DISPUTED` | Tiền bị đóng băng chờ phân xử. | 2/3 chữ ký hoặc Trọng tài xử sau `disputeTimeout` (theo nhóm hàng) → `COMPLETED` hoặc `REFUNDED` | On-chain |
| `COMPLETED` | Đã giải ngân cho Merchant (trừ phí). | Trạng thái cuối. | On-chain |
| `REFUNDED` | Đã hoàn 100% tiền cho Buyer. | Trạng thái cuối. | On-chain |
