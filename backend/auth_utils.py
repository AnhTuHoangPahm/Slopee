"""Lớp xác thực token ký cho Slopee (P0-01).

- Token được ký bằng itsdangerous (URLSafeTimedSerializer) với SECRET_KEY lấy từ env.
- Thời hạn token lấy từ AUTH_TOKEN_TTL_SECONDS (mặc định 3600 giây).
- Danh tính người dùng chỉ được lấy từ token (g.user_id / g.role),
  KHÔNG bao giờ tin userId do client gửi trong body hoặc URL.
"""
import os
from functools import wraps

from flask import g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_TOKEN_SALT = 'slopee-auth-token-v1'
_DEV_ENVS = ('development', 'test')
_DEV_FALLBACK_KEY = 'insecure-dev-only-key-do-not-use-in-prod'
DEFAULT_TTL_SECONDS = 3600


def get_secret_key():
    """Lấy SECRET_KEY từ env. Chỉ cho phép khoá dev khi SLOPEE_ENV=development/test."""
    key = os.environ.get('SECRET_KEY')
    if key:
        return key
    if os.environ.get('SLOPEE_ENV', '').lower() in _DEV_ENVS:
        return _DEV_FALLBACK_KEY
    raise RuntimeError(
        "SECRET_KEY chưa được cấu hình. Đặt biến môi trường SECRET_KEY "
        "(hoặc SLOPEE_ENV=development khi chạy local)."
    )


def get_token_ttl():
    try:
        ttl = int(os.environ.get('AUTH_TOKEN_TTL_SECONDS', DEFAULT_TTL_SECONDS))
    except ValueError:
        return DEFAULT_TTL_SECONDS
    return ttl if ttl > 0 else DEFAULT_TTL_SECONDS


def _serializer():
    return URLSafeTimedSerializer(get_secret_key(), salt=_TOKEN_SALT)


def issue_token(user_id, role):
    """Tạo token ký chứa user_id và role."""
    return _serializer().dumps({'uid': user_id, 'role': role})


def verify_token(token):
    """Trả về payload nếu hợp lệ; ném SignatureExpired / BadSignature nếu không."""
    return _serializer().loads(token, max_age=get_token_ttl())


def _auth_error(message, code, status=401):
    resp = jsonify({"error": message, "code": code})
    resp.status_code = status
    resp.headers['WWW-Authenticate'] = 'Bearer'
    return resp


def authenticate_request(roles=None):
    """Xác thực request hiện tại. Trả về None nếu OK (và gán g.user_id, g.role),
    ngược lại trả về response lỗi (401/403)."""
    header = request.headers.get('Authorization', '')
    scheme, _, token = header.partition(' ')
    if scheme.lower() != 'bearer' or not token.strip():
        return _auth_error("Authentication required.", "auth_required")
    try:
        payload = verify_token(token.strip())
    except SignatureExpired:
        return _auth_error("Session expired. Please log in again.", "token_expired")
    except BadSignature:
        return _auth_error("Invalid authentication token.", "token_invalid")

    user_id = payload.get('uid') if isinstance(payload, dict) else None
    role = payload.get('role') if isinstance(payload, dict) else None
    if not user_id or not role:
        return _auth_error("Invalid authentication token.", "token_invalid")

    if roles and role not in roles:
        resp = jsonify({"error": "You do not have permission to perform this action.", "code": "forbidden"})
        resp.status_code = 403
        return resp

    g.user_id = user_id
    g.role = role
    return None


def require_auth(*roles):
    """Decorator. Dùng `@require_auth` hoặc `@require_auth('seller')`."""
    # Hỗ trợ cả dạng không ngoặc: @require_auth
    if len(roles) == 1 and callable(roles[0]):
        return require_auth()(roles[0])

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            error = authenticate_request(roles or None)
            if error is not None:
                return error
            return fn(*args, **kwargs)
        return wrapper
    return decorator
