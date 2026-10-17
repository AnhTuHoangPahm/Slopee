"""Relayer Tuần 5 (UC-03, SDD 5.3h, DD-06): hàng đợi một luồng, idempotent, ghi tx_outbox, không đụng nonce.

Không cần MySQL/Anvil: dùng chuỗi giả + nhật ký giao dịch giả. Phần chạy trên MySQL thật nằm ở
test/integration_test/test_w3_relayer_mysql.py; phần chạy trên Anvil thật là test `anvil` cùng tệp đó.
"""
import threading
import time

import pytest
from eth_account import Account

from slopee_web3.adapters.relayer_queue import SingleThreadQueue
from slopee_web3.application.relayer_service import RelayerService
from slopee_web3.domain.errors import DomainError, http_status
from slopee_web3.ports.chain_port import ChainUnavailable
from w3_support import ADDR, CHAIN_ID, KEYS, RelayChain, make_signer


class MemoryOutbox:
    """Bảng tx_outbox trong bộ nhớ, đúng máy trạng thái của MySqlOutboxRepo (chuyển có điều kiện trạng thái cũ)."""

    def __init__(self):
        self.rows = []
        self.lock = threading.Lock()

    def insert(self, kind, order_id):
        with self.lock:
            self.rows.append({'id': len(self.rows) + 1, 'kind': kind, 'order_id': order_id, 'tx_hash': None,
                              'status': 'PENDING', 'error': None})
            return len(self.rows)

    def _row(self, oid):
        return self.rows[oid - 1]

    def mark_sent(self, oid, tx_hash):
        r = self._row(oid)
        if r['status'] == 'PENDING':
            r.update(status='SENT', tx_hash=tx_hash)

    def mark_confirmed(self, oid):
        r = self._row(oid)
        if r['status'] == 'SENT':
            r['status'] = 'CONFIRMED'

    def mark_failed(self, oid, error):
        r = self._row(oid)
        if r['status'] in ('PENDING', 'SENT'):
            r.update(status='FAILED', error=str(error))

    def recent_for_order(self, order_id, limit=20):
        return [r for r in reversed(self.rows) if r['order_id'] == order_id][:limit]


class MemoryUow:
    def __init__(self, outbox, commits):
        self.outbox, self._commits = outbox, commits

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def commit(self):
        self._commits.append(1)


@pytest.fixture
def rig():
    outbox, commits = MemoryOutbox(), []
    chain = RelayChain()
    queue = SingleThreadQueue('test-relayer')
    svc = RelayerService(lambda: MemoryUow(outbox, commits), chain, make_signer(), queue, receipt_timeout=1, queue_timeout=5)
    yield svc, chain, outbox, commits, queue
    queue.close()


def test_confirm_delivery_happy_path_logs_pending_sent_confirmed(rig):
    svc, chain, outbox, commits, _ = rig
    chain.states[101] = 'LOCKED'
    out = svc.confirm_delivery('order-a', 101)
    assert out['outcome'] == 'SENT' and out['tx_hash'].startswith('0x') and out['outbox_id'] == 1
    fn, args, sender, nonce = chain.sent[0]
    assert (fn, args, sender) == ('confirmDelivery', [101], ADDR['shipper'])          # đúng hàm, đúng đơn, đúng khóa shipper
    row = outbox.rows[0]
    assert (row['kind'], row['order_id'], row['status'], row['tx_hash']) == ('DELIVER', 'order-a', 'CONFIRMED', out['tx_hash'])
    assert len(commits) == 3                                                          # PENDING, SENT, CONFIRMED mỗi bước một commit


def test_already_delivered_is_idempotent_and_sends_nothing(rig):
    svc, chain, outbox, _, _ = rig
    chain.states[5] = 'DELIVERED'
    assert svc.confirm_delivery('o', 5) == {'outcome': 'ALREADY_DELIVERED', 'tx_hash': None, 'outbox_id': None}
    assert chain.sent == [] and outbox.rows == []


@pytest.mark.parametrize('state', ['NONE', 'DISPUTED', 'COMPLETED', 'REFUNDED'])
def test_wrong_state_is_invalid_state_409(rig, state):
    svc, chain, outbox, _, _ = rig
    chain.states[9] = state
    with pytest.raises(DomainError) as e:
        svc.confirm_delivery('o', 9)
    assert e.value.code == 'INVALID_STATE' and http_status(e.value.code) == 409 and e.value.extra == {'chain_state': state}
    assert chain.sent == [] and outbox.rows == []


def test_contract_revert_marks_failed_and_raises_chain_tx_failed(rig):
    svc, chain, outbox, _, _ = rig
    chain.states[1] = 'LOCKED'
    chain.revert = True
    with pytest.raises(DomainError) as e:
        svc.confirm_delivery('o', 1)
    assert e.value.code == 'CHAIN_TX_FAILED' and http_status('CHAIN_TX_FAILED') == 502
    assert outbox.rows[0]['status'] == 'FAILED' and 'revert' in outbox.rows[0]['error']
    assert 'Invalid state' not in e.value.message           # chi tiết kỹ thuật chỉ ở nhật ký, không trả cho người dùng


def test_rpc_down_at_state_check_raises_chain_unavailable_without_outbox(rig):
    svc, chain, outbox, _, _ = rig
    chain.down = True
    with pytest.raises(ChainUnavailable):
        svc.confirm_delivery('o', 1)
    assert outbox.rows == []


def test_rpc_down_at_send_marks_failed_and_reraises(rig):
    svc, chain, outbox, _, _ = rig
    chain.states[1] = 'LOCKED'
    real = chain.send_tx

    def flaky(*a, **kw):
        chain.down = True
        return real(*a, **kw)
    chain.send_tx = flaky
    with pytest.raises(ChainUnavailable):
        svc.confirm_delivery('o', 1)
    assert outbox.rows[0]['status'] == 'FAILED' and 'ChainUnavailable' in outbox.rows[0]['error']


def test_receipt_timeout_keeps_sent_not_failed(rig):
    """Không biết giao dịch đã được đào chưa => KHÔNG đánh FAILED (sẽ sai nếu nó thật sự đã vào chuỗi)."""
    svc, chain, outbox, _, _ = rig
    chain.states[1] = 'LOCKED'
    chain.receipt_timeout = True
    with pytest.raises(ChainUnavailable):
        svc.confirm_delivery('o', 1)
    assert outbox.rows[0]['status'] == 'SENT' and outbox.rows[0]['tx_hash']
    # thử lại: giao dịch đã được đào (chain.states = DELIVERED do mine_on_send) => idempotent, không gửi lần hai
    assert svc.confirm_delivery('o', 1)['outcome'] == 'ALREADY_DELIVERED'
    assert len(chain.sent) == 1


def test_receipt_status_zero_marks_failed(rig):
    svc, chain, outbox, _, _ = rig
    chain.states[1] = 'LOCKED'
    chain.receipt_status = 0
    with pytest.raises(DomainError) as e:
        svc.confirm_delivery('o', 1)
    assert e.value.code == 'CHAIN_TX_FAILED'
    assert outbox.rows[0]['status'] == 'FAILED' and 'status=0' in outbox.rows[0]['error']


def test_two_clicks_on_same_order_send_exactly_one_transaction(rig):
    """Double-click của Shipper: cả hai yêu cầu cùng thấy LOCKED ở lần kiểm đầu; kiểm lại trong hàng đợi chặn lần hai."""
    svc, chain, outbox, _, _ = rig
    chain.states[1] = 'LOCKED'
    chain.send_delay = 0.15
    results, errors = [], []

    def click():
        try:
            results.append(svc.confirm_delivery('o', 1)['outcome'])
        except Exception as e:          # noqa: BLE001 - thu lỗi để assert
            errors.append(e)
    ts = [threading.Thread(target=click) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors
    assert sorted(results) == ['ALREADY_DELIVERED', 'SENT']
    assert len(chain.sent) == 1 and len(outbox.rows) == 1


def test_concurrent_different_orders_never_overlap_and_nonces_are_sequential(rig):
    """DD-06: nhiều Shipper bấm cùng lúc, send_tx chỉ chạy một lần tại một thời điểm và nonce tăng liên tục 0..n-1."""
    svc, chain, outbox, _, _ = rig
    n = 8
    for i in range(n):
        chain.states[100 + i] = 'LOCKED'
    chain.send_delay = 0.02
    errors = []

    def click(i):
        try:
            svc.confirm_delivery(f'o{i}', 100 + i)
        except Exception as e:          # noqa: BLE001
            errors.append(e)
    ts = [threading.Thread(target=click, args=(i,)) for i in range(n)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors
    assert chain.max_in_flight == 1
    assert sorted(s[3] for s in chain.sent) == list(range(n))
    assert {s[1][0] for s in chain.sent} == {100 + i for i in range(n)}
    assert all(r['status'] == 'CONFIRMED' for r in outbox.rows) and len(outbox.rows) == n


def test_missing_shipper_key_is_web3_not_configured(rig):
    _, chain, outbox, commits, queue = rig
    no_shipper = RelayerService(lambda: MemoryUow(outbox, commits), chain, make_signer(shipper_key=''), queue)
    chain.states[1] = 'LOCKED'
    with pytest.raises(DomainError) as e:
        no_shipper.confirm_delivery('o', 1)
    assert e.value.code == 'WEB3_NOT_CONFIGURED' and chain.sent == []


def test_queue_wait_timeout_maps_to_chain_unavailable_and_job_still_completes():
    outbox, commits = MemoryOutbox(), []
    chain, queue = RelayChain(), SingleThreadQueue('slow')
    chain.states[1] = 'LOCKED'
    chain.send_delay = 0.4
    svc = RelayerService(lambda: MemoryUow(outbox, commits), chain, make_signer(), queue, queue_timeout=0.05)
    try:
        with pytest.raises(DomainError) as e:
            svc.confirm_delivery('o', 1)
        assert e.value.code == 'CHAIN_UNAVAILABLE'
        time.sleep(0.8)                  # job vẫn chạy tiếp ở nền: không mất giao dịch
        assert len(chain.sent) == 1 and outbox.rows[0]['status'] == 'CONFIRMED'
    finally:
        queue.close()


def test_queue_survives_a_failing_job_and_runs_jobs_in_order():
    q = SingleThreadQueue('order')
    try:
        with pytest.raises(ZeroDivisionError):
            q.run(lambda: 1 / 0)
        order = []
        threads = []
        for i in range(5):
            t = threading.Thread(target=lambda i=i: q.run(lambda: order.append(i) or time.sleep(0.01)))
            t.start()
            time.sleep(0.005)
            threads.append(t)
        [t.join() for t in threads]
        assert order == [0, 1, 2, 3, 4]
        assert q.run(lambda: 'alive') == 'alive'
    finally:
        q.close()


def test_outbox_write_failure_does_not_mask_original_error(rig):
    svc, chain, outbox, _, _ = rig
    chain.states[1] = 'LOCKED'
    chain.revert = True
    outbox.mark_failed = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('db down'))
    with pytest.raises(DomainError) as e:
        svc.confirm_delivery('o', 1)
    assert e.value.code == 'CHAIN_TX_FAILED'          # lỗi gốc, không phải 'db down'


# ------------------------------------------------------------------ signer.sign_transaction
def test_sign_transaction_is_signed_by_role_key_and_does_not_leak_it():
    s = make_signer()
    tx = {'to': ADDR['merchant1'], 'value': 0, 'gas': 21000, 'gasPrice': 10 ** 9, 'nonce': 3, 'chainId': CHAIN_ID, 'data': b''}
    raw = s.sign_transaction('shipper', tx)
    assert isinstance(raw, bytes)
    from eth_account import Account as A
    assert A.recover_transaction(raw) == ADDR['shipper']                 # đúng khóa shipper, không phải quote_signer
    assert KEYS['shipper'][2:] not in repr(raw.hex()) and not hasattr(s, 'private_key')


def test_sign_transaction_without_role_key_raises_without_echoing_keys():
    s = make_signer(shipper_key='')
    with pytest.raises(RuntimeError) as e:
        s.sign_transaction('shipper', {})
    assert 'shipper' in str(e.value) and KEYS['quote_signer'][2:] not in str(e.value)
