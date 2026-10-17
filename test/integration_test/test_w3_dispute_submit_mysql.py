"""Tuần 6 (A) UC-06 trên MySQL THẬT + chuỗi giả mô hình đúng contract: nộp `resolveDispute` qua relayer, danh sách Admin, HTTP.

Đơn đi đủ đường LOCKED -> giao -> Buyer raiseDispute -> Indexer DISPUTED. Đề xuất + chữ ký được seed thẳng bằng SQL (DisputeService
của B chưa có): chữ ký Trọng tài do EnvKeySigner.sign_dispute, chữ ký Buyer/Merchant do eth_account như MetaMask.
"""
import pytest
from flask import Flask
from flask_cors import CORS

from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container as container_mod
from slopee_web3.adapters.flask_api import register_web3
from slopee_web3.adapters.flask_api.container import Web3Container
from slopee_web3.application.dispute_admin_service import DisputeAdminService
from slopee_web3.application.dispute_submit_service import DisputeSubmitService
from slopee_web3.domain.dispute import DisputeResolution
from slopee_web3.domain.errors import DomainError
from slopee_web3.settings import Web3Settings
from test_w3_dispute_note_mysql import disputed, note  # noqa: F401
from test_w3_week5_flow_mysql import Stack, db, row, status  # noqa: F401
from w3_support import ADDR, ESCROW, TOKEN, sign_dispute_as, user

pytestmark = pytest.mark.mysql
ORIGIN = 'http://localhost:5173'
DAY = 86400


@pytest.fixture
def st():
    s = Stack()
    yield s
    s.queue.close()


@pytest.fixture(autouse=True)
def _drop_dispute_rows_after_each_test(mysql_db):
    """Fixture `db` dùng chung (B) xóa order_web3 ở đầu mỗi test; dòng dispute_* có khóa ngoại tới đó nên phải dọn SAU mỗi test."""
    yield
    from w3_support import connect
    conn = connect()
    conn.autocommit(True)
    cur = conn.cursor()
    for t in ('dispute_signatures', 'dispute_resolutions', 'dispute_notes'):
        cur.execute(f"DELETE FROM {t}")
    conn.close()


def clean_disputes(db):
    db.execute("DELETE FROM dispute_signatures")
    db.execute("DELETE FROM dispute_resolutions")
    db.execute("DELETE FROM dispute_notes")


def propose(st, db, o, payout='buyer', sign=('arbitrator', 'buyer'), deadline=None, status_='PROPOSED'):
    """Admin 'tạo đề xuất': ghi dispute_resolutions + chữ ký. Trả (resolution_id, params)."""
    oid = int(o['quote']['orderId'])
    co = st.chain.get_order(oid)
    payout_to = co['buyer'] if payout == 'buyer' else co['merchant']
    deadline = deadline if deadline is not None else st.chain.now + 7 * DAY
    nonce = st.chain.dispute_nonce(oid)
    admin = user(db, 'admin')
    db.execute("INSERT INTO dispute_resolutions (order_id, payout_to, amount_raw, nonce, deadline, status, created_by_admin, reason_note) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (o['order_id'], payout_to, str(co['amount']), nonce, deadline, status_, admin, 'Hàng lỗi'))
    rid = db.lastrowid
    for key in sign:
        party = {'arbitrator': 'ARBITRATOR', 'buyer': 'BUYER', 'merchant1': 'MERCHANT'}[key]
        if key == 'arbitrator':
            sig = st.signer.sign_dispute(DisputeResolution(oid, payout_to, co['amount'], nonce, deadline))
        else:
            sig = sign_dispute_as(key, oid, payout_to, co['amount'], nonce, deadline)
        db.execute("INSERT INTO dispute_signatures (resolution_id, party, signer_address, signature) VALUES (%s,%s,%s,%s)",
                   (rid, party, ADDR[key], sig))
    return rid, dict(oid=oid, payout_to=payout_to, deadline=deadline, nonce=nonce)


def submit_svc(st):
    return DisputeSubmitService(st.uow, st.chain, st.signer, st.clock, st.relayer)


def res_row(db, rid):
    return row(db, "SELECT status, submitted_tx_hash FROM dispute_resolutions WHERE id=%s", rid)


def parties(db, order_id):
    r = row(db, "SELECT buyer_user_id AS b, merchant_user_id AS m FROM order_web3 WHERE order_id=%s", order_id)
    return r['b'], r['m']


def test_refund_buyer_end_to_end_then_indexer_catches_up(st, db):
    clean_disputes(db)
    buyer, o = disputed(st, db)
    rid, p = propose(st, db, o, 'buyer', ('arbitrator', 'buyer'))
    out = submit_svc(st).submit(buyer, 'user', o['order_id'])
    assert out['outcome'] == 'SENT' and out['payout_side'] == 'BUYER' and out['resolution_status'] == 'SUBMITTED'
    assert st.chain.get_order_state(p['oid']) == 'REFUNDED' and st.chain.dispute_nonce(p['oid']) == 1
    r = res_row(db, rid)
    assert r['status'] == 'SUBMITTED' and r['submitted_tx_hash'] == out['tx_hash']
    ob = row(db, "SELECT kind, status, tx_hash FROM tx_outbox WHERE order_id=%s AND kind='RESOLVE'", o['order_id'])
    assert (ob['status'], ob['tx_hash']) == ('CONFIRMED', out['tx_hash'])
    assert status(db, o['order_id']) == 'DISPUTED'                  # relayer KHÔNG tự đổi trạng thái (BR-09)
    st.index()
    assert status(db, o['order_id']) == 'REFUNDED'                  # Indexer mới là người ghi
    again = submit_svc(st).submit(buyer, 'user', o['order_id'])     # bấm lại: idempotent
    assert again['outcome'] == 'ALREADY_RESOLVED' and len(st.chain.sent_txs) == 2      # 1 confirmDelivery + 1 resolveDispute


def test_release_merchant_with_merchant_signature_submitted_by_merchant(st, db):
    clean_disputes(db)
    buyer, o = disputed(st, db)
    _, merchant = parties(db, o['order_id'])
    rid, p = propose(st, db, o, 'merchant', ('arbitrator', 'merchant1'))
    out = submit_svc(st).submit(merchant, 'seller', o['order_id'])
    assert out['payout_side'] == 'MERCHANT' and st.chain.get_order_state(p['oid']) == 'COMPLETED'
    st.index()
    assert status(db, o['order_id']) == 'COMPLETED'
    assert res_row(db, rid)['status'] == 'SUBMITTED'


def test_not_ready_changes_nothing_in_the_database(st, db):
    clean_disputes(db)
    buyer, o = disputed(st, db)
    rid, _ = propose(st, db, o, 'buyer', ('arbitrator',))
    with pytest.raises(DomainError) as e:
        submit_svc(st).submit(buyer, 'user', o['order_id'])
    assert e.value.code == 'DISPUTE_NOT_READY' and e.value.extra == {'signed_by': ['ARBITRATOR']}
    assert res_row(db, rid)['status'] == 'PROPOSED'
    assert row(db, "SELECT COUNT(*) AS c FROM tx_outbox WHERE kind='RESOLVE'")['c'] == 0


def test_forged_party_label_is_ignored(st, db):
    """Dòng được gắn nhãn BUYER nhưng chữ ký là của người lạ: không được tính, dù đã nằm trong dispute_signatures."""
    clean_disputes(db)
    buyer, o = disputed(st, db)
    rid, p = propose(st, db, o, 'buyer', ('arbitrator',))
    forged = sign_dispute_as('stranger', p['oid'], p['payout_to'], st.chain.get_order(p['oid'])['amount'], p['nonce'], p['deadline'])
    db.execute("INSERT INTO dispute_signatures (resolution_id, party, signer_address, signature) VALUES (%s,'BUYER',%s,%s)",
               (rid, ADDR['buyer'], forged))
    with pytest.raises(DomainError) as e:
        submit_svc(st).submit(buyer, 'user', o['order_id'])
    assert e.value.code == 'DISPUTE_NOT_READY' and st.chain.get_order_state(p['oid']) == 'DISPUTED'


def test_expired_signature_marks_row_expired(st, db):
    clean_disputes(db)
    buyer, o = disputed(st, db)
    rid, _ = propose(st, db, o, 'buyer', ('arbitrator', 'buyer'), deadline=st.chain.now + 60)
    st.chain.advance(61)
    with pytest.raises(DomainError) as e:
        submit_svc(st).submit(buyer, 'user', o['order_id'])
    assert e.value.code == 'DISPUTE_EXPIRED' and res_row(db, rid)['status'] == 'EXPIRED'
    with pytest.raises(DomainError) as e2:                          # lần sau: đề xuất đã chết
        submit_svc(st).submit(buyer, 'user', o['order_id'])
    assert e2.value.code == 'DISPUTE_EXPIRED'


def test_only_the_newest_proposal_counts(st, db):
    """Admin tạo đề xuất mới sau khi đề xuất cũ hết hạn: dùng bản mới nhất, không bao giờ bản cũ."""
    clean_disputes(db)
    buyer, o = disputed(st, db)
    old, _ = propose(st, db, o, 'buyer', ('arbitrator', 'buyer'), status_='EXPIRED')
    new, p = propose(st, db, o, 'merchant', ('arbitrator', 'merchant1'))
    out = submit_svc(st).submit(buyer, 'user', o['order_id'])
    assert out['resolution_id'] == new and out['payout_side'] == 'MERCHANT'
    assert res_row(db, old)['status'] == 'EXPIRED' and res_row(db, new)['status'] == 'SUBMITTED'


def test_transition_is_state_conditional(st, db):
    clean_disputes(db)
    buyer, o = disputed(st, db)
    rid, _ = propose(st, db, o, status_='EXECUTED')                  # Indexer đã đặt EXECUTED
    with st.uow() as uow:
        assert uow.disputes.transition_resolution(rid, ('PROPOSED', 'READY'), 'SUBMITTED', '0x' + 'ab' * 32) is False
        uow.commit()
    assert res_row(db, rid) == {'status': 'EXECUTED', 'submitted_tx_hash': None}      # không bị ghi đè lùi trạng thái


# ------------------------------------------------------------------ danh sách Admin
def test_admin_list_shows_note_resolution_and_signers_then_drops_resolved(st, db):
    clean_disputes(db)
    buyer, o = disputed(st, db)
    svc = DisputeAdminService(st.uow, st.clock)
    first = svc.list_open()['disputes']
    assert [d['order_id'] for d in first] == [o['order_id']] and first[0]['resolution'] is None and first[0]['note'] is None
    db.execute("INSERT INTO dispute_notes (order_id, buyer_user_id, reason, evidence_url) VALUES (%s,%s,%s,%s)",
               (o['order_id'], buyer, 'Hàng bị vỡ', 'https://example.com/a.jpg'))
    rid, p = propose(st, db, o, 'buyer', ('arbitrator',))
    d = svc.list_open()['disputes'][0]
    co = st.chain.get_order(p['oid'])
    assert d['note'] == {'reason': 'Hàng bị vỡ', 'evidence_url': 'https://example.com/a.jpg'}
    assert d['resolution']['signed_by'] == ['ARBITRATOR'] and d['resolution']['payout_side'] == 'BUYER'
    assert d['resolution']['status'] == 'PROPOSED' and d['resolution']['expired'] is False
    assert d['amount_raw'] == str(co['amount']) and d['force_resolve_at'] == co['disputed_at'] + co['dispute_timeout']
    assert d['onchain_order_id'] == str(p['oid']) and d['shop_name'] and 'buyer_wallet' not in d
    st.chain.advance(8 * DAY)
    assert svc.list_open()['disputes'][0]['resolution']['expired'] is True      # hạn chữ ký đã qua, UI báo "cần đề xuất mới"


def test_admin_list_excludes_resolved_orders(st, db):
    clean_disputes(db)
    buyer, o = disputed(st, db)
    propose(st, db, o, 'buyer', ('arbitrator', 'buyer'))
    submit_svc(st).submit(buyer, 'user', o['order_id'])
    st.index()
    assert DisputeAdminService(st.uow, st.clock).list_open()['disputes'] == []


# ------------------------------------------------------------------ HTTP đầu cuối
@pytest.fixture
def http(st, db):
    settings = Web3Settings(rpc_url='x', chain_id=31337, escrow_address=ESCROW, token_address=TOKEN)
    container_mod.set_container(Web3Container(settings, st.signer, st.chain, st.clock, st.uow))
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": ORIGIN}})
    register_web3(app)
    yield app.test_client()
    container_mod.set_container(None)


def H(uid, role='user'):
    return {'Authorization': f'Bearer {issue_token(uid, role)}', 'Origin': ORIGIN}


def test_http_submit_roles_cors_and_errors(st, db, http):
    clean_disputes(db)
    buyer, o = disputed(st, db)
    _, merchant = parties(db, o['order_id'])
    url = f"/api/disputes/{o['order_id']}/submit"
    pre = http.options(url, headers={'Origin': ORIGIN, 'Access-Control-Request-Method': 'POST',
                                     'Access-Control-Request-Headers': 'authorization,content-type'})
    assert pre.status_code == 200 and pre.headers.get('Access-Control-Allow-Origin') == ORIGIN      # bài học mục 10: preflight không 404
    assert http.post(url).status_code == 401
    assert http.post(url, headers=H(user(db, 'shipper'), 'shipper')).status_code == 403
    r = http.post(url, headers=H(buyer))
    assert r.status_code == 404 and r.get_json()['code'] == 'DISPUTE_NOT_FOUND'                       # chưa có đề xuất
    stranger = http.post(url, headers=H(user(db, 'user')))
    assert stranger.status_code == 404 and stranger.get_json()['code'] == 'ORDER_NOT_FOUND'
    rid, _ = propose(st, db, o, 'buyer', ('arbitrator',))
    nr = http.post(url, headers=H(buyer))
    assert nr.status_code == 409 and nr.get_json()['code'] == 'DISPUTE_NOT_READY' and nr.get_json()['signed_by'] == ['ARBITRATOR']
    rid2, _ = propose(st, db, o, 'buyer', ('arbitrator', 'buyer'))
    ok = http.post(url, headers=H(merchant, 'seller'), json={'ignored': 'x'})
    assert ok.status_code == 200 and ok.get_json()['outcome'] == 'SENT' and ok.get_json()['resolution_id'] == rid2
    assert http.post(url, headers=H(buyer)).get_json()['outcome'] == 'ALREADY_RESOLVED'


def test_http_admin_disputes_list_is_admin_only(st, db, http):
    clean_disputes(db)
    buyer, o = disputed(st, db)
    assert http.get('/api/admin/disputes', headers=H(buyer)).status_code == 403
    assert http.get('/api/admin/disputes').status_code == 401
    r = http.get('/api/admin/disputes', headers=H(user(db, 'admin'), 'admin'))
    body = r.get_json()
    assert r.status_code == 200 and [d['order_id'] for d in body['disputes']] == [o['order_id']] and body['server_time'] == st.clock.now_chain()
