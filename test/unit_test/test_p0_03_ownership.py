"""P0-03: kiểm quyền sở hữu (A-03) và từ chối đơn Web3 / chuyển trạng thái sai (I-06)."""
import pymysql
import pytest

OTHER = 'someone-else'


# ---------------------------------------------------------------- đơn hàng (S-05)
@pytest.fixture
def orders_db(fake_db):
    return fake_db('backend.routes.payments')


def _put_status(client, headers, status, order_id='o1', **extra):
    return client.put(f'/api/checkout/orders/{order_id}', headers=headers, json={"status": status, **extra})


def test_order_of_another_user_is_404_and_untouched(client, orders_db, auth_headers):
    # truy vấn "đơn của tôi" không trả dòng nào = đơn thuộc người khác hoặc không tồn tại
    orders_db.on("FROM orders WHERE id", [])
    r = _put_status(client, auth_headers, 'cancelled', userId=OTHER)
    assert r.status_code == 404
    assert not orders_db.executed("UPDATE orders")


def test_order_lookup_is_scoped_by_token_user_not_body(client, orders_db, auth_headers):
    orders_db.on("FROM orders WHERE id", [])
    _put_status(client, auth_headers, 'received', userId=OTHER)
    sql, params = orders_db.executed("FROM orders WHERE id")[0]
    assert params == ('o1', 'fake-user-id') and "userId=%s" in sql and "FOR UPDATE" in sql


@pytest.mark.parametrize("current,new", [("paid", "received"), ("shipped", "received"),
                                         ("paid", "cancelled"), ("pending", "cancelled")])
def test_valid_order_transitions(client, orders_db, auth_headers, current, new):
    orders_db.on("FROM orders WHERE id", [{"id": "o1", "status": current}])
    orders_db.on("FROM order_web3", [])
    r = _put_status(client, auth_headers, new)
    assert r.status_code == 200
    update = orders_db.executed("UPDATE orders")[0]
    # UPDATE có điều kiện trạng thái hiện tại + chủ đơn (chống ghi đè khi 2 request song song)
    assert update[1] == (new, 'o1', 'fake-user-id', current) and "AND status=%s" in update[0]
    orders_db.conn.commit.assert_called()


@pytest.mark.parametrize("current,new", [("received", "cancelled"), ("cancelled", "received"),
                                         ("received", "received"), ("cancelled", "cancelled"),
                                         ("shipped", "cancelled"), ("pending", "received")])
def test_invalid_order_transitions_rejected(client, orders_db, auth_headers, current, new):
    orders_db.on("FROM orders WHERE id", [{"id": "o1", "status": current}])
    orders_db.on("FROM order_web3", [])
    r = _put_status(client, auth_headers, new)
    assert r.status_code == 409 and r.get_json()['code'] == 'INVALID_STATE'
    assert not orders_db.executed("UPDATE orders")


def test_web3_order_is_rejected(client, orders_db, auth_headers):
    """SRS 5.1: PUT /api/payments/orders/:id phải từ chối đơn đã có dòng order_web3."""
    orders_db.on("FROM orders WHERE id", [{"id": "o1", "status": "paid"}])
    orders_db.on("FROM order_web3", [{"x": 1}])
    r = _put_status(client, auth_headers, 'cancelled')
    assert r.status_code == 409 and r.get_json()['code'] == 'WEB3_ORDER_MANAGED'
    assert not orders_db.executed("UPDATE orders")


def test_missing_order_web3_table_means_legacy_order(client, orders_db, auth_headers):
    """Chưa áp dụng migration Web3 (chưa có bảng order_web3, lỗi 1146) thì đơn cũ vẫn cập nhật bình thường."""
    def no_table(sql, params):
        raise pymysql.err.ProgrammingError(1146, "Table 'order_web3' doesn't exist")
    orders_db.on("FROM orders WHERE id", [{"id": "o1", "status": "paid"}])
    orders_db.on("FROM order_web3", no_table)
    assert _put_status(client, auth_headers, 'received').status_code == 200


def test_other_db_errors_on_web3_check_are_not_swallowed(client, orders_db, auth_headers):
    def boom(sql, params):
        raise pymysql.err.ProgrammingError(1064, "syntax error")
    orders_db.on("FROM orders WHERE id", [{"id": "o1", "status": "paid"}])
    orders_db.on("FROM order_web3", boom)
    r = _put_status(client, auth_headers, 'received')
    assert r.status_code == 500 and r.get_json()['code'] == 'internal_error'


@pytest.mark.parametrize("bad", ["shipped", "paid", "", None, 5, ["received"], {"a": 1}])
def test_order_status_value_whitelisted(client, orders_db, auth_headers, bad):
    assert _put_status(client, auth_headers, bad).status_code == 400


def test_order_update_requires_auth(client):
    assert client.put('/api/checkout/orders/o1', json={"status": "received"}).status_code == 401


# ---------------------------------------------------------------- giỏ hàng
@pytest.fixture
def carts_db(fake_db):
    return fake_db('backend.routes.carts')


def test_cannot_delete_other_users_cart_item(client, carts_db, auth_headers):
    carts_db.on("DELETE FROM cartItems", rowcount=0)
    assert client.delete('/api/cart/items/victim-item', headers=auth_headers).status_code == 404
    sql, params = carts_db.executed("DELETE FROM cartItems")[0]
    assert params == ('victim-item', 'fake-user-id') and "userId=%s" in sql


def test_can_delete_own_cart_item(client, carts_db, auth_headers):
    carts_db.on("DELETE FROM cartItems", rowcount=1)
    assert client.delete('/api/cart/items/mine', headers=auth_headers).status_code == 200


def test_cannot_update_other_users_cart_item(client, carts_db, auth_headers):
    carts_db.on("SELECT p.inStock", [])  # JOIN carts ... userId = tôi -> không có dòng
    r = client.put('/api/cart/items/victim-item', headers=auth_headers, json={"quantity": 3})
    assert r.status_code == 404
    assert not carts_db.executed("UPDATE cartItems")
    assert carts_db.executed("SELECT p.inStock")[0][1] == ('victim-item', 'fake-user-id')


def test_can_update_own_cart_item(client, carts_db, auth_headers):
    carts_db.on("SELECT p.inStock", [{"inStock": 10}])
    assert client.put('/api/cart/items/mine', headers=auth_headers, json={"quantity": 3}).status_code == 200
    assert carts_db.executed("UPDATE cartItems")[0][1] == (3, 'mine', 'fake-user-id')


# ---------------------------------------------------------------- phương thức thanh toán & giỏ khi thanh toán
def _checkout_rules(cur, pm_owner='fake-user-id', cart_rows=None):
    cur.on("FROM credentials", [{"passPhraseHash": "h"}])
    cur.on("FROM cartItems ci", cart_rows if cart_rows is not None else
           [{"cartItemId": 10, "quantity": 1, "cartId": 1, "selectedVariants": "{}", "productId": 100}])
    cur.on("FROM products", [{"productId": 100, "unitPrice": 1000, "inStock": 5, "shopId": 1, "name": "N"}])
    cur.on("FROM shops", [{"shopId": 1, "shopName": "S", "sellerId": "seller-1"}])
    cur.on("SELECT id FROM paymentMethods WHERE userId", [])
    cur.on("FROM paymentMethods WHERE id IN",
           [{"id": "pm-1", "userId": pm_owner, "methodType": "bank", "balance": 999999}])


def test_checkout_with_someone_elses_payment_method_is_404(client, orders_db, auth_headers, mocker):
    mocker.patch('backend.routes.payments.check_password_hash', return_value=True)
    _checkout_rules(orders_db, pm_owner=OTHER)
    r = client.post('/api/checkout/checkout', headers=auth_headers,
                    json={"paymentMethodId": "pm-1", "passPhrase": "123456", "cartItemIds": [10]})
    assert r.status_code == 404 and r.get_json()['code'] == 'payment_method_not_found'
    assert not orders_db.executed("balance - %s") and not orders_db.executed("INSERT INTO orders")


def test_checkout_with_someone_elses_cart_items_is_rejected(client, orders_db, auth_headers, mocker):
    mocker.patch('backend.routes.payments.check_password_hash', return_value=True)
    _checkout_rules(orders_db, cart_rows=[])  # truy vấn giỏ chỉ trả dòng thuộc giỏ của tôi
    r = client.post('/api/checkout/checkout', headers=auth_headers,
                    json={"paymentMethodId": "pm-1", "passPhrase": "123456", "cartItemIds": [10]})
    assert r.status_code == 400
    sql, params = orders_db.executed("FROM cartItems ci")[0]
    assert params[-1] == 'fake-user-id' and "userId=%s" in sql
    assert not orders_db.executed("INSERT INTO orders")


# ---------------------------------------------------------------- shop / sản phẩm (S-06)
@pytest.fixture
def shops_db(fake_db):
    return fake_db('backend.routes.shops')


def _own_product(cur, owned):
    cur.on("FROM products p JOIN shops s", [{"id": "p1"}] if owned else [])


@pytest.mark.parametrize("method,url,body", [
    ('put', '/api/shop/products/p1', {"unitPrice": 5, "inStock": 1}),
    ('delete', '/api/shop/products/p1', None),
    ('post', '/api/shop/products/p1/images', {"imageUrl": "https://x.io/a.png"}),
    ('post', '/api/shop/products/p1/variants', {"variantName": "Size", "variantValue": "L"}),
])
def test_seller_cannot_touch_other_sellers_product(client, shops_db, seller_headers, method, url, body):
    _own_product(shops_db, owned=False)
    kwargs = {"json": body} if body is not None else {}
    r = getattr(client, method)(url, headers=seller_headers, **kwargs)
    assert r.status_code == 404
    writes = [c for c in shops_db.calls if c[0].lstrip().upper().startswith(("UPDATE", "DELETE", "INSERT"))]
    assert writes == []
    assert shops_db.executed("FROM products p JOIN shops s")[0][1] == ('p1', 'fake-seller-id')


@pytest.mark.parametrize("method,url,body,expect_sql", [
    ('put', '/api/shop/products/p1', {"unitPrice": 5, "inStock": 1}, "UPDATE products"),
    ('delete', '/api/shop/products/p1', None, "DELETE FROM products"),
    ('post', '/api/shop/products/p1/images', {"imageUrl": "https://x.io/a.png"}, "INSERT INTO productImages"),
    ('post', '/api/shop/products/p1/variants', {"variantName": "Size", "variantValue": "L"}, "INSERT INTO productVariants"),
])
def test_seller_can_touch_own_product(client, shops_db, seller_headers, method, url, body, expect_sql):
    _own_product(shops_db, owned=True)
    kwargs = {"json": body} if body is not None else {}
    r = getattr(client, method)(url, headers=seller_headers, **kwargs)
    assert r.status_code in (200, 201)
    assert shops_db.executed(expect_sql)


@pytest.mark.parametrize("url,table", [('/api/shop/products/images/i1', 'productImages'),
                                       ('/api/shop/products/variants/v1', 'productVariants')])
def test_seller_cannot_delete_other_sellers_image_or_variant(client, shops_db, seller_headers, url, table):
    shops_db.on(f"DELETE", rowcount=0)
    assert client.delete(url, headers=seller_headers).status_code == 404
    sql, params = shops_db.executed("DELETE")[0]
    assert params[-1] == 'fake-seller-id' and "s.sellerId=%s" in sql


@pytest.mark.parametrize("url", ['/api/shop/products/images/i1', '/api/shop/products/variants/v1',
                                 '/api/shop/products/p1'])
def test_buyer_cannot_use_seller_endpoints(client, auth_headers, url):
    assert client.delete(url, headers=auth_headers).status_code == 403


# ---------------------------------------------------------------- hồ sơ / tên đăng nhập (S-11)
def test_profile_and_username_only_affect_token_user(client, fake_db, auth_headers):
    cur = fake_db('backend.routes.auth')
    assert client.put('/api/auth/profile', headers=auth_headers, json={"bio": "hi", "userId": OTHER}).status_code == 200
    assert cur.executed("UPDATE users SET bio")[0][1] == ("hi", 'fake-user-id')
    r = client.put('/api/auth/username', headers=auth_headers, json={"newUsername": "brandnew", "userId": OTHER})
    assert r.status_code == 200
    assert cur.executed("UPDATE credentials SET username")[0][1] == ("brandnew", 'fake-user-id')


@pytest.mark.parametrize("method,url", [('put', '/api/auth/profile'), ('put', '/api/auth/username'),
                                        ('put', '/api/auth/password')])
def test_account_endpoints_need_token(client, method, url):
    assert getattr(client, method)(url, json={"bio": "x"}).status_code == 401
