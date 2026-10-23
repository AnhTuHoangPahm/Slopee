"""Trạng thái đơn cho polling (DD-04, SDD 9.4/10.2): đọc từ MySQL, không đọc contract; kèm `server_time` theo now_chain()."""
from ..domain.errors import DomainError


class OrderStatusService:
    def __init__(self, uow_factory, clock):
        self._uow = uow_factory
        self._clock = clock

    def get_status(self, user_id, role, order_code):
        """Chỉ Buyer, Merchant của đơn hoặc Admin được xem. Người khác/đơn không tồn tại đều trả ORDER_NOT_FOUND (không lộ sự tồn tại)."""
        with self._uow() as uow:
            row = uow.checkout.order_status_row(order_code)
        if row is None or not (role == 'admin' or user_id in (row['buyer_user_id'], row['merchant_user_id'])):
            raise DomainError('ORDER_NOT_FOUND', 'Không tìm thấy đơn hàng.')

        def opt(v):
            return None if v is None else int(v)
        return {
            'order_id': row['order_id'], 'status': row['status'],
            'chain_created_at': opt(row.get('chain_created_at')),   # mốc ký quỹ theo block; Frontend tính hạn hủy đơn quá 14 ngày theo server_time
            'delivered_at': opt(row['delivered_at']), 'inspection_duration': int(row['inspection_duration']),
            'disputed_at': opt(row['disputed_at']), 'dispute_timeout': int(row['dispute_timeout']),
            'anomaly': bool(row['anomaly_flag']), 'server_time': self._clock.now_chain(),
        }
