"""Tuần 6 [B] (không cần MySQL/Anvil): quy tắc tạo đề xuất/nhận chữ ký ở domain và ma trận quyền của route. (Chữ ký EIP-712 và vector
đóng băng đã được test ở phần của A: test_w3_eip712 / test_w3_dispute_submit.)"""
import pytest
from flask import Flask

from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container, register_web3
from slopee_web3.domain import dispute as dp
from slopee_web3.domain.errors import DomainError
from slopee_web3.ports.chain_port import ChainUnavailable
from w3_support import ADDR

BUYER, MERCHANT = ADDR['buyer'], ADDR['merchant1']
DAY = 86400


def code_of(fn, *a, **kw):
    with pytest.raises(DomainError) as e:
        fn(*a, **kw)
    return e.value.code


# ------------------------------------------------------------------ domain
def test_deadline_is_the_earlier_of_ttl_and_one_second_before_the_timeout():
    assert dp.compute_deadline(1000, 7 * DAY, 500, 90 * DAY) == 1000 + 7 * DAY            # TTL ngắn hơn: dùng TTL
    assert dp.compute_deadline(1000, 7 * DAY, 500, 14 * DAY) == 1000 + 7 * DAY            # 14 ngày vẫn dài hơn TTL 7 ngày
    assert dp.compute_deadline(1000, 7 * DAY, 500, 7 * DAY) == 500 + 7 * DAY - 1          # sát hạn xử đơn phương: lùi về mốc − 1
    assert dp.compute_deadline(1000, 10 ** 9, 500, 7 * DAY) < 500 + 7 * DAY               # luôn nhỏ hơn disputedAt + disputeTimeout
    assert dp.compute_deadline(500 + 7 * DAY - 1, 7 * DAY, 500, 7 * DAY) == 500 + 7 * DAY - 1


@pytest.mark.parametrize('value,expected', [('buyer', 'BUYER'), ('BUYER', 'BUYER'), (' Merchant ', 'MERCHANT'), ('MERCHANT', 'MERCHANT'),
                                            (BUYER, 'BUYER'), (BUYER.lower(), 'BUYER'), (MERCHANT.lower(), 'MERCHANT')])
def test_payout_accepts_role_words_or_the_exact_party_address(value, expected):
    party, address = dp.parse_payout(value, BUYER, MERCHANT)
    assert party == expected and address == (BUYER if expected == 'BUYER' else MERCHANT)


@pytest.mark.parametrize('bad', [None, '', '   ', 'admin', 'arbitrator', ADDR['arbitrator'], '0x' + '0' * 40, 123, ['buyer'], {'a': 1}])
def test_payout_rejects_anyone_but_buyer_or_merchant(bad):
    assert code_of(dp.parse_payout, bad, BUYER, MERCHANT) == 'INVALID_PAYOUT'


def test_party_is_derived_only_from_the_user_id():
    assert dp.party_of('b', 'b', 'm') == 'BUYER' and dp.party_of('m', 'b', 'm') == 'MERCHANT' and dp.party_of('x', 'b', 'm') is None
    assert dp.party_of(None, 'b', 'm') is None


def test_two_of_three_rule_needs_two_distinct_parties():
    assert not dp.is_ready(set()) and not dp.is_ready({'ARBITRATOR'}) and not dp.is_ready({'BUYER'}) and not dp.is_ready({'MERCHANT'})
    assert dp.is_ready({'ARBITRATOR', 'BUYER'}) and dp.is_ready({'ARBITRATOR', 'MERCHANT'}) and dp.is_ready({'BUYER', 'MERCHANT'})
    assert dp.is_ready({'ARBITRATOR', 'BUYER', 'MERCHANT'})


def test_active_states_are_the_non_terminal_ones():
    assert dp.ACTIVE_STATES == ('PROPOSED', 'READY', 'SUBMITTED')
    assert set(dp.ACTIVE_STATES).isdisjoint({'EXECUTED', 'EXPIRED', 'CANCELLED'})


@pytest.mark.parametrize('value,ok', [(None, None), ('', None), ('  ', None), (' ghi chú ', 'ghi chú')])
def test_note_is_optional_and_trimmed(value, ok):
    assert dp.clean_note(value) == ok


def test_note_rejects_non_strings_and_oversize():
    assert code_of(dp.clean_note, 5) == 'INVALID_DISPUTE_NOTE' and code_of(dp.clean_note, 'x' * 2001) == 'INVALID_DISPUTE_NOTE'
    assert dp.clean_note('x' * 2000) == 'x' * 2000


# ------------------------------------------------------------------ route
class Svc:
    def __init__(self):
        self.calls, self.raises = [], None

    def _do(self, name, *a, result):
        self.calls.append((name, a))
        if self.raises:
            raise self.raises
        return result

    def propose(self, admin, code, payout, note): return self._do('propose', admin, code, payout, note, result={'resolution_id': 1})
    def add_signature(self, uid, code, rid, sig): return self._do('sign', uid, code, rid, sig, result={'status': 'READY'})
    def get(self, uid, role, code): return self._do('get', uid, role, code, result={'order_id': code})


class FakeContainer:
    def __init__(self, svc):
        self.svc = svc

    def dispute_service(self):
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


def H(uid='u1', role='user'):
    return {'Authorization': f'Bearer {issue_token(uid, role)}'}


SIG = '0x' + 'ab' * 65
ROUTES = [('POST', '/api/admin/disputes/o1/proposal', {'payout_to': 'BUYER'}), ('GET', '/api/disputes/o1', None),
          ('POST', '/api/disputes/o1/signatures', {'resolution_id': 1, 'signature': SIG})]


@pytest.mark.parametrize('method,path,body', ROUTES)
def test_every_route_requires_a_token(client, svc, method, path, body):
    assert client.open(path, method=method, json=body).status_code == 401 and svc.calls == []


@pytest.mark.parametrize('role', ['user', 'seller', 'shipper'])
def test_proposal_is_admin_only(client, svc, role):
    assert client.post('/api/admin/disputes/o1/proposal', json={'payout_to': 'BUYER'}, headers=H(role=role)).status_code == 403
    assert svc.calls == []


@pytest.mark.parametrize('role', ['admin', 'shipper'])
def test_only_buyer_roles_may_sign(client, svc, role):
    r = client.post('/api/disputes/o1/signatures', json={'resolution_id': 1, 'signature': SIG}, headers=H(role=role))
    assert r.status_code == 403 and svc.calls == []             # Admin không phải bên của đơn: không ký thay


def test_shipper_cannot_read_a_dispute(client, svc):
    assert client.get('/api/disputes/o1', headers=H(role='shipper')).status_code == 403 and svc.calls == []


def test_identity_comes_from_the_token_only(client, svc):
    client.post('/api/disputes/ord-1/signatures', json={'resolution_id': 7, 'signature': SIG, 'party': 'MERCHANT', 'user_id': 'evil'},
                headers=H('me', 'seller'))
    assert svc.calls[-1] == ('sign', ('me', 'ord-1', 7, SIG))
    client.post('/api/admin/disputes/ord-2/proposal', json={'payout_to': 'MERCHANT', 'reason_note': 'đủ bằng chứng', 'admin': 'evil'},
                headers=H('adm', 'admin'))
    assert svc.calls[-1] == ('propose', ('adm', 'ord-2', 'MERCHANT', 'đủ bằng chứng'))
    client.get('/api/disputes/ord-3?role=admin&user_id=evil', headers=H('me', 'user'))
    assert svc.calls[-1] == ('get', ('me', 'user', 'ord-3'))


def test_proposal_returns_201_and_missing_payout_reaches_the_domain(client, svc):
    assert client.post('/api/admin/disputes/o1/proposal', json={'payout_to': 'BUYER'}, headers=H('a', 'admin')).status_code == 201
    client.post('/api/admin/disputes/o1/proposal', json={}, headers=H('a', 'admin'))
    assert svc.calls[-1] == ('propose', ('a', 'o1', None, None))


@pytest.mark.parametrize('body', [{}, {'signature': SIG}, {'resolution_id': 0, 'signature': SIG}, {'resolution_id': -3, 'signature': SIG},
                                   {'resolution_id': 'abc', 'signature': SIG}, {'resolution_id': True, 'signature': SIG},
                                   {'resolution_id': 1.5, 'signature': SIG}, {'resolution_id': None, 'signature': SIG}])
def test_signature_route_validates_resolution_id_before_the_service(client, svc, body):
    assert client.post('/api/disputes/o1/signatures', json=body, headers=H()).status_code == 400 and svc.calls == [], body


def test_resolution_id_accepts_int_like_values(client, svc):
    for rid in (5, '5', 5.0):
        assert client.post('/api/disputes/o1/signatures', json={'resolution_id': rid, 'signature': SIG}, headers=H()).status_code == 200
    assert [c[1][2] for c in svc.calls] == [5, 5, 5]


@pytest.mark.parametrize('code,status', [('BAD_SIGNATURE', 400), ('DISPUTE_NOT_FOUND', 404), ('ORDER_NOT_FOUND', 404),
                                         ('SIGNATURE_EXPIRED', 409), ('ALREADY_SIGNED', 409), ('DISPUTE_WINDOW_CLOSED', 409),
                                         ('INVALID_STATE', 409), ('INVALID_PAYOUT', 422), ('INVALID_DISPUTE_NOTE', 422)])
def test_domain_errors_map_to_http_with_vietnamese_message(client, svc, code, status):
    svc.raises = DomainError(code, 'Thông báo tiếng Việt', {'status': 'READY'})
    r = client.post('/api/disputes/o1/signatures', json={'resolution_id': 1, 'signature': SIG}, headers=H())
    body = r.get_json()
    assert r.status_code == status and body['code'] == code and body['message'] == 'Thông báo tiếng Việt' and body['status'] == 'READY'


def test_rpc_down_is_503_without_leaking_the_url(client, svc):
    svc.raises = ChainUnavailable('Connection refused: http://127.0.0.1:8545')
    r = client.post('/api/admin/disputes/o1/proposal', json={'payout_to': 'BUYER'}, headers=H('a', 'admin'))
    assert r.status_code == 503 and r.get_json()['code'] == 'CHAIN_UNAVAILABLE' and '127.0.0.1' not in r.get_data(as_text=True)
