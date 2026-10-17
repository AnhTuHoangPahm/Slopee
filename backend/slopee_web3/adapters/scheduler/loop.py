"""Vòng lặp tác vụ nền (SDD 5.5, DD-05: tiến trình riêng, một thể hiện nhờ GET_LOCK).

Mỗi tác vụ có chu kỳ riêng và được cô lập lỗi: một tác vụ ném ngoại lệ chỉ bị ghi log, không làm dừng các tác vụ khác hay vòng lặp.
RPC mất kết nối (ChainUnavailable) chỉ là cảnh báo; chu kỳ sau tự thử lại. Đồng hồ và sleep được tiêm để test không phải chờ thật.
"""
import logging
import time
from dataclasses import dataclass
from typing import Callable

from ...ports.chain_port import ChainUnavailable

log = logging.getLogger('slopee.scheduler')

LOCK_NAME = 'slopee_scheduler'


class SchedulerLockBusy(Exception):
    """Đã có một Scheduler khác đang chạy (chỉ một thể hiện, nếu không AutoRelease/Sweeper chạy chồng nhau)."""


@dataclass
class Job:
    name: str
    interval: float
    fn: Callable[[], object]
    next_run: float = 0.0           # 0 = chạy ngay lần đầu


class Scheduler:
    def __init__(self, jobs, *, clock=time.monotonic, sleep=time.sleep, tick=1.0):
        self.jobs = list(jobs)
        self._clock, self._sleep, self._tick = clock, sleep, float(tick)

    @staticmethod
    def acquire_lock(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT GET_LOCK(%s, 0) AS got", (LOCK_NAME,))
            return cur.fetchone()['got'] == 1

    @staticmethod
    def release_lock(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))

    def run_due(self, force=False):
        """Chạy các tác vụ đã tới hạn (hoặc tất cả khi force). Trả {tên: kết quả | {'error': ...}} của những tác vụ đã chạy."""
        now = self._clock()
        results = {}
        for job in self.jobs:
            if not force and now < job.next_run:
                continue
            job.next_run = now + job.interval
            try:
                results[job.name] = job.fn()
                log.debug('Job %s: %s', job.name, results[job.name])
            except ChainUnavailable as e:
                log.warning('Job %s bỏ qua vì RPC lỗi (%s); thử lại sau %.0fs', job.name, e, job.interval)
                results[job.name] = {'error': 'chain_unavailable'}
            except Exception as e:      # noqa: BLE001 - cô lập lỗi từng tác vụ
                log.error('Job %s lỗi: %r', job.name, e, exc_info=True)
                results[job.name] = {'error': type(e).__name__}
        return results

    def run_forever(self, stop=lambda: False):
        while not stop():
            self.run_due()
            self._sleep(self._tick)
