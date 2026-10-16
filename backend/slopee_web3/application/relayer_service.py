"""Relayer cho Shipper (UC-03, SDD 5.3h, DD-06).

Quy tắc:
- Trước khi gửi đọc trạng thái TRỰC TIẾP từ contract: DELIVERED -> thành công (idempotent), khác LOCKED -> INVALID_STATE.
- Kiểm lại một lần NỮA bên trong hàng đợi, vì hai yêu cầu cùng đơn có thể cùng thấy LOCKED ở lần kiểm đầu; yêu cầu thứ hai
  chạy sau khi yêu cầu thứ nhất đã được đào và phải thấy DELIVERED thay vì gửi giao dịch sẽ revert.
- Mỗi bước ghi `tx_outbox` bằng giao dịch MySQL RIÊNG và commit ngay: dấu vết còn nguyên kể cả khi bước sau lỗi.
- Relayer KHÔNG sửa order_web3/orders. Trạng thái DELIVERED trong MySQL do Indexer ghi khi thấy sự kiện OrderDelivered (BR-09).
"""
import logging

from ..domain.errors import DomainError
from ..ports.chain_port import ChainTxFailed, ChainUnavailable

log = logging.getLogger('slopee.web3')

KIND_DELIVER = 'DELIVER'
SHIPPER_ROLE = 'shipper'


class RelayerService:
    def __init__(self, uow_factory, chain, signer, queue, *, receipt_timeout=30.0, queue_timeout=60.0):
        self._uow = uow_factory
        self._chain = chain
        self._signer = signer
        self._queue = queue
        self._receipt_timeout = receipt_timeout
        self._queue_timeout = queue_timeout

    # ------------------------------------------------------------------ UC-03
    def confirm_delivery(self, order_id, onchain_order_id):
        onchain_order_id = int(onchain_order_id)
        sender = self._shipper_address()
        early = self._check_state(onchain_order_id)
        if early is not None:
            return early
        try:
            return self._queue.run(lambda: self._deliver_job(order_id, onchain_order_id, sender), timeout=self._queue_timeout)
        except TimeoutError:
            # Job có thể vẫn chạy tiếp: báo "thử lại sau"; lần thử lại sẽ thấy DELIVERED nếu giao dịch đã được đào.
            raise DomainError('CHAIN_UNAVAILABLE', 'Hệ thống đang bận gửi giao dịch lên blockchain, hãy kiểm tra lại sau ít phút.')

    # ------------------------------------------------------------------ nội bộ
    def _shipper_address(self):
        try:
            return self._signer.sender_address(SHIPPER_ROLE)
        except KeyError:
            raise DomainError('WEB3_NOT_CONFIGURED', 'Máy chủ chưa cấu hình khóa giao hàng (SHIPPER_KEY).')

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
        early = self._check_state(onchain_order_id)          # kiểm lại trong hàng đợi (xem docstring đầu tệp)
        if early is not None:
            return early
        outbox_id = self._log(lambda ob: ob.insert(KIND_DELIVER, order_id))
        try:
            tx_hash = self._chain.send_tx('confirmDelivery', [onchain_order_id], sender,
                                          lambda tx: self._signer.sign_transaction(SHIPPER_ROLE, tx))
        except ChainTxFailed as e:
            self._fail(outbox_id, f'revert: {e}')
            raise DomainError('CHAIN_TX_FAILED', 'Hợp đồng từ chối giao dịch xác nhận giao hàng.')
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
            raise DomainError('CHAIN_TX_FAILED', 'Giao dịch xác nhận giao hàng bị hoàn tác trên blockchain.')
        self._log(lambda ob: ob.mark_confirmed(outbox_id))
        return {'outcome': 'SENT', 'tx_hash': tx_hash, 'outbox_id': outbox_id}
