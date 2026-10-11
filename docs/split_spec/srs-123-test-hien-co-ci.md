<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 12.3. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 12.3. Chuyển đổi bộ kiểm thử sẵn có và CI

Repo Slopee hiện có: pytest với mock con trỏ CSDL (5 tệp), Vitest cho Home, Navbar và logic Tetris, Playwright chỉ trên Firefox (đăng ký và Tetris, dọn dữ liệu bằng kết nối MySQL trực tiếp), và CI GitHub Actions đã có dịch vụ MySQL.

| Test hiện có | Thay đổi bắt buộc | Nguyên nhân |
|---|---|---|
| `test_checkout.py` | Viết lại: gửi token thay `userId`, giá VND số nguyên, các ca race tồn kho và trừ số dư chạy trên MySQL thật vì mock không kiểm chứng được | P0-01, 05, 07 |
| `test_cart.py`, `test_products.py`, integration | Thêm token và ca 401, 403; bỏ `userId` khỏi thân | P0-01, 03 |
| `auth_test.py` | Đăng ký chỉ nhận `user` và `seller`; đăng nhập trả token; giới hạn số lần thử | P0-01, 02, 05 |
| `Home.test.jsx`, `Navbar.test.jsx` | Giá hiển thị theo VND; Navbar có nút ví; mock `fetch` qua client chung | P0-07, UC-00 |
| `auth-flow.spec.js` | Theo luồng token; dọn dữ liệu qua hàm tiện ích dùng chung | P0-01 |
| `tetris-flow.spec.js`, `tetrisLogic.test.js` | Giữ nguyên, chỉ thêm đăng nhập bằng token nếu route yêu cầu | \- |

**Nguyên tắc.** Mock con trỏ CSDL chỉ dùng cho logic thuần. Mọi đường đi liên quan tiền, tồn kho, trạng thái đơn và phân quyền chạy trên MySQL thật (dịch vụ MySQL của CI) kèm một fixture tạo người dùng và token. Các test A-01 đến A-07 và I-06 nằm trong nhóm này.

**Bộ test Web3 mới.** (1) Foundry: `forge test`, độ phủ và Slither cho contract. (2) Kiểm thử chéo ngôn ngữ: pytest, Vitest và Foundry cùng đọc `shared/eip712/vectors.json`. (3) E2E: MetaMask thật không tự động hóa được trong CI, nên Playwright tiêm một nhà cung cấp ví `window.ethereum` (EIP-1193) chạy bằng khóa thử của Anvil, chỉ nạp trong môi trường kiểm thử; bản demo thủ công vẫn dùng MetaMask.

| Công việc CI | Nội dung |
|---|---|
| backend | Có sẵn: pytest với dịch vụ MySQL; thêm các test A-xx trên MySQL thật |
| frontend | Thêm: `npm run lint`, `npm test` (Vitest, gồm F-01 đến F-06) |
| contracts | Mới: `forge test`, `forge coverage` (từ 90%), Slither |
| web3-integration | Mới: Anvil, triển khai, Indexer, backend, kiểm thử I-xx và chéo ngôn ngữ |
| e2e | Mới: Anvil, backend, frontend, Playwright với ví thử nghiệm (E-01 đến E-07) |
