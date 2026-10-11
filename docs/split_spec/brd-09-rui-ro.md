<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, mục 9. Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 9. RỦI RO DỰ ÁN & PHƯƠNG ÁN GIẢM THIỂU

| Rủi ro | Khả năng | Tác động | Giảm thiểu |
|---|---|---|---|
| Contract có lỗi logic bị phát hiện muộn | Trung bình | Cao | Viết test song song từ tuần 1; có checklist bảo mật (reentrancy, replay, quyền); chốt contract cuối tuần 2, chỉ sửa lỗi sau đó. |
| Tích hợp MetaMask / EIP-712 (đặc biệt `signTypedData_v4`) tốn thời gian hơn dự kiến | Cao | Trung bình | Làm "lát cắt end-to-end thô" vào cuối tuần 4; dùng chung thư viện băm kiểu EIP-712 giữa test và frontend. |
| Indexer lệch trạng thái khi khởi động lại | Trung bình | Cao | Lưu con trỏ block đã xử lý; xử lý idempotent; có chế độ replay toàn bộ. |
| Phạm vi phình to (fiat, COD, ETH UI...) | Cao | Trung bình | Khóa phạm vi theo mục 2; tuần 9-10 chỉ kiểm thử, sửa lỗi, demo. |
| Nhóm chỉ có 3 người, mỗi người kiêm nhiều vai trò; một người nghỉ hoặc chậm làm tắc nghẽn cả tiến độ | Cao | Cao | Mỗi hạng mục có người chính và người dự phòng chéo; mọi thay đổi có người khác xem lại; họp ngắn 2 lần mỗi tuần; sau M1, thành viên làm contract chuyển sang hỗ trợ backend và giao diện; nếu trễ M2 quá 3 ngày thì cắt các tính năng phụ (giao diện rút khoản chờ rút, màn hình Merchant nâng cao) trước khi cắt luồng chính. |
| Demo lỗi do môi trường (Anvil, ví, mạng) | Trung bình | Cao | Script khởi tạo môi trường một lệnh; video quay sẵn luồng demo làm phương án dự phòng. |
