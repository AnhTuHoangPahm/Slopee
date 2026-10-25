"""Tuần 9 [B]: phần KHÔNG cần MySQL/Anvil của replay: kiểm tham số CLI, xác nhận, báo cáo, so sánh ảnh chụp, và `scripts/replay.sh`
(mã thoát gộp, không gọi đối soát khi replay lỗi, từ chối khi có Scheduler/Indexer) bằng trình thông dịch giả."""
import argparse
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from slopee_web3.adapters.indexer import __main__ as cli
from slopee_web3.adapters.indexer.replay import diff_snapshots

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'replay.sh'


def parse(*argv):
    return cli.build_parser().parse_args(list(argv))


# ---------------------------------------------------------------------------------------------- tham số CLI
@pytest.mark.parametrize('argv,ok', [
    ((), True),                                                       # chạy Indexer bình thường
    (('--once',), True),
    (('--from-block', '0', '--reset'), True),
    (('--from-block', '120', '--reset', '--yes', '--dry-run', '--no-verify', '--json', '--report', 'r.json'), True),
    (('--reset',), False),                                            # thiếu --from-block
    (('--from-block', '0'), False),                                   # thiếu --reset: không được lỡ tay xóa
    (('--from-block', '-1', '--reset'), False),
    (('--from-block', '0', '--reset', '--once'), False),
    (('--yes',), False),                                              # tùy chọn của replay không dùng một mình
    (('--dry-run',), False),
    (('--report', 'x.json'), False),
])
def test_cli_argument_combinations(argv, ok):
    problem = cli.validate_args(parse(*argv))
    assert (problem is None) == ok, problem


def test_confirmation_needs_yes_or_a_typed_word_and_never_blocks_without_a_terminal():
    class Tty:
        def isatty(self): return True

    class NoTty:
        def isatty(self): return False
    a = parse('--from-block', '0', '--reset')
    assert cli._confirm(parse('--from-block', '0', '--reset', '--yes'), stdin=NoTty()) is True
    assert cli._confirm(parse('--from-block', '0', '--reset', '--dry-run'), stdin=NoTty()) is True      # dry-run không xóa gì
    assert cli._confirm(a, stdin=NoTty(), input_fn=lambda p: pytest.fail('không được hỏi khi không có terminal')) is False
    assert cli._confirm(a, stdin=Tty(), input_fn=lambda p: 'RESET') is True
    assert cli._confirm(a, stdin=Tty(), input_fn=lambda p: ' RESET ') is True
    for wrong in ('', 'y', 'yes', 'reset', 'RESET now'):
        assert cli._confirm(a, stdin=Tty(), input_fn=lambda p, w=wrong: w) is False


# ---------------------------------------------------------------------------------------------- run_replay với đối tượng giả
class FakeIndexer:
    def __init__(self, lock=True):
        self.lock, self.released = lock, False

    def acquire_lock(self, conn): return self.lock

    def release_lock(self, conn): self.released = True


def test_run_replay_busy_lock_returns_2_and_never_calls_replay(monkeypatch, capsys):
    from slopee_web3.adapters.indexer import replay as replay_mod
    monkeypatch.setattr(replay_mod, 'replay', lambda *a, **k: pytest.fail('không được chạy khi khóa bận'))
    code = cli.run_replay(parse('--from-block', '0', '--reset', '--yes'), FakeIndexer(lock=False), None, None, 0, out=lambda s: None)
    assert code == cli.EXIT_ERROR and 'Indexer khác' in capsys.readouterr().err


@pytest.mark.parametrize('ok,expected', [(True, cli.EXIT_OK), (False, cli.EXIT_DIFFERENT)])
def test_run_replay_maps_the_result_to_exit_codes_and_always_releases_the_lock(monkeypatch, ok, expected):
    from slopee_web3.adapters.indexer import replay as replay_mod
    seen = {}

    def fake(indexer, conn, chain, **kw):
        seen.update(kw)
        return {'ok': ok, 'reset': {'from_block': 0, 'events_deleted': 3, 'orders_with_events': 1, 'orders_swept': 0, 'pending_cleared': 0,
                                    'cursor': 'xóa', 'dry_run': False}, 'replayed': None, 'verified': ok, 'differences': [] if ok else ['orders: x'],
                'pinned_block': 9, 'notes': []}
    monkeypatch.setattr(replay_mod, 'replay', fake)
    ix, out = FakeIndexer(), []
    assert cli.run_replay(parse('--from-block', '5', '--reset', '--yes', '--no-verify'), ix, None, None, 2, out=out.append) == expected
    assert ix.released and seen == {'from_block': 5, 'start_block': 2, 'dry_run': False, 'verify': False}
    assert ('KHỚP 100%' in out[0]) == ok and ('KHÁC NHAU' in out[0]) == (not ok)


def test_run_replay_releases_the_lock_even_when_replay_raises(monkeypatch):
    from slopee_web3.adapters.indexer import replay as replay_mod
    monkeypatch.setattr(replay_mod, 'replay', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('mất DB')))
    ix = FakeIndexer()
    with pytest.raises(RuntimeError):
        cli.run_replay(parse('--from-block', '0', '--reset', '--yes'), ix, None, None, 0, out=lambda s: None)
    assert ix.released


def test_format_report_covers_dry_run_notes_and_differences():
    base = {'reset': {'from_block': 0, 'events_deleted': 4, 'orders_with_events': 2, 'orders_swept': 1, 'pending_cleared': 1,
                      'cursor': 'xóa', 'dry_run': True}, 'replayed': None, 'verified': None, 'differences': [], 'pinned_block': None,
            'notes': ['Chuỗi đã bị thay']}
    text = cli.format_report(base)
    assert 'DRY-RUN' in text and '4 sự kiện' in text and 'Chuỗi đã bị thay' in text and 'KHỚP' not in text
    real = dict(base, reset=dict(base['reset'], dry_run=False), replayed={'new_events': 4, 'events': 4, 'last_block': 12}, pinned_block=12,
                verified=False, differences=['orders: 1 dòng trước'])
    text = cli.format_report(real)
    assert 'RESET từ block 0' in text and 'dừng đúng tại block đã chụp 12' in text and 'KHÁC NHAU' in text and '  orders: 1 dòng trước' in text


# ---------------------------------------------------------------------------------------------- so sánh ảnh chụp
def test_diff_snapshots_is_empty_for_equal_and_limits_the_rows_it_prints():
    a = {'orders': [[1, 'COMPLETED']], 'stock': [], 'pending_balances': [], 'notifications': [], 'dispute_resolutions': [], 'chain_events': []}
    assert diff_snapshots(a, {k: list(v) for k, v in a.items()}) == []
    b = dict(a, stock=[[i, i] for i in range(20)])
    out = diff_snapshots(a, b, limit=3)
    assert out[0] == 'stock: 0 dòng trước, 20 dòng sau, 0 dòng chỉ có trước, 20 chỉ có sau' and len(out) == 1 + 3
    assert diff_snapshots(a, dict(a, orders=[[1, 'REFUNDED']]))[1:] == ['  - trước: [1, "COMPLETED"]', '  + sau:   [1, "REFUNDED"]']


def test_snapshot_columns_exclude_wall_clock_columns():
    from slopee_web3.adapters.indexer.replay import _SNAPSHOT_QUERIES
    import re
    for name, sql in _SNAPSHOT_QUERIES.items():
        # `chain_created_at` là giờ BLOCK (dẫn xuất từ chuỗi) nên được phép; `created_at` trần là giờ máy chủ
        assert not re.search(r'\b(created_at|updated_at|processed_at|read_at)\b|NOW\(', sql), name   # đổi mỗi lần ghi: so sánh sẽ luôn lệch


# ---------------------------------------------------------------------------------------------- scripts/replay.sh
bash = shutil.which('bash')
needs_bash = pytest.mark.skipif(bash is None, reason='cần bash')


def run_script(tmp_path, *args, stub_codes=(0, 0), env_extra=None, fake_pgrep=None, with_env_web3=True):
    """Chạy replay.sh trên một bản sao cây thư mục tối thiểu với `PYTHON` giả: ghi lại lệnh được gọi và trả mã theo thứ tự."""
    root = tmp_path / 'repo'
    (root / 'scripts').mkdir(parents=True)
    (root / 'backend').mkdir()
    shutil.copy(SCRIPT, root / 'scripts' / 'replay.sh')
    (root / 'scripts' / 'reconcile.py').write_text('# giả\n')
    if with_env_web3:
        (root / 'backend' / '.env.web3').write_text('X=1\n')
    calls = tmp_path / 'calls.log'
    counter = tmp_path / 'counter'
    counter.write_text('0')
    stub = tmp_path / 'fakepython'
    stub.write_text('#!/usr/bin/env bash\n'
                    # Indexer nền chạy trong lúc đối soát (không có --reset): không tính vào lệnh/mã thoát của kịch bản
                    f'case "$*" in *adapters.indexer*) case "$*" in *--reset*) ;; *) echo follow >> "{tmp_path / "follow.log"}"; exit 0;; esac;; esac\n'
                    f'echo "$@" >> "{calls}"\n'
                    f'n=$(cat "{counter}"); echo $((n+1)) > "{counter}"\n'
                    f'codes=({" ".join(str(c) for c in stub_codes)})\n'
                    'exit "${codes[$n]:-0}"\n')
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, PYTHON=str(stub), **(env_extra or {}))
    if fake_pgrep is not None:                       # thay pgrep để giả lập tiến trình đang chạy
        pbin = tmp_path / 'bin'
        pbin.mkdir()
        p = pbin / 'pgrep'
        p.write_text(f'#!/usr/bin/env bash\ncase "$*" in *"{fake_pgrep}"*) exit 0;; *) exit 1;; esac\n')
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        env['PATH'] = f'{pbin}:{env["PATH"]}'
    r = subprocess.run([bash, str(root / 'scripts' / 'replay.sh'), *args], capture_output=True, text=True, env=env, timeout=30)
    return r, (calls.read_text().splitlines() if calls.exists() else []), root


@needs_bash
def test_script_has_valid_syntax_and_help_exits_zero():
    assert subprocess.run([bash, '-n', str(SCRIPT)], capture_output=True).returncode == 0
    r = subprocess.run([bash, str(SCRIPT), '--help'], capture_output=True, text=True, timeout=10)
    assert r.returncode == 0 and '--from-block' in r.stdout and 'Mã thoát' in r.stdout


@needs_bash
@pytest.mark.parametrize('args', [('--from-block', 'abc'), ('--from-block', '-3'), ('--from-block',), ('--bogus',), ('--report',)])
def test_script_rejects_bad_arguments_with_exit_2_before_running_anything(tmp_path, args):
    r, calls, _ = run_script(tmp_path, *args)
    assert r.returncode == 2 and calls == []


@needs_bash
def test_script_requires_env_web3(tmp_path):
    r, calls, _ = run_script(tmp_path, '--yes', with_env_web3=False)
    assert r.returncode == 2 and 'bootstrap.sh' in r.stderr and calls == []


@needs_bash
def test_script_success_runs_replay_then_reconcile_and_returns_0(tmp_path):
    r, calls, root = run_script(tmp_path, '--yes', '--from-block', '7', fake_pgrep='__nothing__')
    assert r.returncode == 0, r.stderr
    assert len(calls) == 2
    assert calls[0].startswith('-m slopee_web3.adapters.indexer --from-block 7 --reset --yes --report ') and calls[0].endswith('.json')
    assert calls[1].endswith('reconcile.py --deep --events --wait 30')
    assert 'ĐẠT' in r.stdout and (root / '.replay').is_dir()
    assert (tmp_path / 'follow.log').read_text().split() == ['follow']       # Indexer nền được bật đúng một lần cho bước đối soát


@needs_bash
def test_script_does_not_start_the_background_indexer_when_replay_failed_or_for_dry_run(tmp_path):
    for i, args in enumerate((('--yes',), ('--dry-run',))):
        d = tmp_path / str(i)
        d.mkdir()
        run_script(d, *args, stub_codes=(1,) if args == ('--yes',) else (0,), fake_pgrep='__nothing__')
        assert not (d / 'follow.log').exists()


@needs_bash
@pytest.mark.parametrize('codes,expected,reconcile_called', [
    ((0, 0), 0, True), ((1, 0), 1, False), ((2, 0), 2, False), ((0, 1), 1, True), ((0, 2), 2, True), ((3, 0), 2, False)])
def test_script_combines_exit_codes_and_skips_reconcile_when_replay_did_not_finish(tmp_path, codes, expected, reconcile_called):
    r, calls, _ = run_script(tmp_path, '--yes', stub_codes=codes, fake_pgrep='__nothing__')
    assert r.returncode == expected, (r.stdout, r.stderr)
    assert any('reconcile.py' in c for c in calls) == reconcile_called


@needs_bash
def test_script_dry_run_never_reconciles_and_writes_no_report(tmp_path):
    r, calls, root = run_script(tmp_path, '--dry-run', fake_pgrep='__nothing__')
    assert r.returncode == 0 and len(calls) == 1 and '--dry-run' in calls[0] and '--report' not in calls[0]
    assert not (root / '.replay').exists()


@needs_bash
def test_script_no_reconcile_flag_and_explicit_report_path(tmp_path):
    r, calls, _ = run_script(tmp_path, '--yes', '--no-reconcile', '--report', '/tmp/x-biên-bản.json', fake_pgrep='__nothing__')
    assert r.returncode == 0 and len(calls) == 1 and calls[0].endswith('--report /tmp/x-biên-bản.json')


@needs_bash
def test_script_refuses_while_an_indexer_or_scheduler_is_running(tmp_path):
    def sub(name):
        d = tmp_path / name
        d.mkdir()
        return d
    r, calls, _ = run_script(sub('a'), '--yes', fake_pgrep='adapters[.]indexer')
    assert r.returncode == 2 and 'Indexer chạy' in r.stderr and calls == []
    r, calls, _ = run_script(sub('b'), '--yes', fake_pgrep='adapters[.]scheduler')
    assert r.returncode == 2 and 'Scheduler' in r.stderr and calls == []
    r, calls, _ = run_script(sub('c'), '--yes', '--allow-scheduler', fake_pgrep='adapters[.]scheduler')
    assert r.returncode == 0 and len(calls) == 2


def test_replay_modules_import_no_flask_and_the_domain_layer_stays_pure():
    """Replay là adapter: được dùng MySQL/web3, nhưng domain không được biết tới nó (T-ARCH-01)."""
    import ast
    dom = ROOT / 'backend' / 'slopee_web3' / 'domain'
    for f in dom.glob('*.py'):
        tree = ast.parse(f.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
            assert not any('indexer' in n or 'replay' in n for n in names), (f.name, names)
    src = (ROOT / 'backend' / 'slopee_web3' / 'adapters' / 'indexer' / 'replay.py').read_text(encoding='utf-8')
    assert 'flask' not in src.lower() and 'NOW()' not in src       # mốc thời gian chỉ từ block (R-04)
