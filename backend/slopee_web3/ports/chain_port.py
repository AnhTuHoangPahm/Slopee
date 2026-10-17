"""ChainPort (SDD 5.2). Tuần 3: các phương thức đọc. Tuần 5: `send_tx` + `wait_receipt` cho relayer (A); `get_order` + `balance_of` cho tác vụ nền và đối soát (B)."""
from typing import Protocol

ORDER_STATES = ('NONE', 'LOCKED', 'DELIVERED', 'DISPUTED', 'COMPLETED', 'REFUNDED')   # khớp enum OrderState


class ChainUnavailable(Exception):
    """RPC không kết nối được hoặc trả lỗi (adapter ném; application/API ánh xạ sang CHAIN_UNAVAILABLE)."""


class ChainTxFailed(Exception):
    """Giao dịch bị contract từ chối (revert khi ước lượng gas, hoặc biên nhận status = 0). KHÁC ChainUnavailable:
    RPC vẫn sống, lỗi nằm ở nghiệp vụ trên chuỗi, thử lại y nguyên sẽ lại revert."""


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

    def send_tx(self, fn_name: str, args: list, sender: str, sign) -> str:
        """Dựng giao dịch gọi `fn_name(*args)` từ `sender`, ước lượng gas, gọi `sign(tx_dict) -> bytes` (raw đã ký, do
        SignerPort cấp nên khóa không rời signer), gửi đi và trả tx_hash ('0x…'). Chưa chờ biên nhận.
        Ném ChainTxFailed nếu contract revert khi ước lượng; ChainUnavailable nếu RPC lỗi.
        KHÔNG tự tuần tự hóa nonce: người gọi (relayer) phải đảm bảo chỉ một luồng gọi hàm này (DD-06)."""

    def wait_receipt(self, tx_hash: str, timeout: float) -> dict:
        """Chờ biên nhận: {'status': 1|0, 'block_number': int}. Hết `timeout` giây mà chưa có -> ChainUnavailable."""

    def get_order(self, onchain_order_id: int) -> dict:
        """Đọc TRỰC TIẾP `orders(id)`: {'state', 'amount' (int), 'created_at', 'delivered_at', 'disputed_at',
        'dispute_timeout', 'inspection_duration', 'fee_bps', 'buyer', 'merchant', 'token'} (mốc là giây UTC theo block)."""

    def balance_of(self, token_address, at_block=None) -> int:
        """Số dư contract Escrow: ERC-20 `balanceOf(escrow)`; None/0x0 ⇒ ETH. `at_block` đọc tại block đó (đối soát so đúng
        tại block Indexer đã xử lý nên không dương tính giả khi Indexer trễ)."""

    def dispute_nonce(self, onchain_order_id: int) -> int:
        """`disputeNonces(orderId)` trực tiếp từ contract: nonce mà chữ ký phán quyết phải mang (SRS 6)."""
