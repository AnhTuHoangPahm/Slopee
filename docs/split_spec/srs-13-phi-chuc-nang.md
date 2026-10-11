<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 13. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 13. YÊU CẦU PHI CHỨC NĂNG

| Nhóm | Yêu cầu |
|---|---|
| Bảo mật | Không lưu khóa người dùng; khóa sàn tách theo vai trò, nạp từ môi trường; mọi chữ ký có hạn dùng; token phiên ký có hạn, xác thực và phân quyền mọi API, kiểm tra quyền sở hữu tài nguyên, không có route thay đổi lược đồ qua HTTP; kiểm tra đầu vào (địa chỉ, số tiền, chữ ký); không ghi chữ ký hoặc khóa vào log. |
| Hiệu năng | Trạng thái đơn xuất hiện trên giao diện trong vòng 10 giây kể từ khi giao dịch được xác nhận (chu kỳ polling Indexer không quá 2 giây trên Anvil). |
| Độ tin cậy | Indexer khởi động lại không mất và không ghi đôi sự kiện; có chế độ replay; mọi thay đổi trạng thái đơn đều truy vết được tới `chain_events`. |
| Khả năng mở rộng | Trường `payment_method` và giao diện cổng thanh toán cho phép thêm FIAT, COD, SPayLater mà không đổi bảng `orders` (cột Web3 nằm ở `order_web3`). |
| Khả năng vận hành | Một lệnh dựng môi trường (Anvil, triển khai, cấp vai trò, nạp token thử); tệp cấu hình mẫu; nhật ký có cấp độ; script đối soát. |
| Kiểm thử được | Có thể tua thời gian trên Anvil (`evm_increaseTime`) để kiểm thử các hạn kiểm tra và timeout; mọi hạn so với `block.timestamp` tính bằng `now_chain`. |
| Chất lượng mã | Độ phủ dòng lệnh contract từ 90%; tài liệu hóa các hàm công khai; kiểm tra tĩnh (ví dụ Slither) không còn cảnh báo mức cao chưa được giải thích. |
