"""Chính sách thời hạn theo nhóm hàng (SDD 5.3b, BR-10)."""
from dataclasses import dataclass

from .errors import DomainError

MIN_INSPECTION, MAX_INSPECTION = 3600, 2_592_000          # 1 giờ .. 30 ngày
MIN_DISPUTE_TIMEOUT, MAX_DISPUTE_TIMEOUT = 604_800, 7_776_000   # 7 .. 90 ngày


@dataclass(frozen=True)
class Policy:
    code: str
    inspection_duration: int
    dispute_timeout: int


def check_limits(inspection, dispute):
    """Kiểm giới hạn ở backend trước khi ký để lỗi cấu hình lộ sớm thay vì bị contract revert."""
    if not (MIN_INSPECTION <= inspection <= MAX_INSPECTION and MIN_DISPUTE_TIMEOUT <= dispute <= MAX_DISPUTE_TIMEOUT):
        raise DomainError('POLICY_OUT_OF_RANGE',
                          'Chính sách thời hạn của nhóm hàng nằm ngoài giới hạn cho phép, hãy báo quản trị viên.',
                          {'inspection_duration': inspection, 'dispute_timeout': dispute})


def pick_durations(policies):
    """Lấy max RIÊNG từng thời hạn trên mọi sản phẩm. Trả (inspection, dispute, policy_chủ_đạo).

    Policy chủ đạo (ghi vào order_web3.policy_code) là policy có thời hạn kiểm tra lớn nhất,
    hòa thì xét thời hạn tranh chấp, hòa nữa thì theo mã (ổn định, tất định).
    """
    if not policies:
        raise DomainError('POLICY_NOT_CONFIGURED', 'Chưa cấu hình chính sách nhóm hàng, hãy báo quản trị viên.')
    inspection = max(p.inspection_duration for p in policies)
    dispute = max(p.dispute_timeout for p in policies)
    check_limits(inspection, dispute)
    dominant = sorted(policies, key=lambda p: (-p.inspection_duration, -p.dispute_timeout, p.code))[0]
    return inspection, dispute, dominant
