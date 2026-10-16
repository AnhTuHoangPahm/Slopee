<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 7. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 7. GIAO DIỆN PROGRAMMING (REST API)

Mọi endpoint, trừ đăng nhập, đăng ký và danh sách sản phẩm công khai, yêu cầu token phiên trong header `Authorization` (mục 15). Định danh người dùng luôn lấy từ token, không nhận từ thân yêu cầu hay đường dẫn. `:code` là `orders.id` (UUID) của Slopee.

| Phương thức và đường dẫn | Mô tả | Quyền |
|---|---|---|
| `POST /api/wallet/nonce` | Cấp nonce và thông điệp liên kết ví | Đã đăng nhập |
| `POST /api/wallet/link` | Gửi chữ ký, liên kết ví | Đã đăng nhập |
| `GET /api/wallet` | Ví đang liên kết | Đã đăng nhập |
| `POST /api/orders` | Tạo lô thanh toán Web3 từ giỏ hàng (một hoặc nhiều shop, tối đa 5) và trả `checkout_group_id`, `total_amount_raw` cùng mảng `orders` (mỗi phần tử gồm `order_id`, `quote`, `signature`, `fee_bps`) (UC-01) | Buyer |
| `POST /api/checkout-groups/:id/quote` | Cấp lại báo giá cho cả lô nếu hết hạn hoặc phí đổi | Buyer của lô |
| `GET /api/checkout-groups/:id` | Danh sách đơn con của lô và trạng thái từng đơn | Buyer của lô |
| `GET /api/orders/:code` | Chi tiết đơn, giá VND, token, số tiền, hạn các mốc | Buyer, Merchant, Admin |
| `GET /api/orders/:code/status` | Trạng thái đơn cho polling | Buyer, Merchant, Admin |
| `POST /api/shipper/orders/:code/deliver` | Xác nhận giao hàng qua relayer (UC-03) | Shipper |
| `POST /api/orders/:code/dispute-note` | Lưu lý do và đường dẫn bằng chứng của khiếu nại (giao dịch `raiseDispute` do Buyer tự gửi) | Buyer |
| `POST /api/admin/disputes/:code/proposal` | Tạo đề xuất phán quyết và chữ ký Trọng tài (UC-06) | Admin |
| `GET /api/disputes/:code` | Đề xuất, danh sách chữ ký, trạng thái | Buyer, Merchant, Admin |
| `POST /api/disputes/:code/signatures` | Gửi chữ ký EIP-712 của Buyer hoặc Merchant | Buyer, Merchant |
| `POST /api/disputes/:code/submit` | Relayer nộp `resolveDispute` khi đủ chữ ký (tùy chọn) | Buyer, Merchant, Admin |
| `GET /api/categories/policies` | Danh sách nhóm hàng và thời hạn kiểm tra, thời hạn tranh chấp tương ứng (hiển thị cho Buyer và Merchant) | Đã đăng nhập |
| `PUT /api/admin/category-policies/:code` | Cập nhật chính sách một nhóm hàng; chỉ áp dụng cho đơn mới, kiểm tra giới hạn 1 giờ-30 ngày và 7-90 ngày | Admin |
| `PUT /api/admin/settings` | Cập nhật tỷ giá, hạn báo giá, hạn chữ ký | Admin |
| `GET /api/admin/reconcile` | Kết quả đối soát số dư contract và dữ liệu sàn | Admin |
| `GET /api/shipper/orders` | Danh sách đơn `LOCKED` được gán cho Shipper | Shipper |
| `PUT /api/admin/category-policy-map/:categoryId` | Gán danh mục sản phẩm vào nhóm chính sách | Admin |
| `PUT /api/payments/orders/:id` (hiện có) | Chỉ cho chủ đơn, kiểm trạng thái hợp lệ, từ chối đơn Web3 (`WEB3_ORDER_MANAGED`) | Chủ đơn |

Quy ước lỗi: mã HTTP 4xx kèm trường `code` (ví dụ `UNAUTHENTICATED`, `FORBIDDEN`, `QUOTE_EXPIRED`, `FEE_CAP_CHANGED`, `WALLET_NOT_LINKED`, `BAD_SIGNATURE`, `INVALID_STATE`, `WEB3_ORDER_MANAGED`, `BATCH_TOO_LARGE`) và thông báo tiếng Việt cho người dùng.
