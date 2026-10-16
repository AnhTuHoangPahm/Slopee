<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 12.1. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 12.1. Ma trận kiểm thử Smart Contract (tối thiểu)

| Mã | Ca kiểm thử | Kết quả mong đợi | Quy tắc |
|---|---|---|---|
| T-01 | Nạp tiền với báo giá hợp lệ (ERC-20 và ETH) | Thành công, `LOCKED` | BR-06 |
| T-02 | Báo giá hết hạn; sai người nạp; sai chữ ký; ký bởi địa chỉ không có vai trò | Revert | BR-06 |
| T-03 | Dùng lại mã đơn đã tồn tại; giá trị ETH khác số tiền; token kèm ETH; thiếu allowance | Revert | BR-06 |
| T-04 | Merchant trùng Buyer; Trọng tài làm Buyer hoặc Merchant; thời gian kiểm tra ngoài \[1 giờ, 30 ngày\] | Revert | BR-03, 04 |
| T-05 | `confirmDelivery` bởi người không có vai trò; khi đơn không `LOCKED` | Revert | BR-03 |
| T-06 | Mở khóa sớm bởi Buyer; bởi người khác | Thành công / Revert | BR-03 |
| T-07 | Giải ngân sau hết hạn (đúng thời điểm biên và trước 1 giây) | Thành công / Revert | BR-03 |
| T-08 | Chia phí với `feeBps` = 0, 300, 1000; số tiền nhỏ (làm tròn); phí lấy từ báo giá và bằng `feeBps` trong `OrderCreated`; đổi `defaultFeeBps` sau khi nạp không ảnh hưởng đơn cũ | Đúng công thức | BR-02 |
| T-09 | `setDefaultFeeBps` vượt 1.000; bởi người không phải Admin | Revert | BR-02 |
| T-10 | Khiếu nại trong hạn; sau hạn; bởi người khác Buyer | Thành công / Revert | BR-03 |
| T-11 | `resolveDispute` với Arbitrator + Buyer (hoàn tiền) và Arbitrator + Merchant (giải ngân) | Thành công, đúng số tiền | BR-04 |
| T-12 | Hai chữ ký cùng một bên; hai địa chỉ cùng vai Trọng tài; chữ ký người ngoài; chữ ký hết hạn; sai nonce, sai số tiền, sai `payoutTo` | Revert | BR-04 |
| T-13 | Nộp lại chữ ký đã dùng sau khi đơn kết thúc | Revert | BR-04 |
| T-14 | `cancelIfUnfulfilled` trước và sau 14 ngày; bởi Buyer, Admin, người lạ | Revert / Thành công / Revert | BR-05 |
| T-15 | `arbitratorForceResolve` trước và sau `disputeTimeout` của đơn (thử 7, 30 và 90 ngày); bởi người không phải Trọng tài; `payoutTo` lạ. Ca biên: tại mốc trừ 1 giây thì `arbitratorForceResolve` revert và `resolveDispute` (deadline = mốc trừ 1) thành công; tại đúng mốc thì ngược lại | Revert / Thành công / Revert | BR-05 |
| T-16 | Merchant là contract từ chối nhận ETH: giải ngân vẫn hoàn tất, ghi sổ chờ rút; `claimPending` đúng người, rút lần hai | Thành công, không kẹt | BR-05 |
| T-17 | Tấn công reentrancy qua ví nhận ETH và token giả mạo | Bị chặn | An toàn |
| T-18 | Bất biến: số dư contract bằng tổng số tiền các đơn chưa kết thúc cộng sổ chờ rút (fuzz/invariant) | Luôn đúng | G-01 |
| T-19 | Mọi cặp (trạng thái, hàm) không hợp lệ trong bảng mục 5 | Revert | Máy trạng thái |
| T-20 | Báo giá có `disputeTimeout` dưới 7 ngày hoặc trên 90 ngày; giá trị biên đúng 7 và đúng 90 ngày | Revert / Thành công | BR-10 |
| T-21 | Hai đơn có `disputeTimeout` khác nhau chạy song song: đơn 7 ngày xử được ở ngày thứ 8, đơn 45 ngày cùng lúc vẫn revert; sửa `disputeTimeout`, `feeBps` hoặc `buyer` trong báo giá sau khi ký thì bị từ chối | Độc lập / "Bad quote signature" | BR-10, BR-06 |
| T-22 | Báo giá có `feeBps` lớn hơn `defaultFeeBps`; bằng đúng trần; Admin hạ trần sau khi ký thì báo giá cũ bị từ chối còn báo giá mới được chấp nhận | Revert / Thành công / Revert rồi thành công | BR-02, BR-06 |
| T-23 | `q.buyer` khác `msg.sender` | Revert | BR-06 |
| T-24 | `resolveDispute` với `deadline` bằng hoặc lớn hơn `disputedAt + disputeTimeout`; bằng mốc trừ 1 giây | Revert / Thành công | BR-04, BR-05 |
| T-25 | Nạp gom 3 đơn của 3 Merchant: đúng một lần `transferFrom`; số dư contract tăng đúng tổng; 3 sự kiện `OrderCreated`; cả 3 đơn `LOCKED` với số tiền, phí, thời hạn riêng | Thành công | BR-11 |
| T-26 | Lô rỗng; lô quá 5 đơn; số báo giá khác số chữ ký | Revert | BR-11 |
| T-27 | Hai báo giá cùng `orderId` trong một lô | Revert, số dư không đổi | BR-11, G-01 |
| T-28 | Một báo giá trong lô hết hạn, sai chữ ký, phí vượt trần hoặc `buyer` khác người gửi | Cả lô revert, không đơn nào được tạo | BR-11, BR-06 |
| T-29 | Lô gồm nhiều loại token; ETH sai tổng `msg.value`; token kèm ETH | Revert | BR-11 |
| T-30 | Mọi kiểm tra của `depositEscrow` áp dụng cho từng phần tử lô: Merchant trùng Buyer, Trọng tài làm Merchant, thời hạn kiểm tra hoặc tranh chấp ngoài khoảng, số tiền 0 | Revert | BR-06, BR-11 |
| T-31 | Độc lập: lô 3 đơn, đơn A mở khóa sớm, đơn B khiếu nại rồi hoàn tiền, đơn C hết hạn tự giải ngân | Mỗi đơn đúng số tiền và phí, không ảnh hưởng nhau | BR-11 |
| T-32 | Lô đúng 5 đơn thành công; ghi lại gas tiêu thụ (mục tiêu dưới 3 triệu gas) | Thành công | BR-11 |
| T-33 | Fuzz và invariant: handler gọi cả `depositEscrowBatch`; INV-01 đến INV-07 luôn đúng | Luôn đúng | G-01 |
| T-34 | `depositEscrow` đơn lẻ và `depositEscrowBatch` một phần tử cho cùng trạng thái và sự kiện | Giống hệt | BR-11 |
