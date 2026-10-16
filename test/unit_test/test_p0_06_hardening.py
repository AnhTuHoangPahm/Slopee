"""P0-06: không lộ lỗi nội bộ (S-10), kiểm tra đầu vào (S-14), debug chỉ ở development."""
import logging
import os
import re

import pytest
from flask import Flask

import config
import errors

BACKEND = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
SECRET_DETAIL = "Table 'slopee_db.secret_table' doesn't exist (SQL: SELECT * FROM users)"


# ------------------------------------------------------------------ debug
def test_debug_only_in_development(monkeypatch):
    monkeypatch.setenv('SLOPEE_ENV', 'development')
    assert config.is_development() is True
    for value in ('production', 'test', '', 'Dev'):
        monkeypatch.setenv('SLOPEE_ENV', value)
        assert config.is_development() is False
    monkeypatch.delenv('SLOPEE_ENV')
    assert config.is_development() is False


def test_app_py_never_hardcodes_debug_true():
    src = open(os.path.join(BACKEND, 'app.py'), encoding='utf-8').read()
    assert not re.search(r"debug\s*=\s*True", src)
    assert "app.config['DEBUG']" in src and 'register_app_errors' in src


# ------------------------------------------------------------------ lỗi chung, không lộ chi tiết
class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.ERROR)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def captured_log(app):
    h = _Capture()
    app.logger.addHandler(h)
    yield h
    app.logger.removeHandler(h)


def _boom(sql, params):
    raise RuntimeError(SECRET_DETAIL)


@pytest.mark.parametrize("module,method,url,body,headers_fixture,fragment", [
    ('backend.routes.products', 'get', '/api/products/', None, None, "FROM"),
    ('backend.routes.auth', 'post', '/api/auth/signup',
     {"name": "N", "email": "a@b.co", "phone": "0123456789", "username": "someone", "password": "pw", "pass_phrase": "123456"},
     None, "SELECT id FROM users"),
    ('backend.routes.shops', 'put', '/api/shop/products/p1', {"unitPrice": 1, "inStock": 1}, 'seller_headers', "FROM products p"),
    ('backend.routes.carts', 'get', '/api/cart/', None, 'auth_headers', "FROM carts"),
    ('backend.routes.payments', 'get', '/api/checkout/orders', None, 'auth_headers', "FROM orders"),
    ('backend.routes.payments', 'put', '/api/checkout/orders/o1', {"status": "received"}, 'auth_headers', "FROM orders WHERE id"),
    ('backend.routes.reviews', 'post', '/api/reviews/p1', {"rating": 5, "comment": "ok"}, 'auth_headers', "FROM orders o"),
])
def test_unexpected_errors_return_generic_500_and_are_logged(request, client, fake_db, captured_log,
                                                             module, method, url, body, headers_fixture, fragment):
    cur = fake_db(module)
    cur.on(fragment, _boom)
    headers = request.getfixturevalue(headers_fixture) if headers_fixture else {}
    kwargs = {"headers": headers}
    if body is not None:
        kwargs["json"] = body
    r = getattr(client, method)(url, **kwargs)
    assert r.status_code == 500
    text = r.get_data(as_text=True)
    assert 'secret_table' not in text and 'SELECT' not in text and 'RuntimeError' not in text
    assert r.get_json() == {"error": errors.GENERIC_500_MESSAGE, "code": "internal_error"}
    # chi tiết nằm trong log máy chủ
    assert any('secret_table' in rec.getMessage() or 'secret_table' in repr(rec.args) for rec in captured_log.records)


def test_no_route_returns_str_of_exception():
    routes_dir = os.path.join(BACKEND, 'routes')
    for name in os.listdir(routes_dir):
        if name.endswith('.py'):
            assert 'str(e)' not in open(os.path.join(routes_dir, name), encoding='utf-8').read().replace(
                "raise ApiError(str(e), 'invalid_amount', 400)", ''), name


def test_app_level_handlers_return_json_for_404_405_and_500():
    a = Flask(__name__)
    errors.register_app_errors(a)

    @a.route('/only-get')
    def only_get():
        return 'ok'

    @a.route('/crash')
    def crash():
        raise RuntimeError(SECRET_DETAIL)

    c = a.test_client()
    assert c.get('/missing').status_code == 404 and c.get('/missing').is_json
    assert c.post('/only-get').status_code == 405 and c.post('/only-get').is_json
    r = c.get('/crash')
    assert r.status_code == 500 and 'secret_table' not in r.get_data(as_text=True)


def test_http_exceptions_inside_blueprints_keep_their_status(client):
    # body quá lớn / sai method trong blueprint vẫn là JSON, không thành 500
    r = client.open('/api/auth/login', method='DELETE')
    assert r.status_code == 405


# ------------------------------------------------------------------ body JSON hợp lệ
@pytest.mark.parametrize("url,headers_fixture", [
    ('/api/auth/login', None), ('/api/auth/signup', None), ('/api/cart/items', 'auth_headers'),
    ('/api/checkout/checkout', 'auth_headers'), ('/api/checkout/', 'auth_headers'),
    ('/api/shop/products', 'seller_headers'), ('/api/shop/', 'seller_headers'),
])
@pytest.mark.parametrize("raw", ['[1, 2]', '"text"', '123', '{broken', 'null'])
def test_non_object_json_body_is_400_not_500(request, client, fake_db, url, headers_fixture, raw):
    for module in ('auth', 'carts', 'payments', 'shops'):
        fake_db(f'backend.routes.{module}')
    headers = dict(request.getfixturevalue(headers_fixture)) if headers_fixture else {}
    headers['Content-Type'] = 'application/json'
    r = client.post(url, data=raw, headers=headers)
    assert r.status_code == 400 and r.get_json()['code'] == 'invalid_body'


def test_missing_body_is_handled_as_empty_object(client, fake_db, auth_headers):
    fake_db('backend.routes.carts')
    r = client.post('/api/cart/items', headers=auth_headers)
    assert r.status_code == 400  # productId thiếu, không phải lỗi 500


# ------------------------------------------------------------------ giá trị từng trường
@pytest.mark.parametrize("body", [
    {"productId": "p1", "quantity": "abc"}, {"productId": "p1", "quantity": 1.5}, {"productId": "p1", "quantity": True},
    {"productId": "p1", "quantity": 10 ** 9}, {"productId": ["p1"]}, {"productId": "x" * 40},
    {"productId": "p1", "selectedVariants": "red"}, {"productId": "p1", "selectedVariants": [1]},
])
def test_cart_item_validation(client, fake_db, auth_headers, body):
    cur = fake_db('backend.routes.carts')
    assert client.post('/api/cart/items', headers=auth_headers, json=body).status_code == 400
    assert not cur.calls


@pytest.mark.parametrize("body", [
    {"name": "P", "inStock": "abc"}, {"name": "P", "inStock": -1}, {"name": "P", "inStock": 10 ** 9},
    {"name": "P", "categoryId": "x"}, {"name": ["P"]}, {"name": "P" * 300}, {"name": "P", "description": 5},
])
def test_product_create_validation(client, fake_db, seller_headers, body):
    cur = fake_db('backend.routes.shops')
    assert client.post('/api/shop/products', headers=seller_headers, json=body).status_code == 400
    assert not cur.calls


@pytest.mark.parametrize("body", [{"unitPrice": 1, "inStock": "x"}, {"unitPrice": 1, "inStock": -5}])
def test_product_update_validation(client, fake_db, seller_headers, body):
    cur = fake_db('backend.routes.shops')
    assert client.put('/api/shop/products/p1', headers=seller_headers, json=body).status_code == 400
    assert not cur.calls


BAD_URLS = ["javascript:alert(1)", "data:image/png;base64,AAAA", "ftp://x.io/a.png", "//x.io/a.png", "not a url",
            "https://x.io/a b.png", "http://", "https://x.io/" + "a" * 500, 123, ""]


@pytest.mark.parametrize("url", BAD_URLS)
def test_product_image_url_validation(client, fake_db, seller_headers, url):
    cur = fake_db('backend.routes.shops')
    r = client.post('/api/shop/products/p1/images', headers=seller_headers, json={"imageUrl": url})
    assert r.status_code == 400 and not cur.calls


def test_product_image_valid_url_accepted(client, fake_db, seller_headers):
    cur = fake_db('backend.routes.shops')
    cur.on("FROM products p JOIN shops s", [{"id": "p1"}])
    r = client.post('/api/shop/products/p1/images', headers=seller_headers,
                    json={"imageUrl": "https://cdn.example.com/a.png?x=1", "isPrimary": True})
    assert r.status_code == 201


@pytest.mark.parametrize("images", [["javascript:alert(1)"], "https://x.io/a.png", ["https://x.io/a.png"] * 6, [5]])
def test_review_image_validation(client, fake_db, auth_headers, images):
    cur = fake_db('backend.routes.reviews')
    r = client.post('/api/reviews/p1', headers=auth_headers, json={"rating": 5, "comment": "ok", "images": images})
    assert r.status_code == 400 and not cur.calls


@pytest.mark.parametrize("params", ["offset=abc", "limit=abc", "offset=-1", "limit=0", "limit=100000"])
def test_review_listing_query_params_validated(client, fake_db, params):
    fake_db('backend.routes.products')
    r = client.get(f'/api/products/p1/reviews?{params}')
    assert r.status_code == 400


@pytest.mark.parametrize("override", [
    {"email": "not-an-email"}, {"email": "a@b"}, {"phone": "12ab"}, {"phone": "1" * 20}, {"name": "N" * 80},
    {"username": "u" * 40}, {"password": "p" * 500}, {"name": 5}, {"username": ["someone"]},
])
def test_signup_field_validation(client, fake_db, override):
    cur = fake_db('backend.routes.auth')
    body = {"name": "N", "email": "a@b.co", "phone": "0123456789", "username": "someone",
            "password": "pw123456", "pass_phrase": "123456", **override}
    r = client.post('/api/auth/signup', json=body)
    assert r.status_code == 400 and not cur.calls


@pytest.mark.parametrize("body", [{"methodType": "bitcoin"}, {"providerName": "x" * 200}, {"accountNumber": 5}])
def test_payment_method_validation(client, fake_db, auth_headers, body):
    cur = fake_db('backend.routes.payments')
    assert client.post('/api/checkout/', headers=auth_headers, json=body).status_code == 400
    assert not cur.calls


@pytest.mark.parametrize("body", [{"cartItemIds": []}, {"cartItemIds": "1"}, {"cartItemIds": [[1]]},
                                  {"cartItemIds": list(range(500))}, {}])
def test_checkout_cart_ids_validated(client, fake_db, auth_headers, body):
    cur = fake_db('backend.routes.payments')
    r = client.post('/api/checkout/checkout', headers=auth_headers, json={"paymentMethodId": 1, "passPhrase": "123456", **body})
    assert r.status_code == 400 and not cur.calls
