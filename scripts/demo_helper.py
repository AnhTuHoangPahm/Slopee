#!/usr/bin/env python3
"""Trợ thủ cho buổi demo (Tuần 9, thành viên C). CHỈ dùng thư viện chuẩn; chỉ chạy với Anvil cục bộ (chainId 31337).

Giao diện không có nút cho vài thao tác của "hậu trường" (gán Shipper, cấp mUSD thử, tua giờ chuỗi), nên demo dùng script này
thay cho việc gõ tay curl/cast. Script KHÔNG chứa và KHÔNG cần khóa riêng: Anvil mở khóa sẵn 10 tài khoản đầu nên
`eth_sendTransaction` từ tài khoản #0 không cần ký; còn Admin/Shipper đăng nhập bằng REST như người dùng thường.

  python3 scripts/demo_helper.py prepare                                     # tạo sẵn Buyer + 2 shop (mỗi shop 1 sản phẩm); chạy lại an toàn (idempotent)
  python3 scripts/demo_helper.py fund 0xĐịaChỉVí [--usd 1000] [--eth 100]   # cấp ETH thử + mint mUSD cho ví MetaMask của Buyer
  python3 scripts/demo_helper.py assign MÃ_ĐƠN [MÃ_ĐƠN ...]                  # Admin gán đơn cho Shipper
  python3 scripts/demo_helper.py deliver MÃ_ĐƠN [MÃ_ĐƠN ...]                 # Shipper xác nhận giao (relayer gửi confirmDelivery)
  python3 scripts/demo_helper.py ship MÃ_ĐƠN [...]                           # = assign rồi deliver
  python3 scripts/demo_helper.py warp 3d | 14d | 30d | 7200s | 2h            # tua giờ Anvil (TIẾN VĨNH VIỄN) rồi đào 1 block
  python3 scripts/demo_helper.py status MÃ_ĐƠN                               # trạng thái đơn từ API (do Indexer ghi)
  python3 scripts/demo_helper.py reconcile                                   # đối soát số dư contract (AC-10)
  python3 scripts/demo_helper.py check                                       # kiểm nhanh Anvil, backend, contract, tài khoản Admin/Shipper

Biến môi trường (mặc định khớp `./scripts/e2e_stack.sh up`):
  RPC_URL (http://127.0.0.1:8545)   API_URL (http://localhost:5000)
  E2E_ADMIN_USER / E2E_ADMIN_PASSWORD     (e2e_admin / E2eAdminPass#2026)
  E2E_SHIPPER_USER / E2E_SHIPPER_PASSWORD (e2e_shipper / E2eShipperPass#2026)
  DEMO_PASSWORD (SecurePass123!) mật khẩu chung của 3 tài khoản do `prepare` tạo; PIN thanh toán cố định 123456
Mã thoát: 0 thành công, 1 thao tác thất bại (thiếu Anvil/backend, đối soát lệch, API từ chối), 2 tham số sai (argparse).
"""
import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RPC_URL = os.environ.get('RPC_URL', 'http://127.0.0.1:8545')
API_URL = os.environ.get('API_URL', os.environ.get('VITE_API_BASE', 'http://localhost:5000')).rstrip('/')
CHAIN_ID = 31337
MINT_SELECTOR = '40c10f19'            # keccak("mint(address,uint256)")[:4]: MockUSD.mint là hàm mở (chỉ dùng cho môi trường thử)
BALANCE_OF_SELECTOR = '70a08231'      # keccak("balanceOf(address)")[:4]
ADDR_RE = re.compile(r'^0x[0-9a-fA-F]{40}$')
DEMO_PIN = '123456'
DEMO_ACCOUNTS = (   # (username, vai trò, tên hiển thị, sản phẩm [(tên, giá VND)]); giá VND chia tỷ giá 25.000 VND/mUSD của platform_settings
    ('demo_buyer', 'user', 'Demo Người Mua', ()),
    ('demo_shop_a', 'seller', 'Demo Shop A', (('Áo thun Slopee', 400_000),)),
    ('demo_shop_b', 'seller', 'Demo Shop B', (('Cốc sứ Slopee', 500_000),)),
)
UNITS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}


class HelperError(Exception):
    """Lỗi có thể giải thích cho người chạy demo (không in traceback)."""


def _http(method, url, body=None, token=None, timeout=15):
    data = None if body is None else json.dumps(body).encode()
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode() or 'null'
            return res.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors='replace')
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw[:300]
        return e.code, payload
    except (urllib.error.URLError, OSError) as e:
        raise HelperError(f'Không kết nối được {url}: {e}') from e


_rpc_id = 0


def rpc(method, params=None):
    global _rpc_id
    _rpc_id += 1
    status, out = _http('POST', RPC_URL, {'jsonrpc': '2.0', 'id': _rpc_id, 'method': method, 'params': params or []})
    if status != 200 or not isinstance(out, dict):
        raise HelperError(f'RPC {method} lỗi HTTP {status}')
    if out.get('error'):
        raise HelperError(f"RPC {method}: {out['error'].get('message')}")
    return out['result']


def require_anvil():
    try:
        cid = int(rpc('eth_chainId'), 16)
    except HelperError as e:
        raise HelperError(f'Anvil chưa chạy ở {RPC_URL} (chạy ./scripts/e2e_stack.sh up hoặc ./scripts/bootstrap.sh). {e}') from e
    if cid != CHAIN_ID:
        raise HelperError(f'chainId là {cid}, script chỉ chạy với Anvil cục bộ ({CHAIN_ID}).')


def deployment():
    for p in (os.path.join(ROOT, 'deployments', 'local.json'), os.path.join(ROOT, 'frontend', 'public', 'deployments', 'local.json')):
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                return json.load(f)
    raise HelperError('Không thấy deployments/local.json: hãy chạy ./scripts/bootstrap.sh (hoặc ./scripts/e2e_stack.sh up) trước.')


def creds(prefix):
    user = os.environ.get(f'E2E_{prefix}_USER') or f'e2e_{prefix.lower()}'
    default_pw = {'ADMIN': 'E2eAdminPass#2026', 'SHIPPER': 'E2eShipperPass#2026'}[prefix]
    return user, os.environ.get(f'E2E_{prefix}_PASSWORD') or default_pw


def login(prefix):
    user, pw = creds(prefix)
    status, body = _http('POST', f'{API_URL}/api/auth/login', {'username': user, 'password': pw})
    if status != 200 or not isinstance(body, dict) or 'token' not in body:
        raise HelperError(f"Không đăng nhập được '{user}' (HTTP {status}). Đã gieo tài khoản chưa? "
                          f"Chạy ./scripts/e2e_stack.sh seed, hoặc đặt E2E_{prefix}_USER/E2E_{prefix}_PASSWORD. Phản hồi: {body}")
    return body['token'], body['user']


def api(method, path, token, body=None):
    status, out = _http(method, f'{API_URL}{path}', body, token)
    if status >= 400:
        msg = (out.get('error') or out.get('message') or out) if isinstance(out, dict) else out
        raise HelperError(f'{method} {path} -> {status}: {msg}')
    return out


# ------------------------------------------------------------------ lệnh
def parse_duration(text):
    m = re.fullmatch(r'\s*(\d+)\s*([smhd]?)\s*', text.lower())
    if not m or int(m.group(1)) == 0:
        raise HelperError(f"Khoảng thời gian không hợp lệ: '{text}' (ví dụ 3d, 14d, 2h, 7200s).")
    return int(m.group(1)) * UNITS[m.group(2) or 's']


def demo_password():
    return os.environ.get('DEMO_PASSWORD') or 'SecurePass123!'


def _signup_or_login(username, role, name):
    """Đăng ký (bỏ qua nếu đã có) rồi đăng nhập; trả (token, user, created)."""
    created = False
    for _ in range(5):                         # số điện thoại ngẫu nhiên có thể trùng: thử lại
        phone = '0' + ''.join(random.choice('0123456789') for _ in range(9))
        status, body = _http('POST', f'{API_URL}/api/auth/signup', {
            'username': username, 'password': demo_password(), 'pass_phrase': DEMO_PIN, 'name': name,
            'email': f'{username}@example.com', 'phone': phone, 'role': role})
        if status in (200, 201):
            created = True
            break
        text = json.dumps(body, ensure_ascii=False).lower()
        if 'username' in text and ('taken' in text or 'exists' in text):
            break                              # tài khoản đã có từ lần chạy trước
        if 'phone' in text and 'exists' in text:
            continue                           # trùng số điện thoại ngẫu nhiên: thử số khác
        raise HelperError(f'Đăng ký {username} thất bại (HTTP {status}): {body}')
    status, body = _http('POST', f'{API_URL}/api/auth/login', {'username': username, 'password': demo_password()})
    if status != 200 or 'token' not in body:
        raise HelperError(f"Không đăng nhập được '{username}' (HTTP {status}). Tài khoản có từ trước với mật khẩu khác? Đặt DEMO_PASSWORD đúng, hoặc chạy ./scripts/e2e_stack.sh up để làm sạch. Phản hồi: {body}")
    return body['token'], body['user'], created


def cmd_prepare(a):
    for username, role, name, products in DEMO_ACCOUNTS:
        token, user, created = _signup_or_login(username, role, name)
        line = f"  {username:<12} {role:<6} {'tạo mới' if created else 'đã có '}"
        if role == 'seller':
            if not api('GET', '/api/payments/', token).get('methods'):          # shop chỉ mở được khi có phương thức nhận tiền (luồng cũ)
                api('POST', '/api/payments/', token, {'methodType': 'bank', 'providerName': 'Demo Bank', 'accountNumber': '0001'})
            status, shop = _http('GET', f'{API_URL}/api/shops/me', None, token)
            if status == 404:
                api('POST', '/api/shops/', token, {'name': name, 'description': 'Shop demo Slopee'})
                status, shop = _http('GET', f'{API_URL}/api/shops/me', None, token)
            if status != 200:
                raise HelperError(f'Không đọc được shop của {username} (HTTP {status}): {shop}')
            have = {p['name'] for p in shop.get('products', [])}
            for pname, price in products:
                if pname not in have:
                    api('POST', '/api/shops/products', token, {'name': pname, 'description': 'Sản phẩm demo', 'categoryId': 1, 'inStock': 50, 'unitPrice': price})
                    line += f' + {pname} ({price:,} ₫)'
        print(line)
    print(f'Mật khẩu chung: {demo_password()}   PIN thanh toán: {DEMO_PIN}')
    print('Bước tay còn lại (không tự động được vì cần chữ ký ví): đăng nhập từng tài khoản trên /wallet và liên kết ví MetaMask riêng (xem DEMO_GUIDE.md mục 2).')


def cmd_fund(a):
    if not ADDR_RE.match(a.address):
        raise HelperError('Địa chỉ ví phải dạng 0x + 40 ký tự hex.')
    require_anvil()
    eth_wei = int(a.eth * 10 ** 18)
    rpc('anvil_setBalance', [a.address, hex(eth_wei)])
    msg = [f'ETH thử: {a.eth:g}']
    if a.usd > 0:
        dep = deployment()
        deployer = rpc('eth_accounts')[0]          # tài khoản #0 của Anvil, đã được mở khóa sẵn
        calldata = '0x' + MINT_SELECTOR + a.address[2:].lower().rjust(64, '0') + format(int(a.usd * 10 ** 6), 'x').rjust(64, '0')
        tx = rpc('eth_sendTransaction', [{'from': deployer, 'to': dep['mockUSD'], 'data': calldata}])
        for _ in range(40):                        # đợi biên nhận (Anvil --block-time 2)
            if rpc('eth_getTransactionReceipt', [tx]):
                break
            time.sleep(0.5)
        else:
            raise HelperError(f'Giao dịch mint {tx} chưa được đào sau 20 giây.')
        bal = int(rpc('eth_call', [{'to': dep['mockUSD'], 'data': '0x' + BALANCE_OF_SELECTOR + a.address[2:].lower().rjust(64, '0')}, 'latest']), 16)
        msg.append(f'mUSD: {bal / 10 ** 6:,.2f}')
    print(f'Đã cấp cho {a.address}: ' + ', '.join(msg))


def assign_one(admin_token, shipper_id, code):
    api('PUT', f'/api/admin/orders/{code}/shipper', admin_token, {'shipper_user_id': shipper_id})
    print(f'  [assign]  {code} -> Shipper')


def deliver_one(shipper_token, code):
    out = api('POST', f'/api/shipper/orders/{code}/deliver', shipper_token)
    print(f"  [deliver] {code}: {out.get('outcome', out)} (Indexer sẽ ghi DELIVERED trong vài giây)")


def cmd_assign(a):
    admin_token, _ = login('ADMIN')
    _, shipper = login('SHIPPER')
    for code in a.codes:
        assign_one(admin_token, shipper['id'], code)


def cmd_deliver(a):
    shipper_token, _ = login('SHIPPER')
    for code in a.codes:
        deliver_one(shipper_token, code)


def cmd_ship(a):
    admin_token, _ = login('ADMIN')
    shipper_token, shipper = login('SHIPPER')
    for code in a.codes:
        assign_one(admin_token, shipper['id'], code)
        deliver_one(shipper_token, code)


def cmd_warp(a):
    seconds = parse_duration(a.duration)
    require_anvil()
    before = int(rpc('eth_getBlockByNumber', ['latest', False])['timestamp'], 16)
    rpc('evm_increaseTime', [seconds])
    rpc('evm_mine')
    after = int(rpc('eth_getBlockByNumber', ['latest', False])['timestamp'], 16)
    print(f'Đã tua {seconds} giây (~{seconds / 86400:.2f} ngày). Thời gian chuỗi: {before} -> {after}. '
          'Giao diện đọc server_time từ API nên có thể mất vài giây (tối đa một chu kỳ poll) để đồng hồ cập nhật.')
    print('LƯU Ý: tua giờ không đảo ngược được; muốn chuỗi sạch chạy ./scripts/e2e_stack.sh up.')


def cmd_status(a):
    admin_token, _ = login('ADMIN')
    out = api('GET', f'/api/orders/{a.code}/status', admin_token)
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_reconcile(a):
    admin_token, _ = login('ADMIN')
    out = api('GET', '/api/admin/reconcile?deep=1', admin_token)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if isinstance(out, dict) and out.get('ok') is False:
        raise HelperError('Đối soát LỆCH: số dư contract không khớp tổng các đơn đang mở.')


def cmd_check(a):
    problems = []
    try:
        require_anvil()
        print(f'[ok] Anvil {RPC_URL} (chainId {CHAIN_ID})')
        dep = deployment()
        for name in ('escrow', 'mockUSD'):
            code = rpc('eth_getCode', [dep[name], 'latest'])
            (print(f'[ok] contract {name} {dep[name]}') if code not in ('0x', '0x0')
             else problems.append(f'không có mã contract {name} tại {dep[name]} (Anvil đã khởi động lại? chạy bootstrap --fresh)'))
    except HelperError as e:
        problems.append(str(e))
    status = None
    try:
        status, _ = _http('GET', f'{API_URL}/api/health')
        (print(f'[ok] backend {API_URL}') if status == 200 else problems.append(f'backend trả HTTP {status}'))
    except HelperError as e:
        problems.append(str(e))
    if status == 200:
        for prefix in ('ADMIN', 'SHIPPER'):
            try:
                login(prefix)
                print(f'[ok] đăng nhập {prefix.lower()} ({creds(prefix)[0]})')
            except HelperError as e:
                problems.append(str(e))
    for p in problems:
        print(f'[LỖI] {p}', file=sys.stderr)
    if problems:
        raise HelperError(f'{len(problems)} vấn đề, xem phần DEMO_GUIDE.md mục "Khi có sự cố".')
    print('Sẵn sàng demo.')


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('prepare', help='tạo sẵn Buyer + 2 shop demo').set_defaults(fn=cmd_prepare)
    f = sub.add_parser('fund', help='cấp ETH thử + mUSD cho một ví')
    f.add_argument('address')
    f.add_argument('--usd', type=float, default=1000.0, help='số mUSD (mặc định 1000)')
    f.add_argument('--eth', type=float, default=100.0, help='số ETH thử (mặc định 100)')
    f.set_defaults(fn=cmd_fund)
    for name, fn, h in (('assign', cmd_assign, 'Admin gán đơn cho Shipper'), ('deliver', cmd_deliver, 'Shipper xác nhận giao'),
                        ('ship', cmd_ship, 'gán rồi giao')):
        s = sub.add_parser(name, help=h)
        s.add_argument('codes', nargs='+', metavar='MÃ_ĐƠN')
        s.set_defaults(fn=fn)
    w = sub.add_parser('warp', help='tua giờ Anvil')
    w.add_argument('duration', help='vd 3d, 14d, 2h, 7200s')
    w.set_defaults(fn=cmd_warp)
    st = sub.add_parser('status', help='trạng thái đơn')
    st.add_argument('code')
    st.set_defaults(fn=cmd_status)
    sub.add_parser('reconcile', help='đối soát').set_defaults(fn=cmd_reconcile)
    sub.add_parser('check', help='kiểm nhanh môi trường').set_defaults(fn=cmd_check)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.fn(args)
    except HelperError as e:
        print(f'LỖI: {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
