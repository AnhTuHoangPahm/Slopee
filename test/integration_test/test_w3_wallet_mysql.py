"""UC-00 trên MySQL THẬT (I-01): nonce một lần, chữ ký personal_sign, một ví một tài khoản, đổi ví, đua song song."""
import threading

import pytest
from flask import Flask

from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container, register_web3
from slopee_web3.domain.errors import DomainError
from w3_support import ADDR, DOMAIN, KEYS, Env, connect, link_wallet, sign_message, user, with_0x

pytestmark = pytest.mark.mysql


def _clean():
    """Các test dùng chung khóa Anvil cố định: dọn bảng ví/nonce để mỗi test bắt đầu sạch."""
    conn = connect()
    conn.autocommit(True)
    cur = conn.cursor()
    cur.execute("DELETE FROM user_wallets")
    cur.execute("DELETE FROM wallet_nonces")
    return conn, cur


@pytest.fixture
def env(mysql_db):
    _clean()[0].close()
    return Env()


@pytest.fixture
def db(env):
    conn, cur = _clean()
    yield cur
    conn.close()


def _link(env, uid, key, nonce=None, address=None, signer_key=None):
    """Chạy trọn UC-00 cho `uid` bằng khóa `key`. Trả (kết quả link, thông điệp)."""
    address = address or ADDR[key]
    issued = env.wallet.issue_nonce(uid, address)
    sig = with_0x(sign_message(signer_key or key, issued['message']))
    return env.wallet.link_wallet(uid, address, sig, nonce), issued


def _code(fn, *a, **kw):
    with pytest.raises(DomainError) as e:
        fn(*a, **kw)
    return e.value.code


def _rows(db, sql, *args):
    db.execute(sql, args)
    return list(db.fetchall())


def test_happy_path_links_wallet_lowercase_and_consumes_nonce(env, db):
    uid = user(db)
    out, issued = _link(env, uid, 'buyer', nonce=None)
    assert out['address'] == ADDR['buyer'].lower()
    assert _rows(db, "SELECT address, is_active FROM user_wallets WHERE user_id=%s", uid) == [
        {'address': ADDR['buyer'].lower(), 'is_active': 1}]
    assert _rows(db, "SELECT used_at IS NOT NULL AS used FROM wallet_nonces WHERE nonce=%s", issued['nonce'])[0]['used'] == 1
    assert env.wallet.get_wallet(uid) == {'linked': True, 'address': ADDR['buyer'].lower(), 'linked_at': out['linked_at']}


def test_message_binds_address_account_nonce_chain_and_expiry(env, db):
    uid = user(db)
    issued = env.wallet.issue_nonce(uid, ADDR['buyer'])
    m = issued['message']
    assert DOMAIN in m and ADDR['buyer'].lower() in m and uid in m and issued['nonce'] in m and 'Chain ID: 31337' in m
    assert issued['expires_at'] > 0 and len(issued['nonce']) == 32


def test_get_wallet_when_not_linked(env, db):
    assert env.wallet.get_wallet(user(db)) == {'linked': False, 'address': None, 'linked_at': None}


def test_nonce_is_single_use_replay_rejected(env, db):
    uid = user(db)
    issued = env.wallet.issue_nonce(uid, ADDR['buyer'])
    sig = with_0x(sign_message('buyer', issued['message']))
    env.wallet.link_wallet(uid, ADDR['buyer'], sig, issued['nonce'])
    assert _code(env.wallet.link_wallet, uid, ADDR['buyer'], sig, issued['nonce']) == 'NONCE_INVALID'
    assert _code(env.wallet.link_wallet, uid, ADDR['buyer'], sig) == 'NONCE_INVALID'     # không nonce nào còn dùng được


def test_expired_nonce_rejected(env, db):
    uid = user(db)
    issued = env.wallet.issue_nonce(uid, ADDR['buyer'])
    db.execute("UPDATE wallet_nonces SET expires_at = NOW() - INTERVAL 1 SECOND WHERE nonce=%s", (issued['nonce'],))
    sig = with_0x(sign_message('buyer', issued['message']))
    assert _code(env.wallet.link_wallet, uid, ADDR['buyer'], sig, issued['nonce']) == 'NONCE_INVALID'
    assert _rows(db, "SELECT 1 FROM user_wallets WHERE user_id=%s", uid) == []


def test_signature_from_another_key_rejected_and_changes_nothing(env, db):
    uid = user(db)
    issued = env.wallet.issue_nonce(uid, ADDR['buyer'])
    forged = with_0x(sign_message('stranger', issued['message']))
    assert _code(env.wallet.link_wallet, uid, ADDR['buyer'], forged, issued['nonce']) == 'BAD_SIGNATURE'
    assert _rows(db, "SELECT 1 FROM user_wallets WHERE user_id=%s", uid) == []
    assert _rows(db, "SELECT used_at FROM wallet_nonces WHERE nonce=%s", issued['nonce'])[0]['used_at'] is None
    # nonce chưa bị đốt: người dùng thật vẫn ký lại được
    ok = env.wallet.link_wallet(uid, ADDR['buyer'], with_0x(sign_message('buyer', issued['message'])), issued['nonce'])
    assert ok['address'] == ADDR['buyer'].lower()


def test_signature_of_a_different_message_rejected(env, db):
    uid = user(db)
    issued = env.wallet.issue_nonce(uid, ADDR['buyer'])
    sig = with_0x(sign_message('buyer', issued['message'] + ' '))
    assert _code(env.wallet.link_wallet, uid, ADDR['buyer'], sig, issued['nonce']) == 'BAD_SIGNATURE'


def test_claiming_a_different_address_than_the_signer_is_rejected(env, db):
    uid = user(db)
    issued = env.wallet.issue_nonce(uid, ADDR['buyer'])
    sig = with_0x(sign_message('buyer', issued['message']))
    assert _code(env.wallet.link_wallet, uid, ADDR['merchant1'], sig, issued['nonce']) == 'BAD_SIGNATURE'


def test_garbage_signature_rejected(env, db):
    uid = user(db)
    issued = env.wallet.issue_nonce(uid, ADDR['buyer'])
    assert _code(env.wallet.link_wallet, uid, ADDR['buyer'], '0x' + '00' * 65, issued['nonce']) == 'BAD_SIGNATURE'
    assert _code(env.wallet.link_wallet, uid, ADDR['buyer'], 'xyz', issued['nonce']) == 'BAD_SIGNATURE'
    assert _code(env.wallet.link_wallet, uid, 'not-an-address', '0x' + '1' * 130, issued['nonce']) == 'INVALID_ADDRESS'


def test_signature_with_v_0_or_1_is_normalised(env, db):
    uid = user(db)
    issued = env.wallet.issue_nonce(uid, ADDR['buyer'])
    sig = with_0x(sign_message('buyer', issued['message']))
    v0 = sig[:-2] + format(int(sig[-2:], 16) - 27, '02x')
    assert env.wallet.link_wallet(uid, ADDR['buyer'], v0, issued['nonce'])['address'] == ADDR['buyer'].lower()


def test_nonce_of_another_account_cannot_be_used(env, db):
    a, b = user(db), user(db)
    issued = env.wallet.issue_nonce(a, ADDR['buyer'])
    sig = with_0x(sign_message('buyer', issued['message']))
    assert _code(env.wallet.link_wallet, b, ADDR['buyer'], sig, issued['nonce']) == 'NONCE_INVALID'
    assert _rows(db, "SELECT 1 FROM user_wallets WHERE user_id=%s", b) == []


def test_message_for_one_account_is_useless_for_another(env, db):
    """Kẻ có thông điệp đã ký của A không gắn được ví đó vào tài khoản B (thông điệp chứa mã tài khoản)."""
    a, b = user(db), user(db)
    ia = env.wallet.issue_nonce(a, ADDR['buyer'])
    ib = env.wallet.issue_nonce(b, ADDR['buyer'])
    sig_for_a = with_0x(sign_message('buyer', ia['message']))
    assert _code(env.wallet.link_wallet, b, ADDR['buyer'], sig_for_a, ib['nonce']) == 'BAD_SIGNATURE'


def test_wallet_already_linked_to_another_account_is_rejected(env, db):
    a, b = user(db), user(db)
    _link(env, a, 'merchant1')
    issued = env.wallet.issue_nonce(b, ADDR['merchant1'])
    sig = with_0x(sign_message('merchant1', issued['message']))
    assert _code(env.wallet.link_wallet, b, ADDR['merchant1'], sig, issued['nonce']) == 'WALLET_TAKEN'
    assert _rows(db, "SELECT user_id FROM user_wallets WHERE address=%s", ADDR['merchant1'].lower()) == [{'user_id': a}]
    assert _rows(db, "SELECT used_at FROM wallet_nonces WHERE nonce=%s", issued['nonce'])[0]['used_at'] is None  # không đốt nonce


def test_deactivated_wallet_of_another_user_stays_reserved(env, db):
    a, b = user(db), user(db)
    _link(env, a, 'merchant1')
    _link(env, a, 'merchant2')                                     # a đổi ví: merchant1 -> is_active = 0
    issued = env.wallet.issue_nonce(b, ADDR['merchant1'])
    sig = with_0x(sign_message('merchant1', issued['message']))
    assert _code(env.wallet.link_wallet, b, ADDR['merchant1'], sig, issued['nonce']) == 'WALLET_TAKEN'


def test_relinking_same_wallet_is_idempotent(env, db):
    uid = user(db)
    first, _ = _link(env, uid, 'buyer')
    second, _ = _link(env, uid, 'buyer')
    assert first == second
    assert len(_rows(db, "SELECT 1 FROM user_wallets WHERE user_id=%s", uid)) == 1


def test_changing_wallet_keeps_exactly_one_active(env, db):
    uid = user(db)
    _link(env, uid, 'buyer')
    _link(env, uid, 'stranger')
    rows = {r['address']: r['is_active'] for r in _rows(db, "SELECT address, is_active FROM user_wallets WHERE user_id=%s", uid)}
    assert rows == {ADDR['buyer'].lower(): 0, ADDR['stranger'].lower(): 1}
    assert env.wallet.get_wallet(uid)['address'] == ADDR['stranger'].lower()
    _link(env, uid, 'buyer')                                       # quay lại ví cũ: bật lại, ví kia tắt
    rows = {r['address']: r['is_active'] for r in _rows(db, "SELECT address, is_active FROM user_wallets WHERE user_id=%s", uid)}
    assert rows == {ADDR['buyer'].lower(): 1, ADDR['stranger'].lower(): 0}


def test_changing_wallet_requires_signature_from_the_new_wallet(env, db):
    uid = user(db)
    _link(env, uid, 'buyer')
    issued = env.wallet.issue_nonce(uid, ADDR['stranger'])
    old_wallet_sig = with_0x(sign_message('buyer', issued['message']))
    assert _code(env.wallet.link_wallet, uid, ADDR['stranger'], old_wallet_sig, issued['nonce']) == 'BAD_SIGNATURE'
    assert env.wallet.get_wallet(uid)['address'] == ADDR['buyer'].lower()


def test_nonce_rate_limit_per_account(mysql_db):
    conn, cur = _clean()
    env = Env(max_nonces=3)
    uid, other = user(cur), user(cur)
    for _ in range(3):
        env.wallet.issue_nonce(uid, ADDR['buyer'])
    assert _code(env.wallet.issue_nonce, uid, ADDR['buyer']) == 'RATE_LIMITED'
    env.wallet.issue_nonce(other, ADDR['buyer'])                   # giới hạn theo tài khoản, không toàn cục
    conn.close()


def test_issue_nonce_rejects_bad_address(env, db):
    assert _code(env.wallet.issue_nonce, user(db), '0x12') == 'INVALID_ADDRESS'


def test_nonces_are_unique_and_unpredictable_format(env, db):
    uid = user(db)
    nonces = {env.wallet.issue_nonce(uid, ADDR['buyer'])['nonce'] for _ in range(4)}
    assert len(nonces) == 4 and all(len(n) == 32 and int(n, 16) >= 0 for n in nonces)


def test_without_nonce_uses_the_latest_unused_one(env, db):
    uid = user(db)
    env.wallet.issue_nonce(uid, ADDR['buyer'])
    latest = env.wallet.issue_nonce(uid, ADDR['buyer'])
    db.execute("UPDATE wallet_nonces SET expires_at = expires_at - INTERVAL 10 SECOND WHERE user_id=%s AND nonce<>%s", (uid, latest['nonce']))
    out = env.wallet.link_wallet(uid, ADDR['buyer'], with_0x(sign_message('buyer', latest['message'])))
    assert out['address'] == ADDR['buyer'].lower()


def test_concurrent_link_with_same_nonce_only_one_wins(env, db):
    uid = user(db)
    issued = env.wallet.issue_nonce(uid, ADDR['buyer'])
    sig = with_0x(sign_message('buyer', issued['message']))
    results, barrier = [], threading.Barrier(4)

    def go():
        barrier.wait()
        try:
            env.wallet.link_wallet(uid, ADDR['buyer'], sig, issued['nonce'])
            results.append('ok')
        except DomainError as e:
            results.append(e.code)

    ts = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count('ok') == 1 and results.count('NONCE_INVALID') == 3, results
    assert len(_rows(db, "SELECT 1 FROM user_wallets WHERE user_id=%s", uid)) == 1


def test_concurrent_accounts_racing_for_one_wallet_only_one_wins(env, db):
    users = [user(db) for _ in range(4)]
    prepared = []
    for u in users:
        i = env.wallet.issue_nonce(u, ADDR['merchant2'])
        prepared.append((u, i['nonce'], with_0x(sign_message('merchant2', i['message']))))
    results, barrier = [], threading.Barrier(len(users))

    def go(u, n, s):
        barrier.wait()
        try:
            env.wallet.link_wallet(u, ADDR['merchant2'], s, n)
            results.append('ok')
        except DomainError as e:
            results.append(e.code)

    ts = [threading.Thread(target=go, args=p) for p in prepared]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count('ok') == 1 and results.count('WALLET_TAKEN') == 3, results
    assert len(_rows(db, "SELECT 1 FROM user_wallets WHERE address=%s", ADDR['merchant2'].lower())) == 1


def test_http_flow_end_to_end(env, db):
    """Qua Flask thật: token -> nonce -> ký -> link -> GET; lỗi có dạng {code, message}."""
    container.set_container(_FakeContainer(env))
    try:
        app = Flask(__name__)
        register_web3(app)
        c = app.test_client()
        uid = user(db)
        h = {'Authorization': f"Bearer {issue_token(uid, 'user')}"}
        n = c.post('/api/wallet/nonce', json={'address': ADDR['buyer']}, headers=h)
        assert n.status_code == 200
        body = n.get_json()
        sig = with_0x(sign_message('buyer', body['message']))
        ok = c.post('/api/wallet/link', json={'address': ADDR['buyer'], 'signature': sig, 'nonce': body['nonce']}, headers=h)
        assert ok.status_code == 200 and ok.get_json()['address'] == ADDR['buyer'].lower()
        assert c.get('/api/wallet', headers=h).get_json()['linked'] is True
        again = c.post('/api/wallet/link', json={'address': ADDR['buyer'], 'signature': sig, 'nonce': body['nonce']}, headers=h)
        assert again.status_code == 400 and again.get_json()['code'] == 'NONCE_INVALID' and 'message' in again.get_json()
    finally:
        container.set_container(None)


class _FakeContainer:
    def __init__(self, env):
        self.env = env

    def wallet_service(self): return self.env.wallet
    def quote_service(self): return self.env.quote
