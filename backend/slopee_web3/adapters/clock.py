"""ClockPort adapters (SDD 5.2, R-09)."""
import time


class HybridClock:
    """now_system = đồng hồ máy chủ; now_chain = max(đồng hồ hệ thống, thời gian block mới nhất).

    Dùng now_chain cho hạn báo giá/server_time để vẫn đúng khi Anvil bị tua thời gian (evm_increaseTime)."""

    def __init__(self, chain, system=time.time):
        self._chain = chain
        self._system = system

    def now_system(self):
        return int(self._system())

    def now_chain(self):
        return max(self.now_system(), int(self._chain.latest_block()['timestamp']))


class FixedClock:
    """Đồng hồ giả cho test: đặt/tăng tay."""

    def __init__(self, system=1_800_000_000, chain=None):
        self.system = system
        self.chain = chain

    def now_system(self):
        return self.system

    def now_chain(self):
        return max(self.system, self.chain or 0)
