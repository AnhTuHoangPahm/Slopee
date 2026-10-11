"""P0-05: giao dịch an toàn khi thanh toán (A-05 phần unit) và khóa tạm sau 5 lần sai (A-06)."""
import pymysql
import pytest
from werkzeug.security import generate_password_hash

import throttle
from checkout_helpers import setup_checkout, ITEMS, BODY

USER = 'fake-user-id'


@pytest.fixture
def pay(fake_db, mocker):
    mocker.patch('backend.routes.payments.check_password_hash', return_value=True)
    return fake_db('backend.routes.payments')


# ------------------------------------------------------------------ khóa dòng + cập nhật có điều kiện (S-08)
def test_checkout_locks_rows_in_fixed_order(client, pay, auth_headers):
    """cartItems -> products -> paymentMethods, mỗi nhóm ORDER BY id FOR UPDATE (tránh deadlock chéo)."""
    setup_checkout(pay, ITEMS)
    assert client.post('/api/checkout/checkout', headers=auth_headers, json=BODY).status_code == 200
    locking = [sql for sql, _ in pay.calls if "FOR UPDATE" in sql and "authAttempts" not in sql]
    assert len(locking) == 3
    assert "FROM cartItems" in locking[0] and "FROM products" in locking[1] and "FROM paymentMethods" in locking[2]
    assert all("ORDER BY" in sql for sql in locking)


def test_stock_decrement_is_conditional_and_aggregated(client, pay, auth_headers):
    setup_checkout(pay, ITEMS)
    client.post('/api/checkout/checkout', headers=auth_headers, json=BODY)
    sql, params = pay.executed("UPDATE products")[0]
    assert "inStock >= %s" in sql and params == (2, 100, 2)


def test_race_loser_gets_400_and_nothing_is_written(client, pay, auth_headers):
    """Request thua cuộc: UPDATE có điều kiện không khớp dòng nào -> 400, rollback, không tạo đơn."""
    setup_checkout(pay, ITEMS)
    pay.on("UPDATE products", rowcount=0)
    r = client.post('/api/checkout/checkout', headers=auth_headers, json=BODY)
    assert r.status_code == 400 and "Insufficient stock" in r.get_json()['error']
    pay.conn.rollback.assert_called()
    assert not pay.executed("INSERT INTO orders") and not pay.executed("DELETE FROM cartItems")


def test_balance_decrement_is_guarded(client, pay, auth_headers):
    setup_checkout(pay, ITEMS)
    pay.on("balance - %s", rowcount=0)  # số dư bị tiêu bởi request khác ngay trước đó
    r = client.post('/api/checkout/checkout', headers=auth_headers, json=BODY)
    assert r.status_code == 400 and r.get_json()['code'] == 'insufficient_funds'
    assert "balance >= %s" in pay.executed("balance - %s")[0][0]
    assert not pay.executed("INSERT INTO orders")


def test_same_product_in_two_cart_lines_is_checked_cumulatively(client, pay, auth_headers):
    items = [{"cartItemId": 10, "quantity": 2, "productId": 100, "unitPrice": 1000, "inStock": 3},
             {"cartItemId": 11, "quantity": 2, "productId": 100, "unitPrice": 1000, "inStock": 3}]
    setup_checkout(pay, items)
    r = client.post('/api/checkout/checkout', headers=auth_headers, json={**BODY, "cartItemIds": [10, 11]})
    assert r.status_code == 400 and "Insufficient stock" in r.get_json()['error']


def test_inactive_or_deleted_product_is_rejected(client, pay, auth_headers):
    setup_checkout(pay, ITEMS)
    pay.on("FROM products", [])  # isActive = TRUE lọc mất sản phẩm
    r = client.post('/api/checkout/checkout', headers=auth_headers, json=BODY)
    assert r.status_code == 400 and r.get_json()['code'] == 'product_unavailable'
    assert "isActive = TRUE" in pay.executed("FROM products")[0][0]


def test_deadlock_returns_409_not_500(client, pay, auth_headers):
    setup_checkout(pay, ITEMS)

    def deadlock(sql, params):
        raise pymysql.err.OperationalError(1213, "Deadlock found")
    pay.on("UPDATE products", deadlock)
    r = client.post('/api/checkout/checkout', headers=auth_headers, json=BODY)
    assert r.status_code == 409 and r.get_json()['code'] == 'checkout_conflict'
    pay.conn.rollback.assert_called()


def test_money_path_has_no_float():
    import inspect
    from backend.routes import payments
    assert "float(" not in inspect.getsource(payments)


# ------------------------------------------------------------------ PIN
def test_account_without_pin_gets_401_not_500(client, fake_db, auth_headers):
    cur = fake_db('backend.routes.payments')
    cur.on("FROM credentials", [{"passPhraseHash": None}])
    r = client.post('/api/checkout/checkout', headers=auth_headers, json=BODY)
    assert r.status_code == 401 and r.get_json()['code'] == 'pin_not_set'


@pytest.mark.parametrize("pin", ["123", "abcdef", "12345678", "", None, 123456, ["1"]])
def test_pin_format_rejected_before_any_db_work(client, pay, auth_headers, pin):
    r = client.post('/api/checkout/checkout', headers=auth_headers, json={**BODY, "passPhrase": pin})
    assert r.status_code == 400 and not pay.calls


def test_wrong_pin_is_counted_and_committed_before_response(client, fake_db, auth_headers, attempts_store):
    cur = fake_db('backend.routes.payments')
    store = attempts_store(cur)
    cur.on("FROM credentials", [{"passPhraseHash": generate_password_hash("654321")}])
    r = client.post('/api/checkout/checkout', headers=auth_headers, json=BODY)
    assert r.status_code == 401 and r.get_json()['code'] == 'invalid_pin'
    assert r.get_json()['attemptsRemaining'] == 4
    assert store.get('pin', f'id:{USER}')[0] == 1
    cur.conn.commit.assert_called()


# ------------------------------------------------------------------ A-06: khóa tạm
def test_pin_lock_after_five_wrong_attempts_then_unlock(client, fake_db, auth_headers, attempts_store, monkeypatch):
    cur = fake_db('backend.routes.payments')
    store = attempts_store(cur)
    cur.on("FROM credentials", [{"passPhraseHash": generate_password_hash("654321")}])
    for n in range(5):
        r = client.post('/api/checkout/checkout', headers=auth_headers, json=BODY)
        assert r.status_code == 401, n
    # Lần thứ 6: bị khóa, kể cả khi nhập ĐÚNG PIN
    good = {**BODY, "passPhrase": "654321"}
    r = client.post('/api/checkout/checkout', headers=auth_headers, json=good)
    assert r.status_code == 429 and r.get_json()['code'] == 'too_many_attempts'
    assert int(r.headers['Retry-After']) > 0 and r.get_json()['retryAfter'] > 0
    # Hết thời gian khóa -> nhập đúng thì qua và bộ đếm được xóa
    locked_until = store.get('pin', f'id:{USER}')[1]
    monkeypatch.setattr(throttle, 'now', lambda: locked_until + 1)
    setup_checkout(cur, ITEMS)
    cur.on("FROM credentials", [{"passPhraseHash": generate_password_hash("654321")}])
    assert client.post('/api/checkout/checkout', headers=auth_headers, json=good).status_code == 200
    assert store.get('pin', f'id:{USER}') is None


def test_success_resets_failure_counter(client, fake_db, auth_headers, attempts_store, mocker):
    cur = fake_db('backend.routes.payments')
    store = attempts_store(cur)
    cur.on("FROM credentials", [{"passPhraseHash": generate_password_hash("654321")}])
    for _ in range(3):
        client.post('/api/checkout/checkout', headers=auth_headers, json=BODY)
    assert store.get('pin', f'id:{USER}')[0] == 3
    setup_checkout(cur, ITEMS)
    cur.on("FROM credentials", [{"passPhraseHash": generate_password_hash("654321")}])
    assert client.post('/api/checkout/checkout', headers=auth_headers,
                       json={**BODY, "passPhrase": "654321"}).status_code == 200
    assert store.get('pin', f'id:{USER}') is None


def _login(client, username, password):
    return client.post('/api/auth/login', json={"username": username, "password": password})


def _user(password):
    return {'userId': 7, 'passwordHash': generate_password_hash(password), 'role': 'user', 'name': 'N', 'email': 'e'}


def test_login_lock_after_five_wrong_passwords(client, fake_db, attempts_store, monkeypatch):
    cur = fake_db('backend.routes.auth')
    store = attempts_store(cur)
    cur.on("FROM credentials c", [_user('rightpass')])
    for n in range(5):
        assert _login(client, 'alice', 'wrong').status_code == 401
    r = _login(client, 'alice', 'rightpass')  # đúng mật khẩu nhưng đang khóa
    assert r.status_code == 429 and 'Retry-After' in r.headers
    monkeypatch.setattr(throttle, 'now', lambda: store.get('password', 'id:7')[1] + 1)
    assert _login(client, 'alice', 'rightpass').status_code == 200
    assert store.get('password', 'id:7') is None


def test_unknown_username_is_throttled_the_same_way(client, fake_db, attempts_store):
    """Không lộ username nào tồn tại: tên không có thật cũng bị đếm và khóa như tên có thật."""
    cur = fake_db('backend.routes.auth')
    attempts_store(cur)
    codes = [_login(client, 'ghost-user', 'x').status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
    assert all("ghost-user" not in str(p) for _, p in cur.executed("authAttempts"))  # chỉ lưu băm


def test_password_change_shares_the_login_counter(client, fake_db, attempts_store, auth_headers):
    cur = fake_db('backend.routes.auth')
    store = attempts_store(cur)
    cur.on("SELECT passwordHash FROM credentials", [{"passwordHash": generate_password_hash("realold")}])
    for _ in range(5):
        r = client.put('/api/auth/password', headers=auth_headers, json={"oldPassword": "bad", "newPassword": "newpass1"})
        assert r.status_code == 401
    r = client.put('/api/auth/password', headers=auth_headers, json={"oldPassword": "realold", "newPassword": "newpass1"})
    assert r.status_code == 429
    assert not cur.executed("UPDATE credentials SET passwordHash")
    assert store.get('password', f'id:{USER}')[0] == 5


def test_account_deletion_request_is_throttled(client, fake_db, attempts_store, auth_headers):
    cur = fake_db('backend.routes.auth')
    attempts_store(cur)
    cur.on("SELECT passwordHash FROM credentials", [{"passwordHash": generate_password_hash("realold")}])
    codes = [client.post('/api/auth/account/request-deletion', headers=auth_headers,
                         json={"password": "bad"}).status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]


def test_limits_are_configurable(client, fake_db, attempts_store, monkeypatch):
    monkeypatch.setenv('AUTH_MAX_ATTEMPTS', '2')
    cur = fake_db('backend.routes.auth')
    attempts_store(cur)
    cur.on("FROM credentials c", [_user('rightpass')])
    codes = [_login(client, 'alice', 'x').status_code for _ in range(3)]
    assert codes == [401, 401, 429]


def test_throttle_helpers():
    assert throttle.password_subject(user_id=5) == 'id:5'
    s1, s2 = throttle.password_subject(username='Bob'), throttle.password_subject(username=' bob ')
    assert s1 == s2 and s1.startswith('u:') and 'bob' not in s1.lower().replace('u:', '')
    assert throttle.locked_error(61).headers['Retry-After'] == '61'
