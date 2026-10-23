"""Danh sách tranh chấp cho Admin (UC-06, màn hình quản lý tranh chấp). Chỉ đọc MySQL (Indexer đã ghi DISPUTED).

Mới ngoài danh sách SDD 10.2 (`GET /api/admin/disputes`), chờ nhóm xác nhận: SRS chỉ có `GET /api/disputes/:code` cho từng đơn, mà Admin
cần thấy TẤT CẢ đơn đang tranh chấp mới chọn được đơn để thẩm định.
"""
from ..domain.dispute import payout_side


class DisputeAdminService:
    def __init__(self, uow_factory, clock):
        self._uow = uow_factory
        self._clock = clock

    def list_open(self):
        with self._uow() as uow:
            rows = uow.disputes.open_disputes()
        now = self._clock.now_chain()
        out = []
        for r in rows:
            disputed_at, timeout = int(r['disputed_at']), int(r['dispute_timeout'])
            res = r['resolution']
            out.append({
                'order_id': r['order_id'], 'onchain_order_id': str(int(r['onchain_order_id'])),
                'shop_name': r['shop_name'], 'buyer_name': r['buyer_name'],
                'amount_raw': str(r['amount_raw']), 'symbol': r['token_symbol'], 'price_vnd': int(r['price_vnd']),
                'disputed_at': disputed_at, 'dispute_timeout': timeout,
                # Sau mốc này Trọng tài có quyền xử đơn phương (UC-07, Tuần 7); chữ ký của đề xuất luôn hết hạn trước mốc này.
                'force_resolve_at': disputed_at + timeout,
                'note': None if r['note'] is None else {'reason': r['note']['reason'], 'evidence_url': r['note']['evidence_url']},
                'resolution': None if res is None else {
                    'id': res['id'], 'status': res['status'], 'payout_to': res['payout_to'],
                    'payout_side': payout_side(res['payout_to'], r['buyer_wallet'], r['merchant_wallet']),
                    'amount_raw': str(res['amount_raw']), 'nonce': str(res['nonce']), 'deadline': res['deadline'],
                    'signed_by': sorted(res.get('signed_by', [])), 'reason_note': res['reason_note'],
                    'submitted_tx_hash': res['submitted_tx_hash'],
                    'expired': res['status'] in ('PROPOSED', 'READY') and now > res['deadline'],
                },
            })
        return {'disputes': out, 'server_time': now}
