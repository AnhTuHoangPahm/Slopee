<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, BR-06 (mục 4). Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# BR-06: Ràng buộc đơn hàng bằng báo giá có chữ ký của sàn (Signed Quote)

Chỉ những đơn hàng đã được sàn xác nhận mới được ký quỹ. Khi Buyer đặt hàng, sàn phát hành một **báo giá** chứa mã đơn on-chain, ví Buyer, ví Merchant, loại token, số tiền, thời gian kiểm tra, thời hạn tranh chấp, tỷ lệ phí sàn (`feeBps`), mã băm chứng từ (`docHash`) và hạn dùng; báo giá được sàn ký EIP-712. Contract chỉ nhận tiền khi báo giá hợp lệ, chưa hết hạn, đúng người nạp và có tỷ lệ phí không vượt trần on-chain (BR-02). Quy tắc này ngăn: chiếm trước mã đơn, tự đổi ví Merchant, nạp sai số tiền, và phát hành báo giá với phí cao hơn mức quản trị cho phép.
