"""Tuần 7 [B] `scripts/reconcile.py` trên MySQL THẬT + chuỗi giả đúng contract (AC-10, E-06): đối soát sau MỌI kịch bản kết thúc đơn.

Chứng minh: khớp sau giao hàng/mở khóa sớm/hết hạn kiểm tra/khiếu nại + Trọng tài xử đơn phương/hủy quá 14 ngày/khoản chờ rút ETH; báo LỆCH
(mã thoát 1) khi có tiền chuyển thẳng vào contract; và nguồn `chain_events` chỉ ra ĐÚNG phía sai khi `order_web3` bị sửa trái.
"""
import importlib.util
import io
import json
from pathlib import Path

import pytest

from slopee_web3.application.dispute_force_service import DisputeForceResolveService
from test_w3_dispute_note_mysql import disputed  # noqa: F401
from test_w3_week5_flow_mysql import Stack, assign, db, locked_orders, new_shipper, row, status  # noqa: F401
from w3_support import ADDR, TOKEN, connect, user

pytestmark = pytest.mark.mysql
DAY = 86400
ZERO = '0x' + '0' * 40

_spec = importlib.util.spec_from_file_location('reconcile_script', Path(__file__).resolve().parents[2] / 'scripts' / 'reconcile.py')
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


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


def run_script(st, *argv):
    out, err = io.StringIO(), io.StringIO()
    code = script.main(list(argv), service=st.reconcile, out=out, err=err, sleep=lambda s: None)
    return code, out.getvalue(), err.getvalue()


def deliver(st, db, order_id, shipper):
    assign(st, db, order_id, shipper)
    st.shipper.deliver(shipper, order_id)
    st.index()


def test_empty_system_is_reconciled(st, db):
    st.chain.advance(1)                                   # bootstrap.sh luôn khởi tạo con trỏ; chuỗi giả block 0 thì cần một block để Indexer ghi con trỏ
    st.index()
    code, out, _ = run_script(st, '--deep', '--events')
    assert code == 0 and 'KẾT QUẢ: KHỚP' in out


def test_no_indexer_run_yet_is_an_operational_error(st, db):
    code, out, _ = run_script(st)
    assert code == 2 and 'Indexer chưa chạy' in out


def test_matches_after_every_way_an_order_can_end(st, db):
    """Giỏ 3 shop kết thúc ba kiểu khác nhau (E-07) + một đơn khiếu nại bị Trọng tài xử + một đơn hủy quá 14 ngày; sau mỗi bước vẫn khớp."""
    buyer, group, _ = locked_orders(st, db, 3)
    a, b, c = group['orders']
    shipper = new_shipper(db)
    ids = {k: int(o['quote']['orderId']) for k, o in zip('abc', (a, b, c))}
    assert run_script(st, '--deep', '--events')[0] == 0                                     # ba đơn đang mở

    deliver(st, db, a['order_id'], shipper)
    deliver(st, db, b['order_id'], shipper)
    st.chain.early_release(ids['a'])                                                         # A: mở khóa sớm
    st.chain.raise_dispute(ids['b'])                                                         # B: khiếu nại
    st.index()
    assert run_script(st, '--deep', '--events')[0] == 0

    admin = user(db, 'admin')
    force = DisputeForceResolveService(st.uow, st.chain, st.clock, st.relayer)
    timeout = int(st.chain.get_order(ids['b'])['dispute_timeout'])
    st.chain.advance(timeout)                                                                # qua cả 14 ngày giao hàng của C (timeout >= 7 ngày)
    force.force_resolve(admin, b['order_id'], 'BUYER')                                       # B: Trọng tài hoàn tiền
    st.chain.advance(15 * DAY)
    st.chain.cancel_if_unfulfilled(ids['c'])                                                 # C: Buyer hủy sau 14 ngày
    st.index()
    code, out, _ = run_script(st, '--deep', '--events')
    assert code == 0 and 'KẾT QUẢ: KHỚP' in out and 'chain_events) khớp order_web3' in out
    rec = st.reconcile.run(deep=True, events=True)
    assert [t['open_orders'] for t in rec['tokens'] if t['token'] == TOKEN.lower()] == [0]  # không còn đơn mở, contract về 0
    assert int([t for t in rec['tokens'] if t['token'] == TOKEN.lower()][0]['balance_raw']) == 0
    assert {status(db, o['order_id']) for o in group['orders']} == {'COMPLETED', 'REFUNDED'}


def test_eth_pending_withdrawal_is_part_of_the_invariant(st, db):
    st.chain.advance(1)
    st.index()
    st.chain.eth_balance = 900
    st.chain.defer_payout(ZERO, ADDR['merchant1'], 900)                                      # ví Merchant từ chối ETH: nằm trong sổ chờ rút
    st.index()
    code, out, _ = run_script(st, '--events')
    assert code == 0 and 'ETH' in out
    st.chain.eth_balance = 0
    st.chain.claim_pending(ZERO, ADDR['merchant1'])
    st.index()
    assert run_script(st, '--events')[0] == 0


def test_money_sent_straight_to_the_contract_is_a_mismatch_with_exit_1(st, db):
    locked_orders(st, db, 2)
    st.chain.stray_transfer(12_345)
    st.index()
    code, out, _ = run_script(st)
    assert code == 1 and 'LỆCH' in out and 'DƯ tiền' in out and '12345' in out
    data = json.loads(run_script(st, '--json')[1])
    tok = [t for t in data['tokens'] if t['token'] == TOKEN.lower()][0]
    assert data['exit_code'] == 1 and tok['diff_raw'] == '12345' and tok['ok'] is False


def test_events_source_points_at_the_wrong_side_when_order_web3_is_tampered(st, db):
    """Đơn đã đóng trên chuỗi nhưng order_web3 bị đặt lại LOCKED (handler áp sai): số dư contract khớp CHAIN_EVENTS, lệch order_web3."""
    buyer, group, _ = locked_orders(st, db, 2)
    a, b = group['orders']
    shipper = new_shipper(db)
    deliver(st, db, a['order_id'], shipper)
    st.chain.early_release(int(a['quote']['orderId']))
    st.index()
    assert run_script(st, '--events')[0] == 0
    db.execute("UPDATE order_web3 SET status='LOCKED' WHERE order_id=%s", (a['order_id'],))
    rec = st.reconcile.run(events=True)
    assert rec['ok'] is False and rec['event_drift']
    fields = {d['field']: d for d in rec['event_drift']}
    assert int(fields['open_orders_raw']['db_raw']) - int(fields['open_orders_raw']['events_raw']) == int(a['quote']['amount'])
    tok = [t for t in rec['tokens'] if t['token'] == TOKEN.lower()][0]
    assert int(fields['open_orders_raw']['events_raw']) == int(tok['balance_raw'])          # sự kiện KHỚP số dư thật: lỗi nằm ở order_web3
    code, out, _ = run_script(st, '--events')
    assert code == 1 and 'handler' in out


def test_swapped_equal_orders_keep_the_sums_green_but_events_expose_both(st, db):
    """Hai đơn cùng số tiền bị hoán đổi trạng thái: tổng số dư vẫn 'khớp'. `--deep` chỉ thấy đơn CSDL coi là đang mở (đơn đã đóng thật);
    đơn còn mở thật mà CSDL ghi COMPLETED (tiền kẹt) thì CHỈ nguồn sự kiện (`--events`) thấy, vì nó so tập đơn mở theo từng id."""
    buyer, group, _ = locked_orders(st, db, 2)
    a, b = group['orders']
    deliver(st, db, a['order_id'], new_shipper(db))
    st.chain.early_release(int(a['quote']['orderId']))
    st.index()
    db.execute("UPDATE order_web3 SET amount_raw=%s", (str(a['quote']['amount']),))        # cùng số tiền cho cả hai
    db.execute("UPDATE order_web3 SET status='LOCKED' WHERE order_id=%s", (a['order_id'],))
    db.execute("UPDATE order_web3 SET status='COMPLETED' WHERE order_id=%s", (b['order_id'],))
    plain = st.reconcile.run()
    assert plain['ok'] is True                                                               # tổng khớp: đối soát số dư KHÔNG thấy
    deep = st.reconcile.run(deep=True)
    assert [m['order_id'] for m in deep['order_mismatches']] == [a['order_id']]              # --deep chỉ thấy một nửa
    ev = st.reconcile.run(events=True)
    assert ev['ok'] is False
    assert {(d['onchain_order_id'], d['db_open'], d['events_open']) for d in ev['event_order_drift']} == {
        (int(a['quote']['orderId']), True, False), (int(b['quote']['orderId']), False, True)}
    code, out, _ = run_script(st, '--events')
    assert code == 1 and str(int(b['quote']['orderId'])) in out and run_script(st, '--deep')[0] == 1


def test_anomaly_flagged_orders_are_listed_and_strict_fails(st, db):
    buyer, group, _ = locked_orders(st, db, 1)
    db.execute("UPDATE order_web3 SET anomaly_flag=1 WHERE order_id=%s", (group['orders'][0]['order_id'],))
    code, out, _ = run_script(st)
    assert code == 0 and 'CẢNH BÁO' in out and group['orders'][0]['order_id'] in out
    assert run_script(st, '--strict')[0] == 1


def test_script_is_read_only_it_changes_no_rows(st, db):
    locked_orders(st, db, 2)
    tables = ('order_web3', 'chain_events', 'pending_balances', 'tx_outbox', 'notifications', 'indexer_cursor')
    snap = lambda: {t: row(db, f"SELECT COUNT(*) AS c, COALESCE(SUM(CRC32(CONCAT_WS('|', t.status))),0) AS h FROM {t} t", ) if t == 'order_web3'
                    else row(db, f"SELECT COUNT(*) AS c FROM {t}") for t in tables}
    before = snap()
    run_script(st, '--deep', '--events')
    assert snap() == before
