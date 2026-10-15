"""Tiền (SDD 5.3a, BR-08): quy đổi VND -> token bằng số nguyên, không float."""
from decimal import Decimal, InvalidOperation

from .errors import DomainError

FX_SCALE = 10 ** 4   # DECIMAL(18,4): tỷ giá nhân 10^4 thành số nguyên


def parse_fx_scaled(value):
    """'25000' / '25000.5000' / Decimal -> 250000000 / 250005000. Sai định dạng, <= 0 hoặc quá 4 chữ số lẻ -> SETTING_INVALID."""
    msg = 'Tỷ giá FX_VND_PER_TOKEN không hợp lệ, hãy báo quản trị viên.'
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise DomainError('SETTING_INVALID', msg)
    if not d.is_finite() or d <= 0:
        raise DomainError('SETTING_INVALID', msg)
    scaled = d * FX_SCALE
    if scaled != scaled.to_integral_value():
        raise DomainError('SETTING_INVALID', msg)
    return int(scaled)


def fx_to_str(fx_scaled):
    """Tỷ giá dạng chuỗi 4 chữ số lẻ (khớp DECIMAL(18,4)) từ số nguyên đã nhân 10^4."""
    whole, frac = divmod(int(fx_scaled), FX_SCALE)
    return f"{whole}.{frac:04d}"


def vnd_to_token(price_vnd, decimals, fx_scaled):
    """amount_raw = ceil(price_vnd * 10^decimals * 10^4 / fx_scaled) — làm tròn LÊN để sàn không thiệt."""
    if isinstance(price_vnd, bool) or not isinstance(price_vnd, int) or price_vnd < 0:
        raise ValueError('price_vnd phải là số nguyên không âm')
    if fx_scaled <= 0:
        raise ValueError('fx_scaled phải dương')
    return (price_vnd * 10 ** decimals * FX_SCALE + fx_scaled - 1) // fx_scaled


def fee_split(amount, fee_bps):
    """(net, fee) với fee = floor(amount * fee_bps / 10000) — khớp cách contract chia phí."""
    fee = amount * fee_bps // 10_000
    return amount - fee, fee
