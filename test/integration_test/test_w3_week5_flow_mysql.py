"""Tuần 5 [B]+[Q]: luồng giải ngân đầy đủ trên MySQL THẬT với contract giả mô hình đúng máy trạng thái (I-05 phía backend).

Ký quỹ -> Indexer -> gán Shipper -> deliver (RelayerService của A) -> Indexer -> AutoRelease/mở khóa sớm -> Indexer -> đối soát,
cùng các ca âm. Phần chạy trên Anvil + contract thật nằm ở test_w3_week5_anvil.py (tự skip nếu không có Anvil).
"""
import pytest

from slopee_web3.adapters.clock import HybridClock
from slopee_web3.adapters.indexer import Indexer
from slopee_web3.adapters.mysql_repos import MySqlUnitOfWork
from slopee_web3.adapters.relayer_queue import SingleThreadQueue
from slopee_web3.application.jobs import AutoRelease, DeliveryTimeoutReminder, QuoteExpirySweeper
from slopee_web3.application.notification_service import NotificationService
from slopee_web3.application.quote_service import QuoteService
from slopee_web3.application.reconcile_service import ReconcileService
from slopee_web3.application.relayer_service import RelayerService
from slopee_web3.application.shipper_service import ShipperService
from slopee_web3.domain.errors import DomainError
from w3_support import ADDR, TOKEN, FakeEscrowChain, cart_item, connect, make_signer, shop_with_product, user

pytestmark = pytest.mark.mysql

DAY = 86400
INSPECTION = 259200          # nhóm GENERAL mặc định


@pytest.fixture
def db(mysql_db):
    conn = connect()
    conn.autocommit(True)
    cur = conn.cursor()
    for t in ('notifications', 'tx_outbox', 'shipper_assignments', 'pending_balances', 'chain_events', 'indexer_cursor',
              'order_quotes', 'order_web3', 'checkout_groups', 'orders', 'user_wallets'):
        cur.execute(f"DELETE FROM {t}")
    for k, v in (('FX_VND_PER_TOKEN', '25000'), ('QUOTE_TTL_SECONDS', '900'), ('PLATFORM_FEE_BPS', '300')):
        cur.execute("INSERT INTO platform_settings (setting_key, setting_value) VALUES (%s,%s) "
                    "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)", (k, v))
    yield cur
    conn.close()


class Stack:
    def __init__(self):
        self.chain = FakeEscrowChain()
        self.clock = HybridClock(self.chain, system=lambda: self.chain.now)
        self.signer = make_signer()
        self.uow = lambda: MySqlUnitOfWork(connect)
        self.quote = QuoteService(self.uow, self.signer, self.chain, self.clock, token_address=TOKEN)
        self.queue = SingleThreadQueue('week5-test')
        self.relayer = RelayerService(self.uow, self.chain, self.signer, self.queue, receipt_timeout=1, queue_timeout=10)
        self.shipper = ShipperService(self.uow, self.relayer)
        self.release = AutoRelease(self.uow, self.chain, self.clock, self.relayer)
        self.sweeper = QuoteExpirySweeper(self.uow, self.chain, self.clock)
        self.reminder = DeliveryTimeoutReminder(self.uow, self.chain, self.clock)
        self.reconcile = ReconcileService(self.uow, self.chain, known_tokens=[TOKEN])
        self.notifications = NotificationService(self.uow)

    def index(self):
        conn = connect()
        try:
            return Indexer(connect, self.chain, start_block=0).run_once(conn)
        finally:
            conn.close()


@pytest.fixture
def st():
    s = Stack()
    yield s
    s.queue.close()


def row(db, sql, *a):
    db.execute(sql, a)
    return db.fetchone()


def status(db, order_id):
    return row(db, "SELECT status FROM order_web3 WHERE order_id=%s", order_id)['status']


def legacy(db, order_id):
    return row(db, "SELECT status FROM orders WHERE id=%s", order_id)['status']


def seller_shop(db, n, price=100_000):
    sid = user(db, 'seller')
    db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (sid, ADDR[f'merchant{n}'].lower()))
    shop, pid = shop_with_product(db, sid, price=price)
    return sid, pid


def make_group(st, db, n_shops=2):
    """Buyer có ví + giỏ n shop; trả (buyer, group, [product_id])."""
    buyer = user(db)
    db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (buyer, ADDR['buyer'].lower()))
    items, pids = [], []
    for n in range(1, n_shops + 1):
        _, pid = seller_shop(db, n)
        pids.append(pid)
        items.append(cart_item(db, buyer, pid, 2))
    return buyer, st.quote.create_checkout(buyer, items), pids


def extra_group(st, db, buyer, n=3):
    """Lô thứ hai cho Buyer ĐÃ có ví (sản phẩm khác, shop khác)."""
    sid, pid = seller_shop(db, n)
    return st.quote.create_checkout(buyer, [cart_item(db, buyer, pid, 1)])


def locked_orders(st, db, n_shops=2):
    """Tạo lô, nạp tiền trên chuỗi giả cho MỌI đơn, chạy Indexer ⇒ các đơn LOCKED."""
    buyer, group, pids = make_group(st, db, n_shops)
    for o in group['orders']:
        st.chain.deposit(o['quote'])
    st.index()
    return buyer, group, pids


def new_shipper(db):
    return user(db, 'shipper')


def assign(st, db, order_id, shipper):
    admin = user(db, 'admin')
    return st.shipper.assign(admin, order_id, shipper)


# ------------------------------------------------------------------------------------------------ luồng thành công
def test_happy_path_deliver_then_auto_release_then_reconcile(st, db):
    buyer, group, _ = locked_orders(st, db)
    a, b = group['orders']
    shipper = new_shipper(db)
    assign(st, db, a['order_id'], shipper)
    assign(st, db, b['order_id'], shipper)
    assert status(db, a['order_id']) == 'LOCKED' and legacy(db, a['order_id']) == 'paid'

    listed = st.shipper.list_orders(shipper)['orders']
    assert {o['order_id'] for o in listed} == {a['order_id'], b['order_id']}
    assert all(o['status'] == 'LOCKED' and o['delivery_deadline'] == o['chain_created_at'] + 14 * DAY and o['delivered_at'] is None for o in listed)
    assert {'order_id', 'status', 'shop_name', 'buyer_name', 'price_vnd', 'chain_created_at', 'delivered_at'} <= set(listed[0])   # hợp đồng với giao diện A
    assert 'buyer_wallet' not in listed[0] and 'merchant_wallet' not in listed[0]       # không lộ ví

    # --- giao hàng đơn A: relayer gửi giao dịch, MySQL CHƯA đổi (BR-09), Indexer mới là người ghi
    res = st.shipper.deliver(shipper, a['order_id'])
    assert res['outcome'] == 'SENT' and res['tx_hash'] and res['status'] == 'LOCKED'
    assert st.chain.get_order_state(int(a['quote']['orderId'])) == 'DELIVERED'
    assert status(db, a['order_id']) == 'LOCKED'
    ob = row(db, "SELECT kind, status, tx_hash FROM tx_outbox WHERE order_id=%s", a['order_id'])
    assert (ob['kind'], ob['status']) == ('DELIVER', 'CONFIRMED') and ob['tx_hash'] == res['tx_hash']

    st.index()
    r = row(db, "SELECT status, delivered_at FROM order_web3 WHERE order_id=%s", a['order_id'])
    assert r['status'] == 'DELIVERED' and r['delivered_at'] == st.chain.now and legacy(db, a['order_id']) == 'shipped'
    assert status(db, b['order_id']) == 'LOCKED'                                         # đơn cùng lô không liên quan (BR-11)
    assert [o['order_id'] for o in st.shipper.list_orders(shipper)['orders']] == [b['order_id']]   # A rời danh sách LOCKED

    # --- UC-03 bước 3: thông báo Buyer kèm hạn khiếu nại, đúng MỘT lần dù Indexer chạy lại
    st.index()
    notes = st.notifications.list_for_user(buyer)['notifications']
    assert len(notes) == 1 and notes[0]['kind'] == 'ORDER_DELIVERED' and notes[0]['order_id'] == a['order_id']
    assert 'Đã nhận hàng' in notes[0]['message']

    # --- bấm giao lần nữa: idempotent, không gửi thêm giao dịch
    sent_before = len(st.chain.sent_txs)
    again = st.shipper.deliver(shipper, a['order_id'])
    assert again['outcome'] == 'ALREADY_DELIVERED' and again['tx_hash'] is None and len(st.chain.sent_txs) == sent_before

    # --- chưa hết hạn kiểm tra: AutoRelease không làm gì
    assert st.release.run_once() == {'released': 0, 'skipped': 0, 'failed': 0}
    st.chain.advance(INSPECTION - 1)
    assert st.release.run_once()['released'] == 0                                        # còn 1 giây

    # --- hết hạn: giải ngân tự động; chạy lại không gửi gì thêm
    st.chain.advance(1)
    assert st.release.run_once() == {'released': 1, 'skipped': 0, 'failed': 0}
    assert st.chain.get_order_state(int(a['quote']['orderId'])) == 'COMPLETED'
    assert status(db, a['order_id']) == 'DELIVERED'                                      # chưa Indexer
    st.index()
    r = row(db, "SELECT status, closed_at FROM order_web3 WHERE order_id=%s", a['order_id'])
    assert r['status'] == 'COMPLETED' and r['closed_at'] == st.chain.now and legacy(db, a['order_id']) == 'received'
    assert st.release.run_once()['released'] == 0
    kinds = [x['kind'] for x in db_all(db, "SELECT kind FROM tx_outbox ORDER BY id")]
    assert kinds == ['DELIVER', 'RELEASE']

    # --- đối soát: còn đơn B LOCKED, số dư contract = đúng số tiền của B
    rec = st.reconcile.run(deep=True)
    assert rec['ok'] and rec['status'] == 'OK' and rec['indexer_lag_blocks'] == 0 and rec['order_mismatches'] == []
    tok = rec['tokens'][0]
    assert tok['open_orders'] == 1 and tok['expected_raw'] == tok['balance_raw'] == str(int(b['quote']['amount']))


def db_all(db, sql, *a):
    db.execute(sql, a)
    return list(db.fetchall())


def test_buyer_early_release_makes_auto_release_a_noop(st, db):
    _, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    shipper = new_shipper(db)
    assign(st, db, o['order_id'], shipper)
    st.shipper.deliver(shipper, o['order_id'])
    st.index()
    st.chain.early_release(int(o['quote']['orderId']))        # Buyer bấm "Đã nhận hàng" (UC-04 kịch bản 1)
    st.chain.advance(INSPECTION)                              # DB vẫn DELIVERED (Indexer chưa chạy) nên đơn là ứng viên
    assert status(db, o['order_id']) == 'DELIVERED'
    assert st.release.run_once() == {'released': 0, 'skipped': 1, 'failed': 0}     # đọc chuỗi: đã COMPLETED, không gửi
    assert not any(t[0] == 'releaseAfterInspection' for t in st.chain.sent_txs)
    st.index()
    assert status(db, o['order_id']) == 'COMPLETED'
    assert st.reconcile.run()['ok']


def test_dispute_freezes_funds_auto_release_never_touches_disputed_order(st, db):
    _, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    shipper = new_shipper(db)
    assign(st, db, o['order_id'], shipper)
    st.shipper.deliver(shipper, o['order_id'])
    st.index()
    st.chain.raise_dispute(int(o['quote']['orderId']))
    st.index()
    r = row(db, "SELECT status, disputed_at FROM order_web3 WHERE order_id=%s", o['order_id'])
    assert r['status'] == 'DISPUTED' and r['disputed_at'] == st.chain.now and legacy(db, o['order_id']) == 'shipped'
    st.chain.advance(INSPECTION * 2)
    assert st.release.run_once() == {'released': 0, 'skipped': 0, 'failed': 0}
    assert st.chain.get_order_state(int(o['quote']['orderId'])) == 'DISPUTED'
    rec = st.reconcile.run(deep=True)
    assert rec['ok'] and rec['tokens'][0]['open_orders'] == 1          # DISPUTED vẫn là tiền đang giữ


def test_auto_release_survives_chain_revert_race(st, db):
    """Chuỗi báo DELIVERED + đủ hạn nhưng giao dịch vẫn revert (cạnh tranh): bỏ qua, ghi outbox FAILED, không ném lỗi."""
    _, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    shipper = new_shipper(db)
    assign(st, db, o['order_id'], shipper)
    st.shipper.deliver(shipper, o['order_id'])
    st.index()
    st.chain.advance(INSPECTION)
    real = st.chain.send_tx

    def reverting(fn, args, sender, sign):
        from slopee_web3.ports.chain_port import ChainTxFailed
        raise ChainTxFailed('execution reverted: Not delivered')
    st.chain.send_tx = reverting
    assert st.release.run_once() == {'released': 0, 'skipped': 0, 'failed': 1}
    assert row(db, "SELECT status FROM tx_outbox WHERE kind='RELEASE'")['status'] == 'FAILED'
    st.chain.send_tx = real
    assert st.release.run_once()['released'] == 1                       # lần sau tự thành công


# ------------------------------------------------------------------------------------------------ quyền & ca âm của cổng Shipper
def test_shipper_can_only_deliver_orders_assigned_to_them(st, db):
    _, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    mine, other = new_shipper(db), new_shipper(db)
    assign(st, db, o['order_id'], mine)
    with pytest.raises(DomainError) as e:
        st.shipper.deliver(other, o['order_id'])
    assert e.value.code == 'ORDER_NOT_FOUND'                            # không lộ sự tồn tại
    with pytest.raises(DomainError) as e:
        st.shipper.deliver(mine, 'khong-ton-tai')
    assert e.value.code == 'ORDER_NOT_FOUND'
    assert st.shipper.list_orders(other) == {'orders': []}
    assert st.chain.sent_txs == []
    assert st.chain.get_order_state(int(o['quote']['orderId'])) == 'LOCKED'


def test_cannot_deliver_before_deposit_or_after_completion(st, db):
    buyer, group, _ = make_group(st, db, 1)                             # chưa nạp: PENDING_PAYMENT
    o = group['orders'][0]
    shipper = new_shipper(db)
    assign(st, db, o['order_id'], shipper)                              # được phép gán trước khi nạp
    with pytest.raises(DomainError) as e:
        st.shipper.deliver(shipper, o['order_id'])
    assert e.value.code == 'INVALID_STATE' and e.value.extra['status'] == 'PENDING_PAYMENT'
    st.chain.deposit(o['quote'])
    st.index()
    st.shipper.deliver(shipper, o['order_id'])
    st.index()
    st.chain.advance(INSPECTION)
    st.release.run_once()
    st.index()
    with pytest.raises(DomainError) as e:
        st.shipper.deliver(shipper, o['order_id'])
    assert e.value.code == 'INVALID_STATE' and e.value.extra['status'] == 'COMPLETED'


def test_assign_requires_a_real_shipper_account_and_undelivered_order(st, db):
    _, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    admin = user(db, 'admin')
    with pytest.raises(DomainError) as e:
        st.shipper.assign(admin, o['order_id'], user(db, 'user'))      # không phải shipper
    assert e.value.code == 'INVALID_SHIPPER'
    with pytest.raises(DomainError) as e:
        st.shipper.assign(admin, o['order_id'], 'khong-co-user')
    assert e.value.code == 'INVALID_SHIPPER'
    with pytest.raises(DomainError) as e:
        st.shipper.assign(admin, 'khong-co-don', new_shipper(db))
    assert e.value.code == 'ORDER_NOT_FOUND'
    s1, s2 = new_shipper(db), new_shipper(db)
    st.shipper.assign(admin, o['order_id'], s1)
    st.shipper.assign(admin, o['order_id'], s2)                         # đổi Shipper khi chưa giao: được
    assert st.shipper.list_orders(s1) == {'orders': []} and len(st.shipper.list_orders(s2)['orders']) == 1
    st.shipper.deliver(s2, o['order_id'])
    st.index()
    with pytest.raises(DomainError) as e:
        st.shipper.assign(admin, o['order_id'], s1)                     # đã giao: không đổi được
    assert e.value.code == 'INVALID_STATE'


# ------------------------------------------------------------------------------------------------ QuoteExpirySweeper
def test_sweeper_expires_whole_group_and_restores_stock_after_grace(st, db):
    buyer, group, pids = make_group(st, db, 2)
    stock = lambda pid: row(db, "SELECT inStock FROM products WHERE id=%s", pid)['inStock']
    assert [stock(p) for p in pids] == [8, 8]                           # đã giữ chỗ
    deadline = int(group['orders'][0]['quote']['deadline'])
    st.chain.advance(deadline - st.chain.now + 30)                      # đúng hạn + đúng đệm: CHƯA hết hạn
    assert st.sweeper.run_once() == {'groups_expired': 0, 'orders_expired': 0, 'skipped': 0}
    st.chain.advance(1)
    assert st.sweeper.run_once() == {'groups_expired': 1, 'orders_expired': 2, 'skipped': 0}
    for o in group['orders']:
        assert status(db, o['order_id']) == 'EXPIRED' and legacy(db, o['order_id']) == 'cancelled'
    assert [stock(p) for p in pids] == [10, 10]                         # hoàn kho
    assert st.sweeper.run_once()['orders_expired'] == 0                 # idempotent: không hoàn kho lần hai
    assert [stock(p) for p in pids] == [10, 10]


def test_sweeper_never_expires_an_order_that_is_already_on_chain(st, db):
    """Buyer đã nạp trước hạn nhưng Indexer chưa kịp: Sweeper đọc chuỗi (≠ NONE) nên KHÔNG được EXPIRED (tiền sẽ kẹt)."""
    _, group, pids = make_group(st, db, 1)
    o = group['orders'][0]
    st.chain.deposit(o['quote'])
    st.chain.advance(5000)                                              # quá hạn báo giá từ lâu
    assert st.sweeper.run_once() == {'groups_expired': 0, 'orders_expired': 0, 'skipped': 1}
    assert status(db, o['order_id']) == 'PENDING_PAYMENT'
    st.index()
    assert status(db, o['order_id']) == 'LOCKED'                        # Indexer khóa đơn bình thường, không anomaly
    assert row(db, "SELECT anomaly_flag FROM order_web3 WHERE order_id=%s", o['order_id'])['anomaly_flag'] == 0
    assert row(db, "SELECT inStock FROM products WHERE id=%s", pids[0])['inStock'] == 8


def test_sweeper_skips_group_when_buyer_requoted_and_expired_group_can_requote(st, db):
    buyer, group, pids = make_group(st, db, 1)
    o = group['orders'][0]
    st.chain.advance(2000)
    regrouped = st.quote.reissue_group_quotes(buyer, group['checkout_group_id'])      # còn hạn mới
    assert st.sweeper.run_once()['orders_expired'] == 0
    assert status(db, o['order_id']) == 'PENDING_PAYMENT' and int(regrouped['orders'][0]['quote']['deadline']) > st.chain.now
    st.chain.advance(2000)
    assert st.sweeper.run_once()['orders_expired'] == 1
    assert row(db, "SELECT inStock FROM products WHERE id=%s", pids[0])['inStock'] == 10
    st.quote.reissue_group_quotes(buyer, group['checkout_group_id'])                    # EXPIRED -> xin báo giá mới (UC-01)
    assert status(db, o['order_id']) == 'PENDING_PAYMENT'
    assert row(db, "SELECT inStock FROM products WHERE id=%s", pids[0])['inStock'] == 8


def test_sweeper_does_nothing_when_chain_is_down(st, db):
    _, group, _ = make_group(st, db, 1)
    st.chain.advance(2000)
    st.chain.available = False
    from slopee_web3.ports.chain_port import ChainUnavailable
    with pytest.raises(ChainUnavailable):
        st.sweeper.run_once()
    st.chain.available = True
    assert status(db, group['orders'][0]['order_id']) == 'PENDING_PAYMENT'             # không đoán khi không kiểm chứng được


# ------------------------------------------------------------------------------------------------ DeliveryTimeoutReminder
def test_reminder_sends_once_after_14_days_only_while_locked_on_chain(st, db):
    buyer, group, _ = locked_orders(st, db, 2)
    a, b = group['orders']
    st.chain.advance(14 * DAY - 1)
    assert st.reminder.run_once() == {'reminded': 0, 'skipped': 0}
    st.chain.advance(1)
    st.chain.cancel_if_unfulfilled(int(b['quote']['orderId']))          # Buyer đã hủy B trên chuỗi, Indexer chưa kịp
    assert st.reminder.run_once() == {'reminded': 1, 'skipped': 1}      # chỉ nhắc A
    assert st.reminder.run_once() == {'reminded': 0, 'skipped': 1}      # không nhắc lặp
    notes = st.notifications.list_for_user(buyer)['notifications']
    assert [n['kind'] for n in notes] == ['DELIVERY_TIMEOUT'] and notes[0]['order_id'] == a['order_id']
    assert '14 ngày' in notes[0]['message']


def test_refunded_event_restores_stock_and_cancels_legacy_order(st, db):
    _, group, pids = locked_orders(st, db, 1)
    o = group['orders'][0]
    assert row(db, "SELECT inStock FROM products WHERE id=%s", pids[0])['inStock'] == 8
    st.chain.advance(14 * DAY)
    st.chain.cancel_if_unfulfilled(int(o['quote']['orderId']))
    st.index()
    r = row(db, "SELECT status, closed_at FROM order_web3 WHERE order_id=%s", o['order_id'])
    assert r['status'] == 'REFUNDED' and r['closed_at'] == st.chain.now and legacy(db, o['order_id']) == 'cancelled'
    assert row(db, "SELECT inStock FROM products WHERE id=%s", pids[0])['inStock'] == 10
    st.index()                                                           # chạy lại: không hoàn kho hai lần
    assert row(db, "SELECT inStock FROM products WHERE id=%s", pids[0])['inStock'] == 10
    rec = st.reconcile.run()
    assert rec['ok'] and rec['tokens'][0]['open_orders'] == 0 and rec['tokens'][0]['balance_raw'] == '0'


# ------------------------------------------------------------------------------------------------ đối soát
def test_reconcile_detects_money_outside_the_order_flow(st, db):
    _, group, _ = locked_orders(st, db, 1)
    assert st.reconcile.run()['ok']
    st.chain.stray_transfer(777)
    assert st.reconcile.run()['ok']              # số dư đọc TẠI block con trỏ: Indexer chưa đi qua block này nên chưa thấy
    st.index()                                   # Indexer quét liên tục (mỗi 2 giây) nên khoản lạ lộ ra ngay sau đó
    rec = st.reconcile.run()
    assert not rec['ok'] and rec['status'] == 'MISMATCH' and rec['tokens'][0]['diff_raw'] == '777'


def test_reconcile_is_exact_even_while_indexer_is_behind(st, db):
    """Số dư đọc TẠI block con trỏ: một lần nạp mới chưa được Indexer xử lý không được gây báo lệch giả."""
    buyer, group, _ = locked_orders(st, db, 1)
    group2 = extra_group(st, db, buyer)
    st.chain.deposit(group2['orders'][0]['quote'])                      # đã vào chuỗi, Indexer chưa chạy
    rec = st.reconcile.run(deep=True)
    assert rec['ok'] and rec['indexer_lag_blocks'] == 1
    assert rec['order_mismatches'] is None                              # đang trễ: bỏ qua so từng đơn (tránh dương tính giả)
    st.index()
    assert st.reconcile.run(deep=True)['tokens'][0]['open_orders'] == 2


def test_reconcile_deep_flags_order_whose_status_differs_from_chain(st, db):
    _, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    db.execute("UPDATE order_web3 SET status='DELIVERED' WHERE order_id=%s", (o['order_id'],))      # DB bị sửa tay
    rec = st.reconcile.run(deep=True)
    assert rec['order_mismatches'] == [{'order_id': o['order_id'], 'onchain_order_id': int(o['quote']['orderId']),
                                        'db_status': 'DELIVERED', 'chain_state': 'LOCKED'}]
    assert not rec['ok']


def test_reconcile_with_no_orders_still_checks_configured_token(st, db):
    rec = st.reconcile.run()
    assert rec['indexer_cursor_missing'] and rec['ok'] and rec['tokens'][0]['token'] == TOKEN.lower()
    st.chain.stray_transfer(5)
    st.index()
    assert not st.reconcile.run()['ok']


def test_reconcile_includes_deferred_payouts(st, db):
    _, group, _ = locked_orders(st, db, 1)
    zero = '0x' + '0' * 40
    st.chain.defer_payout(zero, ADDR['merchant1'], 40)
    st.chain.claim_pending(zero, ADDR['merchant1'])
    st.index()
    assert row(db, "SELECT amount_raw FROM pending_balances WHERE address=%s", ADDR['merchant1'].lower())['amount_raw'] == '0'


# ------------------------------------------------------------------------------------------------ Indexer: ca bất thường
def test_delivered_event_for_expired_order_only_flags_anomaly(st, db):
    _, group, _ = make_group(st, db, 1)
    o = group['orders'][0]
    st.chain.advance(2000)
    st.sweeper.run_once()
    assert status(db, o['order_id']) == 'EXPIRED'
    st.chain.deposit(o['quote'])                                        # nạp "muộn" (lọt qua hạn): tiền vào, đơn đã EXPIRED
    st.chain.send_tx('confirmDelivery', [int(o['quote']['orderId'])], 'x', lambda tx: b'\x01')
    st.index()
    r = row(db, "SELECT status, anomaly_flag FROM order_web3 WHERE order_id=%s", o['order_id'])
    assert r['status'] == 'EXPIRED' and r['anomaly_flag'] == 1          # không lùi/đổi trạng thái, chỉ báo Admin
    assert st.reconcile.run()['anomalies'][0]['order_id'] == o['order_id']
