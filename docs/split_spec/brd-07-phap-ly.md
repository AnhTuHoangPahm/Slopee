<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, mục 7. Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 7. KHUNG PHÁP LÝ VÀ GIỚI HẠN ÁP DỤNG

Dự án là mô hình học thuật chạy trên mạng thử nghiệm cục bộ. Theo hiểu biết hiện tại, tài sản mã hóa chưa được thừa nhận là phương tiện thanh toán hợp pháp tại Việt Nam, và việc triển khai thương mại cần rà soát lại quy định về thanh toán, thương mại điện tử và giao dịch điện tử \[REF-04\] tại thời điểm triển khai. Báo cáo cuối kỳ cần nêu rõ giới hạn này.

- Chữ ký trong MVP là chữ ký số bằng khóa mật mã (ECDSA) của ví, **không phải** chữ ký số công cộng do CA được cấp phép cấp. Giá trị pháp lý tương đương chữ ký số chuyên dùng cần đánh giá riêng và nằm ngoài phạm vi (Phase 2).
- Dữ liệu cá nhân chỉ lưu tối thiểu (mã tài khoản, địa chỉ ví); không đưa dữ liệu cá nhân lên blockchain, chỉ lưu giá trị băm (`docHash`).
