"""Tuần 8 [B][Q]: quét TOÀN BỘ route của app thật (backend/app.py) cho A-01, A-02, A-04, A-07 và khóa bề mặt API (Feature Freeze).

Không cần MySQL/Anvil: mọi truy cập DB/chuỗi bị chặn. Danh sách quyền theo SRS mục 3 và 7 (không suy từ code).
Sửa EXPECTED_ROUTES khi (và chỉ khi) nhóm chủ ý đổi API sau freeze; ghi lý do vào PROGRESS.md.
"""
import importlib
import logging
import os
import re
import sys

import pymysql
import pytest

import auth_utils
from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container
from slopee_web3.domain.errors import DomainError

EXPECTED_ROUTES = [
    ('DELETE', '/api/admin/categories/<int:cat_id>'),
    ('DELETE', '/api/admin/users/<user_id>'),
    ('DELETE', '/api/carts/items/<item_id>'),
    ('DELETE', '/api/shops/products/<product_id>'),
    ('DELETE', '/api/shops/products/images/<image_id>'),
    ('DELETE', '/api/shops/products/variants/<variant_id>'),
    ('GET', '/api/admin/categories'),
    ('GET', '/api/admin/disputes'),
    ('GET', '/api/admin/reconcile'),
    ('GET', '/api/admin/stats'),
    ('GET', '/api/admin/users'),
    ('GET', '/api/auth/reviews/me'),
    ('GET', '/api/carts/'),
    ('GET', '/api/checkout-groups/<group_id>'),
    ('GET', '/api/disputes/<order_code>'),
    ('GET', '/api/health'),
    ('GET', '/api/merchant/orders'),
    ('GET', '/api/notifications'),
    ('GET', '/api/orders/<order_code>/status'),
    ('GET', '/api/payments/'),
    ('GET', '/api/payments/orders'),
    ('GET', '/api/products/'),
    ('GET', '/api/products/<product_id>'),
    ('GET', '/api/products/<product_id>/reviews'),
    ('GET', '/api/products/categories'),
    ('GET', '/api/shipper/orders'),
    ('GET', '/api/shops/me'),
    ('GET', '/api/wallet'),
    ('POST', '/api/admin/categories'),
    ('POST', '/api/admin/disputes/<order_code>/force-resolve'),
    ('POST', '/api/admin/disputes/<order_code>/proposal'),
    ('POST', '/api/auth/account/request-deletion'),
    ('POST', '/api/auth/login'),
    ('POST', '/api/auth/signup'),
    ('POST', '/api/carts/items'),
    ('POST', '/api/checkout-groups/<group_id>/quote'),
    ('POST', '/api/disputes/<order_code>/signatures'),
    ('POST', '/api/disputes/<order_code>/submit'),
    ('POST', '/api/orders'),
    ('POST', '/api/orders/<order_code>/dispute-note'),
    ('POST', '/api/orders/eligibility'),
    ('POST', '/api/payments/'),
    ('POST', '/api/payments/checkout'),
    ('POST', '/api/reviews/<product_id>'),
    ('POST', '/api/shipper/orders/<order_code>/deliver'),
    ('POST', '/api/shops/'),
    ('POST', '/api/shops/products'),
    ('POST', '/api/shops/products/<product_id>/images'),
    ('POST', '/api/shops/products/<product_id>/variants'),
    ('POST', '/api/wallet/link'),
    ('POST', '/api/wallet/nonce'),
    ('PUT', '/api/admin/categories/<int:cat_id>'),
    ('PUT', '/api/admin/orders/<order_code>/shipper'),
    ('PUT', '/api/auth/password'),
    ('PUT', '/api/auth/profile'),
    ('PUT', '/api/auth/username'),
    ('PUT', '/api/carts/items/<item_id>'),
    ('PUT', '/api/payments/orders/<order_id>'),
    ('PUT', '/api/shops/me/name'),
    ('PUT', '/api/shops/products/<product_id>'),
]

PUBLIC = {
    ('POST', '/api/auth/login'), ('POST', '/api/auth/signup'), ('GET', '/api/health'),
    ('GET', '/api/products/'), ('GET', '/api/products/<product_id>'),
    ('GET', '/api/products/<product_id>/reviews'), ('GET', '/api/products/categories'),
}
ALL_ROLES = ('user', 'seller', 'shipper', 'admin')


def allowed_roles(method, rule):
    """Vai trò được phép theo SRS 3/7 (nguồn độc lập với decorator trong code)."""
    if rule.startswith('/api/admin/'):
        return {'admin'}
    if rule.startswith('/api/shipper/'):
        return {'shipper'}
    if rule.startswith('/api/merchant/') or rule.startswith('/api/shops/'):
        return {'seller'}
    if rule == '/api/orders/<order_code>/status' or rule == '/api/disputes/<order_code>' \
            or rule == '/api/disputes/<order_code>/submit':
        return {'user', 'seller', 'admin'}
    if rule.startswith(('/api/wallet', '/api/orders', '/api/checkout-groups', '/api/disputes')):
        return {'user', 'seller'}
    return set(ALL_ROLES)          # giỏ, thanh toán, đánh giá, tài khoản, thông báo: chỉ cần đăng nhập


@pytest.fixture(scope='module')
def real_app():
    saved = dict(os.environ)
    os.environ['SLOPEE_SKIP_WEB3_BOOT'] = '1'
    try:
        mod = importlib.import_module('app')      # app.py nạp .env/.env.web3 vào os.environ: khôi phục để không làm bẩn test khác
        return mod.app
    finally:
        os.environ.clear()
        os.environ.update(saved)


@pytest.fixture
def api(real_app, monkeypatch, caplog):
    caplog.set_level(logging.CRITICAL)

    def no_db(*a, **k):
        raise pymysql.err.OperationalError(2003, 'no db in unit test')

    def no_web3(factory=None):
        raise DomainError('WEB3_NOT_CONFIGURED', 'unit test')
    monkeypatch.setattr(pymysql, 'connect', no_db)
    monkeypatch.setattr(container, 'get_container', no_web3)
    return real_app.test_client()


def fill(rule):
    return re.sub(r'<(int:)?[a-z_]+>', lambda m: '1' if m.group(1) else 'x1', rule)


def routes_of(app):
    return sorted((m, r.rule) for r in app.url_map.iter_rules() if r.endpoint != 'static' for m in r.methods - {'HEAD', 'OPTIONS'})


def call(c, method, rule, headers=None):
    return c.open(fill(rule), method=method, json={} if method in ('POST', 'PUT') else None, headers=headers or {})


def bearer(role, uid='u-1'):
    return {'Authorization': f'Bearer {issue_token(uid, role)}'}


# ------------------------------------------------------------------ khóa bề mặt API (Feature Freeze)
def test_route_inventory_is_frozen(real_app):
    actual, expected = set(routes_of(real_app)), set(EXPECTED_ROUTES)
    assert actual == expected, f'API đổi sau Feature Freeze. Thêm: {sorted(actual - expected)}; mất: {sorted(expected - actual)}'


def test_public_allowlist_has_no_stale_entries():
    assert PUBLIC <= set(EXPECTED_ROUTES)


# ------------------------------------------------------------------ A-01
def test_a01_every_non_public_route_requires_a_token(api, real_app):
    bad = []
    for m, rule in routes_of(real_app):
        if (m, rule) in PUBLIC:
            continue
        r = call(api, m, rule)
        if r.status_code != 401 or r.get_json().get('code') != 'auth_required':
            bad.append((m, rule, r.status_code))
    assert not bad, f'Route không đòi token: {bad}'


def test_a01_expired_garbage_and_foreign_tokens_get_401_on_every_protected_route(api, real_app, monkeypatch):
    forged = {'Authorization': 'Bearer ' + __import__('itsdangerous').URLSafeTimedSerializer('other-key', salt='slopee-auth-token-v1').dumps({'uid': 'u', 'role': 'admin'})}
    wrong_scheme = {'Authorization': 'Basic ' + 'x' * 20}
    garbage = {'Authorization': 'Bearer not-a-token'}
    expired = bearer('admin')
    monkeypatch.setattr(auth_utils, 'get_token_ttl', lambda: -1)      # mọi token đã cấp coi như quá hạn
    bad = []
    for m, rule in routes_of(real_app):
        if (m, rule) in PUBLIC:
            continue
        for name, h, code in (('expired', expired, 'token_expired'), ('garbage', garbage, 'token_invalid'),
                              ('forged', forged, 'token_invalid'), ('scheme', wrong_scheme, 'auth_required')):
            r = call(api, m, rule, h)
            if r.status_code != 401 or r.get_json().get('code') != code:
                bad.append((name, m, rule, r.status_code))
    assert not bad, bad


def test_a01_token_without_uid_or_role_is_rejected(api):
    ser = auth_utils._serializer()
    for payload in ({'uid': 'u'}, {'role': 'admin'}, {}, ['admin']):
        r = api.get('/api/admin/users', headers={'Authorization': 'Bearer ' + ser.dumps(payload)})
        assert r.status_code == 401, payload


# ------------------------------------------------------------------ A-02
def test_a02_wrong_role_gets_403_and_right_role_is_not_blocked(api, real_app):
    wrong, blocked = [], []
    for m, rule in routes_of(real_app):
        if (m, rule) in PUBLIC:
            continue
        ok = allowed_roles(m, rule)
        restricted = ok != set(ALL_ROLES)                    # role lạ ('root') chỉ phải bị chặn ở route có hạn chế vai trò
        for role in ALL_ROLES + (('root',) if restricted else ()):
            r = call(api, m, rule, bearer(role))
            if role in ok:
                if r.status_code in (401, 403):
                    blocked.append((role, m, rule, r.status_code))
            elif r.status_code != 403 or r.get_json().get('code') != 'forbidden':
                wrong.append((role, m, rule, r.status_code))
    assert not wrong, f'Sai vai trò mà không bị 403: {wrong}'
    assert not blocked, f'Đúng vai trò mà bị chặn: {blocked}'


def test_a02_admin_namespace_is_closed_to_everyone_but_admin(real_app):
    admin_routes = [x for x in routes_of(real_app) if x[1].startswith('/api/admin/')]
    assert len(admin_routes) >= 12 and all(allowed_roles(*x) == {'admin'} for x in admin_routes)


# ------------------------------------------------------------------ A-04
@pytest.mark.parametrize('role', ['admin', 'shipper', 'Admin', 'SHIPPER', ' admin', 'seller ', '', None, ['admin'], {'a': 1}, 1])
def test_a04_signup_rejects_every_role_but_user_and_seller(api, role):
    body = {'name': 'N', 'email': 'a@b.c', 'phone': '0123456789', 'username': 'someone', 'password': 'pw123456',
            'pass_phrase': '123456', 'role': role}
    r = api.post('/api/auth/signup', json=body)
    assert r.status_code == 403, r.get_data(as_text=True)


# ------------------------------------------------------------------ A-07
def test_a07_no_migration_or_balance_granting_route_over_http(real_app):
    sus = [x for x in routes_of(real_app) if re.search(r'migrat|top-?up|faucet|grant|add-?balance|seed|credit', x[1], re.I)]
    assert sus == []
    assert api_gone(real_app, '/api/shops/migrate')


def api_gone(app, path):
    c = app.test_client()
    return all(c.open(path, method=m).status_code in (404, 405) for m in ('GET', 'POST', 'PUT', 'DELETE'))
