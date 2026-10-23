"""Tác vụ nền (MOD-10, SDD 5.5). Mỗi lớp có `run_once()` trả thống kê; vòng lặp/chu kỳ nằm ở adapter Scheduler.

Nguyên tắc chung: idempotent (UPDATE có điều kiện trạng thái, kiểm trạng thái trên chuỗi trước khi gửi), chạy lại vô hại,
và KHÔNG BAO GIỜ đoán khi chuỗi không trả lời: ChainUnavailable được ném lên để Scheduler ghi log và thử lại ở chu kỳ sau.
"""
import logging

from ..domain.errors import DomainError
from ..domain.release import QUOTE_EXPIRY_GRACE_SECONDS, quote_expired, release_due

log = logging.getLogger('slopee.jobs')


class QuoteExpirySweeper:
    """Đơn PENDING_PAYMENT có báo giá mới nhất quá hạn và chuỗi chưa có đơn ⇒ EXPIRED + hoàn tồn kho (SDD 5.3f, 5.5).

    Nạp gom là nguyên tử nên cả lô hết hạn cùng lúc: chuyển cả lô hoặc không chuyển đơn nào. Chỉ chuyển sau khi
    (1) khóa các đơn của lô, (2) kiểm lại hạn từng đơn, (3) đọc `orders(id) == NONE` trực tiếp trên chuỗi cho từng đơn.
    Có đệm QUOTE_EXPIRY_GRACE_SECONDS: contract từ chối nạp sau `deadline`, đệm che lệch nhỏ giữa đồng hồ máy chủ và block
    để không bao giờ EXPIRED một đơn mà người mua vẫn nạp được (nếu lọt thì Indexer chỉ gắn anomaly, tiền kẹt)."""

    def __init__(self, uow_factory, chain, clock, batch=50, grace=QUOTE_EXPIRY_GRACE_SECONDS):
        self._uow, self._chain, self._clock = uow_factory, chain, clock
        self._batch, self._grace = batch, grace

    def run_once(self):
        now = self._clock.now_chain()
        with self._uow() as uow:
            groups = uow.jobs.expired_quote_candidates(now, self._grace, self._batch)
        stats = {'groups_expired': 0, 'orders_expired': 0, 'skipped': 0}
        for group_id in groups:
            n = self._expire_group(group_id, now)
            if n:
                stats['groups_expired'] += 1
                stats['orders_expired'] += n
            else:
                stats['skipped'] += 1
        return stats

    def _expire_group(self, group_id, now):
        with self._uow() as uow:
            pending = [o for o in uow.jobs.lock_group_orders(group_id) if o['status'] == 'PENDING_PAYMENT']
            if not pending:
                return 0                       # Indexer/Buyer đã xử lý trong lúc chờ khóa
            if any(o['deadline'] is None or not quote_expired(o['deadline'], now, self._grace) for o in pending):
                return 0                       # Buyer vừa xin báo giá mới cho lô này
            for o in pending:
                if self._chain.get_order_state(o['onchain_order_id']) != 'NONE':
                    log.info('Lô %s: đơn on-chain %s đã có trên chuỗi, để Indexer xử lý', group_id, o['onchain_order_id'])
                    return 0
            n = sum(1 for o in pending if uow.jobs.expire_order(o['order_id']))
            uow.commit()
            return n


class AutoRelease:
    """Đơn DELIVERED hết hạn kiểm tra ⇒ gọi `releaseAfterInspection` qua relayer (SEQ-03, UC-04 kịch bản 2).

    Tác vụ này không bắt buộc về an toàn (ai cũng gọi được hàm), chỉ để Merchant nhận tiền đúng hạn. Mọi quyết định dựa trên
    dữ liệu ĐỌC TỪ CHUỖI (deliveredAt, inspectionDuration, thời gian block mới nhất), MySQL chỉ dùng để chọn ứng viên.
    Giao dịch revert do cạnh tranh (Buyer vừa mở khóa sớm) được bỏ qua, không phải lỗi."""

    def __init__(self, uow_factory, chain, clock, relayer, batch=20):
        self._uow, self._chain, self._clock, self._relayer = uow_factory, chain, clock, relayer
        self._batch = batch

    def run_once(self):
        now = self._clock.now_chain()
        with self._uow() as uow:
            due = uow.jobs.delivered_due(now, self._batch)
        stats = {'released': 0, 'skipped': 0, 'failed': 0}
        for o in due:
            on = self._chain.get_order(o['onchain_order_id'])
            if on['state'] != 'DELIVERED' or not release_due(on['delivered_at'], on['inspection_duration'],
                                                             self._chain.latest_block()['timestamp']):
                stats['skipped'] += 1          # Buyer đã mở khóa/khiếu nại, hoặc block chưa tới hạn
                continue
            try:
                res = self._relayer.release_after_inspection(o['order_id'], o['onchain_order_id'])
            except DomainError as e:
                if e.code in ('INVALID_STATE', 'CHAIN_TX_FAILED'):
                    log.info('AutoRelease đơn %s bỏ qua: %s', o['onchain_order_id'], e.code)
                    stats['failed' if e.code == 'CHAIN_TX_FAILED' else 'skipped'] += 1
                    continue
                raise
            stats['skipped' if res['outcome'] == 'ALREADY_COMPLETED' else 'released'] += 1
        return stats


class DeliveryTimeoutReminder:
    """Nhắc Buyer có đơn LOCKED quá 14 ngày chưa giao: được hủy và nhận hoàn tiền 100% (UC-07). Gửi đúng MỘT lần mỗi đơn
    nhờ UNIQUE(user, order, kind); chỉ nhắc khi trên chuỗi đơn vẫn LOCKED (Buyer có thể đã hủy mà Indexer chưa kịp ghi)."""

    KIND = 'DELIVERY_TIMEOUT'

    def __init__(self, uow_factory, chain, clock, batch=50):
        self._uow, self._chain, self._clock = uow_factory, chain, clock
        self._batch = batch

    def run_once(self):
        now = self._clock.now_chain()
        with self._uow() as uow:
            rows = uow.jobs.locked_past_delivery_timeout(now, self._batch)
        stats = {'reminded': 0, 'skipped': 0}
        for r in rows:
            if self._chain.get_order_state(r['onchain_order_id']) != 'LOCKED':
                stats['skipped'] += 1
                continue
            msg = (f"Đơn {r['order_id'][:8]} đã quá 14 ngày kể từ khi ký quỹ mà chưa được giao. "
                   "Bạn có thể hủy đơn để nhận hoàn tiền 100%.")
            with self._uow() as uow:
                sent = uow.notifications.add(r['buyer_user_id'], r['order_id'], self.KIND, msg)
                uow.commit()
            stats['reminded' if sent else 'skipped'] += 1
        return stats


class DisputeSigExpiry:
    """Đề xuất PROPOSED/READY quá `deadline` -> EXPIRED (SDD 5.5). Contract chỉ nhận chữ ký khi `block.timestamp <= deadline` nên sau mốc đó
    chữ ký vô dụng; Admin có thể tạo đề xuất mới. UPDATE có điều kiện trạng thái nên chạy lặp/song song với relayer đều vô hại (SUBMITTED không
    bị đụng tới). Nếu một giao dịch đã gửi kịp hạn vào chuỗi sau khi job này đặt EXPIRED, Indexer vẫn đặt EXECUTED (chuỗi là sự thật)."""

    def __init__(self, uow_factory, clock, batch=100):
        self._uow, self._clock, self._batch = uow_factory, clock, batch

    def run_once(self):
        now = self._clock.now_chain()
        with self._uow() as uow:
            n = uow.disputes.expire_due(now, self._batch)
            uow.commit()
        return {'expired': n}

