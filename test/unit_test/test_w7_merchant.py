"""Tuần 7 [A] UC-07 cổng Merchant (không cần MySQL/Anvil): `MerchantService` (đơn của shop mình + số dư chờ rút) và route `GET /api/merchant/orders`."""
import pytest
from flask import Flask

from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container, register_web3
from slopee_web3.application.merchant_service import LISTED_STATES, MAX_ORDERS, MerchantService
from slopee_web3.domain.errors import DomainError
from slopee_web3.ports.chain_port import ChainUnavailable

TOKEN = '0x5FbDB2315678afecb367f032d93F642f64180aa3'
M1 = '0x' + 'a1' * 20
ZERO = '0x' + '0' * 40


def order(**kw):
    row = {'order_id': 'o-1', 'onchain_order_id': 100001, 'status': 'LOCKED', 'amount_raw': '1000000', 'token_symbol': 'mUSD',
           'token_address': TOKEN, 'price_vnd': 25_000_000, 'fee_bps': 250, 'merchant_wallet': M1.upper().replace('0X', '0x'),
           'inspection_duration': 3600, 'dispute_timeout': 7 * 86400, 'chain_created_at': 1_800_000_000, 'delivered_at': None,
           'disputed_at': None, 'closed_at': None, 'buyer_name': 'An', 'items': [{'name': 'Áo', 'quantity': 2, 'variants': None}]}
    row.update(kw)
    return row


class FakeMerchantRepo:
    def __init__(self, orders=(), wallets=(), pending=()):
        self.orders, self.wallets, self.pending = list(orders), list(wallets), list(pending)
        self.calls = []

    def merchant_orders(self, merchant_user_id, statuses, limit):
        self.calls.append(('orders', merchant_user_id, tuple(statuses), limit))
        return [dict(o) for o in self.orders]

    def merchant_wallets(self, merchant_user_id):
        self.calls.append(('wallets', merchant_user_id))
        return list(self.wallets)

    def pending_for_addresses(self, addresses):
        self.calls.append(('pending', tuple(addresses)))
        return [dict(p) for p in self.pending]


class FakeWallets:
    def __init__(self, active=None):
        self.active = active

    def active_wallet(self, user_id):
        return None if self.active is None else {'address': self.active, 'linked_at': 1}


class FakeUow:
    def __init__(self, repo, wallets):
        self.merchant, self.wallets, self.committed = repo, wallets, False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def commit(self):
        self.committed = True


def make(orders=(), wallets=(), pending=(), active=None, tokens=None):
    repo = FakeMerchantRepo(orders, wallets, pending)
    uow = FakeUow(repo, FakeWallets(active))
    svc = MerchantService(lambda: uow, tokens=tokens if tokens is not None else {TOKEN: {'symbol': 'mUSD', 'decimals': 6}})
    return svc, repo, uow


# ------------------------------------------------------------------ service
def test_lists_only_funded_orders_and_always_scopes_by_caller_id():
    svc, repo, uow = make()
    out = svc.list_orders('seller-1')
    assert out == {'wallet': None, 'orders': [], 'pending': []}
    assert repo.calls[0] == ('orders', 'seller-1', LISTED_STATES, MAX_ORDERS)
    assert 'PENDING_PAYMENT' not in LISTED_STATES and 'EXPIRED' not in LISTED_STATES      # chưa có tiền trên chuỗi: không phải việc của shop
    assert set(LISTED_STATES) == {'LOCKED', 'DELIVERED', 'DISPUTED', 'COMPLETED', 'REFUNDED'}
    assert uow.committed is False                                                           # chỉ đọc


def test_order_row_amounts_are_exact_strings_and_net_matches_contract_rounding():
    big = 10 ** 30 + 7                                                                      # vượt 2^53 và 2^64: không được qua float
    svc, _, _ = make([order(amount_raw=str(big), fee_bps=333)])
    o = svc.list_orders('s')['orders'][0]
    fee = big * 333 // 10_000
    assert o['amount_raw'] == str(big) and o['fee_amount_raw'] == str(fee) and o['net_amount_raw'] == str(big - fee)
    assert int(o['net_amount_raw']) + int(o['fee_amount_raw']) == big
    assert all(isinstance(o[k], str) for k in ('amount_raw', 'net_amount_raw', 'fee_amount_raw', 'onchain_order_id'))
    assert o['price_vnd'] == 25_000_000 and isinstance(o['price_vnd'], int)


def test_zero_fee_pays_merchant_everything():
    svc, _, _ = make([order(amount_raw='999', fee_bps=0)])
    o = svc.list_orders('s')['orders'][0]
    assert o['net_amount_raw'] == '999' and o['fee_amount_raw'] == '0'


def test_token_metadata_eth_known_and_unknown():
    svc, _, _ = make([order(token_address=None, token_symbol='ETH'), order(order_id='o-2'),
                      order(order_id='o-3', token_address='0x' + 'ee' * 20, token_symbol='XYZ')])
    eth, known, unknown = svc.list_orders('s')['orders']
    assert (eth['token'], eth['symbol'], eth['decimals']) == ('ETH', 'ETH', 18)
    assert (known['token'], known['symbol'], known['decimals']) == (TOKEN.lower(), 'mUSD', 6)
    assert (unknown['symbol'], unknown['decimals']) == ('XYZ', None)                        # token lạ: không đoán số thập phân


def test_deadlines_are_only_given_for_the_state_they_belong_to():
    svc, _, _ = make([
        order(order_id='l', status='LOCKED'),
        order(order_id='d', status='DELIVERED', delivered_at=1_800_001_000, inspection_duration=600),
        order(order_id='x', status='DISPUTED', delivered_at=1_800_001_000, disputed_at=1_800_002_000, dispute_timeout=7 * 86400),
        order(order_id='c', status='COMPLETED', delivered_at=1_800_001_000, closed_at=1_800_005_000),
    ])
    by = {o['order_id']: o for o in svc.list_orders('s')['orders']}
    assert by['l']['delivery_deadline'] == 1_800_000_000 + 14 * 86400 and by['l']['release_at'] is None and by['l']['force_resolve_at'] is None
    assert by['d']['release_at'] == 1_800_001_600 and by['d']['delivery_deadline'] is None
    assert by['x']['force_resolve_at'] == 1_800_002_000 + 7 * 86400 and by['x']['release_at'] is None
    assert (by['c']['delivery_deadline'], by['c']['release_at'], by['c']['force_resolve_at']) == (None, None, None)
    assert by['c']['closed_at'] == 1_800_005_000


def test_wallet_is_lowercase_or_none_and_order_wallet_lowercased():
    svc, _, _ = make([order()], active='0xAbC' + '0' * 37)
    out = svc.list_orders('s')
    assert out['wallet'] == ('0xabc' + '0' * 37) and out['orders'][0]['merchant_wallet'] == out['orders'][0]['merchant_wallet'].lower()
    assert make()[0].list_orders('s')['wallet'] is None


def test_pending_balances_use_the_merchants_wallets_merge_and_drop_zero():
    rows = [{'token_address': ZERO, 'address': M1, 'amount_raw': '5'}, {'token_address': None, 'address': M1.upper().replace('0X', '0x'), 'amount_raw': '7'},
            {'token_address': TOKEN, 'address': M1, 'amount_raw': '0'}, {'token_address': TOKEN, 'address': '0x' + 'b2' * 20, 'amount_raw': '9'}]
    svc, repo, _ = make(wallets=[M1, '0x' + 'b2' * 20], pending=rows)
    out = svc.list_orders('s')['pending']
    assert ('pending', (M1, '0x' + 'b2' * 20)) in repo.calls                                # chỉ hỏi số dư của ví thuộc người gọi
    assert out == [
        {'token': 'ETH', 'address': M1, 'amount_raw': '12', 'symbol': 'ETH', 'decimals': 18},
        {'token': TOKEN.lower(), 'address': '0x' + 'b2' * 20, 'amount_raw': '9', 'symbol': 'mUSD', 'decimals': 6},
    ]


def test_pending_amounts_above_2_pow_64_stay_exact():
    big = 2 ** 70 + 1
    svc, _, _ = make(wallets=[M1], pending=[{'token_address': ZERO, 'address': M1, 'amount_raw': str(big)}])
    assert svc.list_orders('s')['pending'][0]['amount_raw'] == str(big)


def test_response_never_leaks_other_parties_wallets_or_signatures():
    svc, _, _ = make([order(buyer_wallet='0x' + 'bb' * 20, doc_hash='0x1', deposit_tx_hash='0x2', buyer_user_id='buyer-secret')])
    o = svc.list_orders('s')['orders'][0]
    for leaked in ('buyer_wallet', 'buyer_user_id', 'doc_hash', 'deposit_tx_hash', 'signature'):
        assert leaked not in o


# ------------------------------------------------------------------ route
class Svc:
    def __init__(self):
        self.calls, self.raises = [], None

    def list_orders(self, uid):
        self.calls.append(uid)
        if self.raises:
            raise self.raises
        return {'wallet': None, 'orders': [], 'pending': []}


class FakeContainer:
    def __init__(self, svc):
        self.svc = svc

    def merchant_service(self):
        return self.svc


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


def H(uid='seller-1', role='seller'):
    return {'Authorization': f'Bearer {issue_token(uid, role)}'}


def test_route_requires_a_token(client, svc):
    r = client.get('/api/merchant/orders')
    assert r.status_code == 401 and r.get_json()['code'] == 'auth_required' and svc.calls == []


@pytest.mark.parametrize('role', ['user', 'shipper', 'admin'])
def test_route_is_for_sellers_only(client, svc, role):
    r = client.get('/api/merchant/orders', headers=H(role=role))
    assert r.status_code == 403 and r.get_json()['code'] == 'forbidden' and svc.calls == []


def test_route_takes_identity_from_token_only(client, svc):
    r = client.get('/api/merchant/orders?merchant_user_id=evil&userId=evil&sellerId=evil', headers=H('real-seller'))
    assert r.status_code == 200 and r.get_json() == {'wallet': None, 'orders': [], 'pending': []}
    assert svc.calls == ['real-seller']


def test_route_is_read_only(client, svc):
    for method in ('post', 'put', 'delete', 'patch'):
        assert getattr(client, method)('/api/merchant/orders', headers=H(), json={}).status_code == 405
    assert svc.calls == []


def test_route_maps_domain_and_chain_errors_to_vietnamese_envelope(client, svc):
    svc.raises = DomainError('WEB3_NOT_CONFIGURED', 'Chưa cấu hình Web3.')
    r = client.get('/api/merchant/orders', headers=H())
    assert r.status_code == 503 and r.get_json() == {'code': 'WEB3_NOT_CONFIGURED', 'message': 'Chưa cấu hình Web3.'}
    svc.raises = ChainUnavailable('Connection refused: http://127.0.0.1:8545')
    r = client.get('/api/merchant/orders', headers=H())
    assert r.status_code == 503 and r.get_json()['code'] == 'CHAIN_UNAVAILABLE' and '127.0.0.1' not in r.get_data(as_text=True)
    svc.raises = RuntimeError('SELECT * FROM secret')
    r = client.get('/api/merchant/orders', headers=H())
    assert r.status_code == 500 and r.get_json()['code'] == 'internal_error' and 'secret' not in r.get_data(as_text=True)
