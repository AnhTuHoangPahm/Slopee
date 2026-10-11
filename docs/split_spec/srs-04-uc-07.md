<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, UC-07 (mục 4). Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# UC-07: Timeout và thoát hiểm (BR-05)

- **Delivery Timeout:** đơn `LOCKED` quá 14 ngày kể từ `createdAt` → Buyer hoặc Admin gọi `cancelIfUnfulfilled` → hoàn 100% cho Buyer. Giao diện Buyer hiện nút này khi đến hạn; tác vụ nền của sàn có thể nhắc.
- **Dispute Timeout:** đơn `DISPUTED` quá `disputeTimeout` của đơn (7-90 ngày theo nhóm hàng, mặc định 30 ngày) kể từ `disputedAt` → Trọng tài gọi `arbitratorForceResolve(orderId, payoutTo)`; hoàn tiền Buyer hoặc giải ngân Merchant. Hành động này được ghi nhận là giả định tin cậy vào sàn (BRD mục 6).
