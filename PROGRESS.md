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
| **M1** | Cuối Tuần 2 | Smart Contract hoàn chỉnh, test suite Foundry xanh 100%, coverage ≥ 90%, export ABI chuẩn | `[~] ĐẠT CỤC BỘ, chờ review/CI` | YYYY-MM-DD | A (Dev), B (Review) |
| **M2** | Cuối Tuần 4 | Lát cắt E2E thô: Liên kết ví ➔ Báo giá ➔ Ký quỹ gom ➔ Indexer ➔ UI hiện `LOCKED` | `[ ] CHƯA ĐẠT` | YYYY-MM-DD | Cả nhóm |
| **M3** | Cuối Tuần 7 | Đủ 4 vai trò (Buyer, Merchant, Shipper, Admin), luồng tranh chấp 2/3 chữ ký EIP-712 & timeout | `[ ] CHƯA ĐẠT` | YYYY-MM-DD | Cả nhóm |
| **M4** | Cuối Tuần 8 | Đóng băng tính năng; Toàn bộ bài test tích hợp và E2E xanh; Rà soát checklist an ninh | `[ ] CHƯA ĐẠT` | YYYY-MM-DD | Cả nhóm |
| **M5** | Cuối Tuần 10 | Nghiệm thu toàn diện: Chạy demo lặp lại 3 lần liên tiếp không lỗi, video backup, sẵn sàng bảo vệ | `[ ] CHƯA ĐẠT` | YYYY-MM-DD | Hội đồng |

---

## 3. TIẾN ĐỘ GIAI ĐOẠN 0 (PHASE 0: NỀN TẢNG & SỬA LỖI BẢO MẬT SLOPEE)
> *Bắt buộc hoàn thành P0-01 và P0-02 trước Tuần 3 (khi làm UC-00 liên kết ví).*

| Mã việc | Mô tả kỹ thuật | Khắc phục lỗi | Phụ trách | Tình trạng | PR / Commit |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **P0-01** | Lớp xác thực token ký (`itsdangerous`, `SECRET_KEY` từ env, `AUTH_TOKEN_TTL_SECONDS`), decorator `require_auth`, loại bỏ `userId` từ body/URL, lưu token tại `sessionStorage` | S-01, S-12 | **B** | `[x] Hoàn thành (PR Tuần 1 đã chốt)` | `#PR-` |
| **P0-02** | Đăng ký chỉ cho phép role `user` / `seller`; Khóa `admin_bp`; Bỏ route cấp số dư giả lập vô hạn; Seed tài khoản admin bằng CLI | S-02, S-03, S-04, S-10 | **B** | `[x] Hoàn thành (PR Tuần 1 đã chốt)` | `#PR-` |
| **P0-03** | Kiểm tra quyền sở hữu tài nguyên (đơn hàng, giỏ hàng, shop, sản phẩm, payment method); Chặn ghi đè `orders.status` đối với đơn Web3 (`WEB3_ORDER_MANAGED`) | S-05, S-06, S-11 | **A** | `[~] Đã code, chờ review` | `#PR-` |
| **P0-04** | Xóa bỏ endpoint `GET /api/shops/migrate`; Viết runner migration tự động đánh số qua bảng `schema_migrations`; Dọn schema trùng `reviews` / `reviewImages` (sửa lỗi MySQL strict 1364) | S-07, S-13 | **A** | `[~] Đã code, chờ review` | `#PR-` |
| **P0-05** | Thanh toán an toàn: Lock dòng bằng `SELECT ... FOR UPDATE`, `UPDATE ... WHERE inStock >= qty`; Xóa bỏ tính tiền bằng `float`; Khóa tạm tài khoản sau 5 lần sai mã PIN/mật khẩu | S-08, S-09 | **A** | `[~] Đã code, chờ review` | `#PR-` |
| **P0-06** | Tắt `debug=True` trên production; Chuẩn hóa trả về lỗi chung cho client, chi tiết ghi log máy chủ; Validate schema body JSON | S-10, S-14 | **A** | `[~] Đã code, chờ review` | `#PR-` |
| **P0-07** | Chuyển toàn bộ Slopee sang VND: 4 cột tiền đổi sang `DECIMAL(15,0)`; Đổi frontend dùng chung `formatVND` (`Intl.NumberFormat('vi-VN')`), xóa sạch biểu tượng `$` | Q-09, DD-12 | **B + C** | `[x] Hoàn thành (PR Tuần 1 đã chốt)` | `#PR-` |
| **P0-08** | Cập nhật bộ test cũ: Sửa test checkout, cart, auth theo token phiên và VND; Chuyển test race condition sang chạy trên MySQL service thật | SRS 12.3 | **B + C** | `[~] Đã code, chờ review` | `#PR-` |

**Ghi chú Phase 0 (cập nhật gần nhất):**
- `[~]` = đã code và test xanh cục bộ, **chờ PR được thành viên khác duyệt**; điền cột PR/Commit khi mở PR. `[x]` = đã duyệt và chốt PR. **P0-01, P0-02, P0-07** thuộc Tuần 1 và đã `[x]` khi PR Tuần 1 chốt (cột PR/Commit còn `#PR-`: điền số PR thật). P0-03…P0-06 và P0-08 thuộc Tuần 3 nên vẫn `[~]`.
- **P0-01/02:** token mặc định hết hạn sau 3600 s (đặt `AUTH_TOKEN_TTL_SECONDS`; SDD 16.3 gợi ý 8 giờ → nhóm chốt giá trị). Token mang `role` và không kiểm lại DB. Route theo người dùng đã đổi sang `/me` hoặc bỏ tham số (xem `AI_CONTEXT.md` mục 6). Số dư phương thức thanh toán mới = 0.
- **P0-07:** `migrations/0001_money_to_vnd.sql` mới chạy tay và chỉ làm tròn dữ liệu USD cũ (SDD 16.3 bước 8 yêu cầu nhân với `FX_VND_PER_TOKEN`); DB demo nên tạo lại bằng `init_db.py`. File này đã nằm trong runner của P0-04 (xem ghi chú P0-04).
- **P0-08:** test race condition checkout đã chạy trên MySQL thật (`test/integration_test/test_checkout_race_mysql.py`) và CI có MySQL service (`.github/workflows/tests.yml`). Yêu cầu "không bán lố, tiền khớp" vẫn đúng; sau P0-05 request thua cuộc trả 400 (không còn 500 do `CHECK`).
- **P0-03:** chỉ chủ mới sửa/xóa được cart item, đơn, sản phẩm, ảnh và biến thể; tài nguyên của người khác trả **404** như thể không tồn tại (không lộ sự tồn tại). `PUT /api/payments/orders/:id` khóa dòng `orders` (`FOR UPDATE`), từ chối đơn có dòng `order_web3` bằng `409 WEB3_ORDER_MANAGED` (nếu chưa có bảng `order_web3` thì coi là đơn cũ), và chỉ cho `paid|shipped→received`, `pending|paid→cancelled` (sai → `409 INVALID_STATE`). Thông báo lỗi giữ tiếng Anh như code hiện tại (SRS quy ước tiếng Việt cho API Web3 → nhóm chốt khi làm UC-00).
- **P0-04:** đã xóa `GET /api/shops/migrate`. Runner: `python migrate.py [up|status|mark-applied <tệp>]` hoặc `flask --app app migrate`; bảng `schema_migrations`, khóa `GET_LOCK`, hỗ trợ migration `.sql` và `.py`. Nội dung route cũ chuyển thành `0002_product_fk_snapshots.py` (cột snapshot, `cartItems` CASCADE, `orderLines.productId` NULL + SET NULL); `0003_reviews_dedupe.py` đưa DB cũ về `reviews` có `UNIQUE(userId, productId)`; `0004_auth_attempts.sql` tạo bảng đếm thử sai. `schema.sql` đã gộp khai báo `reviews`/`reviewImages` (giữ `reviewImages.id VARCHAR(36)`, backend sinh UUID) và phản ánh cả 4 migration; `init_db.py` đánh dấu chúng đã áp dụng cho DB **mới**. **DB cũ phải chạy `python migrate.py`** (bắt buộc: bảng `authAttempts` cần cho đăng nhập/thanh toán). `schema.txt` là bản cũ không còn dùng (nên xóa).
- **P0-05:** checkout khóa theo thứ tự cố định `cartItems → products → paymentMethods` (`ORDER BY id FOR UPDATE`), trừ kho `UPDATE … WHERE inStock >= qty` và trừ tiền `… AND balance >= amount` đều kiểm `rowcount`; giá/tồn đọc dưới khóa; deadlock → `409 checkout_conflict`. PIN chưa đặt → `401 pin_not_set` (hết 500). Sai mật khẩu/PIN 5 lần liên tiếp → khóa 15 phút (`AUTH_MAX_ATTEMPTS`, `AUTH_LOCK_SECONDS`), `429 too_many_attempts` + `Retry-After`; đăng nhập, đổi mật khẩu và xin xóa tài khoản dùng chung một bộ đếm; username không tồn tại cũng bị đếm như thật. Bộ đếm lưu trong bảng `authAttempts`.
- **P0-06:** `debug` chỉ bật khi `SLOPEE_ENV=development`; mọi blueprint và app có handler lỗi chung (`{"error","code":"internal_error"}`, chi tiết ghi log); không còn `str(e)`; `json_body()` từ chối body không phải object (`400 invalid_body`); kiểm kiểu/độ dài/khoảng giá trị cho các trường, URL ảnh chỉ nhận `http(s)`; `MAX_CONTENT_LENGTH` 1 MB. Đăng ký nay yêu cầu email hợp lệ và số điện thoại 9–10 chữ số.
- **Quyết định nhóm sau P0-03…06 (đã áp dụng theo docs, `[~]` chờ review):**
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
- [x] **[B] Thành viên B:** Triển khai **P0-01** (Auth Token) và **P0-02** (Phân quyền Role & bảo vệ Admin). *(đã code, chờ review)*
- [x] **[B + C]:** Triển khai **P0-07** (Chuyển schema và giao diện sang VND số nguyên). *(đã code, chờ review)*
- [x] **[F] Thành viên C:** Client API dùng chung `lib/client.js`, hàm định dạng `lib/format.js` (`formatVND`, `shortAddress`), Route Guard `components/RequireRole.jsx` (chưa đăng nhập → `/login`; sai role → thông báo; áp cho `/admin`, `/seller`, `/cart`, `/checkout`, `/orders`, `/settings`). **Đã chốt tên file theo SDD:** `lib/` là nơi chuẩn; `api/http.js` và `utils/formatVND.js` giữ lại chỉ như lớp re-export để không vỡ import/test cũ (một nguồn sự thật). Các `api/*.js` không còn hardcode `http://localhost:5000` (đọc `VITE_API_BASE`).
- [x] **[F] Thành viên C:** Khung ví `hooks/useWallet.js` (`WalletProvider` + `useWallet`: kết nối EIP-1193/MetaMask, theo dõi `accountsChanged`/`chainChanged`, `switchToDeployedChain` có thêm mạng khi mã 4902, `getSigner()` ethers v6, mã 4001 = "Bạn đã hủy thao tác", không lưu gì vào localStorage) và `lib/chain.js` (đọc/kiểm `deployments/local.json`, chỉ chấp nhận chainId 31337). Chưa có UI kết nối (Navbar/`pages/Wallet.jsx` là UC-00, tuần 3) và chưa có ABI (đóng băng ở M1).
- [x] **[Q] Cả nhóm:** Khóa `shared/eip712/types.json` và tạo `shared/eip712/vectors.json` (sinh bằng `scripts/gen_eip712_vectors.py`, có `--check` cho CI): 3 báo giá, 2 phán quyết (kèm chữ ký Trọng tài), 2 `docHash`. **Đã chạy luôn kiểm tra chéo ngôn ngữ** ở cả 3 nơi cho cùng domainSeparator/structHash/digest/người ký: Python (`test_eip712_vectors.py`), JS (`eip712Vectors.test.js`), Solidity (`Eip712Vectors.t.sol`, còn nạp thật báo giá do Python ký vào contract). *Còn thiếu:* vector cho thông điệp liên kết ví (SDD 8.3) — định dạng SIWE chốt ở UC-00 (tuần 3).

**Cách chạy lại tuần 1:** `./scripts/bootstrap.sh && ./scripts/smoke_week1.sh` · `cd contracts && forge test` · `pytest test` · `cd frontend && npx vitest run`.
**Lưu ý cho bên review:** (1) khóa trong `EscrowBase.t.sol`, `Deploy.s.sol`, `bootstrap.sh`, `gen_eip712_vectors.py` là **khóa thử công khai của Anvil** — bài quét E-05 (AC-09) phải cho phép danh sách này, nếu không sẽ báo nhầm; (2) `contracts/lib/` bị `.gitignore` (cài bằng `scripts/install_contract_deps.sh`); (3) `foundry.toml` dùng `solc_version = "0.8.20"` (Foundry tự tải); (4) địa chỉ contract trong vector (`0xe7f1…0512`, token `0x5FbD…0aa3`) khớp lần triển khai đầu trên Anvil sạch của deployer #0.

---

### TUẦN 2: Hoàn thiện Smart Contract, Nạp gom & Đạt Cột mốc M1
> Quy ước `[~]` như Tuần 1: đã code, test xanh cục bộ, **chờ PR được duyệt**. Chưa `[x]` vì chưa qua review/CI.
- [~] **[C] Thành viên A:** Cài đặt logic tranh chấp: `raiseDispute` (chỉ Buyer, `DELIVERED → DISPUTED`, `now < deliveredAt + inspectionDuration`), `resolveDispute` (2 chữ ký EIP-712 của 2 bên khác nhau trong Buyer/Merchant/Trọng tài; ai cũng nộp được; `deadline < disputedAt + disputeTimeout`; nonce theo đơn).
- [~] **[C] Thành viên A:** Cơ chế thoát hiểm timeout: `arbitratorForceResolve` (`ARBITRATOR_ROLE`, chỉ khi `now >= disputedAt + disputeTimeout`). Hai đường `resolveDispute` và thoát hiểm **không bao giờ cùng hợp lệ** (R-02): đã test cả hai phía của mốc (T-15, T-24).
- [~] **[C] Thành viên A:** Nạp gom nhiều shop: `depositEscrowBatch` (nguyên tử, tối đa 5 đơn, một token, thu tiền đúng một lần; dùng chung `_acceptQuote`/`_collect` với `depositEscrow` nên không có đường nạp nào yếu hơn). Ghi đơn `LOCKED` ngay trong vòng lặp nên `orderId` trùng trong cùng lô bị từ chối (`Order exists`) thay vì bị thu tiền hai lần.
- [~] **[C] Thành viên A:** Sổ chờ rút pull-payment: `claimPending` (xóa số dư trước khi chuyển, `nonReentrant`), `PayoutDeferred`/`PendingClaimed`; thêm `setDefaultFeeBps` (trần ≤ 1.000 BPS) và `setFeeRecipient` (Admin). Struct/enum/sự kiện/storage giữ nguyên Tuần 1 — chỉ **thêm** hàm.
- [~] **[C] Thành viên A:** Bộ test Foundry **139 test** (`forge test`): T-01…T-34 đủ + invariant INV-01…INV-07 (8 invariant, handler gọi ngẫu nhiên cả nạp đơn lẻ và nạp gom, 128 run × 100 lời gọi). **Gas nạp gom 5 shop (T-32): 1.229.409 (token), 1.099.331 (ETH)** — dưới mục tiêu 3.000.000. Phân bổ: `Eip712Vectors` 5, `Week1` 41, `Week2` 59, `Batch` 24, `Matrix` 2 (45 cặp âm), `Invariant` 8.
- [~] **[B] Thành viên B:** 15 migration MySQL Web3 `0006`…`0020` (SDD `001_wallets`…`015_shipper`; tên thật: `0006_wallets.py`, `0007_checkout_groups.py`, `0008_order_web3.py`, `0009_order_quotes.py`, `0010_dispute_resolutions.py`, `0011_dispute_signatures.sql`, `0012_chain_events.sql`, `0013_indexer_cursor.sql`, `0014_platform_settings.sql`, `0015_category_policies.sql`, `0016_category_policy_map.sql`, `0017_tx_outbox.sql`, `0018_onchain_id_seq.sql`, `0019_pending_balances.sql`, `0020_shipper.py`), bảng `order_web3` quan hệ 1-1 với `orders`. Migration có khóa ngoại tới bảng Slopee là `.py` và **phòng vệ** (SDD Q-06): đọc kiểu/charset/collation của cột cha, dừng nếu bảng cha không phải InnoDB. `schema.sql` đã phản ánh đủ (16 bảng Web3 + `users.role` có `shipper`). **31 test mới** (6 tĩnh + 25 trên MySQL 8.0 thật); toàn bộ pytest **360 pass, 0 skip**.
- [~] **[Q] Thành viên B + C:** Chạy test chéo ngôn ngữ Python, JavaScript và Solidity khớp 100% digest EIP-712. *(đã chạy sớm ở tuần 1 cho báo giá, phán quyết, docHash; vẫn xanh sau thay đổi tuần 2; còn bổ sung vector liên kết ví nếu chốt định dạng sớm)*
- [~] 🎯 **NGHIỆM THU CỘT MỐC M1:** *(đạt cục bộ; chờ A(Dev)/B(Review) duyệt và CI xanh để chuyển `[x]`)*
  - [~] Độ phủ dòng lệnh contract đạt ≥ 90% (`forge coverage --ir-minimum`): **100% (153/153 dòng của `src/`)**; 100% hàm. Lưu ý: số liệu *nhánh* Foundry báo 33% (30/90) vì nó đếm từng `require`/modifier là nhánh; tiêu chí M1 là dòng lệnh.
  - [~] Chạy Slither không còn cảnh báo mức High chưa giải thích: **0 High, 0 Medium chưa giải thích**. Một High (`reentrancy-balance` ở `_collect`) và 2 Medium (`incorrect-equality`) là false positive có chủ đích, đã ghi lý do ngay tại mã bằng `slither-disable` (đọc chênh lệch số dư để loại token phí-khi-chuyển; mọi đường gọi đều `nonReentrant`, chứng minh bằng T-17). Còn 9 cảnh báo Low (8 `timestamp` do spec bắt buộc dùng `block.timestamp`, 1 `reentrancy-benign` ở `_payout`: ghi sổ chờ rút sau `call` giới hạn 30.000 gas, có `nonReentrant`).
  - [~] Đóng băng ABI `SlopeeEscrowMaster.json` (37 hàm, 15 sự kiện) + `MockUSD.json`: xuất bằng `scripts/export_abi.sh` sang `shared/abi/` (nguồn duy nhất cho backend) và `frontend/src/lib/abi/`; `--check` chạy trong CI để ABI không lệch khỏi contract. *(Chưa nối vào `lib/chain.js`: việc của Thành viên C ở Tuần 3–4.)*

**Cách chạy lại tuần 2:** `(cd contracts && forge test)` (invariant ~1–1,5 phút) · `(cd contracts && forge coverage --ir-minimum --report summary --no-match-coverage "(test|script)")` · `(cd contracts && slither . --exclude-informational)` · `./scripts/export_abi.sh --check` · `pytest test` (cần MySQL 8.0 ≥ 8.0.16 cho phần migration) · `./scripts/bootstrap.sh && ./scripts/smoke_week1.sh` (đã chạy: contract tuần 2 triển khai và smoke tuần 1 `SMOKE OK`).

**Ghi chú & quyết định Tuần 2 (cần nhóm xem khi review):**
1. **Gieo dữ liệu trong migration thay vì `bootstrap.sh`** (lệch nhẹ so với SRS/SDD 7.6): `bootstrap.sh` chưa chạm MySQL và nhóm `GENERAL` là bắt buộc (danh mục chưa ánh xạ dùng GENERAL). Dùng `INSERT IGNORE` nên chạy lại không đè giá trị Admin đã sửa (có test). SDD 7.6 đã được đính chính cho khớp (tài liệu đóng băng nhưng sửa như một góp ý để tránh lặp lại). Giá trị 4 nhóm chính sách là **giá trị đề xuất của SRS, nhóm chốt lại trước Tuần 3**.
2. **Gieo 4 khóa `platform_settings`:** `PLATFORM_FEE_BPS=300`, `QUOTE_TTL_SECONDS=900` (có sẵn trong đặc tả) cùng `FX_VND_PER_TOKEN=25000` (1 token = 25.000 VND) và `DISPUTE_SIG_TTL_SECONDS=604800` (7 ngày), hai giá trị này do nhóm chốt vì đặc tả không có mặc định. Backend vẫn nên báo lỗi rõ nếu một khóa bị Admin xóa.
3. **Ba chỗ sửa test Tuần 1/Phase 0 (hành vi kiểm không yếu đi):** (a) `test_p0_mysql::test_order_with_order_web3_row_is_rejected` trước đây tự tạo bảng `order_web3` tối thiểu, nay chèn dòng vào bảng thật; (b) `test_p0_04::test_schema_statements_are_all_creates_and_splittable` nới để cho phép thêm đúng `INSERT IGNORE INTO` (gieo mặc định); (c) `SlopeeEscrowWeek1::test_T05…` đọc `vm.getBlockTimestamp()` thay `block.timestamp` vì `forge coverage --ir-minimum` làm `block.timestamp` cũ sau `vm.warp` (test xanh ở chế độ thường, đỏ ở chế độ coverage).
4. **Handler invariant bản đầu gần như vô nghĩa (ghi nhận là một đóng góp, giữ nguyên):** đo thực tế cho thấy mỗi run chỉ có ~4 lần nạp, 0 tranh chấp, 0 nạp gom nên invariant xanh chẳng chứng minh gì. Đã chỉnh handler (đa số lời gọi hợp lệ, thêm `progress`/`openDispute`) và đo lại: mỗi run đều chạm nạp gom, giải ngân, hoàn tiền, khiếu nại, phân xử bằng chữ ký, thoát hiểm, hoãn ETH và rút khoản chờ. Mốc này nên được review kỹ.
5. **Nhánh ERC-20 của `claimPending` không thể đến được qua đường đi thật** (`_payout` chỉ hoãn ETH; ERC-20 revert nếu chuyển lỗi). Test T-16 dựng số dư chờ rút ERC-20 bằng `vm.store` để chứng minh nhánh đúng. **Quyết định của nhóm: không sửa contract, giữ nguyên nhánh này.** Test `vm.store` vẫn giữ để chứng minh nhánh đúng.
6. **Test migration phát hiện một điểm tinh tế:** cột tham chiếu bảng Web3 *mới* (`order_web3.checkout_group_id` → `checkout_groups.group_id`) khớp cột cha mới chứ không khớp collation của bảng Slopee cũ; quy tắc đúng là "khớp cột cha", và test collation `utf8mb4_unicode_ci` xác nhận migration phòng vệ xử lý được trường hợp DB cũ lệch collation (DDL ngây thơ lỗi errno 3780).
7. **Chưa kiểm chứng:** CI GitHub Actions thật (mới chạy từng lệnh cục bộ, gồm cả cổng coverage/ABI/Slither mới thêm vào `tests.yml`); frontend (Vitest) không đổi nên không chạy lại. Môi trường đo: Foundry 1.3.0, solc 0.8.20, MySQL 8.0.46, Slither 0.11.6.


---

### TUẦN 3: Liên kết ví, Tạo đơn, Báo giá có chữ ký (Backend Core)
- [~] **[A ➔ B] Thành viên A:** Hỗ trợ Thành viên B hoàn thiện Giai đoạn 0 (P0-03 đến P0-06). *(đã code, chờ review)*
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

### 5.1. Smart Contract Test Suite (Foundry: `contracts/test/*.t.sol`)
> `[~]` = đã viết và pass cục bộ bằng `forge test` (**139 test**, gồm 5 test vector chéo ngôn ngữ và 8 invariant), chờ review/CI. `[x] PASS` chỉ đặt khi CI xanh trên nhánh chính. T-01…T-07, T-14, T-23 (Tuần 1) cũng giữ `[~]` theo đúng quy tắc này dù PR Tuần 1 đã chốt.
| Mã test | Mô tả ca kiểm thử | Kết quả mong đợi | BRD / SRS | Tình trạng |
| :---: | :--- | :--- | :---: | :---: |
| **T-01** | Nạp tiền với báo giá hợp lệ (ERC-20 và ETH) | Thành công, đơn `LOCKED` | BR-06 | `[~] pass cục bộ (forge)` |
| **T-02** | Báo giá quá hạn; sai caller; chữ ký sai; signer thiếu role | Revert | BR-06 | `[~] pass cục bộ (forge)` |
| **T-03** | Trùng `orderId`; ETH khác amount; nạp token gửi kèm ETH; thiếu allowance | Revert | BR-06 | `[~] pass cục bộ (forge)` |
| **T-04** | Merchant trùng Buyer; Trọng tài làm Buyer/Merchant; duration ngoài [1h, 30d] | Revert | BR-03, 04 | `[~] pass cục bộ (forge)` |
| **T-05** | `confirmDelivery` gọi bởi người không có role; gọi khi đơn chưa `LOCKED` | Revert | BR-03 | `[~] pass cục bộ (forge)` |
| **T-06** | `earlyRelease` gọi bởi Buyer; gọi bởi người khác | Thành công / Revert | BR-03 | `[~] pass cục bộ (forge)` |
| **T-07** | `releaseAfterInspection` tại đúng mốc biên và trước 1 giây | Thành công / Revert | BR-03 | `[~] pass cục bộ (forge)` |
| **T-08** | Chia phí theo `feeBps` (0, 300, 1000); Kiểm tra làm tròn; Đổi `defaultFeeBps` không ảnh hưởng đơn cũ | Đúng công thức | BR-02 | `[~] pass cục bộ (forge): feeBps 0/300/1000, làm tròn xuống, đổi trần không ảnh hưởng đơn cũ` |
| **T-09** | `setDefaultFeeBps` > 1000; gọi bởi người không phải Admin | Revert | BR-02 | `[~] pass cục bộ (forge)` |
| **T-10** | `raiseDispute` trong hạn; sau hạn; gọi bởi người không phải Buyer | Thành công / Revert | BR-03 | `[~] pass cục bộ (forge): gồm biên đúng mốc hết hạn và trừ 1 giây` |
| **T-11** | `resolveDispute` đủ 2/3 chữ ký (Arbitrator + Buyer; Arbitrator + Merchant) | Thành công, đúng payout | BR-04 | `[~] pass cục bộ (forge): Trọng tài+Buyer, Trọng tài+Merchant, Buyer+Merchant` |
| **T-12** | 2 chữ ký cùng bên; 2 địa chỉ cùng vai Trọng tài; chữ ký người lạ; quá hạn deadline; sai nonce | Revert | BR-04 | `[~] pass cục bộ (forge): gồm 2 Trọng tài khác địa chỉ, sai nonce/amount/payee/deadline, chữ ký malleable` |
| **T-13** | Nộp lại chữ ký đã dùng sau khi đơn đã đóng | Revert | BR-04 | `[~] pass cục bộ (forge)` |
| **T-14** | `cancelIfUnfulfilled` trước và sau 14 ngày; bởi Buyer, Admin, người ngoài | Revert / OK / Revert | BR-05 | `[~] pass cục bộ (forge)` |
| **T-15** | `arbitratorForceResolve` trước/sau `disputeTimeout`; biên -1s revert, đúng mốc thành công | Revert / OK / Revert | BR-05 | `[~] pass cục bộ (forge): timeout 7/30/90 ngày, hai phía của mốc (R-02)` |
| **T-16** | Ví nhận từ chối ETH: Chuyển vào `pendingWithdrawals`; `claimPending` rút thành công | Thành công, không kẹt | BR-05 | `[~] pass cục bộ (forge): ví từ chối ETH (Merchant/người nhận phí/Buyer), claimPending, rút lại bị chặn` |
| **T-17** | Tấn công Reentrancy qua fallback ví nhận ETH và token độc hại | Bị ReentrancyGuard chặn | Bảo mật | `[~] pass cục bộ (forge): ví tái nhập qua claimPending; token độc hại khi nạp, giải ngân, phân xử` |
| **T-18** | Invariant/Fuzz: Số dư contract = Tổng đơn mở + Tổng sổ chờ rút | Luôn đúng | G-01 | `[~] pass cục bộ (forge invariant, 128 run × 100 lời gọi, ETH và token)` |
| **T-19** | Kiểm tra ma trận âm: Mọi cặp (state, method) không hợp lệ trong SRS mục 5 | Revert | Máy trạng thái | `[~] pass cục bộ (forge): 45 cặp âm, đúng lý do revert, không đổi trạng thái` |
| **T-20** | Báo giá có `disputeTimeout` < 7 ngày hoặc > 90 ngày; biên đúng 7 và 90 ngày | Revert / OK | BR-10 | `[~] pass cục bộ (forge)` |
| **T-21** | Hai đơn có `disputeTimeout` khác nhau chạy song song: độc lập thời gian timeout | Thành công độc lập | BR-10 | `[~] pass cục bộ (forge)` |
| **T-22** | Báo giá có `feeBps > defaultFeeBps`; hạ trần thì báo giá cũ bị từ chối | Revert / OK | BR-02, 06 | `[~] pass cục bộ (forge): hạ trần ⇒ báo giá cũ bị từ chối, báo giá mới được` |
| **T-23** | Báo giá có `q.buyer != msg.sender` | Revert | BR-06 | `[~] pass cục bộ (forge)` |
| **T-24** | `resolveDispute` với `deadline >= disputedAt + disputeTimeout` | Revert | BR-04, 05 | `[~] pass cục bộ (forge): deadline = mốc, > mốc, vô hạn đều revert; mốc − 1 thành công` |
| **T-25** | Nạp gom 3 đơn 3 shop: 1 lần `transferFrom`, tăng số dư đúng tổng, 3 sự kiện `OrderCreated` | Thành công | BR-11 | `[~] pass cục bộ (forge): đúng 1 transferFrom với đúng tổng; cả ETH` |
| **T-26** | Lô nạp rỗng; lô > 5 đơn; lệch độ dài mảng quotes và sigs | Revert | BR-11 | `[~] pass cục bộ (forge)` |
| **T-27** | Trùng `orderId` ngay trong một mảng lô nạp | Revert, số dư không đổi | BR-11, G-01 | `[~] pass cục bộ (forge)` |
| **T-28** | Một báo giá trong lô lỗi (quá hạn, sai chữ ký, vượt trần phí) | Toàn bộ lô Revert | BR-11 | `[~] pass cục bộ (forge): 4 loại lỗi × 3 vị trí trong lô` |
| **T-29** | Lô nạp trộn nhiều loại token; nạp ETH sai tổng `msg.value` | Revert | BR-11 | `[~] pass cục bộ (forge)` |
| **T-30** | Mọi điều kiện đơn lẻ áp dụng chuẩn xác cho từng phần tử của lô | Revert nếu vi phạm | BR-06, 11 | `[~] pass cục bộ (forge): 8 loại vi phạm trên phần tử giữa lô` |
| **T-31** | Sau khi nạp gom: Đơn A early release, đơn B dispute hoàn tiền, đơn C tự giải ngân | Độc lập hoàn toàn | BR-11 | `[~] pass cục bộ (forge)` |
| **T-32** | Đo gas nạp lô 5 đơn (mục tiêu < 3.000.000 gas) | Đạt ngưỡng gas | BR-11 | `[~] pass cục bộ: 1.229.409 gas (token), 1.099.331 gas (ETH)` |
| **T-33** | Fuzz invariant: Gọi ngẫu nhiên cả nạp đơn và nạp gom | INV-01..07 luôn đúng | G-01 | `[~] pass cục bộ (forge invariant: INV-01…07, nạp đơn lẻ và nạp gom)` |
| **T-34** | So sánh nạp đơn lẻ và nạp lô 1 phần tử: Trạng thái và event giống hệt nhau | Khớp 100% | BR-11 | `[~] pass cục bộ (forge): so sánh trạng thái đơn, số dư và từng log` |

---

### 5.2. Integration, System & Backend API Test Suite
> `[~]` = test đã viết và pass cục bộ, chờ CI/PR; `[x] PASS` chỉ đặt sau khi CI xanh trên nhánh chính.
> Ngoài ma trận bên dưới, Tuần 2 thêm **31 test migration Web3** (`test/unit_test/test_web3_migrations_static.py` 6 test; `test/integration_test/test_web3_migrations.py` 25 test trên MySQL 8.0 thật): DB mới == DB nâng cấp, idempotent, collation lệch, MyISAM bị chặn, CHECK/UNIQUE/FK/ENUM. Toàn bộ pytest: **360 pass, 0 skip** (có MySQL).

| Mã test | Phạm vi kiểm thử | Tiêu chuẩn đánh giá | Tình trạng |
| :---: | :--- | :--- | :---: |
| **I-01** | Liên kết ví: Nonce dùng lại, nonce hết hạn, chữ ký sai, ví đã thuộc user khác | AC-01 / Trả đúng mã lỗi HTTP | `[ ] PASS` |
| **I-02** | Báo giá: Quy đổi VND ➔ token chuẩn xác, hợp đồng chấp nhận chữ ký Python | AC-01, AC-02 | `[~] một phần: chữ ký Python được contract chấp nhận (forge + smoke_week1.sh); quy đổi VND→token ở tuần 3` |
| **I-03** | Indexer: Xử lý trùng tx_hash/log_index không ghi đôi, khởi động lại, phục hồi con trỏ | AC-08 / Tính Idempotent | `[ ] PASS` |
| **I-04** | Nhóm hàng: Đơn nhiều nhóm lấy `max()`, đổi chính sách không ảnh hưởng đơn cũ | AC-12 | `[ ] PASS` |
| **I-05** | Đồng bộ thời gian: `now_chain()` theo sát block Anvil; tua thời gian cấp quote mới chuẩn | AC-02 | `[ ] PASS` |
| **I-06** | Đồng bộ ngược: Cập nhật `order_web3` tự động cập nhật `orders.status` cũ; Chặn route ghi đè cũ | AC-08 / Bảng ánh xạ 5.1 | `[ ] PASS` |
| **I-07** | Giỏ 3 shop: Tạo đúng 3 đơn 1 group, tổng token khớp lệnh, Indexer xóa đúng giỏ hàng | AC-14 | `[ ] PASS` |
| **A-01** | Mọi API yêu cầu token: Không token hoặc token hết hạn trả HTTP 401 | Mục 15 (P0-01) | `[~] pass cục bộ` |
| **A-02** | Kiểm tra quyền Role: User/Seller gọi API Admin bị chặn HTTP 403; Shipper chỉ xem đơn gán | Mục 15 (P0-02) | `[~] pass cục bộ` |
| **A-03** | Kiểm tra sở hữu dữ liệu: Xem đơn, giỏ, shop của người khác bị 403 hoặc 404 | Mục 15 (P0-03) | `[~] pass cục bộ (unit + MySQL 8.0 thật)` |
| **A-04** | Đăng ký tài khoản với role `admin` hoặc `shipper` bị từ chối | Mục 15 (P0-02) | `[~] pass cục bộ` |
| **A-05** | Đua tranh đặt hàng (Race condition): Tồn kho không bao giờ bị âm | Mục 15 (P0-05) | `[~] pass cục bộ (unit + race MySQL 8.0 thật, 3 lần liên tiếp)` |
| **A-06** | Giới hạn brute-force: Nhập sai PIN hoặc Password quá 5 lần bị khóa tạm | Mục 15 (P0-05) | `[~] pass cục bộ (unit + MySQL 8.0 thật)` |
| **A-07** | Endpoint `/api/shops/migrate` đã bị xóa bỏ; Không còn API cấp số dư vô hạn | Mục 15 (P0-04) | `[~] unit pass cục bộ` |

---

### 5.3. Frontend Logic & Unit Test Suite (Vitest)
| Mã test | Mô tả ca kiểm thử | Kết quả mong đợi | Tình trạng |
| :---: | :--- | :--- | :---: |
| **F-01** | Hàm định dạng `formatVND`: Kiểm tra số nguyên, làm tròn, số 0, số cực lớn, không còn ký hiệu `$` | Chuẩn định dạng tiếng Việt | `[~] pass cục bộ` |
| **F-02** | Reducer nạp tiền (`depositReducer`): Đủ allowance bỏ bước approve, từ chối ví (4001), hết hạn quote | Chuyển state chính xác | `[ ] PASS` |
| **F-03** | Ánh xạ lỗi tiếng Việt: `BATCH_TOO_LARGE`, `FEE_CAP_CHANGED`, `Invalid batch size` | Hiển thị thông báo dễ hiểu | `[ ] PASS` |
| **F-04** | Client API chung: Tự gắn `Authorization`, tự động xóa token và chuyển trang khi gặp 401 | Hoạt động thông suốt | `[~] pass cục bộ (client.test.js; chỉ đăng xuất khi mã phiên, không phải mọi 401)` |
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
