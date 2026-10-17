"""POST /api/orders/:code/dispute-note (UC-05, SEQ-02), không cần MySQL: quy tắc làm sạch ở domain + ma trận quyền/ánh xạ lỗi của route."""
import pytest
from flask import Flask

from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container, register_web3
from slopee_web3.domain import dispute_note as dn
from slopee_web3.domain.errors import DomainError


def code_of(fn, *a):
    with pytest.raises(DomainError) as e:
        fn(*a)
    return e.value.code


# ------------------------------------------------------------------ lý do
def test_reason_is_trimmed_and_bounded():
    assert dn.clean_reason('  Hàng bị vỡ  ') == 'Hàng bị vỡ'
    assert dn.clean_reason('x' * dn.MAX_REASON_LEN) == 'x' * dn.MAX_REASON_LEN
    for bad in (None, '', '   ', 'ab', 12345, ['a'], {'a': 1}, 'x' * (dn.MAX_REASON_LEN + 1)):
        assert code_of(dn.clean_reason, bad) == 'INVALID_DISPUTE_NOTE', repr(bad)


def test_backend_is_never_stricter_than_the_ui_minimum():
    assert dn.MIN_REASON_LEN <= 3                       # giao diện được phép chặt hơn; backend chỉ chặn rác


# ------------------------------------------------------------------ đường dẫn bằng chứng
@pytest.mark.parametrize('url', [
    'https://example.com/a.jpg', 'http://example.com', 'HTTPS://Example.com/x?y=1&z=2#f', 'https://drive.google.com/file/d/1/view',
    'http://localhost:8080/evidence/1.png', 'https://192.168.1.5/x', 'https://[::1]:8443/x', 'https://a.com/@nguoi-dung', 'https://shop.sieu-thi.vn/anh.jpg',
])
def test_http_and_https_links_are_accepted(url):
    assert dn.clean_evidence_url(url) == url


@pytest.mark.parametrize('empty', [None, '', '   '])
def test_evidence_is_optional(empty):
    assert dn.clean_evidence_url(empty) is None


@pytest.mark.parametrize('url', [
    'javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'data:text/html;base64,PHNjcmlwdD4=', 'file:///etc/passwd', 'ftp://example.com/x',
    'vbscript:x', '//example.com/x', 'example.com/x', 'https://', 'https:///x', 'http://',
    'https://user:pass@example.com/x', 'https://example.com@evil.com/x', 'https://a.com\\@evil.com/x',           # userinfo: lưu mật khẩu / đánh lừa tên miền
    'https://exa mple.com/x', 'https://example.com/a b', 'https://example.com/\nX', 'https://example.com/\x00',
    'https://example.com/' + 'a' * dn.MAX_EVIDENCE_URL_LEN, 123, ['https://a.com'], {'u': 'https://a.com'},
])
def test_dangerous_or_malformed_links_are_rejected(url):
    assert code_of(dn.clean_evidence_url, url) == 'INVALID_DISPUTE_NOTE', repr(url)


def test_url_length_limit_is_inclusive_at_500():
    ok = 'https://a.co/' + 'a' * (dn.MAX_EVIDENCE_URL_LEN - len('https://a.co/'))
    assert len(ok) == dn.MAX_EVIDENCE_URL_LEN and dn.clean_evidence_url(ok) == ok


# ------------------------------------------------------------------ route
class Svc:
    def __init__(self):
        self.calls, self.raises = [], None

    def save_note(self, user_id, code, reason, evidence_url):
        self.calls.append((user_id, code, reason, evidence_url))
        if self.raises:
            raise self.raises
        return {'order_id': code, 'reason': reason, 'evidence_url': evidence_url, 'created': True}


class FakeContainer:
    def __init__(self, svc):
        self.svc = svc

    def dispute_note_service(self):
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


def test_requires_a_token(client, svc):
    r = client.post('/api/orders/o1/dispute-note', json={'reason': 'hàng hỏng'})
    assert r.status_code == 401 and r.get_json()['code'] == 'auth_required' and svc.calls == []


@pytest.mark.parametrize('role', ['admin', 'shipper'])
def test_only_buyer_roles_may_send_a_note(client, svc, role):
    r = client.post('/api/orders/o1/dispute-note', json={'reason': 'hàng hỏng'}, headers=H(role=role))
    assert r.status_code == 403 and r.get_json()['code'] == 'forbidden' and svc.calls == []


@pytest.mark.parametrize('role', ['user', 'seller'])           # người bán cũng có thể là Buyer của đơn khác
def test_buyer_roles_pass_and_identity_comes_from_token_only(client, svc, role):
    r = client.post('/api/orders/ord-9/dispute-note', json={'reason': 'Hàng bị vỡ', 'evidence_url': 'https://a.com/x',
                                                            'user_id': 'evil', 'buyer_user_id': 'evil'}, headers=H('me', role))
    assert r.status_code == 200 and r.get_json()['order_id'] == 'ord-9'
    assert svc.calls == [('me', 'ord-9', 'Hàng bị vỡ', 'https://a.com/x')]


def test_missing_fields_are_passed_as_none_and_validated_by_the_domain(client, svc):
    client.post('/api/orders/o1/dispute-note', json={}, headers=H())
    client.post('/api/orders/o1/dispute-note', headers=H())                  # không body
    assert svc.calls == [('u1', 'o1', None, None)] * 2


def test_malformed_json_body_is_400_not_500(client, svc):
    r = client.post('/api/orders/o1/dispute-note', data='{không phải json', content_type='application/json', headers=H())
    assert r.status_code == 400 and r.get_json()['code'] == 'invalid_body' and svc.calls == []
    r = client.post('/api/orders/o1/dispute-note', json=['a'], headers=H())
    assert r.status_code == 400 and svc.calls == []


@pytest.mark.parametrize('code,status', [('INVALID_DISPUTE_NOTE', 422), ('ORDER_NOT_FOUND', 404), ('INVALID_STATE', 409)])
def test_domain_errors_map_to_http_with_vietnamese_message(client, svc, code, status):
    svc.raises = DomainError(code, 'Thông báo tiếng Việt', {'status': 'LOCKED'})
    r = client.post('/api/orders/o1/dispute-note', json={'reason': 'abc'}, headers=H())
    body = r.get_json()
    assert r.status_code == status and body['code'] == code and body['message'] == 'Thông báo tiếng Việt'
