# INSTALL.md: Hướng dẫn cài đặt Slopee (Web3 Escrow MVP)

Tài liệu này đưa một máy mới từ con số 0 đến lúc mở được `http://localhost:5173` và sẵn sàng demo. Mọi thứ chạy **cục bộ** trên chuỗi Anvil (chainId 31337) với khóa thử công khai; không có tiền thật. Sau khi cài xong, xem [DEMO_GUIDE.md](DEMO_GUIDE.md) để chạy demo.

> **Mức độ đã kiểm chứng.** Các bước 1-6 (Foundry, MySQL 8.0, Python 3.12, Node 22, `e2e_stack.sh up`, `demo_helper.py check/prepare/fund`) đã được chạy thật trên Ubuntu 24.04. Phần MetaMask (bước 7) và trình duyệt chưa được chạy tự động (không tải được trình duyệt ở máy soạn): làm theo, và báo lại nếu nhãn nút khác.

## 1. Yêu cầu

| Thành phần | Phiên bản | Ghi chú |
|---|---|---|
| Hệ điều hành | Linux, macOS hoặc **Windows qua WSL2** | Các script là bash. Chạy toàn bộ lệnh trong WSL, mở trình duyệt ở Windows vẫn được. |
| Python | 3.12 | |
| Node.js | 22 | |
| MySQL | 8.0.16 trở lên | Cần `CHECK` constraint. |
| Foundry | 1.8.x (`forge`, `anvil`, `cast`) | `curl -L https://foundry.paradigm.xyz \| bash` rồi `foundryup` |
| Trình duyệt + MetaMask | Chrome/Firefox mới | Chỉ cần cho demo thủ công |
| git, curl | | |

Cổng cần trống: **5173** (Vite), **5000** (backend), **8545** (Anvil), **3306** (MySQL).

## 2. Lấy mã và cài thư viện

```bash
git clone <địa-chỉ-repo> Slopee && cd Slopee
python3 -m venv .venv && source .venv/bin/activate        # khuyến nghị
pip install -r backend/requirements.txt
(cd frontend && npm ci)
```

Thư viện contract (forge-std v1.9.4, OpenZeppelin v5.0.2) tự được cài ở bước dựng stack; muốn cài trước: `./scripts/install_contract_deps.sh`. Lần `forge build` đầu cần tải solc 0.8.20 (cần mạng tới `binaries.soliditylang.org`).

## 3. Cấu hình MySQL

Ứng dụng kết nối bằng `DB_HOST` (mặc định `localhost`), `DB_USER` (mặc định `root`), `DB_PASSWORD` (mặc định rỗng), `DB_NAME` (mặc định `slopee_db`). Nếu `root` của bạn có mật khẩu:

```bash
export DB_PASSWORD='mật-khẩu-root'
```

Nếu MySQL dùng `auth_socket` cho root (Ubuntu mặc định) thì kết nối TCP bằng mật khẩu sẽ bị từ chối; đặt mật khẩu một lần:

```bash
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'mật-khẩu-root'; FLUSH PRIVILEGES;"
```

> Phiên bản cũ của mã mặc định `DB_USER=slopee` ở `routes/auth.py` làm đăng ký/đăng nhập lỗi `Access denied`; đã sửa ở Tuần 9 (test `test_w9_install_consistency.py`). Nếu vẫn gặp, kiểm `env | grep DB_`.

## 4. Dựng toàn bộ stack bằng một lệnh

```bash
export DB_PASSWORD='...'          # nếu cần
./scripts/e2e_stack.sh up
```

Lệnh này: dựng Anvil sạch (`--block-time 2`) → biên dịch và triển khai MockUSD + SlopeeEscrowMaster → ghi `deployments/local.json` và `backend/.env.web3` (khóa vai trò của Anvil, **chỉ dùng cục bộ**) → tạo CSDL + chạy migration → gieo tài khoản Admin và Shipper → bật backend (`:5000`), Indexer, Scheduler. Log nằm ở `.e2e/*.log`, Anvil ở `.anvil.log`. Mất khoảng 1-2 phút.

Tài khoản vận hành được gieo (đổi bằng biến môi trường nếu muốn):

| Vai trò | Tên đăng nhập | Mật khẩu | Biến |
|---|---|---|---|
| Admin (Trọng tài) | `e2e_admin` | `E2eAdminPass#2026` | `E2E_ADMIN_USER`, `E2E_ADMIN_PASSWORD` |
| Shipper | `e2e_shipper` | `E2eShipperPass#2026` | `E2E_SHIPPER_USER`, `E2E_SHIPPER_PASSWORD` |

Mật khẩu này chỉ để chạy thử cục bộ; không dùng ngoài môi trường demo.

**Làm sạch hoàn toàn** (khi dựng lại chuỗi mà CSDL còn dữ liệu cũ): `RESET_DB=1 ./scripts/e2e_stack.sh up` (xóa CSDL `slopee*` rồi dựng lại). Nếu không xóa, đơn và con trỏ Indexer cũ trỏ tới block không còn tồn tại.

`./scripts/e2e_stack.sh up` đặt `SLOPEE_ENV=test`, `SECRET_KEY=e2e-secret-key`, `AUTO_RELEASE_SECONDS=5`. Muốn chạy với khóa riêng của bạn, `export SECRET_KEY=...` trước.

<details><summary>Cách dựng từng bước (thay cho lệnh trên)</summary>

```bash
./scripts/bootstrap.sh --fresh --force-env       # Anvil + contract + backend/.env.web3
cd backend
python init_db.py && python migrate.py up
ADMIN_PASSWORD='...≥12 ký tự' flask --app app seed-admin --username <tên>
SHIPPER_PASSWORD='...≥12 ký tự' flask --app app seed-shipper --username <tên>
flask --app app run --port 5000                          # terminal 1
python -m slopee_web3.adapters.indexer                   # terminal 2 (một bản duy nhất)
python -m slopee_web3.adapters.scheduler                 # terminal 3 (một bản duy nhất)
```
Với cách này, `python scripts/demo_helper.py` cần đặt `E2E_ADMIN_USER/PASSWORD`, `E2E_SHIPPER_USER/PASSWORD` trùng tài khoản bạn đã gieo.
</details>

## 5. Chạy giao diện

```bash
cd frontend
npm run dev -- --port 5173 --strictPort
```

**Phải đúng `http://localhost:5173`** (không dùng `127.0.0.1`, không đổi cổng): backend chỉ cho CORS từ origin này và thông điệp liên kết ví chứa tên miền `localhost:5173`. `--strictPort` làm Vite báo lỗi thay vì lặng lẽ nhảy sang cổng khác.

Biến tùy chọn: `VITE_API_BASE` (mặc định `http://localhost:5000`), `VITE_RPC_URL` (mặc định `http://127.0.0.1:8545`).

## 6. Kiểm tra và tạo dữ liệu demo

```bash
python3 scripts/demo_helper.py check      # Anvil, contract, backend, đăng nhập Admin/Shipper
python3 scripts/demo_helper.py prepare    # demo_buyer, demo_shop_a, demo_shop_b (+ sản phẩm); chạy lại an toàn
```

`check` in `Sẵn sàng demo.` khi mọi thứ ổn; nếu không, nó liệt kê **tất cả** vấn đề một lượt.

## 7. Cấu hình MetaMask

1. Thêm mạng: **Settings → Networks → Add network manually**: tên `Anvil`, RPC `http://127.0.0.1:8545`, Chain ID `31337`, ký hiệu `ETH`. (Hoặc bấm **Chuyển sang mạng Anvil** ở trang `/wallet`, giao diện tự gọi `wallet_addEthereumChain`.)
2. Tạo **3 tài khoản MetaMask mới**: Buyer, Shop A, Shop B. **Không** nhập khóa của Anvil.
3. Cấp ETH thử và mUSD cho từng địa chỉ (copy từ MetaMask):
   ```bash
   python3 scripts/demo_helper.py fund 0xĐỊA_CHỈ_BUYER --usd 1000
   python3 scripts/demo_helper.py fund 0xĐỊA_CHỈ_SHOP_A --usd 0 --eth 10
   python3 scripts/demo_helper.py fund 0xĐỊA_CHỈ_SHOP_B --usd 0 --eth 10
   ```
4. Để thấy số mUSD trong MetaMask: **Import tokens** → địa chỉ `mockUSD` trong `deployments/local.json`, 6 chữ số thập phân.
5. Liên kết ví (mỗi ví một tài khoản Slopee): đăng nhập `demo_buyer` / `demo_shop_a` / `demo_shop_b` (mật khẩu `SecurePass123!`), mở `/wallet`, **Kết nối MetaMask** (chọn đúng tài khoản MetaMask) → **Liên kết ví này** (chỉ ký thông điệp, không tốn gas). Một ví chỉ liên kết được một tài khoản.

**Sau mỗi lần dựng lại Anvil** (`--fresh`, `RESET_DB=1 … up`): MetaMask giữ nonce cũ và báo lỗi nonce/giao dịch kẹt. Vào **Settings → Advanced → Clear activity tab data** cho từng tài khoản, và phải liên kết lại ví (CSDL đã bị xóa).

## 8. Chạy bộ kiểm thử

```bash
python -m pytest test                          # cần MySQL; test @anvil cần stack đang chạy (REQUIRE_ANVIL=1 để bắt buộc)
(cd contracts && forge test)                   # test contract
(cd frontend && npx vitest run && npm run build)
(cd frontend && npx playwright install firefox && npx playwright test --project=web3-e2e)   # E-01…E-07, cần stack đang chạy
python scripts/scan_no_user_keys.py -v         # AC-09
python scripts/reconcile.py --deep --events    # AC-10
```
Test E2E và một số test `anvil` **tua giờ Anvil vĩnh viễn**; dựng lại stack sạch (`RESET_DB=1 ./scripts/e2e_stack.sh up`) **trước buổi demo**, đừng dùng chung chuỗi đã chạy test.

## 9. Tắt và dọn

```bash
./scripts/e2e_stack.sh down                    # tắt backend/Indexer/Scheduler
kill $(cat .anvil.pid)                         # tắt Anvil
```

## 10. Xử lý sự cố cài đặt

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Thiếu 'forge'` | Chưa cài Foundry / PATH | `foundryup`, mở lại terminal |
| `forge build` lỗi DNS/`list.json` | Không tải được solc | Cần mạng tới `binaries.soliditylang.org`, hoặc đặt sẵn `~/.svm/0.8.20/solc-0.8.20` |
| `Can't connect to MySQL` | MySQL chưa chạy | `sudo service mysql start` |
| `Access denied for user` | Sai mật khẩu hoặc root dùng `auth_socket` | Bước 3; kiểm `env \| grep DB_` |
| Đăng nhập báo 500, log `OperationalError` | Biến `DB_*` không tới được backend | Export trước khi chạy `e2e_stack.sh up` |
| `Hết giờ chờ http://localhost:5000` | Backend không lên | Đọc `.e2e/backend.log` |
| Trang trắng, lỗi CORS | Vào bằng `127.0.0.1` hoặc cổng ≠ 5173 | Dùng đúng `http://localhost:5173` |
| `/wallet` không có mạng Anvil, hoặc báo sai chainId | Chưa thêm mạng | Bước 7.1 |
| MetaMask kẹt nonce | Anvil bị dựng lại | Clear activity tab data |
| `WEB3_NOT_CONFIGURED` (503) | Thiếu `backend/.env.web3` | Chạy `./scripts/bootstrap.sh --force-env` |
| Đơn mãi `PENDING_PAYMENT` | Indexer không chạy | `.e2e/indexer.log`; chỉ chạy **một** Indexer |
| `replay.sh`: "Đang có Indexer/Scheduler chạy" | Replay giữ khóa Indexer và không được có giao dịch mới giữa chừng | `./scripts/e2e_stack.sh down` rồi chạy lại (`--allow-scheduler` nếu chắc chắn) |

## Truy cập từ máy khác trong LAN/VPN (Tailscale, Hamachi, Radmin...) + MetaMask

Chỉ chạy đúng 2 lệnh như thường lệ (máy chủ vẫn mở `localhost:5173`):

```bash
RESET_DB=1 ./scripts/e2e_stack.sh up
(cd frontend && npm run dev -- --port 5173 --strictPort)     # terminal khác
```

**Mô hình mạng:** chỉ cổng **5173** (Vite) nghe mọi interface. Backend `:5000`, Anvil `:8545`, MySQL `:3306` chỉ nghe `127.0.0.1`.
Máy khác đi qua proxy cùng origin của Vite: `/api` → Flask, `/rpc` → Anvil (chỉ cho phương thức đọc + `eth_sendRawTransaction`;
chặn `eth_sendTransaction`, `eth_accounts`, `anvil_*`, `evm_*`... vì Anvil mở khóa sẵn tài khoản công khai). Không cần CORS.

**Vào web (không ví):** mở firewall inbound TCP 5173 (tick cả profile Public cho adapter VPN), rồi `http://<IP-VPN>:5173`.

**Dùng MetaMask từ máy khác (cần HTTPS):** trình duyệt chỉ bật `window.ethereum` ở secure context và MetaMask chỉ nhận RPC
https ngoài loopback. Chạy **một lần** `./scripts/dev_cert.sh [IP-VPN ...]`, sau đó cùng lệnh `npm run dev` tự chạy HTTPS khi thấy `frontend/certs/`
(xóa bằng `./scripts/dev_cert.sh --remove`).
- Tailscale (khuyến nghị): chứng chỉ thật, vào `https://<máy>.<tailnet>.ts.net:5173`, mọi thiết bị tin cậy sẵn.
- mkcert: thiết bị khác phải cài `rootCA.pem`. openssl tự ký: trình duyệt cảnh báo, MetaMask extension thường từ chối RPC tự ký.
- Nút "đổi sang mạng Anvil" tự dùng RPC `https://<host>:5173/rpc` khi không mở bằng localhost (ghi đè bằng `VITE_RPC_URL`).

**Đóng cổng DB:** `e2e_stack.sh up` kiểm tra `bind_address`/`mysqlx_bind_address` của MySQL và cảnh báo nếu nghe ngoài loopback
(mặc định MySQL 8 nghe `*`). Sửa `my.ini`/`my.cnf` mục `[mysqld]`: `bind-address=127.0.0.1` + `mysqlx-bind-address=127.0.0.1`, khởi động lại MySQL;
đặt `REQUIRE_DB_LOOPBACK=1` để script dừng thay vì chỉ cảnh báo. Không mở firewall cho 3306/33060/5000/8545.

Playwright vẫn chạy http://localhost:5173 (ép `VITE_HTTPS=0`); muốn test qua HTTPS: `E2E_BASE_URL=https://localhost:5173 E2E_NO_WEBSERVER=1`.
