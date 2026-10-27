"""Tuần 7 [B] UC-07 trên MySQL THẬT + chuỗi giả mô hình đúng contract: Trọng tài xử đơn phương sau `disputeTimeout`.

Luồng: LOCKED -> giao -> Buyer raiseDispute -> Indexer DISPUTED -> (có thể có đề xuất 2/3 dang dở) -> tua giờ qua disputedAt + disputeTimeout
-> Admin `force-resolve` (relayer ký bằng KHÓA TRỌNG TÀI) -> Indexer REFUNDED/COMPLETED, đề xuất CANCELLED, thông báo cả hai bên, nhật ký,
đối soát khớp. Cộng ca HTTP đầu cuối (quyền, CORS, mã lỗi).
"""
import pytest
from flask import Flask
from flask_cors import CORS

from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container as container_mod
from slopee_web3.adapters.flask_api import register_web3
from slopee_web3.adapters.flask_api.container import Web3Container
from slopee_web3.application.dispute_force_service import DisputeForceResolveService
from slopee_web3.application.dispute_service import DisputeService
from slopee_web3.domain.errors import DomainError
from slopee_web3.settings import Web3Settings
from test_w3_dispute_note_mysql import disputed  # noqa: F401
from test_w3_week5_flow_mysql import Stack, db, row, status  # noqa: F401
from w3_support import ADDR, ESCROW, TOKEN, connect, make_signer, sign_dispute_as, user

pytestmark = pytest.mark.mysql
DAY = 86400
ORIGIN = 'http://localhost:5173'


@pytest.fixture
def st():
    s = Stack()
    yield s
    s.queue.close()


@pytest.fixture(autouse=True)
def _clean(mysql_db):
    yield
    conn = connect()
    conn.autocommit(True)
    cur = conn.cursor()
    for t in ('dispute_force_resolutions', 'dispute_signatures', 'dispute_resolutions', 'dispute_notes'):
        cur.execute(f"DELETE FROM {t}")
    conn.close()


class Rig:
    def __init__(self, st, db):
        self.st, self.db = st, db
        self.svc = DisputeForceResolveService(st.uow, st.chain, st.clock, st.relayer)
        self.ds = DisputeService(st.uow, st.chain, st.signer, st.clock)
        self.admin = user(db, 'admin')
        self.buyer, self.o = disputed(st, db)
        self.code = self.o['order_id']
        self.oid = int(self.o['quote']['orderId'])
        r = row(db, "SELECT dispute_timeout, disputed_at, merchant_user_id FROM order_web3 WHERE order_id=%s", self.code)
        self.timeout, self.disputed_at, self.merchant = int(r['dispute_timeout']), int(r['disputed_at']), r['merchant_user_id']

    def go(self, payout='BUYER', note=None):
        return self.svc.force_resolve(self.admin, self.code, payout, note)

    def audit(self):
        self.db.execute("SELECT * FROM dispute_force_resolutions WHERE order_id=%s ORDER BY id", (self.code,))
        return list(self.db.fetchall())

    def outbox(self):
        self.db.execute("SELECT kind, status, tx_hash FROM tx_outbox WHERE order_id=%s AND kind='FORCE_RESOLVE'", (self.code,))
        return list(self.db.fetchall())


@pytest.fixture
def rig(st, db):
    return Rig(st, db)


def code_of(fn, *a, **kw):
    with pytest.raises(DomainError) as e:
        fn(*a, **kw)
    return e.value


@pytest.mark.parametrize('payout,final,legacy', [('BUYER', 'REFUNDED', 'cancelled'), ('MERCHANT', 'COMPLETED', 'received')])
def test_force_resolve_end_to_end_with_the_indexer(rig, payout, final, legacy):
    st, db = rig.st, rig.db
    st.chain.advance(rig.timeout)                                                       # đúng mốc disputedAt + disputeTimeout
    out = rig.go(payout, 'Cả hai bên không phản hồi')
    assert out['outcome'] == 'SENT' and out['payout_side'] == payout
    assert status(db, rig.code) == 'DISPUTED'                                           # relayer KHÔNG ghi trạng thái (BR-09): chờ Indexer
    st.index()
    assert status(db, rig.code) == final
    assert row(db, "SELECT status FROM orders WHERE id=%s", rig.code)['status'] == legacy
    assert row(db, "SELECT anomaly_flag AS a FROM order_web3 WHERE order_id=%s", rig.code)['a'] == 0
    db.execute("SELECT user_id, message FROM notifications WHERE kind='DISPUTE_RESOLVED' AND order_id=%s", (rig.code,))
    notes = db.fetchall()
    assert {n['user_id'] for n in notes} == {rig.buyer, rig.merchant} and all('Trọng tài' in n['message'] for n in notes)
    # nhật ký: ai, bên nào, bao nhiêu, giao dịch nào, và khớp tx_outbox
    a = rig.audit()
    assert len(a) == 1
    assert (a[0]['admin_user_id'], a[0]['payout_side'], a[0]['reason_note'], a[0]['tx_hash']) == (rig.admin, payout, 'Cả hai bên không phản hồi', out['tx_hash'])
    assert a[0]['amount_raw'] == str(st.chain.get_order(rig.oid)['amount']) and a[0]['onchain_order_id'] == rig.oid
    ob = rig.outbox()
    assert [(o['kind'], o['status'], o['tx_hash']) for o in ob] == [('FORCE_RESOLVE', 'CONFIRMED', out['tx_hash'])] and a[0]['outbox_id'] is not None
    rec = st.reconcile.run(deep=True)                                                   # tiền ra khỏi contract đúng bằng đơn đóng
    assert rec['ok'] is True and rec['order_mismatches'] == []
    assert st.chain.last_msg_sender == ADDR['arbitrator']


def test_one_second_early_is_refused_without_gas_then_allowed_at_the_boundary(rig):
    st = rig.st
    sent_before = len(st.chain.sent_txs)
    st.chain.advance(rig.timeout - 1)
    e = code_of(rig.go)
    assert e.code == 'FORCE_RESOLVE_TOO_EARLY' and e.extra['seconds_remaining'] == 1
    assert rig.audit() == [] and rig.outbox() == [] and len(st.chain.sent_txs) == sent_before     # không gửi giao dịch nào
    assert st.chain.get_order_state(rig.oid) == 'DISPUTED'
    st.chain.advance(1)
    assert rig.go()['outcome'] == 'SENT'


def test_force_resolve_closes_a_half_finished_two_of_three_proposal(rig):
    """Admin đã đề xuất, Buyer đã ký nhưng không ai nộp; hết hạn ký rồi quá timeout: Trọng tài là lối thoát, đề xuất bị Indexer hủy."""
    st, db = rig.st, rig.db
    p = rig.ds.propose(rig.admin, rig.code, 'MERCHANT')
    rig.ds.add_signature(rig.buyer, rig.code, p['resolution_id'],
                         sign_dispute_as('buyer', rig.oid, p['payout_to'], int(p['amount_raw']), int(p['nonce']), p['deadline']))
    assert p['deadline'] < rig.disputed_at + rig.timeout                                # R-02: chữ ký hết hạn trước mốc xử đơn phương
    st.chain.advance(rig.timeout)
    assert rig.go('BUYER')['outcome'] == 'SENT'                                         # Admin có thể chọn KHÁC đề xuất cũ
    st.index()
    assert status(db, rig.code) == 'REFUNDED'
    assert row(db, "SELECT status FROM dispute_resolutions WHERE id=%s", p['resolution_id'])['status'] == 'CANCELLED'


def test_repeat_is_idempotent_and_the_opposite_choice_is_rejected(rig):
    rig.st.chain.advance(rig.timeout)
    first = rig.go('BUYER')
    rig.st.index()
    again = rig.go('BUYER')
    assert (first['outcome'], again['outcome']) == ('SENT', 'ALREADY_RESOLVED') and len(rig.audit()) == 1 and len(rig.outbox()) == 1
    assert code_of(rig.go, 'MERCHANT').code == 'INVALID_STATE'


def test_unknown_order_and_invalid_payout_leave_no_trace(rig):
    rig.st.chain.advance(rig.timeout)
    assert code_of(rig.svc.force_resolve, rig.admin, 'no-such', 'BUYER').code == 'ORDER_NOT_FOUND'
    assert code_of(rig.go, 'arbitrator').code == 'INVALID_PAYOUT'
    assert rig.audit() == [] and rig.outbox() == [] and rig.st.chain.get_order_state(rig.oid) == 'DISPUTED'


def test_audit_table_has_no_foreign_key_so_the_trail_outlives_the_order(rig):
    """Cùng quy ước `tx_outbox`: nhật ký hành động tin cậy của sàn tồn tại độc lập với vòng đời đơn/người dùng."""
    rig.db.execute("SELECT COUNT(*) AS c FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() "
                   "AND TABLE_NAME='dispute_force_resolutions' AND CONSTRAINT_TYPE='FOREIGN KEY'")
    assert rig.db.fetchone()['c'] == 0


# ------------------------------------------------------------------------------------------------ HTTP đầu cuối
@pytest.fixture
def http(rig):
    settings = Web3Settings(rpc_url='x', chain_id=31337, escrow_address=ESCROW, token_address=TOKEN)
    container_mod.set_container(Web3Container(settings, rig.st.signer, rig.st.chain, rig.st.clock, rig.st.uow))
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": ORIGIN}})
    register_web3(app)
    yield app.test_client()
    container_mod.set_container(None)


def H(uid, role='admin'):
    return {'Authorization': f'Bearer {issue_token(uid, role)}', 'Origin': ORIGIN}


def test_http_permissions_cors_errors_and_success(rig, http):
    url = f'/api/admin/disputes/{rig.code}/force-resolve'
    pre = http.options(url, headers={'Origin': ORIGIN, 'Access-Control-Request-Method': 'POST',
                                     'Access-Control-Request-Headers': 'authorization,content-type'})
    assert pre.status_code == 200 and pre.headers['Access-Control-Allow-Origin'] == ORIGIN
    assert http.post(url, json={'payout_to': 'BUYER'}).status_code == 401
    for uid, role in ((rig.buyer, 'user'), (rig.merchant, 'seller')):
        assert http.post(url, json={'payout_to': 'BUYER'}, headers=H(uid, role)).status_code == 403   # ngay cả bên của đơn cũng không tự xử đơn phương

    early = http.post(url, json={'payout_to': 'BUYER'}, headers=H(rig.admin))
    assert early.status_code == 409 and early.get_json()['code'] == 'FORCE_RESOLVE_TOO_EARLY'
    assert early.get_json()['seconds_remaining'] == rig.timeout and 'force_resolve_at' in early.get_json()
    rig.st.chain.advance(rig.timeout)
    assert http.post(url, json={'payout_to': 'nobody'}, headers=H(rig.admin)).get_json()['code'] == 'INVALID_PAYOUT'
    assert http.post(f'/api/admin/disputes/zzz/force-resolve', json={'payout_to': 'BUYER'}, headers=H(rig.admin)).status_code == 404

    ok = http.post(url, json={'payout_to': 'MERCHANT', 'reason_note': 'Hết hạn tranh chấp'}, headers=H(rig.admin))
    assert ok.status_code == 200 and ok.get_json()['outcome'] == 'SENT' and ok.get_json()['payout_side'] == 'MERCHANT'
    assert 'signature' not in str(ok.get_json()).lower()
    rig.st.index()
    assert status(rig.db, rig.code) == 'COMPLETED'
    assert rig.audit()[0]['admin_user_id'] == rig.admin
