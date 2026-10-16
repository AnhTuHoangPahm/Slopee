<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 6. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 6. DỮ LIỆU CHUẨN EIP-712

| Thành phần | Giá trị |
|---|---|
| Domain | `name = "SlopeeEscrow"`, `version = "1"`, `chainId` (Anvil mặc định 31337), `verifyingContract` = địa chỉ contract |
| `OrderQuote` | `(uint256 orderId, address buyer, address merchant, address token, uint256 amount, uint256 inspectionDuration, uint256 disputeTimeout, uint256 feeBps, bytes32 docHash, uint256 deadline)` — ký bởi `QUOTE_SIGNER_ROLE`. Struct `Quote` trong ABI của `depositEscrow` có cùng danh sách và thứ tự trường. |
| `DisputeResolution` | `(uint256 orderId, address payoutTo, uint256 amount, uint256 nonce, uint256 deadline)` — ký bởi Buyer, Merchant hoặc Arbitrator |

Chuỗi định nghĩa kiểu và thứ tự trường ở Python (eth_account), JavaScript (ethers.js) và Solidity phải giống hệt nhau. Dùng chung một tệp định nghĩa kiểu và có test chéo ngôn ngữ (băm cùng dữ liệu ở 3 nơi, kết quả phải bằng nhau).
