"""Tiền tệ VND (P0-07): luôn là số nguyên, không dùng float."""
from decimal import Decimal, InvalidOperation

MAX_VND = 10 ** 15 - 1  # DECIMAL(15,0)


class InvalidMoney(ValueError):
    pass


def to_vnd(value, allow_zero=True):
    """Chuyển giá trị đầu vào/DB sang int VND. Ném InvalidMoney nếu âm, có phần lẻ, hoặc quá lớn."""
    if isinstance(value, bool) or value is None:
        raise InvalidMoney("Invalid amount")
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise InvalidMoney("Invalid amount")
    if not d.is_finite() or d != d.to_integral_value():
        raise InvalidMoney("Amount must be a whole number of VND")
    n = int(d)
    if n < 0 or (n == 0 and not allow_zero) or n > MAX_VND:
        raise InvalidMoney("Amount out of range")
    return n


def format_vnd(amount):
    """1234567 -> '1.234.567 ₫' (dùng cho message phía server)."""
    return f"{int(amount):,}".replace(",", ".") + " ₫"
