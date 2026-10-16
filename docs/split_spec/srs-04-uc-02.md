<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, UC-02 (mục 4). Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# UC-02: Buyer ký quỹ On-chain (Deposit Escrow)

- **Tiền điều kiện:** có báo giá còn hạn; ví Buyer kết nối mạng Anvil, đủ số dư token và ETH trả gas.
- **Luồng chính (MockUSD):**
  1.  Frontend gọi `approve(escrow, total_amount_raw)` với tổng của cả giỏ trên MockUSD (MetaMask yêu cầu xác nhận lần 1).
  2.  Frontend gọi `depositEscrowBatch(quotes, quoteSigs)` (xác nhận lần 2); giỏ một shop dùng cùng đường này với một phần tử.
  3.  Contract kiểm tra từng báo giá, thu tổng tiền bằng đúng một lần chuyển token, ghi từng đơn ở trạng thái `LOCKED` và phát một `OrderCreated` cho mỗi đơn. Cả lô thành công hoặc thất bại cùng nhau.
  4.  Indexer bắt sự kiện, đối chiếu với dữ liệu sàn, cập nhật `order_web3.status = LOCKED` (và `orders.status = paid`) cho từng đơn, kèm `deposit_tx_hash` (chung một giao dịch cho cả lô), rồi xóa các `cartItems` của sản phẩm thuộc đơn đó.
  5.  Frontend nhận trạng thái mới qua polling `GET /api/orders/:code/status`.
- **Luồng ETH (nếu còn thời gian):** token = `address(0)`, gửi kèm `msg.value = amount`, không cần `approve`.
- **Luồng lỗi:** báo giá hết hạn, sai người nạp, mã đơn đã tồn tại, sai số tiền ETH, thiếu allowance, phí trong báo giá vượt trần on-chain, ví gửi khác `buyer` trong báo giá, mã đơn trùng nhau trong lô, bất kỳ báo giá nào trong lô không hợp lệ → cả giao dịch revert, không đơn nào được tạo; Frontend hiển thị lý do và cho phép yêu cầu báo giá mới.
