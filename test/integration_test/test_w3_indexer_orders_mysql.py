"""Tuần 4 [B]: Indexer xử lý OrderCreated trên MySQL THẬT (I-03, I-06, I-07 phần Indexer) + reorg + GET /api/orders/:code/status."""
import pytest
from flask import Flask

from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container, register_web3
from slopee_web3.adapters.indexer import Indexer
from w3_support import ADDR, TOKEN, Env, FakeChain, cart_item, connect, event, shop_with_product, user

pytestmark = pytest.mark.mysql


@pytest.fixture
def db(mysql_db):
    conn = connect()
    conn.autocommit(True)
    cur = conn.cursor()
    for t in ('chain_events', 'indexer_cursor', 'order_quotes', 'order_web3', 'checkout_groups', 'orders', 'user_wallets'):   # mỗi test bắt đầu sạch
        cur.execute(f"DELETE FROM {t}")
    for k, v in (('FX_VND_PER_TOKEN', '25000'), ('QUOTE_TTL_SECONDS', '900'), ('PLATFORM_FEE_BPS', '300')):
        cur.execute("INSERT INTO platform_settings (setting_key, setting_value) VALUES (%s,%s) "
                    "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)", (k, v))
    yield cur
    conn.close()


@pytest.fixture
def env():
    return Env()


@pytest.fixture
def conn(mysql_db):
    c = connect()
    yield c
    c.rollback()
    c.close()


def seller_shop(db, n, price=100_000):
    sid = user(db, 'seller')
    db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (sid, ADDR[f'merchant{n}'].lower()))
    shop, pid = shop_with_product(db, sid, price=price)
    return sid, pid


def checkout(env, db, n_shops=2):
    """Buyer có ví, giỏ n shop + 1 sản phẩm khác KHÔNG thanh toán. Trả (buyer, group, items_not_checked_out)."""
    buyer = user(db)
    db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (buyer, ADDR['buyer'].lower()))
    items = []
    merchants = []
    for n in range(1, n_shops + 1):
        sid, pid = seller_shop(db, n)
        merchants.append(sid)
        items.append(cart_item(db, buyer, pid, 2))
    _, other_pid = seller_shop(db, 3)
    stay = cart_item(db, buyer, other_pid, 1)
    group = env.quote.create_checkout(buyer, items)
    return buyer, merchants, group, stay


def created_event(o, block, log_index=0, tx=None, **over):
    qt = o['quote']
    args = dict(orderId=int(qt['orderId']), buyer=qt['buyer'], merchant=qt['merchant'], token=qt['token'],
                amount=int(qt['amount']), inspectionDuration=int(qt['inspectionDuration']),
                disputeTimeout=int(qt['disputeTimeout']), docHash=qt['docHash'], feeBps=int(qt['feeBps']))
    args.update(over)
    return event('OrderCreated', block, log_index, tx=tx or '0x' + 'ab' * 32, **args)


def row(db, sql, *a):
    db.execute(sql, a)
    return db.fetchone()


def run(conn, chain, **kw):
    return Indexer(connect, chain, start_block=0, **kw).run_once(conn)


# ====================================================================== OrderCreated -> LOCKED
def test_order_created_locks_orders_syncs_legacy_status_and_clears_only_paid_cart_items(env, db, conn):
    buyer, _, group, stay = checkout(env, db, 2)
    chain = FakeChain()
    chain.head = 6
    chain.logs = [created_event(o, 5, i) for i, o in enumerate(group['orders'])]      # nạp gom: cùng tx, khác log_index
    run(conn, chain)
    for o in group['orders']:
        w = row(db, "SELECT status, deposit_tx_hash, chain_created_at, anomaly_flag FROM order_web3 WHERE order_id=%s", o['order_id'])
        assert w['status'] == 'LOCKED' and w['deposit_tx_hash'] == '0x' + 'ab' * 32 and w['anomaly_flag'] == 0
        assert w['chain_created_at'] == chain.block_ts + 5                             # giờ BLOCK, không phải NOW()
        assert row(db, "SELECT status FROM orders WHERE id=%s", o['order_id'])['status'] == 'paid'
    left = row(db, "SELECT COUNT(*) AS n, MIN(ci.id) AS id FROM cartItems ci JOIN carts c ON c.id=ci.cartId WHERE c.userId=%s", buyer)
    assert left['n'] == 1 and left['id'] == stay                                       # giỏ chỉ còn món không thanh toán
    assert env.quote.get_group(buyer, group['checkout_group_id'])['status'] == 'LOCKED'


def test_cart_is_not_cleared_before_the_event_arrives(env, db):
    buyer, _, group, _ = checkout(env, db, 1)
    assert row(db, "SELECT COUNT(*) AS n FROM cartItems ci JOIN carts c ON c.id=ci.cartId WHERE c.userId=%s", buyer)['n'] == 2
    assert row(db, "SELECT status FROM orders WHERE id=%s", group['orders'][0]['order_id'])['status'] == 'pending'


def test_reprocessing_the_same_events_is_idempotent(env, db, conn):
    _, _, group, _ = checkout(env, db, 1)
    chain = FakeChain()
    chain.head = 4
    chain.logs = [created_event(group['orders'][0], 3)]
    run(conn, chain)
    db.execute("DELETE FROM indexer_cursor")                                            # ép quét lại như replay
    stats = run(conn, chain)
    assert stats['new_events'] == 0
    assert row(db, "SELECT status, anomaly_flag FROM order_web3")['anomaly_flag'] == 0


@pytest.mark.parametrize('field,value', [('amount', 1), ('feeBps', 1), ('docHash', '0x' + '11' * 32),
                                         ('inspectionDuration', 3601), ('disputeTimeout', 8 * 86400)])
def test_event_that_differs_from_stored_quote_locks_but_flags_anomaly_without_touching_price(env, db, conn, field, value):
    _, _, group, _ = checkout(env, db, 1)
    o = group['orders'][0]
    before = row(db, "SELECT amount_raw, fee_bps, doc_hash FROM order_web3 WHERE order_id=%s", o['order_id'])
    chain = FakeChain()
    chain.head = 4
    chain.logs = [created_event(o, 3, **{field: value})]
    run(conn, chain)
    w = row(db, "SELECT status, anomaly_flag, amount_raw, fee_bps, doc_hash FROM order_web3 WHERE order_id=%s", o['order_id'])
    assert w['status'] == 'LOCKED' and w['anomaly_flag'] == 1
    assert (w['amount_raw'], w['fee_bps'], w['doc_hash']) == (before['amount_raw'], before['fee_bps'], before['doc_hash'])


def test_wrong_buyer_in_event_is_flagged(env, db, conn):
    _, _, group, _ = checkout(env, db, 1)
    chain = FakeChain()
    chain.head = 4
    chain.logs = [created_event(group['orders'][0], 3, buyer=ADDR['stranger'])]
    run(conn, chain)
    assert row(db, "SELECT anomaly_flag FROM order_web3")['anomaly_flag'] == 1


def test_address_case_does_not_cause_false_anomaly(env, db, conn):
    _, _, group, _ = checkout(env, db, 1)
    o = group['orders'][0]
    chain = FakeChain()
    chain.head = 4
    chain.logs = [created_event(o, 3, buyer=o['quote']['buyer'].lower(), merchant=o['quote']['merchant'].upper().replace('0X', '0x'))]
    run(conn, chain)
    assert row(db, "SELECT anomaly_flag FROM order_web3")['anomaly_flag'] == 0


def test_event_for_unknown_order_is_stored_but_changes_nothing(env, db, conn):
    _, _, group, _ = checkout(env, db, 1)
    chain = FakeChain()
    chain.head = 4
    chain.logs = [event('OrderCreated', 3, 0, orderId=999_999_999, buyer=ADDR['buyer'], merchant=ADDR['merchant1'], token=TOKEN,
                        amount=1, inspectionDuration=3600, disputeTimeout=7 * 86400, docHash='0x' + '00' * 32, feeBps=300)]
    assert run(conn, chain)['new_events'] == 1
    assert row(db, "SELECT status, anomaly_flag FROM order_web3")['status'] == 'PENDING_PAYMENT'
    assert row(db, "SELECT COUNT(*) AS n FROM chain_events")['n'] == 1


def test_expired_order_is_never_resurrected_only_flagged(env, db, conn):
    _, _, group, _ = checkout(env, db, 1)
    o = group['orders'][0]
    db.execute("UPDATE order_web3 SET status='EXPIRED' WHERE order_id=%s", (o['order_id'],))
    db.execute("UPDATE orders SET status='cancelled' WHERE id=%s", (o['order_id'],))
    chain = FakeChain()
    chain.head = 4
    chain.logs = [created_event(o, 3)]
    run(conn, chain)
    w = row(db, "SELECT status, anomaly_flag, deposit_tx_hash FROM order_web3")
    assert (w['status'], w['anomaly_flag'], w['deposit_tx_hash']) == ('EXPIRED', 1, None)
    assert row(db, "SELECT status FROM orders WHERE id=%s", o['order_id'])['status'] == 'cancelled'


def test_handler_failure_after_update_rolls_back_status_cart_and_cursor(env, db, conn):
    from slopee_web3.adapters.indexer import handlers as h
    buyer, _, group, _ = checkout(env, db, 1)
    chain = FakeChain()
    chain.head = 4
    chain.logs = [created_event(group['orders'][0], 3)]

    def boom(cur, ev, ts):
        h.on_order_created(cur, ev, ts)
        raise RuntimeError('lỗi sau khi đã ghi')
    with pytest.raises(RuntimeError):
        Indexer(connect, chain, handlers={'OrderCreated': boom}).run_once(conn)
    assert row(db, "SELECT status FROM order_web3")['status'] == 'PENDING_PAYMENT'
    assert row(db, "SELECT status FROM orders WHERE id=%s", group['orders'][0]['order_id'])['status'] == 'pending'
    assert row(db, "SELECT COUNT(*) AS n FROM cartItems ci JOIN carts c ON c.id=ci.cartId WHERE c.userId=%s", buyer)['n'] == 2
    assert row(db, "SELECT COUNT(*) AS n FROM chain_events")['n'] == 0 and row(db, "SELECT COUNT(*) AS n FROM indexer_cursor")['n'] == 0


# ====================================================================== reorg
def test_reorg_reverts_order_to_pending_and_reapplies_on_new_branch(env, db, conn):
    _, _, group, _ = checkout(env, db, 1)
    o = group['orders'][0]
    chain = FakeChain()
    chain.head = 8
    chain.logs = [created_event(o, 7)]
    run(conn, chain, reorg_depth=3)
    assert row(db, "SELECT status FROM order_web3")['status'] == 'LOCKED'
    chain.blocks[8] = {'hash': '0x' + 'ee' * 32}                       # nhánh mới: block 8 đổi, sự kiện biến mất
    chain.logs = []
    run(conn, chain, reorg_depth=3)
    w = row(db, "SELECT status, deposit_tx_hash, chain_created_at, anomaly_flag FROM order_web3")
    assert (w['status'], w['deposit_tx_hash'], w['chain_created_at'], w['anomaly_flag']) == ('PENDING_PAYMENT', None, None, 0)
    assert row(db, "SELECT status FROM orders WHERE id=%s", o['order_id'])['status'] == 'pending'
    assert row(db, "SELECT COUNT(*) AS n FROM chain_events")['n'] == 0
    cur = row(db, "SELECT last_block, last_block_hash FROM indexer_cursor")
    assert cur['last_block'] == 8
    chain.blocks[9] = {}
    chain.head = 9
    chain.logs = [created_event(o, 9, tx='0x' + 'cd' * 32)]            # nhánh mới có sự kiện ở block 9
    run(conn, chain, reorg_depth=3)
    w = row(db, "SELECT status, deposit_tx_hash, chain_created_at FROM order_web3")
    assert (w['status'], w['deposit_tx_hash'], w['chain_created_at']) == ('LOCKED', '0x' + 'cd' * 32, chain.block_ts + 9)


def test_reorg_keeps_orders_whose_events_are_older_than_the_rewind(env, db, conn):
    _, _, group, _ = checkout(env, db, 2)
    a, b = group['orders']
    chain = FakeChain()
    chain.head = 10
    chain.logs = [created_event(a, 2, tx='0x' + '01' * 32), created_event(b, 9, tx='0x' + '02' * 32)]
    run(conn, chain, reorg_depth=3)
    chain.blocks[10] = {'hash': '0x' + 'ee' * 32}
    chain.logs = [created_event(a, 2, tx='0x' + '01' * 32)]
    run(conn, chain, reorg_depth=3)
    st = {r['order_id']: r['status'] for r in _all(db, "SELECT order_id, status FROM order_web3")}
    assert st[a['order_id']] == 'LOCKED' and st[b['order_id']] == 'PENDING_PAYMENT'


def _all(db, sql):
    db.execute(sql)
    return db.fetchall()


# ====================================================================== GET /api/orders/:code/status
class _C:
    def __init__(self, env): self.env = env
    def wallet_service(self): return self.env.wallet
    def quote_service(self): return self.env.quote
    def order_status_service(self): return self.env.status


def hdr(uid, role='user'):
    return {'Authorization': f"Bearer {issue_token(uid, role)}"}


def test_status_endpoint_follows_indexer_and_enforces_ownership(env, db, conn):
    buyer, merchants, group, _ = checkout(env, db, 1)
    o = group['orders'][0]
    container.set_container(_C(env))
    try:
        app = Flask(__name__)
        register_web3(app)
        c = app.test_client()
        url = f"/api/orders/{o['order_id']}/status"
        r = c.get(url, headers=hdr(buyer))
        body = r.get_json()
        assert r.status_code == 200 and body['status'] == 'PENDING_PAYMENT' and body['anomaly'] is False
        assert body['delivered_at'] is None and body['disputed_at'] is None
        assert body['chain_created_at'] is None      # chưa ký quỹ nên chưa có mốc block (Tuần 7 [C])
        assert body['inspection_duration'] == int(o['inspection_duration']) and body['dispute_timeout'] == int(o['dispute_timeout'])
        assert body['server_time'] == env.clock.now_chain()
        chain = FakeChain()
        chain.head = 4
        chain.logs = [created_event(o, 3)]
        run(conn, chain)
        locked = c.get(url, headers=hdr(buyer)).get_json()
        assert locked['status'] == 'LOCKED'      # polling thấy LOCKED sau Indexer
        assert isinstance(locked['chain_created_at'], int) and locked['chain_created_at'] > 0   # mốc ký quỹ = giờ block của OrderCreated
        assert c.get(url, headers=hdr(merchants[0], 'seller')).status_code == 200
        assert c.get(url, headers=hdr(user(db), 'admin')).status_code == 200
        stranger = c.get(url, headers=hdr(user(db)))
        assert stranger.status_code == 404 and stranger.get_json()['code'] == 'ORDER_NOT_FOUND'
        assert c.get('/api/orders/khong-co/status', headers=hdr(buyer)).status_code == 404
        assert c.get(url).status_code == 401
        assert c.get(url, headers=hdr(buyer, 'shipper')).status_code == 403
    finally:
        container.set_container(None)
