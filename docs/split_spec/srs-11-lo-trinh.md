<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 11. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 11. KẾ HOẠCH BÀN GIAO 10 TUẦN (DELIVERY ROADMAP)

Bốn làn công việc: **\[C\]** Smart Contract, **\[B\]** Backend và Indexer, **\[F\]** Frontend, **\[Q\]** Kiểm thử và tài liệu. Nhóm có 3 thành viên nên mỗi người đảm nhận một làn chính, làn \[Q\] chia đều, và có dự phòng chéo như bảng dưới.

| Thành viên | Phụ trách chính | Dự phòng cho | Ghi chú |
|---|---|---|---|
| **A** (Contract và bảo mật) | \[C\] toàn bộ; \[Q\] kiểm thử contract, rà soát bảo mật | B (phần ký EIP-712, relayer) | Xong M1 (cuối tuần 2) thì chuyển sang hỗ trợ: tuần 3-4 viết thư viện ký EIP-712 và relayer cùng B, đồng thời nhận phần còn lại của Giai đoạn 0 (mục 15.3); từ tuần 5 nhận màn hình Shipper và Admin của \[F\]. |
| **B** (Backend và Indexer) | \[B\] toàn bộ; \[Q\] kiểm thử API, indexer, đối soát | A (contract, ký số) | Tuần 3-6 là điểm nghẽn của cả nhóm; ưu tiên hoàn thành báo giá và indexer trước. |
| **C** (Giao diện và tài liệu) | \[F\] toàn bộ; \[Q\] kiểm thử end-to-end, tài liệu, demo | B (API đơn giản, tài liệu) | Tuần 1-3 dựng giao diện với dữ liệu giả (mock API) để không chờ backend; tích hợp thật từ tuần 4. |

**Giai đoạn 0 (mục 15).** Lớp xác thực và phân quyền của Slopee chưa tồn tại; bước 1 và 2 phải xong trước UC-00 (tuần 3) và bắt đầu ngay tuần 1. Nếu trễ, cắt tính năng phụ theo quy tắc dưới đây, không cắt Giai đoạn 0.

**Quy tắc vận hành:** mỗi thay đổi được một thành viên khác xem lại trước khi gộp; họp ngắn 2 lần mỗi tuần để chốt vướng mắc. Nếu M2 trễ quá 3 ngày thì cắt tính năng phụ (giao diện rút khoản chờ rút, màn hình Merchant nâng cao, giao diện ETH) trước khi cắt luồng chính.

| Tuần | Công việc | Kết quả đầu ra / Tiêu chí hoàn thành |
|---|---|---|
| **1** | \[C\] Khung dự án Foundry (cấu hình ở mục 10.2), MockUSD, `depositEscrow` với báo giá, `confirmDelivery`, giải ngân, hủy quá hạn. \[B\] Script khởi tạo môi trường một lệnh (Anvil, triển khai, cấp vai trò). \[B\] Giai đoạn 0, bước 1 và 2 (mục 15): lớp xác thực và sửa lỗi S-01 đến S-04. \[B\] \[F\] P0-07 chuyển Slopee sang VND. \[F\] Client API chung có token, route guard, hàm định dạng VND (P0-07); dựng khung ví với ethers và kết nối MetaMask thử nghiệm. \[Q\] Chốt thư viện định nghĩa kiểu EIP-712 dùng chung. | Contract biên dịch được, test happy path đầu tiên đạt; môi trường chạy lại bằng một lệnh; mọi endpoint hiện có yêu cầu token và kiểm quyền (test A-01 đến A-04 đạt). |
| **2** | \[C\] Khiếu nại, `resolveDispute`, `arbitratorForceResolve`, `depositEscrowBatch`, pull-payment, hàm quản trị; hoàn thiện bộ test (mục 12), xuất ABI. \[B\] Thiết kế và viết migration CSDL (mục 9). \[Q\] Test chéo ngôn ngữ cho băm EIP-712. | **M1:** test contract đạt toàn bộ, độ phủ dòng lệnh từ 90%; đóng băng giao diện hàm (chỉ sửa lỗi sau tuần này). |
| **3** | \[B\] Liên kết ví (UC-00), tạo đơn và phát hành báo giá (UC-01), cấu hình tham số và chính sách nhóm hàng (`category_policies`); khung Indexer. \[F\] Màn hình liên kết ví. | Liên kết ví và nhận báo giá đúng chuẩn; contract chấp nhận báo giá do Backend ký. |
| **4** | \[B\] Indexer hoàn chỉnh: idempotent, con trỏ block, đối chiếu `OrderCreated`. \[F\] Thanh toán Web3 (approve + deposit), hiển thị trạng thái đơn qua polling. \[Q\] Kịch bản kiểm thử end-to-end đầu tiên. | **M2 - lát cắt end-to-end thô:** liên kết ví → đặt hàng → ký quỹ → indexer → trạng thái `LOCKED` trên giao diện. Nếu chậm, các tuần sau giảm phạm vi thay vì dời cột mốc. |
| **5** | \[B\] Cổng Shipper và relayer (UC-03), tác vụ nền (quét báo giá hết hạn, nhắc hạn), script đối soát. \[F\] Màn hình Shipper, Buyer: đồng hồ kiểm tra, "Đã nhận hàng". \[Q\] Test tích hợp luồng giải ngân. | Luồng thành công (giao hàng, mở khóa sớm, hết hạn kiểm tra) chạy trọn vẹn; đối soát số dư khớp. |
| **6** | \[B\] API đề xuất phán quyết, lưu và xác minh chữ ký, nộp `resolveDispute` (UC-06). \[F\] Màn hình Admin xử lý khiếu nại; Buyer và Merchant ký EIP-712. | Luồng tranh chấp có 2 chữ ký chạy trọn vẹn cả hai hướng (hoàn tiền, giải ngân). |
| **7** | \[F\] Màn hình Merchant, rút khoản chờ rút, nút hủy khi quá hạn, xử lý lỗi và thông báo. \[B\] Timeout (UC-07), nhật ký và cảnh báo bất thường. \[Q\] Test các luồng lỗi và ca âm. | **M3:** đủ chức năng của 4 vai trò. |
| **8** | Đóng băng tính năng. Kiểm thử tích hợp toàn bộ, sửa lỗi. Giao diện ETH và các cải tiến chỉ làm nếu **đã đạt M3 và còn thời gian**. \[Q\] Rà soát bảo mật theo checklist (reentrancy, replay, phân quyền, khóa). | **M4:** không còn lỗi mức cao/nghiêm trọng; AC-01 đến AC-11 được rà soát. |
| **9** | Chỉ kiểm thử, sửa lỗi, tài liệu: hướng dẫn cài đặt, hướng dẫn vận hành, kịch bản demo; chạy thử toàn bộ 3 lần liên tiếp. | Tài liệu hoàn chỉnh; demo ổn định trên máy của ít nhất hai thành viên. |
| **10** | Chuẩn bị slide, tập dượt bảo vệ, quay sẵn video demo dự phòng, trả lời các câu hỏi dự kiến (mô hình tin cậy, vì sao cần sàn làm Trọng tài, quy đổi tiền, giới hạn pháp lý). | **M5:** sẵn sàng bảo vệ. |
