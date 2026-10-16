<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, mục 1. Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 1. TỔNG QUAN DỰ ÁN & TÀI LIỆU THAM CHIẾU

BÁO CÁO PHÂN TÍCH YÊU CẦU NGHIỆP VỤ HỆ THỐNG

TÀI LIỆU YÊU CẦU NGHIỆP VỤ (BRD)

Đề tài: Tự động hóa giao dịch trên Sàn TMĐT bằng Hợp đồng thông minh và Ký số không lưu khóa (Slopee)

|  |  |
|---|---|
| Mã tài liệu: | BRD-SLOPEE-MVP-01 |
| Phiên bản: | v5.3 (Kế hoạch 10 tuần - Bản hoàn thiện, cập nhật sau rà soát thiết kế và mã nguồn Slopee) |
| Nền tảng tích hợp: | Slopee Core (Flask / Python + MySQL) + EVM (Anvil) |
| Phạm vi: | Vertical Slice MVP (Crypto Escrow) + Extension Slots |
| Tài liệu đi kèm: | SRS-SLOPEE-MVP-01 v5.3; SDD-SLOPEE-MVP-01 v1.2 |

# 1. TỔNG QUAN DỰ ÁN & TÀI LIỆU THAM CHIẾU

## 1.1. Bối cảnh và vấn đề của sàn TMĐT truyền thống (Web2)

Trên các sàn TMĐT truyền thống như Shopee, cơ chế ký quỹ và thanh toán tồn tại các hạn chế cấu trúc:

- **Giam giữ dòng tiền và rủi ro cấn trừ (từ T+4 đến T+15):** Theo quy định Shopee công bố trên Seller Centre (\[REF-02\]) và Điều khoản Dịch vụ (\[REF-01\]), doanh thu đơn hàng được ghi nhận vào Số dư tài khoản Shopee của người bán ngay khi người mua bấm "Đã nhận được hàng", hoặc vào ngày thứ 4 kể từ khi giao thành công nếu không có yêu cầu trả hàng/hoàn tiền; đơn có nghi ngờ gian lận có thể phải chờ đến 15 ngày. Người mua vẫn được yêu cầu trả hàng/hoàn tiền trong vòng 15 ngày kể từ khi giao thành công (kể cả sau khi đã bấm nhận hàng), và sàn có thể cấn trừ Số dư của người bán nếu yêu cầu được chấp nhận. Sau khi tiền vào Số dư, rút về ngân hàng mất thêm khoảng 24-48 giờ làm việc. Người bán vì vậy bị đọng vốn và chịu rủi ro bị cấn trừ đơn phương.
- **Trọng tài đơn phương:** Sàn vừa nắm tiền vừa là bên duy nhất phân xử khiếu nại, tạo tâm lý thiếu minh bạch cho người bán.
- **Chi phí đối soát thủ công:** Sàn phải duy trì bộ phận kế toán chạy batch-job đối soát hoa hồng và phí thanh toán cuối kỳ.
- **Rủi ro lưu khóa tập trung:** Sàn lưu thông tin thanh toán và ủy quyền tập trung trên máy chủ, tiềm ẩn rủi ro lộ lọt dữ liệu.

## 1.2. Mục tiêu dự án và chỉ số đo lường (KPI)

| Mã | Mục tiêu | Chỉ số đo lường / Cách kiểm chứng |
|---|---|---|
| G-01 | Tiền của người mua được khóa bởi smart contract thay vì tài khoản của sàn. | Số dư contract khớp tổng tiền các đơn đang ở trạng thái `LOCKED/DELIVERED/DISPUTED` (kiểm tra bằng script đối soát). |
| G-02 | Giải ngân và trích phí hoàn toàn tự động, không đối soát thủ công. | 100% đơn hoàn tất có phí và tiền người bán đúng công thức BR-02 (test tự động). |
| G-03 | Phân xử tranh chấp có kiểm soát, minh bạch, có chữ ký xác minh được. | Mọi quyết định giải quyết tranh chấp đều có 2 chữ ký EIP-712 hợp lệ trên chuỗi, hoặc sự kiện timeout của Trọng tài. |
| G-04 | Không lưu khóa riêng tư của người dùng (BR-01). | Quét mã nguồn và CSDL: không có trường/biến chứa private key, seed phrase của người dùng. |
| G-05 | Dữ liệu sàn luôn đồng bộ với blockchain. | Sau khi xóa trạng thái và chạy lại indexer từ block đầu, bảng `orders` khớp 100% với trạng thái on-chain. |
| G-06 | Demo hoàn chỉnh end-to-end trước hội đồng. | Luồng thành công (happy path) hoàn tất trong dưới 3 phút; luồng tranh chấp hoàn tất trong dưới 5 phút. |

## 1.3. Tài liệu dẫn chiếu

- **\[REF-01\]:** Shopee Việt Nam, *Điều khoản Dịch vụ Shopee*, phần về Shopee Đảm Bảo và Số Dư Tài Khoản Shopee. URL: https://help.shopee.vn/portal/article/77242 (Truy cập ngày: 10/10/2026).
- **\[REF-02\]:** Shopee Seller Centre (Học viện Shopee), *Quy trình Shopee thanh toán cho Người bán* và *Quy trình Trả hàng/Hoàn tiền dành cho Người bán*. URL: https://banhang.shopee.vn/edu/article/234 và https://banhang.shopee.vn/edu/article/563 (Truy cập ngày: 10/10/2026).
- **\[REF-03\]:** EIP-712: *Typed Structured Data Hashing and Signing* (Ethereum Foundation).
- **\[REF-04\]:** Luật Giao dịch điện tử số 20/2023/QH15 của Quốc hội Việt Nam.
- **\[REF-05\]:** EIP-191: *Signed Data Standard* và EIP-4361: *Sign-In with Ethereum* (cơ sở cho bước liên kết ví với tài khoản).
- **\[REF-06\]:** OpenZeppelin Contracts v5.x: `AccessControl`, `ReentrancyGuard`, `EIP712`, `ECDSA`, `SafeERC20`.
