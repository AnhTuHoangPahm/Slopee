"""SignerPort (SDD 5.2): chỉ nhận dữ liệu có cấu trúc và trả chữ ký; KHÔNG có phương thức trả khóa ra ngoài."""
from typing import Protocol

from ..domain.dispute import DisputeResolution
from ..domain.quote import OrderQuote


class SignerPort(Protocol):
    def sign_quote(self, quote: OrderQuote) -> str:
        """Chữ ký EIP-712 65 byte (0x…, v = 27/28) của QUOTE_SIGNER_ROLE."""

    def sender_address(self, role: str) -> str:
        """Địa chỉ (checksum) của vai trò: 'quote_signer' | 'arbitrator' | 'shipper'."""

    def keccak(self, data: bytes) -> bytes:
        """keccak256 — để domain tính docHash mà không phụ thuộc thư viện băm."""

    def to_checksum(self, address: str) -> str:
        """Địa chỉ dạng checksum (EIP-55) để hiển thị và đưa vào báo giá."""

    def sign_transaction(self, role: str, tx: dict) -> bytes:
        """Ký giao dịch (đã đủ nonce/gas/chainId) bằng khóa của vai trò, trả raw transaction. Khóa không bao giờ rời signer."""

    def sign_dispute(self, resolution: DisputeResolution) -> str:
        """Chữ ký EIP-712 65 byte của ARBITRATOR cho phán quyết (UC-06 bước 2)."""

    def recover_dispute_signer(self, resolution: DisputeResolution, signature: str) -> str:
        """Địa chỉ (checksum) ký `resolution`. Chữ ký hỏng -> ValueError. Dùng để kiểm chữ ký Buyer/Merchant/Arbitrator."""
