"""Hàm đồng bộ DUY NHẤT từ trạng thái Web3 sang `orders.status` cũ (SDD 7.4).

Indexer (và Tuần 5: QuoteExpirySweeper) gọi hàm này trong CÙNG giao dịch với việc đổi `order_web3.status`;
không nơi nào khác được ghi `orders.status` cho đơn Web3. `orders` chỉ là bản chiếu cho giao diện cũ.
"""
from ..domain.order_state import to_legacy_status


def sync_legacy_status(cur, order_id, web3_status):
    cur.execute("UPDATE orders SET status=%s WHERE id=%s", (to_legacy_status(web3_status), order_id))
