<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, BR-03 (mục 4). Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# BR-03: Cửa sổ Kiểm tra Động & Mở khóa sớm (Dynamic Inspection & Early Release)

- Khi Shipper xác nhận giao hàng, contract bắt đầu đếm ngược thời gian kiểm tra (`inspectionDuration`) từ **1 giờ đến 30 ngày** tùy loại hàng hóa. Thời lượng do sàn ấn định theo nhóm hàng (BR-10) và được chốt trong báo giá.
- Nếu Buyer hài lòng và bấm "Xác nhận nhận hàng" → **Mở khóa sớm (T+0)**: giải ngân ngay cho Merchant mà không cần chờ hết hạn.
- Nếu hết thời hạn mà Buyer không khiếu nại → bất kỳ ai cũng có thể kích hoạt lệnh giải ngân tự động cho Merchant.
- Buyer chỉ được khiếu nại trong cửa sổ kiểm tra. Sau khi hết hạn, quyền khiếu nại chấm dứt.
