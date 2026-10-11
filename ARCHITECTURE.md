# ARCHITECTURE.md — Kiến trúc, quy ước và hợp đồng giữa các tầng

> Bổ sung cho `AI_CONTEXT.md` (quy tắc bất biến, trạng thái) và `SKELETON.md` (bản đồ file/hàm/API).
> Ký hiệu: ✅ = đã có trong repo · 🔲 = thiết kế theo SDD, **chưa** triển khai. Khi hai phần mâu thuẫn, xem mục 9.

---

## 1. Tech stack và thư viện

| Lớp | Công nghệ | Phiên bản | Ghi chú |
| --- | --- | --- | --- |
| Backend ✅ | Python, Flask | 3.0.3 | Blueprint theo miền nghiệp vụ |
| | Flask-CORS | 4.0.0 | chỉ cho `http://localhost:5173` trên `/api/*` |
| | PyMySQL | 1.1.0 | truy vấn thô, `DictCursor`, tham số hóa `%s` |
| | Werkzeug | 3.0.2 | băm mật khẩu/PIN (`generate/check_password_hash`) |
| | itsdangerous | 2.2.0 | token phiên ký (`URLSafeTimedSerializer`) |
| | python-dotenv | 1.0.1 | nạp `backend/.env` |
| | click | (đi kèm Flask) | CLI `flask --app app seed-admin` |
| | pytest, pytest-mock | 8.1.1, 3.14.0 | test |
| Backend 🔲 | web3.py, eth_account | — | `ChainPort`, ký EIP-712, Indexer |
| | APScheduler (hoặc cron) | — | tác vụ nền |
| CSDL | MySQL | ≥ 8.0.16 | InnoDB, utf8mb4; cần để `CHECK` có hiệu lực |
| Frontend ✅ | React, React DOM | ^19.2 | JavaScript, **không** TypeScript |
| | react-router-dom | ^7.14 | `BrowserRouter` + `Routes` |
| | Vite | ^8 | dev server cổng 5173 |
| | Vitest, Testing Library, jsdom | ^4.1, ^16, ^24 | test đơn vị |
| | Playwright | ^1.59 | E2E (Firefox) |
| | ESLint 9 | ^9.39 | `npm run lint` |
| Frontend 🔲 | ethers.js v6 | — | **thư viện runtime duy nhất được thêm** (SDD 9.1); không thêm TanStack Query/TypeScript |
| Contract 🔲 | Solidity 0.8.20, OpenZeppelin v5.0.2, Foundry (`via_ir`) | — | `contracts/`, Anvil chainId 31337 |
| CI ✅ | GitHub Actions | — | pytest + dịch vụ MySQL, vitest, build |

Quy tắc thư viện: dùng thư viện chuẩn/đã liệt kê; muốn thêm dependency mới phải có lý do và ghi vào bảng này. Phiên bản được khóa (`==`) ở `requirements.txt`.

---

## 2. Kiến trúc tổng thể

```
React (Vite, :5173) ──REST/JSON + Bearer token──▶ Flask (:5000) ──SQL──▶ MySQL
        │                                              │
        └── MetaMask (ví người dùng, 🔲)               ├──▶ Anvil RPC (🔲: ChainPort, Signer, Relayer)
                                                       └── Indexer / Scheduler (🔲, tiến trình riêng)
```

Tiến trình khi chạy: `web` (Flask) ✅ · `indexer` 🔲 (đúng 1 thể hiện, khóa `GET_LOCK('slopee_indexer')`) · `scheduler` 🔲 · `mysql` ✅ · `anvil` 🔲 · `frontend` ✅.

### 2.1. Backend hiện tại ✅ — "Blueprint + transaction script" (MVC rút gọn, không có tầng service)

```
HTTP request
   │
   ▼  Blueprint route (Controller)   routes/*.py   ← kiểm quyền bằng @require_auth, parse JSON, validate, ghi SQL
   │      │ dùng
   │      ├── auth_utils.py   (xác thực, g.user_id / g.role)
   │      ├── validation.py   (json_body, get_str/get_int, validate_url — P0-06)
   │      ├── errors.py       (ApiError + handler lỗi chung gắn vào blueprint — P0-06)
   │      ├── throttle.py     (khóa tạm sai mật khẩu/PIN, bảng authAttempts — P0-05)
   │      ├── guards.py       (is_web3_order — P0-03)
   │      ├── money.py        (tiền VND số nguyên)
   │      └── get_db_connection() → PyMySQL (Model = bảng MySQL, không ORM)
   ▼
JSON response ({"error": "...", "code": "..."} hoặc payload) + HTTP status
```

- **Không có ORM, không có repository, không có service.** Logic nghiệp vụ và SQL nằm cùng hàm route. Mỗi route mở kết nối riêng (`get_db_connection()`) và đóng trong `finally`.
- "View" là JSON; giao diện nằm ở frontend riêng.
- Đây là **nền Slopee gốc**. Không refactor hàng loạt sang Hexagonal; chỉ áp dụng kiến trúc mới cho mô-đun Web3 (2.2).

### 2.2. Mô-đun Web3 🔲 — Hexagonal (DD-01, SDD mục 3.3)

```
backend/slopee_web3/
  domain/        thực thể + quy tắc thuần, KHÔNG I/O   money, policy, quote, dispute, order_state
  application/   ca sử dụng, điều phối các cổng       wallet_service, quote_service, order_service,
                                                       shipper_service, dispute_service, settings_service,
                                                       reconcile_service
  ports/         giao diện trừu tượng                 chain_port, signer_port, clock_port,
                                                       repositories, notification_port
  adapters/      hiện thực cổng                       web3_chain, env_signer, mysql_repos, hybrid clock
  flask_api/     blueprint, schema, ánh xạ lỗi HTTP
  indexer/       vòng lặp + handler từng sự kiện
  jobs/          tác vụ nền
```

Quy tắc phụ thuộc (có test kiểm import `T-ARCH-01`): `domain` chỉ import thư viện chuẩn → `application` chỉ phụ thuộc `domain` + `ports` → `adapters`, `flask_api`, `indexer`, `jobs` phụ thuộc vào tất cả bên trong.

Điểm nối duy nhất với lõi Slopee: tạo đơn (`orders`), danh mục sản phẩm, vai trò người dùng, `sync_legacy_status()` (ghi `orders.status`), và `GET /api/payments/orders` (LEFT JOIN `order_web3`).

### 2.3. Frontend ✅ — Pages → API client → http

```
App.jsx (Routes)
  └─ pages/*.jsx        màn hình; giữ state bằng useState/useEffect; gọi *API()
       └─ api/*.js      mỗi hàm = 1 endpoint, trả Response hoặc JSON thô
            └─ api/http.js   authFetch (gắn Bearer, xử lý hết phiên), getUser/setSession/clearSession
  └─ components/Navbar.jsx   thanh điều hướng + giỏ hàng thu nhỏ
  └─ utils/formatVND.js      định dạng tiền duy nhất
```

Frontend 🔲 theo SDD thêm: `lib/` (client, chain, eip712, errors, format), `hooks/` (useWallet, useEscrow, usePolling, useOrderStatus, useSignDispute, useServerClock, useAuth), `components/` (RequireRole, TxStepper, CountdownTimer, StatusBadge, AddressTag, AmountView), `mocks/` (fetch mock theo hợp đồng API, tuần 1–3). Máy trạng thái nạp tiền là **hàm thuần** `depositReducer(state, event)`; trang chỉ gọi reducer và thực hiện hiệu ứng.

---

## 3. Hợp đồng từng tầng (input → output)

### 3.1. Tầng HTTP (Blueprint route) ✅
- **Input:** JSON body (`request.get_json(silent=True) or {}`), path param, query string, header `Authorization: Bearer <token>`.
- **Output thành công:** JSON + status (200/201). Tiền trả dạng **số nguyên** (VND) nhờ `SlopeeJSONProvider`.
- **Output lỗi (hiện tại):** `{"error": "<thông báo>"}`; lỗi xác thực có thêm `"code"` ∈ `auth_required | token_expired | token_invalid | forbidden`.
- **Output lỗi (Web3 🔲):** `{"code": "<MÃ_LỖI>", "message": "<tiếng Việt>"}`, ánh xạ ở một chỗ (SDD 5.4).
- **Trách nhiệm:** xác thực/ủy quyền, validate đầu vào, trả đúng mã HTTP. Route mới **không** nhận `userId` từ client.

### 3.2. Tầng xác thực ✅ (`auth_utils.py`)
| Hàm | Input | Output / tác dụng phụ |
| --- | --- | --- |
| `issue_token(user_id, role)` | uuid, role | chuỗi token ký (payload `{uid, role}`) |
| `verify_token(token)` | chuỗi | payload dict, hoặc ném `SignatureExpired`/`BadSignature` |
| `authenticate_request(roles=None)` | header hiện tại | `None` nếu hợp lệ (đặt `g.user_id`, `g.role`), ngược lại response 401/403 |
| `@require_auth` / `@require_auth('seller', ...)` | — | bọc route, gọi `authenticate_request` |

### 3.3. Tầng tiền ✅ (`money.py`, `json_provider.py`)
- `to_vnd(value, allow_zero=True) -> int` — nhận `int | str | Decimal | float nguyên`; ném `InvalidMoney` nếu âm, có phần lẻ, `bool/None`, `NaN`, hoặc ≥ 10¹⁵.
- `format_vnd(amount) -> str` — `1234567 → "1.234.567 ₫"` (chỉ dùng cho thông báo server).
- `SlopeeJSONProvider` — `Decimal → int` (nếu nguyên) khi `jsonify`.

### 3.4. Tầng dữ liệu
- ✅ **Hiện tại:** SQL trực tiếp trong route; transaction bằng `conn.commit()/rollback()`; `DictCursor` trả dict theo tên cột.
- 🔲 **Web3:** `Repositories` (mỗi bảng một repo) + `UnitOfWork`; chuyển trạng thái dùng `UPDATE ... WHERE status=:old` và kiểm `rowcount`; `UNIQUE(onchain_order_id)`, `UNIQUE(tx_hash, log_index)`, `UNIQUE(address)` là lớp chống trùng cuối.

### 3.5. Các cổng Web3 🔲
| Cổng | Phương thức chính | Input → Output | Adapter MVP |
| --- | --- | --- | --- |
| `ChainPort` | `get_order(id)`, `get_logs(from,to)`, `get_block(n)`, `send_tx(fn,args,role)`, `balance_of(token)`, `dispute_nonce(id)` | tham số on-chain → dữ liệu chuỗi / biên nhận | `web3.py` → Anvil RPC |
| `SignerPort` | `sign_quote(quote)`, `sign_dispute(res)`, `sender_address(role)` | dữ liệu đã validate → chữ ký 65 byte (không bao giờ trả khóa) | `EnvKeySigner` (khóa từ env) |
| `ClockPort` | `now_system()`, `now_chain()` | — → giây UTC (int) | `HybridClock`: `now_chain = max(hệ thống, block mới nhất)` |
| `Repositories` | mỗi bảng một repo | entity ↔ SQL tham số hóa | MySQL |
| `NotificationPort` | `notify_buyer_delivered(order)` | order → ghi bảng thông báo | bảng thông báo Slopee |

Dùng `now_system()` cho nonce ví, phiên, rate limit; dùng `now_chain()` cho hạn báo giá, hạn chữ ký phán quyết, tác vụ nền, `server_time`.

### 3.6. Tầng frontend API client ✅ (`src/api/*.js`)
- **Input:** tham số JS thường (không có `userId`); **Output:** `fetch Response` (đa số) mà trang tự `await res.json()`; các hàm đọc đơn giản có thể trả JSON.
- `authFetch(url, opts)`: tự thêm `Content-Type: application/json` khi có body và `Authorization: Bearer`; khi nhận 401 với `code ∈ {auth_required, token_expired, token_invalid}` → `clearSession()` và chuyển `/login`. **Không** đăng xuất khi 401 vì sai mật khẩu/PIN.
- Endpoint công khai (products, login, signup) dùng `fetch` thường.

### 3.7. Smart contract 🔲 (`SlopeeEscrowMaster`, SRS mục 10)
- Vào: lời gọi hàm + chữ ký EIP-712 (báo giá do sàn ký; phán quyết 2/3). Ra: sự kiện (`OrderCreated`, `OrderDelivered`, `OrderCompleted`, `OrderRefunded`, `OrderDisputed`, `DisputeResolved`, `ArbitratorForceResolved`, `PayoutDeferred`, `PendingClaimed`, `FeeUpdated`, `FeeRecipientUpdated`).
- Chỉ có contract + Indexer quyết định trạng thái đơn Web3; API không có endpoint ghi trạng thái từ client.

---

## 4. Quy ước đặt tên

### Python / Flask
| Đối tượng | Quy ước | Ví dụ |
| --- | --- | --- |
| Module, hàm, biến | `snake_case` | `get_or_create_cart`, `issue_token` |
| Hằng số | `UPPER_SNAKE` | `ALLOWED_SIGNUP_ROLES`, `MAX_VND` |
| Hàm private | tiền tố `_` | `_serializer`, `_require_admin` |
| Blueprint | biến `<tên>_bp`, prefix `/api/<tên-số-nhiều>` | `carts_bp` → `/api/carts` |
| Hàm route | động từ + đối tượng | `add_to_cart`, `update_order_status` |
| Ngoại lệ | PascalCase, kế thừa `ValueError` nếu là lỗi dữ liệu | `InvalidMoney` |
| File mới | thuộc `backend/` (lõi) hoặc `backend/slopee_web3/<layer>/` | |

### JSON / API
- **API Slopee gốc ✅:** khóa `camelCase` (`cartItemIds`, `paymentMethodId`, `unitPrice`, `inStock`), thông báo `{"error"}`.
- **API Web3 🔲 (SDD 10.2):** khóa `snake_case` (`checkout_group_id`, `amount_raw`, `price_vnd`, `fee_bps`, `inspection_duration`), lỗi `{code, message}`. Hai phong cách cùng tồn tại; **không đổi API cũ**, và API Web3 mới theo SDD.
- Số uint256 trong JSON là **chuỗi thập phân**; thời gian là **giây UTC (int)**; địa chỉ ví **chữ thường** (checksum chỉ để hiển thị).
- URL: danh từ số nhiều, kebab-case cho cụm từ (`/api/checkout-groups/:id`); tài nguyên của người đăng nhập dùng `/me` hoặc bỏ tham số, **không** có `userId` trong URL.

### CSDL
- Bảng/cột Slopee gốc: `camelCase` (`userId`, `cartItems`, `unitPrice`), khóa chính `VARCHAR(36)` UUID (riêng `products.id` là `VARCHAR(15)`, `categories.id` là INT).
- Bảng/cột Web3 🔲: `snake_case` (`order_web3`, `checkout_groups`, `onchain_order_id`, `amount_raw`).
- Tiền: `DECIMAL(15,0)` (VND) cho 4 cột Slopee; `VARCHAR(78)` cho số lượng token on-chain; mốc thời gian on-chain `BIGINT UNSIGNED` (giây UTC).
- Migration ✅ (P0-04): `migrations/NNNN_tên.sql|.py` chạy bằng `python migrate.py` (không có route HTTP), tên tệp ghi vào `schema_migrations`, khóa `GET_LOCK`, **idempotent** (DDL MySQL tự commit nên không rollback được). Hiện có `0001`–`0004`. `schema.sql` luôn là lược đồ mới nhất cho DB tạo mới và `init_db.py` đánh dấu các migration hiện có là đã áp dụng; thêm migration phải đồng thời cập nhật `schema.sql`. Migration Web3 (`001_wallets`…`015_shipper` trong SRS) nên đánh số từ `0005` để không trùng tiền tố. Bảng hạ tầng: `schema_migrations`, `authAttempts`.

### JavaScript / React
| Đối tượng | Quy ước | Ví dụ |
| --- | --- | --- |
| Component, trang | `PascalCase.jsx`, `export default` | `Checkout.jsx`, `Navbar.jsx` |
| Hàm gọi API | `<động từ><Đối tượng>API` | `fetchCartAPI`, `addToCartAPI` |
| Hook 🔲 | `useXxx` | `usePolling`, `useWallet` |
| Hàm tiện ích | `camelCase` trong `src/utils/` | `formatVND` |
| Kiểu dữ liệu | JSDoc nếu cần, **không TypeScript** | |
| Style | CSS thường trong `src/assets/*.css` (Vanilla CSS) | |
| Lưu trữ phiên | `sessionStorage` khóa `token`, `user` (qua `api/http.js`) | |

### Solidity 🔲
Hàm `camelCase`, sự kiện/struct `PascalCase`, hằng `UPPER_SNAKE` (`QUOTE_TYPEHASH`), vai trò `*_ROLE`; một contract `SlopeeEscrowMaster`, `MockUSD` 6 decimals.

### Test
- Python: `test/unit_test/test_*.py`, `test/integration_test/test_*.py`; hàm `test_<đối_tượng>_<hành_vi>`; test cần MySQL thật gắn `pytestmark = pytest.mark.mysql`. Dữ liệu giả dùng chung đặt ở `conftest.py` hoặc module không bắt đầu bằng `test_` (vd. `unit_test/checkout_helpers.py`).
- Frontend: `src/__tests__/*.test.{js,jsx}` (Vitest), `frontend/tests/*.spec.js` (Playwright).
- Mã test của dự án (`T-xx` contract, `I-xx` tích hợp, `A-xx` API/bảo mật, `F-xx` frontend, `E-xx` E2E) theo `PROGRESS.md` mục 5.
- Mã tham chiếu trong code/PR: `BR-xx`, `UC-xx`, `DD-xx`, `INV-xx`, `S-xx` (lỗ hổng), `P0-xx`.

---

## 5. Xác thực và phân quyền (cắt ngang mọi tầng)

- Token: `URLSafeTimedSerializer(SECRET_KEY, salt='slopee-auth-token-v1')`, payload `{uid, role}`, hết hạn theo `AUTH_TOKEN_TTL_SECONDS` (mặc định 3600). Token **không** kiểm lại DB.
- Vai trò tài khoản: `user` (Buyer), `seller` (Merchant), `admin`; 🔲 thêm `shipper` (cuối ENUM `users.role`). Trọng tài là dịch vụ ký phía server, không phải tài khoản đăng nhập.
- Ma trận: route công khai (đăng nhập, đăng ký, sản phẩm, danh mục, `/api/health`) · `@require_auth` (mọi user) · `@require_auth('seller')` (shop/sản phẩm) · `admin_bp` (`before_request` chỉ cho `admin`).
- Quyền sở hữu tài nguyên ✅ (P0-03): id người dùng luôn lấy từ token (`g.user_id`), không từ body/URL. Cart item, đơn, phương thức thanh toán lọc theo `userId`; sản phẩm/ảnh/biến thể kiểm qua `products → shops.sellerId`. Tài nguyên không thuộc người gọi trả **404** (như không tồn tại), không phải 403. Đơn có dòng `order_web3` không đổi được bằng `PUT /api/payments/orders/:id` (`409 WEB3_ORDER_MANAGED`), và chuyển trạng thái theo bảng `paid|shipped→received`, `pending|paid→cancelled` (`409 INVALID_STATE`).
- Chống dò mật khẩu/PIN ✅ (P0-05): sai 5 lần liên tiếp (`AUTH_MAX_ATTEMPTS`) → khóa `AUTH_LOCK_SECONDS` (mặc định 900 s), `429 too_many_attempts` + `Retry-After`, kể cả khi nhập đúng lúc đang khóa. Đăng nhập/đổi mật khẩu/xin xóa tài khoản dùng chung bộ đếm theo tài khoản (scope `password`); PIN thanh toán dùng scope `pin`; username không tồn tại cũng bị đếm (lưu băm). Bộ đếm `commit` riêng nên không bị rollback.

## 6. Xử lý lỗi
- ✅ Hiện tại (P0-06): `{"error": ..., "code": ...}` + 400/401/403/404/409/413/429/500. Route ném `ApiError` cho lỗi người dùng; mọi ngoại lệ khác → `500 {"code": "internal_error"}` với thông báo chung, chi tiết + traceback chỉ ghi log máy chủ (`errors.py`, gắn vào từng blueprint bằng `register_blueprint_errors` và vào app bằng `register_app_errors`). **Không** trả `str(e)`. Body phải là JSON object (`json_body()` → `400 invalid_body`); giới hạn body 1 MB. Mã hiện có: `invalid_body`, `missing_field`, `invalid_field`, `not_found`, `already_exists`, `invalid_pin`, `pin_not_set`, `invalid_credentials`, `too_many_attempts`, `insufficient_stock`, `insufficient_funds`, `checkout_conflict`, `INVALID_STATE`, `WEB3_ORDER_MANAGED`, `internal_error`. Frontend chỉ xóa phiên với các mã trong `SESSION_ERROR_CODES` (401 sai PIN/mật khẩu **không** đăng xuất).
- 🔲 Web3: ngoại lệ miền → mã HTTP + `code` (`WALLET_NOT_LINKED 409`, `WALLET_TAKEN 409`, `NONCE_INVALID 400`, `BAD_SIGNATURE 400`, `QUOTE_EXPIRED 410`, `INVALID_STATE 409`, `FORBIDDEN 403`, `POLICY_OUT_OF_RANGE 422`, `CHAIN_TX_FAILED 502`, `FEE_CAP_CHANGED 409`, `BATCH_TOO_LARGE 422`, `WEB3_ORDER_MANAGED`). Frontend ánh xạ lỗi contract/ví sang tiếng Việt ở một nơi (`lib/errors.js`).

## 7. Cấu hình
| Biến | Mặc định | Dùng ở |
| --- | --- | --- |
| `SECRET_KEY` | bắt buộc (trừ khi `SLOPEE_ENV` = `development`/`test`) | `auth_utils`, `config` |
| `AUTH_TOKEN_TTL_SECONDS` | 3600 | `auth_utils` |
| `SLOPEE_ENV` | (trống = production-like) | `auth_utils`, `config` — chỉ `development` bật `debug` và khóa dev |
| `AUTH_MAX_ATTEMPTS` | 5 | `throttle` |
| `AUTH_LOCK_SECONDS` | 900 | `throttle` |
| `DB_HOST/DB_USER/DB_PASSWORD/DB_NAME` | `localhost` / `root` (riêng `routes/auth.py`: `slopee`) / `` / `slopee_db` | mọi nơi mở kết nối |
| 🔲 `RPC_URL`, `CHAIN_ID`, `ESCROW_ADDRESS`, `MOCKUSD_ADDRESS`, `QUOTE_SIGNER_KEY`, `ARBITRATOR_KEY`, `SHIPPER_KEY`, `POLL_SECONDS`, `CONFIRMATIONS`, `REORG_DEPTH` | — | Web3 |
| 🔲 `platform_settings` (DB) | tỷ giá, `PLATFORM_FEE_BPS` (300), `QUOTE_TTL_SECONDS`, `DISPUTE_SIG_TTL_SECONDS` | Admin đổi không cần restart |

Khóa vận hành chỉ đọc một lần lúc khởi động vào `EnvKeySigner`; `.env` không commit.

## 8. Kiểm thử theo tầng
| Tầng | Công cụ | Cách làm |
| --- | --- | --- |
| Logic thuần (`money`, `auth_utils`, `admin_seed`) | pytest | không DB |
| Route (mock con trỏ DB) | pytest + `client` + `fake_db` (`FakeCursor`) | `FakeCursor` trả dữ liệu theo nội dung SQL, kiểm được SQL/tham số đã chạy; `AttemptsStore` giả lập `authAttempts`; fixture `auth_headers`, `seller_headers`; chỉ cho logic/luồng, **không** chứng minh khóa dòng |
| Route/tiền/tồn kho/phân quyền | pytest + **MySQL thật** | fixture `mysql_db` (DB `slopee_test_<pid>` từ `schema.sql`), `db_conn`; tự skip nếu không kết nối được |
| Frontend | Vitest + Testing Library | mock `fetch` trong `src/__tests__/setup.js` |
| E2E | Playwright (Firefox) | 🔲 ví EIP-1193 giả bằng khóa Anvil, nạp qua `addInitScript` |
| Contract 🔲 | Foundry | `forge test`, fuzz/invariant, `forge coverage ≥ 90%`, Slither |
| Chéo ngôn ngữ 🔲 | `shared/eip712/vectors.json` | Python, JS, Solidity cùng ra một digest |

## 9. Nợ kỹ thuật và mâu thuẫn đã biết
- `get_db_connection()` bị **lặp** ở `admin`, `auth`, `carts`, `payments`, `shops` (còn `products` và `reviews` import từ `routes.auth`); mặc định `DB_USER` không đồng nhất (`slopee` ở `auth.py`, `root` ở nơi khác) → luôn đặt `DB_USER` rõ ràng. Khi refactor, gom về một module `db.py`.
- Hai đường import: code chạy với `backend/` trên `sys.path` (`from routes.auth import ...`), test dùng `backend.routes.*`; hai module này là hai object khác nhau (xem `AI_CONTEXT.md` mục 7).
- Hủy đơn `paid` chưa hoàn tiền/tồn kho (S-05); COD vẫn cộng số dư người bán; `orders.userId` FK `RESTRICT`. Cần nhóm quyết hành vi.
- Test MySQL mới của P0-03…06 (`integration_test/test_p0_mysql.py`) và migration `0002`/`0003` chưa được chạy trên MySQL thật khi viết.
- SDD ghi `lib/client.js`/`lib/format.js`; code là `api/http.js`/`utils/formatVND.js`.
- `backend/schema.txt` là bản schema cũ (DECIMAL(11,2), khai báo trùng) không còn được dùng — nên xóa.
