"""Quy tắc thời hạn giải ngân / giao hàng (SRS UC-04, UC-07; SDD 5.5). Thuần: nhận số giây, không đọc đồng hồ.

Mọi mốc là giây UTC theo thời gian block (`now` do ClockPort.now_chain() cấp). Công thức khớp ĐÚNG contract:
`releaseAfterInspection` cần `block.timestamp >= deliveredAt + inspectionDuration`;
`cancelIfUnfulfilled` cần `block.timestamp >= createdAt + DELIVERY_TIMEOUT`.
"""

DELIVERY_TIMEOUT_SECONDS = 14 * 24 * 3600     # = SlopeeEscrowMaster.DELIVERY_TIMEOUT

# Bộ quét hết hạn báo giá chỉ hạ đơn xuống EXPIRED khi đã quá hạn thêm chừng này (giây): contract từ chối nạp sau `deadline`
# theo block.timestamp, đệm này che lệch nhỏ giữa đồng hồ máy chủ và block để không bao giờ EXPIRED một đơn vẫn nạp được.
QUOTE_EXPIRY_GRACE_SECONDS = 30


def inspection_ends_at(delivered_at, inspection_duration):
    return int(delivered_at) + int(inspection_duration)


def release_due(delivered_at, inspection_duration, now):
    """Đã hết hạn kiểm tra (ai cũng được gọi releaseAfterInspection)."""
    return int(now) >= inspection_ends_at(delivered_at, inspection_duration)


def delivery_timeout_at(chain_created_at):
    return int(chain_created_at) + DELIVERY_TIMEOUT_SECONDS


def delivery_timeout_due(chain_created_at, now):
    """Đơn LOCKED đã quá 14 ngày kể từ lúc ký quỹ: Buyer/Admin được hủy và nhận hoàn tiền (UC-07)."""
    return int(now) >= delivery_timeout_at(chain_created_at)


def quote_expired(deadline, now, grace=QUOTE_EXPIRY_GRACE_SECONDS):
    """Báo giá đã quá hạn đủ lâu để đơn chưa nạp được chuyển EXPIRED."""
    return int(now) > int(deadline) + int(grace)
