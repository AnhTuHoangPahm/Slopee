<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, UC-06 (mục 4). Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# UC-06: Phân xử tranh chấp bằng 2/3 chữ ký EIP-712 (BR-04)

- **Tác nhân:** Admin, Buyer, Merchant.
- **Luồng chính:**
  1.  Admin thẩm định bằng chứng và chọn phán quyết: `payoutTo` = Buyer (hoàn tiền) hoặc Merchant (giải ngân). Backend đọc `disputeNonces(orderId)` từ contract, đặt `deadline` = min(`now_chain` + `DISPUTE_SIG_TTL_SECONDS` (mặc định 7 ngày), `disputedAt + disputeTimeout - 1`) để chữ ký luôn hết hạn trước khi Trọng tài có quyền xử đơn phương; contract cũng từ chối mọi chữ ký có `deadline` không nhỏ hơn `disputedAt + disputeTimeout`; tạo bản ghi `dispute_resolutions` trạng thái `PROPOSED`.
  2.  Backend ký phán quyết bằng `ARBITRATOR_KEY` và lưu chữ ký vai Arbitrator (`dispute_signatures`).
  3.  Buyer và Merchant xem đề xuất. Bên đồng ý ký bằng MetaMask (`eth_signTypedData_v4`, không tốn gas); Backend khôi phục địa chỉ ký, kiểm tra trùng với ví đã liên kết của bên đó và lưu chữ ký.
  4.  Khi có ít nhất 2 chữ ký của 2 bên khác nhau, trạng thái `READY`. Vì chữ ký Trọng tài đã có từ bước 2, một chữ ký hợp lệ của Buyer hoặc Merchant là đủ; giao diện phải cảnh báo rõ rằng việc ký cho phép bất kỳ ai thi hành ngay. Bất kỳ ai (mặc định bên được lợi, hoặc relayer của sàn) nộp `resolveDispute(orderId, payoutTo, deadline, sig1, sig2)`.
  5.  Contract kiểm tra, rồi hoàn 100% cho Buyer hoặc giải ngân cho Merchant (trừ phí theo BR-02), phát `OrderRefunded` hoặc `OrderCompleted`, rồi `DisputeResolved`. Indexer đặt `dispute_resolutions.status = EXECUTED`.
- **Luồng thay thế:** nếu cả hai bên không ký trong hạn → chữ ký hết hạn (`EXPIRED`); Admin có thể tạo đề xuất mới. Nếu bế tắc kéo dài đến hết `disputeTimeout` của đơn → UC-07.
- **Luồng lỗi (contract từ chối):** hai chữ ký cùng một bên; chữ ký không thuộc bộ ba; `payoutTo` không phải Buyer hoặc Merchant; chữ ký hết hạn hoặc có `deadline` không nhỏ hơn `disputedAt + disputeTimeout`; sai số tiền hoặc sai nonce; đơn không ở `DISPUTED`.
