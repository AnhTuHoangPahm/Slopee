import time

import pytest
from itsdangerous import BadSignature, SignatureExpired

import auth_utils


def test_issue_and_verify_roundtrip():
    token = auth_utils.issue_token('u1', 'seller')
    assert auth_utils.verify_token(token) == {'uid': 'u1', 'role': 'seller'}


def test_tampered_token_rejected():
    token = auth_utils.issue_token('u1', 'user')
    with pytest.raises(BadSignature):
        auth_utils.verify_token(token[:-2] + ('AA' if not token.endswith('AA') else 'BB'))


def test_token_signed_with_other_key_rejected(monkeypatch):
    token = auth_utils.issue_token('u1', 'admin')
    monkeypatch.setenv('SECRET_KEY', 'another-key')
    with pytest.raises(BadSignature):
        auth_utils.verify_token(token)


def test_expired_token_rejected(monkeypatch):
    token = auth_utils.issue_token('u1', 'user')
    monkeypatch.setenv('AUTH_TOKEN_TTL_SECONDS', '1')
    time.sleep(2.1)
    with pytest.raises(SignatureExpired):
        auth_utils.verify_token(token)


def test_secret_key_required_outside_dev(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.setenv('SLOPEE_ENV', 'production')
    with pytest.raises(RuntimeError):
        auth_utils.get_secret_key()


def test_ttl_from_env(monkeypatch):
    monkeypatch.setenv('AUTH_TOKEN_TTL_SECONDS', '120')
    assert auth_utils.get_token_ttl() == 120
    monkeypatch.setenv('AUTH_TOKEN_TTL_SECONDS', 'abc')
    assert auth_utils.get_token_ttl() == auth_utils.DEFAULT_TTL_SECONDS


def test_missing_and_garbage_headers(client):
    r = client.get('/api/cart/')
    assert r.status_code == 401 and r.get_json()['code'] == 'auth_required'
    r = client.get('/api/cart/', headers={'Authorization': 'Basic abc'})
    assert r.status_code == 401
    r = client.get('/api/cart/', headers={'Authorization': 'Bearer not-a-token'})
    assert r.status_code == 401 and r.get_json()['code'] == 'token_invalid'


def test_expired_token_returns_token_expired(client, monkeypatch, auth_headers):
    monkeypatch.setattr(auth_utils, 'verify_token', lambda t: (_ for _ in ()).throw(SignatureExpired('x')))
    r = client.get('/api/cart/', headers=auth_headers)
    assert r.status_code == 401 and r.get_json()['code'] == 'token_expired'


def test_user_id_in_url_is_gone(client, auth_headers):
    """Các route cũ /<userId> không còn tồn tại (S-01)."""
    assert client.get('/api/cart/some-other-user', headers=auth_headers).status_code == 404
    assert client.get('/api/checkout/some-other-user', headers=auth_headers).status_code in (404, 405)
    assert client.get('/api/auth/reviews/some-other-user', headers=auth_headers).status_code == 404
