<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, BR-08 (mục 4). Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# BR-08: Định giá và quy đổi tiền tệ

- Giá niêm yết trên sàn là VND. Khi tạo báo giá, sàn quy đổi sang số lượng token theo **tỷ giá cố định cấu hình trong hệ thống** (ví dụ 1 MockUSD = 25.000 VND), và chốt số lượng token trong báo giá.
- Số tiền ký quỹ không thay đổi sau khi báo giá được chấp nhận, bất kể biến động tỷ giá về sau.
- Toàn bộ nền tảng Slopee dùng VND, là số nguyên không có phần lẻ (giá sản phẩm, tổng đơn, số dư giả lập). Giá trị USD không còn xuất hiện trên giao diện.
- Ở MVP không dùng oracle giá. Tích hợp oracle tỷ giá thuộc Phase 2.
