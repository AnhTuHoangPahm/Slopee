# Chỉ mục đặc tả (docs/spec)

Tệp sinh bởi `scripts/split_spec.py`. Bản chỉ đọc của BRD / SRS / SDD đã đóng băng. Bảng "việc nào → tệp nào" nằm ở `AI_CONTEXT.md` mục 9; hãy mở đúng tệp thay vì cả tài liệu.

| Tệp | Nội dung | KB |
|---|---|---|
| `brd-01-tong-quan.md` | 1. TỔNG QUAN DỰ ÁN & TÀI LIỆU THAM CHIẾU | 5.0 |
| `brd-02-pham-vi.md` | 2. PHẠM VI DỰ ÁN 10 TUẦN: LÁT CẮT DỌC (VERTICAL SLICE MVP) | 2.9 |
| `brd-03-chu-the.md` | 3. MA TRẬN CHỦ THỂ NGHIỆP VỤ (STAKEHOLDERS) | 2.6 |
| `brd-04-br-01.md` | BR-01: Nguyên tắc Ký số Không Lưu Khóa (Non-Custodial Mandate) | 0.6 |
| `brd-04-br-02.md` | BR-02: Quy tắc Phí sàn Cấu hình Động (Configurable Platform Fee) | 1.5 |
| `brd-04-br-03.md` | BR-03: Cửa sổ Kiểm tra Động & Mở khóa sớm (Dynamic Inspection & Early Release) | 1.0 |
| `brd-04-br-04.md` | BR-04: Phân xử Tranh chấp có Kiểm soát bằng 2/3 Chữ ký EIP-712 | 1.1 |
| `brd-04-br-05.md` | BR-05: Thoát hiểm khi Sự cố (Timeout & Emergency Exit) | 1.1 |
| `brd-04-br-06.md` | BR-06: Ràng buộc đơn hàng bằng báo giá có chữ ký của sàn (Signed Quote) | 1.0 |
| `brd-04-br-07.md` | BR-07: Liên kết ví với tài khoản Slopee | 0.7 |
| `brd-04-br-08.md` | BR-08: Định giá và quy đổi tiền tệ | 0.9 |
| `brd-04-br-09.md` | BR-09: Nguồn sự thật và đồng bộ dữ liệu | 0.6 |
| `brd-04-br-10.md` | BR-10: Chính sách thời hạn theo nhóm hàng (Category Policy) | 2.4 |
| `brd-04-br-11.md` | BR-11: Giỏ hàng nhiều shop: thanh toán gom một lần, vận hành tách đơn độc lập | 1.2 |
| `brd-05-vong-doi-don.md` | 5. VÒNG ĐỜI ĐƠN HÀNG (ORDER LIFECYCLE) | 1.3 |
| `brd-06-tin-cay-de-doa.md` | 6. GIẢ ĐỊNH TIN CẬY & MÔ HÌNH ĐE DỌA | 2.0 |
| `brd-07-phap-ly.md` | 7. KHUNG PHÁP LÝ VÀ GIỚI HẠN ÁP DỤNG | 1.1 |
| `brd-08-nghiem-thu.md` | 8. TIÊU CHÍ NGHIỆM THU (ACCEPTANCE CRITERIA) | 3.2 |
| `brd-09-rui-ro.md` | 9. RỦI RO DỰ ÁN & PHƯƠNG ÁN GIẢM THIỂU | 1.8 |
| `brd-10-lo-trinh.md` | 10. LỘ TRÌNH TỔNG QUAN & CỘT MỐC | 1.2 |
| `brd-11-thuat-ngu.md` | 11. THUẬT NGỮ | 1.4 |
| `srs-00-lich-su.md` | 0. LỊCH SỬ THAY ĐỔI (v4.1 → v5.0 → v5.1 → v5.2 → v5.3) | 6.5 |
| `srs-01-pham-vi-thuat-ngu.md` | 1. PHẠM VI, ĐỐI TƯỢNG VÀ THUẬT NGỮ | 2.1 |
| `srs-02-kien-truc.md` | 2. KIẾN TRÚC TỔNG THỂ & STACK CÔNG NGHỆ | 3.4 |
| `srs-03-phan-quyen.md` | 3. PHÂN QUYỀN | 1.4 |
| `srs-04-uc-00.md` | UC-00: Liên kết ví với tài khoản Slopee (BR-07) | 1.3 |
| `srs-04-uc-01.md` | UC-01: Tạo đơn và nhận báo giá (BR-06, BR-08) | 2.6 |
| `srs-04-uc-02.md` | UC-02: Buyer ký quỹ On-chain (Deposit Escrow) | 1.8 |
| `srs-04-uc-03.md` | UC-03: Shipper xác nhận giao hàng (BR-03) | 1.0 |
| `srs-04-uc-04.md` | UC-04: Giải ngân tự động & Mở khóa sớm (BR-02, BR-03) | 1.2 |
| `srs-04-uc-05.md` | UC-05: Buyer khiếu nại (BR-03, BR-04) | 0.7 |
| `srs-04-uc-06.md` | UC-06: Phân xử tranh chấp bằng 2/3 chữ ký EIP-712 (BR-04) | 2.4 |
| `srs-04-uc-07.md` | UC-07: Timeout và thoát hiểm (BR-05) | 0.8 |
| `srs-04-uc-08.md` | UC-08: Đồng bộ sự kiện on-chain (Indexer) (BR-09) | 1.9 |
| `srs-04-uc-09.md` | UC-09: Quản trị tham số | 1.0 |
| `srs-05-may-trang-thai.md` | 5. MÁY TRẠNG THÁI ĐƠN HÀNG | 2.6 |
| `srs-06-eip712.md` | 6. DỮ LIỆU CHUẨN EIP-712 | 1.1 |
| `srs-07-rest-api.md` | 7. GIAO DIỆN PROGRAMMING (REST API) | 3.5 |
| `srs-08-giao-dien.md` | 8. YÊU CẦU GIAO DIỆN TỐI THIỂU | 2.4 |
| `srs-09-database.md` | 9. THIẾT KẾ CƠ SỞ DỮ LIỆU MYSQL CHO MODULE BLOCKCHAIN | 14.2 |
| `srs-10-contract.md` | 10. MÃ NGUỒN SMART CONTRACT THAM CHIẾU (OPENZEPPELIN v5.x) | 16.2 |
| `srs-101-quyet-dinh-thiet-ke.md` | 10.1. Quyết định thiết kế và giới hạn đã biết | 3.8 |
| `srs-102-foundry.md` | 10.2. Cấu hình Foundry (foundry.toml) | 1.4 |
| `srs-11-lo-trinh.md` | 11. KẾ HOẠCH BÀN GIAO 10 TUẦN (DELIVERY ROADMAP) | 6.0 |
| `srs-121-test-contract.md` | 12.1. Ma trận kiểm thử Smart Contract (tối thiểu) | 5.6 |
| `srs-122-test-tich-hop-e2e.md` | 12.2. Kiểm thử tích hợp và end-to-end | 4.3 |
| `srs-123-test-hien-co-ci.md` | 12.3. Chuyển đổi bộ kiểm thử sẵn có và CI | 2.7 |
| `srs-13-phi-chuc-nang.md` | 13. YÊU CẦU PHI CHỨC NĂNG | 1.8 |
| `srs-14-truy-vet.md` | 14. MA TRẬN TRUY VẾT YÊU CẦU | 1.5 |
| `srs-15-nen-tang.md` | 15. ĐIỀU KIỆN NỀN TẢNG: HIỆN TRẠNG SLOPEE VÀ GIAI ĐOẠN 0 | 0.5 |
| `srs-151-hien-trang.md` | 15.1. Hiện trạng so với giả định của tài liệu này | 1.5 |
| `srs-152-loi-bao-mat.md` | 15.2. Lỗi bảo mật phát hiện | 3.4 |
| `srs-153-giai-doan-0.md` | 15.3. Giai đoạn 0: yêu cầu bắt buộc trước khi tích hợp | 3.6 |
