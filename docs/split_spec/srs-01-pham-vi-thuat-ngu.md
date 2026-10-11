<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 1. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 1. PHẠM VI, ĐỐI TƯỢNG VÀ THUẬT NGỮ

Tài liệu mô tả yêu cầu kỹ thuật cho mô-đun Web3 tích hợp vào sàn Slopee: smart contract escrow, dịch vụ đồng bộ sự kiện (indexer), các API bổ sung của Flask và các màn hình React. Phần nghiệp vụ được quy định trong BRD-SLOPEE-MVP-01 v5.3; mỗi yêu cầu trong tài liệu này dẫn chiếu mã quy tắc nghiệp vụ (BR-xx) tương ứng.

| Thuật ngữ | Giải thích |
|---|---|
| orderId (on-chain) | Số nguyên 256-bit định danh đơn trên contract, do sàn cấp, ánh xạ 1-1 với `orders.id` (UUID) của Slopee. |
| Quote (báo giá) | Cấu trúc dữ liệu EIP-712 do sàn ký, cho phép Buyer nạp tiền cho đúng một đơn. |
| Bên (party) | Một trong ba vai trò tham gia phân xử: Buyer, Merchant, Arbitrator. |
| MockUSD | ERC-20 giả lập (6 chữ số thập phân, đã chốt) dùng làm đồng tiền mặc định. |
| Nhóm hàng | Phân loại dùng để tra chính sách `inspectionDuration` và `disputeTimeout` (bảng `category_policies`). Danh mục sản phẩm của Slopee được gán vào nhóm qua `category_policy_map`. |
| Đồng hồ chuỗi (`now_chain`) | `max(đồng hồ hệ thống, thời gian block mới nhất)`, dùng cho mọi hạn so với `block.timestamp`; `now_system` chỉ dùng cho nonce liên kết ví, phiên đăng nhập và giới hạn tần suất. |
| Lô thanh toán (checkout group) | Tập các đơn con (mỗi shop một đơn) được nạp trong một giao dịch `depositEscrowBatch`; nguyên tử, tối đa 5 đơn, một token. |
| Giai đoạn 0 | Nhóm việc nền tảng (xác thực, phân quyền, sửa lỗi bảo mật Slopee) bắt buộc xong trước khi tích hợp Web3 (mục 15). |
| Relayer | Dịch vụ của sàn gửi giao dịch hộ (ví dụ `confirmDelivery`, nộp chữ ký tranh chấp); không có quyền di chuyển tiền ngoài các hàm công khai của contract. |
