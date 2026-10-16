"""Hàng đợi MỘT luồng cho relayer (SDD DD-06): mọi giao dịch của tài khoản relayer chạy lần lượt trong một luồng nền.

Vì sao: hai Shipper bấm cùng lúc mà hai luồng cùng lấy `nonce` 'pending' thì một giao dịch bị từ chối (nonce too low /
replacement underpriced). Một luồng duy nhất làm hai việc đó không thể xảy ra, đổi lại thông lượng thấp (đủ cho MVP).

Giới hạn đã biết: hàng đợi nằm TRONG tiến trình. Chạy gunicorn nhiều worker dùng chung một `SHIPPER_KEY` thì mỗi worker có
hàng đợi riêng và lỗi nonce có thể quay lại (SDD rủi ro 'Hai tiến trình dùng cùng khóa'). MVP chạy đúng một tiến trình relayer.
"""
import queue
import threading
from concurrent.futures import Future


class SingleThreadQueue:
    def __init__(self, name='slopee-relayer'):
        self._name = name
        self._q = queue.Queue()
        self._thread = None
        self._lock = threading.Lock()

    def _ensure_started(self):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name=self._name, daemon=True)
                self._thread.start()

    def _loop(self):
        while True:
            item = self._q.get()
            if item is None:                       # tín hiệu dừng từ close()
                return
            job, fut = item
            if not fut.set_running_or_notify_cancel():
                continue
            try:
                fut.set_result(job())
            except BaseException as e:             # mọi lỗi của job trả về cho người gọi, luồng nền không chết
                fut.set_exception(e)

    def run(self, job, timeout=None):
        """Xếp job, chờ xong. Hết `timeout` giây thì ném TimeoutError NHƯNG job vẫn nằm trong hàng đợi/đang chạy:
        người gọi không được coi 'hết hạn chờ' là 'chưa gửi' (hãy đọc lại trạng thái trên chuỗi trước khi thử lại)."""
        self._ensure_started()
        fut = Future()
        self._q.put((job, fut))
        return fut.result(timeout)

    def close(self):
        if self._thread is not None:
            self._q.put(None)
            self._thread.join(timeout=5)
