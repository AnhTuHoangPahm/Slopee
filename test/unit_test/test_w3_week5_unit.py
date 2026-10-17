"""Tuần 5 [B] (không cần MySQL/Anvil): quy tắc thời hạn, đối soát thuần, Scheduler, release qua relayer, khóa liên tiến trình, route."""
import threading

import pytest
from flask import Flask

from auth_utils import issue_token
from slopee_web3.adapters.advisory_lock import MySqlAdvisoryLock
from slopee_web3.adapters.flask_api import container, register_web3
from slopee_web3.adapters.relayer_queue import SingleThreadQueue
from slopee_web3.adapters.scheduler import Job, Scheduler
from slopee_web3.application.relayer_service import RelayerService
from slopee_web3.domain import reconcile as rc
from slopee_web3.domain import release as rl
from slopee_web3.domain.errors import DomainError
from slopee_web3.ports.chain_port import ChainUnavailable
from test_w3_relayer import MemoryOutbox, MemoryUow
from w3_support import ADDR, RelayChain, make_signer


# ------------------------------------------------------------------ domain/release
def test_release_deadlines_match_contract_formulas_at_the_boundary():
    assert rl.DELIVERY_TIMEOUT_SECONDS == 14 * 86400                      # = SlopeeEscrowMaster.DELIVERY_TIMEOUT
    assert rl.inspection_ends_at(1000, 3600) == 4600
    assert not rl.release_due(1000, 3600, 4599) and rl.release_due(1000, 3600, 4600)          # >=, như `block.timestamp >= ...`
    assert not rl.delivery_timeout_due(1000, 1000 + 14 * 86400 - 1) and rl.delivery_timeout_due(1000, 1000 + 14 * 86400)
    assert rl.delivery_timeout_at(5) == 5 + 14 * 86400


def test_quote_expiry_needs_deadline_plus_grace_to_be_strictly_passed():
    assert not rl.quote_expired(1000, 1000 + rl.QUOTE_EXPIRY_GRACE_SECONDS)
    assert rl.quote_expired(1000, 1000 + rl.QUOTE_EXPIRY_GRACE_SECONDS + 1)
    assert not rl.quote_expired(1000, 1100, grace=100) and rl.quote_expired(1000, 1101, grace=100)


# ------------------------------------------------------------------ domain/reconcile
def test_reconcile_token_sums_exactly_and_reports_direction_of_difference():
    big = 10 ** 30                                                          # vượt 2^53 và 2^64: không float
    ok = rc.reconcile_token('0xabc', big, 3, 7, big + 7)
    assert ok.ok and ok.diff_raw == 0 and ok.expected_raw == big + 7
    assert rc.reconcile_token('0xabc', 100, 1, 0, 90).diff_raw == -10      # contract THIẾU tiền
    assert rc.reconcile_token('0xabc', 100, 1, 0, 105).diff_raw == 5        # contract DƯ tiền
    d = ok.as_dict()
    assert d['balance_raw'] == str(big + 7) and all(isinstance(d[k], str) for k in ('open_orders_raw', 'expected_raw', 'diff_raw'))


def test_token_key_normalises_eth_and_case():
    assert rc.token_key(None) == 'ETH' and rc.token_key('0x' + '0' * 40) == 'ETH'
    assert rc.token_key('0xAbC' + '0' * 37) == ('0xabc' + '0' * 37)
    assert rc.OPEN_STATES == ('LOCKED', 'DELIVERED', 'DISPUTED')


# ------------------------------------------------------------------ Scheduler
class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_scheduler_runs_each_job_on_its_own_interval():
    clock, calls = Clock(), []
    sch = Scheduler([Job('fast', 10, lambda: calls.append('fast')), Job('slow', 60, lambda: calls.append('slow'))], clock=clock)
    sch.run_due()
    assert calls == ['fast', 'slow']                                        # lần đầu chạy ngay
    clock.t = 9
    sch.run_due()
    assert calls == ['fast', 'slow']
    clock.t = 10
    sch.run_due()
    assert calls == ['fast', 'slow', 'fast']
    clock.t = 60
    sch.run_due()
    assert calls[-2:] == ['fast', 'slow']


def test_scheduler_isolates_failures_and_treats_rpc_loss_as_warning():
    ran = []

    def boom():
        raise RuntimeError('lỗi tác vụ')

    def rpc():
        raise ChainUnavailable('down')
    sch = Scheduler([Job('boom', 5, boom), Job('rpc', 5, rpc), Job('ok', 5, lambda: ran.append(1) or {'n': 1})], clock=Clock())
    out = sch.run_due()
    assert out == {'boom': {'error': 'RuntimeError'}, 'rpc': {'error': 'chain_unavailable'}, 'ok': {'n': 1}}
    assert ran == [1]                                                       # tác vụ sau vẫn chạy


def test_scheduler_force_and_run_forever_stop_condition():
    clock, calls = Clock(), []
    sch = Scheduler([Job('j', 1000, lambda: calls.append(1))], clock=clock, sleep=lambda s: None)
    sch.run_due()
    assert sch.run_due() == {} and sch.run_due(force=True) == {'j': None}
    n = {'i': 0}

    def stop():
        n['i'] += 1
        return n['i'] > 3
    sch.run_forever(stop=stop)
    assert n['i'] == 4


# ------------------------------------------------------------------ release_after_inspection (RelayerService của A, mở rộng bởi B)
class ReleaseChain(RelayChain):
    def __init__(self):
        super().__init__()
        self.mine_on_send = False

    def send_tx(self, fn, args, sender, sign):
        h = super().send_tx(fn, args, sender, sign)
        self.states[int(args[0])] = 'COMPLETED' if fn == 'releaseAfterInspection' else 'DELIVERED'
        return h


@pytest.fixture
def rig():
    outbox, commits, guard_log = MemoryOutbox(), [], []
    chain = ReleaseChain()
    queue = SingleThreadQueue('week5-unit')

    class Guard:
        def __call__(self):
            return self

        def __enter__(self):
            guard_log.append(('enter', threading.current_thread().name))

        def __exit__(self, *a):
            guard_log.append(('exit', threading.current_thread().name))
    svc = RelayerService(lambda: MemoryUow(outbox, commits), chain, make_signer(), queue, receipt_timeout=1, queue_timeout=5,
                         job_guard=Guard())
    yield svc, chain, outbox, guard_log
    queue.close()


def test_release_after_inspection_sends_and_logs_release_kind(rig):
    svc, chain, outbox, _ = rig
    chain.states[7] = 'DELIVERED'
    out = svc.release_after_inspection('ord-1', 7)
    assert out['outcome'] == 'SENT' and out['tx_hash']
    assert chain.sent[0][:3] == ('releaseAfterInspection', [7], ADDR['shipper'])
    assert (outbox.rows[0]['kind'], outbox.rows[0]['status']) == ('RELEASE', 'CONFIRMED')


def test_release_is_idempotent_and_rejects_wrong_states(rig):
    svc, chain, outbox, _ = rig
    chain.states[7] = 'COMPLETED'
    assert svc.release_after_inspection('o', 7) == {'outcome': 'ALREADY_COMPLETED', 'tx_hash': None, 'outbox_id': None}
    for bad in ('LOCKED', 'DISPUTED', 'REFUNDED', 'NONE'):
        chain.states[8] = bad
        with pytest.raises(DomainError) as e:
            svc.release_after_inspection('o', 8)
        assert e.value.code == 'INVALID_STATE' and e.value.extra['chain_state'] == bad
    assert chain.sent == [] and outbox.rows == []                           # không tốn gas, không ghi outbox


def test_release_revert_is_chain_tx_failed_and_outbox_failed(rig):
    svc, chain, outbox, _ = rig
    chain.states[7] = 'DELIVERED'
    chain.revert = True
    with pytest.raises(DomainError) as e:
        svc.release_after_inspection('o', 7)
    assert e.value.code == 'CHAIN_TX_FAILED' and 'giải ngân' in e.value.message
    assert outbox.rows[0]['status'] == 'FAILED' and 'revert' in outbox.rows[0]['error']


def test_job_guard_wraps_each_sending_job_inside_the_queue_thread_and_skips_noops(rig):
    svc, chain, _, guard_log = rig
    chain.states[1] = 'LOCKED'
    svc.confirm_delivery('a', 1)
    chain.states[2] = 'DELIVERED'
    svc.release_after_inspection('b', 2)
    assert [g[0] for g in guard_log] == ['enter', 'exit', 'enter', 'exit']
    assert {g[1] for g in guard_log} == {'week5-unit'}                      # khóa giữ TRONG luồng hàng đợi, không phải luồng gọi
    guard_log.clear()
    svc.confirm_delivery('a', 1)                                            # đã DELIVERED: trả sớm, không cần khóa
    assert guard_log == []


def test_guard_failure_means_nothing_is_sent():
    outbox, chain = MemoryOutbox(), RelayChain()
    chain.states[1] = 'LOCKED'

    def busy():
        raise ChainUnavailable('Relayer đang bận ở tiến trình khác')
    q = SingleThreadQueue('guard-fail')
    try:
        svc = RelayerService(lambda: MemoryUow(outbox, []), chain, make_signer(), q, receipt_timeout=1, queue_timeout=5,
                             job_guard=busy)
        with pytest.raises(ChainUnavailable):
            svc.confirm_delivery('a', 1)
    finally:
        q.close()
    assert chain.sent == [] and outbox.rows == []


# ------------------------------------------------------------------ khóa liên tiến trình
class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def execute(self, sql, params=()):
        self.conn.log.append((sql.split('(')[0].strip(), params))

    def fetchone(self):
        return {'got': self.conn.got}


class FakeConn:
    def __init__(self, got):
        self.got, self.log, self.closed = got, [], False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


def test_advisory_lock_acquires_releases_and_always_closes_connection():
    conn = FakeConn(1)
    with MySqlAdvisoryLock(lambda: conn, name='x', timeout=7)():
        assert [c[0] for c in conn.log] == ['SELECT GET_LOCK'] and conn.log[0][1] == ('x', 7)
    assert [c[0] for c in conn.log] == ['SELECT GET_LOCK', 'SELECT RELEASE_LOCK'] and conn.closed


def test_advisory_lock_releases_even_if_job_raises_and_signals_busy_on_timeout():
    conn = FakeConn(1)
    with pytest.raises(ValueError):
        with MySqlAdvisoryLock(lambda: conn)():
            raise ValueError('x')
    assert conn.log[-1][0] == 'SELECT RELEASE_LOCK' and conn.closed
    busy = FakeConn(0)
    with pytest.raises(ChainUnavailable):
        with MySqlAdvisoryLock(lambda: busy)():
            pytest.fail('không được vào khi không có khóa')
    assert busy.closed and all(c[0] != 'SELECT RELEASE_LOCK' for c in busy.log)


# ------------------------------------------------------------------ route: ma trận quyền + ánh xạ lỗi
class Svc:
    def __init__(self):
        self.calls, self.raises = [], None

    def _do(self, name, *a, result=None):
        self.calls.append((name, a))
        if self.raises:
            raise self.raises
        return result if result is not None else {'ok': True}

    def list_orders(self, uid): return self._do('list_orders', uid, result={'orders': []})
    def deliver(self, uid, code): return self._do('deliver', uid, code, result={'order_id': code, 'outcome': 'SENT', 'tx_hash': '0x1'})
    def assign(self, admin, code, shipper): return self._do('assign', admin, code, shipper)
    def run(self, deep=False): return self._do('run', deep, result={'ok': True, 'tokens': []})
    def list_for_user(self, uid): return self._do('notes', uid, result={'notifications': []})


class FakeContainer:
    def __init__(self, svc):
        self.svc = svc

    def shipper_service(self): return self.svc
    def reconcile_service(self): return self.svc
    def notification_service(self): return self.svc


@pytest.fixture
def svc():
    s = Svc()
    container.set_container(FakeContainer(s))
    yield s
    container.set_container(None)


@pytest.fixture
def client(svc):
    app = Flask(__name__)
    register_web3(app)
    return app.test_client()


def H(uid='u1', role='shipper'):
    return {'Authorization': f'Bearer {issue_token(uid, role)}'}


SHIPPER_ROUTES = [('GET', '/api/shipper/orders', None), ('POST', '/api/shipper/orders/o1/deliver', {})]
ADMIN_ROUTES = [('GET', '/api/admin/reconcile', None), ('PUT', '/api/admin/orders/o1/shipper', {'shipper_user_id': 's1'})]


@pytest.mark.parametrize('method,path,body', SHIPPER_ROUTES + ADMIN_ROUTES + [('GET', '/api/notifications', None)])
def test_every_week5_route_requires_a_token(client, svc, method, path, body):
    r = client.open(path, method=method, json=body)
    assert r.status_code == 401 and r.get_json()['code'] == 'auth_required' and svc.calls == []


@pytest.mark.parametrize('method,path,body', SHIPPER_ROUTES)
@pytest.mark.parametrize('role', ['user', 'seller', 'admin'])
def test_shipper_gateway_is_for_shippers_only(client, svc, method, path, body, role):
    r = client.open(path, method=method, json=body, headers=H(role=role))
    assert r.status_code == 403 and r.get_json()['code'] == 'forbidden' and svc.calls == []


@pytest.mark.parametrize('method,path,body', ADMIN_ROUTES)
@pytest.mark.parametrize('role', ['user', 'seller', 'shipper'])
def test_reconcile_and_assignment_are_admin_only(client, svc, method, path, body, role):
    r = client.open(path, method=method, json=body, headers=H(role=role))
    assert r.status_code == 403 and svc.calls == []


def test_identity_comes_from_token_not_from_body_or_query(client, svc):
    r = client.post('/api/shipper/orders/ord-9/deliver', json={'shipper_user_id': 'evil', 'userId': 'evil'}, headers=H('real-shipper'))
    assert r.status_code == 200 and r.get_json()['outcome'] == 'SENT'
    assert svc.calls == [('deliver', ('real-shipper', 'ord-9'))]
    client.get('/api/shipper/orders?userId=evil', headers=H('real-shipper'))
    assert svc.calls[-1] == ('list_orders', ('real-shipper',))
    client.put('/api/admin/orders/o1/shipper', json={'shipper_user_id': 's1', 'assigned_by': 'evil'}, headers=H('adm', 'admin'))
    assert svc.calls[-1] == ('assign', ('adm', 'o1', 's1'))                 # người gán lấy từ token
    client.get('/api/notifications?user_id=evil', headers=H('me', 'user'))
    assert svc.calls[-1] == ('notes', ('me',))


def test_reconcile_deep_flag_and_assignment_validation(client, svc):
    client.get('/api/admin/reconcile', headers=H('a', 'admin'))
    client.get('/api/admin/reconcile?deep=1', headers=H('a', 'admin'))
    client.get('/api/admin/reconcile?deep=nope', headers=H('a', 'admin'))
    assert [c[1] for c in svc.calls] == [(False,), (True,), (False,)]
    svc.calls.clear()
    for body in ({}, {'shipper_user_id': ''}, {'shipper_user_id': 'x' * 37}, {'shipper_user_id': 5}):
        r = client.put('/api/admin/orders/o1/shipper', json=body, headers=H('a', 'admin'))
        assert r.status_code == 400, body
    assert svc.calls == []


@pytest.mark.parametrize('code,status', [('ORDER_NOT_FOUND', 404), ('INVALID_STATE', 409), ('CHAIN_TX_FAILED', 502),
                                         ('INVALID_SHIPPER', 422), ('WEB3_NOT_CONFIGURED', 503)])
def test_domain_errors_map_to_http_with_vietnamese_message(client, svc, code, status):
    svc.raises = DomainError(code, 'Thông báo tiếng Việt', {'status': 'X'})
    r = client.post('/api/shipper/orders/o1/deliver', headers=H())
    body = r.get_json()
    assert r.status_code == status and body['code'] == code and body['message'] == 'Thông báo tiếng Việt' and body['status'] == 'X'


def test_rpc_down_is_503_chain_unavailable(client, svc):
    svc.raises = ChainUnavailable('Connection refused: http://127.0.0.1:8545')
    r = client.post('/api/shipper/orders/o1/deliver', headers=H())
    assert r.status_code == 503 and r.get_json()['code'] == 'CHAIN_UNAVAILABLE' and '127.0.0.1' not in r.get_data(as_text=True)
