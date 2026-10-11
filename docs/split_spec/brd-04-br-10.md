<!-- Nguồn: BRD-SLOPEE-MVP-01 v5.3, BR-10 (mục 4). Sinh bởi scripts/split_spec.py từ brd-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# BR-10: Chính sách thời hạn theo nhóm hàng (Category Policy)

Hai thời hạn của đơn là **cửa sổ kiểm tra** (`inspectionDuration`) và **thời hạn tranh chấp** (`disputeTimeout`) không cố định cho mọi đơn mà do sàn cấu hình theo nhóm hàng, vì mỗi nhóm cần thời gian kiểm tra và giám định khác nhau. Hàng dễ hỏng cần xử lý nhanh, hàng điện tử hoặc đặt theo yêu cầu cần nhiều thời gian hơn.

| Nhóm hàng | Cửa sổ kiểm tra | Thời hạn tranh chấp | Lý do |
|---|---|---|---|
| Thực phẩm, hàng dễ hỏng | 2 giờ | 7 ngày | Hư hỏng nhanh, bằng chứng mất giá trị theo thời gian; cần chốt sớm. |
| Hàng tiêu dùng thông thường (mặc định) | 3 ngày | 30 ngày | Mức cân bằng cho phần lớn đơn hàng. |
| Điện tử, đồ gia dụng giá trị cao | 7 ngày | 45 ngày | Cần thời gian dùng thử, kiểm tra lỗi kỹ thuật và giám định. |
| Hàng cồng kềnh, đặt theo yêu cầu | 14 ngày | 60 ngày | Cần lắp đặt, đo đạc; khó kiểm tra ngay khi nhận. |

*Các giá trị trên là mức đề xuất minh họa; nhóm dự án chốt bảng cuối cùng trước tuần 3.*

- **Giới hạn do contract ép:** `inspectionDuration` từ 1 giờ đến 30 ngày; `disputeTimeout` từ **7 đến 90 ngày**. Cận dưới 7 ngày đảm bảo hai bên có đủ thời gian ký phán quyết (chữ ký mặc định có hiệu lực 7 ngày) trước khi Trọng tài được quyền xử đơn phương.
- **Chốt khi tạo đơn:** hai thời hạn nằm trong báo giá do sàn ký (BR-06) và được lưu vào đơn on-chain. Admin đổi chính sách sau đó chỉ ảnh hưởng đơn mới, không ảnh hưởng đơn đã tạo.
- **Cấu hình theo nhóm hàng, không theo từng sản phẩm.** Merchant không được tự chọn hay rút ngắn các thời hạn này.
- **Đơn gồm nhiều nhóm hàng:** mỗi thời hạn lấy giá trị lớn nhất trong các nhóm có mặt trong đơn. Không xác định được nhóm thì dùng nhóm mặc định.
- Trọng tài chỉ có quyền xử đơn phương sau khi hết `disputeTimeout` của chính đơn đó.
