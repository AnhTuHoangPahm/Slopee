"""Tuần 8 [B][Q]: lấp khoảng trống I-07 (3 shop qua Indexer), I-04 (đổi chính sách không ảnh hưởng đơn cũ) và I-03/I-06 (replay tương đương).

Chỉ thêm test (Feature Freeze). Replay ở đây = `rollback_orders_from_block(0)` + xóa con trỏ + chạy lại Indexer từ block 0, đúng phép
SDD 6.3 mô tả cho `--from-block 0 --reset` (CLI/`replay.sh` là việc Tuần 9). Chạy trên MySQL thật + chuỗi giả mô hình đúng contract.
"""
import importlib.util
from pathlib import Path

import pytest

from slopee_web3.adapters.indexer.handlers import rollback_orders_from_block
from test_w3_indexer_orders_mysql import conn, created_event, env, row, run  # noqa: F401  (fixtures + helper)
from test_w3_week5_flow_mysql import Stack, assign, locked_orders, new_shipper, status
from w3_support import ADDR, FakeChain, cart_item, connect, shop_with_product, user

pytestmark = pytest.mark.mysql
_spec = importlib.util.spec_from_file_location('scan_no_user_keys', Path(__file__).resolve().parents[2] / 'scripts' / 'scan_no_user_keys.py')
scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan)
DAY = 86400
CLEAN = ('notifications', 'tx_outbox', 'shipper_assignments', 'pending_balances', 'chain_events', 'indexer_cursor',
         'order_quotes', 'order_web3', 'checkout_groups', 'orders', 'user_wallets')        # thứ tự an toàn với khóa ngoại


@pytest.fixture
def db(mysql_db):
    """Xóa đủ bảng Web3 ở ĐẦU và CUỐI mỗi test: DB test dùng chung cả phiên, và các file chạy sau (test_web3_migrations, test_w8_non_custodial_mysql)
    chèn id cố định / quét giá trị 64 hex nên không chấp nhận dữ liệu thừa của mình."""
    conn = connect()
    conn.autocommit(True)
    cur = conn.cursor()

    def wipe():
        for t in CLEAN:
            cur.execute(f"DELETE FROM {t}")
    wipe()
    for k, v in (('FX_VND_PER_TOKEN', '25000'), ('QUOTE_TTL_SECONDS', '900'), ('PLATFORM_FEE_BPS', '300')):
        cur.execute("INSERT INTO platform_settings (setting_key, setting_value) VALUES (%s,%s) "
                    "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)", (k, v))
    yield cur
    wipe()
    cur.execute("DELETE FROM onchain_id_seq")                                       # như test_w3_chain_anvil: trả bộ đếm id về 100001
    cur.execute("ALTER TABLE onchain_id_seq AUTO_INCREMENT = 100001")               # (test_web3_migrations so sánh seq_start của DB dùng chung)
    conn.close()


def shop(db, n, price=100_000):
    sid = user(db, 'seller')
    db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (sid, ADDR[f'merchant{n}'].lower()))
    return shop_with_product(db, sid, price=price)[1]


def checkout(env, db, n_shops):
    """Giỏ n shop (merchant1..n) + 1 món của shop khác (merchant6) KHÔNG thanh toán. Khác helper cũ: không đụng merchant3 khi n>=3."""
    buyer = user(db)
    db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (buyer, ADDR['buyer'].lower()))
    items = [cart_item(db, buyer, shop(db, n), 2) for n in range(1, n_shops + 1)]
    stay = cart_item(db, buyer, shop(db, 6), 1)
    return buyer, env.quote.create_checkout(buyer, items), stay


# ====================================================================== I-07: 3 và 5 shop qua Indexer
@pytest.mark.parametrize('n_shops', [3, 5])
def test_i07_n_shops_one_group_n_created_events_same_tx_clear_exactly_those_cart_items(env, db, conn, n_shops):
    buyer, group, stay = checkout(env, db, n_shops)
    orders = group['orders']
    assert len(orders) == n_shops and len({o['order_id'] for o in orders}) == n_shops
    assert int(group['total_amount_raw']) == sum(int(o['quote']['amount']) for o in orders)
    assert row(db, "SELECT COUNT(*) AS n FROM order_web3 WHERE checkout_group_id=%s", group['checkout_group_id'])['n'] == n_shops
    chain = FakeChain()
    chain.head = 6
    chain.logs = [created_event(o, 5, i) for i, o in enumerate(orders)]            # cùng giao dịch, log_index 0..n-1
    run(conn, chain)
    for o in orders:
        assert row(db, "SELECT status FROM order_web3 WHERE order_id=%s", o['order_id'])['status'] == 'LOCKED'
        assert row(db, "SELECT status FROM orders WHERE id=%s", o['order_id'])['status'] == 'paid'
    left = row(db, "SELECT COUNT(*) AS n, MIN(ci.id) AS id FROM cartItems ci JOIN carts c ON c.id=ci.cartId WHERE c.userId=%s", buyer)
    assert left['n'] == 1 and left['id'] == stay                                   # đúng món không thanh toán còn lại
    assert env.quote.get_group(buyer, group['checkout_group_id'])['status'] == 'LOCKED'
    run(conn, chain)                                                               # chạy lại: không đổi, không anomaly
    assert row(db, "SELECT COUNT(*) AS n FROM order_web3 WHERE anomaly_flag=1")['n'] == 0


def scan_live_db():
    c = connect()
    try:
        c.autocommit(True)
        cur = c.cursor()
        cur.execute("SELECT DATABASE() AS d")
        r = cur.fetchone()
        return scan.scan_database(c, r['d'] if isinstance(r, dict) else r[0])
    finally:
        c.close()


def test_e05_scanner_accepts_real_quotes_with_doc_hash_in_database(env, db, conn):
    """Hồi quy lỗi CI của E-05: `order_quotes.quote_json` thật (do QuoteService sinh) chứa `docHash` 64 hex, scanner `--db` không được báo HIGH."""
    _, group, _ = checkout(env, db, 3)
    db.execute("SELECT quote_json FROM order_quotes")
    docs = [list(r.values())[0] for r in db.fetchall()]
    assert len(docs) == 3 and all('docHash' in d for d in docs)            # có dữ liệu thật, không phải quét rỗng
    rep = scan_live_db()
    assert [f.line() for f in rep.high] == []
    assert rep.scanned['db values'] >= 3


# ====================================================================== I-04: đổi chính sách sau khi đặt
def test_i04_policy_change_after_order_does_not_touch_existing_order_but_applies_to_new_ones(env, db, conn):
    buyer, group, stay = checkout(env, db, 1)
    o = group['orders'][0]
    q0 = (int(o['quote']['inspectionDuration']), int(o['quote']['disputeTimeout']))
    assert q0 == (259_200, 2_592_000)                                              # GENERAL mặc định
    db.execute("SELECT inspection_duration, dispute_timeout FROM category_policies WHERE policy_code='GENERAL'")
    orig = db.fetchone()
    db.execute("UPDATE category_policies SET inspection_duration=7200, dispute_timeout=604800 WHERE policy_code='GENERAL'")
    try:
        w = row(db, "SELECT inspection_duration, dispute_timeout FROM order_web3 WHERE order_id=%s", o['order_id'])
        assert (w['inspection_duration'], w['dispute_timeout']) == q0              # đơn cũ giữ nguyên
        re = env.quote.reissue_group_quotes(buyer, group['checkout_group_id'])     # cấp lại báo giá KHÔNG áp chính sách mới
        assert (int(re['orders'][0]['quote']['inspectionDuration']), int(re['orders'][0]['quote']['disputeTimeout'])) == q0
        chain = FakeChain()
        chain.head = 6
        chain.logs = [created_event(o, 5, 0, inspectionDuration=q0[0], disputeTimeout=q0[1])]
        run(conn, chain)                                                           # sự kiện mang thời hạn cũ: không bị coi là lệch
        r = row(db, "SELECT status, anomaly_flag FROM order_web3 WHERE order_id=%s", o['order_id'])
        assert r['status'] == 'LOCKED' and r['anomaly_flag'] == 0
        new = env.quote.create_checkout(buyer, [stay])                             # đơn mới nhận chính sách mới
        nq = new['orders'][0]['quote']
        assert (int(nq['inspectionDuration']), int(nq['disputeTimeout'])) == (7200, 604800)
    finally:
        db.execute("UPDATE category_policies SET inspection_duration=%s, dispute_timeout=%s WHERE policy_code='GENERAL'",
                   (orig['inspection_duration'], orig['dispute_timeout']))


# ====================================================================== I-03 / I-06: replay tương đương
def snapshot(db):
    db.execute("SELECT w.onchain_order_id, w.status, w.deposit_tx_hash, w.chain_created_at, w.delivered_at, w.disputed_at, "
               "w.closed_at, w.anomaly_flag, o.status AS legacy FROM order_web3 w JOIN orders o ON o.id=w.order_id "
               "ORDER BY w.onchain_order_id")
    orders = [tuple(r.values()) for r in db.fetchall()]
    db.execute("SELECT id, inStock FROM products ORDER BY id")
    stock = [tuple(r.values()) for r in db.fetchall()]
    db.execute("SELECT token_address, address, amount_raw FROM pending_balances ORDER BY token_address, address")
    pend = [tuple(r.values()) for r in db.fetchall()]
    db.execute("SELECT kind, COUNT(*) AS n FROM notifications GROUP BY kind ORDER BY kind")
    notes = [tuple(r.values()) for r in db.fetchall()]
    db.execute("SELECT event_name, COUNT(*) AS n FROM chain_events GROUP BY event_name ORDER BY event_name")
    events = [tuple(r.values()) for r in db.fetchall()]
    return {'orders': orders, 'stock': stock, 'pending': pend, 'notifications': notes, 'events': events}


def reset_and_replay(st, db=None, before=None):
    c = connect()
    try:
        with c.cursor() as cur:
            rollback_orders_from_block(cur, 0)
            cur.execute("DELETE FROM indexer_cursor")
        c.commit()
    finally:
        c.close()
    if before is not None:
        assert snapshot(db) != before                                              # rollback thật sự đã xóa trạng thái dẫn xuất
    st.index()


@pytest.fixture
def st():
    s = Stack()
    yield s
    s.queue.close()


def test_i03_i06_replay_from_block_zero_reproduces_every_table_exactly(st, db):
    buyer, group, _ = locked_orders(st, db, 4)
    a, b, c, d = group['orders']
    ship = new_shipper(db)
    for o in (a, b, c):
        assign(st, db, o['order_id'], ship)
        st.shipper.deliver(ship, o['order_id'])
    st.index()
    st.chain.early_release(int(a['quote']['orderId']))                              # a: Buyer mở khóa sớm
    st.chain.raise_dispute(int(b['quote']['orderId']))                              # b: khiếu nại
    st.index()
    st.chain.advance(3 * DAY + 5)
    st.release.run_once()                                                           # c: tự giải ngân sau hạn kiểm tra
    st.chain.eth_balance = 40
    st.chain.defer_payout('0x' + '0' * 40, ADDR['merchant1'], 40)                    # sổ chờ rút (ETH khớp số dư contract)
    st.index()
    st.chain.advance(30 * DAY)
    st.chain.arbitrator_force_resolve(int(b['quote']['orderId']), b['quote']['buyer'])   # b: Trọng tài hoàn Buyer sau timeout
    st.chain.cancel_if_unfulfilled(int(d['quote']['orderId']))                      # d: quá 14 ngày chưa giao, hoàn tiền
    st.index()
    assert [status(db, o['order_id']) for o in (a, b, c, d)] == ['COMPLETED', 'REFUNDED', 'COMPLETED', 'REFUNDED']
    rec_before = st.reconcile.run()
    assert rec_before['ok'], rec_before
    before = snapshot(db)
    assert before['pending'] and before['events']
    reset_and_replay(st, db, before)
    after = snapshot(db)
    assert after == before
    assert [f.line() for f in scan_live_db().high] == []                             # vòng đời đầy đủ vẫn không để lọt khóa vào CSDL (E-05)
    assert row(db, "SELECT COUNT(*) AS n FROM order_web3 WHERE anomaly_flag=1")['n'] == 0
    rec_after = st.reconcile.run()
    assert rec_after == rec_before                                                  # đối soát y hệt trước/sau replay
    reset_and_replay(st, db, before)                                                # replay lần hai vẫn ổn định
    assert snapshot(db) == before
