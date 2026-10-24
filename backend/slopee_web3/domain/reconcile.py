"""Đối soát số dư contract với đơn đang mở (SDD 6.3, AC-10). Thuần: cộng/trừ số nguyên, không float.

Bất biến (INV-01): với mỗi token,
    Σ amount_raw của đơn LOCKED/DELIVERED/DISPUTED  +  Σ PayoutDeferred − Σ PendingClaimed  ==  balanceOf(contract)
Phí đã trả cho feeRecipient và tiền đã chuyển cho Merchant/Buyer rời contract nên không nằm trong tổng. Lệch nghĩa là
có tiền vào/ra ngoài luồng đơn (chuyển thẳng vào contract, sự kiện bị bỏ sót, hoặc lỗi contract) và Admin phải thấy cảnh báo đỏ.
"""
from dataclasses import dataclass

OPEN_STATES = ('LOCKED', 'DELIVERED', 'DISPUTED')
ETH = 'ETH'


@dataclass(frozen=True)
class TokenReconciliation:
    token: str                 # địa chỉ chữ thường, hoặc 'ETH'
    open_orders_raw: int       # Σ amount_raw đơn đang mở
    pending_raw: int           # Σ PayoutDeferred − Σ PendingClaimed
    expected_raw: int          # open_orders_raw + pending_raw
    balance_raw: int           # số dư thật của contract
    diff_raw: int              # balance − expected (> 0: contract dư tiền; < 0: contract thiếu tiền)
    open_orders: int           # số đơn đang mở của token này

    @property
    def ok(self):
        return self.diff_raw == 0

    def as_dict(self):
        """Số tiền dạng chuỗi (uint256 vượt giới hạn số nguyên an toàn của JSON/JS, SDD 8.2)."""
        return {'token': self.token, 'ok': self.ok, 'open_orders': self.open_orders,
                'open_orders_raw': str(self.open_orders_raw), 'pending_raw': str(self.pending_raw),
                'expected_raw': str(self.expected_raw), 'balance_raw': str(self.balance_raw),
                'diff_raw': str(self.diff_raw)}


def reconcile_token(token, open_orders_raw, open_orders, pending_raw, balance_raw):
    open_orders_raw, pending_raw, balance_raw = int(open_orders_raw), int(pending_raw), int(balance_raw)
    expected = open_orders_raw + pending_raw
    return TokenReconciliation(token=token, open_orders_raw=open_orders_raw, pending_raw=pending_raw,
                               expected_raw=expected, balance_raw=balance_raw, diff_raw=balance_raw - expected,
                               open_orders=int(open_orders))


def token_key(token_address):
    """Khóa token thống nhất: NULL/0x0 ⇒ ETH, ngược lại địa chỉ chữ thường."""
    if token_address is None:
        return ETH
    t = str(token_address).lower()
    return ETH if t == '0x' + '0' * 40 else t


# ------------------------------------------------------------------ Tuần 7 (B): nguồn thứ ba, dựng từ nhật ký sự kiện
EVENT_NAMES = ('OrderCreated', 'OrderCompleted', 'OrderRefunded', 'PayoutDeferred', 'PendingClaimed')


def totals_from_events(events):
    """Dựng lại `Σ đơn mở` và `Σ chờ rút` theo token CHỈ từ nhật ký sự kiện (`chain_events`), KHÔNG dùng `order_web3.status`.

    Vì sao: đối soát chính so số dư contract với tổng tính từ `order_web3` do handler của Indexer ghi. Nếu handler áp sai (đơn đóng mà
    vẫn `LOCKED`, quên cộng khoản chờ rút...) thì cả hai vế cùng sai theo và vẫn có thể khớp một cách giả tạo, hoặc lệch mà không rõ do đâu.
    Phép tính này đi đường khác (một đơn mở = có OrderCreated mà chưa có OrderCompleted/OrderRefunded), nên so nó với `order_web3` bắt
    được lỗi handler. `events`: [{'event', 'args'}] theo thứ tự chuỗi. Trả {token: {'open_raw', 'open_orders', 'pending_raw'}}.
    Đơn bị đóng mà không có OrderCreated (Indexer bắt đầu muộn) bị bỏ qua, người gọi phải đọc từ block 0."""
    created, closed = {}, set()
    pending = {}
    for e in events:
        name, a = e['event'], e['args']
        if name == 'OrderCreated':
            created[int(a['orderId'])] = (token_key(a['token']), int(a['amount']))
        elif name in ('OrderCompleted', 'OrderRefunded'):
            closed.add(int(a['orderId']))
        elif name == 'PayoutDeferred':
            k = token_key(a['token'])
            pending[k] = pending.get(k, 0) + int(a['amount'])
        elif name == 'PendingClaimed':
            k = token_key(a['token'])
            pending[k] = pending.get(k, 0) - int(a['amount'])
    out = {}
    for oid, (tok, amount) in created.items():
        if oid in closed:
            continue
        t = out.setdefault(tok, {'open_raw': 0, 'open_orders': 0, 'pending_raw': 0})
        t['open_raw'] += amount
        t['open_orders'] += 1
    for tok, amount in pending.items():
        out.setdefault(tok, {'open_raw': 0, 'open_orders': 0, 'pending_raw': 0})['pending_raw'] = amount
    return out


def compare_with_events(db_tokens, event_tokens):
    """So tổng từ `order_web3`/`pending_balances` (db_tokens: [TokenReconciliation]) với tổng dựng từ sự kiện. Trả danh sách lệch
    [{'token','field','db_raw','events_raw'}] (rỗng = hai nguồn dữ liệu của sàn khớp nhau). Số tiền dạng chuỗi (SDD 8.2)."""
    drift = []
    for t in db_tokens:
        ev = event_tokens.get(t.token, {'open_raw': 0, 'open_orders': 0, 'pending_raw': 0})
        for field, db_val, ev_val in (('open_orders_raw', t.open_orders_raw, ev['open_raw']), ('pending_raw', t.pending_raw, ev['pending_raw']),
                                      ('open_orders', t.open_orders, ev['open_orders'])):
            if int(db_val) != int(ev_val):
                drift.append({'token': t.token, 'field': field, 'db_raw': str(int(db_val)), 'events_raw': str(int(ev_val))})
    return drift


def open_order_ids_from_events(events):
    """Tập `onchain_order_id` còn mở theo sự kiện: có OrderCreated mà chưa có OrderCompleted/OrderRefunded."""
    created, closed = set(), set()
    for e in events:
        if e['event'] == 'OrderCreated':
            created.add(int(e['args']['orderId']))
        elif e['event'] in ('OrderCompleted', 'OrderRefunded'):
            closed.add(int(e['args']['orderId']))
    return created - closed


def compare_open_sets(db_open_ids, events_open_ids):
    """Từng đơn: mở theo CSDL nhưng đóng theo sự kiện, hoặc ngược lại. Chỗ `--deep` (chỉ duyệt đơn CSDL coi là đang mở) không thấy được:
    đơn còn mở trên chuỗi mà CSDL ghi COMPLETED/REFUNDED (tiền kẹt) cũng khiến TỔNG số tiền lệch hoặc, nếu bị hoán đổi với đơn khác cùng
    số tiền, vẫn khớp. Trả [{'onchain_order_id', 'db_open', 'events_open'}] theo id tăng dần."""
    db_open, ev_open = {int(i) for i in db_open_ids}, {int(i) for i in events_open_ids}
    return [{'onchain_order_id': i, 'db_open': i in db_open, 'events_open': i in ev_open} for i in sorted(db_open ^ ev_open)]
