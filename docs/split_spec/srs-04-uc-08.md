<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, UC-08 (mục 4). Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# UC-08: Đồng bộ sự kiện on-chain (Indexer) (BR-09)

- **Vòng lặp:** đọc `indexer_cursor`; lấy log từ `last_block + 1` đến `latest - CONFIRMATIONS` (Anvil: 0 hoặc 1; mạng thật: 12 trở lên); với mỗi log theo thứ tự (block, logIndex) trong một giao dịch CSDL: chèn `chain_events` (bỏ qua nếu trùng `tx_hash, log_index`), áp dụng thay đổi vào bảng nghiệp vụ, cập nhật con trỏ. Lỗi giữa chừng thì rollback, lần sau xử lý lại.
- **Bảo vệ reorg:** lưu hash của block cuối đã xử lý; nếu hash không còn khớp khi chạy lại, lùi con trỏ N block (mặc định 20) và xử lý lại.
- **Đối chiếu:** với `OrderCreated`, so khớp buyer, merchant, token, amount, `inspectionDuration`, `disputeTimeout`, `feeBps`, `docHash` với báo giá đã lưu; sai lệch → đặt `order_web3.anomaly_flag = 1`, ghi log cảnh báo, không tự sửa dữ liệu. Sự kiện cho đơn không tồn tại ở sàn → chỉ lưu `chain_events` và cảnh báo.
- **Thời gian block và đồng bộ ngược:** mỗi log kèm `block_timestamp` (đệm theo block, mỗi block gọi RPC một lần); mọi mốc thời gian dẫn xuất lấy từ đây, không dùng đồng hồ máy chủ. Mỗi lần đổi `order_web3.status`, Indexer cập nhật `orders.status` cũ trong cùng giao dịch theo bảng ánh xạ ở mục 5.1.
- **Chế độ replay:** tham số `--from-block 0 --reset` đặt lại các cột dẫn xuất của `order_web3` và trạng thái chiếu ở `orders` cũ rồi dựng lại từ đầu; kết quả phải khớp on-chain (AC-08).
- **Đối soát:** script đối chiếu tổng tiền các đơn đang mở theo từng token với số dư contract (AC-10).
