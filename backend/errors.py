"""Xử lý lỗi tập trung (P0-06, S-10/S-14).

Nguyên tắc:
- Client chỉ nhận thông báo chung + mã `code`; chi tiết (traceback, nội dung exception, SQL) chỉ ghi vào log máy chủ.
- Route ném `ApiError` cho lỗi người dùng (4xx); mọi exception khác -> 500 chung.
- Handler được gắn trực tiếp vào từng blueprint (register_blueprint_errors) nên hoạt động cả khi app
  được dựng tối giản (như trong test), không phụ thuộc vào app.py.
"""
import logging

from flask import current_app, jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger('slopee')

GENERIC_500_MESSAGE = "Something went wrong on our side. Please try again later."


class ApiError(Exception):
    """Lỗi nghiệp vụ/đầu vào có chủ đích, an toàn để hiển thị cho client."""

    def __init__(self, message, code='bad_request', status=400, headers=None, extra=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.headers = headers or {}
        self.extra = extra or {}


def error_response(message, code, status, headers=None, extra=None):
    body = {"error": message, "code": code}
    if extra:
        body.update(extra)
    resp = jsonify(body)
    resp.status_code = status
    for k, v in (headers or {}).items():
        resp.headers[k] = v
    return resp


def internal_error(exc=None, context=None):
    """Ghi log chi tiết (kèm traceback nếu đang trong except) rồi trả 500 chung cho client."""
    try:
        log = current_app.logger
    except RuntimeError:  # ngoài app context
        log = logger
    log.error("Unhandled error%s: %r", f" in {context}" if context else "", exc, exc_info=exc is not None)
    return error_response(GENERIC_500_MESSAGE, 'internal_error', 500)


def _handle_api_error(e):
    return error_response(e.message, e.code, e.status, e.headers, e.extra)


def _handle_unexpected(e):
    if isinstance(e, HTTPException):  # 404/405/413... giữ nguyên status, nhưng trả JSON
        return error_response(e.description or e.name, e.name.lower().replace(' ', '_'), e.code or 500)
    return internal_error(e)


def register_blueprint_errors(bp):
    """Gắn handler ApiError + lỗi bất ngờ vào blueprint."""
    bp.register_error_handler(ApiError, _handle_api_error)
    bp.register_error_handler(Exception, _handle_unexpected)


def register_app_errors(app):
    """Handler cấp ứng dụng: cho 404/405 ngoài blueprint, và lưới an toàn cuối cùng."""
    app.register_error_handler(ApiError, _handle_api_error)
    app.register_error_handler(Exception, _handle_unexpected)
