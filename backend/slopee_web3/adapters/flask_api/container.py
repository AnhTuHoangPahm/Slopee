"""Điểm lắp ghép (composition root) của mô-đun Web3: dựng adapter từ cấu hình rồi đưa vào service.

Test gọi `set_container(...)` để thay bằng adapter giả; production dựng lười từ biến môi trường.
Chưa cấu hình Web3 (chưa chạy bootstrap) -> WEB3_NOT_CONFIGURED 503, ứng dụng Slopee cũ vẫn chạy.
"""
import logging
import threading

from ...application.order_status_service import OrderStatusService
from ...application.quote_service import QuoteService
from ...application.relayer_service import RelayerService
from ...application.wallet_service import WalletService
from ...domain.errors import DomainError
from ...settings import MAX_BATCH_SIZE, Web3Settings
from ..clock import HybridClock
from ..env_signer import EnvKeySigner, recover_personal_sign
from ..mysql_repos import MySqlUnitOfWork
from ..relayer_queue import SingleThreadQueue
from ..web3_chain import Web3Chain

log = logging.getLogger('slopee.web3')


class Web3Container:
    def __init__(self, settings, signer, chain, clock, uow_factory, verifier=recover_personal_sign, relayer_queue=None):
        self.settings, self.signer, self.chain, self.clock = settings, signer, chain, clock
        self.uow_factory = uow_factory
        self.verifier = verifier
        # Hàng đợi relayer PHẢI là một đối tượng duy nhất cho cả tiến trình (DD-06), nên giữ ở container chứ không dựng mỗi lần gọi.
        self.relayer_queue = relayer_queue or SingleThreadQueue()

    def wallet_service(self):
        return WalletService(self.uow_factory, self.verifier, wallet_domain=self.settings.wallet_domain,
                             chain_id=self.settings.chain_id,
                             max_nonces_per_minute=self.settings.nonce_max_per_minute)

    def relayer_service(self):
        """Việc của Thành viên B (ShipperService, AutoRelease) gọi `confirm_delivery(order_id, onchain_order_id)`."""
        return RelayerService(self.uow_factory, self.chain, self.signer, self.relayer_queue)

    def order_status_service(self):
        return OrderStatusService(self.uow_factory, self.clock)

    def quote_service(self):
        s = self.settings
        return QuoteService(self.uow_factory, self.signer, self.chain, self.clock, token_address=s.token_address,
                            token_decimals=s.token_decimals, token_symbol=s.token_symbol, max_batch=MAX_BATCH_SIZE)


_container = None
_lock = threading.Lock()


def set_container(c):
    global _container
    _container = c


def build_container(get_connection, settings=None):
    settings = settings or Web3Settings.from_env()
    if settings is None:
        raise DomainError('WEB3_NOT_CONFIGURED', 'Tính năng thanh toán Web3 chưa được cấu hình trên máy chủ.')
    signer = EnvKeySigner.from_settings(settings)
    chain = Web3Chain(settings.rpc_url, settings.escrow_address, timeout=settings.rpc_timeout)
    signer.verify_against_chain(chain)      # địa chỉ khóa phải đúng vai trò trên contract, sai là dừng (SDD 5.6)
    return Web3Container(settings, signer, chain, HybridClock(chain), lambda: MySqlUnitOfWork(get_connection))


def get_container(get_connection):
    global _container
    if _container is None:
        with _lock:
            if _container is None:
                _container = build_container(get_connection)
    return _container
