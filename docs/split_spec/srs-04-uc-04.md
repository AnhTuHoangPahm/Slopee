<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, UC-04 (mục 4). Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# UC-04: Giải ngân tự động & Mở khóa sớm (BR-02, BR-03)

- **Kịch bản 1 (Mở khóa sớm):** Buyer bấm "Đã nhận hàng" → `earlyRelease(orderId)` → Merchant nhận `amount - feeAmount`, ví thu phí nhận `feeAmount = amount * feeBps / 10000` (`feeBps` chốt trong báo giá, không vượt trần on-chain, mặc định 300).
- **Kịch bản 2 (Hết hạn kiểm tra):** khi `block.timestamp >= deliveredAt + inspectionDuration` và đơn vẫn `DELIVERED`, bất kỳ ai gọi `releaseAfterInspection(orderId)`. Một tác vụ nền của sàn tự gọi hàm này cho các đơn đến hạn (không bắt buộc, vì ai cũng có thể gọi).
- **Hậu điều kiện:** trạng thái `COMPLETED`, phát `OrderCompleted(orderId, netPayout, feeAmount)`.
- **Trường hợp đặc biệt:** nếu ví Merchant là contract từ chối nhận ETH, phần của người đó được ghi vào `pendingWithdrawals` và sự kiện `PayoutDeferred`; người đó gọi `claimPending` sau.
