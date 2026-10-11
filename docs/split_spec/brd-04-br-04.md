<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, BR-04 (mục 4). Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# BR-04: Phân xử Tranh chấp có Kiểm soát bằng 2/3 Chữ ký EIP-712

Khi có khiếu nại, tiền bị phong tỏa trong Escrow. Contract chỉ giải ngân hoặc hoàn tiền khi nhận đủ 2 chữ ký số hợp lệ từ **2 bên khác nhau** thuộc bộ 3 vai trò `{Buyer, Merchant, Slopee Arbitrator}`. Địa chỉ nhận tiền (`payoutTo`) bắt buộc là Buyer hoặc Merchant. Mỗi chữ ký có **thời hạn hiệu lực (deadline)** và gắn với một số thứ tự (nonce) để không thể dùng lại ngoài ý muốn. Hạn hiệu lực của mọi chữ ký phải kết thúc **trước** thời điểm Trọng tài được quyền xử đơn phương (BR-05), và contract ép quy tắc này.

Để tránh một bên nắm 2 phiếu, Trọng tài không được tham gia giao dịch với tư cách Buyer hoặc Merchant, và hai địa chỉ cùng mang vai trò Trọng tài chỉ được tính là một phiếu.
