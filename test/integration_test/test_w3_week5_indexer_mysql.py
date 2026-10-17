"""Tuần 5 [B]+[Q]: handler Indexer mới (Delivered/Disputed/Completed/Refunded/PayoutDeferred/PendingClaimed), reorg đối xứng,
chuyển trạng thái sai chỉ gắn anomaly, và HTTP end-to-end của cổng Shipper (Flask + MySQL + token thật)."""
import pytest
from flask import Flask

from auth_utils import issue_token
from slopee_web3.adapters.clock import HybridClock
from slopee_web3.adapters.flask_api import container as container_mod
from slopee_web3.adapters.flask_api import register_web3
from slopee_web3.adapters.flask_api.container import Web3Container
from slopee_web3.adapters.indexer import Indexer
from slopee_web3.adapters.indexer.handlers import rollback_orders_from_block
from slopee_web3.adapters.mysql_repos import MySqlUnitOfWork
from slopee_web3.settings import Web3Settings
from test_w3_week5_flow_mysql import (Stack, assign, db, extra_group, locked_orders, make_group, new_shipper, row, status)  # noqa: F401
from w3_support import ADDR, ESCROW, TOKEN, connect, event, make_signer, user

pytestmark = pytest.mark.mysql

ZERO = '0x' + '0' * 40


@pytest.fixture
def st():
    s = Stack()
    yield s
    s.queue.close()


def inject(chain, name, **args):
    """Chèn một log THÔ vào chuỗi giả (để tạo trình tự sự kiện mà contract thật không bao giờ sinh)."""
    chain.head += 1
    chain.times[chain.head] = chain.now
    chain.logs.append(event(name, chain.head, 0, **args))
    return chain.head


def pending(db, token=ZERO, addr=None):
    r = row(db, "SELECT amount_raw FROM pending_balances WHERE token_address=%s AND address=%s", token, (addr or ADDR['merchant1']).lower())
    return None if r is None else r['amount_raw']


# ------------------------------------------------------------------ số dư chờ rút
def test_pending_balance_accumulates_and_is_claimed_with_exact_integers(st, db):
    big = 10 ** 30
    st.chain.defer_payout(ZERO, ADDR['merchant1'], big)
    st.chain.defer_payout(ZERO, ADDR['merchant1'], 5)
    st.index()
    assert pending(db) == str(big + 5)                         # số nguyên lớn, không mất độ chính xác
    st.chain.claim_pending(ZERO, ADDR['merchant1'])
    st.index()
    assert pending(db) == '0'
    st.index()                                                 # chạy lại không cộng/trừ lần hai
    assert pending(db) == '0'


def test_claim_larger_than_balance_clamps_to_zero_instead_of_going_negative(st, db):
    inject(st.chain, 'PendingClaimed', token=ZERO, to=ADDR['merchant1'], amount=10)
    st.index()
    assert pending(db) == '0'


def test_reconcile_counts_deferred_payouts_as_expected_balance(st, db):
    """INV-01 nhánh ETH: Σ PayoutDeferred − Σ PendingClaimed phải bằng số ETH thật nằm trong contract."""
    st.chain.defer_payout(ZERO, ADDR['merchant1'], 40)
    st.chain.eth_balance = 40
    st.index()
    eth = [t for t in st.reconcile.run()['tokens'] if t['token'] == 'ETH'][0]
    assert eth['pending_raw'] == '40' and eth['balance_raw'] == '40' and eth['ok']
    st.chain.eth_balance = 0                                   # ETH biến mất khỏi contract mà sổ vẫn ghi nợ: phải báo lệch
    rec = st.reconcile.run()
    eth = [t for t in rec['tokens'] if t['token'] == 'ETH'][0]
    assert eth['diff_raw'] == '-40' and not rec['ok']


# ------------------------------------------------------------------ chuyển trạng thái sai chỉ gắn anomaly
@pytest.mark.parametrize('bad_event,args', [
    ('OrderCompleted', dict(netPayout=1, feeAmount=0)),                       # LOCKED -> COMPLETED (bỏ qua giao hàng)
    ('OrderDisputed', dict(raisedBy=ADDR['buyer'], disputedAt=1)),             # LOCKED -> DISPUTED
    ('OrderRefunded', dict(to=ADDR['buyer'], amount=1)),                       # LOCKED -> REFUNDED hợp lệ! (xem test riêng) nên dùng DELIVERED ở dưới
])
def test_invalid_transition_flags_anomaly_and_never_moves_state(st, db, bad_event, args):
    _, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    oid = int(o['quote']['orderId'])
    if bad_event == 'OrderRefunded':
        shipper = new_shipper(db)
        assign(st, db, o['order_id'], shipper)
        st.shipper.deliver(shipper, o['order_id'])
        st.index()
        expected = 'DELIVERED'                                               # DELIVERED -> REFUNDED không có trong máy trạng thái
    else:
        expected = 'LOCKED'
    inject(st.chain, bad_event, orderId=oid, **args)
    st.index()
    r = row(db, "SELECT status, anomaly_flag, closed_at, disputed_at FROM order_web3 WHERE order_id=%s", o['order_id'])
    assert r['status'] == expected and r['anomaly_flag'] == 1 and r['closed_at'] is None and r['disputed_at'] is None
    assert row(db, "SELECT status FROM orders WHERE id=%s", o['order_id'])['status'] == ('shipped' if expected == 'DELIVERED' else 'paid')


def test_events_for_unknown_onchain_order_are_only_logged(st, db):
    inject(st.chain, 'OrderDelivered', orderId=999999999, deliveredAt=st.chain.now)
    stats = st.index()
    assert stats['new_events'] == 1
    assert row(db, "SELECT COUNT(*) AS c FROM chain_events WHERE event_name='OrderDelivered'")['c'] == 1
    assert row(db, "SELECT COUNT(*) AS c FROM order_web3 WHERE anomaly_flag=1")['c'] == 0


# ------------------------------------------------------------------ reorg đối xứng (rollback_orders_from_block)
def _rollback(from_block):
    conn = connect()
    try:
        with conn.cursor() as cur:
            n = rollback_orders_from_block(cur, from_block)
        conn.commit()
        return n
    finally:
        conn.close()


def test_reorg_of_delivered_block_restores_locked_and_removes_stale_notification(st, db):
    buyer, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    shipper = new_shipper(db)
    assign(st, db, o['order_id'], shipper)
    st.shipper.deliver(shipper, o['order_id'])
    st.index()
    assert status(db, o['order_id']) == 'DELIVERED' and len(st.notifications.list_for_user(buyer)['notifications']) == 1
    delivered_block = row(db, "SELECT block_number FROM chain_events WHERE event_name='OrderDelivered'")['block_number']
    assert _rollback(delivered_block) == 1
    r = row(db, "SELECT status, delivered_at FROM order_web3 WHERE order_id=%s", o['order_id'])
    assert r['status'] == 'LOCKED' and r['delivered_at'] is None                       # dựng lại từ OrderCreated còn lại
    assert st.notifications.list_for_user(buyer)['notifications'] == []
    assert row(db, "SELECT status FROM orders WHERE id=%s", o['order_id'])['status'] == 'paid'


def _index(st, depth=1000):
    conn = connect()
    try:
        return Indexer(connect, st.chain, start_block=0, reorg_depth=depth).run_once(conn)
    finally:
        conn.close()


def _refunded(st, db):
    _, group, pids = locked_orders(st, db, 1)
    o = group['orders'][0]
    st.chain.advance(14 * 86400)
    st.chain.cancel_if_unfulfilled(int(o['quote']['orderId']))
    _index(st)
    stock = lambda: row(db, "SELECT inStock FROM products WHERE id=%s", pids[0])['inStock']
    assert status(db, o['order_id']) == 'REFUNDED' and stock() == 10
    return o, stock


def test_reorg_that_replays_the_refund_restores_stock_exactly_once(st, db):
    """Rollback đưa REFUNDED về PENDING_PAYMENT phải GIỮ LẠI hàng (8), rồi nhánh mới hoàn tiền lại ⇒ đúng 10 (không phải 12)."""
    o, stock = _refunded(st, db)
    st.chain.blocks[st.chain.head] = {'hash': '0x' + 'ee' * 32}                  # block cuối đổi: Indexer phát hiện reorg
    _index(st)
    assert status(db, o['order_id']) == 'REFUNDED' and stock() == 10


def test_reorg_that_drops_the_refund_leaves_order_locked_with_stock_reserved(st, db):
    o, stock = _refunded(st, db)
    st.chain.logs = [e for e in st.chain.logs if e['event'] != 'OrderRefunded']  # nhánh mới không có hoàn tiền
    st.chain.blocks[st.chain.head] = {'hash': '0x' + 'ee' * 32}
    _index(st)
    assert status(db, o['order_id']) == 'LOCKED' and stock() == 8
    assert row(db, "SELECT status FROM orders WHERE id=%s", o['order_id'])['status'] == 'paid'


def test_reorg_undoes_pending_balance_events_in_rolled_back_blocks(st, db):
    st.chain.defer_payout(ZERO, ADDR['merchant1'], 40)
    block = st.chain.head
    st.index()
    assert pending(db) == '40'
    _rollback(block)
    assert pending(db) == '0'                                  # không cộng hai lần khi quét lại nhánh mới
    assert row(db, "SELECT COUNT(*) AS c FROM chain_events WHERE block_number >= %s", block)['c'] == 0


def test_rollback_leaves_orders_untouched_before_the_reorg_point(st, db):
    _, group, _ = locked_orders(st, db, 2)
    created_block = row(db, "SELECT MIN(block_number) AS b FROM chain_events")['b']
    assert _rollback(created_block + 1000) == 0
    assert all(status(db, o['order_id']) == 'LOCKED' for o in group['orders'])


# ------------------------------------------------------------------ HTTP end-to-end
@pytest.fixture
def http(st, db):
    settings = Web3Settings(rpc_url='x', chain_id=31337, escrow_address=ESCROW, token_address=TOKEN)
    ct = Web3Container(settings, st.signer, st.chain, st.clock, st.uow)
    container_mod.set_container(ct)
    app = Flask(__name__)
    register_web3(app)
    yield app.test_client()
    container_mod.set_container(None)


def H(uid, role):
    return {'Authorization': f'Bearer {issue_token(uid, role)}'}


def test_http_shipper_flow_end_to_end(st, db, http):
    buyer, group, _ = locked_orders(st, db, 2)
    a, b = group['orders']
    shipper, stranger = new_shipper(db), new_shipper(db)
    admin = user(db, 'admin')

    # Admin gán; chỉ Admin được gán, người mua/Shipper thì không
    assert http.put(f"/api/admin/orders/{a['order_id']}/shipper", json={'shipper_user_id': shipper}, headers=H(buyer, 'user')).status_code == 403
    r = http.put(f"/api/admin/orders/{a['order_id']}/shipper", json={'shipper_user_id': shipper}, headers=H(admin, 'admin'))
    assert r.status_code == 200 and r.get_json()['shipper_user_id'] == shipper
    r = http.put(f"/api/admin/orders/{a['order_id']}/shipper", json={'shipper_user_id': buyer}, headers=H(admin, 'admin'))
    assert r.status_code == 422 and r.get_json()['code'] == 'INVALID_SHIPPER'

    # Shipper thấy đúng đơn của mình; người khác thấy rỗng; người mua bị 403
    r = http.get('/api/shipper/orders', headers=H(shipper, 'shipper'))
    assert r.status_code == 200 and [o['order_id'] for o in r.get_json()['orders']] == [a['order_id']]
    assert http.get('/api/shipper/orders', headers=H(stranger, 'shipper')).get_json() == {'orders': []}
    assert http.get('/api/shipper/orders', headers=H(buyer, 'user')).status_code == 403

    # Giao hàng: đúng Shipper -> 200 SENT; người khác -> 404; đơn B chưa gán -> 404
    assert http.post(f"/api/shipper/orders/{a['order_id']}/deliver", headers=H(stranger, 'shipper')).status_code == 404
    assert http.post(f"/api/shipper/orders/{b['order_id']}/deliver", headers=H(shipper, 'shipper')).status_code == 404
    r = http.post(f"/api/shipper/orders/{a['order_id']}/deliver", headers=H(shipper, 'shipper'))
    body = r.get_json()
    assert r.status_code == 200 and body['outcome'] == 'SENT' and body['tx_hash'].startswith('0x')
    assert status(db, a['order_id']) == 'LOCKED'                                       # API không ghi trạng thái (BR-09)

    # Indexer ghi nhận; Buyer thấy trạng thái qua polling và có thông báo
    st.index()
    r = http.get(f"/api/orders/{a['order_id']}/status", headers=H(buyer, 'user'))
    assert r.get_json()['status'] == 'DELIVERED' and r.get_json()['delivered_at'] == st.chain.now
    notes = http.get('/api/notifications', headers=H(buyer, 'user')).get_json()['notifications']
    assert len(notes) == 1 and notes[0]['kind'] == 'ORDER_DELIVERED' and notes[0]['read'] is False
    assert http.get('/api/notifications', headers=H(stranger, 'shipper')).get_json() == {'notifications': []}   # chỉ thấy của mình
    r = http.post(f"/api/shipper/orders/{a['order_id']}/deliver", headers=H(shipper, 'shipper'))
    assert r.status_code == 200 and r.get_json()['outcome'] == 'ALREADY_DELIVERED'

    # Đối soát qua API (Admin): số tiền là CHUỖI; Buyer bị 403
    r = http.get('/api/admin/reconcile?deep=1', headers=H(admin, 'admin'))
    rec = r.get_json()
    assert r.status_code == 200 and rec['ok'] and isinstance(rec['tokens'][0]['balance_raw'], str) and rec['order_mismatches'] == []
    assert http.get('/api/admin/reconcile', headers=H(buyer, 'user')).status_code == 403


def test_http_when_chain_is_down_returns_503_and_leaves_outbox_failed(st, db, http):
    _, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    shipper = new_shipper(db)
    assign(st, db, o['order_id'], shipper)
    real = st.chain.get_order_state
    st.chain.available = False
    r = http.post(f"/api/shipper/orders/{o['order_id']}/deliver", headers=H(shipper, 'shipper'))
    assert r.status_code == 503 and r.get_json()['code'] == 'CHAIN_UNAVAILABLE'
    st.chain.available = True
    assert st.chain.get_order_state(int(o['quote']['orderId'])) == 'LOCKED'            # không gửi được gì
    assert http.post(f"/api/shipper/orders/{o['order_id']}/deliver", headers=H(shipper, 'shipper')).status_code == 200
