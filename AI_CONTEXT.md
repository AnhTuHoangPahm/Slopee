# AI_CONTEXT.md — Ngữ cảnh dành cho trợ lý AI

> Đọc file này **trước khi sửa code**. Tài liệu đi kèm: `ARCHITECTURE.md` (kiến trúc, quy ước, hợp đồng giữa các tầng) và `SKELETON.md` (bản đồ file/hàm/API — cập nhật cùng PR khi thêm/sửa hàm hoặc route). Nó tóm tắt dự án, quy tắc bất biến, trạng thái hiện tại và các bẫy đã gặp.
> Tiến độ chi tiết nằm ở `PROGRESS.md` (nguồn duy nhất để cập nhật trạng thái). Đặc tả gốc (BRD/SRS/SDD) **đã đóng băng**, không sửa.

---

## 1. Dự án là gì

**Slopee** là bản sao Shopee (Flask + MySQL + React). Đồ án 10 tuần, nhóm 3 người (A, B, C), đang xây **mô-đun Web3 Escrow MVP**:
người mua ký quỹ tiền vào smart contract (Anvil local, token `MockUSD`), tiền chỉ được giải ngân khi giao hàng thành công / hết hạn kiểm tra / phân xử 2-trên-3 chữ ký EIP-712.

- **Non-custodial (BR-01):** backend **không bao giờ** giữ khóa riêng của Buyer/Merchant. Chỉ có 3–4 khóa vận hành của sàn (quote signer, arbitrator, shipper/relayer) nạp từ biến môi trường.
- **Blockchain là nguồn sự thật (BR-09):** trạng thái đơn Web3 trong MySQL **chỉ do Indexer ghi** (từ `LOCKED` trở đi). Giao diện không tin biên nhận ví.
- **Chỉ chạy trên Anvil (chainId 31337, `--block-time 2`)**, không mainnet, không tiền thật.

### Tài liệu đặc tả (đóng băng) và thứ tự ưu tiên khi mâu thuẫn
1. `BRD-SLOPEE-MVP-01 v5.3` — nghiệp vụ, BR-01…BR-11, AC-01…AC-14
2. `SRS-SLOPEE-MVP-01 v5.3` — use case UC-00…UC-09, máy trạng thái, EIP-712, REST API, DB, test matrix
3. `SDD-SLOPEE-MVP-01 v1.2` — kiến trúc Hexagonal, DD-01…DD-12, thuật toán, lỗi R-01…R-09
4. `PROGRESS.md` — kế hoạch tuần, Phase 0, test tracker (được phép cập nhật)

Đặc tả đã được **tách thành tệp nhỏ trong `docs/spec/`** (mục 9): mở đúng tệp cần theo bảng tra, **không** mở nguyên BRD/SRS/SDD.

Nếu code hiện có lệch đặc tả, **báo cho người dùng** thay vì tự đổi đặc tả. Các quyết định lệch đã biết ở mục 6.

---

## 2. Cấu trúc repo (hiện tại)

```
backend/                Flask + MySQL (không phải package; chạy từ thư mục backend/)
  app.py                tạo app, đăng ký blueprint + handler lỗi chung, CLI `seed-admin`/`migrate`, JSON provider
  config.py             DB_*, SECRET_KEY (bắt buộc), AUTH_TOKEN_TTL_SECONDS, DEBUG (chỉ khi SLOPEE_ENV=development)
  auth_utils.py         token ký (itsdangerous) + decorator require_auth (P0-01)
  money.py              to_vnd / format_vnd — tiền VND số nguyên (P0-07)
  errors.py             ApiError + handler lỗi chung gắn vào blueprint/app; client chỉ nhận lỗi chung, chi tiết vào log (P0-06)
  validation.py         json_body(), get_str/get_int/get_enum, validate_url, get_url_list (P0-06)
  throttle.py           khóa tạm sai mật khẩu/PIN, lưu bảng authAttempts (P0-05)
  guards.py             is_web3_order() — đơn có dòng order_web3 (P0-03)
  migrate.py            bộ chạy migration có số thứ tự + CLI; split_sql() (P0-04)
  dbschema.py           hàm information_schema cho migration .py (FK, cột, index)
  json_provider.py      Decimal -> số (int nếu nguyên) khi jsonify
  admin_seed.py         seed_admin(conn, ...) dùng cho CLI
  init_db.py            tạo DB từ schema.sql (KHÔNG còn tạo admin); DB mới: đánh dấu migration đã áp dụng
  schema.sql            lược đồ MỚI NHẤT cho DB tạo mới (đã gồm mọi migration, kể cả 18 bảng Web3 sau dấu mốc `WEB3 ESCROW`); 4 cột tiền DECIMAL(15,0)
  migrations/           0001 money_to_vnd.sql, 0002 product_fk_snapshots.py, 0003 reviews_dedupe.py, 0004 auth_attempts.sql,
                        0005 order_line_settlement.py (hủy đơn paid hoàn tiền không tạo tiền). Web3: 0006 wallets … 0020 shipper (15 tệp, tuần 2)
  routes/               auth, admin, carts, payments, products, reviews, shops
  slopee_web3/          MÔ-ĐUN WEB3 (tuần 3), kiến trúc Hexagonal; import top-level `slopee_web3.…` (backend/ nằm trên sys.path)
    domain/             thuần, KHÔNG I/O (money, policy, quote/docHash, wallet/SIWE, order_state, errors) — test_w3_architecture.py canh import
    ports/              Clock/Signer/Chain/Repositories (Protocol)
    application/        WalletService (UC-00), QuoteService (UC-01) — chỉ phụ thuộc domain + ports
    adapters/           env_signer (EIP-712), web3_chain (web3.py), mysql_repos (UnitOfWork), clock, logging_filter,
                        flask_api/ (routes + container = điểm lắp ghép), indexer/ (KHUNG: GET_LOCK, con trỏ, chain_events; handlers rỗng)
    settings.py         Web3Settings.from_env() (backend/.env.web3 do bootstrap.sh sinh)
frontend/               React 19 + Vite + React Router 7 (JavaScript, không TypeScript)
  src/lib/client.js     CHUẨN: phiên (sessionStorage), authFetch, getUser/setSession/clearSession, API_ORIGIN (VITE_API_BASE)
  src/lib/format.js     CHUẨN: formatVND (hàm định dạng tiền DUY NHẤT), shortAddress
  src/lib/chain.js      đọc/kiểm deployments/local.json (chainId 31337, địa chỉ contract), tham số wallet_addEthereumChain
  src/lib/eip712.js     kiểu/digest/ký EIP-712 từ shared/eip712/types.json (ethers v6)
  src/hooks/useWallet.js  WalletProvider + useWallet (EIP-1193/MetaMask)
  src/pages/Wallet.jsx  UC-00 (route /wallet); src/components/Web3CheckoutPanel.jsx khung thanh toán Web3 trong /checkout (nút Ký quỹ khóa tới tuần 4)
  src/api/web3.js, lib/errors.js, lib/web3Checkout.js, lib/walletLink.js, mocks/web3Mock.js (VITE_WEB3_MOCK=true)
  src/components/RequireRole.jsx  route guard theo role (chỉ là tiện lợi UI; quyền thật ở backend)
  src/api/http.js, src/utils/formatVND.js  CHỈ re-export lib/ để không vỡ import cũ; mã mới import từ lib/
  src/api/*.js          các client REST (auth, carts, payments, shops, products, admin)
  src/pages, components, __tests__, tests/ (Playwright)
contracts/              Foundry (solc 0.8.20, OpenZeppelin 5.0.2): src/{MockUSD,SlopeeEscrowMaster}.sol, script/Deploy.s.sol, test/*.t.sol
                        lib/ cài bằng scripts/install_contract_deps.sh (bị .gitignore)
shared/eip712/          types.json (kiểu EIP-712 DUY NHẤT, đã khóa) + vectors.json (sinh bằng scripts/gen_eip712_vectors.py)
scripts/                bootstrap.sh (dựng Anvil + deploy một lệnh), smoke_week1.sh, install_contract_deps.sh, gen_eip712_vectors.py, export_abi.sh (xuất/kiểm ABI)
deployments/local.json  do bootstrap.sh sinh (bị .gitignore); frontend đọc bản chép ở frontend/public/deployments/
test/                   pytest (conftest.py: FakeCursor/fake_db/AttemptsStore, unit_test/, integration_test/)
.github/workflows/tests.yml   CI: pytest + MySQL service, vitest, build
docs/                   tài liệu
  split_spec/           đặc tả tách nhỏ BRD/SRS (brd-*, srs-*.md + INDEX.md). **Thực tế thư mục tên `split_spec/`, chưa có tệp `sdd-*.md`**:
                        SDD nằm trong MỘT tệp `docs/SDD TDD - …md` (tra theo số mục ##). Bảng mục 9 dưới đây còn ghi `docs/spec/` và `sdd-*`
                        theo kế hoạch cũ; `scripts/split_spec.py` chưa có trong repo.
```

Cấu trúc **sắp tới** theo SDD (chưa tồn tại): `backend/slopee_web3/` (domain/application/ports/adapters), `frontend/src/{lib/errors.js, hooks/*}` còn lại, `pages/Wallet.jsx` và các trang Web3.

---

## 3. Lệnh thường dùng

```bash
# Backend (từ thư mục gốc repo)
export SLOPEE_ENV=test SECRET_KEY=test-secret-key        # conftest tự đặt nếu thiếu
export DB_HOST=localhost DB_USER=<user> DB_PASSWORD=<pw>  # cho test cần MySQL thật
python -m pytest test -q                    # test MySQL tự skip nếu không kết nối được

# Chạy server local
cd backend && cp .env.example .env         # điền SECRET_KEY ngẫu nhiên
python init_db.py
flask --app app seed-admin                  # tạo admin (mật khẩu >= 12 ký tự)
python app.py                               # cổng 5000

# Web3 (Foundry cần trong PATH; xem scripts/)
./scripts/bootstrap.sh                      # Anvil --block-time 2 + deploy + deployments/local.json + backend/.env.web3
./scripts/smoke_week1.sh                    # smoke test trên Anvil thật (cần Anvil sạch vừa bootstrap)
(cd contracts && forge test)                # 139 test contract (gồm invariant ~1,5 phút) + vector EIP-712
python scripts/gen_eip712_vectors.py --check   # vectors.json còn khớp script sinh?

# Frontend
cd frontend && npm run dev | npx vitest run | npm run build | npm run lint | npm run test:e2e
```

Biến môi trường: `SECRET_KEY` (bắt buộc trừ khi `SLOPEE_ENV` là `development`/`test`), `AUTH_TOKEN_TTL_SECONDS` (mặc định 3600), `DB_HOST/DB_USER/DB_PASSWORD/DB_NAME`, `AUTH_MAX_ATTEMPTS` (mặc định 5), `AUTH_LOCK_SECONDS` (mặc định 900). `debug` chỉ bật khi `SLOPEE_ENV=development`.

Migration: DB mới → `python init_db.py` (đã gồm mọi migration). **DB cũ → `cd backend && python migrate.py`** (hoặc `flask --app app migrate`; `status` để xem). Thêm migration = tạo `migrations/NNNN_ten.sql|.py` (idempotent, không dùng route HTTP) **và** phản ánh vào `schema.sql`.

---

## 4. Quy tắc bất biến khi viết code

**Tiền**
- Mọi số tiền Slopee là **VND số nguyên** (`DECIMAL(15,0)`). Dùng `money.to_vnd()`; **cấm** `float`, `toFixed(2)`, ký hiệu `$`.
- Frontend định dạng tiền chỉ bằng `formatVND` (`Intl.NumberFormat('vi-VN')`).
- Token on-chain (`amount_raw`, uint256) lưu `VARCHAR(78)`, xử lý bằng `int`/`Decimal` ở Python, `BigInt` ở JS, **truyền JSON dưới dạng chuỗi**. Quy đổi VND→token làm tròn **lên**: `ceil(price_vnd * 10^dec * 10^4 / fx_scaled)`; tổng lô = tổng từng shop đã làm tròn.
- MockUSD: 6 decimals.

**Xác thực / phân quyền (P0-01/02, đã làm)**
- Danh tính **chỉ** lấy từ token: `g.user_id`, `g.role`. **Cấm** nhận `userId`/`sellerId` từ body hay URL.
- Dùng `@require_auth` hoặc `@require_auth('seller')` / `@require_auth('admin')` từ `auth_utils`. `admin_bp` đã khóa bằng `before_request`.
- Token gửi qua header `Authorization: Bearer ...`. Lỗi xác thực trả `{"error","code"}` với `code` ∈ `auth_required | token_expired | token_invalid | forbidden`.
- Đăng ký chỉ cho role `user`/`seller`. Admin chỉ tạo bằng CLI. Không có phương thức thanh toán nào được cấp số dư tự động (balance khởi tạo 0).
- Frontend: phiên ở **`sessionStorage`** (`token`, `user`), không dùng `localStorage`. Tự đăng xuất chỉ khi `code` thuộc nhóm phiên (không dựa vào status 401, vì sai PIN/mật khẩu cũng trả 401).

**Dữ liệu / SQL**
- SQL luôn tham số hóa. Chuyển trạng thái dùng câu lệnh có điều kiện (`UPDATE ... WHERE status=:old`, kiểm `rowcount`).
- Khóa chính của Slopee là `VARCHAR(36)` UUID (không phải INT). Địa chỉ ví lưu và so sánh **chữ thường**.
- Mọi mốc thời gian on-chain lấy từ `block.timestamp` (không `NOW()` máy chủ) để replay ra kết quả giống hệt. `now_chain() = max(đồng hồ hệ thống, thời gian block mới nhất)`.

**Web3 (sắp làm)**
- Trạng thái đơn: `PENDING_PAYMENT → LOCKED → DELIVERED → (COMPLETED | DISPUTED → COMPLETED/REFUNDED)`, `LOCKED → REFUNDED` (hủy sau 14 ngày), `PENDING_PAYMENT → EXPIRED`. `COMPLETED`/`REFUNDED` là cuối.
- Ánh xạ sang `orders.status` cũ: PENDING_PAYMENT→`pending`, LOCKED→`paid`, DELIVERED→`shipped`, DISPUTED→`shipped` (+ huy hiệu), COMPLETED→`received`, EXPIRED/REFUNDED→`cancelled` (hoàn tồn kho). Chỉ **một** hàm `sync_legacy_status` được ghi `orders.status` của đơn Web3; `PUT /api/payments/orders/:id` phải từ chối đơn Web3 (`WEB3_ORDER_MANAGED`).
- Giỏ nhiều shop: 1 `checkout_group` → N đơn độc lập (mỗi shop một Merchant), tối đa **5 shop**, nạp bằng `depositEscrowBatch` (nguyên tử). Chỉ xóa `cartItems` khi đơn đã `LOCKED` (Indexer làm).
- Báo giá EIP-712 `OrderQuote(orderId,buyer,merchant,token,amount,inspectionDuration,disputeTimeout,feeBps,docHash,deadline)`; phán quyết `DisputeResolution(orderId,payoutTo,amount,nonce,deadline)`. Một file `shared/eip712/types.json` dùng chung cho Python, JS, Solidity.
- Backend ký `feeBps = min(PLATFORM_FEE_BPS, defaultFeeBps on-chain)`; `deadline` phán quyết = `min(now_chain + TTL, disputedAt + disputeTimeout - 1)`.
- Kiến trúc Hexagonal cho `slopee_web3/`: `domain` không import Flask/web3.py; test import kiểm tra (T-ARCH-01).
- Mã lỗi API: `{code, message}` tiếng Việt: `WALLET_NOT_LINKED, WALLET_TAKEN, NONCE_INVALID, BAD_SIGNATURE, QUOTE_EXPIRED, INVALID_STATE, FORBIDDEN, POLICY_OUT_OF_RANGE, CHAIN_TX_FAILED, FEE_CAP_CHANGED, BATCH_TOO_LARGE, WEB3_ORDER_MANAGED`.

**Không làm**
- Không lưu/ghi log private key, chữ ký người dùng, seed phrase. Không `tx.origin`. Không dùng `float` cho tiền.
- Không thêm tính năng ngoài MVP (fiat, COD, mainnet, partial refund, pause/proxy, nhiều Merchant/đơn on-chain).
- Không sửa BRD/SRS/SDD; không tự ý đổi `SlopeeEscrowMaster` sau khi đóng băng contract (cuối tuần 2).

---

## 5. Trạng thái hiện tại (xem `PROGRESS.md` để biết chi tiết)

| Việc | Trạng thái | Ghi chú |
| --- | --- | --- |
| P0-01 token ký + `require_auth` | **Đã review 14/10/2026 (PR #2)** | B |
| P0-02 khóa role/admin, seed admin CLI, bỏ cấp số dư | **Đã review 14/10/2026 (PR #2)** | B |
| P0-07 VND (`DECIMAL(15,0)`, `formatVND`) | **Đã review 14/10/2026 (PR #2)** | B+C |
| P0-08 cập nhật test + race test MySQL thật + CI | **Đã review 14/10/2026 (PR #2)** | B+C |
| P0-03 kiểm tra quyền sở hữu tài nguyên, `WEB3_ORDER_MANAGED` | **Đã review 14/10/2026 (PR #2)** | A |
| P0-04 xóa `/api/shops/migrate`, runner `schema_migrations`, dọn schema `reviews/reviewImages` | **Đã review 14/10/2026 (PR #2)** | A |
| P0-05 `FOR UPDATE`, `UPDATE ... WHERE inStock >= qty`, khóa tạm sau 5 lần sai PIN/mật khẩu | **Đã review 14/10/2026 (PR #2)** | A |
| P0-06 tắt `debug=True`, lỗi chung cho client, validate body JSON | **Đã review 14/10/2026 (PR #2)** | A |
| **Tuần 1**: Foundry + `MockUSD` + `SlopeeEscrowMaster` (nạp đơn/giao/giải ngân/hủy quá hạn), `bootstrap.sh`, `lib/client` + `RequireRole` + `useWallet`, `shared/eip712` (types + vectors, kiểm chéo Python/JS/Solidity) | Đã code, chờ review (46 test forge, 70 vitest, pytest xanh) | A+B+C |
| Quyết định nhóm sau Phase 0: hủy đơn `paid` hoàn tiền, COD không cộng người bán, giữ FK `RESTRICT`, migration Web3 từ `0006` | Đã code, chờ review | A |
| **Tuần 2**: contract hoàn chỉnh (tranh chấp, thoát hiểm, nạp gom, `claimPending`, quản trị) + bộ test M1 + ABI đóng băng; migration MySQL Web3 `0006`–`0020` | Đã code, chờ review (139 test forge, 360 pytest trên MySQL 8) | A+B |
| **Tuần 3**: UC-00 (liên kết ví) + UC-01 (tạo đơn, báo giá ký EIP-712, cấp lại báo giá) + khung Indexer + `Wallet.jsx` + khung thanh toán Web3 + vector `walletLink` | Đã code, chờ review (580 pytest gồm 5 test trên Anvil thật, 150 vitest). Các quyết định đã chốt 14/10/2026: xem mục 6 | B+C |
| **Tuần 4**: Event Indexer handler `OrderCreated` -> `LOCKED` (đối soát báo giá, `orders.status=paid`, xóa giỏ hàng) + bảo vệ reorg con trỏ; tích hợp Checkout nạp gom 2 bước ví (`approve` + `depositEscrowBatch`), hook `usePolling`; đạt cột mốc **M2** | **Đã hoàn thành** (592 pytest, 203 vitest, đạt mốc M2) | B+C |
| **Tuần 5**: Cổng Shipper (`/shipper/orders`), Relayer gửi `confirmDelivery` (`tx_outbox`), Scheduler (`AutoRelease`, `QuoteExpirySweeper`), Indexer handler `Delivered`/`Completed`/`Refunded`/`Disputed`; UI `MyOrders` nhóm theo lô + đồng hồ kiểm tra + nút "Đã nhận hàng" (`earlyRelease`) và "Khiếu nại" | **Đã hoàn thành** (CI Run #20 xanh 100%: 701 pytest, 302 vitest, 139 forge) | A+B+C |
| **Tuần 6**: Luồng Tranh chấp & Phân xử 2/3 chữ ký EIP-712 (`dispute-note`, đề xuất phán quyết, tiếp nhận chữ ký, relayer nộp `resolveDispute`, Indexer `DisputeResolved`/`ArbitratorForceResolved`, tác vụ `DisputeSigExpiry`, UI Admin/Dispute) + hoàn thiện đồng hồ đếm ngược và polling thích ứng (mục 10-11 của Tuần 5) | **Đã hoàn thành** (chạy cục bộ trên MySQL 8.0 và Anvil thật: 955 pytest pass + 1 skip, 485 vitest pass + 17 skip; số liệu từng phần ở các khối ghi chú Tuần 6 trong `PROGRESS.md`) | A+B+C |
| **Tuần 7 (phần C)**: nút "Hủy đơn & nhận lại tiền" khi đơn `LOCKED` quá 14 ngày chưa giao (`cancelIfUnfulfilled`) trong `Web3OrderPanel`; thêm `chain_created_at` vào `GET /api/orders/:code/status` và `web3` của `GET /api/payments/orders` | **Đã hoàn thành test cục bộ** (MySQL 8.0 thật, KHÔNG có Anvil: vitest pass, pytest pass, build xanh; 8 test Anvil skip chờ chuỗi thật). Chi tiết: `PROGRESS.md` ghi chú Tuần 7 phần C | C (+ B xem phần backend) |
| **Tuần 7 (phần A)**: màn Merchant trong `SellerDashboard` (`components/MerchantWeb3Panel.jsx`): danh sách đơn Web3 của shop (`GET /api/merchant/orders`, mới), tổng quan tiền ký quỹ/đã nhận, liên kết sang `/disputes/:code` cho đơn `DISPUTED`, và rút khoản chờ rút `claimPending` | **Đã hoàn thành** (chạy cục bộ trên MySQL 8.0, KHÔNG có Anvil: 960 pytest pass + 24 skip, 561 vitest pass + 20 skip, `vite build` xanh; chi tiết ở `PROGRESS.md` ghi chú Tuần 7 phần A) | A |
| Phần còn lại của UC-07 (Trọng tài xử đơn phương), UC-08/UC-09, 4 vai trò hoàn chỉnh, đối soát số dư (`reconcile.py`), E-04 | Chưa bắt đầu (trừ phần A và C ở các dòng Tuần 7) | Tuần 7–10 |

**Đã xử lý ở P0-03…06 (đã review 14/10/2026, PR #2; test MySQL thật vẫn chờ CI GitHub xác nhận):** chủ sở hữu cart item/đơn/sản phẩm/ảnh/biến thể (không phải chủ → 404); đơn Web3 bị từ chối bằng `409 WEB3_ORDER_MANAGED`; chuyển trạng thái đơn theo bảng hợp lệ; checkout khóa `FOR UPDATE` + `UPDATE` có điều kiện; khóa tạm 5 lần sai mật khẩu/PIN (`429`); route migrate đã bỏ; `debug` theo môi trường; lỗi chung, không còn `str(e)`; validate body.

**Đã quyết và áp dụng (chờ review):** hủy đơn `paid` hoàn kho + hoàn tiền người mua và thu lại từ người bán (`409 refund_unavailable` nếu người bán không đủ số dư); COD/`cash` không cộng số dư người bán; `orders.userId` giữ `RESTRICT`, admin xóa user có đơn → `409 user_has_orders`. Chi tiết: `PROGRESS.md` ghi chú Phase 0. Đã chạy toàn bộ test backend trên MySQL 8.0 thật (329 pass).

**Còn mở (đừng giả định đã an toàn):**
- Dữ liệu legacy trước migration `0005`: đơn có `productId = NULL` không thu lại được tiền từ người bán khi hủy (người mua vẫn được hoàn, tức tiền có thể bị tạo ra); đơn COD cũ từng cộng tiền cho người bán và **không được sửa hồi tố**. Chỉ đúng với dữ liệu cũ; đơn tạo sau `0005` bảo toàn tiền. Đừng coi số dư legacy là đối soát được; DB demo nên tạo lại bằng `init_db.py`.
- Token chứa `role` và **không** kiểm lại DB: đổi role/xóa user thì token cũ còn hiệu lực đến khi hết hạn.

---

## 6. Điểm lệch giữa code hiện tại và đặc tả (cần nhóm xác nhận)

| Chủ đề | SDD/SRS nói | Code hiện tại | Ghi chú |
| --- | --- | --- | --- |
| TTL token | ví dụ 8 giờ | mặc định `3600` s, đặt qua `AUTH_TOKEN_TTL_SECONDS` | đổi env nếu muốn 8h |
| Decorator | `require_auth(roles=[...])`, `g.user` | `require_auth('seller')`, `g.user_id`/`g.role` | dùng API thực tế |
| Frontend client | `lib/client.js`, `lib/format.js`, `hooks/` | `lib/` là bản chuẩn; `api/http.js`, `utils/formatVND.js` chỉ re-export | **Đã chốt** (tuần 1): một nguồn sự thật, không vỡ import/test cũ |
| Route theo người dùng | `/<userId>` | `/api/carts/`, `/api/payments/`, `/api/payments/orders`, `/api/auth/reviews/me`, `/api/shops/me`, `/api/shops/me/name` | không còn xem shop theo seller ID |
| `add_product` | nhận `shopId` | shop suy ra từ token seller | |
| Số dư mới | "số dư giả lập ban đầu đổi sang VND" (SDD 16.3 bước 8) | số dư mới = 0 (S-04) | checkout ngân hàng cũ cần nạp tiền thủ công; COD vẫn chạy |
| Migration | `001_wallets.sql`…`015_shipper.sql` + `schema_migrations` | runner `migrate.py` + `0001…0005` (4 chữ số) | **Đã chốt:** Web3 đánh số từ `0006` (`001`→`0006` … `015`→`0020`); tên tệp là khóa trong `schema_migrations` |
| Mã lỗi API cũ | `{code, message}` tiếng Việt | `{error, code}` tiếng Anh (`not_found`, `INVALID_STATE`, `WEB3_ORDER_MANAGED`, `too_many_attempts`, `internal_error`…) | API Web3 mới theo SRS; nhóm chốt ngôn ngữ thông báo |
| `POST /api/wallet/nonce` | SDD 10.2: "không có đầu vào" | nhận `{address}` | **Đã chốt 14/10/2026, đã có test.** Thông điệp SIWE phải chứa địa chỉ nên Backend cần biết địa chỉ lúc phát nonce. SDD/SRS không sửa (quy ước repo: tài liệu gốc giữ nguyên, lệch ghi ở đây) |
| `POST /api/wallet/link` | SDD 10.2: `address, signature` | thêm `nonce` **tùy chọn** (bỏ thì dùng nonce còn hạn mới nhất của chính tài khoản) | **Đã chốt 14/10/2026, đã có test.** Ví/địa chỉ/tài khoản khác đều bị `BAD_SIGNATURE` vì thông điệp chứa địa chỉ và mã tài khoản |
| Cấp lại báo giá | SDD 5.3f: đặt deadline mới chung, đọc lại trần phí | làm mới **cả tỷ giá**, ví hiện tại và phí; giữ `price_vnd`, thời hạn, `docHash`, `onchain_order_id` | **Đã chốt 14/10/2026 (không đổi).** `amount_raw` có thể đổi giữa hai lần báo giá; người dùng thấy số mới trước khi ký |
| `POST /api/orders/eligibility` | không có trong SDD 10.2 | endpoint chỉ đọc: shop trong giỏ đã liên kết ví nhận tiền chưa | Đã chốt 14/10/2026 |
| `GET /api/merchant/orders` | SDD 9.2 có màn `/merchant/orders` nhưng SDD 10.2 không có API | endpoint chỉ đọc, role `seller`: đơn Web3 của shop (từ `LOCKED`) + số dư chờ rút của các ví Merchant | **Đã chốt 23/10/2026 (nhóm xác nhận), đã có test.** Danh tính chỉ từ token. Số dư chờ rút là bản dẫn xuất từ sự kiện; khi rút, giao diện đọc lại `pendingWithdrawals` trên chuỗi |
| Màn Merchant Web3 | SDD 9.2: route riêng `/merchant/orders`, `/merchant/pending` | một khung `MerchantWeb3Panel` ngay trong `/seller` (`SellerDashboard`) | **Đã chốt 23/10/2026 (nhóm xác nhận).** `PROGRESS.md` Tuần 7 ghi đúng `pages/SellerDashboard.jsx`; thêm route riêng nếu sau này cần |

---

## 7. Bẫy đã gặp khi làm việc trong repo này

- **Hai đường import:** test import `backend.routes.auth` nhưng route nội bộ import `routes.auth` / `auth_utils` (do `conftest.py` thêm `backend/` vào `sys.path`). Module `backend.routes.x` và `routes.x` là **hai object khác nhau**: `mocker.patch('backend.routes.payments.get_db_connection')` chỉ có tác dụng với module mà blueprint đã đăng ký trong `conftest.py`. Khi patch hàm dùng chéo module, kiểm tra kỹ module nào đang được gọi.
- **`conftest.py` tự đặt** `SLOPEE_ENV=test` và `SECRET_KEY` trước khi import app; nếu thêm entrypoint mới đọc `config` sớm, đảm bảo env có trước.
- **Decimal từ pymysql:** JSON mặc định của Flask trả `Decimal` dạng *chuỗi*. App dùng `SlopeeJSONProvider` để trả số; app trong `conftest.py` cũng đã gắn provider này.
- **`test_*` cần MySQL thật** dùng fixture `mysql_db`/`db_conn` (tạo DB `slopee_test_<pid>` từ `schema.sql`, xóa sau khi xong, skip nếu không kết nối được). Cần user có quyền `CREATE DATABASE`.
- **Mock con trỏ DB** chỉ dùng cho logic thuần. Mọi đường liên quan tiền, tồn kho, trạng thái đơn, phân quyền phải có test trên MySQL thật.
- **CHECK constraint** chỉ được MySQL ≥ 8.0.16 thực thi; chưa chạy trên MariaDB/MySQL cũ.
- **Tài khoản không có PIN** (vd. admin) nay trả `401 pin_not_set` (P0-05). **`reviewImages.id`** là `VARCHAR(36)` không tự tăng: `reviews.py` phải tự cấp UUID (S-13).
- **Test W3 chạy trên database riêng (đã chốt 14/10/2026):** `test/integration_test/conftest.py` tạo DB riêng cho mỗi module `test_w3_*` và xóa sau khi xong, vì chúng ghi dữ liệu dùng chung (ví theo địa chỉ Anvil cố định, id on-chain, `platform_settings`); chia sẻ DB của phiên làm lệch test migration cũ (so sánh cả `AUTO_INCREMENT`).
- **Khóa trong `slopee_web3` (đã gây lỗi thật):** đọc **khóa** (`cartItems` → `products`) phải chạy trước mọi đọc thường trong cùng giao dịch; không `UPDATE`/`FOR UPDATE` có thể không khớp dòng trên khoảng chưa tồn tại; chi tiết ở `ARCHITECTURE.md` 3.8.
- **Test dùng `fake_db`/`FakeCursor`** (trả dữ liệu theo nội dung SQL) thay vì `side_effect` theo thứ tự; route thêm/bớt truy vấn không làm vỡ test. Lỗi chung và `ApiError` được gắn vào **từng blueprint** (`register_blueprint_errors`) nên app tối giản trong `conftest.py` cũng trả đúng; route mới phải gắn handler này.
- **Khóa thanh toán** phải giữ thứ tự `cartItems → products → paymentMethods` (mỗi nhóm `ORDER BY id`); đổi thứ tự có thể gây deadlock. Bộ đếm sai PIN/mật khẩu `commit` riêng trước giao dịch tiền để không bị rollback.
- **`schema.sql` là lược đồ mới nhất:** thêm migration mà quên cập nhật `schema.sql` thì DB mới (được đánh dấu "đã áp dụng") sẽ thiếu thay đổi. `schema.txt` là bản cũ không dùng.
- **Foundry/Contract (tuần 1):** (1) `forge install ...@tag` có thể bỏ qua tag và kéo OpenZeppelin mới nhất (≥ 5.1 đòi solc ≥ 0.8.24) → luôn dùng `scripts/install_contract_deps.sh`. (2) solc 0.8.20 chưa cho `emit Contract.Event`: test khai báo lại sự kiện trong `EscrowBase.t.sol`. (3) `vm.prank` chỉ áp cho **lời gọi ngoài kế tiếp**: tính chữ ký (có gọi `escrow.QUOTE_TYPEHASH()`) **trước** `vm.prank`/`vm.expectRevert`. (4) `contracts/lib/` bị `.gitignore` (kể cả quy tắc `lib/` gốc). (5) Khóa trong test/script/bootstrap là khóa công khai của Anvil; bài quét khóa E-05 phải cho phép. (6) Sửa `types.json`/contract thì chạy lại `scripts/gen_eip712_vectors.py` và cả 3 bộ test.
- **`.gitignore` gốc có `lib/` (mẫu Python):** nó từng làm `frontend/src/lib/` không được commit nên CI không tìm thấy `../lib/client`. Đã thêm ngoại lệ `!frontend/src/lib/`. Thêm thư mục mã nguồn tên `lib`, `build`, `dist`, `out`… thì kiểm `git status`/`git check-ignore -v <file>` trước khi push; tốt nhất mô phỏng CI bằng `git clone` sạch rồi chạy test.
- **Tiền legacy:** người bán chỉ được cộng khi người mua thực sự bị trừ tiền (không COD/`cash`); mọi đường hủy/hoàn phải thu lại đúng khoản đó (`orderLines.sellerCredit`), tuyệt đối không tạo tiền. Test MySQL dùng `created_at` chỉ chính xác tới giây: đừng dựa `ORDER BY created_at` để tìm "đơn vừa tạo" trong vòng lặp.
- Tên shop/sản phẩm/UI của Slopee viết bằng tiếng Anh; thông báo lỗi Web3 và tài liệu viết bằng **tiếng Việt**.
- **Firefox chặn `window.confirm` do console bị nghẽn (Tuần 5):** Khi trình duyệt gặp lỗi lặp nền dồn dập (ví dụ CORS 404 do gọi API chưa có như `dispute-note`), cơ chế bảo vệ giao diện của Firefox tự động ép `window.confirm` trả về `false` ngay lập tức mà không hiển thị hộp thoại, làm ngắt luồng gọi ví. Tránh dùng `confirm` trình duyệt trong các luồng Web3; thay bằng modal React hoặc để MetaMask làm bước xác nhận cuối. *Cập nhật Tuần 6:* nguyên nhân kích hoạt (thiếu endpoint `dispute-note`) đã hết; `window.confirm` ở nút "Đã nhận hàng" của `Web3OrderPanel` vẫn còn, quy tắc trên vẫn áp dụng cho code mới. *Tuần 7:* nút "Hủy đơn" (`cancelIfUnfulfilled`) là code mới nên dùng khung xác nhận trong trang (`cancel-confirm-box`), không dùng `confirm`.
- **Đồng hồ đếm ngược không được ghi đè mốc neo mỗi lần poll (Tuần 5, đã giải quyết ở Tuần 6):** `server_time` luôn CŨ hơn giờ chuỗi 0 tới 1 nấc block (đo được dao động 1,51 giây khi Anvil bị tua giờ) và `secondsRemaining` làm tròn xuống nên đếm ngược giật lùi. Quy ước: nhận `server_time` qua `lib/serverClock.createServerClock().observe(...)` NGAY TRONG hàm poll (cùng nhịp với dữ liệu, không trong `useEffect`), chỉ giữ độ lệch LỚN NHẤT, tính còn lại bằng `deadline − (giờ máy + độ lệch)`. Chu kỳ poll theo trạng thái (`nextPollDelayMs`), và gọi `boost()` của `useOrderStatus` sau mỗi thao tác ví. Sau hạn kiểm tra đơn có thể mất tới ~65 giây mới sang `COMPLETED` (AutoRelease 60 giây + Indexer).
- **Hạn hủy đơn chưa giao (Tuần 7):** contract `cancelIfUnfulfilled` đòi đơn còn `LOCKED` và `block.timestamp >= createdAt + 14 ngày` (`createdAt` = giờ block lúc ký quỹ = `order_web3.chain_created_at`). Giao diện tính hạn theo `server_time` (không theo giờ máy, không theo `orders.created_at`) và làm tròn LÊN (`deliveryRemainingAt`) để nút không bật sớm hơn contract; ngược với đồng hồ kiểm tra làm tròn xuống. `availableActions(status, remaining)` giữ hình dạng `{earlyRelease, dispute}` vì nhiều test so sánh bằng `toEqual`; hủy đơn dùng `canCancelUnfulfilled` riêng, đừng nhét vào `availableActions`. Đơn thiếu `chain_created_at` thì ẩn nút, không đoán.
- **Khoản chờ rút `claimPending` (Tuần 7, A):** chỉ phát sinh với ETH khi ví nhận là hợp đồng từ chối tiền (`PayoutDeferred`); MockUSD (ERC-20) luôn là 0 nên demo mặc định thấy mục này trống. `claimPending` trả tiền cho `msg.sender`, nên phải gọi bằng đúng ví đang có số dư (giao diện khóa nút khi sai ví/sai mạng). Số dư trong MySQL (`pending_balances`) chỉ là bản dẫn xuất: trước khi gửi giao dịch `lib/claimPending.runClaimPending` đọc lại `pendingWithdrawals` trên chuỗi (số dư 0 thì không gửi, khỏi tốn gas) và giao diện chỉ coi là xong khi API (Indexer) bỏ khoản đó (DD-04, BR-09). Số tiền token luôn là chuỗi/BigInt, không float. Để thử bằng test: `FakeEscrowChain.defer_payout(...)` rồi chạy Indexer; để xem giao diện: `VITE_WEB3_MOCK=true` (đã có dữ liệu mẫu 0,005 ETH).
- **Flaky test đồng hồ đếm ngược với fake timers trên CI (Tuần 7):** Khi kiểm tra đồng hồ đếm ngược (`quote-countdown`, `useOrderStatus`, `Web3CheckoutPanel`) bằng `vi.useFakeTimers()`, việc tua thời gian bằng `vi.advanceTimersByTime(1000)` rồi `expect(...)` đồng bộ ngay lập tức rất dễ gây lỗi AssertionError trên CI runner (do độ trễ flush microtasks, chênh lệch nhịp render và sai số làm tròn số nguyên của `Date.now()`). **Quy tắc:** Luôn bọc assertion bằng `await waitFor(() => expect(...))` sau khi tua timer, kèm đệm thời gian nhỏ (ví dụ tua 1100ms thay vì 1000ms vừa khít) để đảm bảo test ổn định 100% trên cả local lẫn GitHub Actions.

---

## 8. Quy trình làm việc mong đợi

1. Đọc `PROGRESS.md` mục tương ứng và điều kiện nghiệm thu (mã test T-/I-/A-/F-/E-, AC-), rồi mở **đúng** các tệp đặc tả trong `docs/spec/` theo bảng ở mục 9.
2. Viết/cập nhật test **cùng lúc** với code; chạy `pytest` (MySQL thật nếu có) và `vitest`; `vite build` phải qua.
3. Mỗi PR: một thành viên khác review, test xanh 100% trước khi merge.
4. Khi xong một mã việc: cập nhật **chỉ** `PROGRESS.md` (trạng thái, PR/commit, tick test). Không sửa BRD/SRS/SDD.
5. Gặp mâu thuẫn đặc tả hoặc lỗ hổng mới: ghi vào mục "Ghi chú" của `PROGRESS.md` và báo người dùng, đừng âm thầm đổi hành vi.
6. Phạm vi cắt giảm nếu trễ (BRD mục 9): xem `PROGRESS.md` mục 7. **Không cắt** P0-01/P0-02.

---

## 9. Bản đồ tra cứu đặc tả: việc nào → mở tệp nào

Đặc tả nằm ở `docs/spec/` (xem `docs/spec/INDEX.md` cho danh sách đầy đủ kèm dung lượng). Quy tắc: mở **tệp đầu tiên** của hàng tương ứng; chỉ mở tệp sau khi tệp đầu chưa đủ. Mã trong tên tệp: `srs-04-uc-01` = UC-01; `sdd-053-...` = SDD mục 5.3; `brd-04-br-02` = BR-02. Nếu mâu thuẫn: BRD > SRS > SDD (mục 1).

### 9.1. Theo loại việc

| Việc cần làm | Mở trước | Mở thêm nếu cần |
| --- | --- | --- |
| Hiểu một quy tắc nghiệp vụ BR-xx | `brd-04-br-NN.md` | `brd-08-nghiem-thu.md` (AC-xx tương ứng) |
| Cài một use case UC-xx | `srs-04-uc-NN.md` | `srs-05-may-trang-thai.md`, `srs-07-rest-api.md` |
| Máy trạng thái đơn, ánh xạ sang `orders.status` cũ | `srs-05-may-trang-thai.md` | `sdd-074-dong-bo-orders-cu.md` |
| Phân quyền theo vai trò, ai được gọi hàm nào | `srs-03-phan-quyen.md` | `sdd-044-mau-bao-ve.md` |
| Viết/sửa **smart contract** (mã tham chiếu) | `srs-10-contract.md` | `sdd-043-ham.md` (từng hàm), `sdd-048-thay-doi-so-voi-srs.md` (phần SRS đã đổi), `srs-101-quyet-dinh-thiet-ke.md` |
| Nạp gom nhiều shop (`depositEscrowBatch`) | `sdd-049-nap-gom.md` | `brd-04-br-11.md`, `srs-04-uc-02.md` |
| Chữ ký EIP-712, `docHash`, `types.json`, vector test | `srs-06-eip712.md` | `sdd-08-mat-ma-eip712.md`, `sdd-045-chu-ky.md` |
| Bất biến contract (INV-xx), fuzz/invariant | `sdd-046-bat-bien.md` | `srs-121-test-contract.md` |
| Foundry, triển khai, cấp vai trò, `Deploy.s.sol` | `sdd-047-trien-khai.md` | `srs-102-foundry.md` |
| **REST API Web3**: endpoint, input/output, mã lỗi | `srs-07-rest-api.md` | `sdd-10-api-luong-tuan-tu.md`, `sdd-054-loi.md` |
| **Bảng CSDL**, migration, schema Web3 | `srs-09-database.md` | `sdd-072-order-web3.md`, `sdd-073-bo-sung.md`, `sdd-076-migration-replay.md` |
| Quyền ghi cột (Indexer hay backend), ràng buộc toàn vẹn | `sdd-071-quyen-ghi.md` | `sdd-075-rang-buoc.md` |
| Đồng bộ ngược `orders` cũ, `WEB3_ORDER_MANAGED`, huy hiệu tranh chấp | `sdd-074-dong-bo-orders-cu.md` | `srs-05-may-trang-thai.md` |
| **Indexer** (vòng lặp, handler, reorg, replay, đối soát) | `sdd-06-indexer.md` | `srs-04-uc-08.md` |
| Thuật toán backend: quy đổi VND→token, chọn thời hạn, `docHash`, báo giá, relayer, phán quyết, liên kết ví | `sdd-053-thuat-toan.md` | `srs-04-uc-01.md`, `srs-04-uc-06.md` |
| Cấu trúc module backend, cổng/adapter, đồng hồ `now_chain` | `sdd-051-module.md` | `sdd-052-ports.md`, `sdd-03-kien-truc.md` |
| Tác vụ nền (hết hạn báo giá, tự giải ngân) | `sdd-055-tac-vu-nen.md` | `srs-04-uc-04.md`, `srs-04-uc-07.md` |
| Cấu hình, khóa, biến môi trường, nhật ký | `srs-02-kien-truc.md` | `sdd-056-cau-hinh-log.md`, `sdd-12-trien-khai-van-hanh.md` |
| Bootstrap môi trường, runbook sự cố | `sdd-12-trien-khai-van-hanh.md` | `sdd-047-trien-khai.md` |
| **Frontend**: trang, tuyến, hook, máy trạng thái nạp tiền | `sdd-092-man-hinh-route.md` | `srs-08-giao-dien.md`, `sdd-093-may-trang-thai-nap.md`, `sdd-091-cong-nghe.md` |
| Frontend: sửa trang Slopee **đã có** (tệp nào đổi gì) | `sdd-098-frontend-hien-co.md` | `sdd-091-cong-nghe.md` |
| Frontend: thông báo lỗi, đồng hồ đếm ngược, thông báo khi ký | `sdd-095-anh-xa-loi.md` | `sdd-094-dong-ho.md`, `sdd-097-thong-bao-ky.md` |
| **Bảo mật**: mối đe dọa, quản lý khóa, danh sách kiểm | `sdd-11-bao-mat.md` | `brd-06-tin-cay-de-doa.md` |
| Lỗi bảo mật Slopee hiện tại S-xx | `srs-152-loi-bao-mat.md` | `sdd-162-loi-bao-mat.md` |
| **Giai đoạn 0** (P0-xx): làm gì, nghiệm thu bằng test nào | `srs-153-giai-doan-0.md` | `sdd-163-giai-doan-0.md`, `sdd-164-anh-huong-ke-hoach.md` |
| Hiện trạng Slopee so với giả định (UUID, trạng thái, shipper, VND) | `srs-151-hien-trang.md` | `sdd-161-gia-dinh-vs-thuc-te.md` |
| **Test contract** T-xx | `srs-121-test-contract.md` | `sdd-132-test-contract.md`, `sdd-134-test-bo-sung.md` |
| **Test tích hợp/E2E/auth/frontend** (I-, E-, A-, F-) | `srs-122-test-tich-hop-e2e.md` | `sdd-131-cac-tang-test.md` |
| Chuyển test cũ, CI, ví thử nghiệm cho E2E | `srs-123-test-hien-co-ci.md` | `sdd-135-test-hien-co-ci.md`, `sdd-133-cong-chat-luong.md` |
| Phi chức năng (hiệu năng, bảo mật, khả dụng) | `srs-13-phi-chuc-nang.md` | `sdd-133-cong-chat-luong.md` |
| Kế hoạch tuần, phạm vi cắt giảm nếu trễ | `srs-11-lo-trinh.md` | `brd-10-lo-trinh.md`, `brd-09-rui-ro.md` |
| Phạm vi MVP, thứ không được làm | `brd-02-pham-vi.md` | `brd-01-tong-quan.md` |
| Khung pháp lý, giới hạn áp dụng | `brd-07-phap-ly.md` | |
| Thuật ngữ | `srs-01-pham-vi-thuat-ngu.md` | `brd-11-thuat-ngu.md` |
| Truy vết BR → UC → test | `srs-14-truy-vet.md` | `sdd-14-truy-vet.md` |
| Lịch sử thay đổi giữa các phiên bản | `srs-00-lich-su.md` | |

### 9.2. Theo mã tra cứu nhanh

| Mã | Tệp |
| --- | --- |
| `BR-01`…`BR-11` | `brd-04-br-NN.md` |
| `AC-01`…`AC-14` | `brd-08-nghiem-thu.md` |
| `UC-00`…`UC-09` | `srs-04-uc-NN.md` |
| `T-01`…`T-34` | `srs-121-test-contract.md` |
| `I-xx`, `E-xx`, `A-xx`, `F-xx` | `srs-122-test-tich-hop-e2e.md` |
| `S-01`…`S-14` | `srs-152-loi-bao-mat.md` |
| `P0-01`…`P0-08` | `srs-153-giai-doan-0.md` |
| `DD-01`…`DD-12` | `sdd-02-quyet-dinh-kien-truc.md` |
| `MOD-01`…`MOD-10` | `sdd-051-module.md` |
| `INV-01`…`INV-07` | `sdd-046-bat-bien.md`, `sdd-048-thay-doi-so-voi-srs.md` |
| `R-01`…`R-09`, `Q-01`…`Q-12` | `sdd-15-quyet-dinh-da-chot.md` |
| `SEQ-01`…`SEQ-03` (luồng tuần tự) | `sdd-10-api-luong-tuan-tu.md` |

### 9.3. Tạo và kiểm tra lại tệp

```bash
# tạo/làm mới docs/spec (BRD/SRS từ HTML cần pandoc; SDD từ Markdown xuất ra từ tài liệu SDD)
python scripts/split_spec.py --brd docs/brd-v5_3.html --srs docs/srs-v5_3.html \
       --sdd docs/sdd-v1_2.md --out docs/spec --check-context AI_CONTEXT.md --lint
```

- `--check-context` báo lỗi nếu bảng ở mục 9 nhắc tới tệp không tồn tại; `--lint` báo mã ngoài phạm vi (ví dụ `T-45`) và con số lệch quy ước (giới hạn 5 shop, `DECIMAL(15,0)`).
- Tệp trong `docs/spec/` là **bản sinh tự động và chỉ đọc**; muốn sửa đặc tả phải sửa nguồn rồi chạy lại. Khi nhóm đổi tên mục, cập nhật bảng slug trong `split_spec.py` và bảng ở mục 9.
