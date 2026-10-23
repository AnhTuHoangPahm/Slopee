"""Tuần 7 [A] UC-07 cổng Merchant trên MySQL THẬT + chuỗi giả mô hình đúng contract.

Đơn đi đủ đường: ký quỹ -> Indexer -> giao -> (khiếu nại) -> giải ngân; kiểm Merchant chỉ thấy đơn của shop mình, số tiền khớp chuỗi,
số dư chờ rút (PayoutDeferred/PendingClaimed qua Indexer) chỉ hiện cho đúng ví, và HTTP đầu cuối (vai trò, danh tính từ token).
"""
import pytest
from flask import Flask

from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container as container_mod
from slopee_web3.adapters.flask_api import register_web3
from slopee_web3.adapters.flask_api.container import Web3Container
from slopee_web3.application.merchant_service import MerchantService
from slopee_web3.settings import Web3Settings
from test_w3_week5_flow_mysql import Stack, db, db_all, locked_orders, make_group, new_shipper, assign, row, status  # noqa: F401
from w3_support import ADDR, ESCROW, TOKEN, user

pytestmark = pytest.mark.mysql
DAY = 86400
ETH = '0x' + '0' * 40


@pytest.fixture
def st():
    s = Stack()
    yield s
    s.queue.close()


@pytest.fixture(autouse=True)
def _drop_dispute_rows_after_each_test(mysql_db):
    yield
    from w3_support import connect
    conn = connect()
    conn.autocommit(True)
    cur = conn.cursor()
    for t in ('dispute_signatures', 'dispute_resolutions', 'dispute_notes'):
        cur.execute(f"DELETE FROM {t}")
    conn.close()


def svc(st):
    return MerchantService(st.uow, tokens={TOKEN: {'symbol': 'mUSD', 'decimals': 6}})


def merchant_of(db, order_id):
    return row(db, "SELECT merchant_user_id, merchant_wallet FROM order_web3 WHERE order_id=%s", order_id)


def deliver(st, db, order_id):
    ship = new_shipper(db)
    assign(st, db, order_id, ship)
    st.shipper.deliver(ship, order_id)
    st.index()


def test_merchant_sees_only_own_funded_orders_with_exact_amounts(st, db):
    _, group, _ = locked_orders(st, db, 2)
    a, b = group['orders']
    ma, mb = merchant_of(db, a['order_id']), merchant_of(db, b['order_id'])
    assert ma['merchant_user_id'] != mb['merchant_user_id']

    out = svc(st).list_orders(ma['merchant_user_id'])
    assert [o['order_id'] for o in out['orders']] == [a['order_id']]                 # đơn của shop khác không lộ
    o = out['orders'][0]
    amount = int(a['quote']['amount'])
    fee = amount * int(a['quote']['feeBps']) // 10_000
    assert (o['status'], o['amount_raw'], o['fee_amount_raw'], o['net_amount_raw']) == ('LOCKED', str(amount), str(fee), str(amount - fee))
    assert o['symbol'] == 'mUSD' and o['decimals'] == 6 and o['token'] == TOKEN.lower()
    assert o['merchant_wallet'] == ma['merchant_wallet'].lower() and o['delivery_deadline'] == o['chain_created_at'] + 14 * DAY
    assert o['items'] and o['items'][0]['quantity'] == 2 and o['buyer_name']
    assert out['wallet'] == ma['merchant_wallet'].lower() and out['pending'] == []
    assert 'buyer_wallet' not in o and 'doc_hash' not in o


def test_unfunded_and_expired_orders_are_not_listed(st, db):
    _, group, _ = make_group(st, db, 1)                                               # PENDING_PAYMENT: chưa nạp tiền
    m = merchant_of(db, group['orders'][0]['order_id'])
    assert svc(st).list_orders(m['merchant_user_id'])['orders'] == []
    db.execute("UPDATE order_web3 SET status='EXPIRED' WHERE order_id=%s", (group['orders'][0]['order_id'],))
    assert svc(st).list_orders(m['merchant_user_id'])['orders'] == []


def test_status_follows_the_chain_through_delivery_and_release(st, db):
    _, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    uid = merchant_of(db, o['order_id'])['merchant_user_id']
    deliver(st, db, o['order_id'])
    d = svc(st).list_orders(uid)['orders'][0]
    assert d['status'] == 'DELIVERED' and d['delivered_at'] == st.chain.now and d['release_at'] == d['delivered_at'] + d['inspection_duration']
    assert d['delivery_deadline'] is None

    st.chain.early_release(int(o['quote']['orderId']))
    st.index()
    c = svc(st).list_orders(uid)['orders'][0]
    assert c['status'] == 'COMPLETED' and c['closed_at'] == st.chain.now and c['release_at'] is None


def test_disputed_order_exposes_force_resolve_deadline_from_chain_time(st, db):
    _, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    uid = merchant_of(db, o['order_id'])['merchant_user_id']
    deliver(st, db, o['order_id'])
    st.chain.raise_dispute(int(o['quote']['orderId']))
    st.index()
    d = svc(st).list_orders(uid)['orders'][0]
    assert d['status'] == 'DISPUTED' and d['disputed_at'] == st.chain.now
    assert d['force_resolve_at'] == d['disputed_at'] + d['dispute_timeout'] and d['release_at'] is None


def test_refunded_order_stays_visible_so_merchant_sees_the_outcome(st, db):
    _, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    uid = merchant_of(db, o['order_id'])['merchant_user_id']
    st.chain.advance(14 * DAY)
    st.chain.cancel_if_unfulfilled(int(o['quote']['orderId']))
    st.index()
    r = svc(st).list_orders(uid)['orders'][0]
    assert r['status'] == 'REFUNDED' and r['closed_at'] == st.chain.now


def test_pending_balance_is_shown_only_to_the_wallet_owner_and_cleared_after_claim(st, db):
    _, group, _ = locked_orders(st, db, 2)
    a, b = group['orders']
    ma, mb = merchant_of(db, a['order_id']), merchant_of(db, b['order_id'])
    st.chain.defer_payout(ETH, ma['merchant_wallet'], 7_000)
    st.chain.defer_payout(ETH, ma['merchant_wallet'], 500)                            # cộng dồn
    st.index()

    mine = svc(st).list_orders(ma['merchant_user_id'])['pending']
    assert mine == [{'token': 'ETH', 'address': ma['merchant_wallet'].lower(), 'amount_raw': '7500', 'symbol': 'ETH', 'decimals': 18}]
    assert svc(st).list_orders(mb['merchant_user_id'])['pending'] == []               # shop khác không thấy tiền của mình

    st.chain.claim_pending(ETH, ma['merchant_wallet'])
    st.index()
    assert svc(st).list_orders(ma['merchant_user_id'])['pending'] == []              # đã rút: số dư dẫn xuất về 0 và bị ẩn


def test_pending_follows_the_wallet_used_on_orders_even_after_relinking(st, db):
    _, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    m = merchant_of(db, o['order_id'])
    old = m['merchant_wallet'].lower()
    db.execute("UPDATE user_wallets SET is_active=0 WHERE user_id=%s", (m['merchant_user_id'],))
    db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (m['merchant_user_id'], ADDR['merchant5'].lower()))
    st.chain.defer_payout(ETH, m['merchant_wallet'], 42)
    st.index()
    out = svc(st).list_orders(m['merchant_user_id'])
    assert out['wallet'] == ADDR['merchant5'].lower()                                 # ví đang liên kết
    assert [(p['address'], p['amount_raw']) for p in out['pending']] == [(old, '42')]  # tiền vẫn nằm ở ví cũ trên chuỗi: phải hiện để rút được


def test_merchant_without_any_order_or_wallet_gets_empty_payload(st, db):
    uid = user(db, 'seller')
    assert svc(st).list_orders(uid) == {'wallet': None, 'orders': [], 'pending': []}


def test_reorg_style_reversal_of_pending_events_is_reflected(st, db):
    _, group, _ = locked_orders(st, db, 1)
    m = merchant_of(db, group['orders'][0]['order_id'])
    st.chain.defer_payout(ETH, m['merchant_wallet'], 10)
    st.index()
    db.execute("UPDATE pending_balances SET amount_raw='0'")                          # số dư dẫn xuất bằng 0 (vd. sau đảo ngược) thì không hiện
    assert svc(st).list_orders(m['merchant_user_id'])['pending'] == []


# ------------------------------------------------------------------ HTTP đầu cuối
@pytest.fixture
def http(st, db):
    settings = Web3Settings(rpc_url='x', chain_id=31337, escrow_address=ESCROW, token_address=TOKEN)
    container_mod.set_container(Web3Container(settings, st.signer, st.chain, st.clock, st.uow))
    app = Flask(__name__)
    register_web3(app)
    yield app.test_client()
    container_mod.set_container(None)


def H(uid, role='seller'):
    return {'Authorization': f'Bearer {issue_token(uid, role)}'}


def test_http_roles_and_identity_from_token(st, db, http):
    buyer, group, _ = locked_orders(st, db, 2)
    a, b = group['orders']
    ua, ub = merchant_of(db, a['order_id'])['merchant_user_id'], merchant_of(db, b['order_id'])['merchant_user_id']

    assert http.get('/api/merchant/orders').status_code == 401
    for role in ('user', 'shipper', 'admin'):
        assert http.get('/api/merchant/orders', headers=H(ua, role)).status_code == 403
    assert http.get('/api/merchant/orders', headers=H(buyer, 'user')).status_code == 403             # Buyer không xem được đơn bán

    r = http.get(f'/api/merchant/orders?merchant_user_id={ub}&userId={ub}', headers=H(ua))       # cố giả danh qua query: bị bỏ qua
    assert r.status_code == 200
    body = r.get_json()
    assert [o['order_id'] for o in body['orders']] == [a['order_id']]
    assert isinstance(body['orders'][0]['amount_raw'], str) and body['pending'] == []
    assert http.get('/api/merchant/orders', headers=H(ub)).get_json()['orders'][0]['order_id'] == b['order_id']
