# 📊 BẢNG THEO DÕI TIẾN ĐỘ THỰC THI DỰ ÁN (PROGRESS.md)
> **Đề tài:** Tự động hóa giao dịch TMĐT bằng Hợp đồng thông minh và Ký số không lưu khóa (Slopee Web3 Escrow MVP)  
> **Trạng thái tài liệu đặc tả:** 🔒 **ĐÃ ĐÓNG BĂNG (FROZEN)**  
> **Căn cứ tham chiếu bất biến:**  
> - `BRD-SLOPEE-MVP-01 v5.3` (Quy tắc nghiệp vụ & Tiêu chí nghiệm thu)  
> - `SRS-SLOPEE-MVP-01 v5.3` (Yêu cầu kỹ thuật, Ca sử dụng, Bảng CSDL, Lộ trình)  
> - `SDD-SLOPEE-MVP-01 v1.2` (Kiến trúc Hexagonal, Cổng/Adapter, Thiết kế chi tiết)  
>
> *Mọi cập nhật tiến độ, trạng thái công việc, kết quả test và nhật ký PR chỉ thực hiện tại file này mà không chỉnh sửa 3 tài liệu đặc tả trên.*

---

## 1. THÔNG TIN CHUNG & MA TRẬN NHÂN SỰ

- **Thời gian kế hoạch:** 10 tuần
- **Môi trường chuỗi:** Anvil EVM (Chain ID: 31337, `--block-time 2`)
- **Đơn vị tiền tệ nền tảng:** VND số nguyên (`DECIMAL(15,0)`) | Token ký quỹ: `MockUSD` (6 decimals)
- **Quy tắc phối hợp:** Họp ngắn 2 lần/tuần; Mọi PR phải có ít nhất 1 thành viên khác duyệt (Code Review); Test xanh 100% trước khi merge.

### Phân công trách nhiệm và dự phòng chéo
| Thành viên | Trách nhiệm chính | Trách nhiệm dự phòng / Hỗ trợ chéo | Mốc chuyển giao nội bộ |
| :--- | :--- | :--- | :--- |
| **Thành viên A** | **[C]** Toàn bộ Smart Contract & Security<br>**[Q]** Contract Unit/Fuzz/Invariant Tests, Slither | Hỗ trợ **B**: Relayer, thư viện EIP-712, P0-03..P0-06 (sau M1)<br>Hỗ trợ **C**: Giao diện Shipper & Admin (từ Tuần 5) | Sau cuối Tuần 2 (M1) hoàn tất contract, bàn giao ABI và chuyển sang Backend & UI |
| **Thành viên B** | **[B]** Flask Core, Web3 Module, Event Indexer, Jobs<br>**[Q]** API Tests, Indexer Tests, Reconcile Scripts | Hỗ trợ **A**: Contract verification, Ký số<br>Điểm nghẽn từ tuần 3–6, được ưu tiên bảo vệ nguồn lực | Bàn giao Mock API tuần 1–3 cho C; xong Indexer & Quotes ở M2 (Tuần 4) |
| **Thành viên C** | **[F]** React 19 Frontend, Vite, ethers.js v6, Hooks<br>**[Q]** E2E Test (Playwright), UI Tests, Docs, Demo | Hỗ trợ **B**: API đơn giản, Viết tài liệu kiểm thử | Tuần 1–3 dựng giao diện trên Mock API; Tuần 4 tích hợp API thật |

---

## 2. BẢNG ĐIỀU KHIỂN CỘT MỐC CHÍNH (MILESTONE DASHBOARD)

| Mốc | Thời hạn | Mục tiêu bàn giao có thể kiểm chứng | Trạng thái | Ngày hoàn thành | Người nghiệm thu |
| :---: | :---: | :--- | :---: | :---: | :---: |
| **M1** | Cuối Tuần 2 | Smart Contract hoàn chỉnh, test suite Foundry xanh 100%, coverage ≥ 90%, export ABI chuẩn | `[ ] CHƯA ĐẠT` | YYYY-MM-DD | A (Dev), B (Review) |
| **M2** | Cuối Tuần 4 | Lát cắt E2E thô: Liên kết ví ➔ Báo giá ➔ Ký quỹ gom ➔ Indexer ➔ UI hiện `LOCKED` | `[ ] CHƯA ĐẠT` | YYYY-MM-DD | Cả nhóm |
| **M3** | Cuối Tuần 7 | Đủ 4 vai trò (Buyer, Merchant, Shipper, Admin), luồng tranh chấp 2/3 chữ ký EIP-712 & timeout | `[ ] CHƯA ĐẠT` | YYYY-MM-DD | Cả nhóm |
| **M4** | Cuối Tuần 8 | Đóng băng tính năng; Toàn bộ bài test tích hợp và E2E xanh; Rà soát checklist an ninh | `[ ] CHƯA ĐẠT` | YYYY-MM-DD | Cả nhóm |
| **M5** | Cuối Tuần 10 | Nghiệm thu toàn diện: Chạy demo lặp lại 3 lần liên tiếp không lỗi, video backup, sẵn sàng bảo vệ | `[ ] CHƯA ĐẠT` | YYYY-MM-DD | Hội đồng |

---

## 3. TIẾN ĐỘ GIAI ĐOẠN 0 (PHASE 0: NỀN TẢNG & SỬA LỖI BẢO MẬT SLOPEE)
> *Bắt buộc hoàn thành P0-01 và P0-02 trước Tuần 3 (khi làm UC-00 liên kết ví).*

| Mã việc | Mô tả kỹ thuật | Khắc phục lỗi | Phụ trách | Tình trạng | PR / Commit |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **P0-01** | Lớp xác thực token ký (`itsdangerous`, `SECRET_KEY` từ env, `AUTH_TOKEN_TTL_SECONDS`), decorator `require_auth`, loại bỏ `userId` từ body/URL, lưu token tại `sessionStorage` | S-01, S-12 | **B** | `[~] Đã code, chờ review` | `#PR-` |
| **P0-02** | Đăng ký chỉ cho phép role `user` / `seller`; Khóa `admin_bp`; Bỏ route cấp số dư giả lập vô hạn; Seed tài khoản admin bằng CLI | S-02, S-03, S-04, S-10 | **B** | `[~] Đã code, chờ review` | `#PR-` |
| **P0-03** | Kiểm tra quyền sở hữu tài nguyên (đơn hàng, giỏ hàng, shop, sản phẩm, payment method); Chặn ghi đè `orders.status` đối với đơn Web3 (`WEB3_ORDER_MANAGED`) | S-05, S-06, S-11 | **A** | `[ ] Sẵn sàng` | `#PR-` |
| **P0-04** | Xóa bỏ endpoint `GET /api/shops/migrate`; Viết runner migration tự động đánh số qua bảng `schema_migrations`; Dọn schema trùng `reviews` / `reviewImages` (sửa lỗi MySQL strict 1364) | S-07, S-13 | **A** | `[ ] Sẵn sàng` | `#PR-` |
| **P0-05** | Thanh toán an toàn: Lock dòng bằng `SELECT ... FOR UPDATE`, `UPDATE ... WHERE inStock >= qty`; Xóa bỏ tính tiền bằng `float`; Khóa tạm tài khoản sau 5 lần sai mã PIN/mật khẩu | S-08, S-09 | **A** | `[ ] Sẵn sàng` | `#PR-` |
| **P0-06** | Tắt `debug=True` trên production; Chuẩn hóa trả về lỗi chung cho client, chi tiết ghi log máy chủ; Validate schema body JSON | S-10, S-14 | **A** | `[ ] Sẵn sàng` | `#PR-` |
| **P0-07** | Chuyển toàn bộ Slopee sang VND: 4 cột tiền đổi sang `DECIMAL(15,0)`; Đổi frontend dùng chung `formatVND` (`Intl.NumberFormat('vi-VN')`), xóa sạch biểu tượng `$` | Q-09, DD-12 | **B + C** | `[~] Đã code, chờ review` | `#PR-` |
| **P0-08** | Cập nhật bộ test cũ: Sửa test checkout, cart, auth theo token phiên và VND; Chuyển test race condition sang chạy trên MySQL service thật | SRS 12.3 | **B + C** | `[~] Đã code, chờ review` | `#PR-` |

**Ghi chú Phase 0 (cập nhật gần nhất):**
- `[~]` = đã code và test xanh cục bộ, **chờ PR được thành viên khác duyệt**; điền cột PR/Commit khi mở PR.
- **P0-01/02:** token mặc định hết hạn sau 3600 s (đặt `AUTH_TOKEN_TTL_SECONDS`; SDD 16.3 gợi ý 8 giờ → nhóm chốt giá trị). Token mang `role` và không kiểm lại DB. Route theo người dùng đã đổi sang `/me` hoặc bỏ tham số (xem `AI_CONTEXT.md` mục 6). Số dư phương thức thanh toán mới = 0.
- **P0-07:** `migrations/0001_money_to_vnd.sql` mới chạy tay và chỉ làm tròn dữ liệu USD cũ (SDD 16.3 bước 8 yêu cầu nhân với `FX_VND_PER_TOKEN`); DB demo nên tạo lại bằng `init_db.py`. P0-04 cần đưa file này vào runner.
- **P0-08:** test race condition checkout đã chạy trên MySQL thật (`test/integration_test/test_checkout_race_mysql.py`) và CI có MySQL service (`.github/workflows/tests.yml`). Hiện chỉ yêu cầu "không bán lố, tiền khớp"; sau P0-05 request thua cuộc nên trả 400 thay vì 500.
- **Còn hở cho A (P0-03…06):** kiểm tra chủ sở hữu cho sản phẩm/ảnh/biến thể/cart item/đơn; `GET /api/shops/migrate` còn công khai; `debug=True` và `str(e)` còn trả cho client; chưa có giới hạn thử sai PIN/mật khẩu; chưa dùng `FOR UPDATE`.

---

## 4. BẢNG THEO DÕI CHI TIẾT THEO TUẦN (WEEKLY SPRINT TRACKER)

### TUẦN 1: Khởi động nền tảng, Smart Contract cơ sở, Chuẩn hóa VND
- [ ] **[C] Thành viên A:** Cấu hình Foundry (`foundry.toml`, solc 0.8.20, `via_ir=true`, OpenZeppelin v5.0.2).
- [ ] **[C] Thành viên A:** Cài đặt contract `MockUSD.sol` (6 decimals, hàm `mint` phục vụ test).
- [ ] **[C] Thành viên A:** Cài đặt `SlopeeEscrowMaster.sol` phần nạp đơn: `depositEscrow` (kèm xác minh EIP-712 `Quote`), `confirmDelivery`, `earlyRelease`, `cancelIfUnfulfilled`.
- [ ] **[B] Thành viên B:** Viết script khởi tạo môi trường một lệnh `./scripts/bootstrap.sh` (chạy Anvil `--block-time 2`, deploy, xuất JSON).
- [~] **[B] Thành viên B:** Triển khai **P0-01** (Auth Token) và **P0-02** (Phân quyền Role & bảo vệ Admin). *(đã code, chờ review)*
- [~] **[B + C]:** Triển khai **P0-07** (Chuyển schema và giao diện sang VND số nguyên). *(đã code, chờ review)*
- [ ] **[F] Thành viên C:** Thiết lập Client API dùng chung (`lib/client.js`), Route Guard (`components/RequireRole.jsx`), hàm định dạng `formatVND`. *(một phần: `api/http.js` và `utils/formatVND.js` đã có; còn `RequireRole.jsx`; xác nhận tên file so với SDD `lib/client.js`/`lib/format.js`)*
- [ ] **[F] Thành viên C:** Khung kết nối ví MetaMask (`hooks/useWallet.js`), đọc thông tin chain từ `deployments/local.json`.
- [ ] **[Q] Cả nhóm:** Khóa file `shared/eip712/types.json` và tạo vector test chéo ngôn ngữ `shared/eip712/vectors.json`.

---

### TUẦN 2: Hoàn thiện Smart Contract, Nạp gom & Đạt Cột mốc M1
- [ ] **[C] Thành viên A:** Cài đặt logic tranh chấp: `raiseDispute`, `resolveDispute` (2/3 chữ ký EIP-712, kiểm tra `deadline < disputedAt + disputeTimeout`).
- [ ] **[C] Thành viên A:** Cài đặt cơ chế thoát hiểm timeout: `arbitratorForceResolve` (chỉ chạy khi `now >= disputedAt + disputeTimeout`).
- [ ] **[C] Thành viên A:** Cài đặt nạp gom nhiều shop: `depositEscrowBatch` (nguyên tử, tối đa 5 đơn, tái sử dụng `_acceptQuote` và `_collect`).
- [ ] **[C] Thành viên A:** Cài đặt sổ chờ rút pull-payment (`pendingWithdrawals`, `claimPending`, sự kiện `PayoutDeferred`).
- [ ] **[C] Thành viên A:** Viết bộ test Foundry T-01 đến T-34, chứng minh bất biến INV-01 đến INV-07. Đo gas nạp gom 5 shop (T-32).
- [ ] **[B] Thành viên B:** Viết các migration CSDL MySQL Web3 (`001_wallets.sql` đến `015_shipper.sql`), bảng `order_web3` quan hệ 1-1 với `orders`.
- [ ] **[Q] Thành viên B + C:** Chạy test chéo ngôn ngữ Python, JavaScript và Solidity khớp 100% digest EIP-712.
- [ ] 🎯 **NGHIỆM THU CỘT MỐC M1:**
  - [ ] Độ phủ dòng lệnh contract đạt ≥ 90% (`forge coverage`).
  - [ ] Chạy Slither không còn cảnh báo mức High chưa giải thích.
  - [ ] Đóng băng ABI `SlopeeEscrowMaster.json`, xuất sang backend và frontend.

---

### TUẦN 3: Liên kết ví, Tạo đơn, Báo giá có chữ ký (Backend Core)
- [ ] **[A ➔ B] Thành viên A:** Hỗ trợ Thành viên B hoàn thiện Giai đoạn 0 (P0-03 đến P0-06).
- [ ] **[B] Thành viên B:** Cài đặt UC-00: API Nonce dùng một lần `POST /api/wallet/nonce` và Liên kết ví `POST /api/wallet/link` (mẫu SIWE).
- [ ] **[B] Thành viên B:** Cài đặt UC-01: API tạo đơn Web3 `POST /api/orders` (nhóm theo shop, cấp `onchain_order_id`, quy đổi VND ➔ token, tính `docHash`, tra nhóm chính sách `category_policies`, ký `OrderQuote` EIP-712 bằng `QUOTE_SIGNER_KEY`).
- [ ] **[B] Thành viên B:** Cài đặt API cấp lại báo giá cho cả lô `POST /api/checkout-groups/:id/quote`.
- [ ] **[B] Thành viên B:** Khung xương tiến trình Indexer (`web3_chain.py`, đọc block Anvil, cơ chế `GET_LOCK`).
- [ ] **[F] Thành viên C:** Màn hình kết nối & liên kết ví (`pages/Wallet.jsx`, ký `personal_sign` không tốn gas).
- [ ] **[F] Thành viên C:** Dựng khung màn hình thanh toán Web3 (`pages/Checkout.jsx`) kết nối API mock.

---

### TUẦN 4: Event Indexer, Tích hợp Ký quỹ & Đạt Cột mốc M2
- [ ] **[B] Thành viên B:** Hoàn thiện Indexer: Lắng nghe sự kiện `OrderCreated`, kiểm tra tính toán vẹn đối soát với báo giá đã lưu, cập nhật `order_web3.status = LOCKED` và đồng bộ `orders.status = paid` trong cùng giao dịch.
- [ ] **[B] Thành viên B:** Indexer xóa `cartItems` của đơn hàng sau khi sự kiện `OrderCreated` được ghi nhận.
- [ ] **[B] Thành viên B:** Cơ chế con trỏ block `indexer_cursor`, bảo vệ reorg, API polling trạng thái `GET /api/orders/:code/status`.
- [ ] **[F] Thành viên C:** Tích hợp giao diện Checkout với hợp đồng thật: Luồng 2 bước MetaMask (Bước 1: `approve` tổng; Bước 2: `depositEscrowBatch`).
- [ ] **[F] Thành viên C:** Hook `usePolling.js` để tự động chuyển màn hình khi đơn chuyển sang `LOCKED`.
- [ ] 🎯 **NGHIỆM THU CỘT MỐC M2 (Lát cắt End-to-End thô):**
  - [ ] Luồng test: Đăng nhập ➔ Liên kết ví ➔ Đặt giỏ 2 shop ➔ Ký quỹ qua MetaMask ➔ Indexer bắt log ➔ DB chuyển `LOCKED` ➔ Frontend hoàn tất thành công.

---

### TUẦN 5: Cổng Shipper, Relayer & Luồng Giải ngân tự động
- [ ] **[B] Thành viên B:** Cổng Shipper: API `GET /api/shipper/orders` và `POST /api/shipper/orders/:code/deliver`.
- [ ] **[A ➔ B] Thành viên A:** Cài đặt Relayer gửi giao dịch `confirmDelivery` lên Anvil bằng khóa `SHIPPER_KEY` qua hàng đợi một luồng (`tx_outbox`).
- [ ] **[B] Thành viên B:** Tác vụ nền (Scheduler): Quét báo giá quá hạn (`QuoteExpirySweeper`), Quét tự động giải ngân khi hết thời hạn kiểm tra (`AutoRelease`).
- [ ] **[A ➔ F] Thành viên A:** Xây dựng màn hình cổng Shipper (`pages/ShipperOrders.jsx`).
- [ ] **[F] Thành viên C:** Cập nhật màn hình Buyer (`pages/MyOrders.jsx`): Hiển thị đồng hồ đếm ngược kiểm tra (`CountdownTimer`), nút "Đã nhận hàng" (`earlyRelease`), nút "Khiếu nại".
- [ ] **[Q] Thành viên C:** Chạy kịch bản tích hợp luồng Happy Path (I-05, E-01).

---

### TUẦN 6: Luồng Tranh chấp & Phân xử 2/3 Chữ ký EIP-712
- [ ] **[B] Thành viên B:** API lưu ghi chú khiếu nại `POST /api/orders/:code/dispute-note`.
- [ ] **[B] Thành viên B:** API Admin tạo đề xuất phán quyết `POST /api/admin/disputes/:code/proposal`, tự động ký phiếu Arbitrator bằng `ARBITRATOR_KEY` với `deadline < disputedAt + disputeTimeout`.
- [ ] **[B] Thành viên B:** API tiếp nhận chữ ký của Buyer / Merchant `POST /api/disputes/:code/signatures`.
- [ ] **[A ➔ B] Thành viên A:** Relayer hỗ trợ nộp giao dịch `resolveDispute` khi đủ 2/3 chữ ký (`POST /api/disputes/:code/submit`).
- [ ] **[A ➔ F] Thành viên A:** Xây dựng màn hình Admin quản lý tranh chấp (`pages/AdminDashboard.jsx`).
- [ ] **[F] Thành viên C:** Xây dựng giao diện ký phán quyết (`pages/Dispute.jsx`): Khung cảnh báo màu vàng, ký `eth_signTypedData_v4` không tốn gas.
- [ ] **[Q] Thành viên C:** Kiểm thử tích hợp kịch bản giải quyết tranh chấp (Hoàn tiền Buyer và Giải ngân Merchant) (E-03).

---

### TUẦN 7: Hoàn thiện 4 Vai trò, Thoát hiểm Timeout & Đạt Cột mốc M3
- [ ] **[A ➔ F] Thành viên A:** Xây dựng màn hình Merchant (`pages/SellerDashboard.jsx`): Danh sách đơn Web3, Rút số dư chờ (`claimPending`).
- [ ] **[F] Thành viên C:** Bổ sung nút "Hủy đơn do quá hạn giao hàng 14 ngày" (`cancelIfUnfulfilled`) trên giao diện Buyer.
- [ ] **[B] Thành viên B:** API kích hoạt thoát hiểm Trọng tài xử đơn phương `arbitratorForceResolve` khi quá `disputeTimeout`.
- [ ] **[B] Thành viên B:** Viết script đối soát tự động `reconcile.py` (so khớp số dư contract và CSDL) (AC-10).
- [ ] **[Q] Cả nhóm:** Kiểm thử toàn diện các luồng timeout (E-04) bằng cách tua thời gian Anvil (`evm_increaseTime`).
- [ ] 🎯 **NGHIỆM THU CỘT MỐC M3:**
  - [ ] Toàn bộ 4 vai trò (Buyer, Merchant, Shipper, Admin) thao tác hoàn chỉnh trên UI.
  - [ ] Không có trường hợp tiền bị kẹt vĩnh viễn trong hợp đồng.

---

### TUẦN 8: Đóng băng tính năng, Kiểm thử tích hợp & Đạt Cột mốc M4
- [ ] 🔒 **ĐÓNG BĂNG MÃ NGUỒN TÍNH NĂNG (FEATURE FREEZE):** Tuyệt đối không thêm tính năng mới, chỉ sửa lỗi.
- [ ] **[Q] Thành viên C:** Thiết lập Playwright test tự động với mock ví EIP-1193 chạy trong GitHub Actions CI (E-01 đến E-07).
- [ ] **[Q] Thành viên B:** Chạy toàn bộ test suite backend và API (A-01 đến A-07, I-01 đến I-07).
- [ ] **[Q] Thành viên A:** Quét mã nguồn và CSDL xác nhận nguyên tắc Non-custodial (E-05, AC-09): Không tồn tại private key người dùng.
- [ ] **[Q] Thành viên A:** Rà soát lại checklist an ninh: Reentrancy, Signature Malleability, Role Separation, Front-running.
- [ ] 🎯 **NGHIỆM THU CỘT MỐC M4:**
  - [ ] Toàn bộ bài test trên CI xanh 100%. Không còn bug mức High/Critical.

---

### TUẦN 9: Kiểm thử tải, Diễn tập Demo & Hoàn thiện Tài liệu
- [ ] **[B] Thành viên B:** Chạy test Replay Indexer từ block 0 (`replay.sh`): Đảm bảo phục hồi 100% trạng thái dữ liệu (AC-08).
- [ ] **[C] Thành viên C:** Hoàn thiện Hướng dẫn cài đặt (`INSTALL.md`) và Hướng dẫn vận hành demo (`DEMO_GUIDE.md`).
- [ ] **[Cả nhóm]:** Chạy diễn tập kịch bản Demo trực tiếp trên 2 máy độc lập:
  - Luồng 1 (Happy path - Giỏ 2 shop, giao hàng, mở khóa sớm): Yêu cầu < 3 phút.
  - Luồng 2 (Dispute path - Khiếu nại, thương lượng 2 chữ ký, hoàn tiền): Yêu cầu < 5 phút.
  - Luồng 3 (Timeout path - Tua thời gian, Trọng tài xử lý đơn phương): Yêu cầu chạy mượt mà.
- [ ] **[Cả nhóm]:** Chạy lặp lại 3 lần liên tiếp toàn bộ kịch bản không phát sinh lỗi (AC-11).

---

### TUẦN 10: Quay Video Backup, Soạn Slide & Sẵn sàng Bảo vệ (M5)
- [ ] **[C] Thành viên C:** Quay video chất lượng cao toàn bộ các luồng demo (kèm thuyết minh) làm phương án dự phòng khi hội đồng mất mạng.
- [ ] **[A + B]:** Soạn slide báo cáo: Nhấn mạnh bài toán nghiệp vụ, cơ chế ký quỹ phân cấp, mô hình bảo mật EIP-712 và các kết quả KPI đạt được.
- [ ] **[Cả nhóm]:** Chuẩn bị bộ câu hỏi phản biện:
  - *Tại sao sàn vẫn giữ vai trò Trọng tài? (Mô hình tin cậy có kiểm soát, phân tích tại BRD mục 6)*
  - *Vấn đề pháp lý của MockUSD/VND tại Việt Nam? (Tham chiếu BRD mục 7)*
  - *Cơ chế chống thất thoát tài sản khi lộ khóa sàn? (Phí bị chặn bởi trần on-chain, chữ ký phân vai)*
- [ ] 🎯 **NGHIỆM THU CỘT MỐC M5:** Hoàn tất toàn bộ hồ sơ, sẵn sàng bảo vệ đồ án trước Hội đồng.

---

## 5. MA TRẬN THEO DÕI KIỂM THỬ (TEST EXECUTION TRACKER)

### 5.1. Smart Contract Test Suite (Foundry: `test/*.t.sol`)
| Mã test | Mô tả ca kiểm thử | Kết quả mong đợi | BRD / SRS | Tình trạng |
| :---: | :--- | :--- | :---: | :---: |
| **T-01** | Nạp tiền với báo giá hợp lệ (ERC-20 và ETH) | Thành công, đơn `LOCKED` | BR-06 | `[ ] PASS` |
| **T-02** | Báo giá quá hạn; sai caller; chữ ký sai; signer thiếu role | Revert | BR-06 | `[ ] PASS` |
| **T-03** | Trùng `orderId`; ETH khác amount; nạp token gửi kèm ETH; thiếu allowance | Revert | BR-06 | `[ ] PASS` |
| **T-04** | Merchant trùng Buyer; Trọng tài làm Buyer/Merchant; duration ngoài [1h, 30d] | Revert | BR-03, 04 | `[ ] PASS` |
| **T-05** | `confirmDelivery` gọi bởi người không có role; gọi khi đơn chưa `LOCKED` | Revert | BR-03 | `[ ] PASS` |
| **T-06** | `earlyRelease` gọi bởi Buyer; gọi bởi người khác | Thành công / Revert | BR-03 | `[ ] PASS` |
| **T-07** | `releaseAfterInspection` tại đúng mốc biên và trước 1 giây | Thành công / Revert | BR-03 | `[ ] PASS` |
| **T-08** | Chia phí theo `feeBps` (0, 300, 1000); Kiểm tra làm tròn; Đổi `defaultFeeBps` không ảnh hưởng đơn cũ | Đúng công thức | BR-02 | `[ ] PASS` |
| **T-09** | `setDefaultFeeBps` > 1000; gọi bởi người không phải Admin | Revert | BR-02 | `[ ] PASS` |
| **T-10** | `raiseDispute` trong hạn; sau hạn; gọi bởi người không phải Buyer | Thành công / Revert | BR-03 | `[ ] PASS` |
| **T-11** | `resolveDispute` đủ 2/3 chữ ký (Arbitrator + Buyer; Arbitrator + Merchant) | Thành công, đúng payout | BR-04 | `[ ] PASS` |
| **T-12** | 2 chữ ký cùng bên; 2 địa chỉ cùng vai Trọng tài; chữ ký người lạ; quá hạn deadline; sai nonce | Revert | BR-04 | `[ ] PASS` |
| **T-13** | Nộp lại chữ ký đã dùng sau khi đơn đã đóng | Revert | BR-04 | `[ ] PASS` |
| **T-14** | `cancelIfUnfulfilled` trước và sau 14 ngày; bởi Buyer, Admin, người ngoài | Revert / OK / Revert | BR-05 | `[ ] PASS` |
| **T-15** | `arbitratorForceResolve` trước/sau `disputeTimeout`; biên -1s revert, đúng mốc thành công | Revert / OK / Revert | BR-05 | `[ ] PASS` |
| **T-16** | Ví nhận từ chối ETH: Chuyển vào `pendingWithdrawals`; `claimPending` rút thành công | Thành công, không kẹt | BR-05 | `[ ] PASS` |
| **T-17** | Tấn công Reentrancy qua fallback ví nhận ETH và token độc hại | Bị ReentrancyGuard chặn | Bảo mật | `[ ] PASS` |
| **T-18** | Invariant/Fuzz: Số dư contract = Tổng đơn mở + Tổng sổ chờ rút | Luôn đúng | G-01 | `[ ] PASS` |
| **T-19** | Kiểm tra ma trận âm: Mọi cặp (state, method) không hợp lệ trong SRS mục 5 | Revert | Máy trạng thái | `[ ] PASS` |
| **T-20** | Báo giá có `disputeTimeout` < 7 ngày hoặc > 90 ngày; biên đúng 7 và 90 ngày | Revert / OK | BR-10 | `[ ] PASS` |
| **T-21** | Hai đơn có `disputeTimeout` khác nhau chạy song song: độc lập thời gian timeout | Thành công độc lập | BR-10 | `[ ] PASS` |
| **T-22** | Báo giá có `feeBps > defaultFeeBps`; hạ trần thì báo giá cũ bị từ chối | Revert / OK | BR-02, 06 | `[ ] PASS` |
| **T-23** | Báo giá có `q.buyer != msg.sender` | Revert | BR-06 | `[ ] PASS` |
| **T-24** | `resolveDispute` với `deadline >= disputedAt + disputeTimeout` | Revert | BR-04, 05 | `[ ] PASS` |
| **T-25** | Nạp gom 3 đơn 3 shop: 1 lần `transferFrom`, tăng số dư đúng tổng, 3 sự kiện `OrderCreated` | Thành công | BR-11 | `[ ] PASS` |
| **T-26** | Lô nạp rỗng; lô > 5 đơn; lệch độ dài mảng quotes và sigs | Revert | BR-11 | `[ ] PASS` |
| **T-27** | Trùng `orderId` ngay trong một mảng lô nạp | Revert, số dư không đổi | BR-11, G-01 | `[ ] PASS` |
| **T-28** | Một báo giá trong lô lỗi (quá hạn, sai chữ ký, vượt trần phí) | Toàn bộ lô Revert | BR-11 | `[ ] PASS` |
| **T-29** | Lô nạp trộn nhiều loại token; nạp ETH sai tổng `msg.value` | Revert | BR-11 | `[ ] PASS` |
| **T-30** | Mọi điều kiện đơn lẻ áp dụng chuẩn xác cho từng phần tử của lô | Revert nếu vi phạm | BR-06, 11 | `[ ] PASS` |
| **T-31** | Sau khi nạp gom: Đơn A early release, đơn B dispute hoàn tiền, đơn C tự giải ngân | Độc lập hoàn toàn | BR-11 | `[ ] PASS` |
| **T-32** | Đo gas nạp lô 5 đơn (mục tiêu < 3.000.000 gas) | Đạt ngưỡng gas | BR-11 | `[ ] PASS` |
| **T-33** | Fuzz invariant: Gọi ngẫu nhiên cả nạp đơn và nạp gom | INV-01..07 luôn đúng | G-01 | `[ ] PASS` |
| **T-34** | So sánh nạp đơn lẻ và nạp lô 1 phần tử: Trạng thái và event giống hệt nhau | Khớp 100% | BR-11 | `[ ] PASS` |

---

### 5.2. Integration, System & Backend API Test Suite
> `[~]` = test đã viết và pass cục bộ, chờ CI/PR; `[x] PASS` chỉ đặt sau khi CI xanh trên nhánh chính.

| Mã test | Phạm vi kiểm thử | Tiêu chuẩn đánh giá | Tình trạng |
| :---: | :--- | :--- | :---: |
| **I-01** | Liên kết ví: Nonce dùng lại, nonce hết hạn, chữ ký sai, ví đã thuộc user khác | AC-01 / Trả đúng mã lỗi HTTP | `[ ] PASS` |
| **I-02** | Báo giá: Quy đổi VND ➔ token chuẩn xác, hợp đồng chấp nhận chữ ký Python | AC-01, AC-02 | `[ ] PASS` |
| **I-03** | Indexer: Xử lý trùng tx_hash/log_index không ghi đôi, khởi động lại, phục hồi con trỏ | AC-08 / Tính Idempotent | `[ ] PASS` |
| **I-04** | Nhóm hàng: Đơn nhiều nhóm lấy `max()`, đổi chính sách không ảnh hưởng đơn cũ | AC-12 | `[ ] PASS` |
| **I-05** | Đồng bộ thời gian: `now_chain()` theo sát block Anvil; tua thời gian cấp quote mới chuẩn | AC-02 | `[ ] PASS` |
| **I-06** | Đồng bộ ngược: Cập nhật `order_web3` tự động cập nhật `orders.status` cũ; Chặn route ghi đè cũ | AC-08 / Bảng ánh xạ 5.1 | `[ ] PASS` |
| **I-07** | Giỏ 3 shop: Tạo đúng 3 đơn 1 group, tổng token khớp lệnh, Indexer xóa đúng giỏ hàng | AC-14 | `[ ] PASS` |
| **A-01** | Mọi API yêu cầu token: Không token hoặc token hết hạn trả HTTP 401 | Mục 15 (P0-01) | `[~] pass cục bộ` |
| **A-02** | Kiểm tra quyền Role: User/Seller gọi API Admin bị chặn HTTP 403; Shipper chỉ xem đơn gán | Mục 15 (P0-02) | `[~] pass cục bộ` |
| **A-03** | Kiểm tra sở hữu dữ liệu: Xem đơn, giỏ, shop của người khác bị 403 hoặc 404 | Mục 15 (P0-03) | `[ ] PASS` |
| **A-04** | Đăng ký tài khoản với role `admin` hoặc `shipper` bị từ chối | Mục 15 (P0-02) | `[~] pass cục bộ` |
| **A-05** | Đua tranh đặt hàng (Race condition): Tồn kho không bao giờ bị âm | Mục 15 (P0-05) | `[~] một phần (chặn nhờ CHECK, chưa FOR UPDATE)` |
| **A-06** | Giới hạn brute-force: Nhập sai PIN hoặc Password quá 5 lần bị khóa tạm | Mục 15 (P0-05) | `[ ] PASS` |
| **A-07** | Endpoint `/api/shops/migrate` đã bị xóa bỏ; Không còn API cấp số dư vô hạn | Mục 15 (P0-04) | `[ ] PASS` |

---

### 5.3. Frontend Logic & Unit Test Suite (Vitest)
| Mã test | Mô tả ca kiểm thử | Kết quả mong đợi | Tình trạng |
| :---: | :--- | :--- | :---: |
| **F-01** | Hàm định dạng `formatVND`: Kiểm tra số nguyên, làm tròn, số 0, số cực lớn, không còn ký hiệu `$` | Chuẩn định dạng tiếng Việt | `[~] pass cục bộ` |
| **F-02** | Reducer nạp tiền (`depositReducer`): Đủ allowance bỏ bước approve, từ chối ví (4001), hết hạn quote | Chuyển state chính xác | `[ ] PASS` |
| **F-03** | Ánh xạ lỗi tiếng Việt: `BATCH_TOO_LARGE`, `FEE_CAP_CHANGED`, `Invalid batch size` | Hiển thị thông báo dễ hiểu | `[ ] PASS` |
| **F-04** | Client API chung: Tự gắn `Authorization`, tự động xóa token và chuyển trang khi gặp 401 | Hoạt động thông suốt | `[ ] PASS` |
| **F-05** | Hook `usePolling`: Dừng khi rời màn hình, dừng khi đơn tới trạng thái cuối | Không memory leak / spam | `[ ] PASS` |
| **F-06** | Đồng hồ đếm ngược: Tính độ lệch dựa trên `server_time`, không lệch theo máy client | Đếm ngược chuẩn xác | `[ ] PASS` |

---

### 5.4. End-to-End Automated Test Suite (Playwright + Mock Provider)
| Mã test | Kịch bản luồng E2E | Tiêu chí nghiệm thu liên quan | Tình trạng |
| :---: | :--- | :---: | :---: |
| **E-01** | **Happy Path:** Đăng ký ➔ Liên kết ví ➔ Đặt hàng ➔ Ký quỹ gom ➔ Giao hàng ➔ Mở khóa sớm | AC-01, AC-03, AC-04 | `[ ] PASS` |
| **E-02** | **Inspection Expiry:** Giao hàng ➔ Tua thời gian Anvil ➔ Tự động giải ngân sau hạn | AC-04 | `[ ] PASS` |
| **E-03** | **Dispute Resolution:** Khiếu nại ➔ Đề xuất phán quyết ➔ Buyer/Merchant ký EIP-712 ➔ Hoàn tiền | AC-05, AC-06 | `[ ] PASS` |
| **E-04** | **Timeouts:** Delivery timeout (14 ngày hủy hoàn tiền); Dispute timeout (Trọng tài xử đơn phương) | AC-07 | `[ ] PASS` |
| **E-05** | **Zero-key Scan:** Quét tự động repo, CSDL, file log không tìm thấy private key người dùng | AC-09 (BR-01) | `[ ] PASS` |
| **E-06** | **Đối soát số dư:** Script kiểm tra số dư contract khớp 100% với đơn mở sau mỗi ca test E2E | AC-10 (G-01) | `[ ] PASS` |
| **E-07** | **Multi-shop Escrow:** Giỏ 3 shop, 2 lần xác nhận ví; Mỗi shop kết thúc độc lập | AC-14 (BR-11) | `[ ] PASS` |

---

## 6. MA TRẬN THEO DÕI TIÊU CHÍ NGHIỆM THU (ACCEPTANCE CRITERIA SIGN-OFF)

| Mã AC | Tóm tắt tiêu chí nghiệm thu | Ràng buộc nghiệp vụ | Kết quả kiểm chứng | Ký duyệt |
| :---: | :--- | :---: | :--- | :---: |
| **AC-01** | Đặt hàng, nhận báo giá, nạp tiền thành công; DB chuyển `LOCKED` trong vòng 10 giây | BR-06, 07, 09 | Test I-01, E-01 đạt | `[ ]` |
| **AC-02** | Báo giá sai (sai người nạp, sai tiền, hết hạn, trùng đơn) đều bị contract từ chối | BR-06 | Test T-02, T-03 đạt | `[ ]` |
| **AC-03** | Chỉ tài khoản có `SHIPPER_ROLE` được xác nhận giao hàng; người khác bị revert | BR-03 | Test T-05 đạt | `[ ]` |
| **AC-04** | Giải ngân chia đúng phí theo `feeBps` trong báo giá; Đổi phí sau đó không ảnh hưởng | BR-02, 03 | Test T-08, E-01 đạt | `[ ]` |
| **AC-05** | Khiếu nại trong hạn đóng băng tiền; Quá thời hạn kiểm tra khiếu nại bị từ chối | BR-03 | Test T-10 đạt | `[ ]` |
| **AC-06** | Phân xử thành công với 2 chữ ký của 2 bên khác nhau; Chặn chữ ký trùng hoặc sai hạn | BR-04, 05 | Test T-11, T-12, T-24 đạt | `[ ]` |
| **AC-07** | Delivery Timeout và Dispute Timeout hoạt động chuẩn xác theo từng giá trị cấu hình | BR-05 | Test T-14, T-15, E-04 đạt | `[ ]` |
| **AC-08** | Xóa CSDL chạy lại Indexer từ block 0 khớp 100% dữ liệu on-chain; Xử lý trùng an toàn | BR-09 | Test I-03, I-06, Replay script đạt | `[ ]` |
| **AC-09** | Quét toàn diện mã nguồn, CSDL, log không có private key hay seed phrase người dùng | BR-01 | Test E-05 đạt | `[ ]` |
| **AC-10** | Số dư contract luôn bằng tổng tiền các đơn đang mở cộng sổ chờ rút | G-01 | Test T-18, E-06, Reconcile tool đạt | `[ ]` |
| **AC-11** | Bộ test contract đạt coverage ≥ 90%; Chạy lặp lại kịch bản demo 3 lần liên tiếp không lỗi | G-06 | Báo cáo test & biên bản demo | `[ ]` |
| **AC-12** | Nhóm hàng nhận đúng thời hạn kiểm tra và tranh chấp; Biên 7–90 ngày do contract ép | BR-05, BR-10 | Test T-20, T-21, I-04 đạt | `[ ]` |
| **AC-13** | Báo giá có phí vượt trần on-chain bị từ chối; Hạ trần phí buộc lấy báo giá mới | BR-02, BR-06 | Test T-22, T-23 đạt | `[ ]` |
| **AC-14** | Giỏ nhiều shop thanh toán gom 2 lần ký ví; Hoạt động độc lập sau nạp; Nguyên tử | BR-11, BR-06 | Test T-25..34, I-07, E-07 đạt | `[ ]` |

---

## 7. QUẢN LÝ RỦI RO & PHƯƠNG ÁN CẮT GIẢM PHẠM VI (SCOPE CONTINGENCY)

Nếu tiến độ bị trễ so với các cột mốc quy định, nhóm sẽ kích hoạt quy tắc cắt giảm phạm vi theo thứ tự ưu tiên dưới đây nhằm bảo toàn tiến độ bảo vệ:

| Thứ tự cắt | Hạng mục cắt giảm | Điều kiện kích hoạt | Nguồn |
| :---: | :--- | :--- | :---: |
| 1 | Giao diện rút khoản chờ rút (`claimPending`) và màn hình Merchant nâng cao | Trễ M2 quá 3 ngày | BRD mục 9 |
| 2 | Giao diện thanh toán bằng ETH (contract và test vẫn giữ) | Còn là hạng mục "nếu còn thời gian" | BRD mục 2 |
| 3 *(đề xuất, cần nhóm xác nhận)* | Màn hình Admin ánh xạ danh mục ➔ nhóm chính sách (seed bằng SQL) | Trễ M3 | - |
| 4 *(đề xuất, cần nhóm xác nhận)* | Thu hẹp E2E tự động còn E-01, E-03; các ca còn lại chạy thủ công có biên bản | Trễ M4 | - |

**Không được cắt:** luồng chính (liên kết ví ➔ báo giá ➔ ký quỹ ➔ giao hàng ➔ giải ngân/tranh chấp), **P0-01 và P0-02** (SDD 16.4), test contract T-01…T-34 và đối soát số dư (AC-10). Tuần 9–10 chỉ kiểm thử, sửa lỗi và demo; không thêm tính năng (BRD mục 9).
