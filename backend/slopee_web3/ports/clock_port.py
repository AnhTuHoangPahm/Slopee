"""ClockPort (SDD 5.2, R-09)."""
from typing import Protocol


class ClockPort(Protocol):
    def now_system(self) -> int:
        """Giây UTC theo đồng hồ máy chủ (nonce, giới hạn tần suất)."""

    def now_chain(self) -> int:
        """max(đồng hồ hệ thống, thời gian block mới nhất): hạn báo giá, hạn chữ ký, server_time."""
