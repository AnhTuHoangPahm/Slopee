"""Relayer cho Shipper (UC-03, SDD 5.3h, DD-06).

Quy tắc:
- Trước khi gửi đọc trạng thái TRỰC TIẾP từ contract: DELIVERED -> thành công (idempotent), khác LOCKED -> INVALID_STATE.
- Kiểm lại một lần NỮA bên trong hàng đợi, vì hai yêu cầu cùng đơn có thể cùng thấy LOCKED ở lần kiểm đầu; yêu cầu thứ hai
  chạy sau khi yêu cầu thứ nhất đã được đào và phải thấy DELIVERED thay vì gửi giao dịch sẽ revert.
- Mỗi bước ghi `tx_outbox` bằng giao dịch MySQL RIÊNG và commit ngay: dấu vết còn nguyên kể cả khi bước sau lỗi.
- Tuần 5 (B) thêm `release_after_inspection` (AutoRelease, UC-04 kịch bản 2) dùng CHUNG khung gửi/outbox, và `job_guard` tùy chọn:
  một factory context manager bọc quanh mỗi job trong hàng đợi (adapter MySQL GET_LOCK) để Flask và Scheduler, hai tiến trình
  cùng dùng SHIPPER_KEY, không tự đọc nonce song song (hàng đợi một luồng chỉ bảo vệ trong MỘT tiến trình).
- Relayer KHÔNG sửa order_web3/orders. Trạng thái DELIVERED trong MySQL do Indexer ghi khi thấy sự kiện OrderDelivered (BR-09).
- Tuần 7 (B) thêm `force_resolve` (UC-07): `arbitratorForceResolve` đòi `msg.sender` có ARBITRATOR_ROLE nên giao dịch này do KHÓA TRỌNG TÀI ký
  và gửi từ địa chỉ Trọng tài, KHÔNG phải Shipper. Dùng chung hàng đợi một luồng và khóa liên tiến trình (an toàn hơn mức cần: hai tài khoản
  khác nhau không đụng nonce của nhau, nhưng một đường gửi duy nhất dễ kiểm chứng và không thêm cơ chế mới).
"""
import logging

from ..domain.dispute import CHAIN_STATE_BY_SIDE
from ..domain.errors import DomainError
from ..ports.chain_port import ChainTxFailed, ChainUnavailable

log = logging.getLogger('slopee.web3')

KIND_DELIVER = 'DELIVER'
KIND_RELEASE = 'RELEASE'
KIND_RESOLVE = 'RESOLVE'
KIND_FORCE = 'FORCE_RESOLVE'
SHIPPER_ROLE = 'shipper'
ARBITRATOR_ROLE = 'arbitrator'


class RelayerService:
    def __init__(self, uow_factory, chain, signer, queue, *, receipt_timeout=30.0, queue_timeout=60.0, job_guard=None):
        self._uow = uow_factory
        self._chain = chain
        self._signer = signer
        self._queue = queue
        self._receipt_timeout = receipt_timeout
        self._queue_timeout = queue_timeout
        self._job_guard = job_guard

    # ------------------------------------------------------------------ UC-03
    def confirm_delivery(self, order_id, onchain_order_id):
        onchain_order_id = int(onchain_order_id)
        sender = self._shipper_address()
        early = self._check_state(onchain_order_id)
        if early is not None:
            return early
        try:
            return self._queue.run(self._guarded(lambda: self._deliver_job(order_id, onchain_order_id, sender)),
                                   timeout=self._queue_timeout)
        except TimeoutError:
            # Job có thể vẫn chạy tiếp: báo "thử lại sau"; lần thử lại sẽ thấy DELIVERED nếu giao dịch đã được đào.
            raise DomainError('CHAIN_UNAVAILABLE', 'Hệ thống đang bận gửi giao dịch lên blockchain, hãy kiểm tra lại sau ít phút.')

    # ------------------------------------------------------------------ UC-04 kịch bản 2 (B, tuần 5)
    def release_after_inspection(self, order_id, onchain_order_id):
        """Gọi `releaseAfterInspection` (ai cũng gọi được sau hạn kiểm tra; relayer trả gas). Trả
        {'outcome': 'SENT'|'ALREADY_COMPLETED', 'tx_hash', 'outbox_id'}. Việc kiểm HẠN kiểm tra là của người gọi (AutoRelease đọc
        deliveredAt/inspectionDuration từ chuỗi); contract vẫn revert 'Under inspection' nếu gọi sớm ⇒ CHAIN_TX_FAILED."""
        onchain_order_id = int(onchain_order_id)
        sender = self._shipper_address()
        early = self._check_release_state(onchain_order_id)
        if early is not None:
            return early
        try:
            return self._queue.run(self._guarded(lambda: self._release_job(order_id, onchain_order_id, sender)),
                                   timeout=self._queue_timeout)
        except TimeoutError:
            raise DomainError('CHAIN_UNAVAILABLE', 'Hệ thống đang bận gửi giao dịch lên blockchain, hãy kiểm tra lại sau ít phút.')

    # ------------------------------------------------------------------ UC-06 (A, tuần 6)
    def resolve_dispute(self, order_id, onchain_order_id, payout_to, deadline, sig1, sig2, nonce):
        """Nộp `resolveDispute(orderId, payoutTo, deadline, sig1, sig2)` (ai cũng nộp được; relayer trả gas). Người gọi PHẢI đã kiểm
        chữ ký ở tầng ứng dụng (DisputeSubmitService); ở đây chỉ kiểm phần chuỗi: đơn còn DISPUTED và `disputeNonces` còn đúng
        `nonce` mà chữ ký mang. Trả {'outcome': 'SENT'|'ALREADY_RESOLVED', 'tx_hash', 'outbox_id'}."""
        onchain_order_id, nonce = int(onchain_order_id), int(nonce)
        sender = self._shipper_address()
        args = [onchain_order_id, payout_to, int(deadline), bytes.fromhex(sig1[2:] if sig1.startswith('0x') else sig1),
                bytes.fromhex(sig2[2:] if sig2.startswith('0x') else sig2)]

        def check(oid):
            return self._check_resolve_state(oid, nonce)

        early = check(onchain_order_id)
        if early is not None:
            return early
        try:
            return self._queue.run(self._guarded(lambda: self._send_job(
                KIND_RESOLVE, 'resolveDispute', check, order_id, onchain_order_id, sender,
                'Hợp đồng từ chối phán quyết (chữ ký, hạn hoặc nonce không hợp lệ).',
                'Giao dịch phán quyết bị hoàn tác trên blockchain.', args=args)), timeout=self._queue_timeout)
        except TimeoutError:
            raise DomainError('CHAIN_UNAVAILABLE', 'Hệ thống đang bận gửi giao dịch lên blockchain, hãy kiểm tra lại sau ít phút.')

    def _check_resolve_state(self, onchain_order_id, nonce):
        state = self._chain.get_order_state(onchain_order_id)
        if state in ('COMPLETED', 'REFUNDED'):
            return {'outcome': 'ALREADY_RESOLVED', 'tx_hash': None, 'outbox_id': None, 'chain_state': state}
        if state != 'DISPUTED':
            raise DomainError('INVALID_STATE', 'Đơn không ở trạng thái tranh chấp.', {'chain_state': state})
        if int(self._chain.dispute_nonce(onchain_order_id)) != nonce:
            raise DomainError('DISPUTE_STALE', 'Đề xuất phán quyết đã cũ (nonce trên chuỗi đã đổi), cần đề xuất mới.')
        return None

    # ------------------------------------------------------------------ UC-07 (B, tuần 7)
    def force_resolve(self, order_id, onchain_order_id, payout_to, side):
        """Nộp `arbitratorForceResolve(orderId, payoutTo)` bằng KHÓA TRỌNG TÀI. `side` ('BUYER'|'MERCHANT') là bên `payout_to` thuộc về, để nhận ra
        yêu cầu lặp: chuỗi đã REFUNDED (Buyer) / COMPLETED (Merchant) đúng ý thì trả ALREADY_RESOLVED, trái ý thì INVALID_STATE. Người gọi
        (DisputeForceResolveService) PHẢI đã kiểm quyền Admin và mốc `disputedAt + disputeTimeout`; ở đây chỉ kiểm phần chuỗi.
        Trả {'outcome': 'SENT'|'ALREADY_RESOLVED', 'tx_hash', 'outbox_id'[, 'chain_state']}."""
        onchain_order_id = int(onchain_order_id)
        sender = self._arbitrator_address()

        def check(oid):
            return self._check_force_state(oid, side)

        early = check(onchain_order_id)
        if early is not None:
            return early
        try:
            return self._queue.run(self._guarded(lambda: self._send_job(
                KIND_FORCE, 'arbitratorForceResolve', check, order_id, onchain_order_id, sender,
                'Hợp đồng từ chối xử đơn phương (chưa tới hạn tranh chấp hoặc đơn không còn ở trạng thái tranh chấp).',
                'Giao dịch xử đơn phương bị hoàn tác trên blockchain.', args=[onchain_order_id, payout_to], role=ARBITRATOR_ROLE)),
                timeout=self._queue_timeout)
        except TimeoutError:
            raise DomainError('CHAIN_UNAVAILABLE', 'Hệ thống đang bận gửi giao dịch lên blockchain, hãy kiểm tra lại sau ít phút.')

    def _check_force_state(self, onchain_order_id, side):
        state = self._chain.get_order_state(onchain_order_id)
        if state in ('COMPLETED', 'REFUNDED'):
            if CHAIN_STATE_BY_SIDE.get(side) == state:
                return {'outcome': 'ALREADY_RESOLVED', 'tx_hash': None, 'outbox_id': None, 'chain_state': state}
            raise DomainError('INVALID_STATE', 'Đơn đã được xử lý theo cách khác, không còn xử đơn phương được nữa.', {'chain_state': state})
        if state != 'DISPUTED':
            raise DomainError('INVALID_STATE', 'Đơn không ở trạng thái tranh chấp.', {'chain_state': state})
        return None

    # ------------------------------------------------------------------ nội bộ
    def _guarded(self, job):
        if self._job_guard is None:
            return job

        def run():
            with self._job_guard():
                return job()
        return run

    def _check_release_state(self, onchain_order_id):
        state = self._chain.get_order_state(onchain_order_id)
        if state == 'COMPLETED':
            return {'outcome': 'ALREADY_COMPLETED', 'tx_hash': None, 'outbox_id': None}
        if state != 'DELIVERED':
            raise DomainError('INVALID_STATE', 'Đơn không ở trạng thái chờ giải ngân.', {'chain_state': state})
        return None

    def _shipper_address(self):
        try:
            return self._signer.sender_address(SHIPPER_ROLE)
        except KeyError:
            raise DomainError('WEB3_NOT_CONFIGURED', 'Máy chủ chưa cấu hình khóa giao hàng (SHIPPER_KEY).')

    def _arbitrator_address(self):
        try:
            return self._signer.sender_address(ARBITRATOR_ROLE)
        except KeyError:
            raise DomainError('WEB3_NOT_CONFIGURED', 'Máy chủ chưa cấu hình khóa Trọng tài (ARBITRATOR_KEY).')

    def _check_state(self, onchain_order_id):
        """None nếu đơn đang LOCKED (được gửi); kết quả idempotent nếu đã DELIVERED; còn lại INVALID_STATE."""
        state = self._chain.get_order_state(onchain_order_id)
        if state == 'DELIVERED':
            return {'outcome': 'ALREADY_DELIVERED', 'tx_hash': None, 'outbox_id': None}
        if state != 'LOCKED':
            raise DomainError('INVALID_STATE', 'Đơn không còn ở trạng thái chờ giao hàng.', {'chain_state': state})
        return None

    def _log(self, fn):
        with self._uow() as uow:
            result = fn(uow.outbox)
            uow.commit()
        return result

    def _fail(self, outbox_id, error):
        try:
            self._log(lambda ob: ob.mark_failed(outbox_id, error))
        except Exception:      # ghi vết hỏng không được che lỗi gốc
            log.error('Không ghi được tx_outbox FAILED cho id=%s', outbox_id, exc_info=True)

    def _deliver_job(self, order_id, onchain_order_id, sender):
        return self._send_job(KIND_DELIVER, 'confirmDelivery', self._check_state, order_id, onchain_order_id, sender,
                              'Hợp đồng từ chối giao dịch xác nhận giao hàng.',
                              'Giao dịch xác nhận giao hàng bị hoàn tác trên blockchain.')

    def _release_job(self, order_id, onchain_order_id, sender):
        return self._send_job(KIND_RELEASE, 'releaseAfterInspection', self._check_release_state, order_id, onchain_order_id,
                              sender, 'Hợp đồng từ chối giao dịch giải ngân.',
                              'Giao dịch giải ngân bị hoàn tác trên blockchain.')

    def _send_job(self, kind, fn_name, check, order_id, onchain_order_id, sender, msg_rejected, msg_reverted, args=None, role=SHIPPER_ROLE):
        early = check(onchain_order_id)                      # kiểm lại trong hàng đợi (xem docstring đầu tệp)
        if early is not None:
            return early
        outbox_id = self._log(lambda ob: ob.insert(kind, order_id))
        try:
            tx_hash = self._chain.send_tx(fn_name, [onchain_order_id] if args is None else args, sender,
                                          lambda tx: self._signer.sign_transaction(role, tx))
        except ChainTxFailed as e:
            self._fail(outbox_id, f'revert: {e}')
            raise DomainError('CHAIN_TX_FAILED', msg_rejected)
        except Exception as e:      # ChainUnavailable, lỗi ký...: ghi FAILED rồi ném nguyên lỗi gốc cho adapter Flask ánh xạ
            self._fail(outbox_id, f'{type(e).__name__}: {e}')
            raise
        self._log(lambda ob: ob.mark_sent(outbox_id, tx_hash))
        try:
            receipt = self._chain.wait_receipt(tx_hash, self._receipt_timeout)
        except ChainUnavailable:
            # Không biết giao dịch đã được đào chưa: GIỮ trạng thái SENT (không đánh FAILED), người dùng thử lại sẽ đọc chuỗi.
            raise
        if receipt['status'] != 1:
            self._fail(outbox_id, f"receipt status=0 block={receipt.get('block_number')}")
            raise DomainError('CHAIN_TX_FAILED', msg_reverted)
        self._log(lambda ob: ob.mark_confirmed(outbox_id))
        return {'outcome': 'SENT', 'tx_hash': tx_hash, 'outbox_id': outbox_id}
