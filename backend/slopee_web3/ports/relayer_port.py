"""RelayerPort (SDD 5.3h, DD-06): gửi giao dịch thay Shipper/hệ thống, tuần tự hóa qua hàng đợi MỘT luồng."""
from typing import Callable, Protocol


class SerialQueue(Protocol):
    def run(self, job: Callable[[], dict], timeout: float = None) -> dict:
        """Xếp `job` vào hàng đợi một luồng, chờ chạy xong và trả kết quả (hoặc ném lại ngoại lệ của job).
        Hai job không bao giờ chạy song song, nên nonce của tài khoản relayer không thể đụng nhau."""


class RelayerPort(Protocol):
    def confirm_delivery(self, order_id: str, onchain_order_id: int) -> dict:
        """UC-03. Trả {'outcome': 'SENT'|'ALREADY_DELIVERED', 'tx_hash': str|None, 'outbox_id': int|None}.
        Idempotent: đơn đã DELIVERED trên chuỗi thì trả ALREADY_DELIVERED, không gửi giao dịch. Không tự cập nhật
        trạng thái đơn trong MySQL (việc của Indexer, BR-09)."""
