"""Trọng tài xử đơn phương khi tranh chấp quá hạn (UC-07 Dispute Timeout, BR-05, SDD 4.3, `POST /api/admin/disputes/:code/force-resolve`). Tuần 7, B.

Vì sao có: đơn `DISPUTED` mà Buyer/Merchant không ký (hoặc không đồng thuận) thì sau `disputedAt + disputeTimeout` (7-90 ngày theo nhóm hàng) Trọng tài
là lối thoát DUY NHẤT; không có nó tiền kẹt vĩnh viễn trong contract (M3: "không có trường hợp tiền bị kẹt"). Đây cũng là hành động duy nhất
dựa hoàn toàn vào niềm tin ở sàn (BRD mục 6), nên được truy vết: Admin nào, chọn bên nào, lý do gì, giao dịch nào (`dispute_force_resolutions`).

Quy tắc (cùng triết lý với DisputeService/DisputeSubmitService):
- CHỈ Admin (route). Danh tính lấy từ token; Admin không phải bên của đơn nhưng được yêu cầu sàn dùng khóa Trọng tài (ARBITRATOR_KEY nằm ở máy chủ).
- Tin CHUỖI, không tin MySQL: trạng thái, người nhận hợp lệ, `disputedAt`, `disputeTimeout` đọc thẳng từ contract (Indexer có thể trễ).
- Mọi kiểm tra chạy TRƯỚC khi gửi (mốc thời gian, người nhận, trạng thái); contract vẫn là chốt cuối. Chưa tới mốc thì FORCE_RESOLVE_TOO_EARLY kèm
  thời gian còn lại, KHÔNG gửi giao dịch sẽ revert.
- Hai đường xử lý không bao giờ cùng hợp lệ (R-02): chữ ký 2/3 luôn có deadline <= disputedAt + disputeTimeout - 1, nên khi đường này mở thì đường kia
  đã đóng; vì vậy không cần hủy/đợi đề xuất đang hoạt động. Indexer (`ArbitratorForceResolved`) tự đặt đề xuất đó CANCELLED.
- Idempotent: chuỗi đã REFUNDED/COMPLETED đúng bên yêu cầu thì ALREADY_RESOLVED (không gửi, không ghi nhật ký thêm); trái bên thì INVALID_STATE.
- Không sửa order_web3/orders: trạng thái cuối do Indexer ghi khi thấy `ArbitratorForceResolved` + `OrderRefunded/OrderCompleted` (BR-09).
"""
import logging

from ..domain.dispute import check_force_resolvable, clean_note, force_resolve_at, parse_payout
from ..domain.errors import DomainError

log = logging.getLogger('slopee.web3')


class DisputeForceResolveService:
    def __init__(self, uow_factory, chain, clock, relayer):
        self._uow, self._chain, self._clock, self._relayer = uow_factory, chain, clock, relayer

    def force_resolve(self, admin_id, order_code, payout_to, reason_note=None):
        reason_note = clean_note(reason_note)
        with self._uow() as uow:
            order = uow.disputes.order_for_dispute(order_code)
        if order is None:
            raise DomainError('ORDER_NOT_FOUND', 'Không tìm thấy đơn hàng.')
        onchain_id = int(order['onchain_order_id'])
        on = self._chain.get_order(onchain_id)                    # nguồn sự thật cho mọi điều kiện
        if on['state'] == 'NONE':
            raise DomainError('INVALID_STATE', 'Đơn chưa có trên blockchain.', {'chain_state': 'NONE'})
        side, address = parse_payout(payout_to, on['buyer'], on['merchant'])
        at = None
        if on['state'] == 'DISPUTED':
            at = force_resolve_at(on['disputed_at'], on['dispute_timeout'])
            try:
                check_force_resolvable(self._clock.now_chain(), on['disputed_at'], on['dispute_timeout'])
            except DomainError as e:
                log.warning('UC-07 từ chối xử đơn phương (chưa tới hạn): admin=%s order=%s còn %ss', admin_id, order['order_id'],
                            e.extra.get('seconds_remaining'))
                raise
        # Mọi trạng thái khác (đã xử lý, chưa tranh chấp...) do relayer phân xử: ALREADY_RESOLVED / INVALID_STATE, cả trong hàng đợi.
        log.warning('UC-07 XỬ ĐƠN PHƯƠNG: admin=%s order=%s onchain=%s bên_nhận=%s', admin_id, order['order_id'], onchain_id, side)
        out = self._relayer.force_resolve(order['order_id'], onchain_id, address, side)
        if out['outcome'] == 'SENT':
            self._record(admin_id, order, onchain_id, side, address, on['amount'], reason_note, out)
        return {'order_id': order['order_id'], 'onchain_order_id': str(onchain_id), 'outcome': out['outcome'], 'tx_hash': out['tx_hash'],
                'payout_side': side, 'payout_to': address, 'amount_raw': str(int(on['amount'])), 'force_resolve_at': at}

    def _record(self, admin_id, order, onchain_id, side, address, amount, reason_note, out):
        """Giao dịch đã gửi (không thể thu hồi) nên lỗi ghi nhật ký KHÔNG được che kết quả: ghi log đủ dữ liệu để dựng lại bằng tay."""
        try:
            with self._uow() as uow:
                uow.disputes.add_force_resolution(order['order_id'], onchain_id, admin_id, side, address, str(int(amount)), reason_note,
                                                  out.get('outbox_id'), out['tx_hash'])
                uow.commit()
        except Exception:      # noqa: BLE001
            log.error('Không ghi được dispute_force_resolutions: admin=%s order=%s tx=%s side=%s', admin_id, order['order_id'],
                      out['tx_hash'], side, exc_info=True)
