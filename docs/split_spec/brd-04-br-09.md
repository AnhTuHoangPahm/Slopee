<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, BR-09 (mục 4). Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# BR-09: Nguồn sự thật và đồng bộ dữ liệu

Trạng thái tiền và đơn Web3 lấy từ blockchain làm nguồn sự thật. Cơ sở dữ liệu của sàn chỉ phản ánh lại thông qua Event Indexer; giao diện không tự cập nhật trạng thái đơn từ phản hồi của ví. Mọi sự kiện xử lý phải idempotent và truy vết được (mã giao dịch, chỉ số log).
