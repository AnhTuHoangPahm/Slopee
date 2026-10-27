#!/usr/bin/env python3
"""Quét Non-custodial (E-05, AC-09, BR-01): KHÔNG tồn tại khóa riêng / seed phrase của người dùng trong mã nguồn, CSDL và log. Tuần 8, A.
CHỈ ĐỌC (không ghi, không gửi giao dịch). Chỉ dùng thư viện chuẩn; `--db` cần PyMySQL (đã có trong backend/requirements.txt).

Ý tưởng: "khóa riêng của người dùng" chỉ có thể xuất hiện dưới vài dạng nhận diện được. Script tìm đúng các dạng đó và
phân loại mọi phát hiện thành một trong các mức:

  HIGH  lỗi (mã thoát 1): khóa/seed LẠ, khóa thử nằm ở mã chạy thật, PEM, cột/trường nhận khóa, API sinh/nhập khóa người dùng.
  WARN  đáng xem nhưng không phải khóa người dùng thật (vd. khóa thử tự tạo, không thuộc Anvil); không làm hỏng kết quả.
  INFO  hợp lệ, được liệt kê làm bằng chứng: khóa CÔNG KHAI của Anvil dùng làm khóa vận hành hoặc ví thử đúng chỗ cho phép.
  (bỏ)  không in: chuỗi 64 hex không mang ngữ cảnh khóa (tx hash, docHash, digest, vector EIP-712).

Khóa công khai của Anvil KHÔNG được ghi cứng làm "danh sách tin cậy": script tự suy ra chúng từ mnemonic công khai
"test test … junk" (BIP39 + BIP32 m/44'/60'/0'/0/i, chỉ bằng hashlib/hmac). Một khóa hex bất kỳ chỉ được coi là khóa thử khi
nó là một trong các khóa suy ra đó; mọi khóa khác trong ngữ cảnh khóa là HIGH.

    python scripts/scan_no_user_keys.py                   # quét mã nguồn + lược đồ + log trong repo
    python scripts/scan_no_user_keys.py --db              # + quét CSDL đang chạy (DB_HOST/DB_USER/DB_PASSWORD/DB_NAME)
    python scripts/scan_no_user_keys.py --logs a.log b/   # + quét thêm tệp/thư mục log (mặc định chỉ *.log trong repo)
    python scripts/scan_no_user_keys.py --json            # kết quả máy đọc được
    python scripts/scan_no_user_keys.py --report out.md   # ghi báo cáo bằng chứng (Markdown)
    python scripts/scan_no_user_keys.py --self-check      # kiểm chính script: khóa suy ra khớp khóa công khai, bộ nhận diện bắt được mẫu dương

Mã thoát:  0 = sạch (chỉ INFO)  |  1 = có HIGH  |  2 = không chạy được (ví dụ --db mà không kết nối được).
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXIT_OK, EXIT_FOUND, EXIT_ERROR = 0, 1, 2

# --------------------------------------------------------------------------------------------------------------------
# Khóa công khai của Anvil, suy ra từ mnemonic công khai (không tin vào danh sách ghi cứng)
# --------------------------------------------------------------------------------------------------------------------
ANVIL_MNEMONIC = 'test test test test test test test test test test test junk'
_P = 2 ** 256 - 2 ** 32 - 977
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
      0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def _add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and (a[1] + b[1]) % _P == 0:
        return None
    if a == b:
        m = 3 * a[0] * a[0] * pow(2 * a[1], -1, _P) % _P
    else:
        m = (b[1] - a[1]) * pow(b[0] - a[0], -1, _P) % _P
    x = (m * m - a[0] - b[0]) % _P
    return x, (m * (a[0] - x) - a[1]) % _P


def _mul(k, pt=_G):
    out = None
    while k:
        if k & 1:
            out = _add(out, pt)
        pt = _add(pt, pt)
        k >>= 1
    return out


def _compressed(k):
    x, y = _mul(k)
    return bytes([2 + (y & 1)]) + x.to_bytes(32, 'big')


def _ckd(key, chain, index):
    hard = index >= 0x80000000
    data = (b'\x00' + key.to_bytes(32, 'big') if hard else _compressed(key)) + index.to_bytes(4, 'big')
    i = hmac.new(chain, data, hashlib.sha512).digest()
    return (int.from_bytes(i[:32], 'big') + key) % _N, i[32:]


def derive_anvil_keys(count=20):
    """Khóa riêng của `count` tài khoản đầu của mnemonic công khai Anvil (m/44'/60'/0'/0/i), dạng '0x' + 64 hex thường."""
    seed = hashlib.pbkdf2_hmac('sha512', ANVIL_MNEMONIC.encode(), b'mnemonic', 2048)
    i = hmac.new(b'Bitcoin seed', seed, hashlib.sha512).digest()
    key, chain = int.from_bytes(i[:32], 'big'), i[32:]
    for idx in (0x8000002C, 0x8000003C, 0x80000000, 0):
        key, chain = _ckd(key, chain, idx)
    out = []
    for n in range(count):
        k, _ = _ckd(key, chain, n)
        out.append('0x%064x' % k)
    return out


ANVIL_KEYS = derive_anvil_keys()
KEY_INDEX = {k: i for i, k in enumerate(ANVIL_KEYS)}
ROLE_OF_INDEX = {0: 'admin/deployer', 1: 'shipper', 2: 'arbitrator', 3: 'quote signer', 4: 'fee recipient'}
OPERATOR_INDEXES = set(ROLE_OF_INDEX)          # khóa VẬN HÀNH của sàn (SRS 2.2). Từ #5 trở đi là ví thử (buyer/merchant giả lập).

# --------------------------------------------------------------------------------------------------------------------
# Phạm vi: nơi nào được phép chứa khóa thử công khai
# --------------------------------------------------------------------------------------------------------------------
# Log của CHÍNH node Anvil (bootstrap.sh ghi ở gốc repo): banner của Anvil in sẵn 10 khóa công khai nên luôn báo HIGH giả.
# Bỏ qua ở bước duyệt mã nguồn và khi tự tìm log mặc định; truyền rõ `--logs .anvil.log` thì vẫn quét.
NODE_BANNER_LOGS = {'.anvil.log'}
SKIP_DIRS = {'.git', 'node_modules', 'out', 'cache', 'dist', 'build', '__pycache__', '.venv', 'venv', 'broadcast',
             'coverage', '.pytest_cache', 'playwright-report', 'test-results', '.mypy_cache'}
SKIP_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.svg', '.mp3', '.wav', '.ogg', '.pdf', '.zip', '.gz', '.woff',
            '.woff2', '.ttf', '.pyc', '.lock', '.map'}
MAX_BYTES = 2_000_000
SKIP_PREFIXES = ('contracts/lib/', 'frontend/certs/')             # thư viện bên thứ ba do install_contract_deps.sh cài (KHÔNG bỏ frontend/src/lib: đó là mã của nhóm)

# Khóa thử (#5+) chỉ được nằm ở các đường dẫn thử/dev. Khóa vận hành (#0..#4) được thêm chỗ sinh môi trường dev.
TEST_PATHS = ('test/', 'frontend/src/__tests__/', 'frontend/tests/', 'contracts/test/', 'scripts/')
OPERATOR_PATHS = TEST_PATHS + ('contracts/script/', 'backend/.env.web3', '.github/')
DOC_EXT = {'.md', '.html'}                       # tài liệu được phép nhắc khóa công khai khi mô tả cách chạy thử

# Biến môi trường dạng khóa mà backend/script được phép đọc. Mọi tên khác khớp (KEY|SECRET|MNEMONIC|SEED) là HIGH.
ENV_ALLOW = {'QUOTE_SIGNER_KEY', 'ARBITRATOR_KEY', 'SHIPPER_KEY',     # 3 khóa vận hành của sàn (không phải của người dùng)
             'SECRET_KEY',                                           # khóa ký token phiên Flask (itsdangerous), không phải khóa ví
             'DEPLOYER_KEY'}                                         # khóa deploy local của Foundry (Anvil #0)
# Biến chỉ dùng trong script thử/dev (khóa thử công khai của Anvil).
ENV_DEV_ONLY = {'BUYER_KEY', 'MERCHANT_KEY', 'ADMIN_KEY', 'FEE_KEY', 'SIGNER_KEY', 'ANVIL_KEY_0', 'TEST_BUYER_KEY'}

OPERATOR_SETTINGS_FIELDS = {'quote_signer_key', 'arbitrator_key', 'shipper_key'}

# Nơi mã chạy thật được phép tạo Account từ khóa riêng (chỉ cho 3 khóa vận hành nạp từ môi trường).
FROM_KEY_ALLOWED = ('backend/slopee_web3/adapters/env_signer.py',)

# --------------------------------------------------------------------------------------------------------------------
# Bộ nhận diện
# --------------------------------------------------------------------------------------------------------------------
HEX64 = re.compile(r'(?<![0-9A-Za-z])(?:0x)?([0-9a-fA-F]{64})(?![0-9A-Za-z])')
HEX130 = re.compile(r'(?<![0-9A-Za-z])0x[0-9a-fA-F]{130}(?![0-9A-Za-z])')
# Ngữ cảnh "đây là khóa": tên có private/priv key/secret/mnemonic/seed hoặc tên kết thúc bằng key/_KEY được gán giá trị.
KEY_CONTEXT = re.compile(r'(?i)(private|priv[_\s-]?key|secret|mnemonic|seed|passphrase|keystore|[a-z_]*key\b\s*["\']?\s*[:=])')
PEM = re.compile(r'-----BEGIN (?:[A-Z]+ )*PRIVATE KEY(?: BLOCK)?-----')
CTX_WORDS = re.compile(r'(?i)mnemonic|seed|recovery|phrase|backup words|bip-?39')

# Mã chạy thật không được tạo/nhập khóa của người dùng
CODE_PATTERNS = [
    ('PY_ACCOUNT_FROM_KEY', re.compile(r'\bAccount\.(?:from_key|privateKeyToAccount)\b|\.privateKeyToAccount\b')),
    ('PY_ACCOUNT_CREATE', re.compile(r'\bAccount\.(?:create|from_mnemonic|create_with_mnemonic)\b|enable_unaudited_hdwallet_features')),
    ('JS_WALLET_CREATE', re.compile(r'\bWallet\.(?:createRandom|fromPhrase|fromEncryptedJson\w*|fromMnemonic)\b|\bHDNodeWallet\b|\bMnemonic\.(?:fromPhrase|fromEntropy)\b|\bprivateKeyToAccount\b')),
    ('JS_WALLET_NEW', re.compile(r'\bnew\s+(?:ethers\.)?Wallet\s*\(')),
    ('NODE_CUSTODY_RPC', re.compile(r'personal_(?:unlockAccount|importRawKey|newAccount)|\bunlock_account\b|\bimportRawKey\b')),
]
# Tên trường người dùng gửi lên không bao giờ được là khóa / seed
FIELD_NAME = re.compile(r"""['"](?:private[_-]?key|priv[_-]?key|privateKey|mnemonic|seed[_-]?phrase|seedPhrase|secret[_-]?key|recovery[_-]?phrase|keystore|seed)['"]""")
STORAGE_SET = re.compile(r'''(?:local|session)Storage\.setItem\(\s*['"]([^'"]+)['"]''')
BAD_STORAGE_NAME = re.compile(r'(?i)private|mnemonic|seed|secret|key|phrase')
OK_STORAGE = {'token', 'user'}                                   # frontend/src/lib/client.js: token phiên + hồ sơ, KHÔNG phải khóa ví
ENV_NAME_LITERAL = re.compile(r'''['"]([A-Z][A-Z0-9_]*(?:KEY|SECRET|MNEMONIC|SEED)[A-Z0-9_]*)['"]''')
ENV_ASSIGN_LINE = re.compile(r'^\s*(?:export\s+)?([A-Z][A-Z0-9_]*(?:KEY|SECRET|MNEMONIC|SEED)[A-Z0-9_]*)\s*=\s*(\S.*)$')

# Cột DB nguy hiểm theo tên
BAD_COLUMN = re.compile(r'(?i)(^|_)(priv|private|privkey|mnemonic|seed|seedphrase|keystore|secret|passphrase|walletkey|signingkey|pk)(_|$)|private_?key|wallet_?key|signing_?key')
OK_COLUMN = {'setting_key', 'idempotency_key', 'lock_key', 'cache_key', 'token_key'}
TEST_KEY_NAME = re.compile(r'''(?i)['"]?\w*(buyer|merchant|shipper|arbitrator|signer|stranger|outsider|wallet|admin|user|key)\w*['"]?\s*[:=]\s*['"](?:0x)?[0-9a-f]{64}['"]''')
TEST_KEY_NOT_NAME = re.compile(r'(?i)hash|doc|tx|digest|topic|root|sig')
HASHISH_COLUMN = re.compile(r'(?i)(hash|digest|tx|sig|signature|topic|doc|root|nonce|cursor|address|addr|payload|args|raw|data|log)')


@dataclass
class Finding:
    level: str            # HIGH | WARN | INFO
    rule: str
    where: str            # đường dẫn:dòng, hoặc bảng.cột
    detail: str
    sample: str = ''      # đã che: không bao giờ in cả khóa

    def line(self):
        return f"[{self.level}] {self.rule}  {self.where}  {self.detail}" + (f"  ({self.sample})" if self.sample else '')


@dataclass
class Report:
    findings: list = field(default_factory=list)
    scanned: Counter = field(default_factory=Counter)        # số mục đã quét theo nguồn
    notes: list = field(default_factory=list)

    def add(self, level, rule, where, detail, sample=''):
        self.findings.append(Finding(level, rule, where, detail, sample))

    @property
    def high(self):
        return [f for f in self.findings if f.level == 'HIGH']

    @property
    def warn(self):
        return [f for f in self.findings if f.level == 'WARN']

    @property
    def info(self):
        return [f for f in self.findings if f.level == 'INFO']


def mask(s):
    s = s.strip()
    return s[:6] + '…' + s[-4:] if len(s) > 14 else s[:3] + '…'


def norm_key(h):
    return '0x' + h.lower()


def classify_known_key(key, rel):
    """Một khóa hex thuộc ANVIL_KEYS xuất hiện ở `rel`: INFO nếu đúng chỗ cho phép, ngược lại HIGH. Trả (level, mô tả)."""
    idx = KEY_INDEX[key]
    role = ROLE_OF_INDEX.get(idx, 'ví thử người dùng (buyer/merchant giả lập)')
    allowed = OPERATOR_PATHS if idx in OPERATOR_INDEXES else TEST_PATHS
    ext = Path(rel).suffix.lower()
    if rel.startswith(allowed) or ext in DOC_EXT or '/__tests__/' in rel:
        return 'INFO', f'khóa công khai Anvil #{idx} ({role})'
    return 'HIGH', f'khóa công khai Anvil #{idx} ({role}) nằm ở mã chạy thật, ngoài phạm vi cho phép'


# --------------------------------------------------------------------------------------------------------------------
# Quét văn bản (dùng chung cho mã nguồn, log, giá trị CSDL)
# --------------------------------------------------------------------------------------------------------------------
def scan_text_secrets(text, where_fn, rel, report, *, kind='file'):
    """Tìm khóa hex, PEM, mnemonic trong `text`. `where_fn(lineno)` -> nhãn vị trí. `rel` dùng để xét phạm vi cho phép."""
    for no, line in enumerate(text.splitlines(), 1):
        if PEM.search(line):
            report.add('HIGH', 'PEM_PRIVATE_KEY', where_fn(no), 'khối PEM khóa riêng')
        for m in HEX64.finditer(line):
            key = norm_key(m.group(1))
            if key in KEY_INDEX:
                level, why = classify_known_key(key, rel) if kind == 'file' else ('HIGH', 'khóa thử công khai nằm trong dữ liệu chạy thật')
                report.add(level, 'KNOWN_DEV_KEY' if level == 'INFO' else 'DEV_KEY_OUT_OF_SCOPE', where_fn(no), why, mask(key))
            elif kind == 'file' and is_test_like(rel) and TEST_KEY_NAME.search(line) and not TEST_KEY_NOT_NAME.search(line):
                report.add('WARN', 'TEST_KEY_NOT_ANVIL', where_fn(no), 'khóa trong tệp thử KHÔNG nằm trong 20 tài khoản đầu của mnemonic Anvil (khóa thử tự tạo?)', mask(key))
            elif KEY_CONTEXT.search(line):
                report.add('HIGH', 'UNKNOWN_PRIVATE_KEY', where_fn(no), 'chuỗi 64 hex trong ngữ cảnh khóa, KHÔNG phải khóa thử công khai', mask(key))
        for w in _mnemonic_hits(line):
            known = w == ANVIL_MNEMONIC
            report.add('INFO' if known else 'HIGH', 'KNOWN_DEV_MNEMONIC' if known else 'MNEMONIC', where_fn(no),
                       'mnemonic công khai của Anvil (chỉ dùng thử)' if known else 'cụm từ khôi phục', mask(w))
        if kind == 'log' and HEX130.search(line):
            report.add('HIGH', 'UNREDACTED_SIGNATURE', where_fn(no), 'chữ ký 65 byte chưa bị che trong log (SDD 5.6)')


_QUOTED_WORDS = re.compile(r"""["'`]((?:[a-z]{3,8} ){11,23}[a-z]{3,8})["'`]""")
_ASSIGNED_WORDS = re.compile(r"""[=:]\s*((?:[a-z]{3,8} ){11,23}[a-z]{3,8})\s*$""")


def _mnemonic_hits(line):
    """Cụm 12/15/18/21/24 từ chữ thường đặt trong dấu nháy (hoặc gán ở cuối dòng) trên dòng có từ ngữ cảnh mnemonic/seed/phrase.
    Không có danh sách từ BIP39 offline nên đòi cả hình dạng lẫn ngữ cảnh, để văn xuôi trong chú thích không bị báo nhầm."""
    if ANVIL_MNEMONIC in line:
        yield ANVIL_MNEMONIC
    if not CTX_WORDS.search(line):
        return
    for m in list(_QUOTED_WORDS.finditer(line)) + list(_ASSIGNED_WORDS.finditer(line)):
        phrase = m.group(1)
        if len(phrase.split()) in (12, 15, 18, 21, 24) and phrase != ANVIL_MNEMONIC:
            yield phrase


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if fn in NODE_BANNER_LOGS or p.suffix.lower() in SKIP_EXT or p.relative_to(root).as_posix().startswith(SKIP_PREFIXES):
                continue
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
                data = p.read_bytes()
            except OSError:
                continue
            if b'\x00' in data[:4096]:
                continue
            yield p, data.decode('utf-8', errors='replace')


def is_test_like(rel):
    return rel.startswith(TEST_PATHS) or '/__tests__/' in rel or '/tests/' in rel or rel.endswith(('.test.js', '.test.jsx', '.spec.js'))


# --------------------------------------------------------------------------------------------------------------------
# 1) Quét mã nguồn
# --------------------------------------------------------------------------------------------------------------------
def scan_source(root=ROOT, report=None):
    report = report or Report()
    root = Path(root)
    for p, text in iter_files(root):
        rel = p.relative_to(root).as_posix()
        if rel == 'scripts/scan_no_user_keys.py' or rel == 'test/unit_test/test_w8_non_custodial.py':
            continue                                                   # chính script/test chứa mẫu dương cố ý
        report.scanned['source files'] += 1
        scan_text_secrets(text, lambda n, rel=rel: f'{rel}:{n}', rel, report)
        _scan_code_rules(rel, text, report)
        _scan_env_names(rel, text, report)
    _check_operator_settings(root, report)
    _check_gitignore(root, report)
    return report


def _scan_code_rules(rel, text, report):
    code_ext = Path(rel).suffix in {'.py', '.js', '.jsx', '.ts', '.tsx'}
    runtime = code_ext and not is_test_like(rel) and not rel.startswith(('scripts/', 'contracts/'))
    if not runtime:
        return
    for no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(('#', '//', '*', '/*')):
            continue
        for name, pat in CODE_PATTERNS:
            if pat.search(line):
                if name == 'PY_ACCOUNT_FROM_KEY' and rel in FROM_KEY_ALLOWED:
                    report.add('INFO', 'OPERATOR_KEY_LOAD', f'{rel}:{no}', 'Account.from_key chỉ cho 3 khóa vận hành nạp từ môi trường')
                else:
                    report.add('HIGH', name, f'{rel}:{no}', 'mã chạy thật tạo/nhập khóa ví: vi phạm Non-custodial', stripped[:60])
        if rel.startswith('backend/') and FIELD_NAME.search(line):
            report.add('HIGH', 'KEY_FIELD_IN_API', f'{rel}:{no}', 'backend nhận/ghi trường tên khóa riêng/seed', stripped[:60])
        for m in STORAGE_SET.finditer(line):
            name = m.group(1)
            if name not in OK_STORAGE and BAD_STORAGE_NAME.search(name):
                report.add('HIGH', 'KEY_IN_BROWSER_STORAGE', f'{rel}:{no}', f'lưu "{name}" vào localStorage/sessionStorage')


def _scan_env_names(rel, text, report):
    ext = Path(rel).suffix.lower()
    if ext in DOC_EXT or ext in {'.json', '.js', '.jsx', '.sol', '.sql', '.css'}:
        return
    in_dev = rel.startswith(('test/', 'contracts/', 'scripts/')) or '/__tests__/' in rel
    for no, line in enumerate(text.splitlines(), 1):
        names = []
        m = ENV_ASSIGN_LINE.match(line)
        if m and ext in {'.sh', '.yml', '.yaml', '.example', '.web3', '.env', ''}:
            names.append(m.group(1))
        if ext in {'.py', '.sh'}:
            names += ENV_NAME_LITERAL.findall(line)
        for name in names:
            if name in ENV_ALLOW or (name in ENV_DEV_ONLY and in_dev):
                continue
            report.add('HIGH', 'UNKNOWN_KEY_ENV', f'{rel}:{no}', f'biến môi trường dạng khóa ngoài danh sách vận hành: {name}')


def _check_operator_settings(root, report):
    """Backend chỉ được nắm đúng 3 khóa vận hành: cấu hình Web3Settings không có trường khóa nào khác."""
    f = Path(root) / 'backend/slopee_web3/settings.py'
    if not f.exists():
        report.notes.append('Không thấy backend/slopee_web3/settings.py: bỏ qua kiểm tra trường khóa.')
        return
    fields = set(re.findall(r'^\s+([a-z_]*(?:key|secret|mnemonic|seed)[a-z_]*)\s*:', f.read_text(encoding='utf-8'), re.M))
    extra = fields - OPERATOR_SETTINGS_FIELDS
    if extra:
        report.add('HIGH', 'EXTRA_KEY_SETTING', 'backend/slopee_web3/settings.py', f'cấu hình giữ thêm trường khóa: {sorted(extra)}')
    else:
        report.add('INFO', 'ONLY_OPERATOR_KEYS', 'backend/slopee_web3/settings.py', f'backend chỉ giữ {len(fields)} khóa vận hành: {sorted(fields)}')


def _check_gitignore(root, report):
    gi = Path(root) / '.gitignore'
    if not gi.exists():
        return
    txt = gi.read_text(encoding='utf-8', errors='replace')
    if 'backend/.env.web3' not in txt:
        report.add('HIGH', 'ENV_NOT_IGNORED', '.gitignore', 'backend/.env.web3 chứa khóa vận hành nhưng không bị .gitignore')
    if not re.search(r'^\.env\s*$', txt, re.M):
        report.add('HIGH', 'ENV_NOT_IGNORED', '.gitignore', '.env không bị .gitignore')


# --------------------------------------------------------------------------------------------------------------------
# 2) Quét lược đồ (schema.sql + migrations)
# --------------------------------------------------------------------------------------------------------------------
COL_DEF = re.compile(r'^\s*`?([A-Za-z_][A-Za-z0-9_]*)`?\s+(?:TINYINT|SMALLINT|INT|BIGINT|DECIMAL|VARCHAR|CHAR|TEXT|MEDIUMTEXT|LONGTEXT|BLOB|JSON|DATETIME|TIMESTAMP|DATE|ENUM|BOOLEAN|BIT|FLOAT|DOUBLE|VARBINARY|BINARY)\b', re.I)
ADD_COL = re.compile(r'(?i)ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([A-Za-z_][A-Za-z0-9_]*)`?')


def column_is_bad(name):
    return name not in OK_COLUMN and bool(BAD_COLUMN.search(name))


def scan_schema(root=ROOT, report=None):
    report = report or Report()
    root = Path(root)
    mig = root / 'backend/migrations'
    files = [root / 'backend/schema.sql'] + (sorted(mig.glob('*.sql')) + sorted(mig.glob('*.py')) if mig.exists() else [])
    for f in files:
        if not f.exists():
            continue
        rel = f.relative_to(root).as_posix()
        for no, line in enumerate(f.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            report.scanned['schema lines'] += 1
            names = []
            m = COL_DEF.match(line)
            if m:
                names.append(m.group(1))
            names += ADD_COL.findall(line)
            if f.suffix == '.py':
                names += [x for x in re.findall(r'''['"]([A-Za-z_][A-Za-z0-9_]*)['"]''', line)]
            for n in names:
                if column_is_bad(n):
                    report.add('HIGH', 'KEY_COLUMN', f'{rel}:{no}', f'cột "{n}" có tên giống nơi chứa khóa/seed')
    # Bằng chứng tích cực: bảng ví chỉ chứa địa chỉ công khai
    wl = _table_columns(root / 'backend/schema.sql', 'user_wallets')
    if wl:
        report.add('INFO', 'WALLET_TABLE_PUBLIC_ONLY', 'user_wallets', f'cột: {", ".join(wl)}')
    return report


def _table_columns(path, table):
    if not Path(path).exists():
        return []
    txt = Path(path).read_text(encoding='utf-8', errors='replace')
    m = re.search(r'CREATE TABLE(?: IF NOT EXISTS)?\s+`?%s`?\s*\((.*?)\n\)' % re.escape(table), txt, re.S | re.I)
    if not m:
        return []
    return [c.group(1) for ln in m.group(1).splitlines() if (c := COL_DEF.match(ln))]


# --------------------------------------------------------------------------------------------------------------------
# 3) Quét log
# --------------------------------------------------------------------------------------------------------------------
def scan_logs(paths=None, root=ROOT, report=None):
    report = report or Report()
    root = Path(root)
    targets = []
    for p in (paths or []):
        p = Path(p)
        targets += [x for x in p.rglob('*') if x.is_file()] if p.is_dir() else [p]
    if not paths:                                                      # mặc định: mọi *.log và thư mục logs/ trong repo
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            targets += [Path(dirpath) / f for f in filenames
                        if (f.endswith('.log') and f not in NODE_BANNER_LOGS) or Path(dirpath).name == 'logs']
    for t in targets:
        try:
            text = t.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        report.scanned['log files'] += 1
        rel = t.as_posix()
        scan_text_secrets(text, lambda n, rel=rel: f'{rel}:{n}', rel, report, kind='log')
    return report


# --------------------------------------------------------------------------------------------------------------------
# 4) Quét CSDL đang chạy
# --------------------------------------------------------------------------------------------------------------------
TEXT_TYPES = {'char', 'varchar', 'tinytext', 'text', 'mediumtext', 'longtext', 'json', 'blob', 'mediumblob', 'longblob', 'varbinary', 'binary'}


def _hex64_under_hashish_json_keys(val):
    """Giá trị 64 hex nằm dưới một TRƯỜNG JSON có tên kiểu hash (docHash, txHash...): vd `order_quotes.quote_json` chứa `docHash` (bytes32 hợp lệ).
    Chỉ xét khi `val` là JSON hợp lệ; tên trường kiểu khóa (`private_key`...) vẫn bị `KEY_FIELD_IN_JSON` bắt riêng."""
    if not val.lstrip().startswith(('{', '[')):
        return set()
    try:
        doc = json.loads(val)
    except ValueError:
        return set()
    ok = set()

    def walk(node, key=''):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, str(k))
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, str) and HASHISH_COLUMN.search(key) and not column_is_bad(key):
            for m in HEX64.finditer(node):
                ok.add(norm_key(m.group(1)))
    walk(doc)
    return ok


def scan_database(conn, schema, report=None, *, row_limit=100_000):
    """`conn`: kết nối DB-API (PyMySQL hoặc giả lập có cursor()). Quét tên cột + giá trị của mọi cột chữ trong `schema`."""
    report = report or Report()
    cur = conn.cursor()
    cur.execute("SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s", (schema,))
    cols = [(_g(r, 'TABLE_NAME', 0), _g(r, 'COLUMN_NAME', 1), str(_g(r, 'DATA_TYPE', 2)).lower()) for r in cur.fetchall()]
    report.scanned['db tables'] += len({c[0] for c in cols})
    report.scanned['db columns'] += len(cols)
    for table, col, dtype in cols:
        if column_is_bad(col):
            report.add('HIGH', 'KEY_COLUMN', f'{table}.{col}', 'tên cột giống nơi chứa khóa/seed (CSDL đang chạy)')
        if dtype not in TEXT_TYPES:
            continue
        cur.execute(f"SELECT `{col}` FROM `{table}` WHERE `{col}` IS NOT NULL LIMIT {int(row_limit)}")
        for row in cur.fetchall():
            val = _g(row, col, 0)
            if isinstance(val, (bytes, bytearray)):
                val = bytes(val).decode('utf-8', errors='replace')
            val = str(val)
            report.scanned['db values'] += 1
            where = f'{table}.{col}'
            hash_fields = _hex64_under_hashish_json_keys(val)
            for m in HEX64.finditer(val):
                key = norm_key(m.group(1))
                if key in KEY_INDEX:
                    report.add('HIGH', 'DEV_KEY_IN_DB', where, 'khóa thử công khai nằm trong CSDL', mask(key))
                elif not HASHISH_COLUMN.search(col) and key not in hash_fields:
                    report.add('HIGH', 'HEX64_IN_NON_HASH_COLUMN', where, 'chuỗi 64 hex ở cột không phải hash/chữ ký', mask(key))
            if PEM.search(val):
                report.add('HIGH', 'PEM_PRIVATE_KEY', where, 'khối PEM khóa riêng trong CSDL')
            for w in _mnemonic_hits(val + ' mnemonic'):
                report.add('HIGH', 'MNEMONIC', where, 'cụm từ khôi phục trong CSDL', mask(w))
            if dtype == 'json' or val.startswith(('{', '[')):
                for k in re.findall(r'"([A-Za-z_]+)"\s*:', val):
                    if column_is_bad(k):
                        report.add('HIGH', 'KEY_FIELD_IN_JSON', where, f'JSON có trường "{k}"')
    return report


def _g(row, name, idx):
    if isinstance(row, dict):
        return row.get(name, row.get(name.lower(), row.get(name.upper())))
    return row[idx]


def connect_db():
    try:
        import pymysql
    except ImportError as e:
        raise RuntimeError('Thiếu PyMySQL: pip install -r backend/requirements.txt') from e
    env = os.environ
    schema = env.get('DB_NAME', 'slopee_db')
    conn = pymysql.connect(host=env.get('DB_HOST', 'localhost'), user=env.get('DB_USER', 'root'), password=env.get('DB_PASSWORD', ''), database=schema)
    return conn, schema


# --------------------------------------------------------------------------------------------------------------------
# Tự kiểm
# --------------------------------------------------------------------------------------------------------------------
def self_check():
    """Trả danh sách lỗi (rỗng = ổn). Chứng minh bộ nhận diện không "câm" khi repo sạch (có mẫu dương) và không báo nhầm."""
    errs = []
    if ANVIL_KEYS[0] != '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80':
        errs.append('khóa suy ra #0 không khớp khóa công khai của Anvil')
    if ANVIL_KEYS[1] != '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d':
        errs.append('khóa suy ra #1 không khớp')
    probes = {
        'UNKNOWN_PRIVATE_KEY': 'private_key = "0x' + 'ab' * 32 + '"',
        'PEM_PRIVATE_KEY': '-----BEGIN EC PRIVATE KEY-----',
        'MNEMONIC': 'const mnemonic = "abandon ability able about above absent absorb abstract absurd abuse access accident"',
        'DEV_KEY_OUT_OF_SCOPE': 'x = "' + ANVIL_KEYS[5] + '"',
    }
    for rule, text in probes.items():
        r = Report()
        scan_text_secrets(text, lambda n: f'probe:{n}', 'backend/app.py', r)
        if rule not in {f.rule for f in r.high}:
            errs.append(f'bộ nhận diện không bắt được mẫu {rule}')
    r = Report()
    scan_text_secrets('tx = "0x' + 'cd' * 32 + '"  # tx hash, docHash', lambda n: f'p:{n}', 'backend/app.py', r)
    if r.findings:
        errs.append('chuỗi 64 hex không có ngữ cảnh khóa (tx hash) bị báo nhầm')
    return errs


# --------------------------------------------------------------------------------------------------------------------
# Báo cáo + CLI
# --------------------------------------------------------------------------------------------------------------------
def render_markdown(report, mode_label):
    lines = ['# Báo cáo quét Non-custodial (E-05 / AC-09)', '', f'- Phạm vi: {mode_label}',
             '- Đã quét: ' + (', '.join(f'{v} {k}' for k, v in sorted(report.scanned.items())) or '(không có)'),
             f'- Kết quả: **{"ĐẠT" if not report.high else "KHÔNG ĐẠT"}** ({len(report.high)} HIGH, {len(report.warn)} WARN, {len(report.info)} INFO)', '']
    if report.high:
        lines += ['## Phát hiện HIGH', ''] + [f'- `{f.rule}` `{f.where}`: {f.detail} {f.sample}' for f in report.high] + ['']
    if report.warn:
        lines += ['## Cảnh báo (WARN, không làm hỏng kết quả)', ''] + [f'- `{f.rule}` `{f.where}`: {f.detail} {f.sample}' for f in report.warn] + ['']
    groups = Counter((f.rule, f.detail) for f in report.info)
    lines += ['## Bằng chứng (INFO)', '']
    lines += [f'- `{rule}` ×{n}: {detail}' for (rule, detail), n in sorted(groups.items())]
    if report.notes:
        lines += ['', '## Ghi chú', ''] + [f'- {n}' for n in report.notes]
    return '\n'.join(lines) + '\n'


def main(argv=None, *, out=None, err=None):
    out, err = out or sys.stdout, err or sys.stderr
    ap = argparse.ArgumentParser(description='Quét Non-custodial: không có khóa riêng/seed người dùng (E-05, AC-09).')
    ap.add_argument('--root', default=str(ROOT))
    ap.add_argument('--db', action='store_true', help='quét CSDL đang chạy (DB_HOST/DB_USER/DB_PASSWORD/DB_NAME)')
    ap.add_argument('--logs', nargs='*', default=None, help='tệp/thư mục log cần quét thêm')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--report', help='ghi báo cáo Markdown')
    ap.add_argument('--self-check', action='store_true')
    ap.add_argument('--verbose', '-v', action='store_true', help='in cả INFO')
    a = ap.parse_args(argv)

    if a.self_check:
        errs = self_check()
        for e in errs:
            print('SELF-CHECK LỖI:', e, file=err)
        print('self-check:', 'ĐẠT' if not errs else 'KHÔNG ĐẠT', file=out)
        return EXIT_OK if not errs else EXIT_FOUND

    report = Report()
    scan_source(a.root, report)
    scan_schema(a.root, report)
    scan_logs(a.logs, a.root, report)
    label = 'mã nguồn + lược đồ + log'
    if a.db:
        try:
            conn, schema = connect_db()
        except Exception as e:                                             # noqa: BLE001 - mọi lỗi kết nối đều là "không chạy được"
            print(f'Không kết nối được CSDL: {e}', file=err)
            return EXIT_ERROR
        try:
            scan_database(conn, schema, report)
        finally:
            conn.close()
        label += f' + CSDL `{schema}`'

    if a.report:
        Path(a.report).write_text(render_markdown(report, label), encoding='utf-8')
    if a.json:
        print(json.dumps({'ok': not report.high, 'scanned': dict(report.scanned), 'high': [asdict(f) for f in report.high], 'warn': [asdict(f) for f in report.warn],
                          'info': [asdict(f) for f in report.info], 'notes': report.notes}, ensure_ascii=False, indent=2), file=out)
    else:
        for f in report.high:
            print(f.line(), file=out)
        for f in report.warn:
            print(f.line(), file=out)
        if a.verbose:
            for f in report.info:
                print(f.line(), file=out)
        scanned = ', '.join(f'{v} {k}' for k, v in sorted(report.scanned.items()))
        print(f'\nĐã quét: {scanned}', file=out)
        print(f'KẾT QUẢ: {"KHỚP NGUYÊN TẮC NON-CUSTODIAL" if not report.high else "VI PHẠM"}  ({len(report.high)} HIGH, {len(report.warn)} WARN, {len(report.info)} INFO)', file=out)
    return EXIT_FOUND if report.high else EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
