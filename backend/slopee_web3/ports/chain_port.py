"""ChainPort (SDD 5.2). Tuần 3 dùng các phương thức đọc; `send_tx` (relayer) làm ở Tuần 5."""
from typing import Protocol

ORDER_STATES = ('NONE', 'LOCKED', 'DELIVERED', 'DISPUTED', 'COMPLETED', 'REFUNDED')   # khớp enum OrderState


class ChainUnavailable(Exception):
    """RPC không kết nối được hoặc trả lỗi (adapter ném; application/API ánh xạ sang CHAIN_UNAVAILABLE)."""


class ChainPort(Protocol):
    def get_order_state(self, onchain_order_id: int) -> str:
        """Một trong ORDER_STATES, đọc TRỰC TIẾP từ contract (không dựa CSDL vì Indexer có thể trễ)."""

    def default_fee_bps(self) -> int:
        """Trần phí on-chain `defaultFeeBps`."""

    def latest_block(self) -> dict:
        """{'number', 'timestamp', 'hash'} của block mới nhất."""

    def get_block(self, number: int) -> dict:
        """{'number', 'timestamp', 'hash'}."""

    def get_logs(self, from_block: int, to_block: int) -> list:
        """Log của contract Escrow, đã giải mã, sắp theo (blockNumber, logIndex)."""

    def has_role(self, role: str, address: str) -> bool:
        """`hasRole(<role>, address)` trên contract; role: 'QUOTE_SIGNER_ROLE' | 'ARBITRATOR_ROLE' | 'SHIPPER_ROLE'."""
