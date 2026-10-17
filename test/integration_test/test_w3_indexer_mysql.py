"""Khung Indexer (MOD-09) trên MySQL THẬT: GET_LOCK, con trỏ, idempotent, cửa sổ, rollback, phát hiện Anvil bị reset."""
import json

import time

import pytest

from slopee_web3.adapters.indexer import ChainReset, Indexer, IndexerLockBusy
from slopee_web3.adapters.indexer.loop import CURSOR_NAME
from w3_support import FakeChain, connect, event

pytestmark = pytest.mark.mysql


@pytest.fixture
def conn(mysql_db):
    c = connect()
    c.autocommit(True)
    cur = c.cursor()
    cur.execute("DELETE FROM chain_events")
    cur.execute("DELETE FROM indexer_cursor")
    c.autocommit(False)
    yield c
    c.rollback()
    c.close()


def rows(conn, sql, *a):
    with conn.cursor() as cur:
        cur.execute(sql, a)
        r = list(cur.fetchall())
    conn.commit()
    return r


def make(chain, **kw):
    return Indexer(connect, chain, **{'start_block': 0, **kw})


def test_processes_events_and_advances_cursor(conn):
    chain = FakeChain()
    chain.head = 5
    chain.logs = [event('OrderCreated', 2, 0, orderId=1001, amount=16_500_000), event('OrderDelivered', 4, 1, orderId=1001)]
    stats = make(chain).run_once(conn)
    assert stats['new_events'] == 2 and stats['last_block'] == 5
    ev = rows(conn, "SELECT event_name, order_id, block_number, block_timestamp, tx_hash FROM chain_events ORDER BY block_number")
    assert [(e['event_name'], e['order_id'], e['block_number']) for e in ev] == [('OrderCreated', 1001, 2), ('OrderDelivered', 1001, 4)]
    assert ev[0]['block_timestamp'] == chain.block_ts + 2           # thời gian lấy từ BLOCK, không phải NOW()
    cur = rows(conn, "SELECT last_block, last_block_hash FROM indexer_cursor WHERE name=%s", CURSOR_NAME)[0]
    assert cur['last_block'] == 5 and cur['last_block_hash'] == '0x' + format(5, '064x')


def test_rerun_is_idempotent_and_picks_up_only_new_blocks(conn):
    chain = FakeChain()
    chain.head = 3
    chain.logs = [event('OrderCreated', 2, 0, orderId=1)]
    ix = make(chain)
    ix.run_once(conn)
    again = ix.run_once(conn)
    assert again['windows'] == 0 and again['new_events'] == 0
    chain.head = 6
    chain.logs.append(event('OrderCompleted', 6, 0, orderId=1))
    third = ix.run_once(conn)
    assert third['new_events'] == 1 and len(rows(conn, "SELECT 1 FROM chain_events")) == 2


def test_replaying_same_logs_never_duplicates(conn):
    chain = FakeChain()
    chain.head = 3
    chain.logs = [event('OrderCreated', 2, 0, orderId=1)]
    make(chain).run_once(conn)
    rows(conn, "DELETE FROM indexer_cursor")                        # ép quét lại từ đầu (như replay)
    stats = make(chain).run_once(conn)
    assert stats['events'] == 1 and stats['new_events'] == 0
    assert len(rows(conn, "SELECT 1 FROM chain_events")) == 1


def test_large_ranges_are_split_into_windows(conn):
    chain = FakeChain()
    chain.head = 10
    chain.logs = [event('OrderCreated', b, 0, orderId=b) for b in (1, 3, 5, 7, 9, 10)]
    stats = make(chain, window=3).run_once(conn)
    assert stats['windows'] == 4 and stats['new_events'] == 6 and stats['last_block'] == 10


def test_confirmations_hold_back_recent_blocks(conn):
    chain = FakeChain()
    chain.head = 10
    chain.logs = [event('OrderCreated', 9, 0, orderId=1), event('OrderCreated', 5, 0, orderId=2)]
    stats = make(chain, confirmations=3).run_once(conn)
    assert stats['last_block'] == 7 and stats['new_events'] == 1


def test_start_block_is_respected_on_first_run(conn):
    chain = FakeChain()
    chain.head = 6
    chain.logs = [event('OrderCreated', 2, 0, orderId=1), event('OrderCreated', 5, 0, orderId=2)]
    stats = make(chain, start_block=4).run_once(conn)
    assert stats['new_events'] == 1                                  # chỉ block > 4


def test_uint256_values_beyond_json_precision_are_stored_as_strings(conn):
    chain = FakeChain()
    chain.head = 2
    big = 2 ** 200
    chain.logs = [event('OrderCreated', 2, 0, orderId=7, amount=big, docHash='0x' + 'ab' * 32)]
    make(chain).run_once(conn)
    payload = rows(conn, "SELECT payload_json FROM chain_events")[0]['payload_json']
    payload = json.loads(payload) if isinstance(payload, str) else payload
    assert payload['amount'] == str(big) and payload['orderId'] == 7


def test_events_without_order_id_are_kept_with_null(conn):
    chain = FakeChain()
    chain.head = 2
    chain.logs = [event('FeeUpdated', 2, 0, newFeeBps=250)]
    make(chain).run_once(conn)
    assert rows(conn, "SELECT order_id FROM chain_events")[0]['order_id'] is None


def test_handler_runs_once_per_new_event_in_order(conn):
    chain = FakeChain()
    chain.head = 4
    chain.logs = [event('OrderCreated', 2, 1, orderId=1), event('OrderCreated', 2, 0, orderId=2)]
    seen = []
    ix = make(chain, handlers={'OrderCreated': lambda cur, ev, ts: seen.append((ev['args']['orderId'], ts))})
    ix.run_once(conn)
    ix.run_once(conn)
    assert seen == [(1, chain.block_ts + 2), (2, chain.block_ts + 2)]       # đúng thứ tự mảng log, không chạy lại


def test_handler_failure_rolls_back_whole_window_and_retry_succeeds(conn):
    chain = FakeChain()
    chain.head = 5
    chain.logs = [event('OrderCreated', 2, 0, orderId=1), event('OrderCreated', 3, 0, orderId=2)]
    calls = []

    def flaky(cur, ev, ts):
        calls.append(ev['args']['orderId'])
        if ev['args']['orderId'] == 2 and len(calls) == 2:
            raise RuntimeError('lỗi giữa chừng')
    ix = make(chain, handlers={'OrderCreated': flaky})
    with pytest.raises(RuntimeError):
        ix.run_once(conn)
    assert rows(conn, "SELECT 1 FROM chain_events") == [] and rows(conn, "SELECT 1 FROM indexer_cursor") == []   # không còn dấu vết
    stats = ix.run_once(conn)                                        # lần sau làm lại từ đầu cửa sổ
    assert stats['new_events'] == 2 and len(rows(conn, "SELECT 1 FROM chain_events")) == 2


def test_missing_handler_is_not_an_error_in_week3_skeleton(conn):
    chain = FakeChain()
    chain.head = 3
    chain.logs = [event('OrderDisputed', 3, 0, orderId=1)]
    assert make(chain, handlers={}).run_once(conn)['new_events'] == 1


def test_anvil_restart_is_detected_when_head_is_behind_cursor(conn):
    chain = FakeChain()
    chain.head = 8
    ix = make(chain)
    ix.run_once(conn)
    chain.head = 2                                                   # Anvil khởi động lại: chuỗi ngắn hơn
    with pytest.raises(ChainReset):
        ix.run_once(conn)


def test_hash_mismatch_stops_when_reorg_depth_zero_and_rewinds_otherwise(conn):
    chain = FakeChain()
    chain.head = 8
    make(chain).run_once(conn)
    chain.blocks[8] = {'hash': '0x' + 'ee' * 32}                     # block 8 bị thay (reorg / chuỗi mới)
    with pytest.raises(ChainReset):
        make(chain, reorg_depth=0).run_once(conn)
    chain.logs = [event('OrderCreated', 7, 0, orderId=1, tx='0x' + '77' * 32)]
    stats = make(chain, reorg_depth=3).run_once(conn)                # lùi 3 block rồi quét lại
    assert stats['last_block'] == 8 and stats['new_events'] == 1


def test_rpc_down_propagates_and_leaves_state_untouched(conn):
    from slopee_web3.ports.chain_port import ChainUnavailable
    chain = FakeChain()
    chain.head = 4
    chain.available = False
    with pytest.raises(ChainUnavailable):
        make(chain).run_once(conn)
    assert rows(conn, "SELECT 1 FROM indexer_cursor") == []


def test_only_one_indexer_may_hold_the_lock(conn):
    other = connect()
    try:
        assert Indexer.acquire_lock(conn) is True
        assert Indexer.acquire_lock(other) is False
        with pytest.raises(IndexerLockBusy):
            make(FakeChain()).run_forever(stop=lambda: True)
        Indexer.release_lock(conn)
        assert Indexer.acquire_lock(other) is True
    finally:
        other.close()


def test_lock_is_released_when_connection_closes(conn):
    holder = connect()
    assert Indexer.acquire_lock(holder) is True
    assert Indexer.acquire_lock(conn) is False
    holder.close()                                                   # tiến trình chết -> MySQL tự nhả khóa
    # MySQL dọn kết nối đã đóng BẤT ĐỒNG BỘ nên khóa nhả sau một khoảnh khắc (race có thật: ~1/40 lần đỏ nếu kiểm ngay)
    deadline = time.monotonic() + 5
    while not Indexer.acquire_lock(conn):
        assert time.monotonic() < deadline, 'khóa không được nhả sau khi kết nối chủ đóng'
        time.sleep(0.05)
    Indexer.release_lock(conn)


def test_run_forever_retries_with_backoff_when_rpc_flaps(conn):
    chain = FakeChain()
    chain.head = 3
    chain.logs = [event('OrderCreated', 2, 0, orderId=1)]
    chain.available = False
    sleeps, state = [], {'n': 0}

    def fake_sleep(s):
        sleeps.append(s)
        state['n'] += 1
        if state['n'] == 3:
            chain.available = True       # RPC hồi phục sau hai lần thử

    ix = Indexer(connect, chain, poll_seconds=0.5, sleep=fake_sleep)
    ix.run_forever(stop=lambda: state['n'] >= 4)
    assert sleeps[:2] == [1.0, 2.0]                                  # backoff tăng dần
    assert len(rows(conn, "SELECT 1 FROM chain_events")) == 1
