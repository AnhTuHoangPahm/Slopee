"""Tuần 6 [B] trên MySQL THẬT + chuỗi giả mô hình đúng contract: Admin đề xuất (Trọng tài ký), Buyer/Merchant ký, A nộp, Indexer EXECUTED.

Luồng đầy đủ: LOCKED -> giao -> Buyer raiseDispute -> Indexer DISPUTED -> [B] propose -> [B] ký -> [A] submit -> [B] Indexer EXECUTED.
Chữ ký Buyer/Merchant do eth_account như MetaMask (`sign_dispute_as`), chữ ký Trọng tài do EnvKeySigner.sign_dispute.
"""
import json
import re

import pytest
from flask import Flask
from flask_cors import CORS

from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container as container_mod
from slopee_web3.adapters.flask_api import register_web3
from slopee_web3.adapters.flask_api.container import Web3Container
from slopee_web3.adapters.indexer import Indexer
from slopee_web3.application.dispute_service import DisputeService
from slopee_web3.application.dispute_submit_service import DisputeSubmitService
from slopee_web3.application.jobs import DisputeSigExpiry
from slopee_web3.domain.dispute import DisputeResolution
from slopee_web3.domain.errors import DomainError
from slopee_web3.ports.chain_port import ChainTxFailed
from slopee_web3.settings import Web3Settings
from test_w3_dispute_note_mysql import disputed  # noqa: F401
from test_w3_week5_flow_mysql import Stack, db, extra_group, row, status  # noqa: F401
from w3_support import ADDR, ESCROW, TOKEN, connect, event, sign_dispute_as, user

pytestmark = pytest.mark.mysql
DAY = 86400
ORIGIN = 'http://localhost:5173'
RAW_SIG = re.compile(r'0x[0-9a-fA-F]{130}')


@pytest.fixture
def st():
    s = Stack()
    yield s
    s.queue.close()


@pytest.fixture(autouse=True)
def _clean_dispute_rows(mysql_db):
    """Fixture `db` dùng chung xóa order_web3 ở đầu mỗi test; dòng dispute_* có khóa ngoại tới đó nên dọn SAU mỗi test."""
    yield
    conn = connect()
    conn.autocommit(True)
    cur = conn.cursor()
    for t in ('dispute_signatures', 'dispute_resolutions', 'dispute_notes'):
        cur.execute(f"DELETE FROM {t}")
    cur.execute("UPDATE platform_settings SET setting_value='604800' WHERE setting_key='DISPUTE_SIG_TTL_SECONDS'")
    conn.close()


class Rig:
    def __init__(self, st, db):
        self.st, self.db = st, db
        self.ds = DisputeService(st.uow, st.chain, st.signer, st.clock)
        self.sub = DisputeSubmitService(st.uow, st.chain, st.signer, st.clock, st.relayer)
        self.expiry = DisputeSigExpiry(st.uow, st.clock)
        self.admin = user(db, 'admin')
        self.buyer, self.o = disputed(st, db)
        self.code = self.o['order_id']
        self.oid = int(self.o['quote']['orderId'])
        r = row(db, "SELECT merchant_user_id, dispute_timeout, disputed_at FROM order_web3 WHERE order_id=%s", self.code)
        self.merchant, self.timeout, self.disputed_at = r['merchant_user_id'], int(r['dispute_timeout']), int(r['disputed_at'])

    def propose(self, payout='BUYER', note=None):
        return self.ds.propose(self.admin, self.code, payout, note)

    def sign(self, key, p):
        return sign_dispute_as(key, self.oid, p['payout_to'], int(p['amount_raw']), int(p['nonce']), p['deadline'])

    def res(self, rid):
        return row(self.db, "SELECT status, submitted_tx_hash FROM dispute_resolutions WHERE id=%s", rid)

    def sigs(self, rid):
        self.db.execute("SELECT party, signer_address FROM dispute_signatures WHERE resolution_id=%s ORDER BY id", (rid,))
        return [(r['party'], r['signer_address']) for r in self.db.fetchall()]

    def count(self, table='dispute_resolutions'):
        return row(self.db, f"SELECT COUNT(*) AS c FROM {table}")['c']


@pytest.fixture
def rig(st, db):
    return Rig(st, db)


def code_of(fn, *a, **kw):
    with pytest.raises(DomainError) as e:
        fn(*a, **kw)
    return e.value


# ------------------------------------------------------------------------------------------------ propose
def test_propose_signs_with_the_arbitrator_key_using_only_values_read_from_the_chain(rig):
    on = rig.st.chain.get_order(rig.oid)
    p = rig.propose('BUYER', note='  Đủ bằng chứng hàng lỗi  ')
    assert p['status'] == 'PROPOSED' and p['payout_side'] == 'BUYER' and p['payout_to'] == on['buyer']
    assert p['amount_raw'] == str(on['amount']) and p['nonce'] == '0'
    assert p['deadline'] == min(rig.st.chain.now + 7 * DAY, rig.disputed_at + rig.timeout - 1) < rig.disputed_at + rig.timeout
    assert rig.sigs(p['resolution_id']) == [('ARBITRATOR', ADDR['arbitrator'].lower())]
    stored = row(rig.db, "SELECT signature FROM dispute_signatures WHERE resolution_id=%s", p['resolution_id'])['signature']
    res = DisputeResolution(rig.oid, p['payout_to'], on['amount'], 0, p['deadline'])
    assert rig.st.signer.recover_dispute_signer(res, stored).lower() == ADDR['arbitrator'].lower()       # chữ ký lưu thật sự là của Trọng tài
    r = row(rig.db, "SELECT status, reason_note, created_by_admin FROM dispute_resolutions WHERE id=%s", p['resolution_id'])
    assert r == {'status': 'PROPOSED', 'reason_note': 'Đủ bằng chứng hàng lỗi', 'created_by_admin': rig.admin}


def test_propose_notifies_both_parties_once_per_proposal(rig):
    p = rig.propose()
    rig.db.execute("SELECT user_id, kind, message FROM notifications WHERE kind LIKE 'DISPUTE_PROPOSED:%'")
    rows = rig.db.fetchall()
    assert {r['user_id'] for r in rows} == {rig.buyer, rig.merchant} and {r['kind'] for r in rows} == {f"DISPUTE_PROPOSED:{p['resolution_id']}"}
    assert all('hoàn tiền cho người mua' in r['message'] and '(giờ Việt Nam)' in r['message'] for r in rows)
    p2 = rig.propose('MERCHANT')                                         # đề xuất mới: thông báo mới (kind mang id nên không bị UNIQUE nuốt)
    rig.db.execute("SELECT COUNT(*) AS c FROM notifications WHERE kind=%s", (f"DISPUTE_PROPOSED:{p2['resolution_id']}",))
    assert rig.db.fetchone()['c'] == 2


@pytest.mark.parametrize('value,side', [('BUYER', 'BUYER'), ('buyer', 'BUYER'), ('MERCHANT', 'MERCHANT'), ('merchant', 'MERCHANT')])
def test_payout_side_selects_the_party_wallet_on_chain(rig, value, side):
    on = rig.st.chain.get_order(rig.oid)
    p = rig.propose(value)
    assert p['payout_side'] == side and p['payout_to'] == (on['buyer'] if side == 'BUYER' else on['merchant'])
    assert row(rig.db, "SELECT LOWER(payout_to) AS t FROM dispute_resolutions WHERE id=%s", p['resolution_id'])['t'] == p['payout_to'].lower()


def test_payout_to_an_address_is_accepted_only_for_the_two_parties(rig):
    on = rig.st.chain.get_order(rig.oid)
    assert rig.propose(on['merchant'].lower())['payout_side'] == 'MERCHANT'
    for bad in (None, '', 'admin', ADDR['arbitrator'], '0x' + '0' * 40, ADDR['merchant2'], 5):
        assert code_of(rig.propose, bad).code == 'INVALID_PAYOUT'
    assert rig.count() == 1


def test_propose_refuses_wrong_states(st, db, rig):
    ds, admin = rig.ds, rig.admin
    assert code_of(ds.propose, admin, 'khong-co-don', 'BUYER').code == 'ORDER_NOT_FOUND'
    db.execute("UPDATE order_web3 SET status='COMPLETED' WHERE order_id=%s", (rig.code,))
    e = code_of(ds.propose, admin, rig.code, 'BUYER')
    assert e.code == 'INVALID_STATE' and e.extra['status'] == 'COMPLETED'
    db.execute("UPDATE order_web3 SET status='DISPUTED' WHERE order_id=%s", (rig.code,))
    st.chain.orders[rig.oid]['state'] = 'COMPLETED'                      # DB còn DISPUTED nhưng chuỗi đã xử xong (Indexer chưa kịp)
    e = code_of(ds.propose, admin, rig.code, 'BUYER')
    assert e.code == 'INVALID_STATE' and e.extra['chain_state'] == 'COMPLETED' and rig.count() == 0


def test_propose_is_refused_when_the_signature_window_is_closed(rig):
    rig.st.chain.advance(rig.timeout - 1)                                # còn đúng 1 giây trước mốc: deadline = mốc − 1 = hiện tại + 0
    e = code_of(rig.propose)
    assert e.code == 'DISPUTE_WINDOW_CLOSED' and e.extra['force_resolve_at'] == rig.disputed_at + rig.timeout and rig.count() == 0


def test_ttl_from_platform_settings_and_invalid_values(rig, db):
    db.execute("UPDATE platform_settings SET setting_value='3600' WHERE setting_key='DISPUTE_SIG_TTL_SECONDS'")
    assert rig.propose()['deadline'] == rig.st.chain.now + 3600
    for bad in ('abc', '0', '-5'):
        db.execute("UPDATE platform_settings SET setting_value=%s WHERE setting_key='DISPUTE_SIG_TTL_SECONDS'", (bad,))
        assert code_of(rig.propose).code == 'SETTING_INVALID'
    db.execute("DELETE FROM platform_settings WHERE setting_key='DISPUTE_SIG_TTL_SECONDS'")
    try:
        assert rig.propose()['deadline'] == min(rig.st.chain.now + 604800, rig.disputed_at + rig.timeout - 1)   # thiếu khóa: dùng mặc định 7 ngày
    finally:
        db.execute("INSERT INTO platform_settings (setting_key, setting_value) VALUES ('DISPUTE_SIG_TTL_SECONDS', '604800')")


def test_new_proposal_cancels_the_previous_one_and_old_one_stops_accepting_signatures(rig):
    first = rig.propose('BUYER')
    second = rig.propose('MERCHANT')
    assert rig.res(first['resolution_id'])['status'] == 'CANCELLED' and rig.res(second['resolution_id'])['status'] == 'PROPOSED'
    assert row(rig.db, "SELECT COUNT(*) AS c FROM dispute_resolutions WHERE status IN ('PROPOSED','READY','SUBMITTED')")['c'] == 1
    e = code_of(rig.ds.add_signature, rig.buyer, rig.code, first['resolution_id'], rig.sign('buyer', first))
    assert e.code == 'INVALID_STATE' and e.extra['status'] == 'CANCELLED'


def test_a_submitted_proposal_blocks_a_new_one_until_its_deadline_passes(rig):
    p = rig.propose()
    rig.ds.add_signature(rig.buyer, rig.code, p['resolution_id'], rig.sign('buyer', p))
    with rig.st.uow() as uow:                                            # relayer của A đã gửi giao dịch
        assert uow.disputes.transition_resolution(p['resolution_id'], ('READY',), 'SUBMITTED', tx_hash='0x' + 'ab' * 32)
        uow.commit()
    assert code_of(rig.propose, 'MERCHANT').extra == {'status': 'SUBMITTED'}
    rig.st.chain.advance(p['deadline'] - rig.st.chain.now + 1)           # giao dịch không bao giờ vào chuỗi và hạn đã qua
    q = rig.propose('MERCHANT')
    assert rig.res(p['resolution_id'])['status'] == 'EXPIRED' and rig.res(q['resolution_id'])['status'] == 'PROPOSED'


# ------------------------------------------------------------------------------------------------ add_signature
def test_buyer_signature_makes_the_proposal_ready_and_resending_is_idempotent(rig):
    p = rig.propose('BUYER')
    sig = rig.sign('buyer', p)
    r = rig.ds.add_signature(rig.buyer, rig.code, p['resolution_id'], sig)
    assert r == {'resolution_id': p['resolution_id'], 'status': 'READY', 'party': 'BUYER', 'signed_parties': ['ARBITRATOR', 'BUYER']}
    assert rig.sigs(p['resolution_id']) == [('ARBITRATOR', ADDR['arbitrator'].lower()), ('BUYER', ADDR['buyer'].lower())]
    again = rig.ds.add_signature(rig.buyer, rig.code, p['resolution_id'], sig.upper().replace('0X', '0x'))   # mất phản hồi, gửi lại
    assert again['status'] == 'READY' and rig.count('dispute_signatures') == 2
    m = rig.ds.add_signature(rig.merchant, rig.code, p['resolution_id'], rig.sign('merchant1', p))
    assert m['status'] == 'READY' and m['signed_parties'] == ['ARBITRATOR', 'BUYER', 'MERCHANT']


def test_a_different_signature_from_a_party_that_already_signed_is_refused(rig):
    p = rig.propose()
    rig.db.execute("INSERT INTO dispute_signatures (resolution_id, party, signer_address, signature) VALUES (%s, 'BUYER', %s, %s)",
                   (p['resolution_id'], ADDR['buyer'].lower(), '0x' + '11' * 65))
    e = code_of(rig.ds.add_signature, rig.buyer, rig.code, p['resolution_id'], rig.sign('buyer', p))
    assert e.code == 'ALREADY_SIGNED' and rig.count('dispute_signatures') == 2        # giữ chữ ký đầu


@pytest.mark.parametrize('who,key', [('buyer', 'merchant1'), ('merchant', 'buyer'), ('buyer', 'arbitrator'), ('merchant', 'merchant2'),
                                     ('buyer', 'quote_signer')])
def test_signature_must_come_from_that_partys_wallet_on_the_order(rig, who, key):
    p = rig.propose()
    user_id = rig.buyer if who == 'buyer' else rig.merchant
    e = code_of(rig.ds.add_signature, user_id, rig.code, p['resolution_id'], rig.sign(key, p))
    assert e.code == 'BAD_SIGNATURE' and rig.res(p['resolution_id'])['status'] == 'PROPOSED' and rig.count('dispute_signatures') == 1


@pytest.mark.parametrize('field,delta', [('amount_raw', 1), ('nonce', 1), ('deadline', 1)])
def test_signing_a_different_content_is_refused(rig, field, delta):
    """Chữ ký ràng buộc cả 5 trường: ký nội dung khác thì khôi phục ra địa chỉ khác nên không khớp ví của bên đó."""
    p = rig.propose()
    q = dict(p)
    q[field] = str(int(p[field]) + delta) if field != 'deadline' else p[field] + delta
    assert code_of(rig.ds.add_signature, rig.buyer, rig.code, p['resolution_id'], rig.sign('buyer', q)).code == 'BAD_SIGNATURE'


def test_signing_the_opposite_payout_is_refused(rig):
    p = rig.propose('BUYER')
    other = dict(p, payout_to=rig.st.chain.get_order(rig.oid)['merchant'])      # Buyer bị lừa ký phán quyết giải ngân cho người bán
    assert code_of(rig.ds.add_signature, rig.buyer, rig.code, p['resolution_id'], rig.sign('buyer', other)).code == 'BAD_SIGNATURE'


@pytest.mark.parametrize('bad', [None, '', '0x', 'khong-phai-hex', 123, '0x' + '00' * 65, '0x' + 'zz' * 65, '0x' + 'ab' * 64, '0x' + 'ab' * 66])
def test_malformed_signatures_are_refused_before_any_lookup(rig, bad):
    p = rig.propose()
    assert code_of(rig.ds.add_signature, rig.buyer, rig.code, p['resolution_id'], bad).code == 'BAD_SIGNATURE'
    if not (isinstance(bad, str) and re.fullmatch(r'0x[0-9a-fA-F]{130}', bad)):    # sai ĐỊNH DẠNG: chặn trước mọi truy vấn/kiểm quyền
        assert code_of(rig.ds.add_signature, 'ai-do', 'khong-co-don', 1, bad).code == 'BAD_SIGNATURE'
    else:                                                                            # đúng định dạng nhưng không khôi phục được: vẫn kiểm quyền trước
        assert code_of(rig.ds.add_signature, 'ai-do', 'khong-co-don', 1, bad).code == 'ORDER_NOT_FOUND'


def test_only_the_parties_of_the_order_may_sign_and_others_see_not_found(rig, db):
    p = rig.propose()
    sig = rig.sign('buyer', p)
    for who in (rig.admin, user(db, 'user'), user(db, 'seller'), 'khong-co-user'):
        assert code_of(rig.ds.add_signature, who, rig.code, p['resolution_id'], sig).code == 'ORDER_NOT_FOUND'
    assert code_of(rig.ds.add_signature, rig.buyer, 'khong-co-don', p['resolution_id'], sig).code == 'ORDER_NOT_FOUND'
    assert rig.count('dispute_signatures') == 1


def test_resolution_must_exist_and_belong_to_that_order(rig, db):
    p = rig.propose()
    sig = rig.sign('buyer', p)
    assert code_of(rig.ds.add_signature, rig.buyer, rig.code, 999999, sig).code == 'DISPUTE_NOT_FOUND'
    other = extra_group(rig.st, db, rig.buyer)['orders'][0]['order_id']                 # đơn khác của cùng Buyer
    db.execute("INSERT INTO dispute_resolutions (order_id, payout_to, amount_raw, nonce, deadline, status, created_by_admin) "
               "VALUES (%s, %s, '1', 0, 4000000000, 'PROPOSED', %s)", (other, ADDR['buyer'], rig.admin))
    stray = row(db, "SELECT id FROM dispute_resolutions WHERE order_id=%s", other)['id']
    assert code_of(rig.ds.add_signature, rig.buyer, rig.code, stray, sig).code == 'DISPUTE_NOT_FOUND'


def test_signing_after_the_deadline_is_refused_and_expiry_job_expires_it(rig):
    p = rig.propose()
    rig.st.chain.advance(p['deadline'] - rig.st.chain.now)               # đúng deadline: contract còn nhận (block.timestamp <= deadline)
    assert rig.ds.add_signature(rig.buyer, rig.code, p['resolution_id'], rig.sign('buyer', p))['status'] == 'READY'
    q = rig.propose('MERCHANT')
    rig.st.chain.advance(q['deadline'] - rig.st.chain.now + 1)           # quá deadline 1 giây
    e = code_of(rig.ds.add_signature, rig.merchant, rig.code, q['resolution_id'], rig.sign('merchant1', q))
    assert e.code == 'SIGNATURE_EXPIRED' and e.extra['deadline'] == q['deadline']
    assert rig.expiry.run_once() == {'expired': 1} and rig.res(q['resolution_id'])['status'] == 'EXPIRED'
    assert rig.expiry.run_once() == {'expired': 0}                       # idempotent
    assert rig.propose('BUYER')['status'] == 'PROPOSED'                  # Admin có thể đề xuất lại


def test_expiry_job_only_touches_proposed_and_ready(rig):
    p = rig.propose()
    rig.ds.add_signature(rig.buyer, rig.code, p['resolution_id'], rig.sign('buyer', p))      # READY
    rig.db.execute("INSERT INTO dispute_resolutions (order_id, payout_to, amount_raw, nonce, deadline, status, created_by_admin) VALUES "
                   "(%s, %s, '1', 1, 1, 'SUBMITTED', %s), (%s, %s, '1', 2, 1, 'EXECUTED', %s), (%s, %s, '1', 3, 1, 'CANCELLED', %s)",
                   (rig.code, ADDR['buyer'], rig.admin) * 3)
    rig.st.chain.advance(p['deadline'] - rig.st.chain.now + 1)
    assert rig.expiry.run_once() == {'expired': 1}
    rig.db.execute("SELECT status FROM dispute_resolutions ORDER BY id")
    assert [r['status'] for r in rig.db.fetchall()] == ['EXPIRED', 'SUBMITTED', 'EXECUTED', 'CANCELLED']


# ------------------------------------------------------------------------------------------------ get (hợp đồng của C)
GET_KEYS = {'order_id', 'onchain_order_id', 'order_status', 'your_party', 'buyer_wallet', 'merchant_wallet', 'amount_raw', 'decimals', 'symbol',
            'fee_bps', 'disputed_at', 'dispute_timeout', 'server_time', 'note', 'resolution'}
RES_KEYS = {'resolution_id', 'payout_to', 'amount_raw', 'nonce', 'deadline', 'status', 'reason_note', 'submitted_tx_hash', 'created_at',
            'payout_side', 'signatures'}


def test_get_matches_the_contract_proposed_by_the_ui_and_never_returns_raw_signatures(rig):
    from slopee_web3.application.dispute_note_service import DisputeNoteService
    DisputeNoteService(rig.st.uow).save_note(rig.buyer, rig.code, 'Hàng bị vỡ', 'https://example.com/a.jpg')
    empty = rig.ds.get(rig.buyer, 'user', rig.code)
    assert set(empty) == GET_KEYS and empty['resolution'] is None and empty['your_party'] == 'BUYER'
    assert empty['note']['reason'] == 'Hàng bị vỡ' and set(empty['note']) == {'reason', 'evidence_url', 'updated_at'}
    p = rig.propose('MERCHANT', note='Có biên bản giao hàng')
    rig.ds.add_signature(rig.merchant, rig.code, p['resolution_id'], rig.sign('merchant1', p))
    on = rig.st.chain.get_order(rig.oid)
    for uid, role, party in ((rig.buyer, 'user', 'BUYER'), (rig.merchant, 'seller', 'MERCHANT'), (rig.admin, 'admin', 'ADMIN')):
        g = rig.ds.get(uid, role, rig.code)
        assert set(g) == GET_KEYS and set(g['resolution']) == RES_KEYS and g['your_party'] == party
        assert g['order_status'] == 'DISPUTED' and g['onchain_order_id'] == str(rig.oid) and g['decimals'] == 6 and g['symbol']
        assert g['buyer_wallet'] == on['buyer'].lower() or g['buyer_wallet'].lower() == on['buyer'].lower()
        assert g['amount_raw'] == str(on['amount']) and g['fee_bps'] == on['fee_bps'] and g['disputed_at'] == rig.disputed_at
        r = g['resolution']
        assert r['status'] == 'READY' and r['payout_side'] == 'MERCHANT' and r['reason_note'] == 'Có biên bản giao hàng'
        assert r['nonce'] == '0' and r['amount_raw'] == str(on['amount']) and isinstance(r['deadline'], int) and r['submitted_tx_hash'] is None
        assert [(s['party'], s['signer']) for s in r['signatures']] == [('ARBITRATOR', ADDR['arbitrator'].lower()),
                                                                          ('MERCHANT', ADDR['merchant1'].lower())]
        assert all(set(s) == {'party', 'signer', 'signed_at'} and isinstance(s['signed_at'], int) for s in r['signatures'])
        assert not RAW_SIG.search(json.dumps(g))                          # KHÔNG có chuỗi chữ ký thô nào trong phản hồi


def test_get_hides_the_order_from_everyone_but_its_parties_and_admin(rig, db):
    for uid, role in ((user(db, 'user'), 'user'), (user(db, 'seller'), 'seller'), (user(db, 'shipper'), 'shipper'), ('khong-co-user', 'user')):
        assert code_of(rig.ds.get, uid, role, rig.code).code == 'ORDER_NOT_FOUND'
    assert code_of(rig.ds.get, rig.admin, 'admin', 'khong-co-don').code == 'ORDER_NOT_FOUND'


def test_get_returns_only_the_latest_proposal(rig):
    first = rig.propose('BUYER')
    second = rig.propose('MERCHANT')
    g = rig.ds.get(rig.buyer, 'user', rig.code)
    assert g['resolution']['resolution_id'] == second['resolution_id'] and g['resolution']['status'] == 'PROPOSED'
    assert first['resolution_id'] != second['resolution_id']


# ------------------------------------------------------------------------------------------------ đầy đủ với phần nộp của A + Indexer
@pytest.mark.parametrize('payout,signer_key,user_attr,final,legacy', [
    ('BUYER', 'buyer', 'buyer', 'REFUNDED', 'cancelled'),
    ('MERCHANT', 'merchant1', 'merchant', 'COMPLETED', 'received'),
])
def test_full_flow_propose_sign_submit_index_executes_the_proposal(rig, payout, signer_key, user_attr, final, legacy):
    st = rig.st
    p = rig.propose(payout)
    uid = getattr(rig, user_attr)
    assert rig.ds.add_signature(uid, rig.code, p['resolution_id'], rig.sign(signer_key, p))['status'] == 'READY'
    out = rig.sub.submit(uid, 'user' if user_attr == 'buyer' else 'seller', rig.code)          # A: relayer nộp resolveDispute
    assert out['outcome'] == 'SENT' and out['tx_hash'] and rig.res(p['resolution_id'])['status'] == 'SUBMITTED'
    assert st.chain.dispute_nonce(rig.oid) == 1 and status(rig.db, rig.code) == 'DISPUTED'     # API không ghi trạng thái đơn (BR-09)
    st.index()                                                                                 # B: Indexer ghi nhận
    assert status(rig.db, rig.code) == final and rig.res(p['resolution_id'])['status'] == 'EXECUTED'
    assert row(rig.db, "SELECT status FROM orders WHERE id=%s", rig.code)['status'] == legacy
    rig.db.execute("SELECT user_id FROM notifications WHERE kind='DISPUTE_RESOLVED' AND order_id=%s", (rig.code,))
    assert {r['user_id'] for r in rig.db.fetchall()} == {rig.buyer, rig.merchant}
    assert row(rig.db, "SELECT anomaly_flag AS a FROM order_web3 WHERE order_id=%s", rig.code)['a'] == 0
    st.index()                                                                                 # chạy lại: không đổi, không nhân đôi
    assert row(rig.db, "SELECT COUNT(*) AS c FROM notifications WHERE kind='DISPUTE_RESOLVED'")['c'] == 2
    assert st.reconcile.run(deep=True)['ok']                                                   # tiền khớp sau phán quyết
    assert rig.ds.get(rig.buyer, 'user', rig.code)['resolution']['status'] == 'EXECUTED'
    assert code_of(rig.ds.add_signature, rig.merchant, rig.code, p['resolution_id'], rig.sign('merchant1', p)).code == 'INVALID_STATE'


# ------------------------------------------------------------------------------------------------ Indexer
def _inject_resolved(rig, payout):
    """Chèn thẳng một DisputeResolved (kèm OrderCompleted/Refunded) như thể ai đó nộp chữ ký ngoài sàn."""
    c = rig.st.chain
    o = c.orders[rig.oid]
    (c._refund if payout.lower() == o['buyer'].lower() else c._complete)(rig.oid, o)
    c._mine(('DisputeResolved', dict(orderId=rig.oid, payoutTo=payout, amount=o['amount'])))


@pytest.mark.parametrize('prior', ['PROPOSED', 'READY', 'SUBMITTED', 'EXPIRED'])
def test_dispute_resolved_executes_the_matching_proposal_from_any_live_state(rig, prior):
    p = rig.propose('BUYER')
    rig.db.execute("UPDATE dispute_resolutions SET status=%s WHERE id=%s", (prior, p['resolution_id']))
    _inject_resolved(rig, p['payout_to'])
    rig.st.index()
    assert rig.res(p['resolution_id'])['status'] == 'EXECUTED'
    assert row(rig.db, "SELECT anomaly_flag AS a FROM order_web3 WHERE order_id=%s", rig.code)['a'] == 0


def test_dispute_resolved_for_a_cancelled_proposal_is_recorded_but_flagged(rig):
    old = rig.propose('BUYER')
    rig.propose('MERCHANT')                                              # Admin đổi ý: đề xuất cũ bị hủy trên sàn nhưng chữ ký còn hiệu lực trên chuỗi
    _inject_resolved(rig, old['payout_to'])
    rig.st.index()
    assert rig.res(old['resolution_id'])['status'] == 'EXECUTED'          # chuỗi là sự thật
    assert row(rig.db, "SELECT anomaly_flag AS a FROM order_web3 WHERE order_id=%s", rig.code)['a'] == 1


def test_dispute_resolved_matching_no_proposal_only_flags_an_anomaly(rig):
    p = rig.propose('BUYER')
    _inject_resolved(rig, rig.st.chain.get_order(rig.oid)['merchant'])    # đề xuất của sàn là hoàn tiền nhưng chuỗi trả cho người bán
    rig.st.index()
    assert rig.res(p['resolution_id'])['status'] == 'PROPOSED'
    assert row(rig.db, "SELECT anomaly_flag AS a FROM order_web3 WHERE order_id=%s", rig.code)['a'] == 1


def test_dispute_resolved_for_unknown_order_is_only_logged(rig):
    c = rig.st.chain
    c._mine(('DisputeResolved', dict(orderId=999999999, payoutTo=ADDR['buyer'], amount=1)))
    assert rig.st.index()['new_events'] == 1
    assert row(rig.db, "SELECT COUNT(*) AS c FROM order_web3 WHERE anomaly_flag=1")['c'] == 0


@pytest.mark.parametrize('payout,final', [('BUYER', 'REFUNDED'), ('MERCHANT', 'COMPLETED')])
def test_arbitrator_force_resolve_cancels_open_proposals_and_notifies(rig, payout, final):
    p = rig.propose('BUYER')
    rig.ds.add_signature(rig.buyer, rig.code, p['resolution_id'], rig.sign('buyer', p))
    c = rig.st.chain
    with pytest.raises(ChainTxFailed):
        c.arbitrator_force_resolve(rig.oid, c.get_order(rig.oid)['buyer'])                   # chưa tới mốc: contract từ chối
    c.advance(rig.timeout)
    c.arbitrator_force_resolve(rig.oid, c.get_order(rig.oid)['buyer' if payout == 'BUYER' else 'merchant'])
    rig.st.index()
    assert status(rig.db, rig.code) == final and rig.res(p['resolution_id'])['status'] == 'CANCELLED'
    rig.db.execute("SELECT message FROM notifications WHERE kind='DISPUTE_RESOLVED' AND order_id=%s", (rig.code,))
    msgs = [r['message'] for r in rig.db.fetchall()]
    assert len(msgs) == 2 and all('Trọng tài' in m for m in msgs)
    assert row(rig.db, "SELECT anomaly_flag AS a FROM order_web3 WHERE order_id=%s", rig.code)['a'] == 0


def _executed_via_submit(rig):
    p = rig.propose('BUYER')
    rig.ds.add_signature(rig.buyer, rig.code, p['resolution_id'], rig.sign('buyer', p))
    rig.sub.submit(rig.buyer, 'user', rig.code)
    rig.st.index()
    assert rig.res(p['resolution_id'])['status'] == 'EXECUTED'
    return p


def _index(rig, depth=1000):
    conn = connect()
    try:
        return Indexer(connect, rig.st.chain, start_block=0, reorg_depth=depth).run_once(conn)
    finally:
        conn.close()


def test_reorg_that_replays_dispute_resolved_keeps_it_executed_without_anomaly(rig):
    p = _executed_via_submit(rig)
    rig.st.chain.blocks[rig.st.chain.head] = {'hash': '0x' + 'ee' * 32}      # block cuối đổi: Indexer phát hiện reorg và quét lại
    _index(rig)
    assert rig.res(p['resolution_id'])['status'] == 'EXECUTED' and status(rig.db, rig.code) == 'REFUNDED'
    assert row(rig.db, "SELECT anomaly_flag AS a FROM order_web3 WHERE order_id=%s", rig.code)['a'] == 0
    assert row(rig.db, "SELECT COUNT(*) AS c FROM notifications WHERE kind='DISPUTE_RESOLVED'")['c'] == 2


def test_reorg_that_drops_dispute_resolved_puts_the_proposal_back_and_the_order_back_to_disputed(rig):
    p = _executed_via_submit(rig)
    c = rig.st.chain
    c.logs = [e for e in c.logs if e['event'] not in ('DisputeResolved', 'OrderRefunded')]   # nhánh mới không có phán quyết
    c.blocks[c.head] = {'hash': '0x' + 'ee' * 32}
    _index(rig)
    assert status(rig.db, rig.code) == 'DISPUTED'
    r = rig.res(p['resolution_id'])
    assert r['status'] == 'SUBMITTED' and r['submitted_tx_hash']             # relayer đã nộp: quay về SUBMITTED, không phải READY
    assert row(rig.db, "SELECT COUNT(*) AS c FROM notifications WHERE kind='DISPUTE_RESOLVED'")['c'] == 0


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


def H(uid, role='user'):
    return {'Authorization': f'Bearer {issue_token(uid, role)}', 'Origin': ORIGIN}


def test_http_end_to_end_including_cors_preflight_and_a_submit(rig, http, db):
    code = rig.code
    for path, method in ((f'/api/admin/disputes/{code}/proposal', 'POST'), (f'/api/disputes/{code}/signatures', 'POST'), (f'/api/disputes/{code}', 'GET')):
        pre = http.options(path, headers={'Origin': ORIGIN, 'Access-Control-Request-Method': method,
                                          'Access-Control-Request-Headers': 'authorization,content-type'})
        assert pre.status_code == 200 and pre.headers['Access-Control-Allow-Origin'] == ORIGIN, path

    assert http.post(f'/api/admin/disputes/{code}/proposal', json={'payout_to': 'BUYER'}, headers=H(rig.buyer)).status_code == 403
    bad = http.post(f'/api/admin/disputes/{code}/proposal', json={'payout_to': 'nobody'}, headers=H(rig.admin, 'admin'))
    assert bad.status_code == 422 and bad.get_json()['code'] == 'INVALID_PAYOUT'
    r = http.post(f'/api/admin/disputes/{code}/proposal', json={'payout_to': 'BUYER', 'reason_note': 'Đủ bằng chứng'}, headers=H(rig.admin, 'admin'))
    p = r.get_json()
    assert r.status_code == 201 and p['status'] == 'PROPOSED' and p['payout_side'] == 'BUYER'

    g = http.get(f'/api/disputes/{code}', headers=H(rig.buyer)).get_json()
    assert g['your_party'] == 'BUYER' and g['resolution']['resolution_id'] == p['resolution_id'] and not RAW_SIG.search(json.dumps(g))
    assert http.get(f'/api/disputes/{code}', headers=H(user(db, 'user'))).status_code == 404
    assert http.get(f'/api/disputes/{code}', headers=H(user(db, 'shipper'), 'shipper')).status_code == 403

    sig = rig.sign('buyer', p)
    body = {'resolution_id': p['resolution_id'], 'signature': sig}
    assert http.post(f'/api/disputes/{code}/signatures', json=body, headers=H(rig.admin, 'admin')).status_code == 403
    assert http.post(f'/api/disputes/{code}/signatures', json=body, headers=H(rig.merchant, 'seller')).status_code == 400      # chữ ký của Buyer, người gửi là Merchant
    ok = http.post(f'/api/disputes/{code}/signatures', json=body, headers=H(rig.buyer))
    assert ok.status_code == 200 and ok.get_json()['status'] == 'READY'
    assert http.post(f'/api/disputes/{code}/signatures', json=body, headers=H(rig.buyer)).status_code == 200                      # gửi lại
    assert http.post(f'/api/disputes/{code}/signatures', json={'signature': sig}, headers=H(rig.buyer)).status_code == 400
    sub = http.post(f'/api/disputes/{code}/submit', headers=H(rig.buyer))                                                          # A
    assert sub.status_code == 200 and sub.get_json()['outcome'] == 'SENT'
    rig.st.index()
    assert http.get(f'/api/disputes/{code}', headers=H(rig.merchant, 'seller')).get_json()['resolution']['status'] == 'EXECUTED'
