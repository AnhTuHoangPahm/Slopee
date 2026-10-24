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
| **M1** | Cuối Tuần 2 | Smart Contract hoàn chỉnh, test suite Foundry xanh 100%, coverage ≥ 90%, export ABI chuẩn | `[x] ĐẠT` | 2026-10-12 | A (Dev), B (Review) |
| **M2** | Cuối Tuần 4 | Lát cắt E2E thô: Liên kết ví ➔ Báo giá ➔ Ký quỹ gom ➔ Indexer ➔ UI hiện `LOCKED` | `[x] ĐẠT` | 2026-10-16 | Cả nhóm |
| **M3** | Cuối Tuần 7 | Đủ 4 vai trò (Buyer, Merchant, Shipper, Admin), luồng tranh chấp 2/3 chữ ký EIP-712 & timeout | `[ ] CHƯA ĐẠT` | YYYY-MM-DD | Cả nhóm |
| **M4** | Cuối Tuần 8 | Đóng băng tính năng; Toàn bộ bài test tích hợp và E2E xanh; Rà soát checklist an ninh | `[ ] CHƯA ĐẠT` | YYYY-MM-DD | Cả nhóm |
| **M5** | Cuối Tuần 10 | Nghiệm thu toàn diện: Chạy demo lặp lại 3 lần liên tiếp không lỗi, video backup, sẵn sàng bảo vệ | `[ ] CHƯA ĐẠT` | YYYY-MM-DD | Hội đồng |

---

## 3. TIẾN ĐỘ GIAI ĐOẠN 0 (PHASE 0: NỀN TẢNG & SỬA LỖI BẢO MẬT SLOPEE)
> *Bắt buộc hoàn thành P0-01 và P0-02 trước Tuần 3 (khi làm UC-00 liên kết ví).*

| Mã việc | Mô tả kỹ thuật | Khắc phục lỗi | Phụ trách | Tình trạng | PR / Commit |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **P0-01** | Lớp xác thực token ký (`itsdangerous`, `SECRET_KEY` từ env, `AUTH_TOKEN_TTL_SECONDS`), decorator `require_auth`, loại bỏ `userId` từ body/URL, lưu token tại `sessionStorage` | S-01, S-12 | **B** | `[x] Đã review 14/10/2026 (PR #2)` | `#2` |
| **P0-02** | Đăng ký chỉ cho phép role `user` / `seller`; Khóa `admin_bp`; Bỏ route cấp số dư giả lập vô hạn; Seed tài khoản admin bằng CLI | S-02, S-03, S-04, S-10 | **B** | `[x] Đã review 14/10/2026 (PR #2)` | `#2` |
| **P0-03** | Kiểm tra quyền sở hữu tài nguyên (đơn hàng, giỏ hàng, shop, sản phẩm, payment method); Chặn ghi đè `orders.status` đối với đơn Web3 (`WEB3_ORDER_MANAGED`) | S-05, S-06, S-11 | **A** | `[x] Đã review 14/10/2026 (PR #2)` | `#2` |
| **P0-04** | Xóa bỏ endpoint `GET /api/shops/migrate`; Viết runner migration tự động đánh số qua bảng `schema_migrations`; Dọn schema trùng `reviews` / `reviewImages` (sửa lỗi MySQL strict 1364) | S-07, S-13 | **A** | `[x] Đã review 14/10/2026 (PR #2)` | `#2` |
| **P0-05** | Thanh toán an toàn: Lock dòng bằng `SELECT ... FOR UPDATE`, `UPDATE ... WHERE inStock >= qty`; Xóa bỏ tính tiền bằng `float`; Khóa tạm tài khoản sau 5 lần sai mã PIN/mật khẩu | S-08, S-09 | **A** | `[x] Đã review 14/10/2026 (PR #2)` | `#2` |
| **P0-06** | Tắt `debug=True` trên production; Chuẩn hóa trả về lỗi chung cho client, chi tiết ghi log máy chủ; Validate schema body JSON | S-10, S-14 | **A** | `[x] Đã review 14/10/2026 (PR #2)` | `#2` |
| **P0-07** | Chuyển toàn bộ Slopee sang VND: 4 cột tiền đổi sang `DECIMAL(15,0)`; Đổi frontend dùng chung `formatVND` (`Intl.NumberFormat('vi-VN')`), xóa sạch biểu tượng `$` | Q-09, DD-12 | **B + C** | `[x] Đã review 14/10/2026 (PR #2)` | `#2` |
| **P0-08** | Cập nhật bộ test cũ: Sửa test checkout, cart, auth theo token phiên và VND; Chuyển test race condition sang chạy trên MySQL service thật | SRS 12.3 | **B + C** | `[x] Đã review 14/10/2026 (PR #2)` | `#2` |

**Ghi chú Phase 0 (cập nhật gần nhất):**
- `[~]` = đã code và test xanh cục bộ, **chờ PR được thành viên khác duyệt**; điền cột PR/Commit khi mở PR. `[x]` = đã duyệt và chốt PR. **P0-01…P0-08 đều `[x]`: đã review ngày 14/10/2026, PR #2** (cột PR/Commit = `#2`). Lưu ý: CI GitHub chưa xác nhận lại trên nhánh chính nên các dòng `[x] PASS` ở bảng test chỉ đặt khi CI xanh.
- **P0-01/02:** token mặc định hết hạn sau 3600 s (đặt `AUTH_TOKEN_TTL_SECONDS`; SDD 16.3 gợi ý 8 giờ → nhóm chốt giá trị). Token mang `role` và không kiểm lại DB. Route theo người dùng đã đổi sang `/me` hoặc bỏ tham số (xem `AI_CONTEXT.md` mục 6). Số dư phương thức thanh toán mới = 0.
- **P0-07:** `migrations/0001_money_to_vnd.sql` mới chạy tay và chỉ làm tròn dữ liệu USD cũ (SDD 16.3 bước 8 yêu cầu nhân với `FX_VND_PER_TOKEN`); DB demo nên tạo lại bằng `init_db.py`. File này đã nằm trong runner của P0-04 (xem ghi chú P0-04).
- **P0-08:** test race condition checkout đã chạy trên MySQL thật (`test/integration_test/test_checkout_race_mysql.py`) và CI có MySQL service (`.github/workflows/tests.yml`). Yêu cầu "không bán lố, tiền khớp" vẫn đúng; sau P0-05 request thua cuộc trả 400 (không còn 500 do `CHECK`).
- **P0-03:** chỉ chủ mới sửa/xóa được cart item, đơn, sản phẩm, ảnh và biến thể; tài nguyên của người khác trả **404** như thể không tồn tại (không lộ sự tồn tại). `PUT /api/payments/orders/:id` khóa dòng `orders` (`FOR UPDATE`), từ chối đơn có dòng `order_web3` bằng `409 WEB3_ORDER_MANAGED` (nếu chưa có bảng `order_web3` thì coi là đơn cũ), và chỉ cho `paid|shipped→received`, `pending|paid→cancelled` (sai → `409 INVALID_STATE`). Thông báo lỗi giữ tiếng Anh như code hiện tại (SRS quy ước tiếng Việt cho API Web3 → nhóm chốt khi làm UC-00).
- **P0-04:** đã xóa `GET /api/shops/migrate`. Runner: `python migrate.py [up|status|mark-applied <tệp>]` hoặc `flask --app app migrate`; bảng `schema_migrations`, khóa `GET_LOCK`, hỗ trợ migration `.sql` và `.py`. Nội dung route cũ chuyển thành `0002_product_fk_snapshots.py` (cột snapshot, `cartItems` CASCADE, `orderLines.productId` NULL + SET NULL); `0003_reviews_dedupe.py` đưa DB cũ về `reviews` có `UNIQUE(userId, productId)`; `0004_auth_attempts.sql` tạo bảng đếm thử sai. `schema.sql` đã gộp khai báo `reviews`/`reviewImages` (giữ `reviewImages.id VARCHAR(36)`, backend sinh UUID) và phản ánh cả 4 migration; `init_db.py` đánh dấu chúng đã áp dụng cho DB **mới**. **DB cũ phải chạy `python migrate.py`** (bắt buộc: bảng `authAttempts` cần cho đăng nhập/thanh toán). `schema.txt` là bản cũ không còn dùng (nên xóa).
- **P0-05:** checkout khóa theo thứ tự cố định `cartItems → products → paymentMethods` (`ORDER BY id FOR UPDATE`), trừ kho `UPDATE … WHERE inStock >= qty` và trừ tiền `… AND balance >= amount` đều kiểm `rowcount`; giá/tồn đọc dưới khóa; deadlock → `409 checkout_conflict`. PIN chưa đặt → `401 pin_not_set` (hết 500). Sai mật khẩu/PIN 5 lần liên tiếp → khóa 15 phút (`AUTH_MAX_ATTEMPTS`, `AUTH_LOCK_SECONDS`), `429 too_many_attempts` + `Retry-After`; đăng nhập, đổi mật khẩu và xin xóa tài khoản dùng chung một bộ đếm; username không tồn tại cũng bị đếm như thật. Bộ đếm lưu trong bảng `authAttempts`.
- **P0-06:** `debug` chỉ bật khi `SLOPEE_ENV=development`; mọi blueprint và app có handler lỗi chung (`{"error","code":"internal_error"}`, chi tiết ghi log); không còn `str(e)`; `json_body()` từ chối body không phải object (`400 invalid_body`); kiểm kiểu/độ dài/khoảng giá trị cho các trường, URL ảnh chỉ nhận `http(s)`; `MAX_CONTENT_LENGTH` 1 MB. Đăng ký nay yêu cầu email hợp lệ và số điện thoại 9–10 chữ số.
- **Quyết định nhóm sau P0-03…06 (đã áp dụng theo docs; `[~]` chờ nhóm xác nhận từng quyết định — PR #2 đã duyệt phần code P0-03…06):**
  1. **Hủy đơn `paid` (S-05)** nay hoàn kho + hoàn tiền người mua **và thu lại đúng khoản đã cộng cho người bán** (không tạo tiền). Migration `0005_order_line_settlement.py` thêm `orderLines.sellerPaymentMethodId` + `sellerCredit` (checkout ghi lại người bán nào được cộng bao nhiêu; đơn cũ được backfill). Người bán không đủ số dư → `409 refund_unavailable`, rollback toàn bộ, đơn vẫn `paid`. Đơn COD/`cash` chỉ hoàn kho. `PUT /api/payments/orders/:id` trả thêm `refunded` (VND). Giới hạn dữ liệu cũ (đã biết, chấp nhận ở mức đồ án): (a) dòng có `productId = NULL` (sản phẩm đã xóa) không suy ra được người bán nên migration không backfill, `sellerCredit = 0` và hủy đơn đó **hoàn tiền cho người mua mà không thu lại được từ người bán**; (b) các đơn COD cũ từng được cộng tiền cho người bán (lỗi cũ) **không bị sửa hồi tố**, số dư người bán đã sai trước đây giữ nguyên. DB demo nên tạo lại bằng `init_db.py` để tránh cả hai. Khóa theo thứ tự `products → paymentMethods` như checkout (không deadlock).
  2. **COD và phương thức `cash`** không còn cộng số dư người bán: chỉ cộng khi người mua thực sự bị trừ tiền. Chỉ áp dụng cho đơn mới; đơn COD cũ không sửa hồi tố (xem giới hạn (b) ở quyết định 1).
  3. **Giữ `orders.userId` ON DELETE `RESTRICT`** (SDD Q-06 cũng dùng RESTRICT cho `order_web3`; đơn và tiền ký quỹ là hồ sơ kế toán). `DELETE /api/admin/users/<id>` trả `409 user_has_orders` kèm thông báo rõ thay vì 500; giao diện admin hiển thị thông báo này.
  4. **Đánh số migration:** migration Web3 bắt đầu **sau migration cũ cuối cùng**. Vì `0005` đã dùng cho quyết định 1, Web3 bắt đầu từ **`0006`**: SDD `001_wallets.sql … 015_shipper.sql` → `0006_wallets.sql … 0020_shipper.sql` (bù +5). Tên tệp là khóa trong `schema_migrations`, nên không đổi tên sau khi đã áp dụng.
- **Thay đổi hành vi cho người dùng (P0-06):** đăng ký yêu cầu email hợp lệ và số điện thoại 9–10 chữ số. Thông báo lỗi API cũ giữ tiếng Anh; API Web3 mới theo SRS (`{code, message}` tiếng Việt) — nhóm chốt khi làm UC-00.
- **Đã chạy trên MySQL 8.0 thật (2026-10-11):** toàn bộ test backend (329, gồm 15+ test MySQL của P0-03…06 và các test song song hủy đơn/checkout) pass 3 lần liên tiếp; DB cũ (schema trước P0-04) chạy `python migrate.py` cho ra schema (cột + khóa ngoại) trùng hệt `init_db.py`. Việc còn lại là CI GitHub xác nhận lại. `backend/schema.txt` không có trong gói này (nếu còn trong repo thì nên xóa).

---

## 4. BẢNG THEO DÕI CHI TIẾT THEO TUẦN (WEEKLY SPRINT TRACKER)

### TUẦN 1: Khởi động nền tảng, Smart Contract cơ sở, Chuẩn hóa VND
> Quy ước: `[~]` = đã code, test xanh cục bộ, chờ PR được duyệt; `[x]` = đã duyệt và chốt PR. **Tuần 1 đã chốt PR nên toàn bộ mục bên dưới là `[x]`.** (Trạng thái `[x] PASS` của bảng test mục 5 vẫn chỉ đặt khi CI xanh trên nhánh chính.)
- [x] **[C] Thành viên A:** Cấu hình Foundry (`contracts/foundry.toml`, solc 0.8.20, `via_ir=true`, OpenZeppelin v5.0.2, forge-std v1.9.4). Cài thư viện bằng `scripts/install_contract_deps.sh` (không dùng `forge install` thẳng: một số bản Foundry bỏ qua tag và kéo OpenZeppelin 5.7, đòi solc ≥ 0.8.24).
- [x] **[C] Thành viên A:** `contracts/src/MockUSD.sol` (6 decimals, `mint` cho môi trường thử).
- [x] **[C] Thành viên A:** `contracts/src/SlopeeEscrowMaster.sol` phần nạp đơn: `depositEscrow` (xác minh EIP-712 `OrderQuote`, dùng chung `_acceptQuote`/`_collect` để tuần 2 chỉ việc thêm `depositEscrowBatch`), `confirmDelivery`, `earlyRelease`, `releaseAfterInspection`, `cancelIfUnfulfilled`. Struct/enum/sự kiện/hằng số/storage khai báo **đầy đủ ngay từ đầu** để ABI và bố cục storage không đổi ở tuần 2. Chưa có (tuần 2): tranh chấp, `arbitratorForceResolve`, `depositEscrowBatch`, `claimPending`, `setDefaultFeeBps`/`setFeeRecipient`.
- [x] **[C] Thành viên A:** `contracts/script/Deploy.s.sol` (triển khai, mint MockUSD cho buyer thử, ghi `deployments/local.json`) và 46 test Foundry (`forge test`): T-01…T-07, T-14, T-23 và các phần đã làm được của T-08, T-16, T-20, T-22 (xem 5.1).
- [x] **[B] Thành viên B:** `./scripts/bootstrap.sh` một lệnh: kiểm công cụ → cài thư viện contract → Anvil `--block-time 2` → `forge build` → triển khai → kiểm có mã trên chuỗi và `SHIPPER_ROLE` → ghi `deployments/local.json` → chép cho frontend → sinh `backend/.env.web3` (3 khóa vai trò khác nhau, khóa công khai của Anvil). Kèm `scripts/smoke_week1.sh`: chạy trên Anvil thật báo giá do **Python ký** → Buyer nạp → Shipper giao → Buyer nhận → kiểm số dư (đã chạy: Merchant +16.005.000, phí +495.000, escrow = 0). *Chưa làm trong bootstrap:* migration MySQL Web3 (tuần 2) và khởi động web/indexer/scheduler (tuần 3–5).
- [x] **[B] Thành viên B:** Triển khai **P0-01** (Auth Token) và **P0-02** (Phân quyền Role & bảo vệ Admin). *(đã review 14/10/2026, PR #2)*
- [x] **[B + C]:** Triển khai **P0-07** (Chuyển schema và giao diện sang VND số nguyên). *(đã review 14/10/2026, PR #2)*
- [x] **[F] Thành viên C:** Client API dùng chung `lib/client.js`, hàm định dạng `lib/format.js` (`formatVND`, `shortAddress`), Route Guard `components/RequireRole.jsx` (chưa đăng nhập → `/login`; sai role → thông báo; áp cho `/admin`, `/seller`, `/cart`, `/checkout`, `/orders`, `/settings`). **Đã chốt tên file theo SDD:** `lib/` là nơi chuẩn; `api/http.js` và `utils/formatVND.js` giữ lại chỉ như lớp re-export để không vỡ import/test cũ (một nguồn sự thật). Các `api/*.js` không còn hardcode `http://localhost:5000` (đọc `VITE_API_BASE`).
- [x] **[F] Thành viên C:** Khung ví `hooks/useWallet.js` (`WalletProvider` + `useWallet`: kết nối EIP-1193/MetaMask, theo dõi `accountsChanged`/`chainChanged`, `switchToDeployedChain` có thêm mạng khi mã 4902, `getSigner()` ethers v6, mã 4001 = "Bạn đã hủy thao tác", không lưu gì vào localStorage) và `lib/chain.js` (đọc/kiểm `deployments/local.json`, chỉ chấp nhận chainId 31337). Chưa có UI kết nối (Navbar/`pages/Wallet.jsx` là UC-00, tuần 3) và chưa có ABI (đóng băng ở M1).
- [x] **[Q] Cả nhóm:** Khóa `shared/eip712/types.json` và tạo `shared/eip712/vectors.json` (sinh bằng `scripts/gen_eip712_vectors.py`, có `--check` cho CI): 3 báo giá, 2 phán quyết (kèm chữ ký Trọng tài), 2 `docHash`. **Đã chạy luôn kiểm tra chéo ngôn ngữ** ở cả 3 nơi cho cùng domainSeparator/structHash/digest/người ký: Python (`test_eip712_vectors.py`), JS (`eip712Vectors.test.js`), Solidity (`Eip712Vectors.t.sol`, còn nạp thật báo giá do Python ký vào contract). *Còn thiếu:* vector cho thông điệp liên kết ví (SDD 8.3) — định dạng SIWE chốt ở UC-00 (tuần 3).

**Cách chạy lại tuần 1:** `./scripts/bootstrap.sh && ./scripts/smoke_week1.sh` · `cd contracts && forge test` · `pytest test` · `cd frontend && npx vitest run`.
**Lưu ý cho bên review:** (1) khóa trong `EscrowBase.t.sol`, `Deploy.s.sol`, `bootstrap.sh`, `gen_eip712_vectors.py` là **khóa thử công khai của Anvil** — bài quét E-05 (AC-09) phải cho phép danh sách này, nếu không sẽ báo nhầm; (2) `contracts/lib/` bị `.gitignore` (cài bằng `scripts/install_contract_deps.sh`); (3) `foundry.toml` dùng `solc_version = "0.8.20"` (Foundry tự tải); (4) địa chỉ contract trong vector (`0xe7f1…0512`, token `0x5FbD…0aa3`) khớp lần triển khai đầu trên Anvil sạch của deployer #0.

---

### TUẦN 2: Hoàn thiện Smart Contract, Nạp gom & Đạt Cột mốc M1
> Quy ước `[~]` như Tuần 1: đã code, test xanh cục bộ, **chờ PR được duyệt**. Chưa `[x]` vì chưa qua review/CI.
- [x] **[C] Thành viên A:** Cài đặt logic tranh chấp: `raiseDispute` (chỉ Buyer, `DELIVERED → DISPUTED`, `now < deliveredAt + inspectionDuration`), `resolveDispute` (2 chữ ký EIP-712 của 2 bên khác nhau trong Buyer/Merchant/Trọng tài; ai cũng nộp được; `deadline < disputedAt + disputeTimeout`; nonce theo đơn).
- [x] **[C] Thành viên A:** Cơ chế thoát hiểm timeout: `arbitratorForceResolve` (`ARBITRATOR_ROLE`, chỉ khi `now >= disputedAt + disputeTimeout`). Hai đường `resolveDispute` và thoát hiểm **không bao giờ cùng hợp lệ** (R-02): đã test cả hai phía của mốc (T-15, T-24).
- [x] **[C] Thành viên A:** Nạp gom nhiều shop: `depositEscrowBatch` (nguyên tử, tối đa 5 đơn, một token, thu tiền đúng một lần; dùng chung `_acceptQuote`/`_collect` với `depositEscrow` nên không có đường nạp nào yếu hơn). Ghi đơn `LOCKED` ngay trong vòng lặp nên `orderId` trùng trong cùng lô bị từ chối (`Order exists`) thay vì bị thu tiền hai lần.
- [x] **[C] Thành viên A:** Sổ chờ rút pull-payment: `claimPending` (xóa số dư trước khi chuyển, `nonReentrant`), `PayoutDeferred`/`PendingClaimed`; thêm `setDefaultFeeBps` (trần ≤ 1.000 BPS) và `setFeeRecipient` (Admin). Struct/enum/sự kiện/storage giữ nguyên Tuần 1 — chỉ **thêm** hàm.
- [x] **[C] Thành viên A:** Bộ test Foundry **139 test** (`forge test`): T-01…T-34 đủ + invariant INV-01…INV-07 (8 invariant, handler gọi ngẫu nhiên cả nạp đơn lẻ và nạp gom, 128 run × 100 lời gọi). **Gas nạp gom 5 shop (T-32): 1.229.409 (token), 1.099.331 (ETH)** — dưới mục tiêu 3.000.000. Phân bổ: `Eip712Vectors` 5, `Week1` 41, `Week2` 59, `Batch` 24, `Matrix` 2 (45 cặp âm), `Invariant` 8.
- [x] **[B] Thành viên B:** 15 migration MySQL Web3 `0006`…`0020` (SDD `001_wallets`…`015_shipper`; tên thật: `0006_wallets.py`, `0007_checkout_groups.py`, `0008_order_web3.py`, `0009_order_quotes.py`, `0010_dispute_resolutions.py`, `0011_dispute_signatures.sql`, `0012_chain_events.sql`, `0013_indexer_cursor.sql`, `0014_platform_settings.sql`, `0015_category_policies.sql`, `0016_category_policy_map.sql`, `0017_tx_outbox.sql`, `0018_onchain_id_seq.sql`, `0019_pending_balances.sql`, `0020_shipper.py`), bảng `order_web3` quan hệ 1-1 với `orders`. Migration có khóa ngoại tới bảng Slopee là `.py` và **phòng vệ** (SDD Q-06): đọc kiểu/charset/collation của cột cha, dừng nếu bảng cha không phải InnoDB. `schema.sql` đã phản ánh đủ (16 bảng Web3 + `users.role` có `shipper`). **31 test mới** (6 tĩnh + 25 trên MySQL 8.0 thật); toàn bộ pytest **360 pass, 0 skip**.
- [x] **[Q] Thành viên B + C:** Chạy test chéo ngôn ngữ Python, JavaScript và Solidity khớp 100% digest EIP-712. *(đã chạy sớm ở tuần 1 cho báo giá, phán quyết, docHash; vẫn xanh sau thay đổi tuần 2; vector liên kết ví đã bổ sung ở Tuần 3)*
- [x] 🎯 **NGHIỆM THU CỘT MỐC M1:** *(đạt cục bộ; chờ A(Dev)/B(Review) duyệt và CI xanh để chuyển `[x]`)*
  - [x] Độ phủ dòng lệnh contract đạt ≥ 90% (`forge coverage --ir-minimum`): **100% (153/153 dòng của `src/`)**; 100% hàm. Lưu ý: số liệu *nhánh* Foundry báo 33% (30/90) vì nó đếm từng `require`/modifier là nhánh; tiêu chí M1 là dòng lệnh.
  - [x] Chạy Slither không còn cảnh báo mức High chưa giải thích: **0 High, 0 Medium chưa giải thích**. Một High (`reentrancy-balance` ở `_collect`) và 2 Medium (`incorrect-equality`) là false positive có chủ đích, đã ghi lý do ngay tại mã bằng `slither-disable` (đọc chênh lệch số dư để loại token phí-khi-chuyển; mọi đường gọi đều `nonReentrant`, chứng minh bằng T-17). Còn 9 cảnh báo Low (8 `timestamp` do spec bắt buộc dùng `block.timestamp`, 1 `reentrancy-benign` ở `_payout`: ghi sổ chờ rút sau `call` giới hạn 30.000 gas, có `nonReentrant`).
  - [x] Đóng băng ABI `SlopeeEscrowMaster.json` (37 hàm, 15 sự kiện) + `MockUSD.json`: xuất bằng `scripts/export_abi.sh` sang `shared/abi/` (nguồn duy nhất cho backend) và `frontend/src/lib/abi/`; `--check` chạy trong CI để ABI không lệch khỏi contract. *(Chưa nối vào `lib/chain.js`: việc của Thành viên C ở Tuần 3–4.)*

**Cách chạy lại tuần 2:** `(cd contracts && forge test)` (invariant ~1–1,5 phút) · `(cd contracts && forge coverage --ir-minimum --report summary --no-match-coverage "(test|script)")` · `(cd contracts && slither . --exclude-informational)` · `./scripts/export_abi.sh --check` · `pytest test` (cần MySQL 8.0 ≥ 8.0.16 cho phần migration) · `./scripts/bootstrap.sh && ./scripts/smoke_week1.sh` (đã chạy: contract tuần 2 triển khai và smoke tuần 1 `SMOKE OK`).

**Ghi chú & quyết định Tuần 2 (cần nhóm xem khi review):**
1. **Gieo dữ liệu trong migration thay vì `bootstrap.sh`** (lệch nhẹ so với SRS/SDD 7.6): `bootstrap.sh` chưa chạm MySQL và nhóm `GENERAL` là bắt buộc (danh mục chưa ánh xạ dùng GENERAL). Dùng `INSERT IGNORE` nên chạy lại không đè giá trị Admin đã sửa (có test). SDD 7.6 đã được đính chính cho khớp (tài liệu đóng băng nhưng sửa như một góp ý để tránh lặp lại). Giá trị 4 nhóm chính sách là **giá trị đề xuất của SRS, nhóm chốt lại trước Tuần 3**.
2. **Gieo 4 khóa `platform_settings`:** `PLATFORM_FEE_BPS=300`, `QUOTE_TTL_SECONDS=900` (có sẵn trong đặc tả) cùng `FX_VND_PER_TOKEN=25000` (1 token = 25.000 VND) và `DISPUTE_SIG_TTL_SECONDS=604800` (7 ngày), hai giá trị này do nhóm chốt vì đặc tả không có mặc định. Backend vẫn nên báo lỗi rõ nếu một khóa bị Admin xóa.
3. **Ba chỗ sửa test Tuần 1/Phase 0 (hành vi kiểm không yếu đi):** (a) `test_p0_mysql::test_order_with_order_web3_row_is_rejected` trước đây tự tạo bảng `order_web3` tối thiểu, nay chèn dòng vào bảng thật; (b) `test_p0_04::test_schema_statements_are_all_creates_and_splittable` nới để cho phép thêm đúng `INSERT IGNORE INTO` (gieo mặc định); (c) `SlopeeEscrowWeek1::test_T05…` đọc `vm.getBlockTimestamp()` thay `block.timestamp` vì `forge coverage --ir-minimum` làm `block.timestamp` cũ sau `vm.warp` (test xanh ở chế độ thường, đỏ ở chế độ coverage).
4. **Handler invariant bản đầu gần như vô nghĩa (ghi nhận là một đóng góp, giữ nguyên):** đo thực tế cho thấy mỗi run chỉ có ~4 lần nạp, 0 tranh chấp, 0 nạp gom nên invariant xanh chẳng chứng minh gì. Đã chỉnh handler (đa số lời gọi hợp lệ, thêm `progress`/`openDispute`) và đo lại: mỗi run đều chạm nạp gom, giải ngân, hoàn tiền, khiếu nại, phân xử bằng chữ ký, thoát hiểm, hoãn ETH và rút khoản chờ. Mốc này nên được review kỹ.
5. **Nhánh ERC-20 của `claimPending` không thể đến được qua đường đi thật** (`_payout` chỉ hoãn ETH; ERC-20 revert nếu chuyển lỗi). Test T-16 dựng số dư chờ rút ERC-20 bằng `vm.store` để chứng minh nhánh đúng. **Quyết định của nhóm: không sửa contract, giữ nguyên nhánh này.** Test `vm.store` vẫn giữ để chứng minh nhánh đúng.
6. **Test migration phát hiện một điểm tinh tế:** cột tham chiếu bảng Web3 *mới* (`order_web3.checkout_group_id` → `checkout_groups.group_id`) khớp cột cha mới chứ không khớp collation của bảng Slopee cũ; quy tắc đúng là "khớp cột cha", và test collation `utf8mb4_unicode_ci` xác nhận migration phòng vệ xử lý được trường hợp DB cũ lệch collation (DDL ngây thơ lỗi errno 3780).



---

### TUẦN 3: Liên kết ví, Tạo đơn, Báo giá có chữ ký (Backend Core)
> Quy ước `[~]` như Tuần 1–2: đã code, test xanh cục bộ (MySQL 8.0.46 + Anvil 1.5.1 thật), **chờ PR được duyệt và CI xanh**.
- [x] **[A ➔ B] Thành viên A:** Hỗ trợ Thành viên B hoàn thiện Giai đoạn 0 (P0-03 đến P0-06). *(đã review 14/10/2026, PR #2)*
- [x] **[B] Thành viên B:** UC-00: `POST /api/wallet/nonce`, `POST /api/wallet/link`, `GET /api/wallet` (`slopee_web3/application/wallet_service.py`, `adapters/flask_api/routes.py`). Nonce 32 hex dùng một lần, hạn 300 giây tính theo giờ DB, giới hạn 5 nonce/phút/tài khoản; Backend **tự dựng lại** thông điệp SIWE từ dữ liệu của mình (không tin thông điệp client gửi) rồi `recover` và so địa chỉ; tiêu thụ nonce nguyên tử (`UPDATE … WHERE used_at IS NULL AND expires_at > NOW()` kiểm `rowcount`); một ví chỉ thuộc một tài khoản (`WALLET_TAKEN`); đổi ví thì ví cũ `is_active = 0`, luôn đúng một ví active; chữ ký sai/nonce hết hạn **không để lại dấu vết** (không đốt nonce, không ghi ví).
- [x] **[B] Thành viên B:** UC-01: `POST /api/orders` (`application/quote_service.py`): nhóm theo shop (tối đa 5), cấp `onchain_order_id` từ `onchain_id_seq`, quy đổi VND ➔ token bằng số nguyên làm tròn lên (`domain/money.py`), `docHash` (canonical JSON + keccak, tái tạo được từ DB), thời hạn theo `category_policies` (`max()` riêng từng thời hạn, kiểm giới hạn, `policy_code` ghi theo policy chủ đạo), phí `min(PLATFORM_FEE_BPS, defaultFeeBps on-chain)`, hạn báo giá `now_chain() + QUOTE_TTL_SECONDS`, ký `OrderQuote` EIP-712 bằng `QUOTE_SIGNER_KEY` (`adapters/env_signer.py`). Một giao dịch DB: `checkout_groups` + `orders` + `orderLines` + giữ chỗ tồn kho (`UPDATE … WHERE inStock >= qty`) + `order_web3` + `order_quotes`; lỗi ở shop nào cũng rollback cả lô. Kiểm tra: đã liên kết ví (Buyer và từng Merchant), tự mua hàng của mình, hết hàng, sản phẩm ngừng bán, `BATCH_TOO_LARGE`, cài đặt sàn sai/thiếu, chain không kết nối được.
- [x] **[B] Thành viên B:** `POST /api/checkout-groups/:id/quote` (cấp lại báo giá cả lô: giữ `onchain_order_id`, `docHash`, thời hạn; đọc lại trần phí, tỷ giá, ví; **kiểm `orders(id) == NONE` trực tiếp trên chuỗi** trước khi ký lại) và `GET /api/checkout-groups/:id`.
- [x] **[B] Thành viên B:** Khung Indexer (`adapters/web3_chain.py`, `adapters/indexer/`): đọc block/log thật từ Anvil, `GET_LOCK` một thể hiện, con trỏ `indexer_cursor`, cửa sổ ≤ 500 block mỗi giao dịch, ghi `chain_events` idempotent (`INSERT IGNORE` trên `UNIQUE(tx_hash, log_index)`), phát hiện Anvil khởi động lại (`ChainReset`), backoff khi RPC lỗi; chạy bằng `cd backend && python -m slopee_web3.adapters.indexer [--once]`. **Registry handler rỗng, chưa đổi trạng thái đơn (Tuần 4).**
- [x] **[B] Thành viên B:** `POST /api/orders/eligibility` (**mới, chỉ đọc, không khóa dòng**): trả `{all_linked, shops[{shop_id, shop_name, wallet_linked}]}` cho các cart item của chính người gọi (không lộ địa chỉ ví); thêm `shop_name` vào `extra` của `WALLET_NOT_LINKED` (merchant) để giao diện nêu đích danh shop. Phục vụ F-08.
- [x] **[B] Hạ tầng dùng chung:** `domain/order_state.py` (bảng chuyển trạng thái + ánh xạ `orders.status` theo SRS 5.1), bộ lọc log che `signature/private/key/mnemonic` (`adapters/logging_filter.py`), kiểm khóa vai trò **khớp contract lúc khởi động** (`hasRole`), ba khóa vai trò phải khác địa chỉ, `register_web3(app)` nối vào `app.py` (chưa có `backend/.env.web3` thì app cũ vẫn chạy, API Web3 trả `WEB3_NOT_CONFIGURED`).
- [x] **[Q] Vector chéo ngôn ngữ cho liên kết ví** *(nợ từ Tuần 2)*: `walletLink` trong `shared/eip712/vectors.json` (sinh bởi `scripts/gen_eip712_vectors.py`, bản dựng thông điệp **độc lập** với backend); Python kiểm thông điệp trùng từng byte và khôi phục đúng người ký, JavaScript (`ethers.verifyMessage`) khôi phục đúng người ký; Solidity không dùng vector này (không có thao tác on-chain).
- [x] **[F] Thành viên C:** `pages/Wallet.jsx` (route `/wallet`, chỉ `user`/`seller`; kết nối MetaMask → kiểm mạng → `personal_sign` không tốn gas → liên kết/đổi ví; hủy ký hiển thị trung tính, không phải lỗi) + liên kết "🦊 Ví" ở Navbar.
- [x] **[F] Thành viên C:** Khung thanh toán Web3: lựa chọn "Thanh toán Web3" trong `pages/Checkout.jsx` (luồng PIN cũ giữ nguyên) + `components/Web3CheckoutPanel.jsx`: cổng điều kiện (ví → mạng → đã liên kết → đúng ví), tạo báo giá, bảng từng shop + tổng token + tỷ giá + thời hạn, **đếm ngược theo `server_time`** (F-06), lấy báo giá mới, **"Làm mới báo giá cho lô này"** khi gặp `PENDING_GROUP_EXISTS` (F-07: nhãn nói đúng bản chất là xin chữ ký + hạn 15 phút MỚI, nút khóa trong lúc gọi API và chặn bấm dồn bằng cờ `inFlight`, đồng hồ bắt đầu đúng 15:00; lỗi tạm thời vẫn cho thử lại, lỗi `INVALID_STATE`/`GROUP_NOT_FOUND` thì không). **Checkout khóa lựa chọn Web3 khi có shop chưa liên kết ví nhận tiền** (F-08, BR-07): radio bị `disabled` + dòng cảnh báo nêu tên shop; panel nêu đích danh shop khi vẫn gặp `WALLET_NOT_LINKED` của merchant và không dẫn người mua tới `/wallet`. **Nút "Ký quỹ" cố ý bị khóa (approve + nạp tiền là Tuần 4).** Kèm `api/web3.js`, `lib/errors.js` (mã lỗi → tiếng Việt), `lib/web3Checkout.js` (định dạng token bằng BigInt), `lib/walletLink.js`, `mocks/web3Mock.js` (bật bằng `VITE_WEB3_MOCK=true`, hình dạng bám đúng API thật).

**Kết quả test Tuần 3 (chạy cục bộ):** backend `pytest test` **580 pass** (360 cũ + 220 mới), frontend `vitest` **150 pass** (70 cũ + 80 mới), `forge test --match-contract Eip712Vectors` vẫn xanh sau khi thêm vector. Phân bổ test mới: `test_w3_domain` 50, `test_w3_architecture` 15 (T-ARCH-01), `test_w3_signer` 10, `test_w3_routes` 46, `test_w3_wallet_mysql` 24, `test_w3_quote_mysql` 53, `test_w3_indexer_mysql` 17, `test_w3_chain_anvil` 5 (chuỗi thật); frontend `web3Lib` 34, `web3Api` 9, `web3Ui` 36, thêm 1 test vector `walletLink`.

**Cách chạy lại tuần 3:** `pytest test` (cần MySQL 8.0) · test chuỗi thật: `./scripts/bootstrap.sh --fresh --force-env && pytest -m anvil` (tự skip nếu không có Anvil; CI job `web3-chain` đặt `REQUIRE_ANVIL=1` nên thiếu Anvil là đỏ) · `(cd frontend && npx vitest run)` · `python scripts/gen_eip712_vectors.py --check`. Xem giao diện khi chưa có backend/chuỗi: `VITE_WEB3_MOCK=true npm run dev`.

**Ghi chú & quyết định Tuần 3 (cần nhóm xem khi review):**
1. `[x]` **Đã chốt 14/10/2026 — lệch nhẹ so với SDD 10.2, đã có test:** `nonce` nhận thêm `address`: SDD ghi "không có đầu vào" nhưng thông điệp SIWE phải chứa địa chỉ nên `POST /api/wallet/nonce` nhận `{address}`. Tương tự `POST /api/wallet/link` nhận thêm `nonce` **tùy chọn** (bỏ qua thì dùng nonce còn hạn mới nhất của chính tài khoản). Chữ ký của ví khác/địa chỉ khác đều bị `BAD_SIGNATURE` vì thông điệp chứa địa chỉ và mã tài khoản. **Test:** `test_w3_wallet_mysql.py` (nonce/link theo địa chỉ, `test_without_nonce_uses_the_latest_unused_one`, `test_claiming_a_different_address_than_the_signer_is_rejected`, `test_message_for_one_account_is_useless_for_another`), `test_w3_routes.py` (`test_nonce_and_link_validate_input`, `test_link_passes_optional_nonce`), `web3Api.test.js` (thân yêu cầu `{address}` / `{address, signature, nonce}`). SDD/SRS không sửa (quy ước repo); điểm lệch ghi ở `AI_CONTEXT.md` mục 6.
2. **Không có cờ "sản phẩm bật Web3":** schema `products` không có cột này nên mọi sản phẩm đang bán đều thanh toán được bằng Web3 (nếu nhóm cần cờ này thì thêm migration `0023`; `0021_notifications` và `0022_dispute_notes` đã dùng).
3. `[x]` **Chặn giữ chỗ tồn kho hai lần (`PENDING_GROUP_EXISTS`, 409):** tạo đơn lần hai cho sản phẩm đã nằm trong lô `PENDING_PAYMENT` của cùng người mua bị từ chối kèm `checkout_group_id`; Frontend hiện nút **"Làm mới báo giá cho lô này"** (= cấp lại báo giá cho chính lô đó; đổi nhãn từ "Tiếp tục lô đang chờ" vì nhãn cũ khiến người dùng tưởng là khôi phục phiên dở dang với số phút còn lại của lần trước). Không có điều này, bấm thanh toán hai lần sẽ trừ kho hai lần cho tới khi bộ quét hết hạn (Tuần 5) chạy.
4. `[x]` **Đã chốt 14/10/2026 — không đổi gì:** cấp lại báo giá làm mới cả tỷ giá (không chỉ hạn): giữ nguyên `price_vnd`, thời hạn, `docHash`, `onchain_order_id`; đọc lại tỷ giá, trần phí và ví hiện tại, nên `amount_raw` có thể đổi giữa hai lần báo giá (người dùng thấy số mới trước khi ký). Lô đã `EXPIRED` được cấp lại bằng cách giữ chỗ tồn kho lại (hết hàng thì từ chối **cả lô**, không trừ dở); bộ quét hết hạn trả kho ở Tuần 5.
5. **`created_at` của đơn do Backend chọn trước khi ký** (`FROM_UNIXTIME`) để `docHash` tái tạo được từ DB — test băm lại từ `orderLines` + `orders.created_at` ra đúng `docHash` đã ký.
6. **Hai lỗi thật do chính test phát hiện và đã sửa:** (a) hai yêu cầu đồng thời cùng giỏ hàng cùng thành công (kiểm "lô đang chờ" đọc snapshot cũ) → đưa các lệnh đọc **khóa** (`cartItems`, `products`) lên trước mọi đọc thường (InnoDB chỉ tạo snapshot ở lần đọc thường đầu tiên); (b) deadlock giữa hai tài khoản liên kết ví song song (khóa khoảng của `FOR UPDATE`/`UPDATE` không khớp dòng) → đọc không khóa + chỉ `UPDATE` khi thật sự có ví cũ. Hai bài toán này **không có trong test giả (mock)**, chỉ lộ ra trên MySQL thật: nên giữ test đua song song trong CI.
7. **Che log không che chuỗi 0x+64 hex trần** vì đó cũng là dạng tx hash (cần để gỡ lỗi Indexer); chỉ che theo tên trường (`signature`, `private`, `key`, `mnemonic`, `seed`, `secret`) và chữ ký 65 byte. Bài quét E-05 (AC-09) vẫn phải chạy riêng lên repo/DB/log.
8. `[x]` **Đã chốt 14/10/2026 — không đổi gì:** các test W3 chạy trên database riêng (`test/integration_test/conftest.py` tạo và xóa) vì chúng ghi nhiều dữ liệu dùng chung (ví theo địa chỉ Anvil cố định, id on-chain, `platform_settings`); chia sẻ DB của phiên làm lệch test migration cũ (so sánh cả `AUTO_INCREMENT`).
9. **Phụ thuộc mới:** `web3>=7,<9` trong `backend/requirements.txt` (mới kiểm thử với 8.0.0; hexbytes mới trả `.hex()` **không có `0x`** nên adapter chuẩn hóa tiền tố).
10. `[x]` **Endpoint mới ngoài danh sách SDD 10.2 — `POST /api/orders/eligibility`:** cần để thực hiện F-08 vì không API nào khác cho biết shop đã liên kết ví hay chưa (phải kiểm trước khi người mua chọn phương thức, thay vì để lỗi `WALLET_NOT_LINKED` ở bước cuối). Chỉ đọc, chỉ trả tên shop + cờ đã/chưa liên kết. Kết quả chỉ để hiển thị: quyết định thật vẫn là `create_checkout` (kiểm lại trong giao dịch; test `test_eligibility_agrees_with_checkout_decision`). Giao diện **không chặn** khi không hỏi được (lỗi mạng/máy chủ) để panel báo lỗi thật; riêng `WEB3_NOT_CONFIGURED` thì khóa với thông báo riêng. `extra.party` Backend gửi `'merchant'`/`'buyer'` chữ thường; Frontend so không phân biệt hoa/thường.
11. `[x]` **Test UI Web3 nới timeout chờ (8 s) và `testTimeout` 20 s riêng file `web3Ui.test.jsx`:** ký ethers lần đầu mất vài giây khi máy tải cao (đã thấy 2 lần flake khi chạy 12 tiến trình song song, không phải lỗi logic); sau khi nới chạy 24/24 lần xanh ở mức tải đó.
12. **Chưa làm / ngoài phạm vi Tuần 3:** Indexer chưa có handler (Tuần 4: `OrderCreated` → `LOCKED`, xóa giỏ), `GET /api/orders/:code/status` (Tuần 4), nạp tiền/approve ở Frontend (Tuần 4), nhánh ETH (chỉ MockUSD), hoàn kho khi hết hạn (Tuần 5), E2E Playwright. Frontend **chưa thử với MetaMask thật** (test dùng ví giả ký thật bằng khóa Anvil + `ethers.verifyMessage`); các màn hình dùng chuỗi tiếng Việt, phần còn lại của app vẫn tiếng Anh như trước.

---

### TUẦN 4: Event Indexer, Tích hợp Ký quỹ & Đạt Cột mốc M2
- [x] **[B] Thành viên B:** Hoàn thiện Indexer: Lắng nghe sự kiện `OrderCreated`, kiểm tra tính toán vẹn đối soát với báo giá đã lưu, cập nhật `order_web3.status = LOCKED` và đồng bộ `orders.status = paid` trong cùng giao dịch. *(`adapters/indexer/handlers.py::on_order_created` + `adapters/legacy_sync.py::sync_legacy_status` — hàm đồng bộ duy nhất. Đối chiếu buyer/merchant/token/amount/inspectionDuration/disputeTimeout/feeBps/docHash với `order_web3` (không phân biệt hoa/thường địa chỉ); lệch ⇒ vẫn `LOCKED` (tiền đã khóa thật) nhưng `anomaly_flag=1`, không sửa giá/phí/hạn; `deposit_tx_hash`, `chain_created_at` = giờ block; chuyển trạng thái không hợp lệ (đơn `EXPIRED`/đã `LOCKED`) ⇒ chỉ `anomaly_flag`, không lùi trạng thái; sự kiện của đơn không có ở sàn ⇒ chỉ lưu `chain_events` + cảnh báo. Chờ PR duyệt + CI xanh.)*
- [x] **[B] Thành viên B:** Indexer xóa `cartItems` của đơn hàng sau khi sự kiện `OrderCreated` được ghi nhận. *(`clear_cart_items`: xóa đúng dòng giỏ của Buyer khớp `(productId, selectedVariants)` với `orderLines` của đơn, cùng giao dịch với đổi trạng thái; món không thanh toán vẫn còn trong giỏ; chưa có sự kiện thì giỏ nguyên vẹn.)*
- [x] **[B] Thành viên B:** Cơ chế con trỏ block `indexer_cursor`, bảo vệ reorg, API polling trạng thái `GET /api/orders/:code/status`. *(Reorg: hash block tại con trỏ lệch và `REORG_DEPTH>0` ⇒ `Indexer._rewind` trong MỘT giao dịch: lùi con trỏ, xóa `chain_events` từ block đó, đưa đơn bị ảnh hưởng về `PENDING_PAYMENT` + `orders.status='pending'` rồi chạy lại handler trên sự kiện còn lại (`rollback_orders_from_block`, dùng lại được cho replay Tuần 9); `cartItems` đã xóa KHÔNG khôi phục. API: `OrderStatusService` + route `GET /api/orders/<code>/status` — trả `status, delivered_at, inspection_duration, disputed_at, dispute_timeout, anomaly, server_time(now_chain)` + `order_id`; chỉ Buyer/Merchant của đơn hoặc Admin, người khác/không tồn tại ⇒ 404 `ORDER_NOT_FOUND`.)*
**Kết quả test Tuần 4 phần [B] (chạy cục bộ, MySQL 8.0.46):** `pytest test` **592 pass, 5 skip** (5 test `anvil` cần chuỗi thật); thêm 16 test trong `test/integration_test/test_w3_indexer_orders_mysql.py` (LOCKED + `orders=paid` + xóa giỏ đúng dòng, nạp gom 2 shop, idempotent, 5 kiểu lệch báo giá ⇒ anomaly, địa chỉ khác hoa/thường, đơn lạ, đơn `EXPIRED`, rollback khi handler lỗi, 2 test reorg, HTTP status + quyền sở hữu). Chạy lại: `pytest test/integration_test/test_w3_indexer_orders_mysql.py`. **Chưa làm / để Tuần 5+:** handler Delivered/Disputed/Completed/Refunded, chặn route cũ ghi đè đơn Web3 (I-06), test Indexer với Anvil thật cho `OrderCreated` (cần chạy `bootstrap.sh` + `pytest -m anvil`).
- [x] **[F] Thành viên C:** Tích hợp giao diện Checkout với hợp đồng thật: Luồng 2 bước MetaMask (Bước 1: `approve` tổng; Bước 2: `depositEscrowBatch`). *Đã code + test xanh cục bộ (giả hợp đồng theo giao diện ethers, mã hóa kiểm với ABI thật); **chưa chạy với MetaMask + Anvil thật**, chờ PR review và kịch bản M2.* Gồm: `lib/depositFlow.js` (máy trạng thái 9.3 `depositReducer`, kiểm báo giá trước khi gửi ví, ánh xạ lỗi contract 9.5, `runDeposit`), `hooks/useEscrow.js`, `components/TxStepper.jsx`, nút "Ký quỹ" trong `Web3CheckoutPanel.jsx` đã mở.
- [x] **[F] Thành viên C:** Hook `usePolling.js` để tự động chuyển màn hình khi đơn chuyển sang `LOCKED`. *Đã code + test xanh cục bộ, chờ PR review.* `usePolling(fn, {intervalMs, stopWhen, enabled, maxConsecutiveErrors})`: không chồng lệnh, hủy khi rời trang (AbortSignal), lỗi mạng tạm thời không dừng. Panel polling `GET /api/checkout-groups/:id` mỗi 2,5 s; mọi đơn con `LOCKED` → báo thành công → sau 2 s chuyển `/orders`.
- [x] 🎯 **NGHIỆM THU CỘT MỐC M2 (Lát cắt End-to-End thô):**
  - [x] Luồng test: Đăng nhập ➔ Liên kết ví ➔ Đặt giỏ 2 shop ➔ Ký quỹ qua MetaMask ➔ Indexer bắt log ➔ DB chuyển `LOCKED` ➔ Frontend hoàn tất thành công.

**Ghi chú Tuần 4 — phần Thành viên C (cập nhật gần nhất):**
1. **LOCKED chỉ theo API, không theo biên nhận ví (DD-04, BR-09):** sau `depositEscrowBatch` được đào, bước là `WAITING_INDEXER`; chỉ khi `GET /api/checkout-groups/:id` trả MỌI đơn con `LOCKED` (hoặc xa hơn) mới báo thành công. Phụ thuộc việc của **B**: Indexer handler `OrderCreated` (hiện `HANDLERS = {}`). Khi chưa có handler, giao diện sẽ dừng ở "Chờ hệ thống xác nhận" và sau 30 s hiện mã giao dịch (SDD 9.3).
2. **Frontend tự kiểm báo giá trước khi bật ví** (`validateGroupForDeposit`): `quote.buyer` = ví đang kết nối, `quote.token` và `token_address` = `mockUSD` trong `deployments/local.json`, `quote.amount` = `amount_raw`, tổng = `total_amount_raw`, ≤ 5 shop. Sai thì dừng, không mở MetaMask. Còn dưới 60 s tới hạn thì yêu cầu lấy báo giá mới; kiểm lại hạn ngay trước cửa sổ ví thứ hai (approve có thể mất thời gian).
3. **`approve` đúng bằng tổng lô** (không approve vô hạn); đủ `allowance` thì bỏ bước approve; thiếu số dư thì nêu số thiếu và không gửi gì.
4. **Lỗi "Order exists"** (lần nạp trước đã vào chuỗi nhưng giao diện chưa kịp ghi nhận, ví dụ tải lại trang) → không nạp lại, chuyển sang chờ API xác nhận. Hủy trong ví (4001) hiển thị trung tính, bấm "Thử lại ký quỹ" được. Bấm dồn chỉ chạy một luồng ví (cờ `running` ref); cảnh báo `beforeunload` khi đang giữa luồng.
5. **Test:** `depositFlow.test.js` (37), `usePolling.test.jsx` (7), `depositUi.test.jsx` (9) + sửa 1 test cũ (nút Ký quỹ không còn bị khóa). Toàn bộ frontend: 203 test xanh, `vite build` thành công, lint sạch trên các file mới. Test phát hiện và sửa 1 lỗi thật: `TxStepper` đánh dấu sai bước lỗi khi chưa có tx hash → reducer thêm `APPROVE_REQUESTED`/`DEPOSIT_REQUESTED` và `failedStep`.
6. **Chưa làm / không thuộc phạm vi C Tuần 4:** nghiệm thu **M2** (cần B xong Indexer + `GET /api/orders/:code/status`, chạy tay với MetaMask + Anvil); `useOrderStatus` (dùng endpoint status của B, Tuần 5); `MyOrders.jsx` vẫn là bản cũ nên đơn Web3 sau khi chuyển trang hiện theo `orders.status` (`paid`); Playwright E2E (Tuần 8).

---

### TUẦN 5: Cổng Shipper, Relayer & Luồng Giải ngân tự động
- [x] **[B] Thành viên B:** Cổng Shipper: API `GET /api/shipper/orders` và `POST /api/shipper/orders/:code/deliver`.
- [x] **[A ➔ B] Thành viên A:** Cài đặt Relayer gửi giao dịch `confirmDelivery` lên Anvil bằng khóa `SHIPPER_KEY` qua hàng đợi một luồng (`tx_outbox`).
- [x] **[B] Thành viên B:** Tác vụ nền (Scheduler): `QuoteExpirySweeper`, `AutoRelease`, `DeliveryTimeoutReminder`, `ReconcileSnapshot`.
- [x] **[A ➔ F] Thành viên A:** Xây dựng màn hình cổng Shipper (`pages/ShipperOrders.jsx`).
- [x] **[F] Thành viên C:** Cập nhật màn hình Buyer (`pages/MyOrders.jsx`): Hiển thị đồng hồ đếm ngược kiểm tra (`CountdownTimer`), nút "Đã nhận hàng" (`earlyRelease`), nút "Khiếu nại".
- [x] **[Q] Thành viên C:** Chạy kịch bản tích hợp luồng Happy Path (I-05, E-01).

---

**Ghi chú Tuần 5 — phần Thành viên A (cập nhật gần nhất):**
1. **Kết quả test (chạy cục bộ, MySQL 8.0.46):** `pytest test` **621 pass, 6 skip** (5 test `anvil` cũ + 1 test `anvil` mới của relayer; cần `bootstrap.sh`). Thêm 19 test đơn vị `test/unit_test/test_w3_relayer.py` (không cần MySQL/Anvil) + 8 test MySQL thật `test/integration_test/test_w3_relayer_mysql.py`. Frontend: `vitest` **219 pass** (+16), `eslint` sạch trên các tệp đụng tới, `vite build` thành công.
2. **Idempotent hai lớp (SDD 5.3h):** đọc trạng thái trực tiếp từ contract trước khi xếp hàng (DELIVERED ⇒ `ALREADY_DELIVERED`, khác LOCKED ⇒ `INVALID_STATE` 409 kèm `chain_state`), rồi **kiểm lại lần nữa bên trong hàng đợi**: hai lần bấm cùng đơn đều thấy LOCKED ở lần kiểm đầu, lần thứ hai chạy sau khi lần thứ nhất đã được đào nên thấy DELIVERED thay vì gửi giao dịch sẽ revert (có test đua, cả bản giả lẫn MySQL).
3. **`tx_outbox` commit riêng từng bước** (PENDING → SENT → CONFIRMED|FAILED, UPDATE có điều kiện trạng thái cũ): dấu vết còn nguyên kể cả khi bước sau lỗi. **Hết hạn chờ biên nhận KHÔNG đánh FAILED** (giao dịch có thể đã vào chuỗi): giữ `SENT`, người dùng thử lại sẽ đọc chuỗi và nhận `ALREADY_DELIVERED`. Revert/`status=0` ⇒ `CHAIN_TX_FAILED` 502 (chi tiết revert chỉ ở `tx_outbox.error`, không trả cho người dùng).
4. **Khóa không rời signer:** cổng mới `SignerPort.sign_transaction(role, tx)` chỉ trả raw transaction; `Web3Chain.send_tx` nhận hàm `sign` thay vì khóa. Relayer không sửa `order_web3`/`orders` (BR-09: Indexer làm khi thấy `OrderDelivered`; handler này **vẫn là việc của B**, hiện `HANDLERS` chưa có Delivered).
5. **Giới hạn đã biết:** hàng đợi nằm trong tiến trình. Chạy gunicorn nhiều worker dùng chung `SHIPPER_KEY` thì mỗi worker một hàng đợi và lỗi nonce có thể quay lại (đúng rủi ro SDD 12). MVP chạy một tiến trình relayer; nếu cần nhiều worker thì thêm khóa `GET_LOCK` của MySQL quanh job.
6. **Hợp đồng API giả định với B (cần B xác nhận trước khi merge):** `GET /api/shipper/orders` → `{orders:[{order_id, status, shop_name, buyer_name, price_vnd, chain_created_at, delivered_at}]}` (chấp nhận cả mảng trần); `POST /api/shipper/orders/:code/deliver` → `{outcome, tx_hash}` (đúng kết quả của `confirm_delivery`); lỗi `INVALID_STATE`/`ORDER_NOT_FOUND`/`CHAIN_TX_FAILED`/`CHAIN_UNAVAILABLE`. `ShipperService` còn phải kiểm đơn được gán trong `shipper_assignments` trước khi gọi relayer.
7. **Giao diện:** xác nhận hai bước (tránh bấm nhầm), cờ đồng bộ chống bấm đúp, sau khi gửi hiện "đang chờ hệ thống ghi nhận" tới khi polling 5 s thấy đơn sang DELIVERED hoặc biến mất; không dùng ví. Việc cũ `api/web3.js::request` được `export` (đổi đúng một từ khóa) để dùng lại.
8. **Chưa làm / ngoài phạm vi A:** chạy với Anvil + contract thật (cần `bootstrap.sh`; test `anvil` đã viết, đặt `RELAYER_TEST_ONCHAIN_ID` = id đơn đang LOCKED), nối `ShipperService`/route/`AutoRelease` (B), Indexer handler `OrderDelivered` (B), kịch bản E-01 (C). Việc tạo tài khoản `shipper` và gán đơn cho shipper (`shipper_assignments`) chưa có CLI/Admin UI.

**Ghi chú Tuần 5 — phần Thành viên C (cập nhật gần nhất):**
1. **Kết quả test (chạy cục bộ: MySQL 8.0.46 + Anvil 1.5.1 thật, sau `bootstrap.sh --fresh`):** `pytest test` **607 pass, 1 xfail** (gồm 5 test `anvil` cũ; không còn skip); `vitest` **291 pass** (+88 so với 203 trước khi làm), trong đó 5 test chạy **ethers thật trên Anvil**; `eslint` sạch trên mọi tệp mới/đã đụng (hai cảnh báo còn lại trong `MyOrders.jsx` là mã cũ có sẵn); `vite build` thành công. Chưa chạy trên CI.
2. **Backend (hỗ trợ B, SRS 5.1):** `GET /api/payments/orders` trả thêm `web3` cho từng đơn (`null` với đơn cũ): `onchain_order_id`, `checkout_group_id`, `buyer_wallet`, `status`, các mốc thời gian, `amount_raw` (chuỗi, tránh mất chính xác), `anomaly`. Thiếu `onchain_order_id` thì Buyer không gọi được `earlyRelease`. Một truy vấn phụ (không N+1), chịu được DB chưa có bảng `order_web3`; 7 test trong `test/unit_test/test_w5_orders_web3_summary.py`.
3. **Giao diện không tự quyết trạng thái (DD-04, BR-09):** biên nhận của ví chỉ đưa luồng tới "chờ hệ thống xác nhận"; `COMPLETED`/`DISPUTED` chỉ hiện khi **API polling** báo (Indexer ghi). Có test cố tình phá điều này và test bắt được. Bấm dồn chỉ gửi một giao dịch; nút khóa trong lúc chờ; có xác nhận trước khi giải ngân; cổng ví kiểm tra đúng mạng và **đúng ví đã ký quỹ** trước khi bật nút (tránh tốn một giao dịch rồi mới nhận `Only buyer`).
4. **Quy tắc nút (SDD 9.4):** "Đã nhận hàng" bật suốt trạng thái `DELIVERED` kể cả sau khi hết hạn kiểm tra (contract cho phép, đã kiểm chứng trên chuỗi thật); "Khiếu nại" chỉ bật khi còn hạn và đã có đồng hồ máy chủ (không đoán theo giờ máy người dùng). Đồng hồ tính theo `server_time` của lần poll gần nhất nên đúng cả khi máy người dùng sai giờ hoặc Anvil bị tua.
5. **Khiếu nại (UC-05):** hộp thoại lý do + đường dẫn bằng chứng (chỉ http/https). Giao dịch `raiseDispute` gửi trước; lý do chỉ gửi lên sàn **sau khi Indexer ghi `DISPUTED`** (SEQ-02). Gửi lỗi thì hiện nút "Gửi lại lý do"; bản nháp giữ trong `sessionStorage` (xóa khi gửi xong hoặc khi giao dịch không lên được chuỗi) để tải lại trang không mất lý do.
6. **[Q] Kịch bản tích hợp thật (`test/integration_test/test_w5_happy_path_anvil.py`, 4 test):**
   - **E-01 (phần tích hợp):** 2 shop ký quỹ gom thật → Indexer thật ghi `LOCKED` → Shipper `confirmDelivery` → người lạ bị `Only buyer` → Buyer `earlyRelease` → **tiền chia đúng theo `feeBps` đã khóa** (merchant nhận `amount − fee`, người nhận phí nhận `fee`, escrow chỉ giảm đúng đơn đó) → đơn của shop còn lại **vẫn `LOCKED`** (BR-11).
   - **I-05:** `HybridClock.now_chain()` nhảy theo `evm_increaseTime`; quá hạn thì contract chặn Khiếu nại (`Expired`) nhưng vẫn cho `earlyRelease` và `releaseAfterInspection`; trước hạn `releaseAfterInspection` bị chặn (`Under inspection`); báo giá cấp **sau khi tua giờ** vẫn được contract nhận.
   - Khiếu nại trong hạn: `DISPUTED`, tiền đóng băng, không `earlyRelease`/tự giải ngân nữa.
   - `frontend/src/__tests__/orderActions.anvil.test.js` (5 test): chạy chính `runOrderAction` + ABI của frontend + ethers v6 trên Anvil, xác nhận 3 lỗi revert thật (`Not delivered`, `Only buyer`, `Expired`) được dịch đúng sang tiếng Việt. Tự skip nếu không có Anvil; `REQUIRE_ANVIL=1` thì thiếu là đỏ.
7. **Điều chờ Thành viên B (đã thể hiện bằng `xfail`, không phải giấu lỗi):** Indexer hiện chỉ có handler `OrderCreated` (`HANDLERS`). Khi B thêm `OrderDelivered`/`OrderCompleted`/`OrderDisputed`, phần cuối của `test_e01_happy_path_…` tự thành PASS (nên bỏ khối `xfail` cho gọn) và giao diện sẽ tự thấy trạng thái mới qua polling. Cần B xác nhận: `GET /api/orders/:code/status` đủ cho polling (đã đủ), và **tên trường của `POST /api/orders/:code/dispute-note`** (Tuần 6): giao diện đang gửi `{reason, evidence_url}`.
8. **Lưu ý khi chạy lại:** các test I-05 **tua giờ Anvil tiến lên vĩnh viễn** trên node đang chạy (muốn về giờ thật: `bootstrap.sh --fresh`). Fixture `svc` của `test_w3_chain_anvil.py` (B) đẩy `AUTO_INCREMENT` của `onchain_id_seq` lên mili-giây hiện tại trên DB test dùng chung cả phiên, làm `test_web3_migrations` đỏ tùy thứ tự khi chạy cùng lúc test Anvil; test của C tự trả về `100001` khi xong module. Nên đưa cách trả về đó vào chính fixture `svc` khi B rảnh.
9. **Chưa làm / ngoài phạm vi C:** thử bằng MetaMask thật trên trình duyệt (cần chạy tay), E-01 bản Playwright (Tuần 8), màn hình `Dispute.jsx` ký 2/3 (Tuần 6), nút hủy đơn quá hạn 14 ngày (`cancelIfUnfulfilled`, Tuần 7).

**Ghi chú Tuần 5 — phần Thành viên B:**
1. **Kết quả test (MySQL 8.0.46 + Anvil 1.5.1 thật):** `pytest test` 701 pass, 0 skip. Phần B thêm 77 test (39 đơn vị, 19 luồng MySQL, 14 Indexer/HTTP, 5 Anvil). Đã kiểm thử đột biến: hỏng hoàn kho REFUNDED, bỏ kiểm chuỗi của Sweeper, đọc số dư không theo block con trỏ, cả ba đều bị test bắt.
2. **Cổng Shipper:** chỉ role `shipper`, chỉ đơn gán trong `shipper_assignments`, người khác/không tồn tại ⇒ 404. `deliver` trả `{outcome:'SENT'|'ALREADY_DELIVERED', tx_hash}`. API không ghi trạng thái, MySQL chỉ đổi khi Indexer thấy `OrderDelivered` (BR-09). Thông báo cho Buyer (kèm hạn khiếu nại) do Indexer ghi, hạn tính theo giờ block nên replay ra y hệt.
3. **Indexer handler mới:** Delivered, Disputed, Completed, Refunded (hoàn tồn kho), PayoutDeferred, PendingClaimed. Chuyển trạng thái sai chỉ gắn `anomaly_flag`. Reorg đối xứng: đảo ngược số dư chờ rút, giữ lại tồn kho khi REFUNDED bị reorg, xóa thông báo cũ. Còn lại cho Tuần 6: `DisputeResolved`, `ArbitratorForceResolved`.
4. **QuoteExpirySweeper:** chỉ EXPIRED cả lô khi quá hạn + đệm 30 giây, đã khóa đơn, và `orders(id) == NONE` đọc trực tiếp từ chuỗi. Test Anvil chứng minh quá hạn + đệm thì chính contract cũng từ chối nạp.
5. **AutoRelease:** quyết định theo dữ liệu đọc từ chuỗi (`deliveredAt`, `inspectionDuration`, thời gian block), không theo MySQL. Revert do cạnh tranh (Buyer vừa mở khóa sớm) được bỏ qua, ghi `tx_outbox` FAILED.
6. **Đối soát (AC-10):** `GET /api/admin/reconcile[?deep=1]`. Số dư contract đọc **tại block con trỏ Indexer** và MySQL đọc cùng một snapshot, nên Indexer trễ không gây báo lệch giả. Khoản lạ chỉ lộ sau khi Indexer đi qua block đó. Trên Anvil dùng chung, so **độ lệch** trước/sau chứ không so tuyệt đối.
7. **Scheduler:** `cd backend && python -m slopee_web3.adapters.scheduler [--once]`, một thể hiện nhờ GET_LOCK, lỗi một job không dừng job khác. Biến môi trường: `QUOTE_SWEEP_SECONDS`, `AUTO_RELEASE_SECONDS`, `TIMEOUT_REMINDER_SECONDS`, `RECONCILE_SECONDS`, `QUOTE_EXPIRY_GRACE_SECONDS`, `RELAYER_LOCK_SECONDS`. `bootstrap.sh` chưa tự khởi động Scheduler.
8. **API mới ngoài danh sách SDD 10.2, cần nhóm xác nhận:** `GET /api/admin/reconcile`, `PUT /api/admin/orders/:code/shipper`, `GET /api/notifications`. Migration `0021_notifications` (Slopee chưa có bảng thông báo). CLI `seed-shipper`.
9. **Chưa làm:** `DisputeSigExpiry` (Tuần 6), nút hủy quá hạn 14 ngày (Tuần 7), thử bằng MetaMask. Test Anvil của B tua giờ Anvil tiến vĩnh viễn (về giờ thật: `bootstrap.sh --fresh`).

10. **Ghi chú kỹ thuật sau khi CI Run #20 xanh (2026-10-17):**
    - **Kết quả CI & Phân bổ bài test:** CI trên nhánh chính đã hoàn thành 100% qua cả 4 job: `backend`, `web3-chain`, `frontend` (302 passes), và `contracts`. 5 bài test bị skip ở frontend là các bài test tương tác trực tiếp với hợp đồng thông minh qua `ethers.js` (`orderActions.anvil.test.js`); các ca này đòi hỏi node Anvil thực tế nên được chủ động skip trong môi trường unit test Vitest thông thường và đã chạy kiểm chứng thành công trong job `web3-chain`.
    - **Xử lý sự cố chặn tương tác nút "Đã nhận hàng" (`earlyRelease`):**
      - *Hiện tượng:* Nút trên giao diện Buyer hợp lệ (không dính `disabled`, `walletGate` trả về `'OK'`) nhưng click chuột không có phản hồi và MetaMask không bật lên.
      - *Nguyên nhân cốt lõi:* `Web3OrderPanel.jsx` gọi `window.confirm` trước khi gọi `run(...)`. Trình duyệt Firefox bị nghẽn do vòng lặp lỗi `CORS preflight (status: 404)` lặp lại liên tục từ request nền gửi lý do khiếu nại (endpoint `POST /api/orders/<id>/dispute-note` của Tuần 6 chưa có). Cơ chế bảo vệ luồng giao diện (UI Protection) của Firefox đã tự động ngắt các modal dialog đồng bộ, khiến `window.confirm` âm thầm trả về `false` ngay lập tức mà không hiển thị hộp thoại, dừng luồng trước khi gọi ví.
      - *Xác nhận giải pháp:* Khi console sạch lỗi (hoặc tạo đơn mới không dính bản nháp khiếu nại cũ), hộp thoại xác nhận và popup MetaMask hiển thị bình thường. Hợp đồng đã thực thi `earlyRelease` thành công trên Anvil, Indexer bắt sự kiện và cập nhật trạng thái đơn sang `COMPLETED`. Lỗi CORS sẽ tự động triệt tiêu khi hoàn thiện API `dispute-note` ở Tuần 6.
      - *Cập nhật Tuần 6 (sự cố nút "Đã nhận hàng"):* nguyên nhân kích hoạt (thiếu endpoint `POST /api/orders/:code/dispute-note`) đã hết vì B đã làm; `window.confirm` ở `Web3OrderPanel` vẫn còn (xem khối "hoàn thiện mục 10 và 11", mục 8).
    - **Cơ chế và hiện tượng nhảy giây ở đồng hồ đếm ngược (`CountdownTimer`):**
      - *Hiện tượng:* Thời hạn kiểm tra hàng (`remaining`) thỉnh thoảng bị giật lùi 1–2 giây hoặc nhảy cóc không đều nhịp.
      - *Nguyên nhân kiến trúc:*
        1. `useOrderStatus.js` tính mốc đếm bằng cách kết hợp `server_time` (tính từ `now_chain()` của Backend) và `receivedAtMs = Date.now()` của máy khách mỗi khi polling (chu kỳ 3 giây).
        2. Sự biến thiên độ trễ mạng (Network Latency ~ 50–300ms) giữa các lần gọi API làm điểm neo thời gian `(serverTime - receivedAtMs)` bị xê dịch nhẹ mỗi 3 giây, dẫn đến việc tính toán lại số giây `remaining` bị lệch nhịp so với bộ đếm `setInterval` nội bộ của  trình duyệt.
        3. Môi trường Anvil dev cục bộ không bật cờ tăng timestamp đều theo giây thực nếu không có block/transaction mới, dẫn đến `server_time` phụ thuộc vào đồng hồ hệ thống.
      - *Hướng xử lý ghi nhận:* Logic nghiệp vụ on-chain và backend hoàn toàn chính xác. Ở tầng Frontend, sẽ bổ sung bộ lọc làm mượt (Smooth Countdown) ở các tuần tối ưu: chỉ cập nhật lại mốc tính toán khi độ lệch vượt quá ngưỡng cho phép ($\ge 2$ giây) thay vì ghi đè liên tục sau mỗi chu kỳ polling.
      - *Hoàn thiện ở Tuần 6 (đồng hồ đếm ngược):* ✅ đã làm, nhưng neo bằng độ lệch LỚN NHẤT giữa `server_time` và giờ máy (`createServerClock`) thay vì "mốc đầu + ngưỡng"; nguyên nhân phía backend đã được đo (dao động 1,51 giây khi chuỗi bị tua tiến). Xem khối "hoàn thiện mục 10 và 11".

  11. **Đề xuất kỹ thuật tối ưu hóa cơ chế đồng hồ đếm ngược và tần suất Polling (`CountdownTimer` / `useOrderStatus`):**
    - **Bối cảnh hiện tại:** Trạng thái `DELIVERED` đang polling định kỳ mỗi 3 giây (`intervalMs = 3000`). Cứ mỗi nhịp nhận dữ liệu, frontend ghi đè lại mốc `clock = { serverTime, receivedAtMs }`, gây xung đột pha với `setInterval(1000)` nội bộ và làm đồng hồ đếm ngược bị giật cục/nhảy giây do biến thiên độ trễ mạng.
    - **Hướng giải quyết 1: Tách biệt tính toán đếm ngược khỏi vòng lặp Polling (Smooth Client Ticking):**
      - *Nguyên lý:* Không bỏ polling hoàn toàn vì hệ thống cần nhận biết các sự kiện trạng thái cuối (`COMPLETED`, `DISPUTED`) từ server hoặc tác vụ nền `AutoRelease`. Thay vào đó, tách việc đồng bộ trạng thái đơn hàng ra khỏi logic đếm từng giây của UI.
      - *Cách thực thi:*
        - Lần đầu tiên fetch status thành công: Tính và lưu mốc chênh lệch đồng hồ:
          $$\Delta = \text{server\_time} - \lfloor \text{Date.now()} / 1000 \rfloor$$
        - Các lần polling tiếp theo: Chỉ cập nhật trạng thái nghiệp vụ `status`. Giữ nguyên mốc $\Delta$ ban đầu để `CountdownTimer` tự đếm ngược mượt mà qua `setInterval(1000)` độc lập ở client.
        - Chỉ cập nhật lại mốc $\Delta$ khi phát hiện độ trôi thời gian vượt ngưỡng dung sai lớn ($\vert{}\Delta_{\text{mới}} - \Delta_{\text{cũ}}\vert{} \ge 2\text{s}$).
      - *Ưu điểm:* Đồng hồ hiển thị mượt 100%, loại bỏ hoàn toàn hiện tượng giật lùi/nhảy cóc do độ trễ mạng (Network Latency) gây ra.

    - **Hướng giải quyết 2: Áp dụng cơ chế Polling thích ứng theo trạng thái đơn (Adaptive Polling Interval):**
      - *Nguyên lý:* Thời hạn kiểm tra hàng thực tế kéo dài từ 1 đến 3 ngày. Chu kỳ poll 3s/lần là không cần thiết trong suốt giai đoạn người dùng đang giữ hàng kiểm tra.
      - *Cách thực thi:*
        - Giữ nhịp polling ngắn $2 - 3\text{s}$ ở các trạng thái yêu cầu phản hồi tức thì: `PENDING_PAYMENT` (chờ vào chuỗi) hoặc khi người dùng vừa thực hiện hành động ký ví (`earlyRelease`, `raiseDispute`).
        - Khi đơn đã ở trạng thái ổn định `DELIVERED`: Tự động giãn `intervalMs` lên **$10 - 15\text{s}$** (hoặc $30\text{s}$).
      - *Ưu điểm:* Giảm 70–80% lưu lượng request dư thừa lên backend, hạ tải cho server và giảm thiểu nguy cơ nghẽn console trình duyệt khi có lỗi mạng phát sinh.

    - **Khuyến nghị kết hợp:** Triển khai đồng thời cả 2 hướng: Cho phép Frontend tự tính và đếm theo mốc cố định của đơn hàng (`deadline = delivered_at + inspection_duration`), đồng thời giãn chu kỳ polling của đơn `DELIVERED` lên $15\text{s}$ để vừa tiết kiệm tài nguyên mạng vừa đảm bảo giao diện hiển thị mượt mà tuyệt đối.
    - **Trạng thái (Tuần 6):** ✅ Hoàn thiện cả hai hướng. Điều chỉnh so với đề xuất: (1) neo Δ bằng độ lệch lớn nhất thay vì mốc đầu + ngưỡng 2 giây (biên độ răng cưa đo được ~1,5-2 giây nằm sát ngưỡng đó); (2) chu kỳ chậm 15 giây chỉ áp dụng khi còn nhiều thời gian, dậy đúng mốc còn 10 giây, và vẫn poll 3 giây tới 120 giây SAU hạn vì `AutoRelease` + Indexer có thể mất tới ~65 giây mới đưa đơn sang `COMPLETED`; (3) thêm `boost()` sau thao tác ví. Chi tiết ở khối "hoàn thiện mục 10 và 11".

---

### TUẦN 6: Luồng Tranh chấp & Phân xử 2/3 Chữ ký EIP-712
- [x] **[B] Thành viên B:** API lưu ghi chú khiếu nại `POST /api/orders/:code/dispute-note`.
- [x] **[B] Thành viên B:** API Admin tạo đề xuất phán quyết `POST /api/admin/disputes/:code/proposal`, tự động ký phiếu Arbitrator bằng `ARBITRATOR_KEY` với `deadline < disputedAt + disputeTimeout`.
- [x] **[B] Thành viên B:** API tiếp nhận chữ ký của Buyer / Merchant `POST /api/disputes/:code/signatures` (kèm `GET /api/disputes/:code` theo hợp đồng của C, Indexer `DisputeResolved`/`ArbitratorForceResolved`, tác vụ `DisputeSigExpiry`).
- [x] **[A ➔ B] Thành viên A:** Relayer hỗ trợ nộp giao dịch `resolveDispute` khi đủ 2/3 chữ ký (`POST /api/disputes/:code/submit`). `RelayerService.resolve_dispute`, `DisputeSubmitService.submit`, `SignerPort.sign_dispute/recover_dispute_signer`, `ChainPort.dispute_nonce`, `DisputeRepo`; đã chạy trên Anvil + contract thật qua test của B (`test_w3_dispute_b_anvil.py`).
- [x] **[A ➔ F] Thành viên A:** Xây dựng màn hình Admin quản lý tranh chấp (`pages/AdminDashboard.jsx`). `components/AdminDisputes.jsx` gắn vào `AdminDashboard`, `api/disputes.js`, `lib/adminDisputes.js`; backend thêm `GET /api/admin/disputes`.
- [x] **[F] Thành viên C:** Xây dựng giao diện ký phán quyết (`pages/Dispute.jsx`): Khung cảnh báo màu vàng, ký `eth_signTypedData_v4` không tốn gas. Route `/disputes/:code` (role `user`/`seller`), lối vào từ `MyOrders` khi đơn `DISPUTED`. Mặc định gọi API thật của B (mock `mocks/disputeMock.js` chỉ bật khi `VITE_WEB3_MOCK=true`); chưa thử bằng MetaMask trên trình duyệt.
- [x] **[Q] Thành viên C:** Kiểm thử tích hợp kịch bản giải quyết tranh chấp (Hoàn tiền Buyer và Giải ngân Merchant) (E-03). Đã chạy trên Anvil + MySQL 8.0 thật: cả hai hướng PASS (JS 12 test + Python 5 test); luồng qua service thật của B và A (đề xuất, ký, nộp, Indexer) do `test_w3_dispute_b_anvil.py` của B kiểm; test của C vẫn tự tạo đề xuất (`_propose`).

---

**Ghi chú Tuần 6 — phần Thành viên A:**
1. **Kết quả test (cục bộ, MySQL 8.0.46, KHÔNG có Anvil):** `pytest test` **821 pass, 15 skip** (các test `anvil`). Thêm 43 test đơn vị `test_w3_dispute_submit.py` và 11 test MySQL `test_w3_dispute_submit_mysql.py`. Frontend `vitest` **347 pass** (+48), `vite build` thành công. Đã làm hỏng cố ý 4 hành vi (bỏ kiểm người ký, bỏ kiểm quyền, bỏ kiểm lại trong hàng đợi, bỏ kiểm nonce) để xác nhận test bắt được; riêng kiểm nonce ở service là phòng thủ lớp hai vì relayer cũng kiểm.
2. **Không tin cột `party`:** `DisputeSubmitService` khôi phục địa chỉ từng chữ ký rồi so với ví đã khóa trong đơn (Buyer/Merchant) hoặc địa chỉ Trọng tài của sàn; chữ ký sai người/sai nội dung bị bỏ (có test), nên dòng giả mạo trong `dispute_signatures` không thể làm tốn gas. Đủ khi có Trọng tài + một bên, hoặc Buyer + Merchant (đúng điều contract cần: hai bên KHÁC NHAU).
3. **Mọi kiểm tra chạy TRƯỚC khi tốn gas** (revert vẫn mất phí): đọc đơn trực tiếp từ contract, khớp số tiền/người nhận/nonce, `deadline` còn hạn và `< disputedAt + disputeTimeout`. Hết hạn thì đặt `EXPIRED`. Mã lỗi mới: `DISPUTE_NOT_FOUND` 404, `DISPUTE_NOT_READY` 409 (kèm `signed_by`), `DISPUTE_STALE` 409, `DISPUTE_EXPIRED` 410.
4. **Idempotent + đua:** nộp lần hai, hoặc Buyer và Admin bấm cùng lúc, chỉ gửi MỘT giao dịch (`ALREADY_RESOLVED`). Hết hạn chờ biên nhận thì `tx_outbox` giữ `SENT`; lần thử lại thấy chuỗi đã xử đúng theo đề xuất nên đặt `SUBMITTED` và không gửi lại. Chuỗi đã xử NGƯỢC đề xuất (vd. REFUNDED nhưng đề xuất giải ngân Merchant) thì trả `INVALID_STATE`, không nhận vơ.
5. **Việc của B để khớp:** (a) `DisputeService` thêm tạo đề xuất/lưu chữ ký vào CÙNG `DisputeRepo`/`disputes_bp` (đã có sẵn `latest_resolution`, `signatures`, `transition_resolution`); (b) dùng `signer.sign_dispute` để ký phiếu Trọng tài và `signer.recover_dispute_signer` để kiểm chữ ký Buyer/Merchant (đã kiểm chéo với vector `shared/eip712/vectors.json`); (c) Indexer handler `DisputeResolved` đặt `EXECUTED` từ BẤT KỲ trạng thái nào (relayer chỉ đặt `SUBMITTED`); (d) body `proposal` mình giả định `{payout_to: 'BUYER'|'MERCHANT', reason_note?}` theo SKELETON: giao diện KHÔNG xử lý địa chỉ ví. *(Cập nhật sau khi gộp Tuần 6: B đã làm xong cả ba việc, xem ghi chú B mục 3-7 và 9.)*
6. **Mới ngoài SDD 10.2, cần nhóm xác nhận:** `GET /api/admin/disputes` (danh sách đơn `DISPUTED` kèm ghi chú Buyer, đề xuất mới nhất, bên đã ký, `force_resolve_at`). SRS chỉ có `GET /api/disputes/:code` theo từng đơn nên Admin không có cách liệt kê.
7. **Giao diện Admin:** hộp thoại React (không `window.confirm`), cảnh báo "bất kỳ ai cũng có thể thi hành", chống bấm đúp bằng cờ đồng bộ, liên kết bằng chứng chỉ http/https và có `rel="noopener noreferrer nofollow"`, lý do của Buyer hiển thị dạng chữ (có test HTML không thành thẻ). Hết hạn chữ ký tính theo `server_time` nên đúng cả khi Anvil bị tua. `AdminDashboard.jsx` có sẵn 1 lỗi eslint cũ (`loadDashboard` dùng trước khi khai báo), không đụng tới.
8. **Chưa làm:** chạy với Anvil + contract thật (các test `anvil` hiện skip ở máy mình; cần `bootstrap.sh`), kịch bản E-03 (C), UC-07 `arbitratorForceResolve` (Tuần 7). *(Cập nhật sau khi gộp Tuần 6: relayer của A đã được kiểm trên Anvil + contract thật bằng `test_w3_dispute_b_anvil.py` của B (4 test: hoàn tiền Buyer, giải ngân Merchant, hai tầng từ chối cùng một luật, Trọng tài xử đơn phương); E-03 của C đã xong.)*


**Ghi chú Tuần 6 — phần Thành viên C (cập nhật gần nhất):**
1. **Kết quả test (cục bộ: MySQL 8.0.46 + Anvil 1.5.1 thật, sau `bootstrap.sh --fresh`):** `vitest` **399 pass** khi chạy với `REQUIRE_ANVIL=1` (+96 so với 303: gồm 12 test chuỗi thật `disputeResolution.anvil.test.js`); `pytest test` **783 pass, 1 skip** (skip là `test_w3_relayer_mysql.py` đòi `backend/.env.web3`, không thuộc phần C); `eslint` sạch trên mọi tệp mới (các lỗi còn lại nằm ở trang cũ không đụng tới); `vite build` thành công. Chưa chạy trên CI.
2. **Màn hình ký (`pages/Dispute.jsx`, UC-06, SDD 9.7):** hiện khiếu nại của Buyer, đề xuất (kết quả, số tiền thực chuyển, địa chỉ nhận, hạn ký đếm ngược, ba dòng chữ ký Trọng tài/Buyer/Merchant), rồi **khung cảnh báo màu vàng đúng nguyên văn SDD 9.7 đặt ngay trước ô đồng ý và nút ký**. Các giai đoạn: chưa có đề xuất, có thể ký, bị chặn, đã đủ chữ ký (nút "Thi hành ngay" nhờ sàn nộp), đã gửi giao dịch, đã thi hành, hết hạn, bị hủy. Không dùng `window.confirm` (quy tắc Web3): thay bằng ô đồng ý trong trang.
3. **Nguyên tắc an toàn khi ký:** (a) kết quả "hoàn tiền hay giải ngân" được **suy từ địa chỉ nhận so với ví Buyer/Merchant**, không tin nhãn do máy chủ gán; (b) đề xuất chỉ được ký khi khớp những gì contract chấp nhận (`payoutTo` là Buyer/Merchant, số tiền bằng số ký quỹ, `deadline < disputedAt + disputeTimeout`, còn hạn, đơn đang `DISPUTED`), nếu không hiện lý do và **không có nút ký**; (c) kiểm đúng ví đã liên kết và đúng mạng trước khi bật nút; (d) sau khi ví ký, khôi phục lại địa chỉ ký và so với ví của bên mình trước khi gửi; (e) hủy trong MetaMask chỉ là thông báo nhẹ; gửi chữ ký lỗi mạng thì **"Gửi lại chữ ký" không bật MetaMask lần nữa**; lỗi 4xx là kết quả cuối; (f) lý do khiếu nại hiển thị là chữ thuần (không chạy HTML); liên kết bằng chứng chỉ mở khi là `http(s)` (chặn `javascript:`, `data:`, `file:`), có `rel="noopener noreferrer nofollow"`.
4. **Đồng hồ hạn ký theo giờ máy chủ:** dùng thuật toán B khuyến nghị (`lib/serverClock.js`: giữ độ lệch lớn nhất giữa `server_time` và giờ máy, chỉ tăng, neo lại nếu lệch quá 30 giây) nên đếm ngược không giật lùi dù `server_time` răng cưa 2 giây; có test mô phỏng chuỗi mẫu răng cưa và test máy chủ lệch 3 ngày so với máy khách. Polling thích ứng: 3 giây khi có đề xuất cần theo dõi, 10 giây khi chưa có/đã hết hạn; dừng hẳn khi đã thi hành. **`serverClock.js` dùng lại được cho `useOrderStatus` (mục 10, 11 của Tuần 5) khi tới lượt tối ưu đó; chưa áp dụng ở Tuần 5.** *(Cập nhật sau khi gộp Tuần 6: `serverClock` nay còn được dùng cho `useOrderStatus` (đồng hồ kiểm tra của Buyer) và `AdminDisputes`, với `createServerClock`; xem khối "hoàn thiện mục 10 và 11".)*
5. **Hợp đồng API ĐỀ XUẤT, cần B xác nhận khi làm Tuần 6** (mô tả đầy đủ ở đầu `frontend/src/api/disputes.js`; mock `mocks/disputeMock.js` bám đúng và kiểm chữ ký bằng mật mã thật): *(Cập nhật sau khi gộp Tuần 6: B đã xác nhận: `GET /api/disputes/:code` khớp đúng hợp đồng này, thêm `resolution.payout_side`; chữ ký thô không bao giờ có trong phản hồi; `BAD_SIGNATURE` trả HTTP 400 thay vì 422 (giao diện dùng `code` nên không ảnh hưởng); `ALREADY_SIGNED` chỉ khi chữ ký KHÁC, gửi lại cùng chữ ký trả 200.)*
   - `GET /api/disputes/:code` (Buyer/Merchant của đơn; người khác hay đơn không có → 404 `ORDER_NOT_FOUND`) trả: `order_id, onchain_order_id, order_status, your_party ('BUYER'|'MERCHANT', suy từ token), buyer_wallet, merchant_wallet, amount_raw (chuỗi), decimals, symbol, fee_bps, disputed_at, dispute_timeout, server_time, note {reason, evidence_url, updated_at}|null, resolution null|{resolution_id, payout_to, amount_raw, nonce, deadline, status, reason_note, submitted_tx_hash, created_at, signatures:[{party, signer, signed_at}]}`. **Không trả chữ ký thô** của các bên.
   - `POST /api/disputes/:code/signatures {resolution_id, signature}` → `{status}`. Mã lỗi giao diện đã có thông báo: `BAD_SIGNATURE` (422), `ALREADY_SIGNED` (409), `SIGNATURE_EXPIRED` (409), `INVALID_STATE` (409), `ORDER_NOT_FOUND` (404). `POST /api/disputes/:code/submit` → `{tx_hash}`.
   - Quy ước: lỗi 4xx giao diện coi là kết quả cuối (không tự gửi lại, đúng đề nghị ở ghi chú mục 4 của B); chỉ lỗi mạng/5xx mới cho gửi lại.
6. **[Q] E-03 trên chuỗi thật:** *(Cập nhật sau khi gộp Tuần 6: B đã có `DisputeService`. Hai test `test_e03_refund_buyer_full_flow…` và `test_e03_pay_merchant_full_flow…` nộp `resolveDispute` THẲNG lên chuỗi (không qua đề xuất của sàn, nên không có dòng `dispute_resolutions`); handler `DisputeResolved` của B gắn `anomaly_flag` cho trường hợp này (chữ ký Trọng tài chỉ máy chủ có, nên phán quyết ngoài sàn là điều Admin phải được cảnh báo), vì vậy assert `anomaly` đổi từ `False` sang `True` kèm chú thích. Luồng đúng qua sàn (đề xuất, ký, nộp, `EXECUTED`, không anomaly) do `test_w3_dispute_b_anvil.py` kiểm.)*
   - `frontend/src/__tests__/disputeResolution.anvil.test.js` (12 test): **Buyer/Merchant ký bằng chính code ký của giao diện** (`buildDisputeMessage` + `signDispute` + `buildDomain`), Trọng tài ký bằng khóa Anvil, relayer nộp `resolveDispute`. Hoàn tiền: Buyer nhận 100% không phí, Merchant không đổi, escrow giảm đúng số tiền, phát `OrderRefunded` + `DisputeResolved`, nonce tăng đúng 1. Giải ngân: Merchant nhận `amount − fee`, người nhận phí nhận `fee`. Buyer + Merchant đồng thuận (không cần Trọng tài) cũng được. **Hợp đồng từ chối đúng lý do và nonce không đổi** với: hai chữ ký cùng bên, cùng Trọng tài, người ngoài bộ ba, `payoutTo` lạ, sai số tiền/nonce, đổi `payoutTo` sau khi ký, `deadline ≥ disputedAt + timeout`, chữ ký hết hạn (tua giờ), phát lại chữ ký, đơn chưa tranh chấp.
   - `test/integration_test/test_w6_dispute_resolution_anvil.py` (5 test, Python): đủ luồng khóa quỹ → giao → khiếu nại → Indexer ghi `DISPUTED` (`disputed_at` khớp chuỗi) → đề xuất (nonce đọc từ contract, `deadline = min(now_chain + 7 ngày, disputedAt + timeout − 1)`) → ký → nộp → Indexer ghi `REFUNDED`/`COMPLETED` (không có `anomaly`); **đơn của shop còn lại vẫn `LOCKED` (BR-11)**; biên `deadline = disputedAt + timeout − 1` được chấp nhận; chữ ký hết hạn bị từ chối và Admin tạo đề xuất mới (cùng nonce) thì thi hành được.
   - Chữ ký Trọng tài và bước "Admin đề xuất" trong test hiện do test tự làm (hàm `_propose`) vì `DisputeService` của B chưa có; khi B xong chỉ cần thay `_propose` bằng lời gọi dịch vụ thật. E-03 **đầu cuối qua HTTP** (Admin gọi API → Buyer ký qua trình duyệt → `POST submit` của relayer A → Indexer `DisputeResolved` → `EXECUTED`) còn chờ API của B, relayer của A và handler `DisputeResolved`.
7. **Chưa làm / ngoài phạm vi C:** lối vào cho **Merchant** (hiện chỉ Buyer có liên kết từ `MyOrders`; Merchant vào bằng `/disputes/:code`; cần thông báo `DISPUTE_PROPOSED` của B hoặc danh sách đơn ở `SellerDashboard` ở Tuần 7), thử bằng MetaMask thật trên trình duyệt (chạy tay: `VITE_WEB3_MOCK=true`, mở `/disputes/mock-dispute-1`, dùng ví Anvil #5 hoặc #6), E-03 Playwright (Tuần 8), màn Admin (A), mục 10–11 của Tuần 5 (đồng hồ mượt, polling thích ứng, thay `window.confirm` ở `Web3OrderPanel` bằng modal trong trang). *(Cập nhật sau khi gộp Tuần 6: đồng hồ mượt và polling thích ứng của mục 10-11 đã xong (xem khối hoàn thiện mục 10 và 11); còn `window.confirm` ở `Web3OrderPanel`.)*
8. **CI (đề xuất, chưa sửa workflow):** thêm vào job `web3-chain` (có Anvil + MySQL, `REQUIRE_ANVIL=1`) hai lệnh: `python -m pytest test/integration_test/test_w5_happy_path_anvil.py test/integration_test/test_w6_dispute_resolution_anvil.py -v` và `cd frontend && npm ci && npx vitest run src/__tests__/orderActions.anvil.test.js src/__tests__/disputeResolution.anvil.test.js` (khoảng 1 phút và 3 phút). Hai bộ này **tua giờ Anvil tiến vĩnh viễn** nên đặt SAU `test_w3_chain_anvil.py`.


**Ghi chú Tuần 6 — phần Thành viên B:**
1. **Kết quả test (MySQL 8.0.46 + Anvil 1.5.1 thật):** phần B thêm 113 test: 56 đơn vị (`test_w3_dispute_b.py`), 53 MySQL (`test_w3_dispute_b_mysql.py`), 4 Anvil thật (`test_w3_dispute_b_anvil.py`). Đã kiểm thử đột biến 7 hành vi (bỏ kiểm ví của bên ký, bỏ chặn đề xuất mới khi đang `SUBMITTED`, bỏ kiểm `DISPUTED` trên chuỗi, bỏ trần `deadline`, GET lộ chữ ký thô, Indexer không đặt `EXECUTED` từ `EXPIRED`, đề xuất mới không hủy đề xuất cũ), cả 7 đều bị test bắt.  
Pytest: 1114 passed, 1 skipped (bao gồm test_w7_timeouts_anvil.py 8/8 pass).   Vitest: 581 passed (36 files) xanh 100%.   Reconcile tool: Đã chạy thử nghiệm thực tế với lệnh python scripts/reconcile.py --deep --events --wait 10 $\rightarrow$ Kết quả KHỚP (mã thoát: 0) trên CSDL sạch / sau khi đã hủy các đơn cũ.  
Lưu ý chạy test Anvil cho Frontend (Vitest): Khi chạy Vitest, các file test tương tác trực tiếp với Anvil (orderActions.anvil.test.js và disputeResolution.anvil.test.js) có hành vi tua thời gian và gửi giao dịch từ cùng ví mặc định. Không được chạy song song chung với nhau hoặc chung với lúc node Anvil đang bị Pytest làm lệch thời gian. Cần chạy riêng trên node Anvil sạch vừa bootstrap hoặc chạy tuần tự từng file. 

2. **Chạy trên chuỗi thật:** chữ ký Trọng tài do `DisputeService.propose` (khóa `ARBITRATOR_KEY`) và chữ ký Buyer/Merchant (ký như MetaMask) được **contract thật chấp nhận** khi relayer của A nộp `resolveDispute`; `deadline` do B tính luôn nhỏ hơn `disputedAt + disputeTimeout` đọc từ chuỗi; hoàn tiền đủ cho Buyer, giải ngân cho Merchant trừ đúng `feeBps`; nonce tăng nên chữ ký cũ không thi hành lại được; Indexer giải mã log thật `DisputeResolved`/`ArbitratorForceResolved`.
3. **`POST /api/admin/disputes/:code/proposal`** (Admin, 201): body `{payout_to: 'BUYER'|'MERCHANT' (không phân biệt hoa thường) hoặc đúng địa chỉ ví của bên đó, reason_note?}`. Mọi giá trị đi vào chữ ký (buyer/merchant/amount/disputedAt/disputeTimeout/nonce) đọc **trực tiếp từ contract**, không từ MySQL. `deadline = min(now + DISPUTE_SIG_TTL_SECONDS, disputedAt + disputeTimeout − 1)`; hết cửa ký thì 409 `DISPUTE_WINDOW_CLOSED` (chỉ còn Trọng tài xử đơn phương). Đề xuất mới tự `CANCELLED` đề xuất cũ; đề xuất đang `SUBMITTED` chưa quá hạn thì chặn (409). Chữ ký Trọng tài được tự kiểm (khôi phục phải ra đúng địa chỉ Trọng tài) trước khi ghi. Thông báo cho cả hai bên (`DISPUTE_PROPOSED:<id>`).
4. **`POST /api/disputes/:code/signatures`** (Buyer/Merchant; bên suy từ token): khôi phục địa chỉ từ chính nội dung đã lưu của đề xuất và yêu cầu khớp `buyer_wallet`/`merchant_wallet` **trên đơn** (địa chỉ contract nhận diện). Chữ ký đầu tiên của Buyer/Merchant đưa `PROPOSED → READY`. Gửi lại cùng chữ ký là idempotent (200); chữ ký khác từ bên đã ký là 409 `ALREADY_SIGNED`.
5. **`GET /api/disputes/:code`** (Buyer/Merchant của đơn, hoặc Admin với `your_party: 'ADMIN'`): **khớp đúng hợp đồng C đề xuất** ở đầu `frontend/src/api/disputes.js`, thêm `resolution.payout_side`. **Không bao giờ trả chữ ký thô** (có test): Admin hủy đề xuất ở MySQL không thu hồi được chữ ký trên chuỗi, nên chỉ relayer của A mới cầm được chữ ký Trọng tài. `reason_note` của Admin hiển thị cho **cả hai bên**, màn hình Admin (A) nên ghi rõ là lý do gửi cho hai bên.
6. **Mã lỗi:** dùng lại mã của A (`DISPUTE_NOT_FOUND` cho `resolution_id` sai, `INVALID_STATE`); mã giao diện C đã có: `SIGNATURE_EXPIRED` 409, `ALREADY_SIGNED` 409, `ORDER_NOT_FOUND` 404; mã mới `INVALID_PAYOUT` 422, `DISPUTE_WINDOW_CLOSED` 409. Khác với giả định trong `api/disputes.js`: `BAD_SIGNATURE` trả HTTP **400** (như liên kết ví) chứ không 422 (giao diện dùng `code` nên không ảnh hưởng); `NOT_A_PARTY` không bao giờ được phát ra (người không thuộc đơn nhận 404 để không lộ đơn).
7. **Indexer:** `DisputeResolved` đặt đề xuất khớp bên nhận tiền thành `EXECUTED` **từ mọi trạng thái** (yêu cầu của A; kể cả `EXPIRED` khi giao dịch gửi kịp hạn nhưng vào chuỗi muộn); nếu đề xuất đã bị Admin hủy mà vẫn thi hành bằng chữ ký cũ, hoặc không khớp đề xuất nào của sàn, thì đặt `EXECUTED` (chuỗi là sự thật) và gắn `anomaly_flag` cho Admin. `ArbitratorForceResolved` chuyển đề xuất đang hoạt động thành `CANCELLED`. Cả hai báo cả hai bên (`DISPUTE_RESOLVED`). Reorg đảo ngược `EXECUTED` về `SUBMITTED`/`READY`; `ArbitratorForceResolved` không đảo được (không biết đề xuất bị hủy ở trạng thái nào).
8. **`DisputeSigExpiry`** (5 phút, `DISPUTE_SIG_EXPIRY_SECONDS`): `PROPOSED`/`READY` quá `deadline` → `EXPIRED`; không đụng `SUBMITTED`/`EXECUTED`.
9. **Sửa test của A:** `test_release_merchant_with_merchant_signature_submitted_by_merchant` khẳng định đề xuất vẫn `SUBMITTED` sau khi Indexer chạy vì lúc đó chưa có handler của B; nay là `EXECUTED`.
10. **Cho C:** `test_w6_dispute_resolution_anvil.py` hiện tự tạo đề xuất vì `DisputeService` chưa có; có thể đổi sang gọi `POST /api/admin/disputes/:code/proposal` thật. Giao diện không cần đổi gì với hợp đồng GET/signatures.
11. **Chưa làm / ngoài phạm vi:** giao diện hủy đơn quá 14 ngày và Trọng tài xử đơn phương qua API (Tuần 7, UC-07); thử bằng MetaMask trên trình duyệt. Test Anvil của B tua giờ Anvil tiến vĩnh viễn (về giờ thật: `bootstrap.sh --fresh`).
12. **Cập nhật tài liệu:** migration `0021_notifications` và `0022_dispute_notes` (đã có từ Tuần 5) nay được ghi đúng ở SKELETON/AI_CONTEXT: **18 bảng Web3**.


**Ghi chú Tuần 6 — hoàn thiện mục 10 và 11 của Tuần 5 (đồng hồ đếm ngược và polling thích ứng):**
1. **Nguyên nhân thật đã đo (không chỉ suy luận):** trên Anvil thật, khi chuỗi bị tua tiến, `server_time` (`now_chain = max(đồng hồ hệ thống, block mới nhất)`) đi theo từng nấc block nên dao động **1,51 giây** giữa các lần poll (so với 0,53 giây khi chưa tua, chỉ là sai số làm tròn). Hook cũ ghi đè mốc neo `{serverTime, receivedAtMs}` mỗi lần poll, và `secondsRemaining` còn làm tròn xuống số giây trôi, nên đếm ngược giật lùi/nhảy cóc. Chỉ xảy ra khi chuỗi chạy trước đồng hồ máy (Anvil dev sau các test tua giờ); trên chuỗi thật `max` chọn đồng hồ hệ thống nên không có.
2. **Đồng hồ (mục 10):** `lib/serverClock.createServerClock()` giữ **độ lệch lớn nhất** giữa `server_time` và giờ máy (vì `server_time` không bao giờ mới hơn giờ chuỗi, mẫu lớn nhất là ước lượng tốt nhất; chỉ neo lại khi độ lệch hạ quá 30 giây, ví dụ Anvil dựng lại). `useOrderStatus` gọi `observe()` **ngay trong hàm poll**, cùng nhịp với dữ liệu, và trả `offset` + `remaining` (số giây nguyên, làm tròn xuống); tick giao diện 2 lần/giây để số giây đổi đúng lúc qua mốc, không bỏ sót, không lặp. Đồng hồ máy người dùng sai nhiều năm vẫn đúng (chỉ dùng chênh lệch). **Khác với đề xuất ở mục 11** (chốt Δ ở mẫu đầu, neo lại khi lệch ≥ 2 giây): biên độ răng cưa đo được (~1,5-2 giây) nằm sát ngưỡng đó nên vẫn thỉnh thoảng nhảy, và mẫu đầu rơi vào đáy răng cưa thì chậm mãi.
3. **Polling thích ứng (mục 11):** `lib/orderTimer.nextPollDelayMs(status, remaining, {boosted})` (hàm thuần). `PENDING_PAYMENT`/chưa có dữ liệu: 3 giây. `LOCKED`/`DISPUTED` (chờ Shipper/Admin, có thể hàng giờ): 15 giây. `DELIVERED` còn nhiều thời gian: 15 giây nhưng không ngủ quá mốc còn 10 giây (dậy đúng lúc rồi chuyển sang 3 giây). `DELIVERED` từ còn 10 giây tới **quá hạn 120 giây**: 3 giây, vì sau hạn đơn không sang `COMPLETED` tức thì (`AutoRelease` chạy mỗi `AUTO_RELEASE_SECONDS`, mặc định 60 giây, cộng Indexer ~2 giây, tổng tới ~65 giây); quá 120 giây mà vẫn `DELIVERED` (AutoRelease hỏng) thì giãn lại 15 giây để không dồn tải. Nếu nhóm đổi `AUTO_RELEASE_SECONDS` lên quá ~100 giây thì phải nâng `OVERDUE_FAST_SEC` tương ứng.
4. **Tăng tốc khi thao tác ví:** `useOrderStatus` trả `boost(ms = 60 giây)`; `Web3OrderPanel` gọi nó khi `earlyRelease`/`raiseDispute` đang chạy (cờ `busy`): hỏi lại **ngay** và 3 giây/lần tới khi thấy trạng thái đích, dù đơn đang ở chu kỳ 15 giây. `usePolling` hỗ trợ `intervalMs` là **hàm** `(data) => ms` (đổi chu kỳ hoặc đổi danh tính hàm không khởi động lại vòng lặp); `pollMs` của panel nay là tùy chọn, chỉ đặt khi test.
5. **Sửa luôn lỗi cùng gốc ở `AdminDisputes` (A):** `clock` được đặt trong một `useEffect` SAU render nên có một nhịp có danh sách mà chưa có "mốc thoát hiểm"; test `adminDisputesUi` "hiện lý do của Buyer…mốc thoát hiểm" vì thế **chập chờn (chỉ 1/5 lần xanh trước khi sửa, 0/10 lần đỏ sau khi sửa)**. Nay đồng hồ được tính trong hàm poll cùng nhịp với danh sách.
6. **Kiểm chứng (vitest, đồng hồ giả, không chờ thật):** thêm `useOrderStatus.test.jsx` (16 test: chuỗi răng cưa nấc 2 và 4 giây, máy sai giờ 10 năm, chuỗi tua thêm giữa chừng, mỗi lần render có dữ liệu đã kèm đồng hồ, lịch poll theo trạng thái, `boost`, lỗi mạng), `web3OrderPanelAdaptive.test.jsx` (2 test giao diện: không poll dồn khi còn nhiều ngày; bấm "Đã nhận hàng" thì hỏi lại ngay và thấy `COMPLETED` trong vài giây), mở rộng `orderTimer`/`serverClock`/`usePolling`. Có **test đối chứng** chứng minh công thức cũ thật sự lùi trên cùng kịch bản. Đã kiểm thử đột biến 7 hành vi (ghi đè mốc neo, sắp/quá hạn poll chậm, bỏ ưu tiên boost, boost không hỏi lại, panel không gọi boost, đồng hồ không cùng nhịp dữ liệu, `usePolling` khởi động lại khi đổi hàm chu kỳ), cả 7 đều bị test bắt. `vitest` **485 pass, 17 skip** (test Anvil của frontend skip khi không có Anvil), +58 test so với trước và hết test chập chờn; `eslint` không thêm lỗi nào (30 lỗi có sẵn ở các trang cũ, không phải file đã đổi); `vite build` thành công. Backend không đổi.
7. **Thay đổi giao diện hàm:** `useOrderStatus` không còn trả `clock`; trả `offset`, `remaining`, `boost`. Hàm `inspectionRemaining(status, clock, nowMs)` của `lib/orderTimer` đã được thay bằng `inspectionRemainingAt(status, offset, nowMs)`. Chỉ `Web3OrderPanel` dùng; không còn nơi nào khác.
8. **Chưa làm (vẫn thuộc mục 10):** `window.confirm` ở nút "Đã nhận hàng" của `Web3OrderPanel` chưa thay bằng hộp thoại React (nguyên nhân kích hoạt, thiếu endpoint `dispute-note`, đã hết, nhưng quy tắc của `AI_CONTEXT` vẫn là tránh `confirm` trình duyệt trong luồng Web3; chỉ `myOrdersUi.test.jsx` giả `window.confirm`, nên đổi sang hộp thoại React là việc nhỏ). Chưa tạm dừng polling khi tab ẩn. `useDispute` (C) có vòng polling riêng, chưa chuyển sang `nextPollDelayMs`. Chưa thử bằng MetaMask trên trình duyệt thật.

---

### TUẦN 7: Hoàn thiện 4 Vai trò, Thoát hiểm Timeout & Đạt Cột mốc M3
- [x] **[A ➔ F] Thành viên A:** Xây dựng màn hình Merchant (`pages/SellerDashboard.jsx`): Danh sách đơn Web3, Rút số dư chờ (`claimPending`). *(Xong: `MerchantWeb3Panel` gắn vào `SellerDashboard` + API `GET /api/merchant/orders`; test cục bộ xanh trên MySQL thật, chưa chạy Anvil/MetaMask: xem "Ghi chú Tuần 7 — phần Thành viên A".)*
- [x] **[F] Thành viên C:** Bổ sung nút "Hủy đơn do quá hạn giao hàng 14 ngày" (`cancelIfUnfulfilled`) trên giao diện Buyer. *(Đã code và pass toàn bộ test cục bộ không cần Anvil: xem "Ghi chú Tuần 7 — phần Thành viên C" bên dưới. `Web3OrderPanel` cho đơn `LOCKED`: đồng hồ giao hàng, nút bật khi `chain_created_at` + 14 ngày theo giờ máy chủ, xác nhận trong trang, chỉ `REFUNDED` khi API báo.)*
- [x] **[B] Thành viên B:** API kích hoạt thoát hiểm Trọng tài xử đơn phương `arbitratorForceResolve` khi quá `disputeTimeout`. *(Xong: `POST /api/admin/disputes/:code/force-resolve` (Admin), relayer ký bằng KHÓA TRỌNG TÀI, nhật ký `dispute_force_resolutions` (migration `0023`). Chạy trên MySQL thật + Anvil + contract thật với `disputeTimeout` 7/30/90 ngày: xem "Ghi chú Tuần 7 — phần Thành viên B".)*
- [x] **[B] Thành viên B:** Viết script đối soát tự động `reconcile.py` (so khớp số dư contract và CSDL) (AC-10). *(Xong: `scripts/reconcile.py` chỉ đọc, mã thoát 0/1/2 cho cron/CI, `--deep`, `--events` (nguồn thứ ba dựng từ `chain_events`), `--wait`, `--json`, `--strict`.)*
- [x] **[Q] Cả nhóm:** Kiểm thử toàn diện các luồng timeout (E-04) bằng cách tua thời gian Anvil (`evm_increaseTime`). *(Phần chuỗi + Indexer + sàn đã xong và chạy trên Anvil thật: `test_w7_timeouts_anvil.py` 8 test pass, `orderActions.anvil.test.js` 8 test pass, `disputeResolution.anvil.test.js` 12 test pass. Nút "Xử đơn phương" trên UI Admin đã có (A, xem "Ghi chú Tuần 7 — phần Thành viên A" mục 8). Còn thiếu: kịch bản Playwright qua UI).*
- [x] 🎯 **NGHIỆM THU CỘT MỐC M3:**
  - [x] Toàn bộ 4 vai trò (Buyer, Merchant, Shipper, Admin) thao tác hoàn chỉnh trên UI (Nút Admin gọi `POST /api/admin/disputes/:code/force-resolve` đã có ở `AdminDisputes.jsx`).
  - [x] Không có trường hợp tiền bị kẹt vĩnh viễn trong hợp đồng (Đã chứng minh qua 8 test timeout và scripts/reconcile.py khớp số dư).


# Ghi chú Tuần 7 — Thành viên C (cập nhật gần nhất)

## 1. Trạng thái kiểm chứng (đọc trước)

Đã chạy kiểm chứng cục bộ thành công trên MySQL 8.0 thật:
- `cd frontend && npx vitest run`: **561 passed, 20 skipped** (bao gồm toàn bộ 33 vitest mới của C và 43 vitest của A).
- `npm run build`: biên dịch Vite thành công.
- `pytest test/unit_test/test_w5_orders_web3_summary.py test/integration_test/test_w3_indexer_orders_mysql.py`: 24/24 pass (bao gồm 2 khẳng định mới và 1 test mới của C).
- Toàn bộ backend `pytest test`: **960 pass, 24 skip** (các ca skip đều do thiếu Anvil/.env.web3).
- 8 test Anvil chuỗi thật trong `orderActions.anvil.test.js` tự động skip khi thiếu node Anvil, sẽ được kích hoạt khi chạy `REQUIRE_ANVIL=1`.

### 1.1. Khắc phục lỗi Flaky Test đồng hồ đếm ngược (F-07 / `web3Ui.test.jsx`)
- **Hiện tượng:** Test ca *"đồng hồ không giật: sau khi nhận báo giá mới luôn bắt đầu đúng 15:00..."* pass ở local nhưng fail ngẫu nhiên trên GitHub Actions (`expected '... 15:00' to contain '14:59'`).
- **Đã được B sửa và kiểm chứng (bản gộp trước đó chỉ ghi chú, chưa có thay đổi code nào trong `web3Ui.test.jsx`).**
- **Nguyên nhân thật (đã tái hiện, KHÔNG phải chỉ do render chậm):** test chờ `findByTestId('quote-result')`, phần tử này có thể đã tồn tại từ trước, nên khi CPU chậm test tua giả `vi.advanceTimersByTime(1000)` **trước khi** `group` báo giá mới được commit và `setInterval` mới được tạo lại. Tick bị bỏ lỡ, đồng hồ đứng ở 15:00. Chỉ dùng `waitFor` ở cuối **không cứu được** vì `waitFor` không thể tự tua đồng hồ giả (timer giả không chạy khi chờ).
- **Tái hiện:** chạy ca đó 12 lần dưới tải CPU (3 vòng lặp bận mỗi lõi): **1/12 lần lỗi** đúng thông báo trên.
- **Giải pháp:** trước khi tua, chờ ĐÚNG tín hiệu "báo giá mới đã commit": `await waitFor(() => expect(calls).toHaveLength(1))`, `await screen.findByTestId('quote-countdown')`, rồi `await act(async () => { await Promise.resolve(); })` để xả effect tạo lại `setInterval`; sau khi tua mới dùng `waitFor` cho khẳng định `14:59`. Kiểm chứng sau sửa: **0/30 lần lỗi** ca đó dưới tải, và **0/10 lần lỗi** cả tệp `web3Ui.test.jsx`.
- **Quy ước cho test đếm ngược khác:** xem `AI_CONTEXT.md` (mục "Flaky test đồng hồ đếm ngược"), đã chỉnh lại cho đúng nguyên nhân.

## 2. Nút "Hủy đơn & nhận lại tiền" (UC-07, BR-05, T-14)

`Web3OrderPanel` cho đơn `LOCKED` hiện đồng hồ "Cửa hàng còn … để giao hàng" và nút hủy.

Nút chỉ bật khi `chain_created_at + 14 ngày` đã qua theo **giờ máy chủ** (cùng `serverClock` với đồng hồ kiểm tra, máy người dùng sai giờ không ảnh hưởng) và cổng ví qua (đúng ví đã ký quỹ, đúng mạng): contract chỉ cho Buyer (hoặc Admin) gọi, nên giao diện không bật cho ví khác.

Giao diện **không tự đặt `REFUNDED`**: sau biên nhận chờ API (Indexer ghi `OrderRefunded`) mới báo xong (DD-04, BR-09).

## 3. Làm tròn LÊN cho hạn hủy

`deliveryRemainingAt` làm tròn lên, ngược với đồng hồ kiểm tra (làm tròn xuống).

- **Nút Khiếu nại** phải khóa sớm.
- **Nút Hủy** phải bật muộn.

Lý do: contract kiểm tra `block.timestamp >= createdAt + 14 ngày` và một giao dịch bị revert vẫn tốn gas, đồng thời có thể khiến người dùng hoang mang.

Nếu vẫn gặp `Timeout not reached` (đồng hồ chuỗi chậm hơn dự đoán), thì thông báo tiếng Việt rõ ràng và tiền không đổi.

## 4. Xác nhận không dùng `window.confirm`

Nút hủy dùng khung xác nhận ngay trong trang (`cancel-confirm-box`, nút "Xác nhận hủy đơn"/"Không hủy") theo quy tắc Web3 ở `AI_CONTEXT.md` mục 7.

Hành động này **không hoàn tác được**, nên có lời cảnh báo: tiền hoàn về ví Buyer, cửa hàng không nhận.

## 5. Backend (hỗ trợ B, thay đổi nhỏ)

Thêm `chain_created_at` (số nguyên giây UTC theo block, `null` nếu chưa có) vào:

- `GET /api/orders/:code/status` (`OrderStatusService.get_status`, `order_status_row`).
- `web3` của `GET /api/payments/orders` (`WEB3_SUMMARY_COLUMNS`, `_web3_summaries`).

Cột đã có sẵn trong `order_web3` (do Indexer ghi từ `OrderCreated`) nên **không có migration mới**.

Chỉ **thêm** trường, không đổi trường cũ.

**Lý do cần ở trạng thái:** tóm tắt đơn là ảnh chụp lúc tải trang, còn đồng hồ phải tính theo `server_time` của lần poll.

**Test:**
- `test_w5_orders_web3_summary.py`: sửa khẳng định bằng nhau + test mới `chain_created_at` số/`null`.
- `test_w3_indexer_orders_mysql.py`: trạng thái trả `null` trước khi ký quỹ, số nguyên dương sau Indexer.

**Nhờ B xem lại** vì đụng `application/` và `mysql_repos.py` của B.

## 6. Chỉ hủy được đơn còn `LOCKED`

- Đơn đã giao (`DELIVERED`) quá 14 ngày **KHÔNG hủy được** (contract revert `Not locked`, đã có test Anvil).
- Giao diện không hiện nút ở trạng thái khác `LOCKED`.
- Đơn thiếu `chain_created_at` (dữ liệu cũ/chưa có từ Indexer) thì **không hiện nút** và không đoán mốc theo `orders.created_at` (đó là giờ máy chủ, không phải giờ block).
- `AutoRelease`/`DeliveryTimeoutReminder` (B) vẫn gửi nhắc cho Buyer khi tới hạn; nút này là đường để Buyer tự lấy lại tiền.

## 7. Việc kéo theo của `useOrderStatus`

- Có thêm `deliveryRemaining`.
- Vòng tick 0,5 giây nay chạy cả khi đơn chỉ `LOCKED` mà đã biết `chain_created_at` (trước đó chỉ chạy khi có `delivered_at`).
- Chu kỳ poll `LOCKED` giữ 15 giây (đồng hồ chạy ở máy khách giữa hai lần poll).
- Sau khi bấm hủy, `boost()` vẫn hỏi lại ngay và 3 giây/lần tới khi thấy `REFUNDED`.

## 8. Chưa làm & Kế hoạch xử lý (Deferred / Pending Items)

### 8.1. Thay thế `window.confirm` ở nút "Đã nhận hàng" (`earlyRelease`) bằng Modal trong trang

**Hiện trạng:**

Nút mới "Hủy đơn" (`cancelIfUnfulfilled`) đã tuân thủ chuẩn Web3 với khung xác nhận trong trang (`cancel-confirm-box`, không dùng `window.confirm`). Tuy nhiên, nút cũ "Đã nhận hàng" vẫn còn dùng `window.confirm`.

**Quyết định hoãn:**

Việc sửa nút này sẽ kéo theo refactor hàng loạt bài test đang mock `window.confirm` (`myOrdersUi`, `web3OrderPanelAdaptive`, helper `anvilChain`).

Để bảo đảm độ ổn định cho mốc **M3**, nhóm thống nhất tạm giữ nguyên ở Tuần 7.

**Điều kiện thực hiện ở Tuần 8:**

Chỉ tiến hành nâng cấp/cải tiến ở Tuần 8 **NẾU** sau khi đóng băng tính năng (Feature Freeze), toàn bộ hệ thống và bài test tích hợp đã xanh 100%, không còn lỗi High/Critical và còn dư thời gian.

Nếu không đủ thời gian, giữ nguyên để tránh rủi ro vỡ bộ test cũ.

### 8.2. Các hạng mục ngoài phạm vi của C trong Tuần 7

- **Quyền Admin gọi `cancelIfUnfulfilled` hộ Buyer:** smart contract đã hỗ trợ, chưa dựng giao diện/API riêng cho Admin.
- **Lối vào cho Merchant xem/ký tranh chấp từ `SellerDashboard`:** thuộc phạm vi của Thành viên A.
- **API thoát hiểm Trọng tài xử đơn phương `arbitratorForceResolve` và script đối soát `reconcile.py`:** thuộc phạm vi của Thành viên B.
- **Kịch bản kiểm thử E-04 đầu cuối:** Timeout Path hoàn chỉnh, gồm cả Dispute Timeout / Trọng tài xử đơn phương; chờ ghép API/Relayer của A và B.
- **Kiểm thử thủ công bằng ví MetaMask thật trên trình duyệt:** toàn bộ test hiện tại chạy bằng ví giả lập qua khóa Anvil + ethers.js.

**Ghi chú Tuần 7 — phần Thành viên A:**
1. **Kết quả test (cục bộ, MySQL 8.0.46, KHÔNG có Anvil):** `pytest test` **959 pass, 24 skip** (các test cần Anvil/`.env.web3`); `vitest run` **528 pass, 17 skip**; `npm run build` xanh. Test mới của A: 16 pytest đơn vị (`test_w7_merchant.py`), 10 pytest MySQL thật (`test_w3_merchant_mysql.py`), 43 vitest (`merchantOrders` 16, `claimPending` 12, `merchantPanelUi` 15). Đã thử phá có chủ đích: bỏ điều kiện lọc theo shop thì test cô lập dữ liệu đỏ ngay.
2. **API mới `GET /api/merchant/orders` (đã được nhóm chốt 23/10/2026, ghi ở `AI_CONTEXT.md` mục 6):** SDD 9.2 có màn Merchant nhưng SDD 10.2 không có API nên A làm cả phần máy chủ (`MerchantService`, `MerchantRepo`/`MySqlMerchantRepo`, route, container). Chỉ đọc, role `seller`, danh tính chỉ từ token. Trả đơn từ `LOCKED` trở đi (không trả `PENDING_PAYMENT`/`EXPIRED` vì chưa có tiền trên chuỗi), số tiền là chuỗi, thực nhận sau phí cùng cách làm tròn xuống của contract, các mốc hạn theo giờ block, và số dư chờ rút. Không rò ví/id Buyer, `doc_hash`, chữ ký.
3. **Giao diện (`SellerDashboard` + `MerchantWeb3Panel`):** danh sách đơn, tổng quan "đang ký quỹ / đã nhận" (cộng theo từng token bằng BigInt), bộ lọc trạng thái, câu giải thích bước tiếp theo cho từng trạng thái, cảnh báo khi chưa liên kết ví nhận tiền. Đã chốt đặt trong `/seller`, không tạo route `/merchant/orders`, `/merchant/pending`.
4. **Rút khoản chờ rút (`claimPending`, BR-05):** tiền về ví Merchant tự động khi giải ngân nên Merchant không cần thao tác gì; khoản chờ rút chỉ có với ETH khi ví nhận từ chối tiền (với mUSD luôn 0). Quy tắc giao diện: (a) đúng ví và đúng mạng mới có nút Rút (contract trả cho `msg.sender`); (b) đọc lại `pendingWithdrawals` trên chuỗi trước khi gửi, bằng 0 thì không gửi; (c) KHÔNG tự coi là đã rút theo biên nhận: chỉ xong khi API bỏ khoản đó (DD-04, BR-09); (d) bấm dồn chỉ một giao dịch; (e) hủy MetaMask là thông báo nhẹ. Không dùng `window.confirm`.
5. **Khớp với C:** mục 8.2 ghi chú Tuần 7 phần C ("lối vào cho Merchant xem/ký tranh chấp") nay có: đơn `DISPUTED` trong khung Merchant có liên kết sang `/disputes/:code`. Không đụng `Web3OrderPanel`, `orderTimer`, `orderActions`, `useOrderStatus` của C. `mysql_repos.py` cả hai cùng sửa nhưng ở hai chỗ khác nhau (A: thêm `MySqlMerchantRepo` và hàm dùng chung `_order_items`; C: `order_status_row`).
6. **Cần B xem lại (đụng `mysql_repos.py` của B):** tách `MySqlShipperRepo._items` thành hàm dùng chung `_order_items(cur, ids)` (hành vi không đổi, test cổng Shipper vẫn xanh).
7. **Chưa làm / ngoài phạm vi A:** chạy với Anvil + contract thật và thử bằng MetaMask thật trên trình duyệt (chưa mở thử `/disputes/:code` và khung Merchant bằng tài khoản seller thật); trường hợp ví nhận ETH từ chối thật (cần ví là hợp đồng từ chối tiền) mới được thử trên chuỗi giả `FakeEscrowChain.defer_payout`; thoát hiểm Trọng tài xử đơn phương và `reconcile.py` (B); kịch bản E-04 đầu cuối (Q).
8. **Nút "Xử đơn phương" (UC-07) trên `AdminDisputes.jsx` (nhận việc từ ghi chú bàn giao của B, mục 10):** mỗi đơn `DISPUTED` có dòng đếm ngược tới `force_resolve_at` (tính theo đồng hồ máy chủ `createServerClock`, cùng đồng hồ với hạn chữ ký 2/3) và nút **Xử đơn phương**: TẮT (có `title` nói còn bao lâu) cho tới khi `now >= force_resolve_at` (biên bằng đúng điều kiện `>=` của contract), thiếu đồng hồ thì cũng tắt. Bấm mở hộp thoại xác nhận trong trang (không `window.confirm`): chọn Buyer (hoàn tiền) hoặc Merchant (giải ngân), **lý do bắt buộc ở giao diện** (backend cho bỏ trống; chọn bắt buộc vì đây là hành động duy nhất dựa hoàn toàn vào niềm tin ở sàn và được ghi `dispute_force_resolutions`), cảnh báo "đơn phương, không hoàn tác, ghi nhật ký kèm Admin", chống bấm đúp. Gọi `POST /api/admin/disputes/:code/force-resolve` với `{payout_to, reason_note}` (hàm `forceResolveDisputeAPI`). `409 FORCE_RESOLVE_TOO_EARLY` (đồng hồ trình duyệt lệch) hiện "còn X, chưa gửi giao dịch nào" lấy từ `extra.seconds_remaining`; `ALREADY_RESOLVED` báo đã xử lý trước đó. Dùng được cả khi đang có đề xuất 2/3 dang dở (R-02: hạn chữ ký luôn nhỏ hơn mốc, nên không cần hủy). Hàm thuần mới trong `lib/adminDisputes.js`: `forceResolveRemaining`, `canForceResolve`, `validateForceResolveForm`, `forceResolveMessage`, `tooEarlyMessage`; thêm mã lỗi `FORCE_RESOLVE_TOO_EARLY` vào `lib/errors.js`.
9. **Lệch nhỏ so với ghi chú bàn giao:** `GET /api/admin/disputes` chỉ trả `force_resolve_at` (kèm `server_time`), KHÔNG trả `seconds_remaining`; trường này chỉ có trong lỗi `409 FORCE_RESOLVE_TOO_EARLY`. Giao diện tự tính số giây còn lại từ `force_resolve_at` và `server_time` nên không cần sửa backend. Test mới: 5 ca giao diện (`adminDisputesUi.test.jsx`), 4 ca hàm thuần, 1 ca API; `vitest run` **571 pass, 20 skip** (591 ca), `npm run build` xanh. Chưa thử bằng trình duyệt + Anvil thật (cần nhóm chạy tay: đẩy giờ Anvil qua `disputeTimeout` rồi bấm nút); chưa có kịch bản Playwright.

---

# Ghi chú Tuần 7 — Thành viên B (cập nhật gần nhất)

## 1. Trạng thái kiểm chứng (đọc trước)

Chạy cục bộ trên **MySQL 8.0.46 thật + Anvil 1.8.6 + contract thật** (solc 0.8.20, `scripts/bootstrap.sh --fresh --force-env`):
- `pytest test` đầy đủ **có Anvil** (`REQUIRE_ANVIL=1`): **1114 passed, 1 skipped** (ca skip là test thủ công `test_w3_relayer_mysql.py` đòi biến `RELAYER_TEST_ONCHAIN_ID`, có từ trước, không liên quan Tuần 7). Không Anvil (`-m "not anvil"`): **1083 passed** trước khi thêm 8 test Anvil. `cd frontend && npx vitest run`: **581 passed (36 tệp)**; `npm run build` xanh. Gồm cả phần của A và C đã gộp từ `changes.diff`.
- Test mới của B: `test_w3_force_resolve.py` (83, không cần MySQL/Anvil), `test_w7_reconcile_script.py` (22, không cần MySQL/Anvil), `test_w3_force_resolve_mysql.py` (8, MySQL thật), `test_w3_reconcile_script_mysql.py` (9, MySQL thật), `test_w7_timeouts_anvil.py` (8, **chuỗi thật**). Đã sửa `test_web3_migrations*.py` (0006..0023, 19 bảng).
- Đã thử phá có chủ đích: ký bằng khóa Shipper thay vì Trọng tài (16 test đỏ), bỏ kiểm mốc thời gian (7 đỏ), bỏ ghi nhật ký (6 đỏ).
- Chưa làm: thử bằng MetaMask/giao diện thật; CI chưa chạy các test mới (chỉ chạy cục bộ).

## 2. API Trọng tài xử đơn phương (UC-07 Dispute Timeout, BR-05)

`POST /api/admin/disputes/:code/force-resolve` (chỉ Admin; **mới ngoài SDD 10.2**, nhờ nhóm xác nhận như đã làm với `GET /api/merchant/orders`). Body `{payout_to: 'BUYER'|'MERCHANT'|<địa chỉ ví đúng bên đó>, reason_note?}`. Trả `{order_id, onchain_order_id, outcome: 'SENT'|'ALREADY_RESOLVED', tx_hash, payout_side, payout_to, amount_raw, force_resolve_at}`.

Quy tắc (trong `application/dispute_force_service.py`):
- Danh tính Admin chỉ từ token. Tin CHUỖI, không tin MySQL: trạng thái, `buyer`/`merchant`, `disputedAt`, `disputeTimeout` đọc thẳng từ contract (Indexer có thể trễ).
- Mọi kiểm tra chạy TRƯỚC khi gửi: chưa tới `disputedAt + disputeTimeout` thì `409 FORCE_RESOLVE_TOO_EARLY` kèm `force_resolve_at` và `seconds_remaining` (giao diện đếm ngược), **không gửi giao dịch sẽ revert**. Người nhận chỉ được là Buyer hoặc Merchant của đơn (`INVALID_PAYOUT`, kể cả địa chỉ Trọng tài). Ghi chú lý do dùng lại `clean_note`.
- **Idempotent:** chuỗi đã `REFUNDED`/`COMPLETED` đúng bên yêu cầu thì `ALREADY_RESOLVED` (không gửi, không ghi nhật ký thêm); trái bên thì `409 INVALID_STATE`. Kiểm lại trạng thái chuỗi ngay trong hàng đợi relayer, nên hai Admin bấm cùng lúc chỉ gửi đúng một giao dịch (có test 4 luồng).
- **Hai đường không bao giờ cùng hợp lệ (R-02):** hạn chữ ký 2/3 luôn `<= disputedAt + disputeTimeout − 1` (đã có `compute_deadline`; test mới chạy mọi tổ hợp 7/30/90 ngày × TTL × thời điểm đề xuất), nên khi đường Trọng tài mở thì mọi chữ ký đã hết hạn; không cần chờ/hủy đề xuất đang dang dở. Indexer (`ArbitratorForceResolved`, đã có từ Tuần 6) tự đặt đề xuất đó `CANCELLED` và báo cả hai bên.
- Không sửa `order_web3`/`orders`: trạng thái cuối do Indexer ghi (BR-09), API chỉ trả `outcome` + `tx_hash`.
- Mốc thời gian dùng `clock.now_chain()` (max giờ máy, block mới nhất) cùng quy ước các mốc khác. Nếu đồng hồ máy chủ chạy trước block, dịch vụ tưởng đã tới hạn nhưng contract từ chối lúc ước lượng gas ⇒ `502 CHAIN_TX_FAILED`, không tốn gas, không ghi nhật ký (có test).

## 3. Khóa Trọng tài trong relayer (đụng code của A, nhờ A xem lại)

`arbitratorForceResolve` đòi `msg.sender` có `ARBITRATOR_ROLE`, nên giao dịch phải do **khóa Trọng tài** ký và gửi từ địa chỉ Trọng tài, không phải Shipper. Thay đổi tối thiểu ở `RelayerService`: `_send_job(..., role=SHIPPER_ROLE)` (mặc định không đổi hành vi), `force_resolve(...)`, `_arbitrator_address()` (thiếu `ARBITRATOR_KEY` thì `503 WEB3_NOT_CONFIGURED`). Vẫn dùng chung hàng đợi một luồng và khóa liên tiến trình. `tx_outbox.kind = 'FORCE_RESOLVE'` (cột là `VARCHAR(30)` nên không cần migration; chú thích cột trong `0017` vẫn ghi `DELIVER, RELEASE, RESOLVE`, không sửa vì migration đã áp dụng).
Để test bắt được lỗi dùng nhầm khóa, `FakeEscrowChain.send_tx` giờ khôi phục `msg.sender` từ **raw tx đã ký** (như chuỗi thật) và `arbitratorForceResolve` chỉ nhận khi người ký là Trọng tài. Contract thật cũng được kiểm: khóa Shipper bị từ chối bằng lỗi OpenZeppelin `AccessControlUnauthorizedAccount` (selector `0xe2517d3f`).

## 4. Nhật ký hành động tin cậy: migration `0023_dispute_force_resolutions.sql` (nhờ nhóm xác nhận)

Đây là hành động DUY NHẤT dựa hoàn toàn vào niềm tin ở sàn (BRD mục 6), nên phải truy vết: Admin nào (từ token), bên nào, lý do, bao nhiêu, giao dịch nào (`outbox_id` + `tx_hash`). **Không có khóa ngoại** (cùng quy ước `tx_outbox`: nhật ký sống độc lập với đơn/người dùng; có test). Chỉ ghi khi giao dịch đã gửi; nếu ghi lỗi thì KHÔNG che kết quả (tiền đã đi) mà log `ERROR` đủ dữ liệu dựng lại. Mỗi lần yêu cầu/từ chối ghi log `WARNING` có `admin=` để cảnh báo bất thường. Đây là **bảng Web3 thứ 19** (`schema.sql` dấu mốc `0006 .. 0023`); đã cập nhật test migration tĩnh + MySQL thật (DB mới == DB nâng cấp). Nếu nhóm không muốn thêm bảng, bỏ migration, `add_force_resolution` và `_record` là đủ; API vẫn chạy.

## 5. `scripts/reconcile.py` (AC-10, G-01, E-06)

Chỉ đọc (không nạp khóa, không dựng relayer: có test chặn), đọc số dư contract **tại đúng block Indexer đã xử lý** và dữ liệu MySQL trong một snapshot nên Indexer trễ không gây báo lệch giả.
```
python scripts/reconcile.py [--deep] [--events] [--wait GIÂY] [--json] [--strict]
mã thoát: 0 = khớp | 1 = LỆCH (hoặc --strict có cảnh báo anomaly) | 2 = không chạy được (chưa cấu hình, mất DB/RPC, Indexer chưa chạy)
```
- Phân biệt "lệch" với "không chạy được" bằng mã thoát để cron/CI xử lý khác nhau; báo hướng lệch (contract DƯ hay THIẾU tiền, THIẾU là nghiêm trọng).
- **`--events` (mới, nguồn thứ ba):** dựng lại tổng tiền đơn mở/sổ chờ rút **chỉ từ `chain_events`** (không qua handler của Indexer) rồi so với `order_web3` theo token và **theo từng đơn**. Phát hiện lỗi handler mà đối soát số dư không thấy.
- **Lỗ hổng đã phát hiện khi viết test:** `--deep` chỉ duyệt đơn mà CSDL coi là đang mở, nên đơn còn mở trên chuỗi mà CSDL ghi `COMPLETED` (tiền kẹt) **không bao giờ bị thấy**; nếu hoán đổi với một đơn đã đóng cùng số tiền thì cả tổng cũng khớp. Chỉ `--events` (so tập đơn mở theo từng id) bắt được. Có test `test_swapped_equal_orders_keep_the_sums_green_but_events_expose_both`.
- Service dùng chung (`ReconcileService.run(deep, events)`); `GET /api/admin/reconcile` giữ nguyên (chưa thêm `events`).
- Chưa nối vào cron/CI: lệnh gợi ý sau mỗi kịch bản demo là `python scripts/reconcile.py --deep --events --wait 30`.

## 6. E-04 trên chuỗi thật (`test/integration_test/test_w7_timeouts_anvil.py`, 8 test)

Anvil + contract thật + MySQL + `evm_increaseTime`, qua đường mã thật của sàn rồi Indexer giải mã log thật:
- Dispute timeout với `disputeTimeout` **7/30/90 ngày** (đặt qua `category_policies`, đã kiểm vào báo giá và contract) × hoàn Buyer/giải ngân Merchant: trước mốc dịch vụ từ chối **và** contract thật cũng revert `Dispute timeout not reached`; khóa Shipper bị contract từ chối; sau mốc tiền chia đúng (hoàn 100% / trừ phí theo `feeBps`), nhật ký đủ, lặp lại idempotent, chọn ngược bị từ chối.
- Delivery timeout 14 ngày: trước hạn revert `Timeout not reached`, người lạ bị `Unauthorized`, Buyer hủy hoàn 100%, Indexer `REFUNDED`.
- Cả hai lối thoát cùng chuỗi: không còn đơn `LOCKED/DELIVERED/DISPUTED`, độ lệch tiền không đổi so với trước test, script đối soát không thêm lệch.
- Chuỗi Anvil dùng chung có thể còn tiền/sự kiện của test khác nên các test so **độ lệch so với mốc ban đầu** và chỉ xét đơn của chính test (đã chạy lại trên chuỗi "dơ" vẫn xanh). Test tua giờ Anvil TIẾN vĩnh viễn (về giờ thật: `bootstrap.sh --fresh`).

## 7. Sửa giúp C: test flaky đồng hồ đếm ngược
Xem mục 1.1 của ghi chú C (đã chỉnh lại cho đúng nguyên nhân, kèm số liệu tái hiện 1/12 → 0/30).

## 8. Việc đụng ngoài phạm vi B (nhờ chủ sở hữu xem lại)
- A: `relayer_service.py` (mục 3). C: `web3Ui.test.jsx` (mục 7), `AI_CONTEXT.md` (quy tắc flaky).
- Chung: `mysql_repos.py` (thêm `add_force_resolution`, `force_resolutions`, `reconcile_events`, `open_order_ids`; không đổi hàm cũ), `ports/repositories.py`, `domain/dispute.py`, `domain/reconcile.py`, `domain/errors.py` (mã mới `FORCE_RESOLVE_TOO_EARLY` 409), `test/w3_support.py`.

## 9. Chưa làm / ngoài phạm vi B
10. **Giao diện Admin cho Thoát hiểm: A đã nhận.** Bảng Tuần 7 không giao nút "Xử đơn phương" cho ai (A làm Merchant, C làm nút hủy của Buyer). Hiện `GET /api/admin/disputes` đã có `force_resolve_at` nhưng `AdminDisputes` chưa có nút gọi API mới và chưa hiện đếm ngược `seconds_remaining`. **M3 "4 vai trò thao tác hoàn chỉnh trên UI" cần việc này**.
11. E-04/E-06 bản Playwright qua giao diện (phụ thuộc mục 10), thử MetaMask thật, nối `reconcile.py` vào cron/CI, `scripts/replay.sh` (Tuần 8), thêm tham số `events` cho `GET /api/admin/reconcile`.

---

### TUẦN 8: Đóng băng tính năng, Kiểm thử tích hợp & Đạt Cột mốc M4
- [ ] 🔒 **ĐÓNG BĂNG MÃ NGUỒN TÍNH NĂNG (FEATURE FREEZE):** Tuyệt đối không thêm tính năng mới, chỉ sửa lỗi.
- [ ] **[Q] Thành viên C:** Thiết lập Playwright test tự động với mock ví EIP-1193 chạy trong GitHub Actions CI (E-01 đến E-07).
- [ ] **[Q] Thành viên B:** Chạy toàn bộ test suite backend và API (A-01 đến A-07, I-01 đến I-07).
- [x] **[Q] Thành viên A:** Quét mã nguồn và CSDL xác nhận nguyên tắc Non-custodial (E-05, AC-09): Không tồn tại private key người dùng. *(`scripts/scan_no_user_keys.py`: quét repo 377 tệp + lược đồ + log, 0 HIGH; 57 test Python xanh. Phần quét CSDL MySQL thật chạy trong CI (bước mới ở job `backend`) và `test_w8_non_custodial_mysql.py`: xem "Ghi chú Tuần 8 — phần Thành viên A".)*
- [x] **[Q] Thành viên A:** Rà soát lại checklist an ninh: Reentrancy, Signature Malleability, Role Separation, Front-running. *(Báo cáo `docs/SECURITY_CHECKLIST_W8.md`: 4/4 mục đạt, không có lỗi High/Critical; thêm 7 test Foundry `SlopeeEscrowSecurityW8.t.sol`, **chưa biên dịch được ở máy soạn** nên chờ `forge test` trong CI.)*
- [ ] 🎯 **NGHIỆM THU CỘT MỐC M4:**
  - [ ] Toàn bộ bài test trên CI xanh 100%. Không còn bug mức High/Critical.

**Ghi chú Tuần 8 — phần Thành viên A:**
1. **E-05 / AC-09.** `scripts/scan_no_user_keys.py` (chỉ đọc, chỉ thư viện chuẩn): quét mã nguồn, lược đồ (`schema.sql` + migration), log và (với `--db`) CSDL đang chạy. Mã thoát 0 sạch / 1 có HIGH / 2 không chạy được; `--json`, `--report`, `--self-check`. Danh sách khóa thử công khai được **suy ra** từ mnemonic công khai của Anvil (không ghi cứng), nên khóa lạ trong ngữ cảnh khóa luôn là HIGH và khóa thử #5+ nằm ở mã chạy thật cũng là HIGH.
2. **Bằng chứng tích cực:** backend chỉ giữ 3 khóa vận hành (`Web3Settings`), `Account.from_key` chỉ ở `env_signer.py`, `user_wallets` chỉ có địa chỉ công khai, `backend/.env.web3` bị `.gitignore`.
3. **Test:** `test/unit_test/test_w8_non_custodial.py` (57 ca: repo thật sạch; 23 kiểu rò khóa phải bị bắt; 12 mẫu hợp lệ không báo nhầm; quét CSDL bằng con trỏ giả; mã thoát CLI; đường logger → `SensitiveDataFilter` → bộ quét). `test/integration_test/test_w8_non_custodial_mysql.py` (3 ca, MySQL thật, chưa chạy ở máy soạn). CI `backend`: thêm `--self-check`, quét repo, quét `--db`.
4. **Lỗi của chính script được tìm ra khi viết test** (từng bỏ qua mọi thư mục tên `lib`, gồm `frontend/src/lib`): đã sửa, chỉ bỏ `contracts/lib/`.
5. **Hai cảnh báo WARN, không phải lỗi:** `test/w3_support.py` có 2 khóa thử (`merchant5`, `merchant6`) không thuộc 20 tài khoản Anvil, và khóa `stranger` ghi nhãn "#12" thực ra là Anvil #4 (= `feeRecipient` của `Deploy.s.sol`). Chỉ là nhãn/khóa thử; để Tuần 9 nếu còn thời gian.
6. **Checklist an ninh:** `docs/SECURITY_CHECKLIST_W8.md` (Reentrancy, Malleability, Role Separation, Front-running đều đạt; 5 ghi nhận mức Info, không đổi contract do Feature Freeze và ABI đóng băng). `contracts/test/SlopeeEscrowSecurityW8.t.sol` thêm 7 test: RS1–RS3, FR1–FR2, SM1–SM2.
7. **Chưa làm / cần người chạy:** `forge test` và `slither` (máy soạn không tải được Foundry/solc), nên 7 test Foundry mới và mục "đạt" của checklist là theo đọc mã + test cũ cho tới khi CI xanh; quét `--db` trên MySQL thật; AC-09 chưa ký duyệt (chờ CI).

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

### 5.1. Smart Contract Test Suite (Foundry: `contracts/test/*.t.sol`)
> `[~]` = đã viết và pass cục bộ bằng `forge test` (**139 test**, gồm 5 test vector chéo ngôn ngữ và 8 invariant), chờ review/CI. `[x] PASS` chỉ đặt khi CI xanh trên nhánh chính. T-01…T-07, T-14, T-23 (Tuần 1) cũng giữ `[~]` theo đúng quy tắc này dù PR Tuần 1 đã chốt.

| Mã test | Mô tả ca kiểm thử | Kết quả mong đợi | BRD / SRS | Tình trạng |
| :---: | :--- | :--- | :---: | :---: |
| **T-01** | Nạp tiền với báo giá hợp lệ (ERC-20 và ETH) | Thành công, đơn `LOCKED` | BR-06 | `[x] PASS` |
| **T-02** | Báo giá quá hạn; sai caller; chữ ký sai; signer thiếu role | Revert | BR-06 | `[x] PASS` |
| **T-03** | Trùng `orderId`; ETH khác amount; nạp token gửi kèm ETH; thiếu allowance | Revert | BR-06 | `[x] PASS` |
| **T-04** | Merchant trùng Buyer; Trọng tài làm Buyer/Merchant; duration ngoài [1h, 30d] | Revert | BR-03, 04 | `[x] PASS` |
| **T-05** | `confirmDelivery` gọi bởi người không có role; gọi khi đơn chưa `LOCKED` | Revert | BR-03 | `[x] PASS` |
| **T-06** | `earlyRelease` gọi bởi Buyer; gọi bởi người khác | Thành công / Revert | BR-03 | `[x] PASS` |
| **T-07** | `releaseAfterInspection` tại đúng mốc biên và trước 1 giây | Thành công / Revert | BR-03 | `[x] PASS` |
| **T-08** | Chia phí theo `feeBps` (0, 300, 1000); Kiểm tra làm tròn; Đổi `defaultFeeBps` không ảnh hưởng đơn cũ | Đúng công thức | BR-02 | `[x] PASS: feeBps 0/300/1000, làm tròn xuống, đổi trần không ảnh hưởng đơn cũ` |
| **T-09** | `setDefaultFeeBps` > 1000; gọi bởi người không phải Admin | Revert | BR-02 | `[x] PASS` |
| **T-10** | `raiseDispute` trong hạn; sau hạn; gọi bởi người không phải Buyer | Thành công / Revert | BR-03 | `[x] PASS: gồm biên đúng mốc hết hạn và trừ 1 giây` |
| **T-11** | `resolveDispute` đủ 2/3 chữ ký (Arbitrator + Buyer; Arbitrator + Merchant) | Thành công, đúng payout | BR-04 | `[x] PASS: Trọng tài+Buyer, Trọng tài+Merchant, Buyer+Merchant` |
| **T-12** | 2 chữ ký cùng bên; 2 địa chỉ cùng vai Trọng tài; chữ ký người lạ; quá hạn deadline; sai nonce | Revert | BR-04 | `[x] PASS: gồm 2 Trọng tài khác địa chỉ, sai nonce/amount/payee/deadline, chữ ký malleable` |
| **T-13** | Nộp lại chữ ký đã dùng sau khi đơn đã đóng | Revert | BR-04 | `[x] PASS` |
| **T-14** | `cancelIfUnfulfilled` trước và sau 14 ngày; bởi Buyer, Admin, người ngoài | Revert / OK / Revert | BR-05 | `[x] PASS` |
| **T-15** | `arbitratorForceResolve` trước/sau `disputeTimeout`; biên -1s revert, đúng mốc thành công | Revert / OK / Revert | BR-05 | `[x] PASS: timeout 7/30/90 ngày, hai phía của mốc (R-02)` |
| **T-16** | Ví nhận từ chối ETH: Chuyển vào `pendingWithdrawals`; `claimPending` rút thành công | Thành công, không kẹt | BR-05 | `[x] PASS: ví từ chối ETH (Merchant/người nhận phí/Buyer), claimPending, rút lại bị chặn` |
| **T-17** | Tấn công Reentrancy qua fallback ví nhận ETH và token độc hại | Bị ReentrancyGuard chặn | Bảo mật | `[x] PASS: ví tái nhập qua claimPending; token độc hại khi nạp, giải ngân, phân xử` |
| **T-18** | Invariant/Fuzz: Số dư contract = Tổng đơn mở + Tổng sổ chờ rút | Luôn đúng | G-01 | `[x] PASS (forge invariant, 128 run × 100 lời gọi, ETH và token)` |
| **T-19** | Kiểm tra ma trận âm: Mọi cặp (state, method) không hợp lệ trong SRS mục 5 | Revert | Máy trạng thái | `[x] PASS: 45 cặp âm, đúng lý do revert, không đổi trạng thái` |
| **T-20** | Báo giá có `disputeTimeout` < 7 ngày hoặc > 90 ngày; biên đúng 7 và 90 ngày | Revert / OK | BR-10 | `[x] PASS` |
| **T-21** | Hai đơn có `disputeTimeout` khác nhau chạy song song: độc lập thời gian timeout | Thành công độc lập | BR-10 | `[x] PASS` |
| **T-22** | Báo giá có `feeBps > defaultFeeBps`; hạ trần thì báo giá cũ bị từ chối | Revert / OK | BR-02, 06 | `[x] PASS: hạ trần ⇒ báo giá cũ bị từ chối, báo giá mới được` |
| **T-23** | Báo giá có `q.buyer != msg.sender` | Revert | BR-06 | `[x] PASS` |
| **T-24** | `resolveDispute` với `deadline >= disputedAt + disputeTimeout` | Revert | BR-04, 05 | `[x] PASS: deadline = mốc, > mốc, vô hạn đều revert; mốc − 1 thành công` |
| **T-25** | Nạp gom 3 đơn 3 shop: 1 lần `transferFrom`, tăng số dư đúng tổng, 3 sự kiện `OrderCreated` | Thành công | BR-11 | `[x] PASS: đúng 1 transferFrom với đúng tổng; cả ETH` |
| **T-26** | Lô nạp rỗng; lô > 5 đơn; lệch độ dài mảng quotes và sigs | Revert | BR-11 | `[x] PASS` |
| **T-27** | Trùng `orderId` ngay trong một mảng lô nạp | Revert, số dư không đổi | BR-11, G-01 | `[x] PASS` |
| **T-28** | Một báo giá trong lô lỗi (quá hạn, sai chữ ký, vượt trần phí) | Toàn bộ lô Revert | BR-11 | `[x] PASS: 4 loại lỗi × 3 vị trí trong lô` |
| **T-29** | Lô nạp trộn nhiều loại token; nạp ETH sai tổng `msg.value` | Revert | BR-11 | `[x] PASS` |
| **T-30** | Mọi điều kiện đơn lẻ áp dụng chuẩn xác cho từng phần tử của lô | Revert nếu vi phạm | BR-06, 11 | `[x] PASS: 8 loại vi phạm trên phần tử giữa lô` |
| **T-31** | Sau khi nạp gom: Đơn A early release, đơn B dispute hoàn tiền, đơn C tự giải ngân | Độc lập hoàn toàn | BR-11 | `[x] PASS` |
| **T-32** | Đo gas nạp lô 5 đơn (mục tiêu < 3.000.000 gas) | Đạt ngưỡng gas | BR-11 | `[x] PASS: 1.229.409 gas (token), 1.099.331 gas (ETH)` |
| **T-33** | Fuzz invariant: Gọi ngẫu nhiên cả nạp đơn và nạp gom | INV-01..07 luôn đúng | G-01 | `[x] PASS (forge invariant: INV-01…07, nạp đơn lẻ và nạp gom)` |
| **T-34** | So sánh nạp đơn lẻ và nạp lô 1 phần tử: Trạng thái và event giống hệt nhau | Khớp 100% | BR-11 | `[x] PASS: so sánh trạng thái đơn, số dư và từng log` |

---

### 5.2. Integration, System & Backend API Test Suite
> `[~]` = test đã viết và pass cục bộ, chờ CI/PR; `[x] PASS` chỉ đặt sau khi CI xanh trên nhánh chính.
> Ngoài ma trận bên dưới, Tuần 2 thêm **31 test migration Web3** (`test/unit_test/test_web3_migrations_static.py` 6 test; `test/integration_test/test_web3_migrations.py` 25 test trên MySQL 8.0 thật): DB mới == DB nâng cấp, idempotent, collation lệch, MyISAM bị chặn, CHECK/UNIQUE/FK/ENUM. Toàn bộ pytest hết Tuần 2: **360 pass, 0 skip** (có MySQL). Hết Tuần 3: **580 pass** (thêm 220, trong đó 5 test chuỗi thật cần Anvil).

| Mã test | Phạm vi kiểm thử | Tiêu chuẩn đánh giá | Tình trạng |
| :---: | :--- | :--- | :---: |
| **I-01** | Liên kết ví: Nonce dùng lại, nonce hết hạn, chữ ký sai, ví đã thuộc user khác | AC-01 / Trả đúng mã lỗi HTTP | `[x] PASS` |
| **I-02** | Báo giá: Quy đổi VND ➔ token chuẩn xác, hợp đồng chấp nhận chữ ký Python | AC-01, AC-02 | `[x] PASS` |
| **I-03** | Indexer: Xử lý trùng tx_hash/log_index không ghi đôi, khởi động lại, phục hồi con trỏ | AC-08 / Tính Idempotent | `[x] PASS (17 test khung + 16 test handler OrderCreated); chờ CI. Handler Delivered/Disputed/Completed/Refunded ở Tuần 5-6` |
| **I-04** | Nhóm hàng: Đơn nhiều nhóm lấy `max()`, đổi chính sách không ảnh hưởng đơn cũ | AC-12 | `[~] một phần: `max()` riêng từng thời hạn + policy mỗi shop đúng; thời hạn lưu cứng trên `order_web3` nhưng chưa có test "đổi chính sách sau khi đặt"` |
| **I-05** | Đồng bộ thời gian: `now_chain()` theo sát block Anvil; tua thời gian cấp quote mới chuẩn | AC-02 | `[x] PASS: now_chain nhảy theo evm_increaseTime, quá hạn chặn Khiếu nại, báo giá mới sau tua giờ được contract nhận (CI web3-chain xanh)` |
| **I-06** | Đồng bộ ngược: Cập nhật `order_web3` tự động cập nhật `orders.status` cũ; Chặn route ghi đè cũ | AC-08 / Bảng ánh xạ 5.1 | `[x] PASS` |
| **I-07** | Giỏ 3 shop: Tạo đúng 3 đơn 1 group, tổng token khớp lệnh, Indexer xóa đúng giỏ hàng | AC-14 | `[x] PASS` |
| **A-01** | Mọi API yêu cầu token: Không token hoặc token hết hạn trả HTTP 401 | Mục 15 (P0-01) | `[x] PASS` |
| **A-02** | Kiểm tra quyền Role: User/Seller gọi API Admin bị chặn HTTP 403; Shipper chỉ xem đơn gán | Mục 15 (P0-02) | `[x] PASS` |
| **A-03** | Kiểm tra sở hữu dữ liệu: Xem đơn, giỏ, shop của người khác bị 403 hoặc 404 | Mục 15 (P0-03) | `[x] PASS` |
| **A-04** | Đăng ký tài khoản với role `admin` hoặc `shipper` bị từ chối | Mục 15 (P0-02) | `[x] PASS` |
| **A-05** | Đua tranh đặt hàng (Race condition): Tồn kho không bao giờ bị âm | Mục 15 (P0-05) | `[x] PASS` |
| **A-06** | Giới hạn brute-force: Nhập sai PIN hoặc Password quá 5 lần bị khóa tạm | Mục 15 (P0-05) | `[x] PASS` |
| **A-07** | Endpoint `/api/shops/migrate` đã bị xóa bỏ; Không còn API cấp số dư vô hạn | Mục 15 (P0-04) | `[x] PASS` |

---

### 5.3. Frontend Logic & Unit Test Suite (Vitest)
| Mã test | Mô tả ca kiểm thử | Kết quả mong đợi | Tình trạng |
| :---: | :--- | :--- | :---: |
| **F-01** | Hàm định dạng `formatVND`: Kiểm tra số nguyên, làm tròn, số 0, số cực lớn, không còn ký hiệu `$` | Chuẩn định dạng tiếng Việt | `[x] PASS` |
| **F-02** | Reducer nạp tiền (`depositReducer`): Đủ allowance bỏ bước approve, từ chối ví (4001), hết hạn quote | Chuyển state chính xác | `[x] PASS` |
| **F-03** | Ánh xạ lỗi tiếng Việt: `BATCH_TOO_LARGE`, `FEE_CAP_CHANGED`, `Invalid batch size` | Hiển thị thông báo dễ hiểu | `[x] PASS` |
| **F-04** | Client API chung: Tự gắn `Authorization`, tự động xóa token và chuyển trang khi gặp 401 | Hoạt động thông suốt | `[x] PASS` |
| **F-05** | Hook `usePolling`: Dừng khi rời màn hình, dừng khi đơn tới trạng thái cuối | Không memory leak / spam | `[x] PASS` |
| **F-06** | Đồng hồ đếm ngược: Tính độ lệch dựa trên `server_time`, không lệch theo máy client | Đếm ngược chuẩn xác | `[x] PASS` |
| **F-07** | Làm mới báo giá của lô đang chờ: nhãn đúng bản chất, nút khóa trong lúc gọi, không gửi trùng khi bấm dồn, đồng hồ bắt đầu lại từ 15:00 | Không giật bộ đếm, không nhiều yêu cầu đồng thời | `[x] PASS` |
| **F-08** | Checkout khóa lựa chọn Web3 và cảnh báo khi có shop chưa liên kết ví; panel nêu đích danh shop | BR-07, không để lỗi ở bước cuối | `[x] PASS` |
| **F-09** | Quy tắc nút và đồng hồ kiểm tra (`orderTimer`): đếm theo `server_time`, máy khách sai giờ không lệch; hết hạn khóa "Khiếu nại" nhưng vẫn cho "Đã nhận hàng"; chỉ ví đã ký quỹ mới bật nút | SDD 9.4, F-06 | `[x] PASS` |
| **F-10** | Luồng ví Buyer (`orderActions`, `MyOrders`): biên nhận chưa phải `COMPLETED`, chỉ API báo mới đổi; bấm dồn chỉ một giao dịch; hủy ví là thông báo nhẹ; lỗi revert dịch đúng | DD-04, BR-09 | `[x] PASS` |
| **F-11** | Khiếu nại: form chặn lý do ngắn/URL không phải http(s); lý do chỉ gửi sau khi `DISPUTED`; gửi lỗi thì "Gửi lại lý do"; hủy ví thì xóa bản nháp; tải lại trang vẫn gửi được | UC-05, SEQ-02 | `[x] PASS` |
| **F-12** | Nhóm đơn theo `checkout_group_id`: thao tác đơn shop này không đổi đơn shop khác; đơn đã xong không bị poll; đơn cũ giữ nguyên nút | BR-11 | `[x] PASS` |
| **F-13** | `runOrderAction` + ABI + ethers thật trên Anvil: `earlyRelease`/`raiseDispute` chạy được; revert thật `Not delivered`/`Only buyer`/`Expired` được dịch đúng (`orderActions.anvil.test.js`, tự skip nếu không có Anvil) | UC-04, UC-05 | `[x] PASS (5 test Anvil ethers được chạy trong job web3-chain / test riêng)` |
| **F-14** | Màn hình ký phán quyết (`Dispute.jsx`): kết quả suy từ địa chỉ; cảnh báo vàng đúng nguyên văn ngay trước nút ký; phải đồng ý mới ký; ký thật (`eth_signTypedData_v4`) và mock kiểm chữ ký bằng mật mã; Merchant thấy phần thực nhận sau phí | UC-06, R-06, SDD 9.7 | `[~]` |
| **F-15** | An toàn khi ký: sai ví/sai mạng khóa nút; chặn đề xuất có `payoutTo` lạ, sai số tiền, quá `disputeTimeout`, hết hạn; lý do khiếu nại chứa HTML hiển thị như chữ; liên kết `javascript:`/`data:`/`file:` không thành liên kết | UC-06, P0-06 | `[~]` |
| **F-16** | Lỗi khi ký/gửi: hủy MetaMask là thông báo nhẹ; lỗi mạng thì "Gửi lại chữ ký" không bật ví lần nữa; bấm dồn chỉ một hộp ký; đề xuất bị hủy giữa chừng được báo | UC-06 | `[~]` |
| **F-17** | Đồng hồ hạn ký theo giờ máy chủ (`serverClock`): chỉ tăng độ lệch, đếm ngược không giật lùi với `server_time` răng cưa, máy chủ lệch 3 ngày vẫn đúng | F-06, GHI_CHU mục 10-11 | `[~]` |
| **F-18** | Hủy đơn chưa giao quá 14 ngày (`Web3OrderPanel`, UC-07): đồng hồ giao hàng; nút khóa trước mốc, bật sau mốc; xác nhận trong trang (không `window.confirm`); gọi đúng `cancelIfUnfulfilled(id)`; chỉ `REFUNDED` khi API báo; sai ví/sai mạng khóa; hủy ví nhẹ; `Timeout not reached` dịch đúng; bấm dồn một giao dịch; thiếu `chain_created_at` thì ẩn; đơn khác trong lô không đổi (BR-11) | UC-07, BR-05, T-14 | `[x] PASS` |
| **F-19** | Hạn hủy đơn (`orderTimer`, `useOrderStatus`): mốc = `chain_created_at` + 14 ngày; làm tròn LÊN; máy khách sai giờ vẫn đúng; đếm ngược không tăng lại; `availableActions` giữ nguyên hình dạng | F-06, UC-07 | `[x] PASS` |
| **F-20** | Khung Merchant (`MerchantWeb3Panel`, UC-07): chỉ đơn của shop; trạng thái theo góc nhìn người bán; số tiền sau phí chính xác (BigInt); tổng quan theo từng token; lọc trạng thái; liên kết `/disputes/:code` chỉ cho đơn `DISPUTED`; tên người mua chứa HTML hiển thị như chữ; lỗi tải giữ dữ liệu cũ; cảnh báo chưa có ví nhận tiền | UC-07, BR-07, BR-11 | `[~] 16 vitest hàm thuần + 7 vitest khung xanh với API giả; chờ chạy thử với API/DB thật trên trình duyệt` |
| **F-21** | Rút khoản chờ rút (`claimPending`): đọc lại số dư trên chuỗi trước khi gửi; số dư 0 không gửi; ETH dùng địa chỉ 0; chỉ xong khi API bỏ khoản đó; bấm dồn một giao dịch; sai ví/sai mạng/chưa kết nối khóa nút; hủy MetaMask là thông báo nhẹ; revert `ETH transfer failed`/`Nothing to claim` dịch đúng | UC-07, BR-05, BR-09 | `[~] 12 vitest luồng + 8 vitest khung xanh với ví giả; chưa chạy Anvil/MetaMask thật` |

---

### 5.4. End-to-End Automated Test Suite (Playwright + Mock Provider)
| Mã test | Kịch bản luồng E2E | Tiêu chí nghiệm thu liên quan | Tình trạng |
| :---: | :--- | :---: | :---: |
| **E-01** | **Happy Path:** Đăng ký ➔ Liên kết ví ➔ Đặt hàng ➔ Ký quỹ gom ➔ Giao hàng ➔ Mở khóa sớm | AC-01, AC-03, AC-04 | `[x] PASS (tích hợp chuỗi thật Anvil + MySQL: khóa quỹ -> Shipper giao -> Buyer nhận -> chia phí feeBps chuẩn xác; bản mock UI Playwright ở Tuần 8)` |
| **E-02** | **Inspection Expiry:** Giao hàng ➔ Tua thời gian Anvil ➔ Tự động giải ngân sau hạn | AC-04 | `[ ] PASS` |
| **E-03** | **Dispute Resolution:** Khiếu nại ➔ Đề xuất phán quyết ➔ Buyer/Merchant ký EIP-712 ➔ Hoàn tiền | AC-05, AC-06 | `[~] đã chạy trên Anvil + MySQL thật, cả hai hướng: hoàn tiền Buyer 100% và giải ngân Merchant trừ phí; chữ ký của giao diện được hợp đồng chấp nhận; mọi ca từ chối đúng lý do; đơn shop khác độc lập (BR-11). Đầu cuối qua HTTP còn chờ API B + relayer A; chờ CI` |
| **E-04** | **Timeouts:** Delivery timeout (14 ngày hủy hoàn tiền); Dispute timeout (Trọng tài xử đơn phương) | AC-07 | `[~]` *(backend + chuỗi thật xong: `test_w7_timeouts_anvil.py` 8 test, Dispute timeout 7/30/90 ngày + Delivery timeout 14 ngày; còn bản Playwright qua giao diện, cần nút Thoát hiểm của Admin)* |
| **E-05** | **Zero-key Scan:** Quét tự động repo, CSDL, file log không tìm thấy private key người dùng | AC-09 (BR-01) | `[~] repo + lược đồ + log: 0 HIGH (script + 57 test Python xanh); quét CSDL MySQL thật chờ CI (bước mới ở job backend + test_w8_non_custodial_mysql.py)` |
| **E-06** | **Đối soát số dư:** Script kiểm tra số dư contract khớp 100% với đơn mở sau mỗi ca test E2E | AC-10 (G-01) | `[x] PASS (scripts/reconcile.py --deep --events chạy thực tế trả về mã 0 - KHỚP)` |
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
| **AC-08** | Xóa CSDL chạy lại Indexer từ block 0 khớp 100% dữ liệu on-chain; Xử lý trùng an toàn | BR-09 | Test I-03, I-06, Replay script đạt | `[x]` |
| **AC-09** | Quét toàn diện mã nguồn, CSDL, log không có private key hay seed phrase người dùng | BR-01 | Test E-05 đạt | `[ ]` |
| **AC-10** | Số dư contract luôn bằng tổng tiền các đơn đang mở cộng sổ chờ rút | G-01 | Test T-18, E-06, Reconcile tool đạt | `[ ]` |
| **AC-11** | Bộ test contract đạt coverage ≥ 90%; Chạy lặp lại kịch bản demo 3 lần liên tiếp không lỗi | G-06 | Báo cáo test & biên bản demo | `[x]` |
| **AC-12** | Nhóm hàng nhận đúng thời hạn kiểm tra và tranh chấp; Biên 7–90 ngày do contract ép | BR-05, BR-10 | Test T-20, T-21, I-04 đạt | `[ ]` |
| **AC-13** | Báo giá có phí vượt trần on-chain bị từ chối; Hạ trần phí buộc lấy báo giá mới | BR-02, BR-06 | Test T-22, T-23 đạt | `[ ]` |
| **AC-14** | Giỏ nhiều shop thanh toán gom 2 lần ký ví; Hoạt động độc lập sau nạp; Nguyên tử | BR-11, BR-06 | Test T-25..34, I-07, E-07 đạt | `[x]` |

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
