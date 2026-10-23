"""Ngoại lệ miền (SDD 5.4). Adapter Flask ánh xạ `code` -> HTTP status; domain không biết HTTP."""


class DomainError(Exception):
    """Lỗi nghiệp vụ có chủ đích. `message` là tiếng Việt, an toàn để hiển thị cho người dùng."""

    def __init__(self, code, message, extra=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra or {}


# code -> HTTP status (SDD 5.4 + các mã bổ sung của UC-00/UC-01)
STATUS_BY_CODE = {
    'WALLET_NOT_LINKED': 409,
    'WALLET_TAKEN': 409,
    'NONCE_INVALID': 400,
    'BAD_SIGNATURE': 400,
    'INVALID_ADDRESS': 400,
    'RATE_LIMITED': 429,
    'QUOTE_EXPIRED': 410,
    'INVALID_STATE': 409,
    'FORBIDDEN': 403,
    'POLICY_OUT_OF_RANGE': 422,
    'BATCH_TOO_LARGE': 422,
    'EMPTY_CART': 400,
    'CART_ITEM_NOT_FOUND': 404,
    'GROUP_NOT_FOUND': 404,
    'ORDER_NOT_FOUND': 404,
    'INVALID_SHIPPER': 422,
    'INVALID_DISPUTE_NOTE': 422,
    'DISPUTE_NOT_FOUND': 404,
    'DISPUTE_NOT_READY': 409,
    'DISPUTE_STALE': 409,
    'DISPUTE_EXPIRED': 410,
    'INVALID_PAYOUT': 422,
    'DISPUTE_WINDOW_CLOSED': 409,
    'SIGNATURE_EXPIRED': 409,
    'ALREADY_SIGNED': 409,
    'PRODUCT_UNAVAILABLE': 409,
    'OUT_OF_STOCK': 409,
    'SELF_PURCHASE': 422,
    'INVALID_AMOUNT': 422,
    'PENDING_GROUP_EXISTS': 409,
    'SETTING_INVALID': 503,
    'POLICY_NOT_CONFIGURED': 503,
    'CHAIN_UNAVAILABLE': 503,
    'WEB3_NOT_CONFIGURED': 503,
    'CHAIN_TX_FAILED': 502,
}


def http_status(code):
    return STATUS_BY_CODE.get(code, 400)
