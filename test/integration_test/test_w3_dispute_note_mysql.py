"""Ghi chú khiếu nại trên MySQL THẬT: đúng thứ tự SEQ-02 (raiseDispute -> Indexer DISPUTED -> mới gửi lý do), quyền, idempotent,
khóa sau khi có đề xuất phán quyết, và HTTP đầu cuối gồm CORS preflight (nguyên nhân vòng lặp lỗi 404 ở PROGRESS Tuần 5 mục 10)."""
import pytest
from flask import Flask
from flask_cors import CORS

from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container as container_mod
from slopee_web3.adapters.flask_api import register_web3
from slopee_web3.adapters.flask_api.container import Web3Container
from slopee_web3.application.dispute_note_service import DisputeNoteService
from slopee_web3.domain.errors import DomainError
from slopee_web3.settings import Web3Settings
from test_w3_week5_flow_mysql import Stack, assign, db, locked_orders, new_shipper, row, status  # noqa: F401
from w3_support import ESCROW, TOKEN, user

pytestmark = pytest.mark.mysql
ORIGIN = 'http://localhost:5173'


@pytest.fixture
def st():
    s = Stack()
    yield s
    s.queue.close()


def disputed(st, db):
    """Đơn đã đi đủ đường: LOCKED -> giao -> Buyer raiseDispute -> Indexer ghi DISPUTED."""
    buyer, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    shipper = new_shipper(db)
    assign(st, db, o['order_id'], shipper)
    st.shipper.deliver(shipper, o['order_id'])
    st.index()
    st.chain.raise_dispute(int(o['quote']['orderId']))
    st.index()
    assert status(db, o['order_id']) == 'DISPUTED'
    return buyer, o


def note(db, order_id):
    return row(db, "SELECT buyer_user_id, reason, evidence_url FROM dispute_notes WHERE order_id=%s", order_id)


def test_buyer_saves_note_after_disputed_and_resend_is_idempotent(st, db):
    buyer, o = disputed(st, db)
    svc = DisputeNoteService(st.uow)
    r = svc.save_note(buyer, o['order_id'], '  Hàng bị vỡ khi nhận  ', ' https://example.com/anh.jpg ')
    assert r == {'order_id': o['order_id'], 'reason': 'Hàng bị vỡ khi nhận', 'evidence_url': 'https://example.com/anh.jpg', 'created': True}
    assert note(db, o['order_id']) == {'buyer_user_id': buyer, 'reason': 'Hàng bị vỡ khi nhận', 'evidence_url': 'https://example.com/anh.jpg'}
    again = svc.save_note(buyer, o['order_id'], 'Hàng bị vỡ khi nhận', 'https://example.com/anh.jpg')      # lỗi mạng -> UI gửi lại
    assert again['created'] is False and row(db, "SELECT COUNT(*) AS c FROM dispute_notes")['c'] == 1
    svc.save_note(buyer, o['order_id'], 'Hàng bị vỡ và thiếu phụ kiện', None)                                 # bổ sung: ghi đè, bỏ bằng chứng
    assert note(db, o['order_id'])['reason'] == 'Hàng bị vỡ và thiếu phụ kiện' and note(db, o['order_id'])['evidence_url'] is None
    assert row(db, "SELECT COUNT(*) AS c FROM dispute_notes")['c'] == 1


def test_only_the_buyer_of_that_order_can_write_the_note(st, db):
    buyer, o = disputed(st, db)
    svc = DisputeNoteService(st.uow)
    merchant = row(db, "SELECT merchant_user_id AS m FROM order_web3 WHERE order_id=%s", o['order_id'])['m']
    for who in (merchant, user(db, 'user'), user(db, 'admin'), 'khong-co-user'):
        with pytest.raises(DomainError) as e:
            svc.save_note(who, o['order_id'], 'Lý do thử', None)
        assert e.value.code == 'ORDER_NOT_FOUND'                              # không lộ sự tồn tại của đơn người khác
    with pytest.raises(DomainError) as e:
        svc.save_note(buyer, 'khong-co-don', 'Lý do thử', None)
    assert e.value.code == 'ORDER_NOT_FOUND'
    assert note(db, o['order_id']) is None


@pytest.mark.parametrize('stage', ['LOCKED', 'DELIVERED', 'COMPLETED'])
def test_note_is_refused_unless_the_indexer_has_recorded_disputed(st, db, stage):
    """SEQ-02: lý do chỉ gửi SAU khi Indexer ghi DISPUTED. Trước đó (kể cả khi chuỗi đã DISPUTED mà Indexer chưa kịp) ⇒ 409."""
    buyer, group, _ = locked_orders(st, db, 1)
    o = group['orders'][0]
    shipper = new_shipper(db)
    assign(st, db, o['order_id'], shipper)
    if stage != 'LOCKED':
        st.shipper.deliver(shipper, o['order_id'])
        st.index()
    if stage == 'COMPLETED':
        st.chain.early_release(int(o['quote']['orderId']))
        st.index()
    with pytest.raises(DomainError) as e:
        DisputeNoteService(st.uow).save_note(buyer, o['order_id'], 'Lý do thử', None)
    assert e.value.code == 'INVALID_STATE' and e.value.extra['status'] == stage and note(db, o['order_id']) is None
    if stage == 'DELIVERED':                                 # chuỗi đã DISPUTED nhưng Indexer chưa chạy: vẫn chặn
        st.chain.raise_dispute(int(o['quote']['orderId']))
        with pytest.raises(DomainError):
            DisputeNoteService(st.uow).save_note(buyer, o['order_id'], 'Lý do thử', None)
        st.index()
        assert DisputeNoteService(st.uow).save_note(buyer, o['order_id'], 'Lý do thử', None)['created'] is True


def test_invalid_input_is_rejected_before_touching_the_order(st, db):
    buyer, o = disputed(st, db)
    svc = DisputeNoteService(st.uow)
    for reason, url in [('ab', None), (None, None), ('Lý do ổn', 'javascript:alert(1)'), ('Lý do ổn', 'ftp://a.com/x'), ('x' * 2001, None)]:
        with pytest.raises(DomainError) as e:
            svc.save_note(buyer, o['order_id'], reason, url)
        assert e.value.code == 'INVALID_DISPUTE_NOTE'
    with pytest.raises(DomainError) as e:                    # kiểm đầu vào đi TRƯỚC kiểm quyền: không dò được đơn bằng lỗi khác nhau
        svc.save_note('ai-do', 'khong-co-don', 'ab', None)
    assert e.value.code == 'INVALID_DISPUTE_NOTE' and note(db, o['order_id']) is None


def test_note_is_locked_once_admin_has_a_resolution_proposal(st, db):
    buyer, o = disputed(st, db)
    svc = DisputeNoteService(st.uow)
    svc.save_note(buyer, o['order_id'], 'Lý do ban đầu', None)
    admin = user(db, 'admin')
    db.execute("INSERT INTO dispute_resolutions (order_id, payout_to, amount_raw, nonce, deadline, status, created_by_admin) "
               "VALUES (%s, %s, '1', 0, 4000000000, 'PROPOSED', %s)", (o['order_id'], '0x' + '1' * 40, admin))
    try:
        with pytest.raises(DomainError) as e:
            svc.save_note(buyer, o['order_id'], 'Đổi lý do sau khi Admin xét', 'https://example.com/moi')
        assert e.value.code == 'INVALID_STATE'
        assert note(db, o['order_id'])['reason'] == 'Lý do ban đầu'               # bằng chứng Admin đang xét không bị đổi
    finally:
        db.execute("DELETE FROM dispute_resolutions WHERE order_id=%s", (o['order_id'],))


def test_note_foreign_key_follows_the_order(st, db):
    """Xóa đơn thì ghi chú đi theo (không để dòng mồ côi, và không chặn việc dọn dữ liệu của các test khác)."""
    assert row(db, "SELECT DELETE_RULE AS r FROM information_schema.REFERENTIAL_CONSTRAINTS "
                   "WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME='fk_dispute_note_order'")['r'] == 'CASCADE'


# ------------------------------------------------------------------ HTTP đầu cuối (+ CORS như backend/app.py)
@pytest.fixture
def http(st, db):
    settings = Web3Settings(rpc_url='x', chain_id=31337, escrow_address=ESCROW, token_address=TOKEN)
    container_mod.set_container(Web3Container(settings, st.signer, st.chain, st.clock, st.uow))
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": ORIGIN}})              # đúng cấu hình của backend/app.py
    register_web3(app)
    yield app.test_client()
    container_mod.set_container(None)


def H(uid, role='user'):
    return {'Authorization': f'Bearer {issue_token(uid, role)}', 'Origin': ORIGIN}


def test_http_end_to_end_with_cors_preflight(st, db, http):
    buyer, o = disputed(st, db)
    url = f"/api/orders/{o['order_id']}/dispute-note"
    # Trình duyệt gửi preflight trước POST có Authorization: route phải tồn tại, nếu không là 404 không kèm header CORS (lỗi ở mục 10)
    pre = http.options(url, headers={'Origin': ORIGIN, 'Access-Control-Request-Method': 'POST',
                                     'Access-Control-Request-Headers': 'authorization,content-type'})
    assert pre.status_code == 200 and pre.headers['Access-Control-Allow-Origin'] == ORIGIN
    assert 'POST' in pre.headers['Access-Control-Allow-Methods'] and 'authorization' in pre.headers['Access-Control-Allow-Headers'].lower()
    other = http.options(url, headers={'Origin': 'http://evil.example', 'Access-Control-Request-Method': 'POST'})
    assert 'Access-Control-Allow-Origin' not in other.headers                              # origin lạ không được phép

    r = http.post(url, json={'reason': 'Hàng bị vỡ', 'evidence_url': 'https://example.com/a.jpg'}, headers=H(buyer))
    assert r.status_code == 200 and r.get_json()['created'] is True and r.headers['Access-Control-Allow-Origin'] == ORIGIN
    assert note(db, o['order_id'])['reason'] == 'Hàng bị vỡ'
    assert http.post(url, json={'reason': 'Hàng bị vỡ', 'evidence_url': 'https://example.com/a.jpg'}, headers=H(buyer)).get_json()['created'] is False

    bad = http.post(url, json={'reason': 'ab'}, headers=H(buyer))
    assert bad.status_code == 422 and bad.get_json()['code'] == 'INVALID_DISPUTE_NOTE'
    assert http.post(url, json={'reason': 'Lý do thử'}, headers=H(user(db, 'user'))).status_code == 404
    assert http.post(url, json={'reason': 'Lý do thử'}, headers=H(user(db, 'admin'), 'admin')).status_code == 403
    assert http.post(url, json={'reason': 'Lý do thử'}, headers={'Origin': ORIGIN}).status_code == 401
