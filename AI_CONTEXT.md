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
  app.py                tạo app, đăng ký blueprint, CLI `seed-admin`, JSON provider
  config.py             DB_*, SECRET_KEY (bắt buộc), AUTH_TOKEN_TTL_SECONDS
  auth_utils.py         token ký (itsdangerous) + decorator require_auth (P0-01)
  money.py              to_vnd / format_vnd — tiền VND số nguyên (P0-07)
  json_provider.py      Decimal -> số (int nếu nguyên) khi jsonify
  admin_seed.py         seed_admin(conn, ...) dùng cho CLI
  init_db.py            tạo DB từ schema.sql (KHÔNG còn tạo admin)
  schema.sql            lược đồ gốc; 4 cột tiền là DECIMAL(15,0)
  migrations/           0001_money_to_vnd.sql (chạy tay; P0-04 sẽ có runner)
  routes/               auth, admin, carts, payments, products, reviews, shops
frontend/               React 19 + Vite + React Router 7 (JavaScript, không TypeScript)
  src/api/http.js       phiên (sessionStorage), authFetch, getUser/setSession/clearSession
  src/api/*.js          các client REST (auth, carts, payments, shops, products, admin)
  src/utils/formatVND.js  hàm định dạng tiền DUY NHẤT
  src/pages, components, __tests__, tests/ (Playwright)
test/                   pytest (conftest.py, unit_test/, integration_test/)
.github/workflows/tests.yml   CI: pytest + MySQL service, vitest, build
docs/                   tài liệu
  spec/                 đặc tả tách nhỏ (brd-*, srs-*, sdd-*.md + INDEX.md) — sinh bằng scripts/split_spec.py
scripts/split_spec.py   tách BRD/SRS (HTML) và SDD (Markdown) thành docs/spec/
```

Cấu trúc **sắp tới** theo SDD (chưa tồn tại): `contracts/` (Foundry), `backend/slopee_web3/` (domain/application/ports/adapters), `shared/eip712/`, `scripts/bootstrap.sh`, `frontend/src/{lib,hooks}`.

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

# Frontend
cd frontend && npm run dev | npx vitest run | npm run build | npm run lint | npm run test:e2e
```

Biến môi trường: `SECRET_KEY` (bắt buộc trừ khi `SLOPEE_ENV` là `development`/`test`), `AUTH_TOKEN_TTL_SECONDS` (mặc định 3600), `DB_HOST/DB_USER/DB_PASSWORD/DB_NAME`.

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
| P0-01 token ký + `require_auth` | Đã code, chờ review | B |
| P0-02 khóa role/admin, seed admin CLI, bỏ cấp số dư | Đã code, chờ review | B |
| P0-07 VND (`DECIMAL(15,0)`, `formatVND`) | Đã code, chờ review | B+C |
| P0-08 cập nhật test + race test MySQL thật + CI | Đã code, chờ review | B+C |
| **P0-03** kiểm tra quyền sở hữu tài nguyên, `WEB3_ORDER_MANAGED` | **Chưa làm** | A |
| **P0-04** xóa `/api/shops/migrate`, runner `schema_migrations`, dọn schema `reviews/reviewImages` | **Chưa làm** | A |
| **P0-05** `FOR UPDATE`, `UPDATE ... WHERE inStock >= qty`, khóa tạm sau 5 lần sai PIN/mật khẩu | **Chưa làm** | A |
| **P0-06** tắt `debug=True`, lỗi chung cho client, validate body JSON | **Chưa làm** | A |
| Contract, Indexer, UC-00…UC-09, giao diện Web3 | Chưa bắt đầu | Tuần 1–10 |

**Lỗ hổng còn mở (đừng giả định đã an toàn):**
- Sửa/xóa sản phẩm, ảnh, biến thể; sửa/xóa cart item; `PUT /api/payments/orders/:id` mới chỉ yêu cầu đăng nhập (và role `seller` ở route shop), **chưa** kiểm tra chủ sở hữu → P0-03 (S-05, S-06, S-11).
- `GET /api/shops/migrate` vẫn công khai → P0-04 (S-07).
- Checkout chưa khóa dòng; chặn oversell hiện nhờ `CHECK (inStock >= 0)` (request thua trả 500) → P0-05 (S-08). Chưa giới hạn số lần thử → S-09.
- `app.run(debug=True)`, nhiều route trả `str(e)` cho client → P0-06 (S-10, S-14).
- Token chứa `role` và **không** kiểm lại DB: đổi role/xóa user thì token cũ còn hiệu lực đến khi hết hạn.

---

## 6. Điểm lệch giữa code hiện tại và đặc tả (cần nhóm xác nhận)

| Chủ đề | SDD/SRS nói | Code hiện tại | Ghi chú |
| --- | --- | --- | --- |
| TTL token | ví dụ 8 giờ | mặc định `3600` s, đặt qua `AUTH_TOKEN_TTL_SECONDS` | đổi env nếu muốn 8h |
| Decorator | `require_auth(roles=[...])`, `g.user` | `require_auth('seller')`, `g.user_id`/`g.role` | dùng API thực tế |
| Frontend client | `lib/client.js`, `lib/format.js`, `hooks/` | `api/http.js`, `utils/formatVND.js` | cùng chức năng; chọn một nơi rồi thống nhất |
| Route theo người dùng | `/<userId>` | `/api/carts/`, `/api/payments/`, `/api/payments/orders`, `/api/auth/reviews/me`, `/api/shops/me`, `/api/shops/me/name` | không còn xem shop theo seller ID |
| `add_product` | nhận `shopId` | shop suy ra từ token seller | |
| Số dư mới | "số dư giả lập ban đầu đổi sang VND" (SDD 16.3 bước 8) | số dư mới = 0 (S-04) | checkout ngân hàng cũ cần nạp tiền thủ công; COD vẫn chạy |
| Migration | `001_wallets.sql`…`015_shipper.sql` + `schema_migrations` | `migrations/0001_money_to_vnd.sql` chạy tay | đánh lại số khi P0-04 làm runner |

---

## 7. Bẫy đã gặp khi làm việc trong repo này

- **Hai đường import:** test import `backend.routes.auth` nhưng route nội bộ import `routes.auth` / `auth_utils` (do `conftest.py` thêm `backend/` vào `sys.path`). Module `backend.routes.x` và `routes.x` là **hai object khác nhau**: `mocker.patch('backend.routes.payments.get_db_connection')` chỉ có tác dụng với module mà blueprint đã đăng ký trong `conftest.py`. Khi patch hàm dùng chéo module, kiểm tra kỹ module nào đang được gọi.
- **`conftest.py` tự đặt** `SLOPEE_ENV=test` và `SECRET_KEY` trước khi import app; nếu thêm entrypoint mới đọc `config` sớm, đảm bảo env có trước.
- **Decimal từ pymysql:** JSON mặc định của Flask trả `Decimal` dạng *chuỗi*. App dùng `SlopeeJSONProvider` để trả số; app trong `conftest.py` cũng đã gắn provider này.
- **`test_*` cần MySQL thật** dùng fixture `mysql_db`/`db_conn` (tạo DB `slopee_test_<pid>` từ `schema.sql`, xóa sau khi xong, skip nếu không kết nối được). Cần user có quyền `CREATE DATABASE`.
- **Mock con trỏ DB** chỉ dùng cho logic thuần. Mọi đường liên quan tiền, tồn kho, trạng thái đơn, phân quyền phải có test trên MySQL thật.
- **CHECK constraint** chỉ được MySQL ≥ 8.0.16 thực thi; chưa chạy trên MariaDB/MySQL cũ.
- **Tài khoản không có PIN** (vd. admin) làm `check_password_hash(None, ...)` ném `AttributeError` → lỗi 500 (S-08, sửa ở P0-05).
- **`schema.sql`** khai báo trùng `reviews`/`reviewImages` (bản đầu thắng do `IF NOT EXISTS`); lỗi MySQL strict 1364 khi chèn ảnh đánh giá (S-13, sửa ở P0-04).
- Tên shop/sản phẩm/UI của Slopee viết bằng tiếng Anh; thông báo lỗi Web3 và tài liệu viết bằng **tiếng Việt**.

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
