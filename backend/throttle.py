"""Giới hạn số lần thử sai mật khẩu / PIN thanh toán (P0-05, S-09, A-06).

- Bộ đếm lưu trong bảng authAttempts (bền qua restart, đúng khi chạy nhiều worker) thay vì dict trong RAM.
- Sai AUTH_MAX_ATTEMPTS lần liên tiếp (mặc định 5) -> khóa AUTH_LOCK_SECONDS giây (mặc định 900 = 15 phút).
  Khi đang khóa, kể cả nhập đúng cũng bị từ chối (HTTP 429, mã too_many_attempts, header Retry-After).
- Đúng thì xóa bộ đếm. Khóa hết hạn thì chu kỳ đếm bắt đầu lại từ 0.
- scope 'password': đăng nhập và mọi thao tác xác nhận mật khẩu (đổi mật khẩu, xin xóa tài khoản)
  dùng CHUNG một bộ đếm theo tài khoản, nên không né giới hạn bằng cách đổi endpoint.
  Username không tồn tại cũng bị đếm/khóa y như username có thật (subject = băm tên) để không lộ tài khoản nào tồn tại.
- scope 'pin': PIN 6 số khi thanh toán, đếm theo userId.
- Đồng hồ: dùng đồng hồ hệ thống (SRS: now_system dùng cho giới hạn tần suất), lưu epoch giây dạng BIGINT để
  không phụ thuộc múi giờ MySQL.
- Người gọi PHẢI commit sau record_failure/reset để bộ đếm không bị rollback theo giao dịch nghiệp vụ.
"""
import hashlib
import math
import os
import time

from errors import ApiError

SCOPE_PASSWORD = 'password'
SCOPE_PIN = 'pin'

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LOCK_SECONDS = 900


def _env_int(name, default):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def max_attempts():
    return _env_int('AUTH_MAX_ATTEMPTS', DEFAULT_MAX_ATTEMPTS)


def lock_seconds():
    return _env_int('AUTH_LOCK_SECONDS', DEFAULT_LOCK_SECONDS)


def now():
    return int(time.time())


def password_subject(user_id=None, username=None):
    """Tài khoản tồn tại -> id:<userId>; không tồn tại -> u:<sha256(username)> (không lộ username nào có thật)."""
    if user_id:
        return f"id:{user_id}"
    digest = hashlib.sha256((username or '').strip().lower().encode('utf-8')).hexdigest()
    return f"u:{digest}"


def pin_subject(user_id):
    return f"id:{user_id}"


def locked_error(remaining_seconds):
    remaining = max(1, int(remaining_seconds))
    minutes = math.ceil(remaining / 60)
    unit = 'minute' if minutes == 1 else 'minutes'
    return ApiError(
        f"Too many failed attempts. Please try again in {minutes} {unit}.",
        'too_many_attempts', 429,
        headers={'Retry-After': str(remaining)},
        extra={'retryAfter': remaining},
    )


def check(cur, scope, subject):
    """Ném 429 nếu đang bị khóa. Trả về số lần sai đang lưu (0 nếu chưa có bản ghi; >0 nghĩa là cần reset khi thành công)."""
    cur.execute("SELECT failedCount, lockedUntil FROM authAttempts WHERE scope=%s AND subject=%s",
                (scope, subject))
    row = cur.fetchone()
    if not row:
        return 0
    locked_until = int(row['lockedUntil'] or 0)
    t = now()
    if locked_until > t:
        raise locked_error(locked_until - t)
    # Còn bản ghi (kể cả khóa đã hết hạn) -> trả số lần sai để người gọi xóa bản ghi khi đăng nhập/PIN đúng
    return int(row['failedCount'] or 0)


def record_failure(cur, scope, subject):
    """Ghi nhận một lần sai (nguyên tử nhờ khóa dòng). Trả về (số lần sai, thời điểm hết khóa hoặc 0)."""
    cur.execute("INSERT IGNORE INTO authAttempts (scope, subject) VALUES (%s, %s)", (scope, subject))
    cur.execute("SELECT failedCount, lockedUntil FROM authAttempts WHERE scope=%s AND subject=%s FOR UPDATE",
                (scope, subject))
    row = cur.fetchone() or {}
    failed = int(row.get('failedCount') or 0)
    locked_until = int(row.get('lockedUntil') or 0)
    t = now()
    if locked_until and locked_until <= t:   # khóa cũ đã hết hạn -> chu kỳ mới
        failed, locked_until = 0, 0
    failed += 1
    if failed >= max_attempts():
        locked_until = t + lock_seconds()
    cur.execute("UPDATE authAttempts SET failedCount=%s, lockedUntil=%s WHERE scope=%s AND subject=%s",
                (failed, locked_until, scope, subject))
    return failed, locked_until


def reset(cur, scope, subject):
    cur.execute("DELETE FROM authAttempts WHERE scope=%s AND subject=%s", (scope, subject))


def attempts_remaining(failed):
    return max(0, max_attempts() - failed)
