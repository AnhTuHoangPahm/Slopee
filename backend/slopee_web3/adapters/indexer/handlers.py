"""Bộ xử lý sự kiện của Indexer (SDD 6.2).

TUẦN 3: chỉ có KHUNG. Registry rỗng, Indexer vẫn ghi `chain_events` và dời con trỏ nhưng chưa đổi trạng thái đơn.
TUẦN 4 điền: on_order_created (đối chiếu báo giá -> LOCKED, đồng bộ orders.status, xóa cartItems), on_order_delivered, ...

Chữ ký handler: handler(cursor, event, block_timestamp) trong cùng giao dịch CSDL với việc ghi chain_events/con trỏ.
Mỗi handler chỉ áp dụng chuyển trạng thái hợp lệ (domain.order_state.is_valid_transition); sai thì đặt anomaly_flag.
"""

HANDLERS = {}
