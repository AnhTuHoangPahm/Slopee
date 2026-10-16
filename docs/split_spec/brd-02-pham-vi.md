<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, mục 2. Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 2. PHẠM VI DỰ ÁN 10 TUẦN: LÁT CẮT DỌC (VERTICAL SLICE MVP)

Để sản phẩm chạy trọn vẹn từ đầu đến cuối (End-to-End) trong 10 tuần mà không phải đập đi xây lại khi mở rộng, dự án phân chia phạm vi như sau:

| Phân hệ | Phạm vi MVP (Làm thật 100%) | Phạm vi Mở rộng (Phase 2 - chỉ thiết kế chỗ cắm) |
|---|---|---|
| **Thanh toán & Ký quỹ (Escrow)** | <span class="badge badge-green">LÀM THẬT</span> Ký quỹ on-chain bằng **token ERC-20 giả lập (MockUSD)** làm phương thức mặc định trên giao diện, nhằm tránh biến động tỷ giá. Smart Contract hỗ trợ cả ETH gốc và được kiểm thử đầy đủ; giao diện ETH là hạng mục "nếu còn thời gian". Giỏ hàng nhiều shop thanh toán gom một lần và tách thành đơn escrow độc lập theo shop (BR-11). | <span class="badge badge-orange">MỞ RỘNG</span> Fiat (VNPAY/MoMo), COD (sổ công nợ), SPayLater (hợp đồng tín dụng on-chain), stablecoin thật, oracle tỷ giá. |
| **Ký số & Pháp lý** | <span class="badge badge-green">LÀM THẬT</span> Ký giao dịch Web3 qua ví cá nhân (không lưu khóa); liên kết ví bằng chữ ký thông điệp; ký off-chain EIP-712 khi phân xử. | <span class="badge badge-orange">MỞ RỘNG</span> Chứng thư số công cộng qua CA thật (VNPT/Viettel), đóng mộc số e-Seal cho hóa đơn PDF. |
| **Hệ thống sàn (Slopee)** | <span class="badge badge-green">LÀM THẬT</span> Giữ nguyên Flask + MySQL; bổ sung Python Event Indexer; màn hình tối thiểu cho Buyer, Merchant, Shipper, Admin. | <span class="badge badge-orange">MỞ RỘNG</span> Tự động hạch toán hóa đơn điện tử vào ERP kế toán; multisig cho khóa quản trị; mạng testnet công khai. |

## 2.1. Ngoài phạm vi (Out of scope) của MVP

- Triển khai trên mainnet hoặc xử lý tiền thật; hệ thống chỉ chạy trên Anvil localhost phục vụ học thuật.
- Hoàn một phần tiền (partial refund); MVP chỉ hỗ trợ hoàn 100% hoặc giải ngân 100% theo từng đơn.
- Một đơn on-chain có nhiều Merchant (mỗi đơn on-chain luôn gắn đúng một Merchant; giỏ nhiều shop được tách thành nhiều đơn độc lập, xem BR-11); thanh toán gom quá 5 shop trong một lần; thanh toán gom nhiều loại token.
- Cơ chế bằng chứng tự động (video unbox lưu on-chain); Admin chỉ tham chiếu bằng chứng ngoài hệ thống, băm tài liệu lưu qua `docHash`.
- Tính năng pause khẩn cấp, nâng cấp contract (upgradeable proxy).
- Chính sách thời hạn theo từng sản phẩm riêng lẻ; MVP chỉ cấu hình theo nhóm hàng (BR-10).
