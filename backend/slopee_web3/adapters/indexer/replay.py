"""Replay Indexer từ block N (SDD 6.3, AC-08). Tuần 9, B.

    cd backend && python -m slopee_web3.adapters.indexer --from-block 0 --reset [--yes] [--dry-run] [--verify] [--report FILE]
    ./scripts/replay.sh                       # bọc quanh lệnh trên + đối soát số dư sau replay

Replay = XÓA dữ liệu dẫn xuất từ chuỗi, rồi dựng lại từ log on-chain bằng chính các handler của Indexer:
  - xóa `chain_events` từ block N, đặt con trỏ về N - 1 (N = 0: xóa con trỏ);
  - đưa mọi đơn `order_web3` ở trạng thái do chuỗi sinh ra (LOCKED, DELIVERED, DISPUTED, COMPLETED, REFUNDED) về PENDING_PAYMENT cùng
    các cột dẫn xuất (`deposit_tx_hash`, `chain_created_at`, `delivered_at`, `disputed_at`, `closed_at`, `anomaly_flag`), chiếu lại
    `orders.status`, giữ lại tồn kho của đơn REFUNDED, xóa thông báo do Indexer sinh, đảo ngược `pending_balances`
    và trạng thái EXECUTED của đề xuất phán quyết;
  - cột sinh từ báo giá (giá VND, `doc_hash`, nhóm hàng, `fee_bps`, hạn...) KHÔNG bị đụng.
Với N = 0 còn quét thêm: đơn đang ở trạng thái do chuỗi sinh ra nhưng KHÔNG còn sự kiện nào trong `chain_events` (ví dụ bảng bị xóa tay) cũng
được đưa về PENDING_PAYMENT, và `pending_balances` bị xóa sạch (bảng này chỉ sinh từ sự kiện), nếu không replay sẽ cộng đôi.

Kiểm chứng: `replay()` chụp ảnh các bảng dẫn xuất TRƯỚC reset (sau khi Indexer đã bắt kịp), reset, chạy lại ĐÚNG TỚI block đã chụp (`upto`, để
giao dịch mới trên chuỗi không làm lệch phép so sánh), chụp lại và so khớp từng dòng. Khác nhau = replay không tái tạo được trạng thái.

Giới hạn đã biết (đều không đảo ngược được về mặt dữ liệu, không phải lỗi):
  - `cartItems` đã bị Indexer xóa không được khôi phục; ngược lại, replay xử lại `OrderCreated` nên sẽ xóa món cùng sản phẩm mà Buyer vừa
    thêm lại vào giỏ SAU khi đơn đó được ký quỹ. Đừng chạy replay giữa lúc có người đang mua.
  - `notifications` do Indexer sinh bị xóa và tạo lại nên mất dấu `read_at` (đã đọc).
  - `ArbitratorForceResolved` đã hủy các đề xuất đang hoạt động; replay xử lại cho cùng kết quả (CANCELLED) nhưng nếu muốn lùi hẳn từ N > 0
    thì Admin phải tạo đề xuất mới (xem `_undo_dispute_events`).
"""
import json
import logging

from .handlers import CHAIN_DERIVED_STATES, HANDLERS, reset_order_to_pending, rollback_orders_from_block
from .loop import CURSOR_NAME, ChainReset

log = logging.getLogger('slopee.indexer.replay')

# Bảng/cột dẫn xuất được so sánh trước/sau replay. Cố ý KHÔNG có created_at/updated_at (giờ máy chủ, đổi mỗi lần ghi) và read_at.
_SNAPSHOT_QUERIES = {
    'orders': (
        "SELECT w.onchain_order_id, w.status, w.deposit_tx_hash, w.chain_created_at, w.delivered_at, w.disputed_at, w.closed_at, "
        "w.anomaly_flag, o.status AS legacy_status FROM order_web3 w JOIN orders o ON o.id = w.order_id ORDER BY w.onchain_order_id"),
    'stock': "SELECT id, inStock FROM products ORDER BY id",
    'pending_balances': "SELECT token_address, address, amount_raw FROM pending_balances ORDER BY token_address, address",
    'notifications': ("SELECT user_id, order_id, kind, message FROM notifications "
                      "WHERE kind IN ('ORDER_DELIVERED', 'DISPUTE_RESOLVED') ORDER BY user_id, order_id, kind"),
    'dispute_resolutions': "SELECT id, order_id, payout_to, status, submitted_tx_hash FROM dispute_resolutions ORDER BY id",
    'chain_events': ("SELECT tx_hash, log_index, event_name, order_id, block_number, block_hash, block_timestamp "
                     "FROM chain_events ORDER BY block_number, log_index"),
}


def _plain(v):
    """Giá trị so sánh được và ghi được ra JSON (Decimal/bytes -> chuỗi)."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (bytes, bytearray)):
        return '0x' + bytes(v).hex()
    return str(v)


def snapshot(cur):
    """Ảnh chụp các bảng dẫn xuất từ chuỗi: {tên: [[giá trị...], ...]} theo thứ tự ổn định."""
    out = {}
    for name, sql in _SNAPSHOT_QUERIES.items():
        cur.execute(sql)
        out[name] = [[_plain(v) for v in r.values()] for r in cur.fetchall()]
    return out


def diff_snapshots(before, after, limit=5):
    """Danh sách câu mô tả chỗ khác nhau giữa hai ảnh chụp (rỗng = khớp 100%). Mỗi bảng nêu tối đa `limit` dòng lệch."""
    problems = []
    for name in _SNAPSHOT_QUERIES:
        a, b = before.get(name, []), after.get(name, [])
        if a == b:
            continue
        a_set, b_set = {json.dumps(r) for r in a}, {json.dumps(r) for r in b}
        only_before = sorted(a_set - b_set)
        only_after = sorted(b_set - a_set)
        problems.append(f"{name}: {len(a)} dòng trước, {len(b)} dòng sau, {len(only_before)} dòng chỉ có trước, {len(only_after)} chỉ có sau")
        for r in only_before[:limit]:
            problems.append(f"  - trước: {r}")
        for r in only_after[:limit]:
            problems.append(f"  + sau:   {r}")
    return problems


def _count(cur, sql, args=()):
    cur.execute(sql, args)
    return int(next(iter(cur.fetchone().values())))


def reset_derived_state(conn, chain, from_block=0, *, start_block=0, handlers=None, dry_run=False):
    """Bước RESET của replay, MỘT giao dịch (lỗi -> ROLLBACK, không để dữ liệu nửa vời). `dry_run`: chỉ đếm, luôn ROLLBACK.

    Người gọi phải đang giữ khóa Indexer (không có Indexer nào khác chạy). Trả thống kê:
    {'from_block', 'full', 'events_deleted', 'orders_with_events', 'orders_swept', 'pending_cleared', 'cursor', 'dry_run'}.
    """
    handlers = HANDLERS if handlers is None else handlers
    from_block = max(0, int(from_block))
    full = from_block <= max(0, int(start_block))        # từ block đầu tiên Indexer quét: tương đương xóa sạch con trỏ
    effective = 0 if full else from_block
    try:
        with conn.cursor() as cur:
            stats = {'from_block': effective, 'full': full, 'dry_run': bool(dry_run),
                     'events_deleted': _count(cur, "SELECT COUNT(*) FROM chain_events WHERE block_number >= %s", (effective,)),
                     'orders_with_events': 0, 'orders_swept': 0, 'pending_cleared': 0, 'cursor': None}
            if dry_run:
                stats['orders_with_events'] = _count(
                    cur, "SELECT COUNT(DISTINCT order_id) FROM chain_events WHERE block_number >= %s AND order_id IS NOT NULL", (effective,))
                marks = ', '.join(['%s'] * len(CHAIN_DERIVED_STATES))
                stats['orders_swept'] = _count(
                    cur, f"SELECT COUNT(*) FROM order_web3 WHERE status IN ({marks}) AND onchain_order_id NOT IN "
                         "(SELECT order_id FROM chain_events WHERE order_id IS NOT NULL)", CHAIN_DERIVED_STATES) if full else 0
                stats['pending_cleared'] = _count(cur, "SELECT COUNT(*) FROM pending_balances") if full else 0
                stats['cursor'] = 'xóa' if full else effective - 1
                conn.rollback()
                return stats
            stats['orders_with_events'] = rollback_orders_from_block(cur, effective, handlers)
            if full:
                # (1) đơn còn ở trạng thái do chuỗi sinh ra mà không có sự kiện nào để lần theo (chain_events bị xóa tay, v.v.)
                marks = ', '.join(['%s'] * len(CHAIN_DERIVED_STATES))
                cur.execute(f"SELECT order_id, status FROM order_web3 WHERE status IN ({marks}) ORDER BY onchain_order_id FOR UPDATE",
                            CHAIN_DERIVED_STATES)
                for row in cur.fetchall():
                    reset_order_to_pending(cur, row)
                    stats['orders_swept'] += 1
                # (2) cờ bất thường chỉ do Indexer ghi; replay đặt lại rồi tự gắn lại đúng chỗ
                cur.execute("UPDATE order_web3 SET anomaly_flag=0 WHERE anomaly_flag=1")
                # (3) số dư chờ rút chỉ sinh từ PayoutDeferred/PendingClaimed
                cur.execute("DELETE FROM pending_balances")
                stats['pending_cleared'] = cur.rowcount
                cur.execute("DELETE FROM indexer_cursor WHERE name=%s", (CURSOR_NAME,))
                stats['cursor'] = 'xóa'
            else:
                new_last = effective - 1
                cur.execute(
                    "INSERT INTO indexer_cursor (name, last_block, last_block_hash) VALUES (%s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE last_block=VALUES(last_block), last_block_hash=VALUES(last_block_hash)",
                    (CURSOR_NAME, new_last, chain.get_block(new_last)['hash']))
                stats['cursor'] = new_last
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    log.warning('Replay RESET từ block %s: xóa %s sự kiện, %s đơn theo sự kiện, %s đơn quét thêm, %s dòng sổ chờ rút',
                effective, stats['events_deleted'], stats['orders_with_events'], stats['orders_swept'], stats['pending_cleared'])
    return stats


def replay(indexer, conn, chain, *, from_block=0, start_block=0, handlers=None, dry_run=False, verify=True):
    """Chạy trọn quy trình: bắt kịp -> chụp ảnh -> reset -> dựng lại tới đúng block đã chụp -> so ảnh -> bắt kịp phần mới.

    Người gọi giữ khóa Indexer. Trả dict: `ok` (reset + dựng lại xong và, nếu `verify`, ảnh khớp 100%), `reset` (thống kê),
    `replayed` (thống kê run_once), `verified` (True/False/None = không so được), `differences` (danh sách mô tả), `pinned_block`, `notes`.
    Chuỗi đã bị thay (Anvil khởi động lại, `ChainReset` ở bước bắt kịp) KHÔNG phải lỗi ở đây: đó chính là lý do chạy replay (SDD 15),
    nên bỏ bước so sánh (ảnh trước không còn ý nghĩa) và ghi vào `notes`.
    """
    result = {'ok': False, 'reset': None, 'replayed': None, 'verified': None, 'differences': [], 'pinned_block': None, 'notes': []}
    before = None
    pinned = None
    if dry_run:                     # chỉ đọc: không bắt kịp, không chụp ảnh
        result['reset'] = reset_derived_state(conn, chain, from_block, start_block=start_block, handlers=handlers, dry_run=True)
        result['ok'] = True
        return result
    try:
        indexer.run_once(conn)
        pos = indexer.cursor_position(conn)
        pinned = pos[0] if pos else None
        if verify:
            with conn.cursor() as cur:
                before = snapshot(cur)
            conn.commit()
    except ChainReset as e:
        result['notes'].append(f'Chuỗi đã bị thay, bỏ qua bước chụp ảnh trước replay: {e}')
        before = None
        pinned = None
        if verify:
            result['notes'].append('Không so sánh được trước/sau (chuỗi mới khác chuỗi cũ); chỉ dựng lại từ chuỗi hiện tại.')
    result['pinned_block'] = pinned

    result['reset'] = reset_derived_state(conn, chain, from_block, start_block=start_block, handlers=handlers)
    result['replayed'] = indexer.run_once(conn, upto=pinned)
    if verify and before is not None:
        with conn.cursor() as cur:
            after = snapshot(cur)
        conn.commit()
        result['differences'] = diff_snapshots(before, after)
        result['verified'] = not result['differences']
    elif verify:
        result['verified'] = None
    indexer.run_once(conn)          # phần mới hơn block đã chụp (nếu có): xử lý như bình thường, KHÔNG nằm trong phép so sánh
    result['ok'] = result['verified'] is not False
    return result
