# SKELETON.md — Bản đồ file, hàm và API

> Mục đích: AI biết **file nào làm gì, hàm nào làm gì, API nhận/trả gì** mà không cần đọc phần triển khai.
> Khi sửa hoặc thêm hàm/route/file, **cập nhật file này trong cùng PR**.
> Ký hiệu: ✅ có trong repo · 🔲 chưa làm (chữ ký dự kiến theo SRS/SDD; có thể điều chỉnh khi triển khai).
> `Auth`: `—` công khai · `U` đăng nhập (mọi role) · `S` role `seller` · `A` role `admin`.
> Prefix mọi API: `http://localhost:5000`. Lỗi: `{"error": "..."}` (✅ cũ) hoặc `{"code","message"}` (✅ Web3, tuần 3; chi tiết thêm như `checkout_group_id`, `shop_id`, `party` nằm cùng cấp). Lỗi xác thực: 401 `auth_required|token_expired|token_invalid`, 403 `forbidden`.

---

## 1. Backend ✅

### 1.1. File lõi (`backend/`)
| File | Vai trò | Hàm / đối tượng | Làm gì |
| --- | --- | --- | --- |
| `app.py` | Điểm vào Flask | `app` | Tạo Flask, nạp `config`, gắn `SlopeeJSONProvider`, bật CORS (`localhost:5173`), đăng ký blueprint, `register_app_errors`, `MAX_CONTENT_LENGTH` 1 MB; `app.run(debug=app.config['DEBUG'])` (chỉ `SLOPEE_ENV=development`) |
| | | `health_check()` | `GET /api/health` → trạng thái server |
| | | `seed_admin_command(username,name,email,password)` | CLI `flask --app app seed-admin`; gọi `admin_seed.seed_admin` |
| | | `migrate_command(action)` | CLI `flask --app app migrate [up\|status]`; gọi `migrate.main` |
| `config.py` | Cấu hình | `Config`, `is_development()` | `DB_*`, `SECRET_KEY` (qua `get_secret_key`), `AUTH_TOKEN_TTL_SECONDS`, `DEBUG` (chỉ khi `SLOPEE_ENV=development`) |
| `errors.py` | Lỗi chung (P0-06) | `ApiError(message, code, status, headers, extra)` | lỗi người dùng có chủ đích → JSON `{error, code}` |
| | | `register_blueprint_errors(bp)`, `register_app_errors(app)` | `ApiError` → đúng status; `HTTPException` → JSON; ngoại lệ khác → `internal_error()` |
| | | `internal_error(exc)` | ghi log chi tiết + traceback, trả 500 `{code: internal_error}` thông báo chung |
| `validation.py` | Kiểm đầu vào (P0-06) | `json_body()` | body rỗng → `{}`; không phải JSON object → `ApiError 400 invalid_body` |
| | | `get_str`, `get_int`, `as_int`, `get_bool`, `get_enum` | ép kiểu + giới hạn độ dài/khoảng, sai → 400 |
| | | `validate_url`, `get_url_list` | chỉ `http(s)` tuyệt đối, ≤ 500 ký tự, không khoảng trắng/ký tự điều khiển |
| `throttle.py` | Khóa tạm (P0-05) | `check(cur,scope,subject)` | ném `429 too_many_attempts` nếu đang khóa; trả số lần sai đang lưu |
| | | `record_failure`, `reset`, `attempts_remaining` | tăng bộ đếm (khóa dòng), xóa khi thành công |
| | | `password_subject(user_id\|username)`, `pin_subject(user_id)` | khóa đếm: `id:<userId>` hoặc `u:<sha256 username>`; scope `password`/`pin` |
| `guards.py` | Guard (P0-03) | `is_web3_order(cursor, order_id)` | đơn có dòng `order_web3`; chưa có bảng (lỗi 1146) → `False` |
| `migrate.py` | Runner migration (P0-04) | `split_sql`, `discover`, `migrate(conn)`, `mark_applied`, `status`, `main` | `python migrate.py [up\|status\|mark-applied]`; `schema_migrations`, `GET_LOCK`, `.sql` và `.py` |
| `dbschema.py` | Tiện ích migration | `column_exists`, `add_column_if_missing`, `index_exists`, `foreign_keys`, `ensure_foreign_key` | dùng `DATABASE()`, idempotent |
| `auth_utils.py` | Xác thực token | `get_secret_key()` | Đọc `SECRET_KEY` từ env; khóa dev chỉ khi `SLOPEE_ENV` = development/test, nếu không ném `RuntimeError` |
| | | `get_token_ttl()` | TTL giây từ env (mặc định 3600) |
| | | `issue_token(user_id, role)` | Ký token `{uid, role}` |
| | | `verify_token(token)` | Giải mã + kiểm hạn; ném `SignatureExpired`/`BadSignature` |
| | | `authenticate_request(roles=None)` | Đọc `Authorization: Bearer`; đặt `g.user_id`, `g.role`; trả `None` hoặc response lỗi 401/403 |
| | | `require_auth(*roles)` | Decorator: `@require_auth` hoặc `@require_auth('seller')` |
| `money.py` | Tiền VND | `to_vnd(value, allow_zero=True)` → `int` | Chuẩn hóa/validate số tiền nguyên; ném `InvalidMoney` |
| | | `format_vnd(amount)` → `str` | `1234567` → `"1.234.567 ₫"` |
| | | `InvalidMoney` | Ngoại lệ dữ liệu tiền sai |
| `json_provider.py` | JSON | `SlopeeJSONProvider` | `Decimal` → `int` (nếu nguyên) / `float` |
| `admin_seed.py` | Seed admin | `seed_admin(conn, username, password, name, email, phone)` → `user_id` | Validate (username > 3 ký tự, mật khẩu ≥ 12), kiểm trùng, chèn `users` + `credentials` (role `admin`); ném `ValueError` |
| `init_db.py` | Khởi tạo DB | `create_connection()`, `init_database()` | Tạo DB, chạy `schema.sql` (tách bằng `migrate.split_sql`); DB mới → `mark_applied` mọi migration; DB cũ → nhắc chạy `migrate.py`; **không** tạo admin |
| `schema.sql` | Lược đồ mới nhất | — | 14 bảng gốc + `authAttempts` (mục 1.4); 4 cột tiền `DECIMAL(15,0)`; `reviews`/`reviewImages` khai báo một lần; `users.role` có `shipper`; sau dấu mốc `WEB3 ESCROW` là 16 bảng Web3 + gieo `PLATFORM_FEE_BPS=300`, `QUOTE_TTL_SECONDS=900`, 4 nhóm `category_policies` |
| `migrations/0001_money_to_vnd.sql` | Migration | — | `MODIFY` 4 cột tiền sang `DECIMAL(15,0)` |
| `migrations/0002_product_fk_snapshots.py` | Migration | `upgrade(cursor)` | (thay route `/migrate` cũ) cột snapshot + backfill; `cartItems.productId` CASCADE; `orderLines.productId` NULL + SET NULL |
| `migrations/0003_reviews_dedupe.py` | Migration | `upgrade(cursor)` | DB cũ: `comment NOT NULL`, bỏ trùng, `UNIQUE(userId,productId)`, FK `userId` CASCADE |
| `migrations/0004_auth_attempts.sql` | Migration | — | tạo `authAttempts` |
| `migrations/0005_order_line_settlement.py` | Migration | — | thêm `orderLines.sellerPaymentMethodId` (FK SET NULL) + `sellerCredit`; backfill đơn cũ đã thanh toán không phải `cash`; idempotent. **Web3 bắt đầu từ `0006`** |
| `migrations/0006`–`0020` | Migration Web3 (tuần 2) | — | `0006_wallets.py` (user_wallets, wallet_nonces), `0007_checkout_groups.py`, `0008_order_web3.py` (phòng vệ charset/collation/InnoDB, FK `RESTRICT`), `0009_order_quotes.py`, `0010_dispute_resolutions.py`, `0011_dispute_signatures.sql`, `0012_chain_events.sql`, `0013_indexer_cursor.sql`, `0014_platform_settings.sql` (+gieo 4 khóa), `0015_category_policies.sql` (+gieo 4 nhóm), `0016_category_policy_map.sql`, `0017_tx_outbox.sql`, `0018_onchain_id_seq.sql` (bắt đầu 100001), `0019_pending_balances.sql`, `0020_shipper.py` (ENUM `shipper` + `shipper_assignments`) |
| `dbschema.py` (bổ sung) | Introspection | `require_innodb`, `column_like`, `table_exists`, `SchemaError` | giúp migration FK khớp kiểu/charset/collation cột cha |
| `.env.example` | Mẫu env | — | `SECRET_KEY`, `AUTH_TOKEN_TTL_SECONDS`, `SLOPEE_ENV`, `DB_*`, `AUTH_MAX_ATTEMPTS`, `AUTH_LOCK_SECONDS` |

### 1.2. Route (`backend/routes/`)
Mỗi file có `get_db_connection()` mở kết nối PyMySQL (trừ `products`, `reviews` import từ `routes.auth`).

#### `auth.py` — prefix `/api/auth`
| Method + path | Auth | Request | Response | Hành vi chính |
| --- | :-: | --- | --- | --- |
| `POST /signup` | — | `name,email,phone,username,password,pass_phrase,role?` | 201 `{message}` | role chỉ `user`/`seller` (sai → 403); PIN đúng 6 chữ số; username 4–25 ký tự; email hợp lệ (≤ 50); phone 9–10 chữ số; trùng email/phone/username → 400 (đua song song → 409) |
| `POST /login` | — | `username,password` | 200 `{message,token,expiresIn,user{id,role,name,email,...}}` | sai thông tin → 401 `Invalid username or password` (+ `attemptsRemaining`); sai 5 lần → khóa 15 phút, 429 `too_many_attempts` + `Retry-After` (kể cả username không tồn tại) |
| `POST /account/request-deletion` | U | `password` | 200 `{message}` | đánh dấu yêu cầu xóa tài khoản để Admin xử lý; sai mật khẩu → 401; chung bộ đếm khóa với đăng nhập |
| `PUT /profile` | U | `bio` | 200 `{message}` | cập nhật tiểu sử của chính mình |
| `PUT /username` | U | `newUsername` | 200 / 400 / 409 | đổi tên đăng nhập (kiểm độ dài, trùng) |
| `PUT /password` | U | `oldPassword,newPassword` | 200 / 401 / 429 | đổi mật khẩu (băm mới); sai mật khẩu cũ được đếm chung với đăng nhập |
| `GET /reviews/me` | U | — | `{reviews:[...]}` | lịch sử đánh giá của chính mình |

#### `products.py` — prefix `/api/products` (công khai)
| Method + path | Request | Response | Hành vi chính |
| --- | --- | --- | --- |
| `GET /categories` | — | `{categories}` | danh sách danh mục |
| `GET /?search=` | query `search` | `{time_taken_sec, items:[product+shopName+ảnh chính+averageRating]}` | tìm theo tên sản phẩm hoặc tên shop, chỉ `isActive` |
| `GET /<product_id>` | — | `{product{..., images[], variants[]}}` / 404 | chi tiết sản phẩm |
| `GET /<product_id>/reviews?offset=&limit=` | query | `{reviews[], stats{average,total}}` / 400 | đánh giá phân trang (mặc định limit 5; `offset` ≥ 0, `limit` 1–50, sai → 400) |

#### `reviews.py` — prefix `/api/reviews`
| Method + path | Auth | Request | Response | Hành vi chính |
| --- | :-: | --- | --- | --- |
| `POST /<product_id>` | U | `rating(1-5),comment,images[]` | 201 `{message,reviewId}` / 400 / 403 / 409 | chỉ người **đã mua** mới đánh giá; mỗi người một đánh giá/sản phẩm; `images` ≤ 5 URL `http(s)`, backend cấp UUID cho `reviewImages.id` |

#### `carts.py` — prefix `/api/carts`
| Hàm | Method + path | Auth | Request | Response | Hành vi chính |
| --- | --- | :-: | --- | --- | --- |
| `get_or_create_cart(cursor,user_id)` | (nội bộ) | | | `cart_id` | lấy/tạo giỏ `active` của user |
| `fetch_cart` | `GET /` | U | — | `{cartId, items[]}` | giỏ của chính mình kèm thông tin sản phẩm |
| `add_to_cart` | `POST /items` | U | `productId,quantity,selectedVariants?` | 200 / 400 / 404 | validate kiểu (`quantity` nguyên ≤ 10000); kiểm tồn kho; cộng dồn nếu đã có (không vượt tồn) |
| `manage_cart_item` | `PUT\|DELETE /items/<item_id>` | U | `quantity` (PUT) | 200 / 400 / 404 | đổi số lượng (≤ tồn kho) hoặc xóa dòng; **chỉ dòng thuộc giỏ của mình**, của người khác → 404 |

#### `payments.py` — prefix `/api/payments`
| Hàm | Method + path | Auth | Request | Response | Hành vi chính |
| --- | --- | :-: | --- | --- | --- |
| `get_payment_methods` | `GET /` | U | — | `{methods[]}` | phương thức thanh toán của mình (kèm `balance` VND) |
| `add_payment_method` | `POST /` | U | `methodType,providerName,accountNumber` | 201 / 400 | tạo phương thức (`methodType` ∈ `bank|credit_card|cash`, độ dài có giới hạn), **số dư khởi tạo 0** |
| `execute_checkout` | `POST /checkout` | U | `cartItemIds[],paymentMethodId` (hoặc `"CASH_ON_DELIVERY"`), `passPhrase` | 200 `{message}` / 400 / 401 / 404 / 409 / 429 | `_verify_pin` (PIN chưa đặt → 401 `pin_not_set`; sai 5 lần → 429; bộ đếm commit riêng) → **transaction tiền**: khóa `cartItems` của mình → khóa `products` (`isActive`) → đọc `shops` → khóa `paymentMethods` (người mua + người bán, `ORDER BY id FOR UPDATE`) → kiểm tồn kho/số dư theo giá đã khóa → `UPDATE … balance >= x`, cộng ví người bán, `UPDATE products … inStock >= qty` (kiểm `rowcount`) → tạo **một** `orders` (`paid`) + `orderLines`, xóa `cartItems`. Deadlock → 409 `checkout_conflict` Người bán chỉ được **cộng khi người mua thực sự bị trừ tiền** (COD/`cash` không cộng); mỗi `orderLines` ghi `sellerPaymentMethodId` + `sellerCredit` để hủy đơn thu lại đúng khoản đó |
| `update_order_status` | `PUT /orders/<order_id>` | U | `status ∈ {cancelled,received}` | 200 `{message, refunded}` / 400 / 404 / 409 (`INVALID_STATE`, `WEB3_ORDER_MANAGED`, `refund_unavailable`) | đổi trạng thái đơn cũ: chỉ **chủ đơn** (khác → 404), khóa dòng; đơn có `order_web3` → 409 `WEB3_ORDER_MANAGED`; chỉ `paid\|shipped→received`, `pending\|paid→cancelled` (sai → 409 `INVALID_STATE`); UPDATE kèm điều kiện trạng thái cũ. **hủy đơn `paid`** (`_settle_cancelled_paid_order`): hoàn kho (bỏ qua sản phẩm đã xóa), hoàn tiền người mua (chỉ khi đã bị trừ, không phải `cash`) và **thu lại** từ `sellerPaymentMethodId` (`UPDATE … AND balance >= x`; không đủ → 409 `refund_unavailable`, rollback). Khóa `products → paymentMethods` như checkout. `pending→cancelled` và `received` không đụng tiền/kho |
| `get_orders` | `GET /orders` | U | — | `{orders:[{orderId,totalAmount,created_at,status,items[]}]}` | đơn của mình, nhóm theo đơn (🔲 thêm cờ khiếu nại Web3) |

#### `shops.py` — prefix `/api/shops`
| Hàm | Method + path | Auth | Request | Response | Hành vi chính |
| --- | --- | :-: | --- | --- | --- |
| `setup_shop` | `POST /` | S | `name,description?` | 201 `{shopId}` / 400 / 403 | tạo shop cho seller (một shop/seller; phải có ≥ 1 phương thức thanh toán) |
| `get_shop` | `GET /me` | S | — | shop + `products[]` (kèm ảnh, biến thể) / 404 | shop của chính seller |
| `update_shop_name` | `PUT /me/name` | S | `name` | 200 | đổi tên shop của mình |
| `add_product` | `POST /products` | S | `name,description?,categoryId?,inStock,unitPrice(VND nguyên)` | 201 `{productId}` / 400 / 403 | shop suy ra từ token; `unitPrice` qua `to_vnd` |
| `update_product` | `PUT /products/<product_id>` | S | `unitPrice,inStock` | 200 / 400 / 404 | sửa giá/tồn; **chỉ sản phẩm thuộc shop của mình** (khác → 404); `inStock` nguyên 0…1.000.000 |
| `delete_product` | `DELETE /products/<product_id>` | S | — | 200 / 404 | xóa sản phẩm của mình (lịch sử đơn giữ nhờ snapshot, `orderLines.productId` → NULL) |
| `add_product_image` | `POST /products/<product_id>/images` | S | `imageUrl,isPrimary?` | 201 `{imageId}` / 400 / 404 | thêm ảnh cho sản phẩm của mình; `imageUrl` chỉ `http(s)` ≤ 500 ký tự |
| `delete_product_image` | `DELETE /products/images/<image_id>` | S | — | 200 / 404 | xóa ảnh (JOIN tới `shops.sellerId` = mình) |
| `add_product_variant` | `POST /products/<product_id>/variants` | S | `variantName,variantValue` | 201 `{variantId}` / 404 | thêm biến thể cho sản phẩm của mình |
| `delete_product_variant` | `DELETE /products/variants/<variant_id>` | S | — | 200 / 404 | xóa biến thể (JOIN tới `shops.sellerId` = mình) |

#### `admin.py` — prefix `/api/admin` (toàn bộ blueprint chỉ cho `A`, qua `before_request`)
| Hàm | Method + path | Request | Response | Hành vi chính |
| --- | --- | --- | --- | --- |
| `get_stats` | `GET /stats` | — | `{users,shops,products}` | đếm tổng |
| `get_users` | `GET /users` | — | danh sách user (kèm cờ yêu cầu xóa) | liệt kê tài khoản |
| `delete_user` | `DELETE /users/<user_id>` | — | 200 / 403 / 404 / 409 `user_has_orders` | xóa user; cấm xóa chính mình và mọi admin; user đã có đơn → 409 (giữ `orders.userId` RESTRICT, đơn là hồ sơ kế toán) |
| `get_admin_categories` | `GET /categories` | — | `{categories}` | danh mục |
| `create_category` | `POST /categories` | `name` | 201 | thêm danh mục |
| `rename_category` | `PUT /categories/<int:cat_id>` | `name` | 200 | đổi tên |
| `delete_category` | `DELETE /categories/<int:cat_id>` | — | 200 / 409 | xóa; 409 nếu còn sản phẩm dùng |

### 1.3. Hợp đồng nội bộ quan trọng
- `g.user_id` / `g.role` chỉ tồn tại sau `@require_auth`; **mọi route cần danh tính dùng `g.user_id`, không đọc từ body/URL**.
- Tiền: DB `Decimal` → `to_vnd()` → `int`; so sánh/cộng bằng `int`; JSON ra là số.
- Khởi tạo ngoại lệ: `InvalidMoney` → 400; `SignatureExpired`/`BadSignature` → 401 (do `authenticate_request`); `ApiError` → status/`code` của nó; mọi ngoại lệ khác → 500 `internal_error` (chi tiết chỉ trong log). **Mỗi blueprint mới phải gọi `register_blueprint_errors(bp)`.**
- Quyền sở hữu: tài nguyên không thuộc người gọi → **404** (không 403); sở hữu sản phẩm/ảnh/biến thể kiểm qua `shops.sellerId = g.user_id`.
- Mọi route đọc body bằng `json_body()` (không dùng `request.get_json(silent=True) or {}`).

### 1.4. Bảng CSDL gốc (`schema.sql`)
| Bảng | Mục đích | Cột chính / ghi chú |
| --- | --- | --- |
| `users` | tài khoản | `id`(UUID), `role`(`admin|seller|user`), `name`, `email`, `phone`(char10, UNIQUE), `bio`, cờ yêu cầu xóa |
| `credentials` | đăng nhập | `userId`, `username`, `passwordHash`, `passwordSalt`, `passPhraseHash` (PIN 6 số; NULL với admin) |
| `shops` | cửa hàng | `id`, `sellerId`, `name`, `description` |
| `paymentMethods` | ví/ngân hàng giả lập | `id`, `userId`, `methodType`(`bank|credit_card|cash`), `providerName`, `accountNumber`, `balance` DECIMAL(15,0) |
| `categories` | danh mục | `id` INT, `name` |
| `products` | sản phẩm | `id`(varchar 15), `categoryId`, `shopId`, `name`, `description`, `inStock`(CHECK ≥ 0), `unitPrice` DECIMAL(15,0), `isActive` |
| `productImages`, `productVariants` | ảnh / biến thể | gắn `productId`; ảnh có `isPrimary` |
| `reviews`, `reviewImages` | đánh giá (khai báo một lần, S-13) | `reviews`: `userId`, `productId`, `rating`, `comment NOT NULL`, `UNIQUE(userId,productId)`; `reviewImages`: `id` VARCHAR(36) do backend cấp, `reviewId`, `imageUrl` |
| `carts`, `cartItems` | giỏ | `carts.status` `active|ordered`; `cartItems`: `cartId`, `productId` (FK CASCADE), `quantity`, `selectedVariants` |
| `orders` | đơn | `id`, `userId`, `paymentMethodId`, `created_at`, `status`(`pending|paid|shipped|cancelled|received`), `totalAmount` DECIMAL(15,0) |
| `orderLines` | dòng đơn | `orderId`, `productId` (NULL được, FK SET NULL), `selectedVariants`, `unitPrice`, `quantity`, `snapshotProductName`, `snapshotShopName`, `sellerPaymentMethodId` (FK SET NULL → `paymentMethods`), `sellerCredit` DECIMAL(15,0) (VND đã cộng cho người bán) |
| `authAttempts` | đếm sai mật khẩu/PIN (P0-05) | PK `(scope, subject)`, `failedCount`, `lockedUntil` (epoch giây, BIGINT) |
| `schema_migrations` | migration đã chạy (do `migrate.py` tạo, không nằm trong `schema.sql`) | `version` (tên tệp), `appliedAt` |

---

## 2. Frontend ✅ (`frontend/src/`)

### 2.1. Route và trang
| Route | File | Làm gì | API dùng |
| --- | --- | --- | --- |
| `/` | `pages/Home.jsx` | lưới sản phẩm; tìm kiếm đọc từ query `?search=` trên URL (Navbar đẩy từ khóa lên URL); thêm vào giỏ | `fetchProductsAPI`, `addToCartAPI` |
| `/product/:id` | `pages/ProductView.jsx` | chi tiết, chọn biến thể, đánh giá (xem + viết) | `fetchProductDetailsAPI`, `fetchProductReviewsAPI`, `publishProductReviewAPI`, `addToCartAPI` |
| `/login` | `pages/Login.jsx` | đăng nhập, lưu phiên, về `/` (admin → `/admin`); nếu có `location.state.pendingCartItem` thì thêm vào giỏ sau khi đăng nhập | `loginAPI`, `addToCartAPI` |
| `/signup` | `pages/Signup.jsx` | đăng ký (user/seller) | `signupAPI` |
| `/cart` | `pages/Cart.jsx` | xem/sửa/xóa dòng giỏ, chọn dòng, sang thanh toán | `fetchCartAPI`, `updateCartItemAPI`, `removeCartItemAPI` |
| `/checkout` | `pages/Checkout.jsx` | chọn phương thức (kể cả COD), nhập PIN, thanh toán; thêm ngân hàng. **Tuần 3:** thêm lựa chọn "Thanh toán Web3 (ký quỹ mUSD)" (`selectedMethodId === 'WEB3_ESCROW'`) → thay khung PIN bằng `Web3CheckoutPanel`; luồng cũ không đổi. **F-08:** gọi `fetchWeb3EligibilityAPI` khi vào trang; `web3Gate.status` = `checking\|ok\|blocked\|unavailable\|unknown`; `blocked` (có shop chưa liên kết ví) hoặc `unavailable` (503 `WEB3_NOT_CONFIGURED`) → radio `disabled` + dòng cảnh báo (kèm tên shop), tự chuyển khỏi Web3 nếu đã lỡ chọn; `unknown` (lỗi mạng) thì KHÔNG chặn | `fetchPaymentMethodsAPI`, `addPaymentMethodAPI`, `checkoutAPI`, `fetchWeb3EligibilityAPI` |
| `/wallet` ✅ | `pages/Wallet.jsx` | UC-00: kết nối MetaMask, kiểm mạng, liên kết/đổi ví bằng `personal_sign` (không gas); bốn trạng thái `linkState` = `NO_ACCOUNT\|NOT_LINKED\|LINKED_THIS\|LINKED_OTHER`; hủy ký = thông báo trung tính. Chỉ `user`/`seller` | `fetchLinkedWalletAPI`, `requestWalletNonceAPI`, `linkWalletAPI` |
| `/orders` | `pages/MyOrders.jsx` | danh sách đơn, hủy/đã nhận | `fetchOrdersAPI`, `updateOrderStatusAPI` |
| `/settings` | `pages/UserSettings.jsx` | tiểu sử, đổi tên đăng nhập/mật khẩu, yêu cầu xóa tài khoản, đánh giá của tôi | `updateProfileAPI`, `updateUsernameAPI`, `updatePasswordAPI`, `requestDeletionAPI`, `fetchUserReviewsAPI` |
| `/seller` | `pages/SellerDashboard.jsx` | lập shop, quản lý sản phẩm/ảnh/biến thể, liên kết ngân hàng nhận tiền | `getShopAPI`, `setupShopAPI`, `updateShopNameAPI`, `addProductAPI`, `updateProductAPI`, `deleteProductAPI`, `addProductImageAPI`, `addProductVariantAPI`, `fetchCategoriesAPI`, `fetchPaymentMethodsAPI`, `addPaymentMethodAPI` |
| `/admin` | `pages/AdminDashboard.jsx` | thống kê, quản lý user, quản lý danh mục | `getStatsAPI`, `getUsersAPI`, `deleteUserAPI`, `fetchAdminCategoriesAPI`, `addCategoryAPI`, `updateCategoryAPI`, `deleteCategoryAPI` |
| `/play/tetris` | `pages/Tetris.jsx` | trò chơi Tetris (độc lập, không API) | — |
| (mọi trang) | `components/Navbar.jsx` | thanh điều hướng, ô tìm kiếm (điều hướng `/?search=`), giỏ thu nhỏ, menu theo role; liên kết "🦊 Ví" → `/wallet` cho `user`/`seller` | `fetchCartAPI` |
| (trong `/checkout`) ✅ | `components/Web3CheckoutPanel.jsx` | props `{cartItemIds}`. Cổng điều kiện (không có ví → chưa kết nối → sai mạng → đang kiểm tra liên kết → chưa liên kết → ví khác ví đã liên kết) rồi "Tạo báo giá"; bảng từng shop (giá VND, số token, phí, thời hạn), tổng, tỷ giá, đếm ngược theo `server_time` (<60 giây = sắp hết hạn), "Lấy báo giá mới", **"Làm mới báo giá cho lô này"** khi `PENDING_GROUP_EXISTS` (F-07: xin báo giá MỚI cho lô cũ, không khôi phục phiên; giữ lại khi lỗi tạm thời, bỏ khi `INVALID_STATE`/`GROUP_NOT_FOUND`). Mọi yêu cầu báo giá đi qua `run()` có cờ `inFlight` (ref) nên bấm dồn chỉ gửi một yêu cầu; nhận báo giá thì đặt `receivedAt` và `now` cùng lúc để đồng hồ bắt đầu đúng 15:00. `WALLET_NOT_LINKED` với `extra.party` = merchant (so không phân biệt hoa/thường) → nêu tên shop (`extra.shop_name`), không dẫn tới `/wallet`. **Nút "Ký quỹ" (Tuần 4) chạy approve tổng → `depositEscrowBatch` → chờ API `LOCKED` → chuyển `/orders`** | `createWeb3OrderAPI`, `requoteGroupAPI`, `fetchLinkedWalletAPI` |

Route guard ✅ `components/RequireRole.jsx` bọc `/admin` (admin), `/seller` (seller), `/cart`, `/checkout`, `/orders`, `/settings` (chỉ cần đăng nhập): chưa đăng nhập → `/login`; sai role → thông báo. Chỉ là tiện lợi giao diện; quyền thật do backend kiểm. `WalletProvider` (`hooks/useWallet.js`) bọc toàn app.

### 2.2. API client (`src/api/`)
| File | Hàm | → Endpoint |
| --- | --- | --- |
| `http.js` | (**chỉ re-export `lib/client.js`**) `API_ORIGIN`, `getToken()`, `getUser()`, `setSession(token,user)`, `updateStoredUser(user)`, `clearSession()`, `authFetch(url, opts)` | phiên ở `sessionStorage`; `authFetch` gắn Bearer, tự đăng xuất khi mã phiên hết hạn/sai |
| `auth.js` | `loginAPI(username,password)`, `signupAPI(userData)` | `POST /api/auth/login`, `/signup` (không cần token) |
| | `requestDeletionAPI(password)`, `updateProfileAPI(bio)`, `updateUsernameAPI(newUsername)`, `updatePasswordAPI(old,new)`, `fetchUserReviewsAPI()` | `/account/request-deletion`, `/profile`, `/username`, `/password`, `GET /reviews/me` |
| `products.js` | `fetchProductsAPI(search='')`, `fetchCategoriesAPI()`, `fetchProductDetailsAPI(id)`, `fetchProductReviewsAPI(id,offset,limit)` | `GET /api/products...` (công khai) |
| | `publishProductReviewAPI(id,reviewData)` | `POST /api/reviews/<id>` (cần token) |
| `carts.js` | `fetchCartAPI()`, `addToCartAPI(productId,quantity=1,selectedVariants={})`, `updateCartItemAPI(itemId,quantity)`, `removeCartItemAPI(itemId)` | `/api/carts/...` |
| `payments.js` | `fetchPaymentMethodsAPI()`, `addPaymentMethodAPI(data)`, `checkoutAPI(data)`, `fetchOrdersAPI()`, `updateOrderStatusAPI(orderId,status)` | `/api/payments/...` |
| `shops.js` | `setupShopAPI(data)`, `getShopAPI()`, `updateShopNameAPI(name)`, `addProductAPI`, `updateProductAPI(id,data)`, `deleteProductAPI(id)`, `addProductImageAPI(id,url,isPrimary)`, `deleteProductImageAPI(imageId)`, `addProductVariantAPI(id,name,value)`, `deleteProductVariantAPI(variantId)` | `/api/shops/...` |
| `web3.js` ✅ | `requestWalletNonceAPI(address)`, `linkWalletAPI({address, signature, nonce})`, `fetchLinkedWalletAPI()` | `POST /api/wallet/nonce`, `POST /api/wallet/link`, `GET /api/wallet` |
| | `fetchWeb3EligibilityAPI(cartItemIds)` | `POST /api/orders/eligibility` (chỉ đọc) |
| | `createWeb3OrderAPI(cartItemIds)`, `requoteGroupAPI(groupId)`, `fetchCheckoutGroupAPI(groupId)` | `POST /api/orders`, `POST /api/checkout-groups/:id/quote`, `GET /api/checkout-groups/:id`. Mọi lỗi ném `Web3ApiError {code, message, status, extra}` (mất mạng → `NETWORK_ERROR`) |
| `admin.js` | `getStatsAPI`, `getUsersAPI`, `deleteUserAPI(userId)`, `fetchAdminCategoriesAPI`, `addCategoryAPI(name)`, `updateCategoryAPI(id,name)`, `deleteCategoryAPI(id)` | `/api/admin/...` |

### 2.3. Tiện ích và test
| File | Làm gì |
| --- | --- |
| `lib/client.js` | **chuẩn**: `API_ORIGIN` (đọc `VITE_API_BASE`, mặc định `http://localhost:5000`), `getToken/getUser/setSession/updateStoredUser/clearSession`, `SESSION_ERROR_CODES`, `authFetch` |
| `lib/format.js` | **chuẩn**: `formatVND(value) → "1.234.567 ₫"` (duy nhất để hiển thị tiền), `shortAddress(addr) → "0x9965…A4dc"` |
| `utils/formatVND.js` | chỉ re-export `lib/format.js` |
| `lib/chain.js` | `ANVIL_CHAIN_ID=31337`, `parseDeployment(raw)`, `loadDeployment()` (đọc `/deployments/local.json`), `DeploymentError`, `toChainIdHex`, `addChainParams(deployment)`, `sameAddress(a,b)` |
| `lib/eip712.js` | `EIP712_TYPES` (từ `shared/eip712/types.json`), `buildDomain(deployment)`, `quoteDigest`, `disputeDigest`, `recoverQuoteSigner`, `recoverDisputeSigner`, `signDispute(signer, domain, msg)` |
| `hooks/useWallet.js` | `WalletProvider({provider?, deployment?})`, `useWallet() → {status, account, chainId, isConnected, isCorrectChain, deployment, deploymentStatus, error, connect, disconnect, clearError, switchToDeployedChain, getSigner}`; hàm thuần `walletReducer`, `normalizeWalletError`, `getInjectedProvider`, `parseChainId`; mã lỗi `WALLET_ERROR` (4001 → `USER_REJECTED`) |
| `lib/errors.js` ✅ | `Web3ApiError`, `ERROR_MESSAGES` (mã → tiếng Việt), `toUserMessage(err)` (API/ví/lạ), `isUserRejection(err)` |
| `lib/web3Checkout.js` ✅ | `formatTokenAmount(raw, decimals, symbol)` (BigInt, `"15,96 mUSD"`), `sumRaw`, `secondsRemaining({deadline, serverTime, receivedAtMs, nowMs})` (theo giờ máy chủ), `quoteStatus(remaining) → ok\|expiring\|expired`, `formatCountdown`, `describeDuration`, `formatFeeBps` |
| `lib/walletLink.js` ✅ | `runLinkFlow({address, signer, api, onStep})` (nonce → ký đúng thông điệp của backend → link), `LINK_STEP`, `linkState({linked, account})` |
| `mocks/web3Mock.js` ✅ | `installWeb3Mock({ttlSeconds, latencyMs, shops, fxVndPerToken, unlinkedShopIds}) → {uninstall, state}` (`state.unlinkedShopIds` sửa được lúc chạy để mô phỏng shop chưa liên kết ví); bật bằng `VITE_WEB3_MOCK=true` (`main.jsx`); chỉ chặn `/api/wallet*`, `/api/orders`, `/api/checkout-groups*`, còn lại gọi fetch thật; chữ ký giả |
| `components/RequireRole.jsx` | `<RequireRole roles?="admin"|[...]>` — route guard |
| `__tests__/client.test.js`, `format.test.js`, `chain.test.js`, `RequireRole.test.jsx`, `useWallet.test.jsx`, `eip712Vectors.test.js` | F-04, tiện ích định dạng, `deployments/local.json`, route guard, ví (EIP-1193 giả), vector EIP-712 chéo ngôn ngữ |
| `__tests__/web3Lib.test.js`, `web3Api.test.js`, `web3Ui.test.jsx` | tuần 3: hàm thuần + luồng liên kết (34), API + mock (9), trang Wallet/panel/Checkout/Navbar với ví giả **ký thật** bằng khóa Anvil (36; có F-07 làm mới báo giá + chống bấm dồn, F-08 khóa Web3 khi shop chưa liên kết; timeout chờ nới 8 s cho máy tải cao); `eip712Vectors.test.js` có thêm vector `walletLink` |
| `__tests__/setup.js` | mock `fetch`/môi trường cho Vitest |
| `__tests__/Home.test.jsx`, `Navbar.test.jsx` | test trang Home và Navbar |
| `__tests__/formatVND.test.js` | test định dạng tiền |
| `__tests__/tetrisLogic.test.js` | test logic Tetris |
| `frontend/tests/*.spec.js` | Playwright: luồng đăng ký/đăng nhập và Tetris |

---

## 3. Test ✅ (`test/`)
| File | Phạm vi |
| --- | --- |
| `conftest.py` | fixture: `app`, `client`, `mock_db_cursor`, `make_auth_headers(user_id,role)`, `auth_headers`, `seller_headers`, `mysql_db` (DB tạm từ `schema.sql`), `db_conn`; **`FakeCursor`/`fake_db(module)`** (trả dữ liệu theo nội dung SQL, `cur.on(fragment, rows, rowcount)`, `cur.executed(fragment)`), `fake_conn`, `attempts_store` (giả lập `authAttempts`) |
| `unit_test/test_auth_token.py` | token ký/hết hạn/giả mạo, SECRET_KEY bắt buộc, header sai, route `/<userId>` đã biến mất |
| `unit_test/test_p0_02_admin.py` | đăng ký chỉ user/seller, `admin_bp` chỉ admin, không xóa admin/chính mình, số dư mới = 0, `seed_admin` |
| `unit_test/auth_test.py` | đăng nhập (trả token), đăng ký (validate) |
| `unit_test/test_cart.py`, `test_products.py`, `test_checkout.py` | giỏ, sản phẩm (kiểm giá VND), checkout (tổng nguyên VND, thiếu tiền, COD) — mock DB (`checkout_helpers.py` dựng dữ liệu giả dùng chung) |
| `unit_test/test_p0_03_ownership.py` | A-03: đơn/giỏ/sản phẩm/ảnh/biến thể của người khác → 404 và không ghi gì; chuyển trạng thái đơn; `WEB3_ORDER_MANAGED`; hồ sơ/username chỉ theo token |
| `unit_test/test_web3_migrations_static.py` | Migration Web3 tĩnh (không cần MySQL): đúng 0006–0020 liên tục, mọi bảng có trong `schema.sql`, chỉ CREATE/INSERT IGNORE, không DROP/DELETE, FK tiền ký quỹ `RESTRICT` |
| `integration_test/test_web3_migrations.py` | MySQL thật: DB mới == DB nâng cấp (parity information_schema), idempotent (không đè giá trị Admin), collation lệch (`unicode_ci`), MyISAM bị chặn, CHECK/UNIQUE/FK/ENUM của từng bảng |
| `unit_test/test_p0_04_migrations.py` | A-07: route migrate biến mất; `split_sql`; runner (thứ tự, bỏ qua đã chạy, lỗi không ghi nhận, khóa); `dbschema`; `schema.sql` không khai báo trùng; ảnh đánh giá có UUID |
| `unit_test/test_p0_05_payment_security.py` | A-05/A-06: thứ tự khóa `FOR UPDATE`, `UPDATE` có điều kiện + `rowcount`, deadlock → 409, PIN chưa đặt → 401, khóa 5 lần (PIN, đăng nhập, đổi mật khẩu, xin xóa), mở khóa khi hết hạn |
| `unit_test/test_p0_06_hardening.py` | lỗi chung không lộ chi tiết (+ có log), JSON body sai → 400, validate từng trường/URL ảnh/query, `debug` chỉ ở development |
| `unit_test/test_money.py` | `to_vnd`, `format_vnd`, JSON provider, schema `DECIMAL(15,0)` |
| `integration_test/test_checkout_race_mysql.py` | **MySQL thật**: nhiều người mua tranh tồn kho, không bán lố, tiền khớp; số tiền lưu là int VND |
| `integration_test/test_products_api.py` | **MySQL thật**: `GET /api/products/` trả danh sách hợp lệ |
| `unit_test/test_p0_decisions.py` | quyết định nhóm: COD/`cash` không cộng người bán, hủy đơn `paid` (hoàn kho + hoàn tiền + thu lại, bảo toàn tiền, người bán không đủ → 409, thứ tự khóa), xóa user có đơn → 409 |
| `w3_support.py` ✅ | tuần 3: khóa thử Anvil (`KEYS`, `ADDR`), `FakeChain`, `event(...)`, `make_signer`, `Env` (service + adapter giả), `sign_message`, seed MySQL (`user`, `link_wallet`, `shop_with_product`, `cart_item`) |
| `integration_test/conftest.py` ✅ | mỗi module `test_w3_*` chạy trên **database riêng** (tạo từ `schema.sql`, xóa sau khi xong) để không làm lệch test cũ |
| `unit_test/test_w3_domain.py` | miền thuần: tiền (làm tròn lên, không float), chính sách `max()`, `docHash` khớp vector, thông điệp liên kết ví khớp vector `walletLink`, máy trạng thái |
| `unit_test/test_w3_architecture.py` | T-ARCH-01: quét import — `domain` thuần, `ports` chỉ domain, `application` chỉ domain+ports |
| `unit_test/test_w3_signer.py` | `EnvKeySigner` tái tạo **đúng từng byte** chữ ký trong vector; ba khóa vai trò phải khác nhau; không lộ khóa; che log |
| `unit_test/test_w3_routes.py` (46) | API Web3 (gồm `/api/orders/eligibility`): 401/403 theo role, danh tính chỉ từ token, validate, ánh xạ lỗi `{code,message}`, không lộ chi tiết nội bộ, `WEB3_NOT_CONFIGURED` |
| `integration_test/test_w3_wallet_mysql.py` | **MySQL thật** UC-00 (I-01): nonce một lần/hết hạn, chữ ký sai không để dấu vết, `WALLET_TAKEN`, đổi ví, giới hạn tần suất, đua song song (cùng nonce; hai tài khoản cùng ví) |
| `integration_test/test_w3_quote_mysql.py` (53) | **MySQL thật** UC-01 (I-04/I-07) + `check_web3_eligibility` (chỉ đọc, không khóa, khớp quyết định của `create_checkout`): lô nhiều shop, `docHash` tái tạo từ DB, chính sách, phí ≤ trần, giữ chỗ kho, mọi lỗi nghiệp vụ không để dấu vết, rollback giữa chừng, cấp lại báo giá (kể cả lô `EXPIRED`), đua giành món cuối / bấm đúp |
| `integration_test/test_w3_indexer_mysql.py` | **MySQL thật**: `GET_LOCK`, con trỏ, idempotent, cửa sổ, rollback cửa sổ, `ChainReset`, backoff |
| `integration_test/test_w3_chain_anvil.py` (`-m anvil`) | **Anvil + contract thật**: contract chấp nhận lô do backend ký, từ chối sửa/sai người nạp/hết hạn/phí vượt trần, Indexer giải mã log thật. Tự skip nếu không có Anvil (`REQUIRE_ANVIL=1` ở CI → đỏ) |
| `unit_test/test_eip712_vectors.py` | tuần 1: vector EIP-712 chéo ngôn ngữ phía Python (digest, người ký, chữ ký 65 byte low-s, `docHash`, `vectors.json` khớp script sinh) |
| `integration_test/test_p0_mysql.py` | **MySQL thật** (đã chạy trên MySQL 8.0, gồm quyết định nhóm: hủy đơn hoàn tiền/hủy song song/COD/xóa user/migration `0005`): sở hữu đơn, đơn Web3, bấm thanh toán 2 lần chỉ ra 1 đơn, thanh toán chéo không deadlock, khóa đăng nhập/PIN, ảnh đánh giá ở strict mode, runner + migration 0002/0003 idempotent, xóa sản phẩm giữ lịch sử đơn |

---

## 4. Mô-đun Web3 🟡 (tuần 3–4: ví, đơn, báo giá, Indexer OrderCreated, đồng bộ legacy, polling status ✅ — còn lại 🔲)

Nguồn: SRS mục 4–7, 9–10; SDD mục 3–8, 10. Đặt dưới `backend/slopee_web3/` (✅ = có trong repo, 🔲 = dự kiến). Cấu hình qua `settings.py` (`Web3Settings.from_env()` đọc `backend/.env.web3` do `bootstrap.sh` sinh; thêm `WALLET_LINK_DOMAIN` (mặc định `localhost:5173`), `WALLET_NONCE_MAX_PER_MINUTE`, `TOKEN_DECIMALS`).

### 4.1. `domain/` (thuần, không I/O — được test kiến trúc canh)
| File | Hàm / kiểu | Làm gì |
| --- | --- | --- |
| `errors.py` ✅ | `DomainError(code, message, extra)`, `http_status(code)` | lỗi nghiệp vụ + bảng mã → HTTP status (domain không biết HTTP) |
| `money.py` ✅ | `parse_fx_scaled(str) -> int` (×10⁴; sai → `SETTING_INVALID`), `fx_to_str`, `vnd_to_token(price_vnd, decimals, fx_scaled) -> int`, `fee_split(amount, fee_bps) -> (net, fee)` | `ceil(price_vnd·10^dec·10^4 / fx_scaled)` bằng số nguyên; từ chối float/bool/âm |
| `policy.py` ✅ | `Policy(code, inspection_duration, dispute_timeout)`, `pick_durations(policies) -> (inspection, dispute, policy_chủ_đạo)`, `check_limits` | `max` riêng từng thời hạn; kiểm 1h–30d và 7–90d (`POLICY_OUT_OF_RANGE`) |
| `quote.py` ✅ | `OrderQuote` (+ `.message()` uint256 thành chuỗi), `QUOTE_FIELDS`, `build_summary(order_code, items, price_vnd, created_at)`, `canonical_json`, `doc_hash(summary, keccak)`, `validate_quote` | chuẩn hóa JSON (khóa sắp xếp, UTF-8, chỉ số nguyên) rồi `keccak256`; danh sách hàng sắp ổn định |
| `wallet.py` ✅ | `normalize_address`, `normalize_signature` (v→27/28), `is_valid_nonce`, `build_link_message(domain, address, user_id, nonce, chain_id, issued_at, expires_at)`, `NONCE_TTL_SECONDS=300` | thông điệp SIWE cố định từng byte (khớp vector `walletLink`) |
| `order_state.py` ✅ | `STATES`, `is_valid_transition(old, new)`, `to_legacy_status(web3_status)` | bảng chuyển trạng thái (kể cả `EXPIRED → PENDING_PAYMENT` khi cấp lại báo giá) + ánh xạ `orders.status` |
| `dispute.py` 🔲 | `ResolutionState`, `next_state(state, event)` | `PROPOSED → READY → SUBMITTED → EXECUTED / EXPIRED / CANCELLED` |

### 4.2. `ports/` và `adapters/`
| Cổng | Phương thức | Adapter |
| --- | --- | --- |
| `ChainPort` ✅ (`chain_port.py`) | `get_order_state(id) -> NONE\|LOCKED\|…`, `default_fee_bps()`, `latest_block()`, `get_block(n)`, `get_logs(from,to)`, `has_role(role, addr)`; ngoại lệ `ChainUnavailable` | `adapters/web3_chain.py` ✅ `Web3Chain(rpc_url, escrow_address)` (mọi lỗi RPC → `ChainUnavailable`; hash luôn có tiền tố `0x`). 🔲 `send_tx`, `balance_of`, `dispute_nonce` |
| `SignerPort` ✅ (`signer_port.py`) | `sign_quote(quote) -> 0x…65 byte`, `sender_address(role)`, `keccak(bytes)`, `to_checksum(addr)` | `adapters/env_signer.py` ✅ `EnvKeySigner` (khóa chỉ trong thuộc tính riêng, `repr` không lộ, 3 khóa vai trò khác địa chỉ, `verify_against_chain`), `recover_personal_sign(message, signature)`. 🔲 `sign_dispute` |
| `ClockPort` ✅ (`clock_port.py`) | `now_system()`, `now_chain()` | `adapters/clock.py` ✅ `HybridClock(chain)` (`max(hệ thống, block mới nhất)`), `FixedClock` cho test |
| `Repositories` ✅ (`repositories.py`) | `WalletRepo`, `SettingsRepo`, `PolicyRepo`, `CheckoutRepo`, `UnitOfWork` (thoát `with` chưa `commit()` thì ROLLBACK), `DuplicateWallet` | `adapters/mysql_repos.py` ✅ (`MySqlUnitOfWork(connection_factory)`); SQL tham số hóa; thứ tự khóa `cartItems → products` và đọc khóa **trước** đọc thường (xem ghi chú tuần 3) |
| (legacy sync) ✅ | `sync_legacy_status(conn, order_id, web3_status)` | `adapters/legacy_sync.py` ✅ (ghi `orders.status` theo bảng ánh xạ SRS 5.1: LOCKED→paid, PENDING_PAYMENT→pending khi reorg) |
| `NotificationPort` 🔲 | `notify_buyer_delivered(order)` | ghi bảng thông báo |
| (log) ✅ | `adapters/logging_filter.py`: `redact(text)`, `SensitiveDataFilter`, `install()` | che giá trị của trường `signature/private/key/mnemonic/seed/secret` và chữ ký 65 byte (không che tx hash) |

### 4.3. `application/` (ca sử dụng)
| Service | Hàm chính | Làm gì (UC) |
| --- | --- | --- |
| `WalletService` ✅ | `issue_nonce(user_id, address) -> {nonce, message, expires_at}`, `link_wallet(user_id, address, signature, nonce=None) -> {address, linked_at}`, `get_wallet(user_id) -> {linked, address, linked_at}` | UC-00: nonce 32 hex một lần (300 giây, ≤ 5/phút/tài khoản), dựng lại thông điệp, `recover`, tiêu thụ nonce nguyên tử, `UNIQUE(address)`; đổi ví = ví cũ `is_active=0`; lỗi: `INVALID_ADDRESS`, `NONCE_INVALID`, `BAD_SIGNATURE`, `WALLET_TAKEN`, `RATE_LIMITED` |
| `QuoteService` ✅ | `create_checkout(user_id, cart_item_ids) -> group`, `reissue_group_quotes(user_id, group_id) -> group`, `get_group(user_id, group_id)`, `check_web3_eligibility(user_id, cart_item_ids) -> {all_linked, shops[]}` (chỉ đọc) | UC-01: nhóm theo shop (≤ 5), cấp `onchain_order_id`, quy đổi, `docHash`, ký, ghi `checkout_groups`+`orders`+`orderLines`+`order_web3`+`order_quotes`, giữ chỗ kho, một transaction. Cấp lại: kiểm `NONE` trên chuỗi, giữ id/`docHash`/thời hạn, làm mới tỷ giá/phí/ví/hạn. Lỗi: `WALLET_NOT_LINKED` (`extra.party` = `buyer`\|`merchant`; merchant kèm `shop_id`, `shop_name`), `EMPTY_CART`, `CART_ITEM_NOT_FOUND`, `PRODUCT_UNAVAILABLE`, `OUT_OF_STOCK`, `SELF_PURCHASE`, `BATCH_TOO_LARGE`, `PENDING_GROUP_EXISTS`, `INVALID_AMOUNT`, `SETTING_INVALID`, `POLICY_*`, `CHAIN_UNAVAILABLE`, `GROUP_NOT_FOUND`, `INVALID_STATE` |
| `OrderQueryService` ✅ | `get_status(user_id, role, order_code)` | trạng thái polling đơn Web3 cho Buyer, Merchant hoặc Admin; trả `status, delivered_at, inspection_duration, disputed_at, dispute_timeout, anomaly, server_time, order_id` (404 `ORDER_NOT_FOUND` nếu không thuộc quyền) |
| `ShipperService` 🔲 | `list_orders(shipper)`, `deliver(code, shipper)` | UC-03: đọc chuỗi, idempotent, gửi `confirmDelivery` qua relayer (hàng đợi một luồng, ghi `tx_outbox`) |
| `DisputeService` 🔲 | `propose(code, admin, payout_to)`, `add_signature(code, user, signature)`, `submit(code)`, `add_note(code, user, text)` | UC-05/06: đề xuất, ký Arbitrator, nhận chữ ký Buyer/Merchant, nộp `resolveDispute` |
| `SettingsService` 🔲 | `set_fee(...)`, `set_category_policy(code, ...)`, `set_category_policy_map(category_id, policy_code)` | UC-09: tham số vận hành, ghi `updated_by` |
| `ReconcileService` 🔲 | `snapshot() -> report` | AC-10: số dư contract = Σ đơn mở + sổ chờ rút |

### 4.4. Indexer và tác vụ nền
| Thành phần | Làm gì |
| --- | --- |
| `adapters/indexer/loop.py` ✅ | `Indexer(...)`: `acquire_lock/release_lock(conn)` (`GET_LOCK('slopee_indexer')`), `run_once`, `run_forever`. Cửa sổ ≤ 500 block/transaction: ghi `chain_events` (`INSERT IGNORE`) → handler → `indexer_cursor`. Xử lý reorg qua `_rewind` / `rollback_orders_from_block`: lùi con trỏ, hoàn tác đơn về `PENDING_PAYMENT` + `orders.status='pending'`, chạy lại log |
| `adapters/indexer/handlers.py` ✅ | `HANDLERS`: `on_order_created` (đối chiếu báo giá: khớp → `order_web3=LOCKED` + đồng bộ `orders.status=paid` qua `legacy_sync` + xóa đúng dòng `cartItems`; lệch báo giá → `anomaly_flag=1`; đơn không có ở sàn → chỉ lưu log). 🔲 Tuần 5–6: handler Delivered, Disputed, Completed, Refunded |
| `python -m slopee_web3.adapters.indexer [--once]` ✅ | chạy Indexer như tiến trình riêng (từ thư mục `backend/`) |
| `scripts/bootstrap.sh` ✅ | dựng Anvil + build + deploy + `deployments/local.json` + `backend/.env.web3` (`--no-anvil`, `--fresh`, `--force-env`) |
| `scripts/smoke_week1.sh` ✅ | smoke test trên Anvil thật: báo giá Python ký → nạp → giao → nhận → kiểm số dư |
| `scripts/install_contract_deps.sh` ✅ | cài forge-std v1.9.4 + OpenZeppelin v5.0.2 đúng tag |
| `scripts/gen_eip712_vectors.py` ✅ | sinh `shared/eip712/vectors.json` (`orderQuote`, `disputeResolution`, `docHash`, `walletLink`; `--check` để CI so khớp) |
| `scripts/replay.sh`, `scripts/reconcile.py` 🔲 | replay từ block 0 (`--reset`), đối soát số dư |
| `jobs/` 🔲 | `QuoteExpirySweeper` (1 phút), `AutoRelease` (1 phút), `DeliveryTimeoutReminder` (1 giờ), `DisputeSigExpiry` (5 phút), `ReconcileSnapshot` (10 phút) |

### 4.5. API Web3 (snake_case, lỗi `{code,message}`; `adapters/flask_api/routes.py`)
Quyền: chỉ role `user`/`seller` (admin/shipper → 403 `forbidden`, dạng lỗi cũ; riêng API status hỗ trợ Admin). Danh tính chỉ từ token. Đăng ký bằng `register_web3(app)` trong `app.py`; chưa có `.env.web3` → các API này trả 503 `WEB3_NOT_CONFIGURED`, phần còn lại của app chạy bình thường. Khi `.env.web3` có mà khóa vai trò không khớp contract → **app không khởi động**.
| Method + path | Auth | Request | Response chính |
| --- | :-: | --- | --- |
| `POST /api/wallet/nonce` ✅ | U/S | `address` | `nonce, message, expires_at` — ký **nguyên văn** `message` |
| `POST /api/wallet/link` ✅ | U/S | `address, signature, nonce?` | `address, linked_at` (địa chỉ chữ thường) |
| `GET /api/wallet` ✅ | U/S | — | `linked, address, linked_at` |
| `POST /api/orders/eligibility` ✅ | U/S | `cart_item_ids[]` | **200** `all_linked, shops[{shop_id, shop_name, wallet_linked}]` — chỉ đọc |
| `POST /api/orders` ✅ | U/S | `cart_item_ids[]` (≤ 100 dòng, nhiều shop ≤ 5) | **201** `checkout_group_id, total_amount_raw, decimals, symbol, token_address, deadline, server_time, orders[...]` |
| `POST /api/checkout-groups/:id/quote` ✅ | U/S (chủ lô) | — | như trên (cấp lại cho cả lô); người khác → 404 |
| `GET /api/checkout-groups/:id` ✅ | U/S (chủ lô) | — | `checkout_group_id, total_amount_raw, decimals, symbol, deadline, status (hoặc MIXED), server_time, orders[...]` |
| `GET /api/orders/:code/status` ✅ | U/S/A | — | `status, delivered_at, inspection_duration, disputed_at, dispute_timeout, anomaly, server_time, order_id` (chỉ Buyer/Merchant của đơn hoặc Admin; người khác → 404 `ORDER_NOT_FOUND`) |
| `GET /api/orders/:code` 🔲 | U | — | chi tiết đầy đủ đơn hàng (Tuần 5) |
| `POST /api/orders/:code/dispute-note` 🔲 | U (Buyer) | lý do/bằng chứng | 200 |
| `GET /api/shipper/orders`, `POST /api/shipper/orders/:code/deliver` 🔲 | Shipper | — | đơn `LOCKED` được gán / kết quả |
| `POST /api/admin/disputes/:code/proposal` 🔲 | A | `payout_to` | đề xuất `PROPOSED` |
| `POST /api/disputes/:code/signatures` 🔲 | U | `resolution_id, signature` | trạng thái đề xuất (`PROPOSED|READY`) |
| `POST /api/disputes/:code/submit` 🔲 | U | — | `tx_hash` |
| `PUT /api/admin/category-policies/:code`, `PUT /api/admin/category-policy-map/:categoryId` 🔲 | A | thời hạn / `policy_code` | bản đã lưu |

### 4.6. Bảng Web3 (✅ đã có từ migration `0006`–`0020`)
`wallet_nonces`, `user_wallets`, `checkout_groups`, `order_web3` (1–1 với `orders`), `order_quotes`, `dispute_resolutions`, `dispute_signatures`, `chain_events`, `indexer_cursor`, `category_policies`, `category_policy_map`, `platform_settings`, `pending_balances`, `tx_outbox`, `onchain_id_seq`, `shipper_assignments`, `schema_migrations`.

### 4.7. Smart contract `SlopeeEscrowMaster` (+ `MockUSD`) — tuần 1 ✅ và tuần 2 ✅ (`contracts/`)
> ✅ `depositEscrow`, `confirmDelivery`, `earlyRelease`, `releaseAfterInspection`, `cancelIfUnfulfilled` + `_acceptQuote/_collect/_verifyQuote/_refund/_executePayout/_payout` (ETH bị từ chối → `pendingWithdrawals`). Struct `Order`/`Quote`, enum, sự kiện, hằng số, storage đã đủ từ tuần 1; ✅ tuần 2 thêm `raiseDispute`, `resolveDispute`, `arbitratorForceResolve`, `depositEscrowBatch`, `claimPending`, `setDefaultFeeBps`, `setFeeRecipient` (+ `_settle`, `_partyOf`). Test: `EscrowBase.t.sol` (helper), `SlopeeEscrowWeek1/Week2.t.sol`, `SlopeeEscrowBatch.t.sol` (T-25…T-34), `SlopeeEscrowMatrix.t.sol` (T-19), `SlopeeEscrowInvariant.t.sol` (T-18/T-33, handler), `TestActors.sol` (ví từ chối ETH, ví tái nhập, token độc hại/thu phí). ABI: `shared/abi/*.json` (+ bản chép `frontend/src/lib/abi/`). `MockUSD`: ERC-20 6 decimals, `mint` công khai (chỉ để thử). `script/Deploy.s.sol` ghi `deployments/local.json`.
| Hàm | Ai gọi | Làm gì |
| --- | --- | --- |
| `depositEscrow(q, sig)` | Buyer | xác minh báo giá → thu tiền → đơn `LOCKED` (`OrderCreated`) |
| `depositEscrowBatch(quotes, sigs)` | Buyer | nguyên tử, ≤ 5 đơn, một token; dùng chung `_acceptQuote` + `_collect` |
| `confirmDelivery(id)` | `SHIPPER_ROLE` | `LOCKED → DELIVERED`, ghi `deliveredAt` |
| `earlyRelease(id)` | Buyer | `DELIVERED → COMPLETED` |
| `releaseAfterInspection(id)` | bất kỳ (sau hạn) | giải ngân khi hết hạn kiểm tra |
| `raiseDispute(id)` | Buyer (trong hạn) | `DELIVERED → DISPUTED` |
| `resolveDispute(id, payoutTo, deadline, s1, s2)` | bất kỳ | cần 2 chữ ký của 2 bên khác nhau; `deadline < disputedAt + disputeTimeout` |
| `arbitratorForceResolve(id, payoutTo)` | `ARBITRATOR_ROLE` | chỉ khi `now ≥ disputedAt + disputeTimeout` |
| `cancelIfUnfulfilled(id)` | Buyer/Admin | hoàn tiền nếu `LOCKED` quá 14 ngày |
| `claimPending(token)` | chủ khoản chờ | rút số dư chờ (pull-payment) |
| `setDefaultFeeBps`, `setFeeRecipient` | Admin | trần phí ≤ 1.000 BPS / địa chỉ nhận phí |

### 4.8. Frontend Web3 (✅ tuần 3: xem mục 2; còn lại 🔲)
`pages/`: ✅ `Wallet.jsx` (UC-00), 🔲 `ShipperOrders.jsx`, `Dispute.jsx`; `components/`: `RequireRole`, ✅ `TxStepper`, `CountdownTimer`, `StatusBadge`, `AddressTag`, `AmountView`; `hooks/`: ✅ `useWallet`, ✅ `useEscrow`, 🔲 `useOrderStatus`, `useSignDispute`, `useServerClock`, ✅ `usePolling`, `useAuth`; `lib/`: ✅ `client`, `chain`, `eip712`, `errors`, `format`, `web3Checkout`, `walletLink`, `depositFlow`; thay đổi trang cũ: `Checkout.jsx` (✅ khung báo giá tuần 3; ✅ nạp gom 2 bước ví tuần 4 — chưa thử MetaMask/Anvil thật), `MyOrders.jsx` (nhóm theo lô, đồng hồ, khiếu nại), `SellerDashboard.jsx`, `AdminDashboard.jsx`, `Navbar.jsx` (nút ví), `App.jsx` (`RequireRole`, route mới).
`depositReducer(state, event)` là hàm thuần của máy trạng thái nạp tiền: `CHECK_NETWORK → CHECK_QUOTE → CHECK_ALLOWANCE → APPROVING → DEPOSITING → WAITING_INDEXER`.
