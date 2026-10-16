"""Che dữ liệu nhạy cảm trong log (SDD 5.6): giá trị của trường tên signature/private/key/mnemonic/seed/secret và mọi
chữ ký 65 byte. KHÔNG che chuỗi 0x + 64 hex trần vì đó cũng là dạng của tx hash (cần để gỡ lỗi Indexer)."""
import logging
import re

_KV = re.compile(r"""(?i)((?:signature|private|key|mnemonic|seed|secret)[\w-]*['"]?\s*[:=]\s*['"]?)(0x[0-9a-fA-F]+|[^\s,'"}\]]+)""")
_SIG130 = re.compile(r'\b0x[0-9a-fA-F]{130}\b')


def redact(text):
    text = _KV.sub(lambda m: m.group(1) + '[REDACTED]', text)
    return _SIG130.sub('0x[REDACTED-SIGNATURE]', text)


class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:
            pass
        return True


def install(logger=None):
    """Gắn vào mọi handler của root để cả thư viện bên thứ ba cũng bị che."""
    logger = logger or logging.getLogger()
    for h in logger.handlers:
        if not any(isinstance(f, SensitiveDataFilter) for f in h.filters):
            h.addFilter(SensitiveDataFilter())
