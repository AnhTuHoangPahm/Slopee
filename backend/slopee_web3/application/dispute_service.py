"""Tạo đề xuất phán quyết, nhận chữ ký Buyer/Merchant, xem tranh chấp (MOD-06, UC-06, BR-04, SDD 5.3i). Tuần 6, B.

Phần NỘP `resolveDispute` lên chuỗi là của A (`DisputeSubmitService`); service này dùng CHUNG `DisputeRepo` với nó.
Hợp đồng phản hồi của `get` do giao diện (C) đề xuất ở đầu `frontend/src/api/disputes.js` và B xác nhận ở đây.

Nguyên tắc:
- Tin CHUỖI, không tin MySQL, cho mọi số liệu đưa vào chữ ký: buyer/merchant/amount/disputedAt/disputeTimeout/nonce đọc trực tiếp từ contract.
- Mỗi đơn chỉ có MỘT đề xuất đang hoạt động; khóa dòng đơn (FOR UPDATE) rồi mới tạo/đổi trạng thái.
- Chữ ký Buyer/Merchant được khôi phục từ CHÍNH nội dung đã lưu của đề xuất (không nhận nội dung từ client) và phải ra đúng địa chỉ ví của bên
  đó TRÊN ĐƠN (`buyer_wallet`/`merchant_wallet`, cũng là địa chỉ contract nhận diện), nếu không contract sẽ revert.
- Chữ ký thô KHÔNG bao giờ trả cho client: Admin hủy đề xuất ở MySQL không thu hồi được chữ ký trên chuỗi, nên chỉ relayer của A được cầm
  chữ ký Trọng tài (qua repo); đề xuất đã hủy thì relayer từ chối nộp.
"""
import re

from ..domain.dispute import (ACTIVE_STATES, DEFAULT_SIG_TTL_SECONDS, PARTY_ARBITRATOR, SUBMITTABLE, DisputeResolution, clean_note,
                              compute_deadline, is_ready, parse_payout, party_of, payout_side)
from ..domain.errors import DomainError
from ..domain.timefmt import fmt_vn

SIGNATURE_RE = re.compile(r'^0x[0-9a-fA-F]{130}$')          # 65 byte r||s||v
PARTY_LABEL = {'BUYER': 'hoàn tiền cho người mua', 'MERCHANT': 'giải ngân cho người bán'}


class DisputeService:
    def __init__(self, uow_factory, chain, signer, clock, token_decimals=6):
        self._uow, self._chain, self._signer, self._clock = uow_factory, chain, signer, clock
        self._decimals = int(token_decimals)

    # ------------------------------------------------------------------ UC-06 bước 1-2: Admin đề xuất, Trọng tài ký
    def propose(self, admin_id, order_code, payout_to, reason_note=None):
        reason_note = clean_note(reason_note)
        with self._uow() as uow:
            order = uow.disputes.order_for_dispute(order_code, lock=True)
            if order is None:
                raise DomainError('ORDER_NOT_FOUND', 'Không tìm thấy đơn hàng.')
            if order['status'] != 'DISPUTED':
                raise DomainError('INVALID_STATE', 'Chỉ đề xuất phán quyết cho đơn đang khiếu nại.', {'status': order['status']})
            onchain_id = int(order['onchain_order_id'])
            on = self._chain.get_order(onchain_id)                 # nguồn sự thật cho mọi giá trị đi vào chữ ký
            if on['state'] != 'DISPUTED':
                raise DomainError('INVALID_STATE', 'Đơn không còn ở trạng thái khiếu nại trên blockchain.', {'chain_state': on['state']})
            now = self._clock.now_chain()

            active = uow.disputes.latest_resolution(order['order_id'], lock=True)
            if active is not None and active['status'] in ACTIVE_STATES:
                if active['status'] == 'SUBMITTED' and now <= active['deadline']:
                    raise DomainError('INVALID_STATE', 'Đề xuất hiện tại đang được nộp lên blockchain, hãy chờ kết quả.',
                                      {'status': 'SUBMITTED'})
                # Admin tạo đề xuất mới thay cho đề xuất cũ (SDD 5.3i). SUBMITTED đã quá hạn mà vẫn chưa vào chuỗi thì coi là hết hạn.
                uow.disputes.transition_resolution(active['id'], (active['status'],),
                                                   'EXPIRED' if active['status'] == 'SUBMITTED' else 'CANCELLED')

            party, payout_address = parse_payout(payout_to, on['buyer'], on['merchant'])
            deadline = compute_deadline(now, self._sig_ttl(uow), on['disputed_at'], on['dispute_timeout'])
            if deadline <= now:
                raise DomainError('DISPUTE_WINDOW_CLOSED', 'Đã hết thời hạn dùng chữ ký 2/3; đơn này chỉ còn cách để Trọng tài xử đơn '
                                  'phương (UC-07).', {'force_resolve_at': int(on['disputed_at']) + int(on['dispute_timeout'])})
            res = DisputeResolution(orderId=onchain_id, payoutTo=self._signer.to_checksum(payout_address), amount=int(on['amount']),
                                    nonce=int(self._chain.dispute_nonce(onchain_id)), deadline=deadline)
            signature = self._signer.sign_dispute(res)
            arbitrator = self._signer.sender_address('arbitrator')
            if str(self._signer.recover_dispute_signer(res, signature)).lower() != arbitrator.lower():   # tự kiểm trước khi ghi gì
                raise RuntimeError('Chữ ký Trọng tài không khôi phục về địa chỉ Trọng tài: kiểm tra ARBITRATOR_KEY.')

            rid = uow.disputes.create_resolution(order['order_id'], res.payoutTo, str(res.amount), res.nonce, res.deadline,
                                                 reason_note, admin_id)
            uow.disputes.add_signature(rid, PARTY_ARBITRATOR, arbitrator, signature)
            message = (f"Đơn {order['order_id'][:8]} có đề xuất phán quyết: {PARTY_LABEL[party]}. Bạn có thể xem và ký trước "
                       f"{fmt_vn(deadline)} (giờ Việt Nam); một chữ ký của người mua hoặc người bán là đủ để thi hành ngay.")
            for user_id in (order['buyer_user_id'], order['merchant_user_id']):
                uow.notifications.add(user_id, order['order_id'], f'DISPUTE_PROPOSED:{rid}', message)
            uow.commit()
        return {'resolution_id': rid, 'order_id': order['order_id'], 'status': 'PROPOSED', 'payout_side': party,
                'payout_to': res.payoutTo, 'amount_raw': str(res.amount), 'nonce': str(res.nonce), 'deadline': res.deadline}

    # ------------------------------------------------------------------ UC-06 bước 3-4: Buyer/Merchant ký
    def add_signature(self, user_id, order_code, resolution_id, signature):
        if not isinstance(signature, str) or not SIGNATURE_RE.match(signature.strip()):
            raise DomainError('BAD_SIGNATURE', 'Chữ ký không hợp lệ (cần chuỗi hex 0x… dài 65 byte).')
        signature = signature.strip()
        with self._uow() as uow:
            order = uow.disputes.order_for_dispute(order_code, lock=True)
            party = None if order is None else party_of(user_id, order['buyer_user_id'], order['merchant_user_id'])
            if party is None:                                      # không lộ sự tồn tại của đơn người khác
                raise DomainError('ORDER_NOT_FOUND', 'Không tìm thấy đơn hàng.')
            res = uow.disputes.get_resolution(resolution_id)
            if res is None or res['order_id'] != order['order_id']:
                raise DomainError('DISPUTE_NOT_FOUND', 'Không tìm thấy đề xuất phán quyết của đơn này.')
            if order['status'] != 'DISPUTED' or res['status'] not in SUBMITTABLE:
                raise DomainError('INVALID_STATE', 'Đề xuất này không còn nhận chữ ký.',
                                  {'status': res['status'], 'order_status': order['status']})
            if self._clock.now_chain() > res['deadline']:
                raise DomainError('SIGNATURE_EXPIRED', 'Đề xuất đã hết hạn ký, hãy nhờ Admin tạo đề xuất mới.', {'deadline': res['deadline']})
            message = DisputeResolution(orderId=int(order['onchain_order_id']), payoutTo=self._signer.to_checksum(res['payout_to']),
                                        amount=res['amount_raw'], nonce=res['nonce'], deadline=res['deadline'])
            try:
                signer_address = str(self._signer.recover_dispute_signer(message, signature)).lower()
            except ValueError:
                raise DomainError('BAD_SIGNATURE', 'Chữ ký không hợp lệ.')
            expected = order['buyer_wallet' if party == 'BUYER' else 'merchant_wallet']
            if signer_address != expected.lower():
                raise DomainError('BAD_SIGNATURE', 'Chữ ký không khớp ví của bạn trong đơn này hoặc không ký đúng nội dung đề xuất.')

            existing = {s['party']: s for s in uow.disputes.signatures(res['id'])}
            if party in existing:
                # Gửi lại cùng chữ ký (lỗi mạng làm mất phản hồi) là idempotent; chữ ký KHÁC thì từ chối, giữ chữ ký đầu.
                if existing[party]['signature'].lower() != signature.lower():
                    raise DomainError('ALREADY_SIGNED', 'Bạn đã ký đề xuất này rồi.', {'status': res['status']})
            else:
                uow.disputes.add_signature(res['id'], party, signer_address, signature)
                existing[party] = {'party': party}
            status = res['status']
            if status == 'PROPOSED' and is_ready(existing):
                if uow.disputes.transition_resolution(res['id'], ('PROPOSED',), 'READY'):
                    status = 'READY'
            uow.commit()
        return {'resolution_id': res['id'], 'status': status, 'party': party, 'signed_parties': sorted(existing)}

    # ------------------------------------------------------------------ xem (hợp đồng đề xuất của C, B xác nhận)
    def get(self, user_id, role, order_code):
        """Buyer/Merchant của đơn, hoặc Admin (`your_party` = 'ADMIN'). Chữ ký thô không bao giờ có trong kết quả."""
        with self._uow() as uow:
            order = uow.disputes.order_for_dispute(order_code)
            party = None if order is None else party_of(user_id, order['buyer_user_id'], order['merchant_user_id'])
            if order is None or (role != 'admin' and party is None):
                raise DomainError('ORDER_NOT_FOUND', 'Không tìm thấy đơn hàng.')
            res = uow.disputes.latest_resolution(order['order_id'])
            sigs = uow.disputes.signatures(res['id']) if res else []
            note = uow.dispute_notes.get(order['order_id'])
        resolution = None
        if res is not None:
            resolution = {
                'resolution_id': res['id'], 'payout_to': res['payout_to'], 'amount_raw': str(res['amount_raw']),
                'nonce': str(res['nonce']), 'deadline': res['deadline'], 'status': res['status'], 'reason_note': res['reason_note'],
                'submitted_tx_hash': res['submitted_tx_hash'], 'created_at': res['created_at'],
                'payout_side': payout_side(res['payout_to'], order['buyer_wallet'], order['merchant_wallet']),
                'signatures': [{'party': s['party'], 'signer': s['signer_address'], 'signed_at': int(s['signed_at'])} for s in sigs],
            }
        return {
            'order_id': order['order_id'], 'onchain_order_id': str(int(order['onchain_order_id'])), 'order_status': order['status'],
            'your_party': party or 'ADMIN', 'buyer_wallet': order['buyer_wallet'], 'merchant_wallet': order['merchant_wallet'],
            'amount_raw': str(order['amount_raw']), 'decimals': self._decimals, 'symbol': order['token_symbol'],
            'fee_bps': int(order['fee_bps']),
            'disputed_at': None if order['disputed_at'] is None else int(order['disputed_at']),
            'dispute_timeout': int(order['dispute_timeout']), 'server_time': self._clock.now_chain(),
            'note': None if note is None else {'reason': note['reason'], 'evidence_url': note['evidence_url'],
                                               'updated_at': int(note['updated_at'])},
            'resolution': resolution,
        }

    # ------------------------------------------------------------------ nội bộ
    @staticmethod
    def _sig_ttl(uow):
        raw = uow.settings.get_many(['DISPUTE_SIG_TTL_SECONDS']).get('DISPUTE_SIG_TTL_SECONDS')
        try:
            ttl = int(raw) if raw is not None else DEFAULT_SIG_TTL_SECONDS
        except (TypeError, ValueError):
            raise DomainError('SETTING_INVALID', 'Cấu hình hạn chữ ký không hợp lệ.')
        if ttl <= 0:
            raise DomainError('SETTING_INVALID', 'Cấu hình hạn chữ ký không hợp lệ.')
        return ttl
