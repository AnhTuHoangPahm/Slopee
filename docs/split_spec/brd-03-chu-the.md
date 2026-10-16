<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, mục 3. Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 3. MA TRẬN CHỦ THỂ NGHIỆP VỤ (STAKEHOLDERS)

| Chủ thể | Hành vi nghiệp vụ trong MVP | Cơ chế xác thực / Bảo mật |
|---|---|---|
| **Người mua (Buyer)** | Liên kết ví, đặt hàng, nạp tiền vào Escrow qua MetaMask, xác nhận mở khóa sớm (Early Release), tạo khiếu nại, ký chấp nhận phán quyết. | Tự giữ private key tại ví cá nhân (non-custodial). Ký off-chain EIP-712 khi chấp nhận giải pháp tranh chấp. |
| **Người bán (Merchant)** | Đăng bán, liên kết ví nhận tiền, nhận thanh toán tự động (đã trừ phí sàn) khi kết thúc thời hạn kiểm tra, ký chấp thuận thỏa thuận tranh chấp. | Liên kết ví bằng chữ ký thông điệp. Ký off-chain EIP-712 khi tham gia phân xử. |
| **Đơn vị Vận chuyển (Shipper)** | Cập nhật trạng thái "Đã giao hàng" để kích hoạt cửa sổ kiểm tra. | Tài khoản Slopee có vai trò Shipper thao tác trên cổng giao vận; ví của sàn giữ `SHIPPER_ROLE` trên contract và gửi giao dịch thay mặt (xem mục 3.1). |
| **Sàn TMĐT (Slopee)** | Phát hành báo giá có chữ ký, thu phí hoa hồng tự động, đóng vai Trọng tài (`ARBITRATOR_ROLE`) trong cơ chế 2/3 chữ ký, xử lý timeout. | Sàn giữ 1 phiếu trong bộ 3. Sàn không thể tự rút tiền nếu thiếu chữ ký đối ứng, trừ trường hợp hết hạn tranh chấp (BR-05). |
| **Quản trị viên (Admin)** | Thẩm định khiếu nại, đề xuất phán quyết, cấu hình phí sàn trong ngưỡng an toàn và chính sách thời hạn theo nhóm hàng. | Tài khoản Slopee có vai trò Admin; thao tác ký của Trọng tài thực hiện qua dịch vụ ký phía máy chủ. |

## 3.1. Quản lý khóa của sàn (ngoại lệ có kiểm soát của BR-01)

Nguyên tắc "không lưu khóa" áp dụng cho **khóa của người dùng cuối** (Buyer, Merchant). Riêng các khóa vận hành của sàn (Trọng tài, Shipper, người ký báo giá, ví thu phí) bắt buộc phải do máy chủ nắm giữ để thực thi tự động. Các khóa này:

- Tách biệt hoàn toàn: mỗi vai trò dùng một khóa riêng, không dùng chung.
- Nạp từ biến môi trường hoặc kho bí mật, tuyệt đối không ghi vào CSDL hay commit vào mã nguồn.
- Trong MVP là khóa của môi trường Anvil; ở Phase 2 chuyển sang KMS/HSM và multisig.
