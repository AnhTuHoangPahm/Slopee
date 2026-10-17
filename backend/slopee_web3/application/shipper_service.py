"""Cổng Shipper (MOD-05, UC-03, BR-03): liệt kê đơn được gán và xác nhận giao hàng qua RelayerService (A).

Quyền: chỉ tài khoản role `shipper` (route kiểm), và CHỈ đơn gán cho đúng Shipper đó trong `shipper_assignments`.
Đơn không được gán/không tồn tại đều trả ORDER_NOT_FOUND (không lộ sự tồn tại của đơn người khác).
Trạng thái đơn do Indexer ghi: sau `deliver` trạng thái trong MySQL vẫn là LOCKED cho tới khi Indexer thấy `OrderDelivered`.
"""
from ..domain.errors import DomainError
from ..domain.release import delivery_timeout_at

LISTED_STATES = ('LOCKED',)
ASSIGNABLE_STATES = ('PENDING_PAYMENT', 'LOCKED')


class ShipperService:
    def __init__(self, uow_factory, relayer):
        self._uow = uow_factory
        self._relayer = relayer

    def list_orders(self, shipper_user_id):
        """Đơn LOCKED được gán cho Shipper. Không trả ví của Buyer/Merchant; số token dạng chuỗi (uint256)."""
        with self._uow() as uow:
            rows = uow.shipper.assigned_orders(shipper_user_id, LISTED_STATES)
        orders = []
        for r in rows:
            created = None if r['chain_created_at'] is None else int(r['chain_created_at'])
            delivered = None if r['delivered_at'] is None else int(r['delivered_at'])
            orders.append({
                'order_id': r['order_id'], 'onchain_order_id': str(int(r['onchain_order_id'])), 'status': r['status'],
                'shop_name': r['shop_name'], 'buyer_name': r['buyer_name'], 'items': r['items'],
                'price_vnd': int(r['price_vnd']), 'amount_raw': str(r['amount_raw']), 'symbol': r['token_symbol'],
                'inspection_duration': int(r['inspection_duration']),
                'assigned_at': int(r['assigned_at']),
                # Tên trường theo hợp đồng giao diện Shipper (A): chain_created_at (lúc ký quỹ), delivered_at (null khi còn LOCKED)
                'chain_created_at': created, 'delivered_at': delivered,
                'delivery_deadline': None if created is None else delivery_timeout_at(created),
            })
        return {'orders': orders}

    def deliver(self, shipper_user_id, order_code):
        with self._uow() as uow:
            row = uow.shipper.assigned_order(order_code, shipper_user_id)
        if row is None:
            raise DomainError('ORDER_NOT_FOUND', 'Không tìm thấy đơn hàng được gán cho bạn.')
        status = row['status']
        if status == 'DELIVERED':       # bấm lại sau khi Indexer đã ghi nhận: thành công, không gửi lại giao dịch
            return {'order_id': row['order_id'], 'status': status, 'outcome': 'ALREADY_DELIVERED', 'tx_hash': None}
        if status != 'LOCKED':
            raise DomainError('INVALID_STATE', 'Chỉ xác nhận giao hàng cho đơn đã ký quỹ và chưa giao.',
                              {'status': status})
        res = self._relayer.confirm_delivery(row['order_id'], row['onchain_order_id'])
        # Hợp đồng với Frontend (A): {outcome: 'SENT'|'ALREADY_DELIVERED', tx_hash}. `status` là trạng thái MySQL hiện tại (vẫn
        # LOCKED cho tới khi Indexer thấy OrderDelivered); giao diện polling để thấy đơn sang DELIVERED.
        return {'order_id': row['order_id'], 'status': status, 'outcome': res['outcome'], 'tx_hash': res['tx_hash']}

    def assign(self, admin_user_id, order_code, shipper_user_id):
        """Admin gán (hoặc đổi) Shipper cho đơn Web3 chưa giao. Tài khoản được gán phải thật sự là `shipper`."""
        with self._uow() as uow:
            user = uow.shipper.get_user(shipper_user_id)
            if user is None or user['role'] != 'shipper':
                raise DomainError('INVALID_SHIPPER', 'Tài khoản được gán không phải Shipper.')
            order = uow.shipper.order_for_assignment(order_code, lock=True)
            if order is None:
                raise DomainError('ORDER_NOT_FOUND', 'Không tìm thấy đơn hàng.')
            if order['status'] not in ASSIGNABLE_STATES:
                raise DomainError('INVALID_STATE', 'Chỉ gán Shipper cho đơn chưa giao.', {'status': order['status']})
            uow.shipper.assign(order['order_id'], shipper_user_id, admin_user_id)
            uow.commit()
        return {'order_id': order['order_id'], 'shipper_user_id': shipper_user_id, 'shipper_name': user['name']}
