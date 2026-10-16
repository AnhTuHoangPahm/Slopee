<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, BR-07 (mục 4). Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# BR-07: Liên kết ví với tài khoản Slopee

Mỗi ví chỉ được dùng cho giao dịch khi đã được liên kết với tài khoản Slopee bằng cách ký một thông điệp có mã dùng một lần (nonce) và thời hạn (theo EIP-191/EIP-4361). Một tài khoản có thể có một ví đang hoạt động; đổi ví yêu cầu ký lại. Sàn chỉ phát hành báo giá cho ví đã liên kết. Ví của Merchant phải được liên kết trước khi sản phẩm được phép nhận đơn Web3.
