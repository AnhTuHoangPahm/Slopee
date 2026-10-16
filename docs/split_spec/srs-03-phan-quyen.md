<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 3. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 3. PHÂN QUYỀN

| Hành động | Buyer | Merchant | Shipper | Arbitrator | Admin | Bất kỳ ai |
|---|---|---|---|---|---|---|
| `depositEscrow` (cần báo giá) | Có | \- | \- | Không | \- | \- |
| `depositEscrowBatch` (mỗi đơn một báo giá) | Có | \- | \- | Không | \- | \- |
| `confirmDelivery` | \- | \- | Có | \- | \- | \- |
| `earlyRelease` | Có | \- | \- | \- | \- | \- |
| `releaseAfterInspection` | Có | Có | Có | Có | Có | Có (sau hạn) |
| `raiseDispute` (trong hạn) | Có | \- | \- | \- | \- | \- |
| `resolveDispute` (cần 2 chữ ký) | Nộp | Nộp | Nộp | Nộp | Nộp | Nộp |
| `arbitratorForceResolve` (sau `disputeTimeout`) | \- | \- | \- | Có | \- | \- |
| `cancelIfUnfulfilled` (sau 14 ngày) | Có | \- | \- | \- | Có | \- |
| `claimPending` | Chủ sở hữu khoản chờ rút |  |  |  |  |  |
| `setDefaultFeeBps` (trần phí), `setFeeRecipient` | \- | \- | \- | \- | Có | \- |

Bảng trên là quyền trên contract. Ở tầng API, bốn vai trò tài khoản Slopee là `user` (Buyer), `seller` (Merchant), `shipper` và `admin`; vai trò Trọng tài là dịch vụ ký phía máy chủ, không phải tài khoản đăng nhập. Mọi API Web3 kiểm vai trò và quyền sở hữu từ token phiên (mục 15).
