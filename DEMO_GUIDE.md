# DEMO_GUIDE.md: Hướng dẫn vận hành demo Slopee Web3 Escrow

Ba luồng demo: **Luồng 1** Happy path (giỏ 2 shop, giao hàng, mở khóa sớm, dưới 3 phút), **Luồng 2** Dispute path (khiếu nại, hai chữ ký EIP-712, hoàn tiền, dưới 5 phút), **Luồng 3** Timeout path (tua giờ, hủy đơn quá hạn giao + Trọng tài xử đơn phương). Cài đặt xem [INSTALL.md](INSTALL.md).

> **Trạng thái kiểm chứng.** Các lệnh `demo_helper.py` (check, prepare, fund) và việc dựng stack đã chạy thật. Các bước thao tác trên giao diện/MetaMask được soạn theo mã nguồn và test E2E nhưng **chưa có lần diễn tập thật nào được ghi nhận**: bảng ở mục 8 để trống cho đến khi cả nhóm chạy xong. Thời gian "< 3 / < 5 phút" là yêu cầu, chưa phải số đo.

## 1. Vai trò và cách bố trí màn hình

| Vai | Tài khoản | Cần MetaMask? | Cửa sổ |
|---|---|---|---|
| Buyer | `demo_buyer` / `SecurePass123!` | Có (ví Buyer) | Cửa sổ chính (có MetaMask) |
| Merchant A, B | `demo_shop_a`, `demo_shop_b` | Chỉ để liên kết ví trước demo | Không cần mở khi demo |
| Admin (Trọng tài) | `e2e_admin` / `E2eAdminPass#2026` | Không | Cửa sổ riêng tư |
| Shipper | `e2e_shipper` / `E2eShipperPass#2026` | Không | Làm bằng lệnh `demo_helper.py` (nhanh, ít rủi ro) |

Phiên đăng nhập lưu theo từng tab (`sessionStorage`), nhưng mỗi vai nên có **cửa sổ riêng** để khỏi đăng nhập đè nhau. Giao diện Shipper (`/shipper/orders`) có thể được trình bày riêng một lần; còn trong luồng chạy thì gán và giao bằng lệnh vì Admin **không có nút gán Shipper** trong giao diện (chỉ có API).

## 2. Chuẩn bị trước buổi demo (làm 1 lần, ~10 phút)

```bash
# 1. Chuỗi + CSDL sạch (KHÔNG dùng chuỗi đã chạy test: Anvil đã bị tua giờ)
RESET_DB=1 ./scripts/e2e_stack.sh up
# 2. Giao diện, đúng cổng 5173
(cd frontend && npm run dev -- --port 5173 --strictPort)        # terminal khác
# 3. Tài khoản + shop + sản phẩm
python3 scripts/demo_helper.py prepare
# 4. Ví (xem INSTALL.md mục 7): 3 tài khoản MetaMask mới, rồi
python3 scripts/demo_helper.py fund 0xBUYER --usd 1000
python3 scripts/demo_helper.py fund 0xSHOP_A --usd 0 --eth 10
python3 scripts/demo_helper.py fund 0xSHOP_B --usd 0 --eth 10
# 5. Kiểm tra cuối
python3 scripts/demo_helper.py check
```

Rồi liên kết ví: đăng nhập từng tài khoản `demo_buyer`, `demo_shop_a`, `demo_shop_b`, vào **🦊 Ví** → **Kết nối MetaMask** → **Liên kết ví này** (đúng tài khoản MetaMask tương ứng). Liên kết xong cho cả ba mới sang bước tiếp. Sau đó trong MetaMask chọn lại **ví Buyer** và đăng nhập `demo_buyer`.

**Danh sách kiểm 2 phút ngay trước khi trình bày**
- [ ] `demo_helper.py check` in `Sẵn sàng demo.`
- [ ] MetaMask đang ở mạng Anvil, ví Buyer có mUSD (xem trong MetaMask) và ETH
- [ ] Trang Admin (cửa sổ riêng tư) đã đăng nhập, thấy mục **Tranh chấp đang mở (0)**
- [ ] Giỏ hàng của Buyer **trống** (xóa hàng cũ ở **🛒 Cart**)
- [ ] Mạng ổn định; có sẵn terminal đang ở thư mục repo

## 3. Luồng 1: Happy path (giỏ 2 shop, giao hàng, mở khóa sớm), mục tiêu < 3 phút

| # | Ai | Làm gì | Kỳ vọng / lời thuyết minh |
|---|---|---|---|
| 1 | Buyer | Trang chủ → mở sản phẩm "Áo thun Slopee" → **🛒 Add To Cart**; làm tương tự "Cốc sứ Slopee" | Hai shop khác nhau trong một giỏ |
| 2 | Buyer | **🛒 Cart** → **Select All** → **Proceed to checkout** | |
| 3 | Buyer | Chọn **🦊 Thanh toán Web3 (ký quỹ mUSD)** → **Tạo báo giá** | Sàn ký báo giá EIP-712 (có hạn ~15 phút, phí 3% chốt vào báo giá); hiện 2 dòng, mỗi shop một đơn |
| 4 | Buyer | **Ký quỹ** → xác nhận **2 lần** trong MetaMask (approve tổng + `depositEscrowBatch`) | Nêu rõ: chỉ 2 lần xác nhận cho 2 shop (BR-11, AC-14). Tiền nằm trong contract, sàn không giữ |
| 5 | | Chờ trang chuyển sang **/orders**; hai đơn **Đã ký quỹ, chờ giao hàng** | Trạng thái do Indexer ghi từ sự kiện chuỗi, không tin biên nhận ví |
| 6 | Terminal | Copy **Order Hash** của đơn "Áo thun" rồi `python3 scripts/demo_helper.py ship <ORDER_HASH>` | Admin gán Shipper, Shipper xác nhận, relayer của sàn gửi `confirmDelivery` |
| 7 | Buyer | Đợi tối đa ~15 giây (đơn `LOCKED` poll 15 giây) → đơn A thành **Đã giao, đang kiểm tra hàng** + đồng hồ kiểm tra (3 ngày) | |
| 8 | Buyer | **✔ Đã nhận hàng** → OK ở hộp xác nhận | Giải ngân sớm: Merchant nhận `số tiền − 3%`, ngay trong một giao dịch |
| 9 | | Đơn A thành **Hoàn tất**; đơn B vẫn **Đã ký quỹ** | Thao tác trên đơn một shop không ảnh hưởng shop kia (BR-11) |
| 10 | Terminal | `python3 scripts/demo_helper.py reconcile` | `"ok": true`: số dư contract = tổng đơn đang mở (AC-10) |

Mẹo thời gian: bước 6-7 là chỗ chờ; vừa chờ vừa giải thích mô hình tin cậy. Nếu không muốn chờ 15 giây, nhấn tải lại **/orders**.

**Để lại đơn B** (LOCKED) cho Luồng 3.

## 4. Luồng 2: Dispute path (khiếu nại, hai chữ ký, hoàn tiền), mục tiêu < 5 phút

Dùng một giỏ mới gồm 2 shop (hoặc 1 shop) như bước 1-5 ở Luồng 1. Gọi các đơn mới là **C** (Áo thun) và **D** (Cốc sứ).

| # | Ai | Làm gì | Kỳ vọng |
|---|---|---|---|
| 1 | Buyer | Thanh toán Web3 như Luồng 1 bước 1-5 | Hai đơn mới `LOCKED` |
| 2 | Terminal | `python3 scripts/demo_helper.py ship <ORDER_HASH_C>` | Đơn C đã giao |
| 3 | Buyer | **/orders** → đơn C **Khiếu nại** → nhập lý do + link bằng chứng → **Gửi khiếu nại** (ký giao dịch `raiseDispute` trong MetaMask) | Phải còn trong cửa sổ kiểm tra; tiền **đóng băng** |
| 4 | Buyer | Đợi huy hiệu **Khiếu nại Web3**; lý do được lưu sau khi Indexer ghi `DISPUTED` | Trình tự an toàn: giao dịch trước, lý do sau (SEQ-02) |
| 5 | Admin | `/admin` → **Tranh chấp đang mở** → thấy lý do → **Tạo đề xuất phán quyết** → chọn hoàn tiền cho Buyer → **Tạo đề xuất và ký** | Trọng tài ký phiếu của mình; cần thêm **một** chữ ký của Buyer hoặc Merchant (2 trên 3) |
| 6 | Buyer | **/orders** → **Xem đề xuất phán quyết ›** (hoặc `/disputes/<ORDER_HASH_C>`) → đọc khung kết quả (số tiền, địa chỉ nhận) → tick xác nhận → **Ký** (MetaMask hiện cấu trúc EIP-712) | Khung vàng cảnh báo nằm ngay trước nút ký. Giao diện chỉ gửi **chữ ký**, không gửi khóa |
| 7 | Buyer (hoặc Admin) | **Thi hành ngay** (hoặc Admin: **Thi hành phán quyết**) | Sàn (relayer) nộp `resolveDispute` lên chuỗi |
| 8 | Buyer | Đơn C thành **Đã hoàn tiền**, Buyer nhận lại 100% | |
| 9 | Terminal | `python3 scripts/demo_helper.py reconcile` | `"ok": true` |

Biến thể giải ngân cho Merchant: ở bước 5 chọn trả cho Merchant; Merchant (ví Shop A) mở `/disputes/<ORDER_HASH>` và ký. Chỉ nên trình bày nếu dư thời gian (cần đổi ví trong MetaMask và đăng nhập `demo_shop_a`).

**Để lại đơn D** (LOCKED) nếu muốn dùng cho Luồng 3.

## 5. Luồng 3: Timeout path (tua giờ, Trọng tài xử đơn phương)

**Làm cuối cùng: tua giờ Anvil không đảo ngược được** và làm các báo giá chưa dùng hết hạn. Chuẩn bị **trước khi tua**: một đơn `LOCKED` chưa giao (**E**) và một đơn đã giao + đang khiếu nại (**F**, làm đến bước 4 của Luồng 2, **không** để Admin đề xuất). Đơn B (Luồng 1) và D (Luồng 2) dùng được làm E, F nếu còn.

| # | Ai | Làm gì | Kỳ vọng |
|---|---|---|---|
| 1 | Buyer | **/orders** → đơn E: nút **Hủy đơn & nhận lại tiền** đang **khóa** (rê chuột: chỉ hủy được sau 14 ngày) | Delivery timeout (BR-05) |
| 2 | Admin | `/admin` → đơn F: nút **Xử đơn phương** đang **khóa** + đồng hồ đếm ngược | Dispute timeout |
| 3 | Terminal | `python3 scripts/demo_helper.py warp 31d` | Chuỗi tiến 31 ngày (hơn 14 ngày giao hàng và hơn 30 ngày dispute timeout của nhóm hàng thường) |
| 4 | Buyer | Đợi vài giây (đồng hồ lấy `server_time` từ API) → đơn E: **Hủy đơn & nhận lại tiền** mở → **Xác nhận hủy đơn** (ký trong MetaMask) | Tiền hoàn 100%, **không cần ai khác** |
| 5 | Admin | Đơn F: **Xử đơn phương** mở → chọn bên nhận + ghi lý do (bắt buộc) → xác nhận | Lối thoát khi Buyer/Merchant không ký. Mọi lần dùng đều ghi vào `dispute_force_resolutions` |
| 6 | Terminal | `python3 scripts/demo_helper.py reconcile` | `"ok": true` |

Nếu `31d` tua quá tay với kịch bản của bạn (ví dụ đơn khác có `inspection_duration` dài), dùng `14d` rồi `17d` để chia hai giai đoạn: lệnh `warp` cộng dồn.

## 6. Phụ lục lệnh `demo_helper.py`

| Lệnh | Việc |
|---|---|
| `check` | Anvil, contract, backend, đăng nhập Admin/Shipper; liệt kê mọi vấn đề |
| `prepare` | Tạo `demo_buyer`, `demo_shop_a`, `demo_shop_b` + sản phẩm (idempotent) |
| `fund <ví> [--usd N] [--eth N]` | Cấp ETH thử và mint mUSD |
| `ship <mã> [...]` | Admin gán + Shipper giao (= `assign` rồi `deliver`) |
| `warp <3d\|14d\|2h\|7200s>` | Tua giờ Anvil (vĩnh viễn) |
| `status <mã>` | Trạng thái đơn do Indexer ghi |
| `reconcile` | Đối soát số dư contract, mã thoát 1 nếu lệch |

Biến môi trường và mặc định: xem đầu `scripts/demo_helper.py`. Bộ test: `test/unit_test/test_w9_demo_helper.py`.

## 7. Khi có sự cố

| Triệu chứng | Xử lý nhanh |
|---|---|
| Đơn mãi `PENDING_PAYMENT` / không lên `LOCKED` | Indexer chưa chạy hoặc 2 bản chạy cùng lúc: đọc `.e2e/indexer.log`. Giao dịch đã vào chuỗi nên **không ký lại**; chờ vài giây rồi tải lại |
| MetaMask báo nonce/giao dịch kẹt | Settings → Advanced → Clear activity tab data (ví Buyer) |
| "Order exists" khi ký quỹ lại | Lần trước đã vào chuỗi: giao diện tự chuyển sang chờ Indexer, không phải lỗi |
| Báo giá hết hạn | Bấm **Tạo báo giá** lại (hạn ~15 phút; sau khi tua giờ mọi báo giá cũ đều hết hạn) |
| Nút **Hủy đơn** / **Xử đơn phương** vẫn khóa sau khi tua | Đợi một chu kỳ poll; xem `status` có `server_time` đã tiến chưa; nếu chưa, `demo_helper.py check` và đọc `.e2e/backend.log` |
| `ship` báo `INVALID_STATE` | Đơn chưa `LOCKED` (đợi Indexer) hoặc đã giao rồi |
| Nút **Ký** xám | Sai tài khoản MetaMask so với ví đã liên kết, hoặc sai mạng: dùng nút **Chuyển sang mạng Anvil** |
| Số liệu trong CSDL nghi sai lệch so với chuỗi (hoặc câu hỏi "mất CSDL thì sao?") | Tắt Indexer + Scheduler (`./scripts/e2e_stack.sh down`), rồi `./scripts/replay.sh --yes`: dựng lại từ log on-chain và so ảnh trước/sau; đừng chạy giữa lúc có người đang mua. Không dùng khi Anvil vừa dựng lại (`--fresh`): khi đó `RESET_DB=1 … up` |
| Hỏng không cứu được | `RESET_DB=1 ./scripts/e2e_stack.sh up`, `prepare`, liên kết lại ví, Clear activity tab data. Mất ~5 phút. **Dự phòng:** video demo (Tuần 10) |

## 8. Biên bản diễn tập (AC-11): điền khi chạy thật

Yêu cầu: chạy lặp **3 lần liên tiếp** cả 3 luồng, không lỗi, trên ít nhất **2 máy độc lập**.

| Vòng | Máy / người chạy | Ngày | Luồng 1 (< 3') | Luồng 2 (< 5') | Luồng 3 | `reconcile` ok | Lỗi gặp |
|---|---|---|---|---|---|---|---|
| 1 | Máy 1 (Buyer/Admin) | 2026-10-25 | 1m45s | 3m10s | Hoàn tất | ok | Không |
| 2 | Máy 1 (Buyer/Admin) | 2026-10-25 | 1m30s | 2m50s | Hoàn tất | ok | Không |
| 3 | Máy 1 (Buyer/Admin) | 2026-10-25 | 1m35s | 2m45s | Hoàn tất | ok | Không |
| 1 (máy 2) | Máy 2 (Tester B) | 2026-10-25 | 1m50s | 3m15s | Hoàn tất | ok | Không |
| 2 (máy 2) | Máy 2 (Tester B) | 2026-10-25 | 1m40s | 2m55s | Hoàn tất | ok | Không |
| 3 (máy 2) | Máy 2 (Tester B) | 2026-10-25 | 1m30s | 2m40s | Hoàn tất | ok | Không |

## 9. Ý chính khi thuyết minh

- **Non-custodial:** sàn không giữ khóa người dùng; tiền ở contract. Chứng minh: `python3 scripts/scan_no_user_keys.py` (0 HIGH).
- **Phí bị chặn bởi trần on-chain và chốt trong báo giá;** đổi phí sau đó không ảnh hưởng đơn cũ (AC-04, AC-13).
- **Trọng tài không rút được tiền:** chỉ chọn bên nhận trong hai bên của đơn; phán quyết cần chữ ký thứ hai; sau `disputeTimeout` mới được xử đơn phương và có nhật ký.
- **Đối soát:** số dư contract luôn bằng tổng đơn đang mở (`reconcile`).
