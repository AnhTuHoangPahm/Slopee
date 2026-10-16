<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 15.2. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 15.2. Lỗi bảo mật phát hiện

| Mã | Mức | Vị trí | Vấn đề |
|---|---|---|---|
| S-01 | Nghiêm trọng | Toàn bộ routes | Không endpoint nào xác thực; `userId` lấy từ thân yêu cầu hoặc đường dẫn nên ai cũng đọc được phương thức thanh toán (số tài khoản, số dư), đơn hàng, giỏ hàng của người khác. |
| S-02 | Nghiêm trọng | `auth.py` đăng ký | `role` lấy thẳng từ client và ENUM cho phép `admin`, nên ai cũng tạo được tài khoản admin. |
| S-03 | Nghiêm trọng | `admin.py` | Không kiểm quyền: liệt kê người dùng (email, điện thoại), xóa người dùng, sửa danh mục. |
| S-04 | Nghiêm trọng | `payments.py` thêm phương thức | Mỗi lần gọi cấp 10.000 số dư giả lập cho `userId` tùy ý, nên tạo tiền vô hạn. |
| S-05 | Cao | `payments.py` cập nhật đơn | Không kiểm chủ đơn và trạng thái hiện tại; hủy đơn không hoàn tiền hay tồn kho. Đây là đường ghi `orders.status` mà Web3 phải chặn. |
| S-06 | Cao | `shops.py` | Sửa giá, tồn kho, xóa sản phẩm, thêm ảnh và biến thể không kiểm chủ shop; thêm sản phẩm vào shop bất kỳ. |
| S-07 | Cao | `shops.py` `/migrate` | Route GET không xác thực chạy `ALTER TABLE`, hardcode tên schema. |
| S-08 | Cao | `payments.py` thanh toán | Kiểm kho rồi trừ kho không khóa và không điều kiện (race, bán lố); tiền tính bằng `float`; trừ số dư không điều kiện; không có `SELECT ... FOR UPDATE`. Tài khoản không có PIN (như admin) gây lỗi 500: `check_password_hash(None, ...)` ném `AttributeError` (đã chạy thử) và API trả thông báo lỗi nội bộ cho client. |
| S-09 | Trung bình | Đăng nhập, PIN 6 số | Không giới hạn số lần thử, nên dò mật khẩu và PIN được. |
| S-10 | Trung bình | `app.py`, `config.py`, `init_db.py` | `debug=True`, `SECRET_KEY` mặc định, admin/admin ghi sẵn trong mã và README, trả `str(e)` cho client. |
| S-11 | Trung bình | `auth.py` | Đổi tên đăng nhập và tiểu sử không cần xác thực hay mật khẩu. |
| S-12 | Thấp | Frontend | Phân quyền chỉ ở phía client (route `/admin`, vai trò đọc từ `localStorage`). |
| S-13 | Thấp | `schema.sql` | `reviews` và `reviewImages` khai báo hai lần khác nhau, bản đầu thắng do `IF NOT EXISTS`; bản đầu của `reviewImages` có `id VARCHAR(36)` không tự sinh trong khi `reviews.py` chèn không cung cấp `id`, nên thêm ảnh đánh giá gặp lỗi 1364 ở chế độ strict mặc định của MySQL; bản đầu của `reviews` cũng thiếu `UNIQUE(userId, productId)` của bản sau. |
| S-14 | Thấp | Nhiều route | `request.json` có thể là `None`; URL ảnh không được kiểm tra; `int()` trên đầu vào không bắt lỗi. |

Liên quan trực tiếp tới Web3: nếu không sửa S-01 thì bước liên kết ví (BR-07) vô nghĩa, vì kẻ tấn công có thể liên kết ví của mình với tài khoản người bán rồi nhận tiền; S-05 cho phép đổi trạng thái chiếu của đơn Web3; S-02 và S-03 cho phép chiếm quyền Admin, tức quyền tạo đề xuất phán quyết.
