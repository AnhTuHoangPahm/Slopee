<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 0. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 0. LỊCH SỬ THAY ĐỔI (v4.1 → v5.0 → v5.1 → v5.2 → v5.3)

BÁO CÁO THIẾT KẾ KỸ THUẬT PHẦN MỀM (ISO/IEC/IEEE 29148:2018)

ĐẶC TẢ YÊU CẦU PHẦN MỀM (SRS)

Dự án: Tích hợp Hợp đồng thông minh Escrow và Ký điện tử không lưu khóa vào Sàn Slopee

|  |  |
|---|---|
| Mã tài liệu: | SRS-SLOPEE-MVP-01 |
| Phiên bản: | v5.3 (Kế hoạch 10 tuần - Bản hoàn thiện, thanh toán gom nhiều shop, chuyển VND) |
| Công nghệ: | Python Flask / MySQL 8.0 / React (ethers.js) / Solidity (Anvil) |
| Kiến trúc: | Hexagonal Architecture + Event-driven Indexer |
| Tài liệu đi kèm: | BRD-SLOPEE-MVP-01 v5.3; SDD-SLOPEE-MVP-01 v1.2 |

# 0. LỊCH SỬ THAY ĐỔI (v4.1 → v5.0 → v5.1 → v5.2 → v5.3)

Bảng dưới là các thay đổi của v5.0 so với v4.1; các thay đổi của v5.1, v5.2 và v5.3 nằm ngay sau bảng.

| \# | Thay đổi | Liên quan |
|---|---|---|
| 1 | Thêm `disputedAt` và hàm `arbitratorForceResolve` để hiện thực Dispute Timeout (v4.1 khai báo hằng số nhưng chưa có hàm). | BR-05 |
| 2 | Thêm `deadline` vào chữ ký `DisputeResolution`; mỗi chữ ký có hạn dùng. | BR-04 |
| 3 | Nạp tiền phải kèm báo giá EIP-712 do sàn ký (`OrderQuote`), ràng buộc mã đơn, ví Buyer, ví Merchant, token, số tiền, `docHash`. | BR-06 |
| 4 | Chữ ký tranh chấp được tính theo "bên" (Buyer / Merchant / Trọng tài), không theo địa chỉ; hai địa chỉ cùng vai Trọng tài chỉ là một phiếu. Cấm Trọng tài làm Buyer/Merchant. | BR-04 |
| 5 | Thêm sổ chờ rút (pull-payment) khi người nhận ETH từ chối nhận; từ chối token phí-khi-chuyển (fee-on-transfer). | BR-05 |
| 6 | Thêm UC-00 liên kết ví, UC-01 tạo đơn và báo giá, quy đổi VND sang token; làm rõ khóa vận hành của sàn. | BR-01, 07, 08 |
| 7 | Bổ sung bảng CSDL: `user_wallets`, `wallet_nonces`, `order_quotes`, `dispute_resolutions`, `dispute_signatures`, `indexer_cursor`, `platform_settings`; mở rộng `orders`. Đổi trạng thái `CREATED` thành `PENDING_PAYMENT` (trạng thái chỉ có ở sàn), thêm `EXPIRED`. | BR-09 |
| 8 | Sửa "97%/3%" thành "theo `feeBps`"; bổ sung mô hình tin cậy, danh sách API, kế hoạch kiểm thử, ma trận truy vết, lộ trình có cột mốc và phân công theo vai trò. | BR-02 |

### Thay đổi trong v5.1

| \# | Thay đổi | Liên quan |
|---|---|---|
| 9 | Thời hạn tranh chấp theo nhóm hàng: thêm `disputeTimeout` vào báo giá `OrderQuote`, lưu trong đơn, giới hạn 7-90 ngày; `arbitratorForceResolve` dùng giá trị của từng đơn thay cho hằng số 30 ngày. | BR-05, BR-10 |
| 10 | Thêm bảng `category_policies`, cột `category_code` và `dispute_timeout` ở `orders`, API chính sách nhóm hàng; hạn chữ ký phán quyết bị chặn trên bởi `disputedAt + disputeTimeout`. | BR-10 |
| 11 | Thêm cấu hình Foundry (`foundry.toml`: solc 0.8.20, optimizer, `via_ir`, remappings) ở mục 10.2. | Môi trường |
| 12 | Phân công cho nhóm 3 người với dự phòng chéo (mục 11); thêm ca kiểm thử T-20, T-21, I-04. | AC-12 |

### Thay đổi trong v5.2

| \# | Thay đổi | Liên quan |
|---|---|---|
| 13 | Thêm `buyer` và `feeBps` vào `Quote` và `OrderQuote` (struct ABI và kiểu EIP-712 trùng nhau). `defaultFeeBps` trở thành trần phí on-chain; phí của đơn chốt trong báo giá và phải không vượt trần (`require(q.feeBps <= defaultFeeBps)`, `require(q.buyer == msg.sender)`). | BR-02, BR-06, AC-13 |
| 14 | `resolveDispute` ép `deadline < disputedAt + disputeTimeout`; backend ký `deadline = min(now_chain + TTL, disputedAt + disputeTimeout - 1)`, bỏ điểm giao nhau với `arbitratorForceResolve` tại đúng mốc timeout. | BR-04, BR-05 |
| 15 | Thay việc mở rộng bảng `orders` bằng bảng 1-1 `order_web3`; đổi mọi khóa sang `VARCHAR(36)` cho khớp UUID của Slopee; mốc thời gian chuỗi lưu `BIGINT`; thêm `chain_events.block_timestamp`, `tx_outbox`, `onchain_id_seq`, `pending_balances`, `shipper_assignments`, `category_policy_map`; đồng bộ trạng thái ngược sang `orders` cũ (mục 5.1). | BR-09, BR-10 |
| 16 | Tách đồng hồ `now_system()` và `now_chain()`; Anvil chạy với `--block-time 2`. | BR-05, BR-06 |
| 17 | Thêm vai trò `shipper` vào `users.role` và quan hệ Shipper-đơn; MVP chặn thanh toán Web3 khi giỏ có nhiều shop; giá và tổng tiền đơn Web3 là VND số nguyên. | BR-03, BR-06, BR-08 |
| 18 | Thêm mục 15: điều kiện nền tảng và Giai đoạn 0 (xác thực, phân quyền, sửa các lỗi bảo mật của Slopee) phải xong trước khi tích hợp. | BR-01, BR-07 |
| 19 | Thêm ca kiểm thử T-22 đến T-24, I-05, I-06, A-01 đến A-07; sửa T-08, T-15, T-21; thêm AC-13 ở BRD. | AC-13 |

### Thay đổi trong v5.3

| \# | Thay đổi | Liên quan |
|---|---|---|
| 20 | Thanh toán gom: thêm `depositEscrowBatch` (nguyên tử, tối đa 5 đơn, một token, một lần chuyển token). Mọi kiểm tra của `depositEscrow` dùng chung một hàm nội bộ `_acceptQuote` nên không có đường nạp yếu hơn; mã đơn trùng trong cùng lô bị từ chối. | BR-11, BR-06 |
| 21 | Bỏ việc chặn giỏ nhiều shop: giỏ được tách thành một đơn cho mỗi shop (báo giá, mã đơn on-chain, thời hạn riêng), thanh toán gom với đúng hai lần xác nhận ví; thêm bảng `checkout_groups`, cột `order_web3.checkout_group_id`, API theo lô. | BR-11, AC-14 |
| 22 | Toàn bộ Slopee dùng VND số nguyên (cột tiền `DECIMAL(15,0)`, định dạng VND ở giao diện, không còn USD); thêm P0-07. | BR-08 |
| 23 | Chốt cơ chế xác thực bằng token ký (P0-01). Hai lỗi S-08 và S-13 đã được kiểm chứng; bổ sung phát hiện `reviews` bản đầu thiếu `UNIQUE(userId, productId)`. | Mục 15 |
| 24 | Thêm ca kiểm thử T-25 đến T-34, I-07, E-07. | AC-14 |
| 25 | Giữ nguyên stack frontend hiện có (React 19, JavaScript, không TypeScript, không TanStack Query), chỉ thêm `ethers` v6; thêm yêu cầu client API chung và route guard (mục 8); thêm kiểm thử frontend F-01 đến F-06, chuyển bộ test sẵn có và CI (mục 12.3); thêm P0-08. | Mục 8, 12, 15 |
