"""Đối soát số dư contract với đơn đang mở (MOD-08, SDD 6.3, AC-10). Chỉ đọc; không sửa dữ liệu nào.

Để không báo lệch giả khi Indexer đang trễ, số dư contract được đọc TẠI ĐÚNG block mà Indexer đã xử lý xong (`last_block` của
con trỏ), và dữ liệu MySQL được đọc trong cùng MỘT snapshot với con trỏ (Indexer ghi con trỏ + dữ liệu nghiệp vụ trong cùng giao dịch).
Hai nguồn khi đó mô tả cùng một thời điểm và phải khớp tuyệt đối.
"""
from ..domain.reconcile import reconcile_token, token_key

DEEP_LIMIT = 200


class ReconcileService:
    def __init__(self, uow_factory, chain, known_tokens=(), confirmations=0):
        self._uow = uow_factory
        self._chain = chain
        self._known = tuple(token_key(t) for t in known_tokens)       # luôn kiểm các token đã cấu hình, kể cả khi chưa có đơn
        self._confirmations = int(confirmations)

    def run(self, deep=False):
        with self._uow() as uow:                       # MỘT giao dịch ⇒ một snapshot nhất quán với con trỏ
            cursor = uow.reconcile.indexer_cursor()
            opens = {t['token']: t for t in uow.reconcile.open_totals()}
            pendings = {t['token']: t for t in uow.reconcile.pending_totals()}
            anomalies = uow.reconcile.anomaly_orders()
            open_orders = uow.reconcile.open_orders(DEEP_LIMIT) if deep else []
        latest = self._chain.latest_block()
        at_block = cursor['last_block'] if cursor else None
        lag = max(0, latest['number'] - self._confirmations - cursor['last_block']) if cursor else None

        tokens = []
        for key in sorted(set(opens) | set(pendings) | set(self._known)):
            o, p = opens.get(key), pendings.get(key)
            balance = self._chain.balance_of(None if key == 'ETH' else key, at_block)
            tokens.append(reconcile_token(key, o['amount_raw'] if o else 0, o['orders'] if o else 0,
                                          p['amount_raw'] if p else 0, balance))

        result = {
            'indexer_cursor_missing': cursor is None,
            'checked_at_block': at_block, 'latest_block': latest['number'], 'indexer_lag_blocks': lag,
            'tokens': [t.as_dict() for t in tokens], 'anomalies': anomalies,
            'order_mismatches': None,
        }
        if deep:
            result['order_mismatches'] = self._deep_check(open_orders, lag)
        bad = [t for t in tokens if not t.ok]
        result['ok'] = not bad and not result['order_mismatches']
        result['status'] = 'OK' if result['ok'] else 'MISMATCH'
        return result

    def _deep_check(self, open_orders, lag):
        """Từng đơn đang mở: trạng thái MySQL phải bằng trạng thái contract. Chỉ so khi Indexer đã bắt kịp (lag = 0), vì
        `orders(id)` chỉ đọc được ở block mới nhất; so khi đang trễ sẽ báo lệch giả. Trả None nếu bỏ qua."""
        if lag != 0:
            return None
        mismatches = []
        for o in open_orders:
            chain_state = self._chain.get_order_state(o['onchain_order_id'])
            if chain_state != o['status']:
                mismatches.append({'order_id': o['order_id'], 'onchain_order_id': o['onchain_order_id'],
                                   'db_status': o['status'], 'chain_state': chain_state})
        return mismatches
