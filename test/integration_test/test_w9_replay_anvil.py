"""Tuần 9 [B][Q]: AC-08 trên CHUỖI THẬT (Anvil + contract của bootstrap.sh) + MySQL thật.

Ký quỹ gom 3 shop bằng báo giá do Python ký -> Shipper giao -> Buyer nhận sớm đơn A, khiếu nại đơn B, đơn C vẫn LOCKED -> Indexer ghi
-> `replay()` (chính hàm CLI/`scripts/replay.sh` dùng) với Web3Chain thật: xóa dữ liệu dẫn xuất, dựng lại từ log thật, ảnh các bảng phải khớp
từng dòng, rồi đối soát số dư contract. Tự skip nếu không có Anvil/MySQL.
Chạy: ./scripts/bootstrap.sh --fresh --force-env && pytest -m anvil test/integration_test/test_w9_replay_anvil.py
"""
import pytest

from slopee_web3.adapters.indexer import Indexer
from slopee_web3.adapters.indexer.replay import replay, snapshot
from slopee_web3.adapters.mysql_repos import MySqlUnitOfWork
from slopee_web3.application.reconcile_service import ReconcileService
from w3_support import connect
from test_w3_chain_anvil import stack, svc  # noqa: F401  (fixture dùng chung)
from test_w5_happy_path_anvil import _index, _locked_orders, _restore_onchain_id_seq, _send  # noqa: F401

pytestmark = [pytest.mark.mysql, pytest.mark.anvil]
WIPE = ('dispute_signatures', 'dispute_resolutions', 'dispute_notes', 'notifications', 'tx_outbox', 'shipper_assignments',
        'pending_balances', 'chain_events', 'indexer_cursor', 'order_quotes', 'order_web3', 'checkout_groups', 'orders')


def take():
    conn = connect()
    try:
        with conn.cursor() as cur:
            return snapshot(cur)
    finally:
        conn.close()


def test_ac08_replay_from_block_zero_on_the_real_chain_reproduces_state_and_balances(svc):
    cur, quote, signer, chain, token, s = svc
    for t in WIPE:                                    # bỏ đơn của các test Anvil trước trên cùng DB dùng chung
        cur.execute(f"DELETE FROM {t}")
    buyer_id, orders = _locked_orders(svc, shops=3)
    a, b, c = (int(o['onchain_order_id']) for o in orders)
    _index(chain)
    _send(chain, 'confirmDelivery', a, 'shipper')
    _send(chain, 'confirmDelivery', b, 'shipper')
    _send(chain, 'earlyRelease', a, 'buyer')          # A: COMPLETED
    _send(chain, 'raiseDispute', b, 'buyer')          # B: DISPUTED (tiền đóng băng)
    _index(chain)                                     # C: vẫn LOCKED
    cur.execute("SELECT status FROM order_web3 ORDER BY onchain_order_id")
    assert [r['status'] for r in cur.fetchall()] == ['COMPLETED', 'DISPUTED', 'LOCKED']
    before = take()
    assert len(before['chain_events']) >= 3 + 2 + 1 + 1 + 1       # 3 OrderCreated, 2 giao, 1 nhận, 1 khiếu nại (+ sự kiện của test trước)
    rec = ReconcileService(lambda: MySqlUnitOfWork(connect), chain, known_tokens=[s.token_address])
    rec_before = rec.run(deep=True, events=True)
    assert rec_before['indexer_lag_blocks'] == 0

    conn = connect()
    try:
        ix = Indexer(connect, chain, start_block=0)
        assert ix.acquire_lock(conn)
        res = replay(ix, conn, chain, from_block=0)
        ix.release_lock(conn)
    finally:
        conn.close()

    assert res['ok'] and res['verified'] is True and res['differences'] == [], res
    assert res['reset']['full'] and res['reset']['orders_with_events'] >= 3 and res['pinned_block'] is not None
    assert take() == before                                         # từng dòng giống hệt sau khi dựng lại từ log THẬT
    cur.execute("SELECT status, anomaly_flag FROM order_web3 ORDER BY onchain_order_id")
    assert [(r['status'], r['anomaly_flag']) for r in cur.fetchall()] == [('COMPLETED', 0), ('DISPUTED', 0), ('LOCKED', 0)]
    # Anvil dùng chung: tiền của test khác có thể còn trong contract nên `ok` tuyệt đối không bảo đảm; điều replay phải giữ là KẾT QUẢ ĐỐI SOÁT y hệt trước/sau (trên chuỗi sạch sau bootstrap --fresh thì `ok` cũng True).
    assert rec.run(deep=True, events=True) == rec_before
