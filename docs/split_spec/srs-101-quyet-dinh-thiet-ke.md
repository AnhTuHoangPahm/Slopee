<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 10.1. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 10.1. Quyết định thiết kế và giới hạn đã biết

- **Chống chiếm mã đơn và đổi Merchant:** contract chỉ nhận tiền khi có báo giá do `QUOTE_SIGNER_ROLE` ký, gắn với đúng ví người nạp (`q.buyer == msg.sender`). Một báo giá chỉ dùng được một lần vì mã đơn chuyển khỏi `NONE` sau lần nạp đầu.
- **Chữ ký theo "bên":** kể cả khi có nhiều địa chỉ mang vai Trọng tài, chỉ tính một phiếu. Trọng tài bị cấm làm Buyer hoặc Merchant ở cùng đơn. Nếu địa chỉ Buyer hoặc Merchant được cấp vai Trọng tài sau khi đơn đã tạo, `_partyOf` ưu tiên vai Buyer/Merchant.
- **Nonce:** `disputeNonces` tăng mỗi lần `resolveDispute` chạy thành công; giao dịch revert thì nonce không đổi. Chữ ký còn bị giới hạn bởi `deadline`. Chưa có hàm hủy chữ ký chủ động (Phase 2).
- **ETH gửi đến ví từ chối nhận:** chuyển tiền với giới hạn gas 30.000, thất bại thì ghi sổ chờ rút. Với ERC-20, MVP chỉ hỗ trợ token chuẩn (MockUSD); token có danh sách đen hoặc phí-khi-chuyển nằm ngoài phạm vi.
- **Khóa vận hành tập trung:** xem mô hình tin cậy ở BRD mục 6. Không có chức năng tạm dừng khẩn cấp hay nâng cấp contract trong MVP.
- **Thời hạn tranh chấp theo nhóm hàng:** `disputeTimeout` do sàn đặt trong báo giá (đã được ký) nên Merchant và Buyer không tự đổi được; contract chỉ kiểm tra khoảng 7-90 ngày chứ không biết nhóm hàng. Tính đúng của giá trị theo nhóm là trách nhiệm của backend, do đó indexer đối chiếu lại với bảng `category_policies` (UC-08).
- **Trần phí on-chain:** phí của từng đơn do backend đặt trong báo giá đã ký, nhưng contract từ chối báo giá có `feeBps` lớn hơn `defaultFeeBps` do Admin đặt. Nhờ đó khóa ký báo giá bị lộ cũng không thể phát hành báo giá có phí vượt mức Admin cho phép. Admin hạ trần thì báo giá cũ phí cao bị từ chối và phải cấp lại (UC-09).
- **Hạn chữ ký phán quyết:** `resolveDispute` chỉ nhận chữ ký có `deadline < disputedAt + disputeTimeout`, còn `arbitratorForceResolve` hợp lệ từ `disputedAt + disputeTimeout`; hai đường xử lý không bao giờ cùng hợp lệ tại một thời điểm.
- **Chữ ký Trọng tài có sẵn:** vì chữ ký Trọng tài được tạo cùng đề xuất, một chữ ký của Buyer hoặc Merchant là đủ để thi hành; đây là thiết kế của BR-04, giao diện phải cảnh báo người ký.
- **Nạp gom:** `depositEscrowBatch` và `depositEscrow` dùng chung `_acceptQuote`, nên không có đường nạp nào kiểm tra yếu hơn. Lô là nguyên tử, tối đa `MAX_BATCH_SIZE` = 5 đơn (giới hạn của bản demo, có thể nâng sau khi đo gas), một token duy nhất; vòng lặp ghi đơn LOCKED ngay nên mã đơn trùng trong cùng lô bị từ chối (nếu chỉ kiểm tra trước rồi ghi sau thì hai báo giá cùng mã đơn sẽ bị thu tiền hai lần nhưng chỉ ghi một đơn, làm sai bất biến số dư). Tiền được thu một lần ở cuối.
- **Độc lập sau khi nạp:** mỗi đơn trong lô có trạng thái, thời hạn, phí và Merchant riêng; mọi hàm sau nạp thao tác trên một `orderId`, không có hàm nào chạm đơn khác.
- **Hủy đơn bởi Merchant, hoàn một phần:** ngoài phạm vi MVP. Một đơn on-chain luôn gắn đúng một Merchant; giỏ nhiều shop dùng nạp gom (BR-11).
