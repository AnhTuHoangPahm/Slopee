"""Tuần 6 (A) UC-06: nộp `resolveDispute` qua relayer khi đủ 2/3 chữ ký. Không cần MySQL/Anvil.

Chuỗi là FakeEscrowChain mô hình đúng contract và KHÔNG dùng EnvKeySigner để kiểm chữ ký (dùng eth_account trực tiếp với
shared/eip712/types.json), nên test này cũng kiểm chéo EnvKeySigner.sign_dispute với "contract".
"""
import threading

import pytest

from slopee_web3.adapters.relayer_queue import SingleThreadQueue
from slopee_web3.application.dispute_submit_service import DisputeSubmitService
from slopee_web3.application.relayer_service import RelayerService
from slopee_web3.domain import dispute as dm
from slopee_web3.domain.dispute import DisputeResolution
from slopee_web3.domain.errors import DomainError, http_status
from slopee_web3.ports.chain_port import ChainUnavailable
from w3_support import (ADDR, TOKEN, VECTORS, FakeEscrowChain, MemoryDisputeRepo, MemoryDisputeUow, MemoryOutbox,
                        make_signer, sign_dispute_as)

NOW = 1_800_000_000
OID = 1001
AMOUNT = 16_500_000
TIMEOUT = 30 * 86400
ORDER = 'ord-0001'


class ChainClock:
    def __init__(self, chain):
        self.chain = chain

    def now_chain(self):
        return self.chain.now

    def now_system(self):
        return self.chain.now


class Rig:
    def __init__(self, payout='buyer', deadline=None, nonce=0, status='PROPOSED'):
        self.chain = FakeEscrowChain(now=NOW)
        self.chain.orders[OID] = {'state': 'DISPUTED', 'buyer': ADDR['buyer'], 'merchant': ADDR['merchant1'], 'token': TOKEN,
                                  'amount': AMOUNT, 'created_at': NOW - 9 * 86400, 'delivered_at': NOW - 5 * 86400,
                                  'disputed_at': NOW - 3600, 'dispute_timeout': TIMEOUT, 'inspection_duration': 86400, 'fee_bps': 300}
        self.repo, self.outbox, self.commits = MemoryDisputeRepo(), MemoryOutbox(), []
        self.repo.orders[ORDER] = {'order_id': ORDER, 'onchain_order_id': OID, 'buyer_user_id': 'u-buyer', 'merchant_user_id': 'u-merchant',
                                   'buyer_wallet': ADDR['buyer'].lower(), 'merchant_wallet': ADDR['merchant1'].lower(),
                                   'status': 'DISPUTED', 'amount_raw': str(AMOUNT), 'disputed_at': NOW - 3600, 'dispute_timeout': TIMEOUT}
        self.payout_to = ADDR['buyer'] if payout == 'buyer' else ADDR['merchant1']
        self.deadline = deadline if deadline is not None else NOW + 7 * 86400
        self.nonce = nonce
        self.repo.resolutions.append({'id': 1, 'order_id': ORDER, 'payout_to': self.payout_to, 'amount_raw': AMOUNT, 'nonce': nonce,
                                      'deadline': self.deadline, 'status': status, 'reason_note': None, 'submitted_tx_hash': None})
        self.signer = make_signer()
        self.queue = SingleThreadQueue('dispute-test')
        uow = lambda: MemoryDisputeUow(self.outbox, self.commits, self.repo)      # noqa: E731
        self.relayer = RelayerService(uow, self.chain, self.signer, self.queue, receipt_timeout=1, queue_timeout=10)
        self.svc = DisputeSubmitService(uow, self.chain, self.signer, ChainClock(self.chain), self.relayer)

    # chữ ký như client: Buyer/Merchant ký bằng MetaMask, Arbitrator do backend ký
    def sig(self, key_name, **over):
        a = dict(order_id=OID, payout_to=self.payout_to, amount=AMOUNT, nonce=self.nonce, deadline=self.deadline)
        a.update(over)
        return sign_dispute_as(key_name, a['order_id'], a['payout_to'], a['amount'], a['nonce'], a['deadline'])

    def add(self, party, key_name=None, **over):
        key = key_name or {'BUYER': 'buyer', 'MERCHANT': 'merchant1', 'ARBITRATOR': 'arbitrator'}[party]
        self.repo.sigs.setdefault(1, []).append({'party': party, 'signer_address': ADDR[key], 'signature': self.sig(key, **over)})

    def submit(self, user='u-buyer', role='user'):
        return self.svc.submit(user, role, ORDER)

    @property
    def status(self):
        return self.repo.resolutions[-1]['status']

    def close(self):
        self.queue.close()


@pytest.fixture
def rig():
    r = Rig()
    yield r
    r.close()


# ------------------------------------------------------------------ đường vui
def test_refund_buyer_with_arbitrator_plus_buyer_signature(rig):
    rig.add('ARBITRATOR')
    rig.add('BUYER')
    out = rig.submit()
    assert out['outcome'] == 'SENT' and out['resolution_status'] == 'SUBMITTED' and out['payout_side'] == 'BUYER'
    assert rig.chain.orders[OID]['state'] == 'REFUNDED' and rig.chain.dispute_nonces[OID] == 1
    assert rig.status == 'SUBMITTED' and rig.repo.resolutions[0]['submitted_tx_hash'] == out['tx_hash']
    row = rig.outbox.rows[0]
    assert (row['kind'], row['order_id'], row['status']) == ('RESOLVE', ORDER, 'CONFIRMED')
    assert rig.chain.sent_txs[0][0] == 'resolveDispute' and rig.chain.sent_txs[0][2] == ADDR['shipper']     # relayer = khóa shipper của sàn


def test_release_to_merchant_with_arbitrator_plus_merchant_signature():
    r = Rig(payout='merchant')
    try:
        r.add('ARBITRATOR')
        r.add('MERCHANT')
        out = r.submit(user='u-merchant', role='seller')
        assert out['payout_side'] == 'MERCHANT' and r.chain.orders[OID]['state'] == 'COMPLETED'
        assert [e['event'] for e in r.chain.logs][-2:] == ['OrderCompleted', 'DisputeResolved']
    finally:
        r.close()


def test_buyer_plus_merchant_without_arbitrator_is_also_valid(rig):
    rig.add('BUYER')
    rig.add('MERCHANT')
    assert rig.submit()['outcome'] == 'SENT'


def test_admin_may_submit(rig):
    rig.add('ARBITRATOR')
    rig.add('BUYER')
    assert rig.submit(user='u-admin', role='admin')['outcome'] == 'SENT'


# ------------------------------------------------------------------ chưa đủ / giả mạo chữ ký
def test_arbitrator_alone_is_not_ready_409(rig):
    rig.add('ARBITRATOR')
    with pytest.raises(DomainError) as e:
        rig.submit()
    assert e.value.code == 'DISPUTE_NOT_READY' and http_status(e.value.code) == 409 and e.value.extra == {'signed_by': ['ARBITRATOR']}
    assert rig.chain.sent_txs == [] and rig.outbox.rows == []          # không tốn gas, không để lại dấu vết gửi


@pytest.mark.parametrize('label,signed_by', [('BUYER', 'stranger'), ('BUYER', 'merchant1'), ('ARBITRATOR', 'buyer')])
def test_signature_by_the_wrong_person_is_ignored(rig, label, signed_by):
    """Không tin cột `party`: chữ ký phải khôi phục đúng ra ví của bên đó (đã khóa trong đơn) hoặc địa chỉ Trọng tài."""
    if label != 'ARBITRATOR':
        rig.add('ARBITRATOR')
    rig.add(label, key_name=signed_by)
    with pytest.raises(DomainError) as e:
        rig.submit()
    assert e.value.code == 'DISPUTE_NOT_READY' and rig.chain.sent_txs == []


@pytest.mark.parametrize('field,value', [('amount', AMOUNT + 1), ('nonce', 5), ('deadline', NOW + 99), ('payout_to', ADDR['merchant1']),
                                         ('order_id', OID + 1)])
def test_signature_over_different_content_is_ignored(rig, field, value):
    rig.add('ARBITRATOR')
    rig.add('BUYER', **{field: value})
    with pytest.raises(DomainError) as e:
        rig.submit()
    assert e.value.code == 'DISPUTE_NOT_READY' and e.value.extra['signed_by'] == ['ARBITRATOR']


def test_garbage_signature_is_ignored_not_a_500(rig):
    rig.add('ARBITRATOR')
    rig.repo.sigs[1].append({'party': 'BUYER', 'signer_address': ADDR['buyer'], 'signature': '0x' + '00' * 65})
    rig.repo.sigs[1].append({'party': 'MERCHANT', 'signer_address': ADDR['merchant1'], 'signature': 'không-phải-chữ-ký'})
    with pytest.raises(DomainError) as e:
        rig.submit()
    assert e.value.code == 'DISPUTE_NOT_READY'


# ------------------------------------------------------------------ quyền
@pytest.mark.parametrize('user,role', [('u-stranger', 'user'), ('u-stranger', 'seller'), ('u-shipper', 'shipper')])
def test_non_party_gets_order_not_found(rig, user, role):
    rig.add('ARBITRATOR')
    rig.add('BUYER')
    with pytest.raises(DomainError) as e:
        rig.submit(user=user, role=role)
    assert e.value.code == 'ORDER_NOT_FOUND' and rig.chain.sent_txs == []


def test_unknown_order_looks_the_same_as_foreign_order(rig):
    with pytest.raises(DomainError) as e:
        rig.svc.submit('u-buyer', 'user', 'khong-co')
    assert e.value.code == 'ORDER_NOT_FOUND'


# ------------------------------------------------------------------ đề xuất không dùng được
def test_no_resolution_yet_is_dispute_not_found(rig):
    rig.repo.resolutions.clear()
    with pytest.raises(DomainError) as e:
        rig.submit()
    assert e.value.code == 'DISPUTE_NOT_FOUND' and http_status(e.value.code) == 404


@pytest.mark.parametrize('status', ['EXPIRED', 'CANCELLED'])
def test_dead_resolution_is_410(status):
    r = Rig(status=status)
    try:
        r.add('ARBITRATOR'), r.add('BUYER')
        with pytest.raises(DomainError) as e:
            r.submit()
        assert e.value.code == 'DISPUTE_EXPIRED' and http_status(e.value.code) == 410
    finally:
        r.close()


def test_expired_deadline_marks_expired_and_sends_nothing():
    r = Rig(deadline=NOW - 1)
    try:
        r.add('ARBITRATOR'), r.add('BUYER')
        with pytest.raises(DomainError) as e:
            r.submit()
        assert e.value.code == 'DISPUTE_EXPIRED' and r.status == 'EXPIRED' and r.chain.sent_txs == []
    finally:
        r.close()


def test_deadline_not_before_dispute_timeout_is_stale():
    r = Rig(deadline=NOW - 3600 + TIMEOUT)         # = disputedAt + disputeTimeout: contract từ chối (R-02)
    try:
        r.add('ARBITRATOR'), r.add('BUYER')
        with pytest.raises(DomainError) as e:
            r.submit()
        assert e.value.code == 'DISPUTE_STALE' and r.chain.sent_txs == []
    finally:
        r.close()


def test_stale_nonce_and_amount_are_dispute_stale(rig):
    rig.add('ARBITRATOR'), rig.add('BUYER')
    rig.chain.dispute_nonces[OID] = 1
    with pytest.raises(DomainError) as e:
        rig.submit()
    assert e.value.code == 'DISPUTE_STALE'
    rig.chain.dispute_nonces[OID] = 0
    rig.chain.orders[OID]['amount'] = AMOUNT + 1
    with pytest.raises(DomainError) as e2:
        rig.submit()
    assert e2.value.code == 'DISPUTE_STALE' and rig.chain.sent_txs == []


def test_payout_address_not_in_order_is_stale(rig):
    rig.repo.resolutions[0]['payout_to'] = ADDR['stranger']
    rig.add('ARBITRATOR')
    with pytest.raises(DomainError) as e:
        rig.submit()
    assert e.value.code == 'DISPUTE_STALE'


def test_order_not_disputed_on_chain_is_invalid_state(rig):
    rig.chain.orders[OID]['state'] = 'DELIVERED'
    with pytest.raises(DomainError) as e:
        rig.submit()
    assert e.value.code == 'INVALID_STATE' and e.value.extra == {'chain_state': 'DELIVERED'}


# ------------------------------------------------------------------ idempotent / đua / lỗi chuỗi
def test_second_submit_is_already_resolved_without_new_tx(rig):
    rig.add('ARBITRATOR'), rig.add('BUYER')
    rig.submit()
    again = rig.submit()
    assert again['outcome'] == 'ALREADY_RESOLVED' and len(rig.chain.sent_txs) == 1 and len(rig.outbox.rows) == 1


def test_retry_after_receipt_timeout_recovers_status_without_resending(rig):
    rig.add('ARBITRATOR'), rig.add('BUYER')
    real = rig.chain.wait_receipt

    def timeout(*a, **k):
        raise ChainUnavailable('TimeExhausted')
    rig.chain.wait_receipt = timeout
    with pytest.raises(ChainUnavailable):
        rig.submit()
    assert rig.outbox.rows[0]['status'] == 'SENT' and rig.status == 'PROPOSED'        # giao dịch ĐÃ vào chuỗi nhưng ta chưa biết
    rig.chain.wait_receipt = real
    out = rig.submit()
    assert out['outcome'] == 'ALREADY_RESOLVED' and rig.status == 'SUBMITTED' and len(rig.chain.sent_txs) == 1


def test_order_resolved_the_other_way_is_not_claimed_as_ours(rig):
    """Chuỗi đã REFUNDED nhưng đề xuất này là giải ngân Merchant: KHÔNG được nói 'đã thi hành'."""
    r = Rig(payout='merchant')
    try:
        r.add('ARBITRATOR'), r.add('MERCHANT')
        r.chain.orders[OID]['state'] = 'REFUNDED'
        with pytest.raises(DomainError) as e:
            r.submit(user='u-merchant', role='seller')
        assert e.value.code == 'INVALID_STATE' and r.status == 'PROPOSED'
    finally:
        r.close()


def test_two_parties_clicking_together_send_one_transaction(rig):
    rig.add('ARBITRATOR'), rig.add('BUYER')
    results, errors = [], []

    def go(user, role):
        try:
            results.append(rig.submit(user, role)['outcome'])
        except Exception as e:      # noqa: BLE001
            errors.append(e)
    ts = [threading.Thread(target=go, args=('u-buyer', 'user')), threading.Thread(target=go, args=('u-admin', 'admin'))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors and sorted(results) == ['ALREADY_RESOLVED', 'SENT'] and len(rig.chain.sent_txs) == 1


def test_contract_revert_surfaces_as_chain_tx_failed_and_marks_outbox_failed(rig):
    """Bỏ qua tầng ứng dụng, đưa thẳng hai chữ ký CÙNG một bên cho relayer: contract (mô hình) revert 'Need two distinct parties'."""
    s1 = rig.sig('buyer')
    with pytest.raises(DomainError) as e:
        rig.relayer.resolve_dispute(ORDER, OID, rig.payout_to, rig.deadline, s1, s1, 0)
    assert e.value.code == 'CHAIN_TX_FAILED' and http_status('CHAIN_TX_FAILED') == 502
    assert rig.outbox.rows[0]['status'] == 'FAILED' and 'two distinct parties' in rig.outbox.rows[0]['error']
    assert rig.chain.dispute_nonces.get(OID, 0) == 0           # revert không tăng nonce


def test_relayer_checks_nonce_inside_queue(rig):
    s1, s2 = rig.sig('arbitrator'), rig.sig('buyer')
    rig.chain.dispute_nonces[OID] = 3
    with pytest.raises(DomainError) as e:
        rig.relayer.resolve_dispute(ORDER, OID, rig.payout_to, rig.deadline, s1, s2, 0)
    assert e.value.code == 'DISPUTE_STALE' and rig.outbox.rows == []


# ------------------------------------------------------------------ domain thuần
def S(party, sig=None):
    return {'party': party, 'signature': sig or f'0x{party}'}


def test_pick_pair_prefers_arbitrator_plus_one_party():
    assert dm.pick_signature_pair([S('BUYER'), S('ARBITRATOR')]) == ('0xARBITRATOR', '0xBUYER')
    assert dm.pick_signature_pair([S('MERCHANT'), S('ARBITRATOR'), S('BUYER')]) == ('0xARBITRATOR', '0xBUYER')
    assert dm.pick_signature_pair([S('BUYER'), S('MERCHANT')]) == ('0xBUYER', '0xMERCHANT')


@pytest.mark.parametrize('sigs', [[], [S('BUYER')], [S('ARBITRATOR')], [S('BUYER'), S('BUYER', '0xother')]])
def test_pick_pair_needs_two_distinct_parties(sigs):
    assert dm.pick_signature_pair(sigs) is None


def test_check_deadline_matches_the_contract_conditions():
    dm.check_deadline(100, 100, 0, 1000)                       # now == deadline vẫn hợp lệ (contract: now <= deadline)
    with pytest.raises(DomainError) as e:
        dm.check_deadline(101, 100, 0, 1000)
    assert e.value.code == 'DISPUTE_EXPIRED'
    with pytest.raises(DomainError) as e2:
        dm.check_deadline(1, 1000, 0, 1000)                    # deadline == disputedAt + timeout bị từ chối
    assert e2.value.code == 'DISPUTE_STALE'


def test_payout_side_is_case_insensitive():
    assert dm.payout_side('0xABC', '0xabc', '0xdef') == 'BUYER'
    assert dm.payout_side('0xDEF', '0xabc', '0xdef') == 'MERCHANT'
    assert dm.payout_side('0x123', '0xabc', '0xdef') is None


# ------------------------------------------------------------------ signer.sign_dispute / recover (vector chung 3 ngôn ngữ)
@pytest.mark.parametrize('v', VECTORS['disputeResolution'], ids=lambda v: v['name'])
def test_sign_dispute_reproduces_shared_vector_signature(v):
    m = v['message']
    res = DisputeResolution(int(m['orderId']), m['payoutTo'], int(m['amount']), int(m['nonce']), int(m['deadline']))
    s = make_signer()
    assert s.sign_dispute(res) == v['arbitratorSignature']                      # ECDSA tất định: cùng khóa, cùng digest, cùng chữ ký
    assert s.recover_dispute_signer(res, v['signature']) == v['signer']          # chữ ký của Buyer/Merchant trong vector
    assert s.recover_dispute_signer(res, v['arbitratorSignature']) == v['arbitrator']


def test_recover_changes_when_any_field_changes_and_rejects_garbage():
    v = VECTORS['disputeResolution'][0]
    m = v['message']
    s = make_signer()
    base = DisputeResolution(int(m['orderId']), m['payoutTo'], int(m['amount']), int(m['nonce']), int(m['deadline']))
    for f, val in (('orderId', 9), ('amount', 1), ('nonce', 7), ('deadline', 5)):
        tampered = DisputeResolution(**{**base.__dict__, f: val})
        assert s.recover_dispute_signer(tampered, v['signature']) != v['signer']
    with pytest.raises(ValueError):
        s.recover_dispute_signer(base, '0x1234')


def test_sign_dispute_requires_arbitrator_key():
    with pytest.raises(RuntimeError):
        make_signer(arbitrator_key='').sign_dispute(DisputeResolution(1, ADDR['buyer'], 1, 0, 1))
