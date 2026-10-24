"""Tuần 7 [B] `scripts/reconcile.py` (AC-10): nguồn sự kiện, mã thoát, báo cáo, chờ Indexer. Không cần MySQL/Anvil."""
import importlib.util
import io
import json
from pathlib import Path

import pytest

from slopee_web3.domain import reconcile as rc

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'reconcile.py'
spec = importlib.util.spec_from_file_location('reconcile_script', SCRIPT)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)

TOK, ZERO = '0x5fbdb2315678afecb367f032d93f642f64180aa3', '0x' + '0' * 40


def ev(name, **args):
    return {'event': name, 'args': args}


# ------------------------------------------------------------------ domain: nguồn thứ ba
def test_events_rebuild_open_totals_without_looking_at_order_status():
    events = [ev('OrderCreated', orderId=1, token=TOK, amount=100), ev('OrderCreated', orderId=2, token=TOK, amount=250),
              ev('OrderCreated', orderId=3, token=ZERO, amount=7), ev('OrderCompleted', orderId=1, netPayout=97, feeAmount=3),
              ev('OrderRefunded', orderId=3, to='0xb', amount=7)]
    t = rc.totals_from_events(events)
    assert t == {TOK: {'open_raw': 250, 'open_orders': 1, 'pending_raw': 0}}                  # đơn 1 và 3 đã đóng; ETH hết đơn mở


def test_deferred_and_claimed_payouts_net_out_and_eth_is_keyed_as_eth():
    events = [ev('PayoutDeferred', token=ZERO, to='0xa', amount=900), ev('PayoutDeferred', token=ZERO, to='0xb', amount=100),
              ev('PendingClaimed', token=ZERO, to='0xa', amount=900), ev('OrderCreated', orderId=9, token=ZERO, amount=5)]
    t = rc.totals_from_events(events)
    assert t['ETH'] == {'open_raw': 5, 'open_orders': 1, 'pending_raw': 100}


def test_big_uint256_amounts_sum_exactly_as_python_ints():
    big = 2 ** 200 + 12345
    t = rc.totals_from_events([ev('OrderCreated', orderId=1, token=TOK, amount=str(big)), ev('OrderCreated', orderId=2, token=TOK, amount=1)])
    assert t[TOK]['open_raw'] == big + 1


def test_a_closed_order_that_was_never_created_in_the_log_is_ignored_not_negative():
    t = rc.totals_from_events([ev('OrderCompleted', orderId=77, netPayout=1, feeAmount=0)])
    assert t == {}


def test_compare_reports_each_disagreeing_field_as_strings():
    db = [rc.reconcile_token(TOK, 350, 2, 0, 350)]
    ok = rc.compare_with_events(db, {TOK: {'open_raw': 350, 'open_orders': 2, 'pending_raw': 0}})
    assert ok == []
    drift = rc.compare_with_events(db, {TOK: {'open_raw': 250, 'open_orders': 1, 'pending_raw': 5}})
    assert {(d['field'], d['db_raw'], d['events_raw']) for d in drift} == {('open_orders_raw', '350', '250'), ('open_orders', '2', '1'), ('pending_raw', '0', '5')}
    assert rc.compare_with_events([rc.reconcile_token(TOK, 0, 0, 0, 0)], {}) == []            # cả hai bên đều trống: khớp


def test_open_sets_are_compared_order_by_order_in_both_directions():
    events = [ev('OrderCreated', orderId=1, token=TOK, amount=5), ev('OrderCreated', orderId=2, token=TOK, amount=5),
              ev('OrderCompleted', orderId=1, netPayout=5, feeAmount=0)]
    assert rc.open_order_ids_from_events(events) == {2}
    assert rc.compare_open_sets([2], {2}) == [] and rc.compare_open_sets([], set()) == []
    swapped = rc.compare_open_sets([1], {2})                                                  # CSDL: 1 mở; sự kiện: 2 mở (hai đơn cùng số tiền hoán đổi)
    assert swapped == [{'onchain_order_id': 1, 'db_open': True, 'events_open': False}, {'onchain_order_id': 2, 'db_open': False, 'events_open': True}]


# ------------------------------------------------------------------ script
def result(**over):
    r = {'indexer_cursor_missing': False, 'checked_at_block': 120, 'latest_block': 120, 'indexer_lag_blocks': 0,
         'tokens': [{'token': TOK, 'ok': True, 'open_orders': 2, 'open_orders_raw': '350', 'pending_raw': '0', 'expected_raw': '350',
                     'balance_raw': '350', 'diff_raw': '0'}],
         'anomalies': [], 'order_mismatches': None, 'event_drift': None, 'ok': True, 'status': 'OK'}
    r.update(over)
    return r


class FakeService:
    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def run(self, deep=False, events=False):
        self.calls.append((deep, events))
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


def run_main(service, *argv, sleep=lambda s: None):
    out, err = io.StringIO(), io.StringIO()
    code = script.main(list(argv), service=service, out=out, err=err, sleep=sleep)
    return code, out.getvalue(), err.getvalue()


def test_matching_balances_exit_0_and_say_so():
    code, out, _ = run_main(FakeService(result()))
    assert code == 0 and 'KẾT QUẢ: KHỚP' in out and 'block 120' in out


def test_contract_missing_money_exits_1_and_is_called_serious():
    bad = result(ok=False, status='MISMATCH', tokens=[dict(result()['tokens'][0], ok=False, balance_raw='340', diff_raw='-10')])
    code, out, _ = run_main(FakeService(bad))
    assert code == 1 and 'LỆCH' in out and 'THIẾU tiền' in out and 'NGHIÊM TRỌNG' in out


def test_contract_holding_extra_money_exits_1_with_the_other_direction():
    bad = result(ok=False, tokens=[dict(result()['tokens'][0], ok=False, balance_raw='360', diff_raw='10')])
    code, out, _ = run_main(FakeService(bad))
    assert code == 1 and 'DƯ tiền' in out


def test_anomalies_are_a_warning_by_default_and_an_error_with_strict():
    r = result(anomalies=[{'order_id': 'o-1', 'onchain_order_id': 5, 'status': 'LOCKED'}])
    code, out, _ = run_main(FakeService(r))
    assert code == 0 and 'CẢNH BÁO: 1 đơn' in out and 'o-1' in out
    assert run_main(FakeService(r), '--strict')[0] == 1


def test_missing_cursor_is_an_operational_error_not_a_mismatch():
    r = result(indexer_cursor_missing=True, checked_at_block=None, indexer_lag_blocks=None, ok=True)
    code, out, _ = run_main(FakeService(r))
    assert code == 2 and 'Indexer chưa chạy' in out


def test_service_failure_exits_2_with_the_reason_on_stderr_and_nothing_on_stdout():
    class Boom:
        def run(self, **kw):
            raise ConnectionError('RPC down')
    code, out, err = run_main(Boom())
    assert code == 2 and out == '' and 'ConnectionError' in err and 'RPC down' in err


def test_build_service_failure_exits_2(monkeypatch):
    monkeypatch.setattr(script, 'build_service', lambda: (_ for _ in ()).throw(RuntimeError('Chưa cấu hình Web3')))
    code, _, err = run_main(None)
    assert code == 2 and 'Chưa cấu hình Web3' in err


def test_flags_are_passed_through_to_the_service():
    s = FakeService(result())
    run_main(s, '--deep', '--events')
    assert s.calls == [(True, True)]
    s = FakeService(result())
    run_main(s)
    assert s.calls == [(False, False)]


def test_json_output_is_parseable_keeps_amounts_as_strings_and_carries_the_exit_code():
    bad = result(ok=False, tokens=[dict(result()['tokens'][0], ok=False, diff_raw='-10')])
    code, out, _ = run_main(FakeService(bad), '--json')
    data = json.loads(out)
    assert code == 1 and data['exit_code'] == 1 and data['tokens'][0]['diff_raw'] == '-10' and isinstance(data['tokens'][0]['balance_raw'], str)


def test_event_drift_is_reported_and_fails_the_run():
    drift = [{'token': TOK, 'field': 'open_orders_raw', 'db_raw': '350', 'events_raw': '250'}]
    code, out, _ = run_main(FakeService(result(ok=False, event_drift=drift)), '--events')
    assert code == 1 and 'handler' in out and 'order_web3=350 chain_events=250' in out
    assert 'khớp order_web3' in run_main(FakeService(result(event_drift=[])), '--events')[1]


def test_per_order_open_set_drift_is_reported_by_id_and_fails():
    od = [{'onchain_order_id': 100008, 'db_open': False, 'events_open': True}]
    code, out, _ = run_main(FakeService(result(ok=False, event_drift=[], event_order_drift=od)), '--events')
    assert code == 1 and 'đơn on-chain 100008' in out and 'ĐÃ ĐÓNG' in out and 'ĐANG MỞ' in out and 'khớp order_web3' not in out


def test_deep_skip_is_explained_when_the_indexer_is_behind():
    code, out, _ = run_main(FakeService(result(indexer_lag_blocks=3, latest_block=123)), '--deep')
    assert code == 0 and 'Bỏ qua so từng đơn' in out and 'trễ 3 block' in out


def test_wait_polls_until_the_indexer_catches_up_then_reports_that_run():
    s = FakeService(result(indexer_lag_blocks=5), result(indexer_lag_blocks=2), result(indexer_lag_blocks=0))
    slept = []
    code, out, _ = run_main(s, '--wait', '30', sleep=slept.append)
    assert code == 0 and len(s.calls) == 3 and len(slept) == 2 and 'trễ 0 block' in out


def test_wait_gives_up_at_the_deadline_and_still_reports():
    ticks = iter(range(100))
    s = FakeService(result(indexer_lag_blocks=9))
    res = script.run_checks(s, wait=3, sleep=lambda x: None, clock=lambda: next(ticks))
    assert res['indexer_lag_blocks'] == 9 and 1 < len(s.calls) < 10


def test_no_wait_means_exactly_one_run():
    s = FakeService(result(indexer_lag_blocks=4))
    script.run_checks(s)
    assert len(s.calls) == 1


def test_the_script_never_imports_signing_or_relayer_code():
    """Đối soát chỉ đọc: không nạp khóa, không dựng relayer/signer (an toàn khi chạy trên máy không có khóa vận hành)."""
    body = SCRIPT.read_text(encoding='utf-8')
    for banned in ('EnvKeySigner', 'RelayerService', 'sign_transaction', 'send_tx', 'ARBITRATOR_KEY', 'SHIPPER_KEY', 'QUOTE_SIGNER_KEY'):
        assert banned not in body.replace('KHÔNG cần khóa riêng', ''), banned
