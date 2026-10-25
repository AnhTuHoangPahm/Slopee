"""Tuần 9 [C]: `scripts/demo_helper.py` (trợ thủ demo). Không cần MySQL/Anvil: một máy chủ HTTP giả đóng vai cả JSON-RPC của Anvil lẫn REST của backend.
Mục tiêu: lệnh nào cũng gửi đúng cuộc gọi, từ chối đầu vào xấu TRƯỚC khi chạm mạng, thông báo lỗi dễ hiểu khi thiếu stack,
và script không chứa khóa riêng (AC-09)."""
import importlib.util
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('demo_helper', ROOT / 'scripts' / 'demo_helper.py')
dh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dh)

BUYER = '0x' + 'ab' * 20
SHIPPER_ID = 'shipper-uuid-1'


class Fake:
    """Trạng thái dùng chung giữa test và máy chủ giả."""
    def __init__(self):
        self.rpc = []            # [(method, params)]
        self.http = []           # [(method, path, auth, body)]
        self.chain_id = 31337
        self.login_ok = True
        self.reconcile_ok = True
        self.deliver_status = 200
        self.now = 1_800_000_000
        self.users = {}          # username -> role (đã đăng ký)
        self.methods = {}        # token -> số phương thức nhận tiền
        self.shops = {}          # token -> {'name', 'products': [...]}
        self.phone_clash = 0     # số lần đầu signup trả "Phone already exists"


@pytest.fixture()
def fake(monkeypatch, tmp_path):
    state = Fake()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            raw = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _body(self):
            n = int(self.headers.get('Content-Length') or 0)
            return json.loads(self.rfile.read(n)) if n else None

        def do_POST(self):
            body = self._body()
            if self.path == '/rpc':
                m, p = body['method'], body.get('params', [])
                state.rpc.append((m, p))
                res = {
                    'eth_chainId': hex(state.chain_id),
                    'eth_accounts': ['0x' + '11' * 20],
                    'anvil_setBalance': None,
                    'eth_sendTransaction': '0x' + 'cd' * 32,
                    'eth_getTransactionReceipt': {'status': '0x1'},
                    'eth_call': hex(1_000 * 10 ** 6),
                    'evm_increaseTime': '0x0', 'evm_mine': '0x0',
                    'eth_getBlockByNumber': {'timestamp': hex(state.now)},
                    'eth_getCode': '0x6080',
                }.get(m)
                if m == 'evm_mine':
                    state.now += 1
                return self._send(200, {'jsonrpc': '2.0', 'id': body['id'], 'result': res})
            state.http.append(('POST', self.path, self.headers.get('Authorization'), body))
            if self.path == '/api/auth/signup':
                if state.phone_clash > 0:
                    state.phone_clash -= 1
                    return self._send(400, {'error': 'Email or Phone already exists!'})
                if body['username'] in state.users:
                    return self._send(400, {'error': 'Username already taken!'})
                state.users[body['username']] = body['role']
                return self._send(201, {'message': 'ok'})
            if self.path == '/api/auth/login':
                if not state.login_ok:
                    return self._send(401, {'error': 'bad credentials'})
                u = body['username']
                if u in state.users:
                    return self._send(200, {'token': f'T-{u}', 'user': {'id': f'id-{u}'}})
                is_admin = u == 'e2e_admin'
                return self._send(200, {'token': 'T-admin' if is_admin else 'T-ship', 'user': {'id': 'admin-1' if is_admin else SHIPPER_ID}})
            tok = (self.headers.get('Authorization') or '').replace('Bearer ', '')
            if self.path == '/api/payments/':
                state.methods[tok] = state.methods.get(tok, 0) + 1
                return self._send(201, {'ok': True})
            if self.path == '/api/shops/':
                state.shops[tok] = {'name': body['name'], 'products': []}
                return self._send(201, {'shopId': 'shop-' + tok})
            if self.path == '/api/shops/products':
                state.shops[tok]['products'].append({'name': body['name'], 'unitPrice': body['unitPrice'], 'inStock': body['inStock']})
                return self._send(201, {'productId': 'p1'})
            if self.path.endswith('/deliver'):
                return self._send(state.deliver_status, {'outcome': 'SENT'} if state.deliver_status == 200 else {'error': 'INVALID_STATE'})
            self._send(404, {'error': 'nf'})

        def do_PUT(self):
            state.http.append(('PUT', self.path, self.headers.get('Authorization'), self._body()))
            self._send(200, {'ok': True})

        def do_GET(self):
            state.http.append(('GET', self.path, self.headers.get('Authorization'), None))
            if self.path == '/api/health':
                return self._send(200, {'status': 'healthy'})
            tok = (self.headers.get('Authorization') or '').replace('Bearer ', '')
            if self.path == '/api/payments/':
                return self._send(200, {'methods': [{'id': 'm'}] * state.methods.get(tok, 0)})
            if self.path == '/api/shops/me':
                return self._send(200, state.shops[tok]) if tok in state.shops else self._send(404, {'error': 'Shop not found'})
            if self.path.startswith('/api/admin/reconcile'):
                return self._send(200, {'ok': state.reconcile_ok, 'status': 'OK' if state.reconcile_ok else 'MISMATCH'})
            if self.path.endswith('/status'):
                return self._send(200, {'order_id': 'o1', 'status': 'LOCKED'})
            self._send(404, {'error': 'nf'})

    srv = HTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_port}'
    monkeypatch.setattr(dh, 'RPC_URL', f'{base}/rpc')
    monkeypatch.setattr(dh, 'API_URL', base)
    monkeypatch.setattr(dh, 'ROOT', str(tmp_path))
    (tmp_path / 'deployments').mkdir()
    (tmp_path / 'deployments' / 'local.json').write_text(json.dumps({'escrow': '0x' + '22' * 20, 'mockUSD': '0x' + '33' * 20}))
    for k in ('E2E_ADMIN_USER', 'E2E_ADMIN_PASSWORD', 'E2E_SHIPPER_USER', 'E2E_SHIPPER_PASSWORD'):
        monkeypatch.delenv(k, raising=False)
    yield state
    srv.shutdown()


def rpc_methods(state):
    return [m for m, _ in state.rpc]


# ---------------------------------------------------------------- thời lượng
@pytest.mark.parametrize('text,secs', [('3d', 259_200), ('14d', 1_209_600), ('30D', 2_592_000), ('2h', 7_200), ('90m', 5_400), ('7200s', 7_200), ('45', 45)])
def test_parse_duration_ok(text, secs):
    assert dh.parse_duration(text) == secs


@pytest.mark.parametrize('bad', ['', '0d', 'abc', '-3d', '1.5d', '3 days', '3w'])
def test_parse_duration_rejects(bad):
    with pytest.raises(dh.HelperError):
        dh.parse_duration(bad)


# ---------------------------------------------------------------- prepare
def test_prepare_creates_buyer_two_shops_and_products(fake, capsys):
    assert dh.main(['prepare']) == 0
    assert fake.users == {'demo_buyer': 'user', 'demo_shop_a': 'seller', 'demo_shop_b': 'seller'}
    assert fake.methods == {'T-demo_shop_a': 1, 'T-demo_shop_b': 1}            # chỉ shop mới cần phương thức nhận tiền
    assert fake.shops['T-demo_shop_a']['products'] == [{'name': 'Áo thun Slopee', 'unitPrice': 400_000, 'inStock': 50}]
    assert fake.shops['T-demo_shop_b']['products'] == [{'name': 'Cốc sứ Slopee', 'unitPrice': 500_000, 'inStock': 50}]
    out = capsys.readouterr().out
    assert 'SecurePass123!' in out and '/wallet' in out and 'DEMO_GUIDE.md' in out


def test_prepare_is_idempotent(fake):
    assert dh.main(['prepare']) == 0
    assert dh.main(['prepare']) == 0
    assert fake.methods == {'T-demo_shop_a': 1, 'T-demo_shop_b': 1}            # không thêm phương thức nhận tiền thứ hai
    assert [len(v['products']) for v in fake.shops.values()] == [1, 1]         # không nhân đôi sản phẩm
    assert len([h for h in fake.http if h[1] == '/api/shops/']) == 2


def test_prepare_retries_random_phone_collision(fake):
    fake.phone_clash = 2
    assert dh.main(['prepare']) == 0
    assert len(fake.users) == 3


def test_prepare_uses_demo_password_env(fake, monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD', 'AnotherPass#99')
    assert dh.main(['prepare']) == 0
    signups = [h[3] for h in fake.http if h[1] == '/api/auth/signup']
    assert signups and all(b['password'] == 'AnotherPass#99' and b['pass_phrase'] == '123456' for b in signups)


def test_prepare_login_failure_is_explained(fake, capsys):
    fake.login_ok = False
    assert dh.main(['prepare']) == 1
    assert 'DEMO_PASSWORD' in capsys.readouterr().err


# ---------------------------------------------------------------- fund
def test_fund_sends_eth_and_exact_mint_calldata(fake, capsys):
    assert dh.main(['fund', BUYER, '--usd', '250.5', '--eth', '3']) == 0
    sets = [p for m, p in fake.rpc if m == 'anvil_setBalance']
    assert sets == [[BUYER, hex(3 * 10 ** 18)]]
    tx = [p for m, p in fake.rpc if m == 'eth_sendTransaction'][0][0]
    assert tx['to'] == '0x' + '33' * 20 and tx['from'] == '0x' + '11' * 20          # từ tài khoản mở khóa sẵn của Anvil, không khóa riêng
    assert tx['data'] == '0x40c10f19' + BUYER[2:].rjust(64, '0') + format(250_500_000, 'x').rjust(64, '0')   # 6 chữ số thập phân
    assert 'mUSD' in capsys.readouterr().out


def test_fund_usd_zero_skips_mint(fake):
    assert dh.main(['fund', BUYER, '--usd', '0']) == 0
    assert 'eth_sendTransaction' not in rpc_methods(fake)


@pytest.mark.parametrize('bad', ['0x123', 'abc', '0x' + 'zz' * 20, '0x' + 'ab' * 21])
def test_fund_rejects_bad_address_before_any_network_call(fake, bad, capsys):
    assert dh.main(['fund', bad]) == 1
    assert fake.rpc == [] and fake.http == []
    assert 'Địa chỉ ví' in capsys.readouterr().err


def test_refuses_non_anvil_chain(fake, capsys):
    fake.chain_id = 1
    assert dh.main(['fund', BUYER]) == 1
    assert dh.main(['warp', '1d']) == 1
    assert not {'anvil_setBalance', 'eth_sendTransaction', 'evm_increaseTime'} & set(rpc_methods(fake))   # không bao giờ ghi lên chuỗi lạ
    assert '31337' in capsys.readouterr().err


# ---------------------------------------------------------------- warp
def test_warp_increases_time_then_mines(fake, capsys):
    assert dh.main(['warp', '14d']) == 0
    m = rpc_methods(fake)
    assert [p for k, p in fake.rpc if k == 'evm_increaseTime'] == [[1_209_600]]
    assert m.index('evm_increaseTime') < m.index('evm_mine')
    assert 'không đảo ngược' in capsys.readouterr().out


def test_warp_bad_duration_does_not_touch_chain(fake):
    assert dh.main(['warp', 'soon']) == 1
    assert fake.rpc == []


# ---------------------------------------------------------------- assign / deliver / ship
def test_assign_uses_admin_token_and_shipper_id(fake):
    assert dh.main(['assign', 'ORD-1', 'ORD-2']) == 0
    puts = [h for h in fake.http if h[0] == 'PUT']
    assert [(p[1], p[2], p[3]) for p in puts] == [
        ('/api/admin/orders/ORD-1/shipper', 'Bearer T-admin', {'shipper_user_id': SHIPPER_ID}),
        ('/api/admin/orders/ORD-2/shipper', 'Bearer T-admin', {'shipper_user_id': SHIPPER_ID}),
    ]


def test_deliver_uses_shipper_token(fake, capsys):
    assert dh.main(['deliver', 'ORD-1']) == 0
    d = [h for h in fake.http if h[1].endswith('/deliver')]
    assert d == [('POST', '/api/shipper/orders/ORD-1/deliver', 'Bearer T-ship', None)]
    assert 'SENT' in capsys.readouterr().out


def test_ship_assigns_before_delivering_each_order(fake):
    assert dh.main(['ship', 'A', 'B']) == 0
    seq = [(h[0], h[1].split('/')[-2] if h[0] == 'PUT' else h[1].split('/')[-2]) for h in fake.http if h[0] in ('PUT',) or h[1].endswith('/deliver')]
    assert [s[0] for s in seq] == ['PUT', 'POST', 'PUT', 'POST']


def test_deliver_failure_is_reported_not_crashed(fake, capsys):
    fake.deliver_status = 409
    assert dh.main(['deliver', 'ORD-1']) == 1
    assert 'INVALID_STATE' in capsys.readouterr().err


def test_login_failure_explains_how_to_seed(fake, capsys):
    fake.login_ok = False
    assert dh.main(['assign', 'X']) == 1
    err = capsys.readouterr().err
    assert 'e2e_stack.sh seed' in err and 'E2E_ADMIN_PASSWORD' in err


def test_credentials_can_be_overridden_by_env(fake, monkeypatch):
    monkeypatch.setenv('E2E_ADMIN_USER', 'boss')
    monkeypatch.setenv('E2E_ADMIN_PASSWORD', 'x' * 12)
    dh.main(['assign', 'X'])
    logins = [h[3] for h in fake.http if h[1] == '/api/auth/login']
    assert {'username': 'boss', 'password': 'x' * 12} in logins


# ---------------------------------------------------------------- status / reconcile / check
def test_status_prints_json(fake, capsys):
    assert dh.main(['status', 'ORD-1']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'LOCKED'


def test_reconcile_ok_and_mismatch_exit_codes(fake, capsys):
    assert dh.main(['reconcile']) == 0
    fake.reconcile_ok = False
    assert dh.main(['reconcile']) == 1
    assert 'LỆCH' in capsys.readouterr().err
    assert any('deep=1' in h[1] for h in fake.http)


def test_check_ready_when_everything_is_up(fake, capsys):
    assert dh.main(['check']) == 0
    assert 'Sẵn sàng demo' in capsys.readouterr().out


def test_check_reports_every_problem_at_once(fake, monkeypatch, capsys):
    fake.login_ok = False
    (Path(dh.ROOT) / 'deployments' / 'local.json').unlink()
    assert dh.main(['check']) == 1
    err = capsys.readouterr().err
    assert 'deployments/local.json' in err and 'Không đăng nhập' in err


def test_missing_stack_gives_human_message(monkeypatch, capsys):
    monkeypatch.setattr(dh, 'RPC_URL', 'http://127.0.0.1:9')        # cổng đóng
    monkeypatch.setattr(dh, 'API_URL', 'http://127.0.0.1:9')
    assert dh.main(['fund', BUYER]) == 1
    assert 'Anvil chưa chạy' in capsys.readouterr().err


# ---------------------------------------------------------------- AC-09: không khóa trong script
def test_script_contains_no_private_key_material():
    text = (ROOT / 'scripts' / 'demo_helper.py').read_text(encoding='utf-8')
    assert not re.search(r'0x[0-9a-fA-F]{64}', text), 'script demo không được chứa chuỗi hex 32 byte (khóa/hash)'
    assert not re.search(r'(?i)private[_ ]?key\s*=', text)
    assert 'Account.from_key' not in text
