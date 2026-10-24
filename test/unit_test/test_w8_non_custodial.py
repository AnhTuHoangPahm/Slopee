"""Tuần 8 [A] E-05 / AC-09 (BR-01): quét Non-custodial. `scripts/scan_no_user_keys.py` phải
(1) báo SẠCH trên repo thật, (2) THỰC SỰ bắt được từng dạng rò khóa (mẫu dương) và (3) không báo nhầm tx hash/docHash.
Không cần MySQL/Anvil. Test (2) quan trọng hơn (1): một bộ quét "câm" cũng báo sạch."""
import importlib.util
import io
import logging
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


scan = _load('scan_no_user_keys', ROOT / 'scripts' / 'scan_no_user_keys.py')
redaction = _load('logging_filter_w8', ROOT / 'backend' / 'slopee_web3' / 'adapters' / 'logging_filter.py')

UNKNOWN_KEY = '0x' + 'ab' * 32            # không thuộc Anvil


def make_repo(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
    return tmp_path


def run(tmp_path, files):
    r = scan.Report()
    make_repo(tmp_path, files)
    scan.scan_source(tmp_path, r)
    scan.scan_schema(tmp_path, r)
    scan.scan_logs(None, tmp_path, r)
    return r


def rules(report):
    return {f.rule for f in report.high}


# ------------------------------------------------------------------------------------------ nền tảng của bộ quét
def test_self_check_passes():
    assert scan.self_check() == []


def test_anvil_keys_derived_from_public_mnemonic_match_repo_operator_keys():
    """Danh sách tin cậy được SUY RA từ mnemonic công khai, không ghi cứng: khóa vận hành trong bootstrap.sh phải nằm trong đó."""
    boot = (ROOT / 'scripts' / 'bootstrap.sh').read_text(encoding='utf-8')
    for name, idx in (('QUOTE_SIGNER_KEY', 3), ('ARBITRATOR_KEY', 2), ('SHIPPER_KEY', 1)):
        assert f'{name}={scan.ANVIL_KEYS[idx]}' in boot
    assert scan.ANVIL_KEYS[0] == '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'
    assert len(set(scan.ANVIL_KEYS)) == len(scan.ANVIL_KEYS) == 20


# ------------------------------------------------------------------------------------------ repo thật
def test_real_repo_has_no_user_private_keys():
    r = scan.Report()
    scan.scan_source(ROOT, r)
    scan.scan_schema(ROOT, r)
    scan.scan_logs(None, ROOT, r)
    assert [f.line() for f in r.high] == []
    assert r.scanned['source files'] > 100                      # quét thật, không phải thư mục rỗng
    # bằng chứng tích cực
    assert any(f.rule == 'ONLY_OPERATOR_KEYS' for f in r.info)
    assert any(f.rule == 'WALLET_TABLE_PUBLIC_ONLY' for f in r.info)
    assert any(f.rule == 'OPERATOR_KEY_LOAD' for f in r.info)


def test_wallet_table_stores_public_address_only():
    cols = scan._table_columns(ROOT / 'backend' / 'schema.sql', 'user_wallets')
    assert 'address' in cols
    assert not [c for c in cols if scan.column_is_bad(c)]


def test_only_three_operator_keys_are_loadable_by_backend():
    txt = (ROOT / 'backend' / 'slopee_web3' / 'settings.py').read_text(encoding='utf-8')
    import re
    assert set(re.findall(r'^\s+([a-z_]*key[a-z_]*)\s*:', txt, re.M)) == scan.OPERATOR_SETTINGS_FIELDS


# ------------------------------------------------------------------------------------------ mẫu dương: phải bắt được
@pytest.mark.parametrize('files, expected', [
    ({'backend/x.py': f'private_key = "{UNKNOWN_KEY}"\n'}, 'UNKNOWN_PRIVATE_KEY'),
    ({'frontend/src/a.js': f'const secret = "{UNKNOWN_KEY}";\n'}, 'UNKNOWN_PRIVATE_KEY'),
    ({'backend/k.pem': '-----BEGIN RSA PRIVATE KEY-----\nMIIB\n'}, 'PEM_PRIVATE_KEY'),
    ({'backend/config2.py': f'KEY = "{scan.ANVIL_KEYS[5]}"\n'}, 'DEV_KEY_OUT_OF_SCOPE'),                      # khóa thử ở mã chạy thật
    ({'frontend/src/lib/w.js': f'export const k = "{scan.ANVIL_KEYS[1]}";\n'}, 'DEV_KEY_OUT_OF_SCOPE'),
    ({'backend/svc.py': 'acct = Account.create()\n'}, 'PY_ACCOUNT_CREATE'),
    ({'backend/svc.py': 'acct = Account.from_key(user_key)\n'}, 'PY_ACCOUNT_FROM_KEY'),                       # chỉ env_signer.py được phép
    ({'backend/svc.py': 'w3.geth.personal.unlock_account(a, p)\n'}, 'NODE_CUSTODY_RPC'),
    ({'frontend/src/lib/w.js': 'const w = ethers.Wallet.createRandom();\n'}, 'JS_WALLET_CREATE'),
    ({'frontend/src/lib/w.js': 'const w = new Wallet(pk, provider);\n'}, 'JS_WALLET_NEW'),
    ({'frontend/src/lib/w.js': 'sessionStorage.setItem("privateKey", pk);\n'}, 'KEY_IN_BROWSER_STORAGE'),
    ({'frontend/src/lib/w.js': 'localStorage.setItem("wallet_seed", s);\n'}, 'KEY_IN_BROWSER_STORAGE'),
    ({'backend/routes/w.py': 'pk = body.get("private_key")\n'}, 'KEY_FIELD_IN_API'),
    ({'backend/routes/w.py': "m = data['mnemonic']\n"}, 'KEY_FIELD_IN_API'),
    ({'backend/schema.sql': 'CREATE TABLE t (\n    id INT,\n    private_key VARCHAR(66)\n);\n'}, 'KEY_COLUMN'),
    ({'backend/schema.sql': 'CREATE TABLE t (\n    id INT,\n    mnemonic TEXT\n);\n'}, 'KEY_COLUMN'),
    ({'backend/migrations/0099_x.sql': 'ALTER TABLE users ADD COLUMN seed_phrase TEXT;\n'}, 'KEY_COLUMN'),
    ({'backend/svc.py': 'import os\nk = os.environ["USER_WALLET_KEY"]\n'}, 'UNKNOWN_KEY_ENV'),
    ({'scripts/run.sh': 'WALLET_SECRET=abc\n'}, 'UNKNOWN_KEY_ENV'),
    ({'docs/note.md': 'mnemonic = "legal winner thank year wave sausage worth useful legal winner thank yellow"\n'}, 'MNEMONIC'),
    ({'.gitignore': '.env\n'}, 'ENV_NOT_IGNORED'),                                                          # thiếu backend/.env.web3
    ({'backend/slopee_web3/settings.py': 'class S:\n    quote_signer_key: str = ""\n    buyer_key: str = ""\n'}, 'EXTRA_KEY_SETTING'),
    ({'app/server.log': 'INFO signed 0x' + 'ab' * 65 + '\n'}, 'UNREDACTED_SIGNATURE'),
])
def test_scanner_catches_each_leak_shape(tmp_path, files, expected):
    r = run(tmp_path, files)
    assert expected in rules(r), [f.line() for f in r.findings]


# ------------------------------------------------------------------------------------------ mẫu âm: không báo nhầm
@pytest.mark.parametrize('files', [
    {'backend/a.py': f'tx_hash = "0x{"cd" * 32}"\n'},                                                       # tx hash
    {'backend/a.py': f'doc_hash = "0x{"cd" * 32}"  # docHash\n'},
    {'frontend/src/__tests__/a.test.js': f'const buyer = "{scan.ANVIL_KEYS[5]}";\n'},                       # khóa thử đúng chỗ
    {'test/w.py': f'KEYS = {{"buyer": "{scan.ANVIL_KEYS[5]}"}}\n'},
    {'scripts/bootstrap.sh': f'SHIPPER_KEY={scan.ANVIL_KEYS[1]}\n'},                                         # khóa vận hành, tệp bootstrap
    {'backend/slopee_web3/adapters/env_signer.py': 'a = Account.from_key(key)\n'},                          # nơi duy nhất được phép
    {'backend/auth_utils.py': "key = os.environ.get('SECRET_KEY')\n"},                                     # khóa ký phiên Flask
    {'frontend/src/lib/client.js': 'sessionStorage.setItem(TOKEN_KEY, token);\nsessionStorage.setItem("token", t);\n'},
    {'backend/a.py': '# an old comment: seed the database with fixtures and run the migration once before the demo today\n'},
    {'backend/schema.sql': 'CREATE TABLE t (\n    id INT,\n    setting_key VARCHAR(64)\n);\n'},
    {'docs/guide.md': f'Khóa công khai của Anvil #5: {scan.ANVIL_KEYS[5]}\n'},
    {'.gitignore': '.env\nbackend/.env.web3\n'},
])
def test_scanner_does_not_flag_legit_things(tmp_path, files):
    r = run(tmp_path, files)
    assert rules(r) == set(), [f.line() for f in r.high]


def test_node_modules_and_lib_are_skipped(tmp_path):
    r = run(tmp_path, {'frontend/node_modules/x/index.js': f'const secret = "{UNKNOWN_KEY}";\n',
                       'contracts/lib/oz/a.sol': f'// private key {UNKNOWN_KEY}\n'})
    assert rules(r) == set()


def test_reports_never_contain_the_full_key(tmp_path):
    r = run(tmp_path, {'backend/x.py': f'private_key = "{UNKNOWN_KEY}"\n'})
    assert all(UNKNOWN_KEY[2:] not in f.line() for f in r.findings)


# ------------------------------------------------------------------------------------------ CSDL (giả lập con trỏ)
class FakeCursor:
    def __init__(self, columns, values):
        self.columns, self.values, self.last = columns, values, None

    def execute(self, sql, params=None):
        self.last = sql

    def fetchall(self):
        if 'information_schema' in self.last:
            return [{'TABLE_NAME': t, 'COLUMN_NAME': c, 'DATA_TYPE': d} for t, c, d in self.columns]
        col = self.last.split('`')[1]
        table = self.last.split('`')[3]
        return [{col: v} for v in self.values.get((table, col), [])]


class FakeConn:
    def __init__(self, columns, values):
        self._cur = FakeCursor(columns, values)

    def cursor(self):
        return self._cur


GOOD_COLUMNS = [('user_wallets', 'address', 'char'), ('order_web3', 'tx_hash', 'char'), ('chain_events', 'payload', 'json'),
                ('users', 'id', 'int'), ('dispute_signatures', 'signature', 'varchar')]


def test_db_scan_clean_with_hashes_and_signatures():
    values = {('user_wallets', 'address'): ['0x' + '12' * 20], ('order_web3', 'tx_hash'): ['0x' + 'cd' * 32],
              ('chain_events', 'payload'): ['{"orderId": 1, "docHash": "0x' + 'ee' * 32 + '"}'],
              ('dispute_signatures', 'signature'): ['0x' + 'ab' * 65]}
    r = scan.scan_database(FakeConn(GOOD_COLUMNS, values), 'slopee_db')
    assert r.high == []
    assert r.scanned['db columns'] == 5 and r.scanned['db values'] == 4


@pytest.mark.parametrize('columns, values, expected', [
    (GOOD_COLUMNS + [('users', 'private_key', 'varchar')], {}, 'KEY_COLUMN'),
    (GOOD_COLUMNS + [('users', 'bio', 'text')], {('users', 'bio'): [scan.ANVIL_KEYS[5]]}, 'DEV_KEY_IN_DB'),
    (GOOD_COLUMNS + [('users', 'bio', 'text')], {('users', 'bio'): ['0x' + 'ab' * 32]}, 'HEX64_IN_NON_HASH_COLUMN'),
    (GOOD_COLUMNS + [('users', 'bio', 'text')], {('users', 'bio'): ['-----BEGIN EC PRIVATE KEY-----']}, 'PEM_PRIVATE_KEY'),
    (GOOD_COLUMNS + [('users', 'bio', 'text')], {('users', 'bio'): ['"legal winner thank year wave sausage worth useful legal winner thank yellow"']}, 'MNEMONIC'),
    (GOOD_COLUMNS, {('chain_events', 'payload'): ['{"private_key": "x"}']}, 'KEY_FIELD_IN_JSON'),
])
def test_db_scan_catches_leaks(columns, values, expected):
    r = scan.scan_database(FakeConn(columns, values), 'slopee_db')
    assert expected in rules(r), [f.line() for f in r.findings]


# ------------------------------------------------------------------------------------------ CLI
def test_cli_exit_codes(tmp_path):
    out, err = io.StringIO(), io.StringIO()
    clean = make_repo(tmp_path / 'clean', {'backend/a.py': 'x = 1\n'})
    assert scan.main(['--root', str(clean)], out=out, err=err) == scan.EXIT_OK
    dirty = make_repo(tmp_path / 'dirty', {'backend/a.py': f'private_key = "{UNKNOWN_KEY}"\n'})
    out = io.StringIO()
    assert scan.main(['--root', str(dirty)], out=out, err=err) == scan.EXIT_FOUND
    assert 'VI PHẠM' in out.getvalue() and UNKNOWN_KEY[2:] not in out.getvalue()


def test_cli_json_and_report(tmp_path):
    repo = make_repo(tmp_path / 'r', {'backend/a.py': 'x = 1\n'})
    out = io.StringIO()
    rep = tmp_path / 'report.md'
    assert scan.main(['--root', str(repo), '--json', '--report', str(rep)], out=out, err=io.StringIO()) == 0
    import json
    assert json.loads(out.getvalue())['ok'] is True
    assert 'ĐẠT' in rep.read_text(encoding='utf-8')


# ------------------------------------------------------------------------------------------ lớp bảo vệ thứ hai: lọc log
@pytest.mark.parametrize('line, leaked', [
    (f'sign failed private_key={UNKNOWN_KEY}', UNKNOWN_KEY),
    (f'cfg {{"mnemonic": "word word word"}} ok', 'word word word'),
    ('relay 0x' + 'ab' * 65, 'ab' * 65),
    (f'SHIPPER_KEY={UNKNOWN_KEY}', UNKNOWN_KEY),
])
def test_log_filter_redacts_secrets(line, leaked):
    assert leaked not in redaction.redact(line)


def test_log_filter_keeps_tx_hash_and_scanner_agrees():
    txh = '0x' + 'cd' * 32
    assert txh in redaction.redact(f'tx {txh}')
    r = scan.Report()
    scan.scan_text_secrets(f'tx {txh}', lambda n: f'l:{n}', 'x.log', r, kind='log')
    assert r.findings == []


def test_log_pipeline_output_passes_the_scanner():
    """Đường đi thật: logger -> SensitiveDataFilter -> tệp log -> bộ quét log. Khóa/chữ ký bị che nên quét sạch."""
    stream = io.StringIO()
    h = logging.StreamHandler(stream)
    h.addFilter(redaction.SensitiveDataFilter())
    lg = logging.getLogger('w8-noncustodial')
    lg.setLevel(logging.INFO)
    lg.addHandler(h)
    try:
        lg.info('quote signer_key=%s signature=%s', UNKNOWN_KEY, '0x' + 'ab' * 65)
        lg.info('relayed %s', '0x' + 'ab' * 65)
    finally:
        lg.removeHandler(h)
    r = scan.Report()
    scan.scan_text_secrets(stream.getvalue(), lambda n: f'l:{n}', 'app.log', r, kind='log')
    assert r.high == [], stream.getvalue()


def test_anvil_node_banner_log_is_not_scanned_by_default_but_explicit_path_still_is(tmp_path):
    """Tuần 8 [B]: sau bootstrap.sh, `.anvil.log` (banner Anvil in sẵn khóa công khai) từng làm test repo thật đỏ giả trên máy dev."""
    banner = tmp_path / '.anvil.log'
    banner.write_text('Private Keys\n(0) 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80\n')
    rep = scan.Report()
    scan.scan_source(tmp_path, rep)
    scan.scan_logs(None, tmp_path, rep)
    assert not rep.high and rep.scanned['log files'] == 0                      # không quét ở cả hai đường mặc định
    assert scan.scan_logs([banner], tmp_path, scan.Report()).scanned['log files'] == 1     # chỉ định rõ: vẫn đọc
    (tmp_path / 'backend.log').write_text('signer key 0x' + 'ab' * 32 + '\n')
    assert scan.scan_logs(None, tmp_path, scan.Report()).scanned['log files'] == 1         # log khác vẫn được quét


QUOTE = ('{"orderId": "100001", "buyer": "0x' + '12' * 20 + '", "amount": "8000000", "docHash": "0x' + 'ee' * 32 + '", "feeBps": 300}')


def test_db_scan_accepts_doc_hash_inside_quote_json_column():
    """Tuần 8 [B] (lỗi thật bắt được ở CI, E-05): `order_quotes.quote_json` chứa `docHash` bytes32 hợp lệ, không phải khóa."""
    cols = GOOD_COLUMNS + [('order_quotes', 'quote_json', 'json')]
    r = scan.scan_database(FakeConn(cols, {('order_quotes', 'quote_json'): [QUOTE]}), 'slopee_db')
    assert r.high == [], [f.line() for f in r.findings]


@pytest.mark.parametrize('doc', [
    '{"note": "0x' + 'ab' * 32 + '"}',                           # 64 hex dưới trường không phải hash
    '{"docHash": "0x' + 'ee' * 32 + '", "extra": "0x' + 'ab' * 32 + '"}',   # một hash hợp lệ không che được giá trị khác
    '{"hash_note": "x", "other": ["0x' + 'ab' * 32 + '"]}',
])
def test_db_scan_still_flags_64_hex_under_non_hash_json_fields(doc):
    cols = GOOD_COLUMNS + [('order_quotes', 'quote_json', 'json')]
    r = scan.scan_database(FakeConn(cols, {('order_quotes', 'quote_json'): [doc]}), 'slopee_db')
    assert 'HEX64_IN_NON_HASH_COLUMN' in rules(r)


def test_db_scan_known_dev_key_is_flagged_even_under_a_hash_field():
    cols = GOOD_COLUMNS + [('order_quotes', 'quote_json', 'json')]
    doc = '{"docHash": "' + scan.ANVIL_KEYS[5] + '"}'
    assert 'DEV_KEY_IN_DB' in rules(scan.scan_database(FakeConn(cols, {('order_quotes', 'quote_json'): [doc]}), 'slopee_db'))
