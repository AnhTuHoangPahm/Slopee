"""Relayer Tuần 5 trên MySQL THẬT (I-05 phần relayer): `tx_outbox` ghi đúng máy trạng thái, bền khi lỗi, đua hai yêu cầu.

Chuỗi là RelayChain giả (không cần Anvil); đoạn chạy contract thật là test `anvil` ở cuối tệp (tự skip nếu không có RPC).
"""
import os
import threading
import uuid

import pytest

from slopee_web3.adapters.mysql_repos import MySqlUnitOfWork
from slopee_web3.adapters.relayer_queue import SingleThreadQueue
from slopee_web3.application.relayer_service import RelayerService
from slopee_web3.domain.errors import DomainError
from w3_support import ADDR, RelayChain, connect, make_signer

pytestmark = pytest.mark.mysql


@pytest.fixture
def rig(mysql_db):
    conn = connect()
    conn.autocommit(True)
    conn.cursor().execute("DELETE FROM tx_outbox")
    conn.close()
    chain, queue = RelayChain(), SingleThreadQueue('it-relayer')
    svc = RelayerService(lambda: MySqlUnitOfWork(connect), chain, make_signer(), queue, receipt_timeout=1, queue_timeout=10)
    yield svc, chain
    queue.close()


def _rows(order_id=None):
    conn = connect()
    try:
        with conn.cursor() as cur:
            if order_id:
                cur.execute("SELECT kind, order_id, tx_hash, status, error FROM tx_outbox WHERE order_id=%s ORDER BY id", (order_id,))
            else:
                cur.execute("SELECT kind, order_id, tx_hash, status, error FROM tx_outbox ORDER BY id")
            return list(cur.fetchall())
    finally:
        conn.close()


def test_happy_path_persists_confirmed_row_with_tx_hash(rig):
    svc, chain = rig
    chain.states[301] = 'LOCKED'
    oid = str(uuid.uuid4())
    out = svc.confirm_delivery(oid, 301)
    rows = _rows(oid)
    assert out['outcome'] == 'SENT' and len(rows) == 1
    assert (rows[0]['kind'], rows[0]['status'], rows[0]['tx_hash'], rows[0]['error']) == ('DELIVER', 'CONFIRMED', out['tx_hash'], None)


def test_failed_row_survives_and_keeps_error_text(rig):
    """Commit riêng từng bước: dòng FAILED vẫn còn trong DB dù service ném lỗi cho người gọi."""
    svc, chain = rig
    chain.states[302] = 'LOCKED'
    chain.revert = True
    oid = str(uuid.uuid4())
    with pytest.raises(DomainError):
        svc.confirm_delivery(oid, 302)
    rows = _rows(oid)
    assert len(rows) == 1 and rows[0]['status'] == 'FAILED' and 'revert' in rows[0]['error'] and rows[0]['tx_hash'] is None


def test_receipt_timeout_leaves_sent_row_with_hash(rig):
    svc, chain = rig
    chain.states[303] = 'LOCKED'
    chain.receipt_timeout = True
    oid = str(uuid.uuid4())
    with pytest.raises(Exception):
        svc.confirm_delivery(oid, 303)
    rows = _rows(oid)
    assert rows[0]['status'] == 'SENT' and rows[0]['tx_hash'] and rows[0]['error'] is None


def test_idempotent_second_call_adds_no_row(rig):
    svc, chain = rig
    chain.states[304] = 'LOCKED'
    oid = str(uuid.uuid4())
    svc.confirm_delivery(oid, 304)
    assert svc.confirm_delivery(oid, 304)['outcome'] == 'ALREADY_DELIVERED'
    assert len(_rows(oid)) == 1 and len(chain.sent) == 1


def test_race_two_clicks_one_row_one_tx(rig):
    svc, chain = rig
    chain.states[305] = 'LOCKED'
    chain.send_delay = 0.15
    oid = str(uuid.uuid4())
    res = []
    ts = [threading.Thread(target=lambda: res.append(svc.confirm_delivery(oid, 305)['outcome'])) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(res) == ['ALREADY_DELIVERED', 'SENT'] and len(_rows(oid)) == 1 and len(chain.sent) == 1


def test_long_error_is_truncated_not_rejected(rig):
    from slopee_web3.adapters.mysql_repos import MySqlOutboxRepo
    with MySqlUnitOfWork(connect) as uow:
        i = uow.outbox.insert('DELIVER', 'trunc-order')
        uow.outbox.mark_failed(i, 'x' * 10_000)
        uow.commit()
    err = _rows('trunc-order')[0]['error']
    assert len(err) == MySqlOutboxRepo.MAX_ERROR


def test_outbox_transitions_are_state_conditional(rig):
    """CONFIRMED không bị ghi đè thành FAILED/SENT bởi một lần gọi muộn (UPDATE có điều kiện trạng thái cũ, SDD 7.5)."""
    with MySqlUnitOfWork(connect) as uow:
        i = uow.outbox.insert('DELIVER', 'cond-order')
        uow.outbox.mark_sent(i, '0x' + 'ab' * 32)
        uow.outbox.mark_confirmed(i)
        uow.outbox.mark_failed(i, 'late error')
        uow.outbox.mark_sent(i, '0x' + 'cd' * 32)
        uow.commit()
    r = _rows('cond-order')[0]
    assert r['status'] == 'CONFIRMED' and r['tx_hash'] == '0x' + 'ab' * 32 and r['error'] is None


def test_recent_for_order_newest_first(rig):
    with MySqlUnitOfWork(connect) as uow:
        a = uow.outbox.insert('DELIVER', 'hist-order')
        b = uow.outbox.insert('DELIVER', 'hist-order')
        uow.commit()
        got = uow.outbox.recent_for_order('hist-order')
    assert [g['id'] for g in got] == [b, a]


# ------------------------------------------------------------------ Anvil thật (tự skip nếu chưa chạy bootstrap)
@pytest.mark.anvil
def test_confirm_delivery_on_real_anvil_contract(mysql_db):
    """Cần `./scripts/bootstrap.sh` (Anvil + contract + backend/.env.web3). Chạy: pytest -m anvil test/integration_test/test_w3_relayer_mysql.py"""
    from slopee_web3.settings import Web3Settings
    from slopee_web3.adapters.web3_chain import Web3Chain
    from slopee_web3.adapters.env_signer import EnvKeySigner
    s = Web3Settings.from_env()
    if s is None or not s.shipper_key:
        pytest.skip('Chưa có backend/.env.web3 (chạy scripts/bootstrap.sh)')
    chain = Web3Chain(s.rpc_url, s.escrow_address, timeout=2)
    try:
        chain.latest_block()
    except Exception:
        pytest.skip('Anvil không chạy')
    signer = EnvKeySigner.from_settings(s)
    signer.verify_against_chain(chain)
    queue = SingleThreadQueue('anvil-relayer')
    svc = RelayerService(lambda: MySqlUnitOfWork(connect), chain, signer, queue, receipt_timeout=20)
    oid_env = os.environ.get('RELAYER_TEST_ONCHAIN_ID')
    if not oid_env:
        pytest.skip('Đặt RELAYER_TEST_ONCHAIN_ID = id đơn đang LOCKED trên chuỗi (kịch bản I-05/E-01 tạo sẵn)')
    try:
        out = svc.confirm_delivery(str(uuid.uuid4()), int(oid_env))
        assert out['outcome'] in ('SENT', 'ALREADY_DELIVERED')
        assert chain.get_order_state(int(oid_env)) == 'DELIVERED'
        if out['outcome'] == 'SENT':
            assert _rows()[-1]['status'] == 'CONFIRMED'
    finally:
        queue.close()
    assert ADDR['shipper'] == signer.sender_address('shipper')
