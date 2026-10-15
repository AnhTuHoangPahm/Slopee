"""OrderQuote (SRS 6) và docHash (SDD 5.3c). Thuần: chỉ băm/chuẩn hóa, không ký, không I/O."""
import json
from dataclasses import dataclass, fields

from .errors import DomainError

# Thứ tự trường PHẢI khớp shared/eip712/types.json (có test kiểm chéo) và struct Quote trong contract.
QUOTE_FIELDS = ('orderId', 'buyer', 'merchant', 'token', 'amount', 'inspectionDuration',
                'disputeTimeout', 'feeBps', 'docHash', 'deadline')


@dataclass(frozen=True)
class OrderQuote:
    orderId: int
    buyer: str
    merchant: str
    token: str
    amount: int
    inspectionDuration: int
    disputeTimeout: int
    feeBps: int
    docHash: str
    deadline: int

    def message(self):
        """Dạng JSON cho client / order_quotes: uint256 là chuỗi thập phân (SDD 8.2), địa chỉ giữ nguyên."""
        out = {}
        for f in fields(self):
            v = getattr(self, f.name)
            out[f.name] = str(v) if isinstance(v, int) else v
        return out


def canonical_json(obj):
    """Khóa sắp xếp tăng dần, không khoảng trắng thừa, UTF-8, chỉ số nguyên (SDD 5.3c)."""
    def check(o):
        if isinstance(o, (bool, float)):
            raise ValueError('canonical_json chỉ nhận số nguyên, không nhận float/bool')
        if isinstance(o, dict):
            for v in o.values():
                check(v)
        elif isinstance(o, list):
            for v in o:
                check(v)
    check(obj)
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def build_summary(order_code, items, price_vnd, created_at):
    """Bản tóm tắt đơn để băm. Danh sách hàng được sắp ổn định để băm lại từ DB cho cùng kết quả."""
    lines = [{'product_id': i['product_id'], 'quantity': int(i['quantity']), 'unit_price_vnd': int(i['unit_price_vnd'])}
             for i in items]
    lines.sort(key=lambda i: (i['product_id'], i['unit_price_vnd'], i['quantity']))
    return {'order_code': order_code, 'items': lines, 'price_vnd': int(price_vnd), 'created_at': int(created_at)}


def doc_hash(summary, keccak):
    """`keccak` là hàm bytes -> bytes (adapter truyền vào để domain không phụ thuộc thư viện băm)."""
    return '0x' + keccak(canonical_json(summary).encode('utf-8')).hex()


def validate_quote(q):
    if q.amount <= 0:
        raise DomainError('INVALID_AMOUNT', 'Số tiền quy đổi phải lớn hơn 0.')
    if q.feeBps < 0 or q.feeBps > 1000:
        raise DomainError('INVALID_AMOUNT', 'Phí sàn nằm ngoài giới hạn cho phép.')
