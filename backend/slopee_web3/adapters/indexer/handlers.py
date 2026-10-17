"""Bộ xử lý sự kiện của Indexer (SDD 6.2).

Chữ ký handler: handler(cursor, event, block_timestamp), chạy trong cùng giao dịch CSDL với việc ghi
chain_events/con trỏ (lỗi -> ROLLBACK cả cửa sổ). Mỗi handler chỉ áp dụng chuyển trạng thái hợp lệ
(domain.order_state.is_valid_transition); sai thì đặt anomaly_flag = 1 và ghi log, KHÔNG làm lùi trạng thái.
Mọi mốc thời gian lấy từ block_timestamp, không bao giờ từ NOW() (replay phải cho kết quả giống hệt).

TUẦN 4: OrderCreated. TUẦN 5: OrderDelivered, OrderDisputed, OrderCompleted, OrderRefunded, PayoutDeferred, PendingClaimed.
Còn lại cho Tuần 6: DisputeResolved, ArbitratorForceResolved (cần dispute_resolutions của DisputeService).
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from ...domain.order_state import is_valid_transition
from ..legacy_sync import sync_legacy_status
from ..mysql_repos import add_notification, release_order_stock, reserve_order_stock

log = logging.getLogger('slopee.indexer')

ZERO_ADDRESS = '0x' + '0' * 40
# Trạng thái chỉ có thể do chuỗi tạo ra (reorg phải đưa đơn về PENDING_PAYMENT nếu mất sự kiện gốc).
CHAIN_DERIVED_STATES = ('LOCKED', 'DELIVERED', 'DISPUTED', 'COMPLETED', 'REFUNDED')


def _flag_anomaly(cur, order_id, reason):
    cur.execute("UPDATE order_web3 SET anomaly_flag=1 WHERE order_id=%s", (order_id,))
    log.warning('ANOMALY đơn %s: %s', order_id, reason)


def _lower(v):
    return str(v).lower() if v is not None else ''


def _mismatches(row, a):
    """Đối chiếu tham số sự kiện với báo giá đã lưu (order_web3 chốt lúc ký). Trả danh sách trường lệch."""
    token_db = _lower(row['token_address']) if row['token_address'] else ZERO_ADDRESS
    pairs = (
        ('buyer', _lower(row['buyer_wallet']), _lower(a.get('buyer'))),
        ('merchant', _lower(row['merchant_wallet']), _lower(a.get('merchant'))),
        ('token', token_db, _lower(a.get('token'))),
        ('amount', str(row['amount_raw']), str(a.get('amount'))),
        ('inspectionDuration', str(row['inspection_duration']), str(a.get('inspectionDuration'))),
        ('disputeTimeout', str(row['dispute_timeout']), str(a.get('disputeTimeout'))),
        ('feeBps', str(row['fee_bps']), str(a.get('feeBps'))),
        ('docHash', _lower(row['doc_hash']), _lower(a.get('docHash'))),
    )
    return [name for name, db, ev in pairs if db != ev]


def clear_cart_items(cur, order_id, buyer_user_id):
    """Xóa cartItems của các sản phẩm (kèm biến thể) thuộc đơn khỏi giỏ của Buyer (SDD 6.2). Trả số dòng đã xóa."""
    cur.execute(
        "DELETE ci FROM cartItems ci JOIN carts c ON c.id = ci.cartId "
        "JOIN orderLines ol ON ol.productId = ci.productId AND ol.selectedVariants <=> ci.selectedVariants "
        "WHERE ol.orderId = %s AND c.userId = %s", (order_id, buyer_user_id))
    return cur.rowcount


def on_order_created(cur, ev, block_ts):
    a = ev['args']
    onchain_id = a.get('orderId')
    cur.execute("SELECT * FROM order_web3 WHERE onchain_order_id=%s FOR UPDATE", (onchain_id,))
    row = cur.fetchone()
    if row is None:      # đơn không có ở sàn (giả mạo hoặc nạp bằng đường khác): chỉ giữ chain_events + cảnh báo
        log.warning('OrderCreated cho đơn on-chain %s không tồn tại ở sàn (tx %s)', onchain_id, ev['tx_hash'])
        return
    order_id = row['order_id']
    if not is_valid_transition(row['status'], 'LOCKED'):
        # ví dụ EXPIRED (nạp muộn) hoặc đã LOCKED: không lùi/đổi trạng thái, chỉ đánh dấu để Admin xem
        _flag_anomaly(cur, order_id, f"OrderCreated khi đơn đang {row['status']}")
        return
    bad = _mismatches(row, a)
    cur.execute(
        "UPDATE order_web3 SET status='LOCKED', deposit_tx_hash=%s, chain_created_at=%s, anomaly_flag=%s "
        "WHERE order_id=%s", (ev['tx_hash'], block_ts, 1 if bad else row['anomaly_flag'], order_id))
    if bad:      # không sửa dữ liệu sàn (giá, phí, hạn): tiền đã khóa thật nên vẫn LOCKED, nhưng phải báo lệch
        log.warning('ANOMALY đơn %s: sự kiện lệch báo giá ở %s', order_id, ', '.join(bad))
    sync_legacy_status(cur, order_id, 'LOCKED')
    clear_cart_items(cur, order_id, row['buyer_user_id'])


# Cột do chuỗi sinh ra mà một lần chuyển trạng thái được phép đặt (tên cột cố định, KHÔNG bao giờ lấy từ dữ liệu ngoài).
_DERIVED_COLUMNS = ('delivered_at', 'disputed_at', 'closed_at')
_VN_TZ = timezone(timedelta(hours=7))


def _transition(cur, ev, new_status, **columns):
    """Khung chung cho mọi sự kiện đổi trạng thái (SDD 6.2): khóa dòng đơn, chỉ áp dụng chuyển HỢP LỆ (SRS mục 5), cập nhật
    có điều kiện trạng thái cũ (SDD 7.5), đồng bộ `orders` cũ cùng giao dịch. Chuyển sai thì KHÔNG lùi/đổi trạng thái, chỉ đặt
    anomaly_flag. Trả dòng order_web3 TRƯỚC khi đổi, hoặc None nếu không áp dụng."""
    assert set(columns) <= set(_DERIVED_COLUMNS), columns
    onchain_id = ev['args'].get('orderId')
    cur.execute("SELECT * FROM order_web3 WHERE onchain_order_id=%s FOR UPDATE", (onchain_id,))
    row = cur.fetchone()
    if row is None:      # sự kiện của đơn không có ở sàn: chỉ giữ chain_events + cảnh báo (SDD 6.3)
        log.warning('%s cho đơn on-chain %s không tồn tại ở sàn (tx %s)', ev['event'], onchain_id, ev['tx_hash'])
        return None
    if not is_valid_transition(row['status'], new_status):
        _flag_anomaly(cur, row['order_id'], f"{ev['event']} khi đơn đang {row['status']}")
        return None
    assignments = ''.join(f", {name}=%s" for name in columns)
    cur.execute(f"UPDATE order_web3 SET status=%s{assignments} WHERE order_id=%s AND status=%s",
                (new_status, *columns.values(), row['order_id'], row['status']))
    sync_legacy_status(cur, row['order_id'], new_status)
    return row


def _fmt_vn(ts):
    return datetime.fromtimestamp(int(ts), _VN_TZ).strftime('%d/%m/%Y %H:%M')


def on_order_delivered(cur, ev, block_ts):
    delivered_at = int(ev['args'].get('deliveredAt', block_ts))
    row = _transition(cur, ev, 'DELIVERED', delivered_at=delivered_at)
    if row is not None:
        # UC-03 bước 3: báo Buyer kèm hạn khiếu nại. Hạn lấy từ giờ block (không từ đồng hồ máy chủ) nên replay ra y hệt;
        # UNIQUE(user, order, kind) giữ cho chạy lại không gửi trùng.
        until = delivered_at + int(row['inspection_duration'])
        add_notification(cur, row['buyer_user_id'], row['order_id'], 'ORDER_DELIVERED',
                         f"Đơn {row['order_id'][:8]} đã được giao. Bạn có thể khiếu nại hoặc bấm \"Đã nhận hàng\" "
                         f"trước {_fmt_vn(until)} (giờ Việt Nam); quá hạn tiền sẽ tự động chuyển cho người bán.")


def on_order_disputed(cur, ev, block_ts):
    _transition(cur, ev, 'DISPUTED', disputed_at=int(ev['args'].get('disputedAt', block_ts)))


def on_order_completed(cur, ev, block_ts):
    _transition(cur, ev, 'COMPLETED', closed_at=block_ts)


def on_order_refunded(cur, ev, block_ts):
    row = _transition(cur, ev, 'REFUNDED', closed_at=block_ts)
    if row is not None:
        release_order_stock(cur, row['order_id'])      # SDD 7.4: REFUNDED -> cancelled + hoàn tồn kho


def _adjust_pending(cur, token, to, delta):
    """Số dư chờ rút (dẫn xuất từ PayoutDeferred +, PendingClaimed −) cho giao diện rút và đối soát (INV-01)."""
    token, to = str(token).lower(), str(to).lower()
    cur.execute("SELECT amount_raw FROM pending_balances WHERE token_address=%s AND address=%s FOR UPDATE", (token, to))
    row = cur.fetchone()
    new = (int(row['amount_raw']) if row else 0) + int(delta)
    if new < 0:
        log.error('ANOMALY số dư chờ rút âm (%s, %s): %s; đặt về 0, đối soát sẽ báo lệch', token, to, new)
        new = 0
    cur.execute("INSERT INTO pending_balances (token_address, address, amount_raw) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE amount_raw=VALUES(amount_raw)", (token, to, str(new)))


def on_payout_deferred(cur, ev, block_ts):
    a = ev['args']
    _adjust_pending(cur, a['token'], a['to'], +int(a['amount']))


def on_pending_claimed(cur, ev, block_ts):
    a = ev['args']
    _adjust_pending(cur, a['token'], a['to'], -int(a['amount']))


HANDLERS = {
    'OrderCreated': on_order_created,
    'OrderDelivered': on_order_delivered,
    'OrderDisputed': on_order_disputed,
    'OrderCompleted': on_order_completed,
    'OrderRefunded': on_order_refunded,
    'PayoutDeferred': on_payout_deferred,
    'PendingClaimed': on_pending_claimed,
}


def _undo_pending_events(cur, from_block):
    """Reorg: sự kiện PayoutDeferred/PendingClaimed không gắn đơn nên rollback theo đơn không chạm tới; phải đảo ngược từng sự kiện
    sắp bị xóa, nếu không số dư chờ rút bị cộng/trừ hai lần khi quét lại nhánh mới."""
    cur.execute("SELECT event_name, payload_json FROM chain_events WHERE block_number >= %s "
                "AND event_name IN ('PayoutDeferred', 'PendingClaimed')", (from_block,))
    for e in cur.fetchall():
        p = e['payload_json']
        p = json.loads(p) if isinstance(p, (str, bytes)) else p
        sign = -1 if e['event_name'] == 'PayoutDeferred' else +1
        _adjust_pending(cur, p['token'], p['to'], sign * int(p['amount']))


def rollback_orders_from_block(cur, from_block, handlers=None):
    """Reorg: đưa dữ liệu dẫn xuất về đúng trạng thái "chưa từng thấy các block >= from_block".

    Xóa chain_events của các block đó, đặt lại các cột do chuỗi sinh ra của đơn bị ảnh hưởng về giá trị ban đầu,
    rồi chạy lại handler trên các sự kiện còn lại (theo block, log_index). Cột sinh từ báo giá không bị đụng.
    KHÔNG khôi phục cartItems đã xóa (không đảo ngược được; Buyer chỉ cần thêm lại hàng nếu đơn quay về PENDING).
    Trả số đơn bị ảnh hưởng.
    """
    handlers = HANDLERS if handlers is None else handlers
    cur.execute("SELECT DISTINCT order_id FROM chain_events WHERE block_number >= %s AND order_id IS NOT NULL",
                (from_block,))
    affected = [r['order_id'] for r in cur.fetchall()]
    _undo_pending_events(cur, from_block)
    cur.execute("DELETE FROM chain_events WHERE block_number >= %s", (from_block,))
    for onchain_id in affected:
        cur.execute("SELECT order_id, status, buyer_user_id FROM order_web3 WHERE onchain_order_id=%s FOR UPDATE",
                    (onchain_id,))
        row = cur.fetchone()
        if row is None:
            continue
        if row['status'] in CHAIN_DERIVED_STATES:
            if row['status'] == 'REFUNDED' and not reserve_order_stock(cur, row['order_id']):
                log.error('Reorg đưa đơn %s từ REFUNDED về PENDING_PAYMENT nhưng hàng đã hết: tồn kho không giữ lại được',
                          row['order_id'])
            cur.execute("DELETE FROM notifications WHERE order_id=%s AND kind='ORDER_DELIVERED'", (row['order_id'],))
            cur.execute(
                "UPDATE order_web3 SET status='PENDING_PAYMENT', deposit_tx_hash=NULL, chain_created_at=NULL, "
                "delivered_at=NULL, disputed_at=NULL, closed_at=NULL, anomaly_flag=0 WHERE order_id=%s", (row['order_id'],))
            sync_legacy_status(cur, row['order_id'], 'PENDING_PAYMENT')
        cur.execute("SELECT event_name, tx_hash, log_index, block_number, block_hash, block_timestamp, payload_json "
                    "FROM chain_events WHERE order_id=%s ORDER BY block_number, log_index", (onchain_id,))
        for e in cur.fetchall():
            h = handlers.get(e['event_name'])
            if h:
                payload = e['payload_json']
                payload = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
                h(cur, {'event': e['event_name'], 'tx_hash': e['tx_hash'], 'log_index': e['log_index'],
                        'block_number': e['block_number'], 'block_hash': e['block_hash'], 'args': payload},
                  e['block_timestamp'])
    return len(affected)
