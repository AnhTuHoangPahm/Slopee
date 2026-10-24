"""Tuần 7 [B] UC-07 (Dispute Timeout, BR-05) không cần MySQL/Anvil: mốc thời gian, khóa Trọng tài, idempotent, nhật ký, quyền route.

Chuỗi giả `FakeEscrowChain` mô hình đúng `arbitratorForceResolve`: chỉ khi `now >= disputedAt + disputeTimeout`, chỉ khi người KÝ giao dịch
(khôi phục từ raw tx) có ARBITRATOR_ROLE, phát `OrderRefunded|OrderCompleted` rồi `ArbitratorForceResolved`. Phần chạy trên MySQL thật
(Indexer, thông báo, đối soát) ở test/integration_test/test_w3_force_resolve_mysql.py; trên Anvil + contract thật ở test_w7_timeouts_anvil.py.
"""
import threading

import pytest
from flask import Flask

from auth_utils import issue_token
from slopee_web3.adapters.clock import HybridClock
from slopee_web3.adapters.flask_api import container, register_web3
from slopee_web3.adapters.relayer_queue import SingleThreadQueue
from slopee_web3.application.dispute_force_service import DisputeForceResolveService
from slopee_web3.application.relayer_service import RelayerService
from slopee_web3.domain import dispute as dp
from slopee_web3.domain.errors import DomainError, http_status
from slopee_web3.ports.chain_port import ChainTxFailed, ChainUnavailable
from w3_support import ADDR, MemoryDisputeRepo, MemoryDisputeUow, MemoryOutbox, FakeEscrowChain, make_signer

DAY = 86400
BUYER, MERCHANT = ADDR['buyer'], ADDR['merchant1']
OID, CODE, ADMIN = 4242, 'order-force-1', 'admin-1'
AMOUNT = 16_005_000


def code_of(fn, *a, **kw):
    with pytest.raises(DomainError) as e:
        fn(*a, **kw)
    return e.value


# ------------------------------------------------------------------ domain
@pytest.mark.parametrize('timeout', [7 * DAY, 30 * DAY, 90 * DAY])
def test_force_resolve_opens_exactly_at_disputed_at_plus_timeout(timeout):
    disputed_at = 1_800_000_000
    at = dp.force_resolve_at(disputed_at, timeout)
    assert at == disputed_at + timeout
    e = code_of(dp.check_force_resolvable, at - 1, disputed_at, timeout)                  # mốc − 1 giây: còn đóng
    assert e.code == 'FORCE_RESOLVE_TOO_EARLY' and http_status(e.code) == 409
    assert e.extra == {'force_resolve_at': at, 'seconds_remaining': 1}
    assert dp.check_force_resolvable(at, disputed_at, timeout) == at                       # đúng mốc: mở
    assert dp.check_force_resolvable(at + 10 * DAY, disputed_at, timeout) == at            # sau mốc: vẫn mở (không có hạn chót)


@pytest.mark.parametrize('timeout', [7 * DAY, 30 * DAY, 90 * DAY])
@pytest.mark.parametrize('ttl', [60, 3600, 7 * DAY, 10 ** 9])
@pytest.mark.parametrize('offset', [0, 1, 3600, 6 * DAY])
def test_signature_window_always_closes_before_force_resolve_opens(timeout, ttl, offset):
    """R-02: hai đường xử lý không bao giờ cùng hợp lệ. Hạn chữ ký B tính luôn < mốc xử đơn phương, với mọi TTL/thời điểm đề xuất."""
    disputed_at = 1_800_000_000
    deadline = dp.compute_deadline(disputed_at + offset, ttl, disputed_at, timeout)
    assert deadline < dp.force_resolve_at(disputed_at, timeout)


# ------------------------------------------------------------------ hạ tầng test
class SpySigner:
    """Bọc EnvKeySigner thật, ghi lại vai trò đã dùng để ký giao dịch (khóa không rời signer)."""

    def __init__(self, inner):
        self._inner = inner
        self.roles = []

    def sign_transaction(self, role, tx):
        self.roles.append(role)
        return self._inner.sign_transaction(role, tx)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class InlineQueue:
    def run(self, job, timeout=None):
        return job()


class Rig:
    def __init__(self, *, timeout=30 * DAY, state='DISPUTED', signer=None, clock=None, queue=None):
        self.chain = FakeEscrowChain()
        self.outbox, self.commits, self.disputes = MemoryOutbox(), [], MemoryDisputeRepo()
        self.disputes.orders[CODE] = {'order_id': CODE, 'onchain_order_id': OID, 'buyer_user_id': 'u-b', 'merchant_user_id': 'u-m',
                                      'buyer_wallet': BUYER.lower(), 'merchant_wallet': MERCHANT.lower(), 'status': 'DISPUTED',
                                      'amount_raw': AMOUNT, 'token_symbol': 'mUSD', 'fee_bps': 300, 'disputed_at': self.chain.now,
                                      'dispute_timeout': timeout}
        self.chain.orders[OID] = {'state': state, 'buyer': BUYER, 'merchant': MERCHANT, 'token': '0x' + '1' * 40, 'amount': AMOUNT,
                                  'created_at': self.chain.now - 5 * DAY, 'delivered_at': self.chain.now - DAY,
                                  'disputed_at': self.chain.now if state == 'DISPUTED' else 0, 'dispute_timeout': timeout,
                                  'inspection_duration': 3 * DAY, 'fee_bps': 300}
        self.signer = SpySigner(signer or make_signer())
        self.clock = clock or HybridClock(self.chain, system=lambda: self.chain.now)
        self.uow = lambda: MemoryDisputeUow(self.outbox, self.commits, self.disputes)
        self.queue = queue or InlineQueue()
        self.relayer = RelayerService(self.uow, self.chain, self.signer, self.queue, receipt_timeout=1, queue_timeout=5)
        self.svc = DisputeForceResolveService(self.uow, self.chain, self.clock, self.relayer)
        self.disputed_at, self.timeout = self.chain.now, timeout

    def go(self, payout='BUYER', note=None, admin=ADMIN):
        return self.svc.force_resolve(admin, CODE, payout, note)

    def to_boundary(self, delta=0):
        self.chain.advance(self.timeout + delta)

    def events(self):
        return [e['event'] for e in self.chain.logs]


@pytest.fixture
def rig():
    return Rig()


# ------------------------------------------------------------------ thời gian
def test_too_early_sends_nothing_and_says_how_long_is_left(rig):
    rig.chain.advance(rig.timeout - 1)                                   # còn đúng 1 giây
    e = code_of(rig.go)
    assert e.code == 'FORCE_RESOLVE_TOO_EARLY'
    assert e.extra == {'force_resolve_at': rig.disputed_at + rig.timeout, 'seconds_remaining': 1}
    assert rig.chain.sent_txs == [] and rig.outbox.rows == [] and rig.disputes.force_resolutions(CODE) == []
    assert rig.signer.roles == []                                        # không tốn gas, không đụng khóa
    assert rig.chain.orders[OID]['state'] == 'DISPUTED'


@pytest.mark.parametrize('timeout', [7 * DAY, 30 * DAY, 90 * DAY])
@pytest.mark.parametrize('payout,final', [('BUYER', 'REFUNDED'), ('MERCHANT', 'COMPLETED')])
def test_force_resolve_works_at_the_boundary_for_each_dispute_timeout(timeout, payout, final):
    r = Rig(timeout=timeout)
    r.chain.advance(timeout - 1)
    assert code_of(r.go, payout).code == 'FORCE_RESOLVE_TOO_EARLY'
    r.chain.advance(1)                                                   # đúng mốc disputedAt + disputeTimeout
    out = r.go(payout, 'Không bên nào phản hồi')
    assert out['outcome'] == 'SENT' and out['payout_side'] == payout and out['tx_hash'].startswith('0x')
    assert r.chain.orders[OID]['state'] == final
    assert out['force_resolve_at'] == r.disputed_at + timeout and out['amount_raw'] == str(AMOUNT)


def test_clock_ahead_of_the_chain_still_cannot_make_the_contract_accept_early(rig):
    """Đồng hồ máy chủ chạy trước block: dịch vụ tưởng đã tới mốc nhưng contract (block.timestamp) từ chối ⇒ CHAIN_TX_FAILED, không ghi nhật ký."""
    ahead = HybridClock(rig.chain, system=lambda: rig.chain.now + rig.timeout + 60)
    r = Rig(clock=ahead)
    e = code_of(r.go)
    assert e.code == 'CHAIN_TX_FAILED' and http_status(e.code) == 502
    assert r.outbox.rows[0]['kind'] == 'FORCE_RESOLVE' and r.outbox.rows[0]['status'] == 'FAILED'
    assert r.disputes.force_resolutions(CODE) == [] and r.chain.orders[OID]['state'] == 'DISPUTED'


# ------------------------------------------------------------------ khóa Trọng tài, kết quả, nhật ký
def test_transaction_is_sent_from_and_signed_by_the_arbitrator_never_the_shipper(rig):
    rig.to_boundary()
    out = rig.go('MERCHANT')
    assert rig.signer.roles == ['arbitrator']
    assert rig.chain.sent_txs == [('arbitratorForceResolve', OID, ADDR['arbitrator'])]
    assert rig.chain.last_msg_sender == ADDR['arbitrator']
    row = rig.outbox.rows[0]
    assert (row['kind'], row['order_id'], row['status'], row['tx_hash']) == ('FORCE_RESOLVE', CODE, 'CONFIRMED', out['tx_hash'])


def test_the_model_contract_rejects_a_shipper_signed_force_resolve(rig):
    """Chứng minh chuỗi giả bắt được lỗi dùng nhầm khóa (nếu relayer ký bằng SHIPPER_KEY thì contract thật cũng revert onlyRole)."""
    rig.to_boundary()
    with pytest.raises(ChainTxFailed, match='ARBITRATOR_ROLE'):
        rig.chain.send_tx('arbitratorForceResolve', [OID, BUYER], ADDR['shipper'], lambda tx: rig.signer.sign_transaction('shipper', tx))
    assert rig.chain.orders[OID]['state'] == 'DISPUTED'


@pytest.mark.parametrize('payout,final,side,expected_event', [
    ('BUYER', 'REFUNDED', 'BUYER', 'OrderRefunded'), ('MERCHANT', 'COMPLETED', 'MERCHANT', 'OrderCompleted')])
def test_events_and_audit_row_describe_exactly_what_happened(rig, payout, final, side, expected_event):
    rig.to_boundary()
    out = rig.go(payout, '  Cả hai bên không phản hồi sau 30 ngày  ', admin='admin-77')
    assert rig.chain.orders[OID]['state'] == final
    assert rig.events()[-2:] == [expected_event, 'ArbitratorForceResolved']              # đúng thứ tự như contract (Indexer dựa vào đây)
    rows = rig.disputes.force_resolutions(CODE)
    assert len(rows) == 1
    r = rows[0]
    assert (r['admin_user_id'], r['payout_side'], r['amount_raw'], r['onchain_order_id']) == ('admin-77', side, str(AMOUNT), OID)
    assert r['payout_to'] == (BUYER if side == 'BUYER' else MERCHANT).lower()            # địa chỉ chữ thường
    assert r['reason_note'] == 'Cả hai bên không phản hồi sau 30 ngày' and r['tx_hash'] == out['tx_hash'] and r['outbox_id'] == 1


def test_payout_accepts_role_words_or_the_exact_party_address_and_nothing_else(rig):
    rig.to_boundary()
    for bad in (None, '', 'admin', 'arbitrator', ADDR['arbitrator'], ADDR['stranger'], '0x' + '0' * 40, 7, ['buyer']):
        assert code_of(rig.go, bad).code == 'INVALID_PAYOUT', bad
    assert rig.chain.sent_txs == [] and rig.outbox.rows == []
    assert rig.go(BUYER.lower())['payout_side'] == 'BUYER'                              # địa chỉ chữ thường vẫn nhận ra


def test_reason_note_is_validated_before_anything_touches_the_chain(rig):
    rig.to_boundary()
    assert code_of(rig.go, 'BUYER', 'x' * 2001).code == 'INVALID_DISPUTE_NOTE'
    assert code_of(rig.go, 'BUYER', 123).code == 'INVALID_DISPUTE_NOTE'
    assert rig.chain.sent_txs == [] and rig.outbox.rows == []
    assert rig.go('BUYER', '   ')['outcome'] == 'SENT' and rig.disputes.force_resolutions(CODE)[0]['reason_note'] is None


# ------------------------------------------------------------------ trạng thái / idempotent
@pytest.mark.parametrize('state', ['LOCKED', 'DELIVERED'])
def test_only_a_disputed_order_can_be_force_resolved(state):
    r = Rig(state=state)
    r.chain.advance(100 * DAY)
    e = code_of(r.go)
    assert e.code == 'INVALID_STATE' and e.extra == {'chain_state': state}
    assert r.chain.sent_txs == [] and r.outbox.rows == [] and r.disputes.force_resolutions(CODE) == []


def test_unknown_order_and_order_missing_on_chain(rig):
    assert code_of(rig.svc.force_resolve, ADMIN, 'no-such-order', 'BUYER').code == 'ORDER_NOT_FOUND'
    del rig.chain.orders[OID]
    e = code_of(rig.go)
    assert e.code == 'INVALID_STATE' and e.extra == {'chain_state': 'NONE'}


def test_repeat_request_is_idempotent_and_writes_one_audit_row(rig):
    rig.to_boundary()
    first = rig.go('BUYER')
    again = rig.go('BUYER')                                              # lỗi mạng làm Admin bấm lại
    assert first['outcome'] == 'SENT' and again['outcome'] == 'ALREADY_RESOLVED' and again['tx_hash'] is None
    assert len(rig.chain.sent_txs) == 1 and len(rig.outbox.rows) == 1 and len(rig.disputes.force_resolutions(CODE)) == 1


def test_opposite_request_after_resolution_is_rejected_not_silently_accepted(rig):
    rig.to_boundary()
    rig.go('BUYER')                                                      # đã hoàn tiền Buyer
    e = code_of(rig.go, 'MERCHANT')
    assert e.code == 'INVALID_STATE' and e.extra == {'chain_state': 'REFUNDED'}
    assert len(rig.chain.sent_txs) == 1


def test_an_order_already_settled_by_the_two_of_three_route_is_reported_not_resent(rig):
    rig.chain.orders[OID]['state'] = 'COMPLETED'                         # Buyer + Merchant đã ký trước đó
    out = rig.go('MERCHANT')
    assert out['outcome'] == 'ALREADY_RESOLVED' and rig.chain.sent_txs == [] and rig.outbox.rows == []
    assert code_of(rig.go, 'BUYER').code == 'INVALID_STATE'


def test_concurrent_requests_send_exactly_one_transaction():
    q = SingleThreadQueue('force-test')
    r = Rig(queue=q)
    r.to_boundary()
    results, errors, start = [], [], threading.Barrier(4)

    def call():
        start.wait()
        try:
            results.append(r.go('BUYER'))
        except DomainError as e:            # pragma: no cover - không được xảy ra
            errors.append(e.code)

    threads = [threading.Thread(target=call) for _ in range(4)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    q.close()
    assert errors == [] and sorted(x['outcome'] for x in results) == ['ALREADY_RESOLVED'] * 3 + ['SENT']
    assert len(r.chain.sent_txs) == 1 and len(r.disputes.force_resolutions(CODE)) == 1


# ------------------------------------------------------------------ lỗi vận hành
def test_missing_arbitrator_key_is_a_configuration_error_not_a_crash():
    r = Rig(signer=make_signer(arbitrator_key=''))
    r.to_boundary()
    e = code_of(r.go)
    assert e.code == 'WEB3_NOT_CONFIGURED' and 'ARBITRATOR_KEY' in e.message and http_status(e.code) == 503
    assert r.chain.sent_txs == [] and r.outbox.rows == []


def test_chain_down_records_nothing(rig):
    rig.to_boundary()
    rig.chain.available = False
    with pytest.raises(ChainUnavailable):
        rig.go()
    assert rig.outbox.rows == [] and rig.disputes.force_resolutions(CODE) == []


def test_audit_failure_does_not_hide_a_transaction_that_is_already_on_chain(rig, caplog):
    rig.to_boundary()
    rig.disputes.fail_force_audit = True
    with caplog.at_level('ERROR', logger='slopee.web3'):
        out = rig.go('BUYER', 'lý do')
    assert out['outcome'] == 'SENT' and rig.chain.orders[OID]['state'] == 'REFUNDED'
    log = ' '.join(r.getMessage() for r in caplog.records)
    assert 'dispute_force_resolutions' in log and CODE in log and out['tx_hash'] in log        # đủ dữ liệu để dựng lại bằng tay


def test_attempt_is_logged_as_a_warning_with_the_admin_identity(rig, caplog):
    rig.to_boundary()
    with caplog.at_level('WARNING', logger='slopee.web3'):
        rig.go('MERCHANT', admin='admin-9')
    msgs = [r.getMessage() for r in caplog.records if r.levelname == 'WARNING']
    assert any('admin=admin-9' in m and CODE in m and 'MERCHANT' in m for m in msgs)


# ------------------------------------------------------------------ route
class FakeForce:
    def __init__(self):
        self.calls, self.raises = [], None

    def force_resolve(self, admin_id, code, payout_to, note):
        self.calls.append((admin_id, code, payout_to, note))
        if self.raises:
            raise self.raises
        return {'order_id': code, 'outcome': 'SENT', 'tx_hash': '0x' + 'ab' * 32}


class FakeContainer:
    def __init__(self, svc):
        self.svc = svc

    def dispute_force_service(self):
        return self.svc


@pytest.fixture
def fsvc():
    s = FakeForce()
    container.set_container(FakeContainer(s))
    yield s
    container.set_container(None)


@pytest.fixture
def client(fsvc):
    app = Flask(__name__)
    register_web3(app)
    return app.test_client()


def H(uid='u1', role='admin'):
    return {'Authorization': f'Bearer {issue_token(uid, role)}'}


URL = '/api/admin/disputes/o1/force-resolve'


def test_route_requires_a_token(client, fsvc):
    assert client.post(URL, json={'payout_to': 'BUYER'}).status_code == 401 and fsvc.calls == []


@pytest.mark.parametrize('role', ['user', 'seller', 'shipper'])
def test_route_is_admin_only(client, fsvc, role):
    assert client.post(URL, json={'payout_to': 'BUYER'}, headers=H(role=role)).status_code == 403 and fsvc.calls == []


def test_route_takes_identity_from_the_token_and_forwards_the_body(client, fsvc):
    r = client.post(URL, json={'payout_to': 'MERCHANT', 'reason_note': 'quá hạn', 'admin_id': 'evil', 'userId': 'evil'}, headers=H('admin-5'))
    assert r.status_code == 200 and r.get_json()['outcome'] == 'SENT'
    assert fsvc.calls == [('admin-5', 'o1', 'MERCHANT', 'quá hạn')]


def test_route_maps_the_early_error_to_409_with_the_countdown(client, fsvc):
    fsvc.raises = dp.DomainError('FORCE_RESOLVE_TOO_EARLY', 'Chưa tới thời điểm.', {'force_resolve_at': 10, 'seconds_remaining': 3})
    r = client.post(URL, json={'payout_to': 'BUYER'}, headers=H())
    assert r.status_code == 409
    assert r.get_json() == {'code': 'FORCE_RESOLVE_TOO_EARLY', 'message': 'Chưa tới thời điểm.', 'force_resolve_at': 10, 'seconds_remaining': 3}


def test_route_rejects_a_non_object_body_before_calling_the_service(client, fsvc):
    r = client.post(URL, data='[1,2]', content_type='application/json', headers=H())
    assert r.status_code == 400 and fsvc.calls == []
