<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, BR-02 (mục 4). Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# BR-02: Quy tắc Phí sàn Cấu hình Động (Configurable Platform Fee)

**Công thức trích phí sàn:**  
`Platform Fee = (Order Amount * feeBps) / 10.000`  
`Merchant Payout = Order Amount - Platform Fee`

- Phí cơ sở mặc định: **300 BPS (3,0%)**.
- Admin cấu hình tỷ lệ phí mặc định (`defaultFeeBps`) trên chuỗi, không vượt trần an toàn **1.000 BPS (10,0%)**. Mức này đóng vai trò **trần phí**: contract từ chối mọi báo giá có phí cao hơn.
- Tỷ lệ phí của đơn được **chốt trong báo giá do sàn ký tại thời điểm tạo đơn** (BR-06) và lưu vào đơn on-chain khi nạp tiền; thay đổi phí sau đó không ảnh hưởng đơn đã tạo. Phí trong báo giá bằng mức phí cấu hình của sàn nhưng không vượt trần hiện hành trên chuỗi.
- Nếu Admin hạ trần phí sau khi báo giá đã phát hành và phí trong báo giá cao hơn trần mới, contract từ chối lần nạp và Buyer nhận báo giá mới với phí đã cập nhật. Buyer không bao giờ bị tính phí cao hơn mức đã hiển thị trong báo giá mà họ chấp nhận.
- Phí chỉ thu khi tiền được giải ngân cho Merchant. Khi hoàn tiền cho Buyer, hoàn 100% và không thu phí.
- Phép chia làm tròn xuống; phần dư (nếu có) thuộc về Merchant.
