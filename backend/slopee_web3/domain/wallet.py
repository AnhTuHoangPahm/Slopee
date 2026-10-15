"""Liên kết ví (UC-00, SDD 5.3g): thông điệp mẫu SIWE và chuẩn hóa địa chỉ/chữ ký. Thuần."""
import re
from datetime import datetime, timezone

from .errors import DomainError

NONCE_TTL_SECONDS = 300
_ADDR_RE = re.compile(r'^0x[0-9a-fA-F]{40}$')
_SIG_RE = re.compile(r'^0x[0-9a-fA-F]{130}$')   # 65 byte (r, s, v)
_NONCE_RE = re.compile(r'^[0-9a-f]{32}$')


def normalize_address(address):
    """Địa chỉ đầu vào phải là 0x + 40 hex; lưu/so sánh bằng chữ thường (SDD 8.2)."""
    if not isinstance(address, str) or not _ADDR_RE.match(address.strip()):
        raise DomainError('INVALID_ADDRESS', 'Địa chỉ ví không hợp lệ.')
    return address.strip().lower()


def normalize_signature(signature):
    """Chữ ký đúng 65 byte; v chuẩn hóa về 27/28 (SDD 8.2)."""
    if not isinstance(signature, str) or not _SIG_RE.match(signature.strip()):
        raise DomainError('BAD_SIGNATURE', 'Chữ ký không hợp lệ.')
    sig = signature.strip().lower()
    v = int(sig[-2:], 16)
    if v in (0, 1):
        sig = sig[:-2] + format(v + 27, '02x')
    elif v not in (27, 28):
        raise DomainError('BAD_SIGNATURE', 'Chữ ký không hợp lệ.')
    return sig


def is_valid_nonce(nonce):
    return isinstance(nonce, str) and bool(_NONCE_RE.match(nonce))


def _iso(ts):
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def build_link_message(domain, address, user_id, nonce, chain_id, issued_at, expires_at):
    """Thông điệp personal_sign (SRS UC-00 bước 2): tên miền, địa chỉ, mã tài khoản, nonce, chainId, phát hành, hết hạn.

    Định dạng cố định để Backend dựng lại đúng từng byte lúc xác minh (không tin thông điệp do client gửi).
    `issued_at`/`expires_at` là giây UTC; địa chỉ in chữ thường để không phụ thuộc cách client viết hoa.
    """
    return (
        f"{domain} wants you to link your wallet to a Slopee account.\n"
        f"\n"
        f"Address: {address.lower()}\n"
        f"Account: {user_id}\n"
        f"Nonce: {nonce}\n"
        f"Chain ID: {int(chain_id)}\n"
        f"Issued At: {_iso(issued_at)}\n"
        f"Expiration Time: {_iso(expires_at)}"
    )
