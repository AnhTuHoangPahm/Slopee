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
