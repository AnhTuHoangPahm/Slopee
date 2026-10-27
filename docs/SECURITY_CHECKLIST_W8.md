# Tuần 8 [A] — Non-custodial (E-05, AC-09) và checklist an ninh contract

> Phạm vi: hai việc của Thành viên A trong Tuần 8 (Feature Freeze). **Không đổi contract** (ABI/storage đóng băng từ M1); chỉ thêm script quét, test, tài liệu và một bước CI.
> Cách chạy lại mọi thứ ở mục 4.

## 1. E-05 / AC-09 — Không có khóa riêng hay seed của người dùng

**Công cụ:** `scripts/scan_no_user_keys.py` (chỉ đọc, chỉ dùng thư viện chuẩn). Test: `test/unit_test/test_w8_non_custodial.py` (57 ca) và `test/integration_test/test_w8_non_custodial_mysql.py` (3 ca, MySQL thật). CI: 3 bước mới trong job `backend`.

**Cách làm.** Khóa của người dùng chỉ có thể xuất hiện dưới vài dạng nhận diện được, nên script tìm đúng các dạng đó ở ba nơi: mã nguồn, lược đồ/CSDL, log.

| Nơi quét | Bắt gì | Kết quả trên repo |
| :--- | :--- | :--- |
| Mã nguồn (377 tệp, gồm `frontend/src/lib`) | Chuỗi 64 hex trong ngữ cảnh khóa; khối PEM; cụm từ khôi phục 12–24 từ; mã chạy thật gọi `Account.create/from_mnemonic`, `Wallet.createRandom/fromPhrase`, `new Wallet(`, `personal_unlockAccount`; trường `private_key`/`mnemonic`/`seed` trong API; khóa ghi vào `localStorage/sessionStorage`; biến môi trường dạng `*_KEY/SECRET/MNEMONIC/SEED` ngoài danh sách vận hành | **0 HIGH** |
| Lược đồ (`schema.sql` + 23 migration) | Cột tên giống nơi chứa khóa/seed | **0 HIGH**; `user_wallets` chỉ có `id, user_id, address, is_active, linked_at` |
| CSDL đang chạy (`--db`) | Như trên, cộng giá trị: hex64 ở cột không phải hash/chữ ký, khóa thử, PEM, mnemonic, trường khóa trong JSON | Chạy trong CI trên MySQL dựng từ `schema.sql`; chưa có MySQL ở máy soạn tài liệu này |
| Log (`*.log`, `logs/`, hoặc `--logs`) | Như trên, cộng chữ ký 65 byte chưa bị che | Repo không chứa tệp log; test chứng minh đường logger → `SensitiveDataFilter` → bộ quét cho kết quả sạch |

**Phân biệt khóa vận hành và khóa người dùng.** Backend giữ đúng 3 khóa vận hành (`QUOTE_SIGNER_KEY`, `ARBITRATOR_KEY`, `SHIPPER_KEY`, SRS 2.2), chỉ nạp từ môi trường bởi `env_signer.py` (nơi duy nhất được gọi `Account.from_key`; `Web3Settings` không có trường khóa nào khác). Mọi khóa còn lại trong repo là khóa **công khai của Anvil** dùng làm ví thử trong test/script. Script **không ghi cứng** danh sách này: nó tự suy ra 20 khóa từ mnemonic công khai `test … junk` (BIP39 + BIP32, `m/44'/60'/0'/0/i`). Khóa #1–#3 (vận hành) khớp `bootstrap.sh`; khóa #5+ (ví buyer/merchant giả lập) chỉ được nằm ở `test/`, `frontend/src/__tests__/`, `contracts/test/`, `scripts/`. Khóa thử nằm ở mã chạy thật là HIGH.

**Script có thật sự bắt được lỗi không?** Một bộ quét "câm" cũng báo sạch, nên test dựng repo giả với 23 kiểu rò khóa và đòi script báo đúng từng kiểu, cùng 12 mẫu hợp lệ không được báo nhầm (tx hash, `docHash`, `SECRET_KEY` của Flask, `token` trong sessionStorage...). Khi viết test này đã lộ một lỗ hổng của chính script (nó từng bỏ qua toàn bộ thư mục tên `lib`, tức cả `frontend/src/lib`); đã sửa, chỉ còn bỏ `contracts/lib/`.

**Hai cảnh báo (WARN, không phải lỗi).** `test/w3_support.py` dòng 40–41 (`merchant5`, `merchant6`, ghi chú "#10", "#11") chứa khóa **không** thuộc 20 tài khoản Anvil: #10 khác khóa Anvil thật đúng một ký tự hex, #11 khác hẳn. Chúng chỉ là khóa thử tự tạo (test chỉ ký, không gửi giao dịch), không liên quan người dùng thật. Ngoài ra khóa `stranger` (ghi chú "#12") thực ra là Anvil #4, cũng là địa chỉ `feeRecipient` của `Deploy.s.sol`; nhãn sai, không ảnh hưởng kết quả test hiện có. Đề xuất sửa nhãn ở Tuần 9 nếu còn thời gian; không đụng vào lúc Feature Freeze.

**Ba lớp bảo vệ độc lập cho nguyên tắc này:** (1) không có đường mã nào tạo/nhập khóa người dùng (quét mã); (2) không có nơi lưu (quét lược đồ + CSDL); (3) nếu lỡ ghi ra log thì `SensitiveDataFilter` che giá trị trường `private/key/mnemonic/seed/secret` và mọi chữ ký 65 byte (quét log + test).

## 2. Checklist an ninh contract (`SlopeeEscrowMaster.sol`)

Rà bằng đọc mã từng hàm kết hợp với test hiện có. `Slither` và `forge test` **không chạy được ở máy soạn tài liệu này** (không tải được Foundry/solc), nên trạng thái các test mới là `[~]` cho tới khi CI xanh.

### 2.1 Reentrancy — ĐẠT

| Hàm có tương tác ngoài | Bảo vệ | Thứ tự |
| :--- | :--- | :--- |
| `depositEscrow`, `depositEscrowBatch` | `nonReentrant` | Ghi đơn `LOCKED` trước, rồi mới `safeTransferFrom` |
| `earlyRelease`, `releaseAfterInspection`, `cancelIfUnfulfilled` | `nonReentrant` | `state` đổi trước `_payout` |
| `resolveDispute`, `arbitratorForceResolve` | `nonReentrant` | `nonce++` và `state` đổi trước `_payout` |
| `claimPending` | `nonReentrant` | Xóa số dư về 0 trước khi chuyển |
| `confirmDelivery`, `raiseDispute`, hàm quản trị | (không có lời gọi ngoài) | — |

Mọi hàm di chuyển tiền dùng chung một khóa nên không có tái nhập chéo hàm. ETH trả bằng `call` giới hạn 30.000 gas, thất bại thì ghi sổ chờ rút thay vì revert (không kẹt đơn). Bằng chứng: T-16 (ví từ chối ETH), T-17 (ví tấn công gọi lại 4 hàm, token độc hại gọi lại khi nạp / chi trả / phán quyết), INV-01 và `contractAlwaysSolvent` (128 run × 100 lời gọi).

### 2.2 Signature Malleability và Replay — ĐẠT

- OpenZeppelin 5.0.2 `ECDSA.recover` từ chối `s` cao (`ECDSAInvalidSignatureS`), `v` ngoài {27, 28}, độ dài sai và địa chỉ 0.
- Digest dùng `abi.encode` với trường độ dài cố định (không có kiểu động nên không mơ hồ mã hóa) và domain `EIP712("SlopeeEscrow","1")` gắn `chainId` + `verifyingContract` nên chữ ký không dùng lại được ở contract hay chain khác.
- Báo giá chỉ dùng được một lần vì `orderId` đã `!= NONE` sau khi nạp. Phán quyết gắn `orderId, payoutTo, amount, nonce, deadline`; đơn rời `DISPUTED` ngay khi thành công nên không phát lại được; chữ ký của đơn này vô dụng ở đơn khác (T-13).
- Hai chữ ký phải của **hai bên khác nhau** (`_partyOf`): một bên ký hai lần, hay hai địa chỉ Trọng tài, đều chỉ tính một bên (T-12).
- Test cũ: T-12 `malleableSignature_rejected`, `malformedSignatures_revert`. **Test mới (Tuần 8):** `SM1` một bên không tự nhân đôi chữ ký bằng bản EIP-2098 compact 64 byte hoặc bản sinh đôi `s` cao; `SM2` chữ ký báo giá `s` cao bị từ chối, bản chuẩn vẫn dùng được.
- Giới hạn đã biết: chỉ hỗ trợ chữ ký EOA (không có ERC-1271), nên Buyer dùng ví hợp đồng thông minh không ký được phán quyết. Chấp nhận cho MVP.

### 2.3 Role Separation — ĐẠT, kèm 2 ghi chú

- 4 vai tách bạch: `DEFAULT_ADMIN_ROLE` (quản trị), `SHIPPER_ROLE` (chỉ `confirmDelivery`), `ARBITRATOR_ROLE` (chỉ `arbitratorForceResolve` và là một "bên" ký phán quyết), `QUOTE_SIGNER_ROLE` (chỉ ký báo giá). Không vai nào có đường rút tiền ký quỹ: Admin chỉ `cancelIfUnfulfilled` (tiền về **Buyer**), đổi trần phí (≤ 10%) và địa chỉ nhận phí.
- Trọng tài không được làm Buyer/Merchant của đơn (`Arbitrator cannot trade`, T-04, T-30).
- Test cũ: T-05, T-09, T-14, T-15 (kiểm quyền từng hàm theo từng vai). **Test mới:** `RS1` chỉ Admin cấp/thu hồi vai; `RS2` Admin không giải ngân, không khiếu nại, không xử đơn phương, tiền nguyên vẹn; `RS3` signer/Trọng tài không xác nhận giao hàng, Shipper không giải ngân/khiếu nại/xử đơn, signer không xử đơn.

### 2.4 Front-running — ĐẠT

| Tình huống | Vì sao an toàn | Test |
| :--- | :--- | :--- |
| Chép báo giá + chữ ký từ mempool để đốt `orderId` | Báo giá gắn `buyer == msg.sender`; Buyer thật vẫn nạp được | T-02 wrongCaller, **FR1 mới** |
| Chạy trước `resolveDispute` rồi đổi người nhận | `payoutTo` nằm trong digest; đổi là chữ ký sai | T-12, **FR2 mới** |
| Chạy trước `resolveDispute` nguyên văn | Tiền vẫn về đúng người đã ký; người nộp không nhận gì | **FR2 mới** |
| Đua `raiseDispute` với `releaseAfterInspection` | Hai điều kiện loại trừ nhau tại đúng mốc `deliveredAt + inspectionDuration` | T-10 |
| Đua chữ ký với thoát hiểm tại `disputeTimeout` | `deadline < disputedAt + disputeTimeout` nên không bao giờ cùng hợp lệ (R-02) | T-15, T-24 |
| Admin đổi trần phí giữa lúc ký và nạp | Báo giá cũ bị từ chối, lấy báo giá mới (AC-13); chỉ ảnh hưởng thanh khoản, không mất tiền; đơn đã nạp giữ phí đã chốt | T-22, T-28, INV-06 |

### 2.5 Ghi nhận (không có lỗi High/Critical)

Không đổi contract vì Feature Freeze và ABI đã đóng băng; các mục dưới ghi lại để bảo vệ đồ án.

| # | Mức | Nội dung | Xử lý |
| :-: | :-: | :--- | :--- |
| 1 | Info | Admin có thể tự cấp `ARBITRATOR_ROLE` cho mình rồi xử đơn phương sau `disputeTimeout` | Đúng mô hình tin cậy có kiểm soát (BRD mục 6): chỉ sau timeout, chỉ trả về Buyer hoặc Merchant, phí bị chặn trần 10%. Môi trường thật nên dùng ví đa chữ ký cho Admin |
| 2 | Info | `confirmDelivery` không cấm Shipper trùng Merchant/Buyer của đơn (chỉ Trọng tài bị cấm giao dịch) | Khóa Shipper do sàn giữ (relayer); Buyer vẫn khiếu nại được trong hạn kiểm tra. Đưa vào backlog sau M1 |
| 3 | Info | Constructor không chặn địa chỉ 0 cho shipper/arbitrator/signer, và không bắt 4 vai khác nhau | Vô hại (`ECDSA.recover` không trả địa chỉ 0). `Deploy.s.sol` dùng 4 địa chỉ khác nhau |
| 4 | Info | Token ERC-20 có blacklist làm `safeTransfer` revert, kẹt đơn (nhánh chờ rút chỉ áp dụng cho ETH) | Token do backend ký báo giá nên chỉ whitelist `MockUSD` (không blacklist) |
| 5 | Info | `disputeNonces` luôn bằng 0 ở trạng thái đã commit, vì phán quyết thành công thì đơn rời `DISPUTED` | Thừa nhưng vô hại; giữ vì ABI/storage đóng băng (INV-04) |

## 3. Trạng thái và việc còn lại

| Hạng mục | Trạng thái |
| :--- | :--- |
| E-05 (quét mã nguồn + lược đồ + log) | Đạt, 57 test Python xanh ở máy soạn tài liệu |
| E-05 (quét CSDL MySQL thật) | Chờ CI (cần MySQL) |
| 7 test Foundry mới (`SlopeeEscrowSecurityW8.t.sol`) | **Chưa biên dịch/chạy được ở đây** (Foundry không tải được): cần `forge test` trong CI trước khi đánh `[x]` |
| `slither . --exclude-informational --fail-medium` | Chạy trong CI như cũ; không đổi contract nên không kỳ vọng phát hiện mới |
| Chạy thử bằng MetaMask thật | Ngoài phạm vi, vẫn là việc chạy tay |

## 4. Chạy lại

```bash
python scripts/scan_no_user_keys.py --self-check     # bộ nhận diện còn bắt được mẫu dương
python scripts/scan_no_user_keys.py -v               # mã nguồn + lược đồ + log (mã thoát 1 nếu có HIGH)
python scripts/scan_no_user_keys.py --db             # + CSDL (DB_HOST/DB_USER/DB_PASSWORD/DB_NAME)
python scripts/scan_no_user_keys.py --report docs/e05_report.md
python -m pytest test/unit_test/test_w8_non_custodial.py test/integration_test/test_w8_non_custodial_mysql.py -v
cd contracts && forge test --match-contract SlopeeEscrowSecurityW8Test -vv
```
