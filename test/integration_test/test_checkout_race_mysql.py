"""Race condition khi checkout, chạy trên MySQL service THẬT (P0-08).

Nhiều người mua cùng giành món hàng còn ít tồn kho. Bất biến cần giữ (đúng cả trước và sau P0-05):
  * số đơn thành công == tồn kho ban đầu (không bán lố), tồn kho cuối >= 0
  * mỗi người mua chỉ bị trừ tiền đúng khi đơn của họ thành công
  * người bán nhận đúng tổng tiền các đơn thành công
Sau khi P0-05 (SELECT ... FOR UPDATE) xong, request thua cuộc nên trả 400 thay vì 500;
test chỉ yêu cầu "không phải 200" để không gắn chặt vào chi tiết triển khai.
"""
import threading
import uuid

import pytest
from werkzeug.security import generate_password_hash

from auth_utils import issue_token

pytestmark = pytest.mark.mysql

PRICE = 150000
BALANCE = 1000000
PIN = "123456"


def _seed_user(cur, role, pin=True):
    uid = str(uuid.uuid4())
    cur.execute("INSERT INTO users (id, role, name, email, phone) VALUES (%s,%s,%s,%s,%s)",
                (uid, role, f"{role}-{uid[:6]}", f"{uid[:12]}@t.io", uid.replace('-', '')[:10]))
    cur.execute("INSERT INTO credentials (userId, username, passwordHash, passwordSalt, passPhraseHash) VALUES (%s,%s,%s,%s,%s)",
                (uid, f"u{uid[:10]}", generate_password_hash("pw"), "x", generate_password_hash(PIN) if pin else None))
    return uid


def _seed_market(conn, buyers, stock):
    cur = conn.cursor()
    seller = _seed_user(cur, 'seller', pin=False)
    seller_pm = str(uuid.uuid4())
    cur.execute("INSERT INTO paymentMethods (id, userId, methodType, providerName, accountNumber, balance) VALUES (%s,%s,'bank','B','1',0)",
                (seller_pm, seller))
    shop = str(uuid.uuid4())
    cur.execute("INSERT INTO shops (id, sellerId, name) VALUES (%s,%s,'Race Shop')", (shop, seller))
    cur.execute("INSERT INTO categories (name) VALUES ('c')")
    cat = cur.lastrowid
    prod = uuid.uuid4().hex[:15]
    cur.execute("INSERT INTO products (id, categoryId, shopId, name, inStock, unitPrice, isActive) VALUES (%s,%s,%s,'Last item',%s,%s,TRUE)",
                (prod, cat, shop, stock, PRICE))
    result = []
    for _ in range(buyers):
        uid = _seed_user(cur, 'user')
        pm = str(uuid.uuid4())
        cur.execute("INSERT INTO paymentMethods (id, userId, methodType, providerName, accountNumber, balance) VALUES (%s,%s,'bank','B','2',%s)",
                    (pm, uid, BALANCE))
        cart = str(uuid.uuid4())
        cur.execute("INSERT INTO carts (id, userId) VALUES (%s,%s)", (cart, uid))
        item = str(uuid.uuid4())
        cur.execute("INSERT INTO cartItems (id, cartId, productId, quantity, selectedVariants) VALUES (%s,%s,%s,1,'{}')",
                    (item, cart, prod))
        result.append({"user": uid, "pm": pm, "item": item})
    return {"seller_pm": seller_pm, "product": prod, "buyers": result}


@pytest.mark.parametrize("buyers,stock", [(8, 3), (6, 1)])
def test_concurrent_checkout_never_oversells(app, db_conn, buyers, stock):
    m = _seed_market(db_conn, buyers, stock)
    statuses = [None] * buyers
    barrier = threading.Barrier(buyers)

    def attempt(i):
        b = m["buyers"][i]
        client = app.test_client()
        barrier.wait()
        resp = client.post('/api/checkout/checkout',
                           headers={'Authorization': f"Bearer {issue_token(b['user'], 'user')}"},
                           json={"paymentMethodId": b["pm"], "passPhrase": PIN, "cartItemIds": [b["item"]]})
        statuses[i] = resp.status_code

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(buyers)]
    [t.start() for t in threads]
    [t.join(timeout=60) for t in threads]
    assert None not in statuses, "một request bị treo/deadlock"

    cur = db_conn.cursor()
    ok = [i for i, s in enumerate(statuses) if s == 200]
    assert len(ok) == stock, f"statuses={statuses}"

    cur.execute("SELECT inStock FROM products WHERE id=%s", (m["product"],))
    assert cur.fetchone()["inStock"] == 0

    for i, b in enumerate(m["buyers"]):
        cur.execute("SELECT balance FROM paymentMethods WHERE id=%s", (b["pm"],))
        expected = BALANCE - PRICE if i in ok else BALANCE
        assert int(cur.fetchone()["balance"]) == expected, f"buyer {i} balance sai"
        cur.execute("SELECT COUNT(*) c FROM orders WHERE userId=%s", (b["user"],))
        assert cur.fetchone()["c"] == (1 if i in ok else 0)

    cur.execute("SELECT balance FROM paymentMethods WHERE id=%s", (m["seller_pm"],))
    assert int(cur.fetchone()["balance"]) == PRICE * stock


def test_checkout_amounts_stored_as_integer_vnd(app, db_conn):
    m = _seed_market(db_conn, buyers=1, stock=5)
    b = m["buyers"][0]
    resp = app.test_client().post('/api/checkout/checkout',
                                  headers={'Authorization': f"Bearer {issue_token(b['user'], 'user')}"},
                                  json={"paymentMethodId": b["pm"], "passPhrase": PIN, "cartItemIds": [b["item"]]})
    assert resp.status_code == 200
    orders = app.test_client().get('/api/checkout/orders',
                                   headers={'Authorization': f"Bearer {issue_token(b['user'], 'user')}"}).get_json()['orders']
    assert orders[0]["totalAmount"] == PRICE and isinstance(orders[0]["totalAmount"], int)
    assert orders[0]["items"][0]["unitPrice"] == PRICE
