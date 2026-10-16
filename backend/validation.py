"""Kiểm tra đầu vào dùng chung (P0-06, S-14).

- json_body(): body phải là JSON object (hoặc rỗng); không bao giờ trả None -> hết lỗi AttributeError/500.
- get_str / get_int / get_enum / get_url_list...: ép kiểu + giới hạn độ dài/khoảng giá trị, sai thì ném ApiError 400
  (thay cho int() không bắt lỗi và lỗi tràn cột của MySQL strict mode).
- Tiền VND vẫn dùng money.to_vnd (không lặp lại ở đây).
"""
import re
from urllib.parse import urlsplit

from flask import request

from errors import ApiError

MAX_URL_LEN = 500  # khớp productImages.imageUrl / reviewImages.imageUrl varchar(500)
_CONTROL_OR_SPACE = re.compile(r'[\s\x00-\x1f\x7f]')


def invalid(message, code='invalid_field'):
    return ApiError(message, code, 400)


def json_body():
    """Trả về dict từ body JSON. Body rỗng -> {}. Body hỏng hoặc không phải object -> 400."""
    raw = request.get_data(cache=True)
    if not raw or not raw.strip():
        return {}
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.", 'invalid_body', 400)
    return data


def get_str(data, key, *, required=True, min_len=1, max_len=None, label=None, required_msg=None, strip=True):
    """Lấy chuỗi từ data[key]. Không chấp nhận số/list/dict thay cho chuỗi."""
    label = label or key
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise invalid(required_msg or f"{label} is required", 'missing_field')
        return None
    if not isinstance(value, str):
        raise invalid(f"{label} must be a string")
    if strip:
        value = value.strip()
    if len(value) < min_len:
        raise invalid(f"{label} must be at least {min_len} characters")
    if max_len is not None and len(value) > max_len:
        raise invalid(f"{label} must be at most {max_len} characters")
    return value


def as_int(value, label, *, minimum=None, maximum=None):
    """Ép giá trị về int. Chấp nhận int, số thực nguyên (2.0) và chuỗi số nguyên ("2"); từ chối bool/None/rác."""
    if isinstance(value, bool) or value is None:
        raise invalid(f"{label} must be an integer")
    try:
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError
            n = int(value)
        elif isinstance(value, int):
            n = value
        elif isinstance(value, str):
            n = int(value.strip())
        else:
            raise ValueError
    except (ValueError, OverflowError):
        raise invalid(f"{label} must be an integer")
    if minimum is not None and n < minimum:
        raise invalid(f"{label} must be >= {minimum}")
    if maximum is not None and n > maximum:
        raise invalid(f"{label} must be <= {maximum}")
    return n


def get_int(data, key, *, default=None, required=False, minimum=None, maximum=None, label=None):
    label = label or key
    if key not in data or data[key] is None:
        if required:
            raise invalid(f"{label} is required", 'missing_field')
        return default
    return as_int(data[key], label, minimum=minimum, maximum=maximum)


def get_bool(data, key, default=False, label=None):
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise invalid(f"{label or key} must be true or false")
    return value


def get_enum(data, key, allowed, *, default=None, label=None):
    label = label or key
    value = data.get(key, default)
    if value not in allowed:
        raise invalid(f"{label} must be one of: {', '.join(allowed)}")
    return value


def validate_url(value, label='imageUrl', max_len=MAX_URL_LEN):
    """Chỉ cho phép http/https tuyệt đối, không khoảng trắng/ký tự điều khiển, tối đa 500 ký tự."""
    if not isinstance(value, str):
        raise invalid(f"{label} must be a string")
    url = value.strip()
    if not url:
        raise invalid(f"{label} is required", 'missing_field')
    if len(url) > max_len:
        raise invalid(f"{label} must be at most {max_len} characters")
    if _CONTROL_OR_SPACE.search(url):
        raise invalid(f"{label} is not a valid URL")
    parts = urlsplit(url)
    if parts.scheme.lower() not in ('http', 'https') or not parts.netloc or not parts.hostname:
        raise invalid(f"{label} must be an absolute http(s) URL")
    return url


def get_url_list(data, key, *, max_items=10, label=None):
    """Danh sách URL (có thể rỗng). Bỏ qua phần tử rỗng như hành vi cũ, nhưng URL sai thì 400."""
    label = label or key
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise invalid(f"{label} must be a list")
    urls = [v for v in value if not (v is None or (isinstance(v, str) and not v.strip()))]
    if len(urls) > max_items:
        raise invalid(f"{label} must contain at most {max_items} items")
    return [validate_url(u, label) for u in urls]
