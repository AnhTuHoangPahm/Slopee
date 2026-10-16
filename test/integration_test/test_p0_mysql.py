"""P0-03…06 trên MySQL THẬT (tự skip nếu không có MySQL; CI chạy với MySQL service).

Phần mock không kiểm được: FOR UPDATE thật, khóa chéo (deadlock), strict mode (S-13), SQL của migration.
"""
import threading
import uuid

import pytest
from werkzeug.security import generate_password_hash

import dbschema
import migrate
from auth_utils import issue_token

pytestmark = pytest.mark.mysql

PIN = "123456"


def _user(cur, role='user', pw='pw12345', pin=PIN):
    uid = str(uuid.uuid4())
    cur.execute("INSERT INTO users (id, role, name, email, phone) VALUES (%s,%s,%s,%s,%s)",
                (uid, role, f"{role}-{uid[:6]}", f"{uid[:12]}@t.io", uid.replace('-', '')[:10]))
    cur.execute("INSERT INTO credentials (userId, username, passwordHash, passwordSalt, passPhraseHash) VALUES (%s,%s,%s,%s,%s)",
                (uid, f"u{uid[:10]}", generate_password_hash(pw), "x", generate_password_hash(pin) if pin else None))
    return uid


def _bank(cur, uid, balance=0):
    pm = str(uuid.uuid4())
    cur.execute("INSERT INTO paymentMethods (id, userId, methodType, providerName, accountNumber, balance) VALUES (%s,%s,'bank','B','1',%s)",
                (pm, uid, balance))
    return pm


def _shop_product(cur, seller, stock=5, price=100000):
    shop = str(uuid.uuid4())
    cur.execute("INSERT INTO shops (id, sellerId, name) VALUES (%s,%s,'S')", (shop, seller))
    cur.execute("INSERT INTO categories (name) VALUES ('c')")
    prod = uuid.uuid4().hex[:15]
    cur.execute("INSERT INTO products (id, categoryId, shopId, name, inStock, unitPrice, isActive) VALUES (%s,%s,%s,'P',%s,%s,TRUE)",
                (prod, cur.lastrowid, shop, stock, price))
    return prod


def _cart_item(cur, buyer, prod, qty=1):
    cart = str(uuid.uuid4())
    cur.execute("INSERT INTO carts (id, userId) VALUES (%s,%s)", (cart, buyer))
    item = str(uuid.uuid4())
    cur.execute("INSERT INTO cartItems (id, cartId, productId, quantity, selectedVariants) VALUES (%s,%s,%s,%s,'{}')",
                (item, cart, prod, qty))
    return item


def _h(uid, role='user'):
    return {'Authorization': f"Bearer {issue_token(uid, role)}"}


def _order(cur, uid, status='paid'):
    oid = str(uuid.uuid4())
    cur.execute("INSERT INTO orders (id, userId, status, totalAmount) VALUES (%s,%s,%s,1000)", (oid, uid, status))
    return oid


# ------------------------------------------------------------------ P0-03: sở hữu đơn
def test_order_update_ownership_and_transitions(app, db_conn):
    cur = db_conn.cursor()
    owner, other = _user(cur), _user(cur)
    oid = _order(cur, owner, 'paid')
    c = app.test_client()
    assert c.put(f'/api/checkout/orders/{oid}', headers=_h(other), json={"status": "cancelled"}).status_code == 404
    cur.execute("SELECT status FROM orders WHERE id=%s", (oid,))
    assert cur.fetchone()['status'] == 'paid'
    assert c.put(f'/api/checkout/orders/{oid}', headers=_h(owner), json={"status": "received"}).status_code == 200
    r = c.put(f'/api/checkout/orders/{oid}', headers=_h(owner), json={"status": "cancelled"})
    assert r.status_code == 409 and r.get_json()['code'] == 'INVALID_STATE'


def test_order_with_order_web3_row_is_rejected(app, db_conn):
    """Dùng bảng `order_web3` THẬT (migration 0008) thay vì bảng tối thiểu tự tạo như trước tuần 2."""
    cur = db_conn.cursor()
    owner = _user(cur)
    merchant = _user(cur, 'seller', pin=None)
    oid = _order(cur, owner, 'paid')
    group = str(uuid.uuid4())
    cur.execute("INSERT INTO checkout_groups (group_id, buyer_user_id, token_address, total_amount_raw, order_count) "
                "VALUES (%s,%s,NULL,'1000000',1)", (group, owner))
    try:
        cur.execute("INSERT INTO order_web3 (order_id, onchain_order_id, buyer_user_id, merchant_user_id, shop_id, "
                    "checkout_group_id, buyer_wallet, merchant_wallet, amount_raw, price_vnd, fx_vnd_per_token, "
                    "fee_bps, inspection_duration, dispute_timeout, doc_hash, status) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'1000000',100000,25000.0000,300,259200,2592000,%s,'LOCKED')",
                    (oid, 900000 + int(oid[:6], 16) % 99999, owner, merchant, str(uuid.uuid4()), group,
                     '0x' + 'a' * 40, '0x' + 'b' * 40, '0x' + 'c' * 64))
        r = app.test_client().put(f'/api/checkout/orders/{oid}', headers=_h(owner), json={"status": "received"})
        assert r.status_code == 409 and r.get_json()['code'] == 'WEB3_ORDER_MANAGED'
    finally:
        cur.execute("DELETE FROM order_web3 WHERE order_id=%s", (oid,))
        cur.execute("DELETE FROM checkout_groups WHERE group_id=%s", (group,))


# ------------------------------------------------------------------ P0-05: khóa dòng
def test_same_cart_checked_out_twice_concurrently_creates_one_order(app, db_conn):
    cur = db_conn.cursor()
    seller, buyer = _user(cur, 'seller', pin=None), _user(cur)
    _bank(cur, seller)
    pm = _bank(cur, buyer, 10_000_000)
    prod = _shop_product(cur, seller, stock=10)
    item = _cart_item(cur, buyer, prod)
    statuses, barrier = [None, None], threading.Barrier(2)

    def go(i):
        barrier.wait()
        statuses[i] = app.test_client().post('/api/checkout/checkout', headers=_h(buyer),
                                             json={"paymentMethodId": pm, "passPhrase": PIN, "cartItemIds": [item]}).status_code
    ts = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    [t.start() for t in ts]
    [t.join(timeout=60) for t in ts]
    assert sorted(statuses) == [200, 400]
    cur.execute("SELECT COUNT(*) AS c FROM orders WHERE userId=%s", (buyer,))
    assert cur.fetchone()['c'] == 1
    cur.execute("SELECT inStock FROM products WHERE id=%s", (prod,))
    assert cur.fetchone()['inStock'] == 9


def test_crossed_checkouts_do_not_deadlock(app, db_conn):
    """X mua hàng của Y trong khi Y mua hàng của X: thứ tự khóa cố định nên không deadlock, cả hai đều thành công."""
    cur = db_conn.cursor()
    for _ in range(5):
        x, y = _user(cur, 'seller'), _user(cur, 'seller')
        pm_x, pm_y = _bank(cur, x, 5_000_000), _bank(cur, y, 5_000_000)
        px, py = _shop_product(cur, x), _shop_product(cur, y)
        ix, iy = _cart_item(cur, x, py), _cart_item(cur, y, px)
        res, barrier = {}, threading.Barrier(2)

        def go(name, uid, pm, item):
            barrier.wait()
            res[name] = app.test_client().post('/api/checkout/checkout', headers=_h(uid, 'seller'),
                                               json={"paymentMethodId": pm, "passPhrase": PIN, "cartItemIds": [item]}).status_code
        ts = [threading.Thread(target=go, args=('x', x, pm_x, ix)), threading.Thread(target=go, args=('y', y, pm_y, iy))]
        [t.start() for t in ts]
        [t.join(timeout=60) for t in ts]
        assert res == {'x': 200, 'y': 200}, res


# ------------------------------------------------------------------ A-06 trên DB thật
def test_login_lockout_end_to_end(app, db_conn, monkeypatch):
    monkeypatch.setenv('AUTH_LOCK_SECONDS', '60')
    cur = db_conn.cursor()
    uid = _user(cur, pw='rightpass')
    cur.execute("SELECT username FROM credentials WHERE userId=%s", (uid,))
    username = cur.fetchone()['username']
    c = app.test_client()
    for _ in range(5):
        assert c.post('/api/auth/login', json={"username": username, "password": "bad"}).status_code == 401
    r = c.post('/api/auth/login', json={"username": username, "password": "rightpass"})
    assert r.status_code == 429 and int(r.headers['Retry-After']) <= 60
    cur.execute("UPDATE authAttempts SET lockedUntil = 1 WHERE subject=%s", (f"id:{uid}",))  # giả lập hết hạn khóa
    assert c.post('/api/auth/login', json={"username": username, "password": "rightpass"}).status_code == 200
    cur.execute("SELECT COUNT(*) AS c FROM authAttempts WHERE subject=%s", (f"id:{uid}",))
    assert cur.fetchone()['c'] == 0


def test_wrong_pin_lockout_end_to_end(app, db_conn):
    cur = db_conn.cursor()
    seller, buyer = _user(cur, 'seller', pin=None), _user(cur)
    _bank(cur, seller)
    pm = _bank(cur, buyer, 1_000_000)
    item = _cart_item(cur, buyer, _shop_product(cur, seller))
    c = app.test_client()
    body = {"paymentMethodId": pm, "passPhrase": "000000", "cartItemIds": [item]}
    assert [c.post('/api/checkout/checkout', headers=_h(buyer), json=body).status_code for _ in range(6)] == [401] * 5 + [429]


def test_account_without_pin_returns_401(app, db_conn):
    cur = db_conn.cursor()
    uid = _user(cur, 'seller', pin=None)
    r = app.test_client().post('/api/checkout/checkout', headers=_h(uid, 'seller'),
                               json={"paymentMethodId": "CASH_ON_DELIVERY", "passPhrase": PIN, "cartItemIds": ["x"]})
    assert r.status_code == 401 and r.get_json()['code'] == 'pin_not_set'


# ------------------------------------------------------------------ S-13: ảnh đánh giá ở strict mode
def test_review_with_images_succeeds_on_strict_mysql(app, db_conn):
    cur = db_conn.cursor()
    seller, buyer = _user(cur, 'seller', pin=None), _user(cur)
    prod = _shop_product(cur, seller)
    oid = _order(cur, buyer, 'received')
    cur.execute("INSERT INTO orderLines (id, orderId, productId, unitPrice, quantity) VALUES (%s,%s,%s,1000,1)",
                (str(uuid.uuid4()), oid, prod))
    r = app.test_client().post(f'/api/reviews/{prod}', headers=_h(buyer),
                               json={"rating": 5, "comment": "ok", "images": ["https://i.io/1.png", "https://i.io/2.png"]})
    assert r.status_code == 201, r.get_json()
    cur.execute("SELECT COUNT(*) AS c FROM reviewImages WHERE reviewId=%s", (r.get_json()['reviewId'],))
    assert cur.fetchone()['c'] == 2


# ------------------------------------------------------------------ P0-04: migration trên DB thật
def test_fresh_database_has_all_migrations_marked_applied(mysql_db, db_conn):
    cur = db_conn.cursor()
    assert migrate.pending(cur) == []                      # init_db đã baseline
    assert migrate.migrate(db_conn, log=lambda *_: None) == []


def test_python_migrations_are_idempotent_on_current_schema(mysql_db, db_conn):
    """0002/0003 chạy lại trên schema mới không đổi gì và không lỗi (kiểm tra SQL information_schema thật)."""
    import importlib.util, os
    cur = db_conn.cursor()
    for name in ('0002_product_fk_snapshots.py', '0003_reviews_dedupe.py'):
        path = os.path.join(os.path.dirname(migrate.__file__), 'migrations', name)
        spec = importlib.util.spec_from_file_location('m_' + name[:4], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.upgrade(cur)
        mod.upgrade(cur)
    assert dbschema.foreign_keys(cur, 'cartItems', 'productId', 'products')[0]['delete_rule'] == 'CASCADE'
    assert dbschema.foreign_keys(cur, 'orderLines', 'productId', 'products')[0]['delete_rule'] == 'SET NULL'
    assert dbschema.foreign_keys(cur, 'reviews', 'userId', 'users')[0]['delete_rule'] == 'CASCADE'
    assert dbschema.index_exists(cur, 'reviews', 'uniqueReview')


def test_deleting_product_keeps_order_history(app, db_conn):
    cur = db_conn.cursor()
    seller, buyer = _user(cur, 'seller', pin=None), _user(cur)
    prod = _shop_product(cur, seller)
    oid = _order(cur, buyer, 'paid')
    cur.execute("INSERT INTO orderLines (id, orderId, productId, unitPrice, quantity, snapshotProductName) VALUES (%s,%s,%s,1000,1,'P')",
                (str(uuid.uuid4()), oid, prod))
    assert app.test_client().delete(f'/api/shop/products/{prod}', headers=_h(seller, 'seller')).status_code == 200
    cur.execute("SELECT productId, snapshotProductName FROM orderLines WHERE orderId=%s", (oid,))
    row = cur.fetchone()
    assert row['productId'] is None and row['snapshotProductName'] == 'P'


# ================================================================== Quyết định nhóm sau Phase 0 (MySQL thật)
def _balance(cur, pm):
    cur.execute("SELECT balance FROM paymentMethods WHERE id=%s", (pm,))
    return int(cur.fetchone()['balance'])


def _stock(cur, prod):
    cur.execute("SELECT inStock FROM products WHERE id=%s", (prod,))
    return cur.fetchone()['inStock']


def _checkout(app, buyer, pm, item):
    return app.test_client().post('/api/checkout/checkout', headers=_h(buyer),
                                  json={"paymentMethodId": pm, "passPhrase": PIN, "cartItemIds": [item]})


def _cancel_order(app, buyer, order_id):
    return app.test_client().put(f'/api/checkout/orders/{order_id}', headers=_h(buyer), json={"status": "cancelled"})


def _latest_order(cur, buyer, status=None):
    # created_at chỉ chính xác tới giây: khi cần "đơn vừa tạo" trong vòng lặp thì lọc theo status
    cur.execute("SELECT id, status FROM orders WHERE userId=%s AND (%s IS NULL OR status=%s) ORDER BY created_at DESC LIMIT 1",
                (buyer, status, status))
    return cur.fetchone()


def test_cancel_paid_bank_order_refunds_restocks_and_conserves_money(app, db_conn):
    cur = db_conn.cursor()
    seller, buyer = _user(cur, 'seller', pin=None), _user(cur)
    seller_pm, buyer_pm = _bank(cur, seller, 0), _bank(cur, buyer, 1_000_000)
    prod = _shop_product(cur, seller, stock=5, price=100_000)
    item = _cart_item(cur, buyer, prod, qty=2)

    assert _checkout(app, buyer, buyer_pm, item).status_code == 200
    assert (_balance(cur, buyer_pm), _balance(cur, seller_pm), _stock(cur, prod)) == (800_000, 200_000, 3)

    order = _latest_order(cur, buyer)
    r = _cancel_order(app, buyer, order['id'])
    assert r.status_code == 200 and r.get_json()['refunded'] == 200_000
    assert (_balance(cur, buyer_pm), _balance(cur, seller_pm), _stock(cur, prod)) == (1_000_000, 0, 5)   # đúng như chưa mua
    assert _latest_order(cur, buyer)['status'] == 'cancelled'
    # Hủy lần hai: không hoàn thêm
    assert _cancel_order(app, buyer, order['id']).status_code == 409
    assert (_balance(cur, buyer_pm), _balance(cur, seller_pm), _stock(cur, prod)) == (1_000_000, 0, 5)


def test_cancel_is_rejected_when_seller_already_spent_the_money(app, db_conn):
    cur = db_conn.cursor()
    seller, buyer = _user(cur, 'seller', pin=None), _user(cur)
    seller_pm, buyer_pm = _bank(cur, seller, 0), _bank(cur, buyer, 1_000_000)
    prod = _shop_product(cur, seller, stock=5, price=100_000)
    item = _cart_item(cur, buyer, prod, qty=1)
    assert _checkout(app, buyer, buyer_pm, item).status_code == 200
    cur.execute("UPDATE paymentMethods SET balance = 0 WHERE id=%s", (seller_pm,))   # người bán đã tiêu hết

    order = _latest_order(cur, buyer)
    r = _cancel_order(app, buyer, order['id'])
    assert r.status_code == 409 and r.get_json()['code'] == 'refund_unavailable'
    # Rollback trọn vẹn: đơn vẫn paid, tiền và kho không đổi (không có tiền được tạo ra)
    assert _latest_order(cur, buyer)['status'] == 'paid'
    assert (_balance(cur, buyer_pm), _balance(cur, seller_pm), _stock(cur, prod)) == (900_000, 0, 4)


def test_cod_checkout_creates_no_money_and_cancel_only_restocks(app, db_conn):
    cur = db_conn.cursor()
    seller, buyer = _user(cur, 'seller', pin=None), _user(cur)
    seller_pm = _bank(cur, seller, 0)
    prod = _shop_product(cur, seller, stock=5, price=100_000)
    item = _cart_item(cur, buyer, prod, qty=2)

    assert _checkout(app, buyer, 'CASH_ON_DELIVERY', item).status_code == 200
    assert _balance(cur, seller_pm) == 0 and _stock(cur, prod) == 3          # COD không cộng tiền cho người bán

    order = _latest_order(cur, buyer)
    r = _cancel_order(app, buyer, order['id'])
    assert r.status_code == 200 and r.get_json()['refunded'] == 0
    assert _balance(cur, seller_pm) == 0 and _stock(cur, prod) == 5


def test_cash_type_method_checkout_creates_no_money(app, db_conn):
    cur = db_conn.cursor()
    seller, buyer = _user(cur, 'seller', pin=None), _user(cur)
    seller_pm = _bank(cur, seller, 0)
    cash_pm = str(uuid.uuid4())
    cur.execute("INSERT INTO paymentMethods (id, userId, methodType, providerName, accountNumber, balance) VALUES (%s,%s,'cash','C','1',0)",
                (cash_pm, buyer))
    item = _cart_item(cur, buyer, _shop_product(cur, seller, price=100_000), qty=1)
    assert _checkout(app, buyer, cash_pm, item).status_code == 200
    assert _balance(cur, seller_pm) == 0


def test_two_concurrent_cancels_refund_exactly_once(app, db_conn):
    cur = db_conn.cursor()
    seller, buyer = _user(cur, 'seller', pin=None), _user(cur)
    seller_pm, buyer_pm = _bank(cur, seller, 0), _bank(cur, buyer, 1_000_000)
    prod = _shop_product(cur, seller, stock=5, price=100_000)
    item = _cart_item(cur, buyer, prod, qty=1)
    assert _checkout(app, buyer, buyer_pm, item).status_code == 200
    oid = _latest_order(cur, buyer)['id']

    statuses, barrier = [None, None], threading.Barrier(2)

    def go(i):
        barrier.wait()
        statuses[i] = _cancel_order(app, buyer, oid).status_code
    ts = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    [t.start() for t in ts]
    [t.join(timeout=60) for t in ts]
    assert sorted(statuses) == [200, 409], statuses
    assert (_balance(cur, buyer_pm), _balance(cur, seller_pm), _stock(cur, prod)) == (1_000_000, 0, 5)


def test_concurrent_cancel_and_checkout_do_not_deadlock(app, db_conn):
    """Hủy đơn (products -> paymentMethods) và checkout (cartItems -> products -> paymentMethods) cùng thứ tự khóa."""
    cur = db_conn.cursor()
    seller, buyer, other = _user(cur, 'seller', pin=None), _user(cur), _user(cur)
    _bank(cur, seller, 0)
    buyer_pm, other_pm = _bank(cur, buyer, 5_000_000), _bank(cur, other, 5_000_000)
    prod = _shop_product(cur, seller, stock=50, price=100_000)
    for _ in range(4):
        item = _cart_item(cur, buyer, prod, qty=1)
        assert _checkout(app, buyer, buyer_pm, item).status_code == 200
        oid = _latest_order(cur, buyer, 'paid')['id']
        item2 = _cart_item(cur, other, prod, qty=1)
        res, barrier = {}, threading.Barrier(2)

        def cancel():
            barrier.wait()
            res['cancel'] = _cancel_order(app, buyer, oid).status_code

        def buy():
            barrier.wait()
            res['buy'] = _checkout(app, other, other_pm, item2).status_code
        ts = [threading.Thread(target=cancel), threading.Thread(target=buy)]
        [t.start() for t in ts]
        [t.join(timeout=60) for t in ts]
        assert res == {'cancel': 200, 'buy': 200}, res


def test_admin_delete_user_with_orders_is_409_and_without_orders_is_200(app, db_conn):
    cur = db_conn.cursor()
    admin, with_orders, no_orders = _user(cur, 'admin', pin=None), _user(cur), _user(cur)
    _order(cur, with_orders, 'paid')
    c = app.test_client()
    r = c.delete(f'/api/admin/users/{with_orders}', headers=_h(admin, 'admin'))
    assert r.status_code == 409 and r.get_json()['code'] == 'user_has_orders'
    cur.execute("SELECT COUNT(*) AS c FROM users WHERE id=%s", (with_orders,))
    assert cur.fetchone()['c'] == 1                                            # FK RESTRICT được giữ, user còn nguyên
    assert c.delete(f'/api/admin/users/{no_orders}', headers=_h(admin, 'admin')).status_code == 200


def test_orders_user_fk_is_still_restrict(mysql_db, db_conn):
    cur = db_conn.cursor()
    assert [f['delete_rule'] for f in dbschema.foreign_keys(cur, 'orders', 'userId', 'users')] == ['RESTRICT']


def test_migration_0005_backfills_legacy_orders_and_is_idempotent(mysql_db, db_conn):
    import importlib.util
    import os
    cur = db_conn.cursor()
    seller, buyer = _user(cur, 'seller', pin=None), _user(cur)
    seller_pm, buyer_pm = _bank(cur, seller, 0), _bank(cur, buyer, 0)
    prod = _shop_product(cur, seller, price=100_000)
    # Dữ liệu CŨ: đơn đã thanh toán bằng bank (seller đã được cộng), đơn COD (buyer không bị trừ)
    bank_order, cod_order = _order(cur, buyer, 'paid'), _order(cur, buyer, 'paid')
    cur.execute("UPDATE orders SET paymentMethodId=%s WHERE id=%s", (buyer_pm, bank_order))
    for oid in (bank_order, cod_order):
        cur.execute("INSERT INTO orderLines (id, orderId, productId, unitPrice, quantity) VALUES (%s,%s,%s,100000,3)",
                    (str(uuid.uuid4()), oid, prod))
    # Đưa schema về trạng thái trước migration 0005
    for fk in dbschema.foreign_keys(cur, 'orderLines', 'sellerPaymentMethodId', 'paymentMethods'):
        cur.execute(f"ALTER TABLE orderLines DROP FOREIGN KEY `{fk['name']}`")
    cur.execute("ALTER TABLE orderLines DROP COLUMN sellerPaymentMethodId, DROP COLUMN sellerCredit")

    path = os.path.join(os.path.dirname(migrate.__file__), 'migrations', '0005_order_line_settlement.py')
    spec = importlib.util.spec_from_file_location('m0005', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.upgrade(cur)

    cur.execute("SELECT orderId, sellerPaymentMethodId, sellerCredit FROM orderLines WHERE orderId IN (%s,%s)", (bank_order, cod_order))
    rows = {r['orderId']: r for r in cur.fetchall()}
    assert (rows[bank_order]['sellerPaymentMethodId'], int(rows[bank_order]['sellerCredit'])) == (seller_pm, 300_000)
    assert (rows[cod_order]['sellerPaymentMethodId'], int(rows[cod_order]['sellerCredit'])) == (None, 0)

    cur.execute("UPDATE orderLines SET sellerCredit = 7 WHERE orderId=%s", (bank_order,))
    mod.upgrade(cur)                                                            # chạy lại: không ghi đè, không lỗi
    cur.execute("SELECT sellerCredit FROM orderLines WHERE orderId=%s", (bank_order,))
    assert int(cur.fetchone()['sellerCredit']) == 7
    assert len(dbschema.foreign_keys(cur, 'orderLines', 'sellerPaymentMethodId', 'paymentMethods')) == 1
