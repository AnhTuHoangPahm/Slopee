<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 2. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 2. KIẾN TRÚC TỔNG THỂ & STACK CÔNG NGHỆ

Hệ thống kết hợp phần lõi Web2 hiện có của Slopee (Flask + MySQL) với mô-đun Web3 (smart contract trên Anvil) theo kiến trúc không xâm lấn:

```text
[ REACT FRONTEND (ethers.js + MetaMask) ]
       │                            ▲
       │ 1. REST API                │ 5. Polling trạng thái đơn
       ▼                            │
[ FLASK BACKEND (Python) ] ─────────┴──► [ MYSQL (Slopee DB) ]
   │  ▲  │                                      ▲
   │  │  └─ Dịch vụ ký của sàn (báo giá,        │ 4. Ghi idempotent
   │  │     Trọng tài) + Relayer (Shipper)      │    (tx_hash, log_index)
   │  │                                         │
   ▼  │ 2. Tx của Relayer / chữ ký người dùng   │
[ ANVIL EVM CHAIN ] ─────────────────► [ PYTHON INDEXER (web3.py) ]
  (SlopeeEscrowMaster, MockUSD)    3. Đọc sự kiện on-chain theo con trỏ block
```

## 2.1. Thành phần và trách nhiệm

| Thành phần | Trách nhiệm |
|---|---|
| Smart Contract | Giữ tiền, ép luật chuyển trạng thái, chia phí, xác minh chữ ký báo giá và phán quyết. Là nguồn sự thật về tiền (BR-09). |
| Flask Backend | Xác thực và phân quyền người dùng bằng token ký (xây mới, mục 15), liên kết ví, tính giá và phát hành báo giá, quản lý đề xuất tranh chấp và chữ ký, relayer cho Shipper, API đọc trạng thái. |
| Indexer | Lắng nghe sự kiện, cập nhật `order_web3` (và đồng bộ bảng `orders` cũ), `dispute_resolutions`, kiểm tra khớp với dữ liệu sàn, lưu con trỏ block. |
| React Frontend | Kết nối MetaMask, gửi giao dịch nạp tiền (approve + deposit), mở khóa sớm, khiếu nại, ký EIP-712; màn hình Buyer, Merchant, Shipper, Admin. |

## 2.2. Khóa và cấu hình môi trường

| Khóa / cấu hình | Mục đích | Nơi lưu |
|---|---|---|
| `QUOTE_SIGNER_KEY` | Ký báo giá (`QUOTE_SIGNER_ROLE`) | Biến môi trường |
| `ARBITRATOR_KEY` | Ký phán quyết (`ARBITRATOR_ROLE`) | Biến môi trường |
| `SHIPPER_KEY` | Gửi `confirmDelivery` (`SHIPPER_ROLE`) | Biến môi trường |
| `FEE_RECIPIENT` | Địa chỉ nhận phí (chỉ cần địa chỉ công khai) | Cấu hình triển khai |
| `FX_VND_PER_TOKEN`, `QUOTE_TTL_SECONDS`, `DISPUTE_SIG_TTL_SECONDS`, `CONFIRMATIONS`, `PLATFORM_FEE_BPS` (mặc định 300), `AUTH_TOKEN_TTL_SECONDS` | Tham số vận hành. Phí báo giá = `min(PLATFORM_FEE_BPS, defaultFeeBps on-chain)` | Bảng `platform_settings` |
| `SECRET_KEY` | Ký token phiên đăng nhập | Biến môi trường, bắt buộc, không có giá trị mặc định |
| Chính sách theo nhóm hàng (`inspection_duration`, `dispute_timeout`) | Thời hạn kiểm tra và thời hạn tranh chấp của từng nhóm hàng | Bảng `category_policies` |

Bốn khóa của sàn phải khác nhau và không được ghi vào CSDL, nhật ký hay kho mã nguồn; `SECRET_KEY` là bí mật riêng, cũng không được ghi vào mã nguồn. Không có khóa của Buyer hoặc Merchant ở bất kỳ nơi nào của hệ thống (BR-01).
