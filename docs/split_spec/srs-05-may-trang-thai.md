<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 5. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 5. MÁY TRẠNG THÁI ĐƠN HÀNG

| Từ trạng thái | Sự kiện / Hàm | Điều kiện | Sang trạng thái |
|---|---|---|---|
| (chưa có) | Backend tạo đơn | Ví đã liên kết | `PENDING_PAYMENT` (chỉ ở sàn) |
| `PENDING_PAYMENT` | Quá hạn báo giá | Chưa có `OrderCreated` | `EXPIRED` (chỉ ở sàn) |
| `PENDING_PAYMENT` | `depositEscrow` | Báo giá hợp lệ | `LOCKED` |
| `LOCKED` | `confirmDelivery` | Có `SHIPPER_ROLE` | `DELIVERED` |
| `LOCKED` | `cancelIfUnfulfilled` | Quá 14 ngày; Buyer hoặc Admin | `REFUNDED` |
| `DELIVERED` | `earlyRelease` | Buyer | `COMPLETED` |
| `DELIVERED` | `releaseAfterInspection` | Hết hạn kiểm tra | `COMPLETED` |
| `DELIVERED` | `raiseDispute` | Buyer, trong hạn kiểm tra | `DISPUTED` |
| `DISPUTED` | `resolveDispute` | 2 chữ ký của 2 bên khác nhau, còn hạn | `REFUNDED` hoặc `COMPLETED` |
| `DISPUTED` | `arbitratorForceResolve` | Quá `disputeTimeout` của đơn; Trọng tài | `REFUNDED` hoặc `COMPLETED` |

`COMPLETED` và `REFUNDED` là trạng thái cuối. Mọi cặp (trạng thái, hàm) không có trong bảng đều phải revert; bộ kiểm thử phải có ca âm cho từng cặp.

Các đơn cùng một lô thanh toán chỉ chung giao dịch nạp; sau đó không có quan hệ trạng thái nào giữa chúng. Mở khóa, khiếu nại, hoàn tiền, phán quyết và timeout được áp dụng riêng cho từng đơn (BR-11).

## 5.1. Ánh xạ sang trạng thái của bảng `orders` cũ

Giá trị ENUM của `orders.status` trong Slopee là `pending, paid, shipped, cancelled, received`; không sửa ENUM. Trạng thái Web3 là nguồn sự thật, bảng cũ chỉ là bản chiếu cho giao diện hiện có.

| Trạng thái Web3 | `orders.status` | Ghi chú |
|---|---|---|
| `PENDING_PAYMENT` | `pending` | Đã giữ chỗ tồn kho. |
| `LOCKED` | `paid` | Tiền đã khóa trong contract. |
| `DELIVERED` | `shipped` | \- |
| `DISPUTED` | `shipped` | Giữ nguyên; giao diện cũ thêm huy hiệu vàng Khiếu nại Web3 lấy từ `order_web3` (`LEFT JOIN` trong `GET /api/payments/orders`) và khóa nút thao tác thường. |
| `COMPLETED` | `received` | \- |
| `EXPIRED`, `REFUNDED` | `cancelled` | Hoàn tồn kho. |

Đường ghi trạng thái cũ `PUT /api/payments/orders/:id` phải từ chối đơn đã có dòng `order_web3` (mã `WEB3_ORDER_MANAGED`). Chỉ một hàm đồng bộ duy nhất được ghi `orders.status` của đơn Web3.
