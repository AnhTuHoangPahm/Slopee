"""Vòng lặp Indexer (SDD 6.1): GET_LOCK -> con trỏ -> cửa sổ <= 500 block -> chain_events idempotent -> handler -> con trỏ.

Mỗi cửa sổ là MỘT giao dịch: lỗi bất kỳ -> ROLLBACK, lần sau làm lại từ đầu cửa sổ. Mọi mốc thời gian lấy từ
`block_timestamp`, không bao giờ từ NOW() của máy chủ (replay phải cho kết quả giống hệt).
"""
import json
import logging
import time

from .handlers import HANDLERS

log = logging.getLogger('slopee.indexer')

LOCK_NAME = 'slopee_indexer'
CURSOR_NAME = 'escrow'
WINDOW = 500
_MAX_SAFE_INT = 2 ** 53 - 1


class IndexerLockBusy(Exception):
    """Đã có một Indexer khác đang giữ khóa (chỉ một thể hiện được chạy)."""


class ChainReset(Exception):
    """Block mới nhất nhỏ hơn con trỏ hoặc hash không khớp: Anvil đã khởi động lại. Dừng thay vì chạy tiếp trên dữ liệu lệch."""


def _jsonable(v):
    """MySQL JSON làm tròn số > 64 bit; uint256 lớn phải lưu dạng chuỗi (SDD 8.2)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return str(v) if abs(v) > _MAX_SAFE_INT else v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (bytes, bytearray)):
        return '0x' + bytes(v).hex()
    return v


class Indexer:
    def __init__(self, connection_factory, chain, *, start_block=0, confirmations=0, reorg_depth=0,
                 handlers=None, window=WINDOW, poll_seconds=2.0, sleep=time.sleep):
        self._factory = connection_factory
        self._chain = chain
        self._start = int(start_block)
        self._confirmations = int(confirmations)
        self._reorg_depth = int(reorg_depth)
        self._handlers = HANDLERS if handlers is None else handlers
        self._window = int(window)
        self._poll = poll_seconds
        self._sleep = sleep

    # ---- khóa một thể hiện (GET_LOCK gắn với kết nối, tự nhả khi kết nối đóng)
    @staticmethod
    def acquire_lock(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT GET_LOCK(%s, 0) AS got", (LOCK_NAME,))
            return cur.fetchone()['got'] == 1

    @staticmethod
    def release_lock(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))

    def _load_cursor(self, cur):
        cur.execute("SELECT last_block, last_block_hash FROM indexer_cursor WHERE name=%s", (CURSOR_NAME,))
        row = cur.fetchone()
        if row:
            return int(row['last_block']), row['last_block_hash']
        return self._start, ''

    def run_once(self, conn):
        """Xử lý hết các block mới tới `latest - confirmations`. Trả thống kê {'windows', 'events', 'new_events', 'last_block'}."""
        stats = {'windows': 0, 'events': 0, 'new_events': 0, 'last_block': None}
        with conn.cursor() as cur:
            last_block, last_hash = self._load_cursor(cur)
        conn.commit()

        latest = self._chain.latest_block()
        if last_hash:
            if latest['number'] < last_block:
                raise ChainReset('Block mới nhất nhỏ hơn con trỏ: Anvil đã khởi động lại. Chạy bootstrap rồi replay.')
            if self._chain.get_block(last_block)['hash'] != last_hash:
                if self._reorg_depth <= 0:
                    raise ChainReset('Hash block tại con trỏ không khớp: chuỗi đã bị thay. Chạy bootstrap rồi replay.')
                last_block = max(self._start, last_block - self._reorg_depth)   # TUẦN 4: kèm rollback dữ liệu dẫn xuất

        to_block = latest['number'] - self._confirmations
        start = last_block + 1
        stats['last_block'] = last_block
        while start <= to_block:
            end = min(start + self._window - 1, to_block)
            self._process_window(conn, start, end, stats)
            stats['windows'] += 1
            stats['last_block'] = end
            start = end + 1
        return stats

    def _process_window(self, conn, start, end, stats):
        logs = self._chain.get_logs(start, end)
        block_ts = {}                      # mỗi block chỉ hỏi timestamp một lần (R-04)
        try:
            with conn.cursor() as cur:
                for ev in logs:
                    stats['events'] += 1
                    bn = ev['block_number']
                    if bn not in block_ts:
                        block_ts[bn] = self._chain.get_block(bn)['timestamp']
                    cur.execute(
                        "INSERT IGNORE INTO chain_events (tx_hash, log_index, event_name, order_id, block_number, block_hash, "
                        "block_timestamp, payload_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (ev['tx_hash'], ev['log_index'], ev['event'], ev['args'].get('orderId'), bn, ev['block_hash'],
                         block_ts[bn], json.dumps(_jsonable(ev['args']))))
                    if cur.rowcount == 0:
                        continue           # đã xử lý (UNIQUE(tx_hash, log_index)): idempotent
                    stats['new_events'] += 1
                    handler = self._handlers.get(ev['event'])
                    if handler:
                        handler(cur, ev, block_ts[bn])
                    else:
                        log.debug('Chưa có handler cho %s (Tuần 4)', ev['event'])
                end_hash = self._chain.get_block(end)['hash']
                cur.execute(
                    "INSERT INTO indexer_cursor (name, last_block, last_block_hash) VALUES (%s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE last_block=VALUES(last_block), last_block_hash=VALUES(last_block_hash)",
                    (CURSOR_NAME, end, end_hash))
            conn.commit()
        except Exception:
            conn.rollback()                # lỗi bất kỳ -> làm lại cả cửa sổ lần sau
            raise

    def run_forever(self, stop=lambda: False):
        """Giữ khóa; mất kết nối RPC thì thử lại với backoff tăng dần tới 30 giây, không làm sập tiến trình."""
        from ...ports.chain_port import ChainUnavailable
        conn = self._factory()
        try:
            if not self.acquire_lock(conn):
                raise IndexerLockBusy('Đã có Indexer khác đang chạy.')
            backoff = 1.0
            while not stop():
                try:
                    self.run_once(conn)
                    backoff = 1.0
                    self._sleep(self._poll)
                except ChainUnavailable as e:
                    log.warning('RPC lỗi (%s); thử lại sau %.0fs', e, backoff)
                    self._sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
        finally:
            try:
                self.release_lock(conn)
            finally:
                conn.close()
