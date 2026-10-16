"""API Web3 (SRS 7): xác thực, phân quyền, kiểm đầu vào, ánh xạ lỗi {code, message}. Service được thay bằng bản giả."""
import pytest
from flask import Flask

from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container, register_web3
from slopee_web3.domain.errors import DomainError
from slopee_web3.ports.chain_port import ChainUnavailable


class Svc:
    def __init__(self):
        self.calls = []
        self.raises = None

    def _do(self, name, *a, result=None):
        self.calls.append((name, a))
        if self.raises:
            raise self.raises
        return result or {'ok': True}

    def issue_nonce(self, uid, address): return self._do('issue_nonce', uid, address, result={'nonce': 'n', 'message': 'm', 'expires_at': 1})
    def link_wallet(self, uid, address, sig, nonce): return self._do('link_wallet', uid, address, sig, nonce)
    def get_wallet(self, uid): return self._do('get_wallet', uid)
    def create_checkout(self, uid, ids): return self._do('create_checkout', uid, ids)
    def reissue_group_quotes(self, uid, gid): return self._do('reissue', uid, gid)
    def get_group(self, uid, gid): return self._do('get_group', uid, gid)
    def check_web3_eligibility(self, uid, ids): return self._do('eligibility', uid, ids, result={'all_linked': True, 'shops': []})


class FakeContainer:
    def __init__(self, svc):
        self.svc = svc

    def wallet_service(self): return self.svc
    def quote_service(self): return self.svc


@pytest.fixture
def svc():
    s = Svc()
    container.set_container(FakeContainer(s))
    yield s
    container.set_container(None)


@pytest.fixture
def client(svc):
    app = Flask(__name__)
    register_web3(app)
    return app.test_client()


def H(uid='u1', role='user'):
    return {'Authorization': f'Bearer {issue_token(uid, role)}'}


ADDR = '0x' + 'a' * 40
ROUTES = [('POST', '/api/wallet/nonce', {'address': ADDR}), ('POST', '/api/wallet/link', {'address': ADDR, 'signature': '0x' + '1' * 130}),
          ('GET', '/api/wallet', None), ('POST', '/api/orders', {'cart_item_ids': ['c1']}),
          ('POST', '/api/checkout-groups/g1/quote', {}), ('GET', '/api/checkout-groups/g1', None),
          ('POST', '/api/orders/eligibility', {'cart_item_ids': ['c1']})]


@pytest.mark.parametrize('method,path,body', ROUTES)
def test_every_route_requires_auth(client, svc, method, path, body):
    r = client.open(path, method=method, json=body)
    assert r.status_code == 401 and r.get_json()['code'] == 'auth_required'
    assert svc.calls == []


@pytest.mark.parametrize('role', ['admin', 'shipper'])
@pytest.mark.parametrize('method,path,body', ROUTES)
def test_admin_and_shipper_are_forbidden(client, svc, role, method, path, body):
    r = client.open(path, method=method, json=body, headers=H(role=role))
    assert r.status_code == 403 and svc.calls == []


@pytest.mark.parametrize('role', ['user', 'seller'])
def test_user_and_seller_allowed(client, svc, role):
    assert client.post('/api/wallet/nonce', json={'address': ADDR}, headers=H(role=role)).status_code == 200


def test_identity_comes_from_token_not_body(client, svc):
    client.post('/api/wallet/link', json={'address': ADDR, 'signature': '0x1', 'userId': 'victim', 'user_id': 'victim'},
                headers=H('real-user'))
    assert svc.calls[0][1][0] == 'real-user'
    client.post('/api/orders', json={'cart_item_ids': ['c1'], 'buyer_user_id': 'victim'}, headers=H('real-user'))
    assert svc.calls[1][1][0] == 'real-user'


def test_nonce_and_link_validate_input(client):
    for body in ({}, {'address': 5}, {'address': ''}):
        r = client.post('/api/wallet/nonce', json=body, headers=H())
        assert r.status_code == 400 and set(r.get_json()) >= {'code', 'message'}
    r = client.post('/api/wallet/link', json={'address': ADDR}, headers=H())
    assert r.status_code == 400
    r = client.post('/api/wallet/nonce', data='not json', headers={**H(), 'Content-Type': 'application/json'})
    assert r.status_code == 400


def test_link_passes_optional_nonce(client, svc):
    client.post('/api/wallet/link', json={'address': ADDR, 'signature': '0x1', 'nonce': 'n1'}, headers=H())
    assert svc.calls[-1][1][3] == 'n1'
    client.post('/api/wallet/link', json={'address': ADDR, 'signature': '0x1'}, headers=H())
    assert svc.calls[-1][1][3] is None


@pytest.mark.parametrize('body,code', [({}, 'EMPTY_CART'), ({'cart_item_ids': []}, 'EMPTY_CART'), ({'cart_item_ids': 'x'}, 'EMPTY_CART'),
                                        ({'cart_item_ids': [1]}, 'CART_ITEM_NOT_FOUND'), ({'cart_item_ids': ['']}, 'CART_ITEM_NOT_FOUND'),
                                        ({'cart_item_ids': ['x' * 37]}, 'CART_ITEM_NOT_FOUND'),
                                        ({'cart_item_ids': ['a'] * 101}, 'INVALID_AMOUNT')])
def test_create_order_input_validation(client, svc, body, code):
    r = client.post('/api/orders', json=body, headers=H())
    assert r.get_json()['code'] == code and svc.calls == []


def test_create_order_success_is_201_and_trims_ids(client, svc):
    r = client.post('/api/orders', json={'cart_item_ids': [' a ', 'b']}, headers=H())
    assert r.status_code == 201 and svc.calls[0][1][1] == ['a', 'b']


@pytest.mark.parametrize('code,status', [('WALLET_NOT_LINKED', 409), ('QUOTE_EXPIRED', 410), ('RATE_LIMITED', 429),
                                          ('BATCH_TOO_LARGE', 422), ('POLICY_OUT_OF_RANGE', 422), ('GROUP_NOT_FOUND', 404),
                                          ('NONCE_INVALID', 400)])
def test_domain_errors_map_to_status_and_vietnamese_message(client, svc, code, status):
    svc.raises = DomainError(code, 'Thông báo tiếng Việt', {'shop_id': 's1'})
    r = client.post('/api/orders', json={'cart_item_ids': ['a']}, headers=H())
    body = r.get_json()
    assert r.status_code == status and body == {'code': code, 'message': 'Thông báo tiếng Việt', 'shop_id': 's1'}


def test_chain_unavailable_is_503(client, svc):
    svc.raises = ChainUnavailable('Connection refused http://127.0.0.1:8545 secret')
    r = client.post('/api/orders', json={'cart_item_ids': ['a']}, headers=H())
    assert r.status_code == 503 and r.get_json()['code'] == 'CHAIN_UNAVAILABLE'
    assert '127.0.0.1' not in r.get_data(as_text=True)          # chi tiết hạ tầng không lộ ra client


def test_unexpected_error_is_500_without_leaking_details(client, svc):
    svc.raises = RuntimeError('SELECT * FROM users password=hunter2')
    r = client.get('/api/wallet', headers=H())
    assert r.status_code == 500 and r.get_json()['code'] == 'internal_error'
    assert 'hunter2' not in r.get_data(as_text=True) and 'SELECT' not in r.get_data(as_text=True)


def test_web3_not_configured_returns_503(monkeypatch):
    monkeypatch.delenv('ESCROW_ADDRESS', raising=False)
    container.set_container(None)
    app = Flask(__name__)
    register_web3(app)
    r = app.test_client().get('/api/wallet', headers=H())
    assert r.status_code == 503 and r.get_json()['code'] == 'WEB3_NOT_CONFIGURED'


def test_group_routes_pass_ids(client, svc):
    client.post('/api/checkout-groups/abc/quote', headers=H('u9'))
    client.get('/api/checkout-groups/abc', headers=H('u9'))
    assert svc.calls == [('reissue', ('u9', 'abc')), ('get_group', ('u9', 'abc'))]


def test_eligibility_route_validates_like_create_order_and_uses_token_identity(client, svc):
    assert client.post('/api/orders/eligibility', json={}, headers=H()).get_json()['code'] == 'EMPTY_CART'
    assert client.post('/api/orders/eligibility', json={'cart_item_ids': [5]}, headers=H()).get_json()['code'] == 'CART_ITEM_NOT_FOUND'
    r = client.post('/api/orders/eligibility', json={'cart_item_ids': [' a ', 'b'], 'user_id': 'victim'}, headers=H('real'))
    assert r.status_code == 200 and r.get_json()['all_linked'] is True          # đọc thuần: 200, không phải 201
    assert svc.calls[-1] == ('eligibility', ('real', ['a', 'b']))
