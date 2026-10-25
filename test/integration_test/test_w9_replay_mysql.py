"""Tuần 9 [B][Q]: replay Indexer từ block 0 (`--from-block 0 --reset`, SDD 6.3, AC-08) trên MySQL THẬT + chuỗi giả mô hình đúng contract.

Khác `test_w8_i_gaps_mysql` (chỉ chứng minh `rollback_orders_from_block(0)` + xóa con trỏ là đủ): ở đây chạy chính `replay()`/`run_replay()`/
`reset_derived_state()` mà CLI và `scripts/replay.sh` dùng, trên vòng đời đầy đủ (nhận sớm, 2/3 chữ ký, tự giải ngân, Trọng tài thoát hiểm,
hủy quá hạn, sổ chờ rút), cộng các tình huống mà test Tuần 8 không có: replay từng phần, dry-run, bảng sự kiện bị xóa tay, giao dịch mới xuất
hiện giữa lúc replay, khóa Indexer đang bận, chuỗi bị thay, và một handler hỏng (replay PHẢI báo khác nhau).
"""
import argparse

import pytest

from slopee_web3.adapters.indexer import Indexer
from slopee_web3.adapters.indexer.__main__ import EXIT_DIFFERENT, EXIT_ERROR, EXIT_OK, run_replay
from slopee_web3.adapters.indexer.handlers import HANDLERS
from slopee_web3.adapters.indexer.replay import diff_snapshots, replay, reset_derived_state, snapshot
from slopee_web3.application.dispute_service import DisputeService
from slopee_web3.application.dispute_submit_service import DisputeSubmitService
from test_w3_week5_flow_mysql import Stack, assign, extra_group, locked_orders, new_shipper, row, status
from w3_support import ADDR, connect, sign_dispute_as, user

pytestmark = pytest.mark.mysql
DAY = 86400
ETH = '0x' + '0' * 40
CLEAN = ('dispute_signatures', 'dispute_resolutions', 'dispute_notes', 'dispute_force_resolutions', 'notifications', 'tx_outbox',
         'shipper_assignments', 'pending_balances', 'chain_events', 'indexer_cursor', 'order_quotes', 'order_web3', 'checkout_groups',
         'orders', 'user_wallets')        # thứ tự an toàn với khóa ngoại


@pytest.fixture
def db(mysql_db):
    """Dọn đủ bảng Web3 ở ĐẦU và CUỐI (DB test dùng chung cả phiên; test migration so cả AUTO_INCREMENT)."""
    conn = connect()
    conn.autocommit(True)
    cur = conn.cursor()

    def wipe():
        for t in CLEAN:
            cur.execute(f"DELETE FROM {t}")
    wipe()
    for k, v in (('FX_VND_PER_TOKEN', '25000'), ('QUOTE_TTL_SECONDS', '900'), ('PLATFORM_FEE_BPS', '300'), ('DISPUTE_SIG_TTL_SECONDS', '604800')):
        cur.execute("INSERT INTO platform_settings (setting_key, setting_value) VALUES (%s,%s) "
                    "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)", (k, v))
    yield cur
    wipe()
    cur.execute("DELETE FROM onchain_id_seq")
    cur.execute("ALTER TABLE onchain_id_seq AUTO_INCREMENT = 100001")
    conn.close()


@pytest.fixture
def st():
    s = Stack()
    yield s
    s.queue.close()


def indexer_for(st, **kw):
    return Indexer(connect, st.chain, start_block=0, **kw)


def lifecycle(st, db):
    """5 đơn đi hết mọi nhánh kết thúc. Trả (buyer, [a, b, c, d, e]) với
    a: Buyer nhận sớm  b: khiếu nại -> phán quyết 2/3 chữ ký (hoàn Buyer)  c: tự giải ngân sau hạn kiểm tra
    d: quá 14 ngày chưa giao -> hủy hoàn tiền  e: khiếu nại -> Trọng tài thoát hiểm sau timeout. Cộng thêm một khoản chờ rút ETH."""
    buyer, group, _ = locked_orders(st, db, 5)
    a, b, c, d, e = group['orders']
    ship = new_shipper(db)
    for o in (a, b, c, e):
        assign(st, db, o['order_id'], ship)
        st.shipper.deliver(ship, o['order_id'])
    st.index()
    oid = lambda o: int(o['quote']['orderId'])           # noqa: E731
    st.chain.early_release(oid(a))
    st.chain.raise_dispute(oid(b))
    st.chain.raise_dispute(oid(e))
    st.index()
    # b: phán quyết 2/3 (Trọng tài + Buyer) qua đúng đường đề xuất -> ký -> relayer nộp -> Indexer
    admin = user(db, 'admin')
    ds = DisputeService(st.uow, st.chain, st.signer, st.clock)
    sub = DisputeSubmitService(st.uow, st.chain, st.signer, st.clock, st.relayer)
    p = ds.propose(admin, b['order_id'], 'BUYER', 'hoàn tiền')
    sig = sign_dispute_as('buyer', oid(b), p['payout_to'], int(p['amount_raw']), int(p['nonce']), p['deadline'])
    assert ds.add_signature(buyer, b['order_id'], p['resolution_id'], sig)['status'] == 'READY'
    assert sub.submit(buyer, 'user', b['order_id'])['outcome'] == 'SENT'
    st.index()
    st.chain.advance(3 * DAY + 5)
    st.release.run_once()                                 # c: AutoRelease
    st.chain.eth_balance = 40
    st.chain.defer_payout(ETH, ADDR['merchant1'], 40)     # sổ chờ rút (ETH khớp số dư contract)
    st.index()
    st.chain.advance(30 * DAY)
    st.chain.arbitrator_force_resolve(oid(e), e['quote']['buyer'])
    st.chain.cancel_if_unfulfilled(oid(d))
    st.index()
    assert [status(db, o['order_id']) for o in (a, b, c, d, e)] == ['COMPLETED', 'REFUNDED', 'COMPLETED', 'REFUNDED', 'REFUNDED']
    return buyer, [a, b, c, d, e]


def take(db):
    conn = connect()
    try:
        with conn.cursor() as cur:
            return snapshot(cur)
    finally:
        conn.close()


def run(st, **kw):
    conn = connect()
    try:
        ix = indexer_for(st)
        assert ix.acquire_lock(conn)
        try:
            return replay(ix, conn, st.chain, **kw)
        finally:
            ix.release_lock(conn)
    finally:
        conn.close()


# ====================================================================================== AC-08: replay từ block 0
def test_replay_from_block_zero_restores_every_table_100_percent_and_reconciles_the_same(st, db):
    _, orders = lifecycle(st, db)
    before = take(db)
    rec_before = st.reconcile.run(deep=True)
    assert rec_before['ok'], rec_before
    assert before['pending_balances'] and before['chain_events'] and before['dispute_resolutions'] and before['notifications']
    n_events = len(before['chain_events'])

    res = run(st, from_block=0)

    assert res['ok'] and res['verified'] is True and res['differences'] == [], res
    assert res['reset']['full'] and res['reset']['events_deleted'] == n_events and res['reset']['cursor'] == 'xóa'
    assert res['reset']['orders_with_events'] == 5 and res['reset']['orders_swept'] == 0
    assert take(db) == before                                                      # từng bảng dẫn xuất giống hệt
    assert row(db, "SELECT COUNT(*) AS n FROM order_web3 WHERE anomaly_flag=1")['n'] == 0
    assert row(db, "SELECT status FROM dispute_resolutions")['status'] == 'EXECUTED'
    assert st.reconcile.run(deep=True) == rec_before                               # đối soát trước/sau y hệt
    assert [status(db, o['order_id']) for o in orders] == ['COMPLETED', 'REFUNDED', 'COMPLETED', 'REFUNDED', 'REFUNDED']
    res2 = run(st, from_block=0)                                                   # chạy lần hai vẫn ổn định
    assert res2['ok'] and res2['verified'] is True and take(db) == before


def test_replay_really_wipes_state_in_between_so_it_cannot_pass_by_doing_nothing(st, db):
    lifecycle(st, db)
    before = take(db)
    conn = connect()
    try:
        stats = reset_derived_state(conn, st.chain, 0)
    finally:
        conn.close()
    mid = take(db)
    assert mid != before and mid['chain_events'] == [] and mid['pending_balances'] == []
    assert {r[1] for r in mid['orders']} == {'PENDING_PAYMENT'}                    # mọi đơn về PENDING_PAYMENT
    assert {r[-1] for r in mid['orders']} == {'pending'}                            # và orders.status cũ cũng về `pending`
    assert row(db, "SELECT COUNT(*) AS n FROM indexer_cursor")['n'] == 0
    assert stats['orders_with_events'] == 5
    st.index()
    assert take(db) == before


def test_replay_keeps_everything_generated_from_the_quote_untouched(st, db):
    lifecycle(st, db)
    cols = ("onchain_order_id, buyer_user_id, merchant_user_id, buyer_wallet, merchant_wallet, token_address, amount_raw, price_vnd, "
            "fx_vnd_per_token, fee_bps, inspection_duration, dispute_timeout, doc_hash, policy_code, checkout_group_id")
    db.execute(f"SELECT {cols} FROM order_web3 ORDER BY onchain_order_id")
    quote_cols = db.fetchall()
    db.execute("SELECT id, status FROM orders ORDER BY id")
    assert run(st, from_block=0)['ok']
    db.execute(f"SELECT {cols} FROM order_web3 ORDER BY onchain_order_id")
    assert db.fetchall() == quote_cols                                              # giá, doc_hash, nhóm hàng, phí, hạn không bị đụng
    assert row(db, "SELECT COUNT(*) AS n FROM order_quotes")['n'] == 5


def test_replay_when_the_event_table_was_wiped_by_hand_sweeps_orphan_orders_and_pending_balances(st, db):
    lifecycle(st, db)
    before = take(db)
    db.execute("DELETE FROM chain_events")                                          # mất hết sự kiện nhưng đơn còn trạng thái cũ
    db.execute("DELETE FROM indexer_cursor")
    conn = connect()
    try:
        stats = reset_derived_state(conn, st.chain, 0)
    finally:
        conn.close()
    assert stats['orders_with_events'] == 0 and stats['orders_swept'] == 5 and stats['pending_cleared'] >= 1
    assert {r[1] for r in take(db)['orders']} == {'PENDING_PAYMENT'}
    assert take(db)['pending_balances'] == []                                       # không còn số dư chờ rút để bị cộng đôi
    st.index()
    after = take(db)
    assert after == before
    assert row(db, "SELECT COUNT(*) AS n FROM order_web3 WHERE anomaly_flag=1")['n'] == 0


def test_replay_clears_a_stale_anomaly_flag_that_the_chain_cannot_reproduce(st, db):
    """Cờ bất thường nằm ở đơn CHƯA ký quỹ (không bị rollback theo trạng thái) và không có sự kiện nào sinh lại nó: replay phải xóa cờ
    và BÁO là khác ảnh trước, vì đó là dữ liệu không dựng lại được từ chuỗi (ví dụ cờ cũ còn sót sau khi chuỗi bị thay)."""
    buyer, _ = lifecycle(st, db)
    pending = extra_group(st, db, buyer, n=6)['orders'][0]
    assert status(db, pending['order_id']) == 'PENDING_PAYMENT'
    db.execute("UPDATE order_web3 SET anomaly_flag=1 WHERE order_id=%s", (pending['order_id'],))
    res = run(st, from_block=0)
    assert res['ok'] is False and res['verified'] is False and any(d.startswith('orders:') for d in res['differences'])
    assert row(db, "SELECT anomaly_flag AS a FROM order_web3 WHERE order_id=%s", pending['order_id'])['a'] == 0
    assert run(st, from_block=0)['verified'] is True                                # lần sau đã sạch


# ====================================================================================== replay từng phần
def test_partial_replay_from_a_middle_block_restores_100_percent(st, db):
    lifecycle(st, db)
    before = take(db)
    blocks = sorted({r[4] for r in before['chain_events']})
    mid = blocks[len(blocks) // 2]
    n_after = len([r for r in before['chain_events'] if r[4] >= mid])
    assert 0 < n_after < len(before['chain_events'])
    res = run(st, from_block=mid)
    assert res['ok'] and res['verified'] is True, res
    assert res['reset']['full'] is False and res['reset']['from_block'] == mid and res['reset']['cursor'] == mid - 1
    assert res['reset']['events_deleted'] == n_after
    assert take(db) == before


def test_replay_from_start_block_or_below_is_a_full_replay(st, db):
    lifecycle(st, db)
    conn = connect()
    try:
        assert reset_derived_state(conn, st.chain, 3, start_block=5, dry_run=True)['full'] is True
        assert reset_derived_state(conn, st.chain, 6, start_block=5, dry_run=True)['full'] is False
    finally:
        conn.close()


# ====================================================================================== dry-run
def test_dry_run_reports_counts_but_changes_nothing(st, db):
    lifecycle(st, db)
    before = take(db)
    cursor_before = row(db, "SELECT last_block, last_block_hash FROM indexer_cursor")
    res = run(st, from_block=0, dry_run=True)
    assert res['ok'] and res['reset']['dry_run'] is True
    assert res['reset']['events_deleted'] == len(before['chain_events']) and res['reset']['orders_with_events'] == 5
    assert res['reset']['pending_cleared'] == len(before['pending_balances']) and res['reset']['cursor'] == 'xóa'
    assert take(db) == before
    assert row(db, "SELECT last_block, last_block_hash FROM indexer_cursor") == cursor_before


# ====================================================================================== giao dịch mới giữa lúc replay
def test_events_that_arrive_during_replay_are_not_compared_but_are_indexed_afterwards(st, db):
    lifecycle(st, db)
    n_events = row(db, "SELECT COUNT(*) AS n FROM chain_events")['n']

    class Bumping(Indexer):
        """Ngay sau khi chụp ảnh (cursor_position được gọi ở đó) có thêm một giao dịch mới trên chuỗi."""

        def cursor_position(self, conn):
            pos = super().cursor_position(conn)
            st.chain.defer_payout(ETH, ADDR['merchant2'], 7)
            return pos

    conn = connect()
    try:
        ix = Bumping(connect, st.chain, start_block=0)
        assert ix.acquire_lock(conn)
        res = replay(ix, conn, st.chain, from_block=0)
        ix.release_lock(conn)
    finally:
        conn.close()
    assert res['ok'] and res['verified'] is True and res['differences'] == [], res        # sự kiện mới KHÔNG làm lệch phép so sánh
    assert row(db, "SELECT COUNT(*) AS n FROM chain_events")['n'] == n_events + 1         # nhưng vẫn được xử lý ở bước bắt kịp cuối
    db.execute("SELECT amount_raw FROM pending_balances WHERE LOWER(address)=%s", (ADDR['merchant2'].lower(),))
    assert [r['amount_raw'] for r in db.fetchall()] == ['7']


def test_run_once_upto_stops_exactly_at_the_pinned_block(st, db):
    lifecycle(st, db)
    head = st.chain.head
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM indexer_cursor")
        conn.commit()
        ix = indexer_for(st)
        stats = ix.run_once(conn, upto=3)
        assert stats['last_block'] == 3 and ix.cursor_position(conn)[0] == 3 and head > 3
        assert ix.run_once(conn)['last_block'] == head
    finally:
        conn.close()


# ====================================================================================== phát hiện replay sai
def test_replay_fails_loudly_when_a_handler_does_not_reproduce_the_state(st, db, monkeypatch):
    lifecycle(st, db)
    monkeypatch.delitem(HANDLERS, 'OrderDelivered')                                  # giả lập handler hỏng/thiếu
    res = run(st, from_block=0)
    assert res['ok'] is False and res['verified'] is False
    assert any(d.startswith('orders:') for d in res['differences']), res['differences']


def test_diff_snapshots_names_the_table_and_rows_that_differ(st, db):
    lifecycle(st, db)
    a = take(db)
    b = take(db)
    assert diff_snapshots(a, b) == []
    b['orders'][0][1] = 'PENDING_PAYMENT'
    out = diff_snapshots(a, b)
    assert out[0].startswith('orders:') and any(l.startswith('  - trước') for l in out) and any(l.startswith('  + sau') for l in out)


# ====================================================================================== khóa Indexer + chuỗi bị thay
def _args(**kw):
    base = dict(from_block=0, reset=True, yes=True, dry_run=False, no_verify=False, report=None, json=False, once=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_run_replay_refuses_when_another_indexer_holds_the_lock_and_touches_nothing(st, db, capsys):
    lifecycle(st, db)
    before = take(db)
    other = connect()
    try:
        assert indexer_for(st).acquire_lock(other)                                  # một Indexer khác đang chạy
        conn = connect()
        try:
            code = run_replay(_args(), indexer_for(st), conn, st.chain, 0, out=lambda s: None)
        finally:
            conn.close()
    finally:
        other.close()
    assert code == EXIT_ERROR and 'Indexer khác' in capsys.readouterr().err
    assert take(db) == before


def test_run_replay_exit_codes_report_file_and_lock_release(st, db, tmp_path):
    lifecycle(st, db)
    out, report = [], tmp_path / 'replay.json'
    conn = connect()
    try:
        code = run_replay(_args(report=str(report)), indexer_for(st), conn, st.chain, 0, out=out.append)
    finally:
        conn.close()
    assert code == EXIT_OK and 'KHỚP 100%' in out[0]
    import json
    saved = json.loads(report.read_text(encoding='utf-8'))
    assert saved['ok'] is True and saved['verified'] is True and saved['reset']['events_deleted'] > 0
    conn = connect()                                                                # khóa đã nhả: có thể lấy lại ngay
    try:
        assert indexer_for(st).acquire_lock(conn)
    finally:
        conn.close()


def test_run_replay_returns_exit_1_when_the_rebuilt_state_differs(st, db, monkeypatch):
    lifecycle(st, db)
    monkeypatch.delitem(HANDLERS, 'OrderCompleted')
    out = []
    conn = connect()
    try:
        code = run_replay(_args(), indexer_for(st), conn, st.chain, 0, out=out.append)
    finally:
        conn.close()
    assert code == EXIT_DIFFERENT and 'KHÁC NHAU' in out[0]


def test_replay_after_the_chain_was_replaced_skips_the_comparison_but_still_rebuilds(st, db):
    """Anvil khởi động lại (SDD 15): bước bắt kịp báo ChainReset; replay là cách phục hồi nên KHÔNG coi đó là lỗi."""
    lifecycle(st, db)
    st.chain.head -= 3                                                              # chuỗi mới ngắn hơn con trỏ
    res = run(st, from_block=0)
    assert res['ok'] is True and res['verified'] is None and res['differences'] == []
    assert any('Chuỗi đã bị thay' in n for n in res['notes'])
    assert res['pinned_block'] is None and res['replayed'] is not None
    cur = row(db, "SELECT last_block FROM indexer_cursor")
    assert cur['last_block'] == st.chain.head                                       # con trỏ khớp chuỗi mới
