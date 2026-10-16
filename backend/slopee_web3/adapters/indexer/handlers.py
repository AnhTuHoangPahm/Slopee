"""Bộ xử lý sự kiện của Indexer (SDD 6.2).

Chữ ký handler: handler(cursor, event, block_timestamp), chạy trong cùng giao dịch CSDL với việc ghi
chain_events/con trỏ (lỗi -> ROLLBACK cả cửa sổ). Mỗi handler chỉ áp dụng chuyển trạng thái hợp lệ
(domain.order_state.is_valid_transition); sai thì đặt anomaly_flag = 1 và ghi log, KHÔNG làm lùi trạng thái.
Mọi mốc thời gian lấy từ block_timestamp, không bao giờ từ NOW() (replay phải cho kết quả giống hệt).

TUẦN 4: OrderCreated. Các sự kiện còn lại (Delivered, Disputed, Completed, Refunded...) điền ở Tuần 5-6.
"""
import logging

from ...domain.order_state import is_valid_transition
from ..legacy_sync import sync_legacy_status

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


HANDLERS = {
    'OrderCreated': on_order_created,
}


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
    cur.execute("DELETE FROM chain_events WHERE block_number >= %s", (from_block,))
    for onchain_id in affected:
        cur.execute("SELECT order_id, status, buyer_user_id FROM order_web3 WHERE onchain_order_id=%s FOR UPDATE",
                    (onchain_id,))
        row = cur.fetchone()
        if row is None:
            continue
        if row['status'] in CHAIN_DERIVED_STATES:
            cur.execute(
                "UPDATE order_web3 SET status='PENDING_PAYMENT', deposit_tx_hash=NULL, chain_created_at=NULL, "
                "delivered_at=NULL, disputed_at=NULL, closed_at=NULL, anomaly_flag=0 WHERE order_id=%s", (row['order_id'],))
            sync_legacy_status(cur, row['order_id'], 'PENDING_PAYMENT')
        cur.execute("SELECT event_name, tx_hash, log_index, block_number, block_hash, block_timestamp, payload_json "
                    "FROM chain_events WHERE order_id=%s ORDER BY block_number, log_index", (onchain_id,))
        import json
        for e in cur.fetchall():
            h = handlers.get(e['event_name'])
            if h:
                payload = e['payload_json']
                payload = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
                h(cur, {'event': e['event_name'], 'tx_hash': e['tx_hash'], 'log_index': e['log_index'],
                        'block_number': e['block_number'], 'block_hash': e['block_hash'], 'args': payload},
                  e['block_timestamp'])
    return len(affected)
