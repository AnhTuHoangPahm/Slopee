<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, UC-03 (mục 4). Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# UC-03: Shipper xác nhận giao hàng (BR-03)

- **Ràng buộc:** chỉ ví có `SHIPPER_ROLE` gọi được `confirmDelivery`. Trong MVP, tài khoản có vai trò `shipper` (giá trị mới của `users.role`) trên cổng Slopee thao tác, Backend (relayer) ký bằng `SHIPPER_KEY` thay mặt.
- **Luồng chính:**
  1.  Shipper bấm "Xác nhận phát hàng thành công" (`POST /api/shipper/orders/:code/deliver`); Backend kiểm tra đơn `LOCKED` và đơn được gán cho Shipper đó trong `shipper_assignments`.
  2.  Relayer gọi `confirmDelivery(orderId)`; contract ghi `deliveredAt = block.timestamp`, chuyển `DELIVERED`, phát `OrderDelivered`.
  3.  Indexer cập nhật `delivered_at`, trạng thái; Backend gửi thông báo cho Buyer kèm hạn khiếu nại.
