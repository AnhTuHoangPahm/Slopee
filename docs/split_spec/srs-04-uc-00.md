<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, UC-00 (mục 4). Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# UC-00: Liên kết ví với tài khoản Slopee (BR-07)

- **Tác nhân:** Buyer, Merchant. **Tiền điều kiện:** đã đăng nhập tài khoản Slopee (có token phiên hợp lệ, mục 15), đã cài MetaMask. Mã tài khoản lấy từ token, không nhận từ thân yêu cầu.
- **Luồng chính:**
  1.  Người dùng bấm "Kết nối ví"; Frontend lấy địa chỉ ví từ MetaMask.
  2.  Frontend gọi `POST /api/wallet/nonce`; Backend tạo nonce dùng một lần (hết hạn sau 5 phút) và thông điệp chuẩn: tên miền, địa chỉ, mã tài khoản, nonce, chainId, thời điểm phát hành và hết hạn.
  3.  MetaMask yêu cầu ký thông điệp (`personal_sign`), không tốn gas.
  4.  Frontend gửi chữ ký qua `POST /api/wallet/link`; Backend khôi phục địa chỉ ký, so khớp ví, kiểm tra nonce chưa dùng và còn hạn, rồi lưu `user_wallets`.
- **Luồng thay thế:** nonce hết hạn hoặc đã dùng, chữ ký sai, ví đã liên kết với tài khoản khác → từ chối, không thay đổi dữ liệu. Đổi ví: ví cũ chuyển `is_active = 0`, yêu cầu ký lại với ví mới.
