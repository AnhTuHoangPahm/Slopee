"""Quy tắc ghi chú khiếu nại của Buyer (UC-05, SEQ-02). Thuần: chỉ làm sạch/kiểm chuỗi, ném DomainError khi sai.

Giao diện (C) chặn sớm cho người dùng thấy lỗi ngay, nhưng backend KHÔNG tin client: mọi giá trị đều kiểm lại ở đây.
Cố ý lỏng hơn giao diện ở độ dài tối thiểu: backend chỉ chặn rác, giao diện được phép chặt hơn mà không bị backend từ chối.
"""
import re

from .errors import DomainError

MIN_REASON_LEN = 3
MAX_REASON_LEN = 2000
MAX_EVIDENCE_URL_LEN = 500
_CONTROL_OR_SPACE = re.compile(r'[\s\x00-\x1f\x7f]')
# http(s)://<host>[:port][/?#...]. Host = tên miền/IPv4 (không chứa @ : / ? # \ khoảng trắng) hoặc IPv6 trong []. Vì host không được
# chứa '@' và ':' chỉ được theo sau bởi số cổng, `user:pass@host` và `host@evil.com` đều KHÔNG khớp. (Dùng regex thay urllib vì
# T-ARCH-01 cấm họ urllib trong domain.)
_HTTP_URL = re.compile(r'^https?://(?:[^\s/?#@:\[\]\\]+|\[[0-9a-f:.]+\])(?::\d{1,5})?(?:[/?#]\S*)?$', re.IGNORECASE)


def _invalid(message):
    return DomainError('INVALID_DISPUTE_NOTE', message)


def clean_reason(value):
    if not isinstance(value, str):
        raise _invalid('Lý do khiếu nại phải là chuỗi ký tự.')
    reason = value.strip()
    if len(reason) < MIN_REASON_LEN:
        raise _invalid('Hãy nhập lý do khiếu nại.')
    if len(reason) > MAX_REASON_LEN:
        raise _invalid(f'Lý do khiếu nại tối đa {MAX_REASON_LEN} ký tự.')
    return reason


def clean_evidence_url(value):
    """None/rỗng ⇒ None (bằng chứng là tùy chọn). Chỉ chấp nhận http(s) có tên miền, không khoảng trắng/ký tự điều khiển, không
    `user:pass@` (tránh lưu thông tin đăng nhập và URL đánh lừa). Chặn javascript:, data:, file:... vì Admin sẽ bấm vào liên kết này."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise _invalid('Đường dẫn bằng chứng phải là chuỗi ký tự.')
    url = value.strip()
    if not url:
        return None
    if len(url) > MAX_EVIDENCE_URL_LEN:
        raise _invalid(f'Đường dẫn bằng chứng tối đa {MAX_EVIDENCE_URL_LEN} ký tự.')
    if _CONTROL_OR_SPACE.search(url):
        raise _invalid('Đường dẫn bằng chứng không được chứa khoảng trắng hay ký tự điều khiển.')
    # '\\' bị trình duyệt coi như '/', cho phép nó là cách đánh lừa phần tên miền (https://a.com\\@evil.com)
    if '\\' in url or not _HTTP_URL.match(url):
        raise _invalid('Đường dẫn bằng chứng phải là liên kết http:// hoặc https:// hợp lệ.')
    return url
