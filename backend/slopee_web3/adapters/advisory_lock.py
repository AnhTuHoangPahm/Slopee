"""Khóa liên tiến trình bằng MySQL GET_LOCK (SDD 12.3 "chỉ một relayer", DD-06).

Hàng đợi một luồng của relayer (A) chỉ tuần tự hóa trong MỘT tiến trình. Flask (UC-03) và Scheduler (AutoRelease) là hai tiến
trình dùng chung SHIPPER_KEY, nên mỗi job gửi giao dịch được bọc thêm khóa này: tại một thời điểm chỉ một tiến trình đọc nonce
'pending' và gửi. GET_LOCK gắn với KẾT NỐI nên mỗi lần dùng mở một kết nối riêng và đóng lại là nhả khóa, kể cả khi tiến trình chết.
"""
import contextlib

from ..ports.chain_port import ChainUnavailable

RELAYER_LOCK = 'slopee_relayer'


class MySqlAdvisoryLock:
    def __init__(self, connection_factory, name=RELAYER_LOCK, timeout=30):
        self._factory = connection_factory
        self._name = name
        self._timeout = int(timeout)

    @contextlib.contextmanager
    def __call__(self):
        conn = self._factory()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT GET_LOCK(%s, %s) AS got", (self._name, self._timeout))
                got = cur.fetchone()['got']
            if got != 1:        # hết hạn chờ (hoặc lỗi): giống "hệ thống bận", API ánh xạ 503, người dùng thử lại
                raise ChainUnavailable('Relayer đang bận ở tiến trình khác, hãy thử lại sau.')
            try:
                yield
            finally:
                with conn.cursor() as cur:
                    cur.execute("SELECT RELEASE_LOCK(%s)", (self._name,))
        finally:
            conn.close()
