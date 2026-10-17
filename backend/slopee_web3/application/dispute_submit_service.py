"""Nộp phán quyết tranh chấp lên chuỗi (UC-06 bước 4, SDD 5.3i, `POST /api/disputes/:code/submit`). Tuần 6, A.

Quyền: Buyer hoặc Merchant của đơn, hoặc Admin. Người khác/đơn không tồn tại đều trả ORDER_NOT_FOUND (không lộ sự tồn tại).

Quy trình (mọi kiểm tra ĐỀU chạy trước khi tốn gas, vì contract revert vẫn mất phí và tăng nonce relayer):
  1. Có đề xuất mới nhất chưa bị bỏ (EXPIRED/CANCELLED -> DISPUTE_EXPIRED).
  2. Đọc đơn TRỰC TIẾP từ contract (Indexer có thể trễ): số tiền, người nhận, nonce, hạn khớp đề xuất; sai -> DISPUTE_STALE.
  3. Khôi phục địa chỉ từng chữ ký đã lưu và so với ví đã khóa trong đơn (Buyer/Merchant) hoặc địa chỉ Trọng tài của sàn;
     CHỈ chữ ký đúng người mới được tính (không tin cột `party` ở CSDL). Chưa đủ hai bên khác nhau -> DISPUTE_NOT_READY.
  4. Relayer nộp `resolveDispute`; thành công thì PROPOSED/READY -> SUBMITTED (EXECUTED do Indexer, BR-09).
Idempotent: đơn đã được xử đúng theo đề xuất này (kể cả khi lần nộp trước hết hạn chờ biên nhận) -> ALREADY_RESOLVED, không gửi giao dịch.
"""
import logging

from ..domain.dispute import (DEAD, DONE, PARTY_ARBITRATOR, PARTY_BUYER, PARTY_MERCHANT, SUBMITTABLE, DisputeResolution,
                              check_deadline, parties_present, payout_side, pick_signature_pair)
from ..domain.errors import DomainError

log = logging.getLogger('slopee.web3')


class DisputeSubmitService:
    def __init__(self, uow_factory, chain, signer, clock, relayer):
        self._uow = uow_factory
        self._chain = chain
        self._signer = signer
        self._clock = clock
        self._relayer = relayer

    def submit(self, user_id, role, order_code):
        with self._uow() as uow:
            order = uow.disputes.order_for_dispute(order_code)
            if order is None or not (role == 'admin' or user_id in (order['buyer_user_id'], order['merchant_user_id'])):
                raise DomainError('ORDER_NOT_FOUND', 'Không tìm thấy đơn hàng.')
            res = uow.disputes.latest_resolution(order['order_id'])
            if res is None:
                raise DomainError('DISPUTE_NOT_FOUND', 'Đơn này chưa có đề xuất phán quyết.')
            sigs = uow.disputes.signatures(res['id'])
        if res['status'] in DEAD:
            raise DomainError('DISPUTE_EXPIRED', 'Đề xuất phán quyết đã hết hạn hoặc bị hủy, cần Admin tạo đề xuất mới.')

        onchain_id = int(order['onchain_order_id'])
        co = self._chain.get_order(onchain_id)
        side = payout_side(res['payout_to'], co['buyer'], co['merchant'])
        if co['state'] in ('COMPLETED', 'REFUNDED'):
            return self._already_resolved(order, res, co, side)
        if co['state'] != 'DISPUTED':
            raise DomainError('INVALID_STATE', 'Đơn không ở trạng thái tranh chấp.', {'chain_state': co['state']})
        if res['status'] in DONE:
            # Đã nộp mà chuỗi vẫn DISPUTED: giao dịch trước chưa được đào hoặc bị revert. Cho nộp lại (các kiểm tra dưới vẫn áp dụng).
            log.info('Nộp lại phán quyết order=%s (đề xuất %s đang %s nhưng chuỗi còn DISPUTED)', order['order_id'], res['id'], res['status'])
        if side is None or int(res['amount_raw']) != int(co['amount']):
            raise DomainError('DISPUTE_STALE', 'Đề xuất phán quyết không khớp với đơn trên chuỗi, cần đề xuất mới.')
        if int(self._chain.dispute_nonce(onchain_id)) != res['nonce']:
            raise DomainError('DISPUTE_STALE', 'Đề xuất phán quyết đã cũ (nonce trên chuỗi đã đổi), cần đề xuất mới.')
        try:
            check_deadline(self._clock.now_chain(), res['deadline'], co['disputed_at'], co['dispute_timeout'])
        except DomainError as e:
            if e.code == 'DISPUTE_EXPIRED':
                self._mark(res['id'], SUBMITTABLE, 'EXPIRED')
            raise

        resolution = DisputeResolution(orderId=onchain_id, payoutTo=res['payout_to'], amount=int(co['amount']),
                                       nonce=res['nonce'], deadline=res['deadline'])
        valid = self._verified(resolution, sigs, order)
        pair = pick_signature_pair(valid)
        if pair is None:
            raise DomainError('DISPUTE_NOT_READY', 'Chưa đủ chữ ký của hai bên khác nhau để thi hành phán quyết.',
                              {'signed_by': parties_present(valid)})

        out = self._relayer.resolve_dispute(order['order_id'], onchain_id, res['payout_to'], res['deadline'],
                                            pair[0], pair[1], res['nonce'])
        if out['outcome'] == 'ALREADY_RESOLVED':     # đua: người khác nộp ngay trước (hoặc lần trước đã được đào)
            return self._already_resolved(order, res, dict(co, state=out['chain_state']), side)
        self._mark(res['id'], SUBMITTABLE + ('SUBMITTED',), 'SUBMITTED', out['tx_hash'])
        return {'order_id': order['order_id'], 'resolution_id': res['id'], 'outcome': 'SENT', 'tx_hash': out['tx_hash'],
                'resolution_status': 'SUBMITTED', 'payout_side': side}

    # ------------------------------------------------------------------ nội bộ
    def _expected_address(self, party, order):
        if party == PARTY_BUYER:
            return order['buyer_wallet']
        if party == PARTY_MERCHANT:
            return order['merchant_wallet']
        if party == PARTY_ARBITRATOR:
            return self._signer.sender_address('arbitrator')
        return None

    def _verified(self, resolution, sigs, order):
        out = []
        for s in sigs:
            expected = self._expected_address(s['party'], order)
            try:
                got = self._signer.recover_dispute_signer(resolution, s['signature'])
            except (ValueError, KeyError):
                log.warning('Bỏ chữ ký không khôi phục được (order=%s, party=%s)', order['order_id'], s['party'])
                continue
            if expected is not None and str(got).lower() == str(expected).lower():
                out.append(s)
            else:
                log.warning('Bỏ chữ ký không khớp người ký (order=%s, party=%s)', order['order_id'], s['party'])
        return out

    def _mark(self, resolution_id, from_states, to_status, tx_hash=None):
        try:
            with self._uow() as uow:
                uow.disputes.transition_resolution(resolution_id, from_states, to_status, tx_hash)
                uow.commit()
        except Exception:     # ghi trạng thái hỏng không được che kết quả giao dịch đã gửi; Indexer sẽ đặt EXECUTED
            log.error('Không cập nhật được dispute_resolutions id=%s -> %s', resolution_id, to_status, exc_info=True)

    def _already_resolved(self, order, res, co, side):
        """Chuỗi đã COMPLETED/REFUNDED. Khớp phía đề xuất (REFUNDED<->Buyer, COMPLETED<->Merchant) thì coi là đã thi hành đề xuất này."""
        expected = {'BUYER': 'REFUNDED', 'MERCHANT': 'COMPLETED'}.get(side)
        if co['state'] != expected:
            raise DomainError('INVALID_STATE', 'Đơn đã được xử lý theo cách khác, không còn nộp phán quyết này được.',
                              {'chain_state': co['state']})
        if res['status'] in SUBMITTABLE:
            self._mark(res['id'], SUBMITTABLE, 'SUBMITTED')
        return {'order_id': order['order_id'], 'resolution_id': res['id'], 'outcome': 'ALREADY_RESOLVED',
                'tx_hash': res.get('submitted_tx_hash'), 'resolution_status': 'EXECUTED' if res['status'] == 'EXECUTED' else 'SUBMITTED',
                'payout_side': side}
