<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, BR-11 (mục 4). Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# BR-11: Giỏ hàng nhiều shop: thanh toán gom một lần, vận hành tách đơn độc lập

- Khi giỏ hàng có sản phẩm của nhiều shop, Buyer vẫn thanh toán một lần với đúng hai lần xác nhận ví: cho phép (approve) tổng số tiền của cả giỏ, rồi một giao dịch nạp gom.
- Sàn tách giỏ thành một đơn cho mỗi shop. Mỗi đơn có báo giá, mã đơn on-chain, thời gian kiểm tra và thời hạn tranh chấp riêng, và gắn đúng một Merchant.
- Nạp gom là nguyên tử: tất cả đơn trong lần thanh toán cùng thành công hoặc cùng bị từ chối; không có trạng thái nạp một phần.
- Sau khi nạp, mỗi đơn vận hành hoàn toàn độc lập: mở khóa, khiếu nại, hoàn tiền, phán quyết và timeout của đơn này không ảnh hưởng đơn của shop khác.
- Giới hạn MVP: một loại token cho cả lần thanh toán và tối đa 5 shop mỗi lần (giới hạn của bản demo).
