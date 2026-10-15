"""Máy trạng thái đơn Web3 (SRS mục 5) và ánh xạ sang `orders.status` cũ (SRS 5.1, SDD 7.4). Thuần."""

STATES = ('PENDING_PAYMENT', 'EXPIRED', 'LOCKED', 'DELIVERED', 'DISPUTED', 'COMPLETED', 'REFUNDED')
FINAL_STATES = ('EXPIRED', 'COMPLETED', 'REFUNDED')

# Chuyển trạng thái hợp lệ. EXPIRED -> PENDING_PAYMENT chỉ xảy ra khi Buyer xin báo giá mới (UC-01, luồng thay thế).
_TRANSITIONS = {
    'PENDING_PAYMENT': {'EXPIRED', 'LOCKED'},
    'EXPIRED': {'PENDING_PAYMENT'},
    'LOCKED': {'DELIVERED', 'REFUNDED'},
    'DELIVERED': {'COMPLETED', 'DISPUTED'},
    'DISPUTED': {'COMPLETED', 'REFUNDED'},
    'COMPLETED': set(),
    'REFUNDED': set(),
}

_LEGACY = {
    'PENDING_PAYMENT': 'pending',
    'LOCKED': 'paid',
    'DELIVERED': 'shipped',
    'DISPUTED': 'shipped',     # giữ nguyên; huy hiệu Khiếu nại lấy từ order_web3
    'COMPLETED': 'received',
    'EXPIRED': 'cancelled',
    'REFUNDED': 'cancelled',
}


def is_valid_transition(old, new):
    return new in _TRANSITIONS.get(old, set())


def to_legacy_status(web3_status):
    """Trạng thái Web3 -> giá trị ENUM của orders.status. Trạng thái lạ -> KeyError (không đoán)."""
    return _LEGACY[web3_status]
