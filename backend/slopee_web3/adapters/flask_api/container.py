"""Điểm lắp ghép (composition root) của mô-đun Web3: dựng adapter từ cấu hình rồi đưa vào service.

Test gọi `set_container(...)` để thay bằng adapter giả; production dựng lười từ biến môi trường.
Chưa cấu hình Web3 (chưa chạy bootstrap) -> WEB3_NOT_CONFIGURED 503, ứng dụng Slopee cũ vẫn chạy.
"""
import logging
import threading

from ...application.dispute_admin_service import DisputeAdminService
from ...application.dispute_note_service import DisputeNoteService
from ...application.dispute_service import DisputeService
from ...application.dispute_submit_service import DisputeSubmitService
from ...application.jobs import AutoRelease, DeliveryTimeoutReminder, DisputeSigExpiry, QuoteExpirySweeper
from ...application.notification_service import NotificationService
from ...application.order_status_service import OrderStatusService
from ...application.quote_service import QuoteService
from ...application.reconcile_service import ReconcileService
from ...application.relayer_service import RelayerService
from ...application.shipper_service import ShipperService
from ...application.wallet_service import WalletService
from ...domain.errors import DomainError
from ...settings import MAX_BATCH_SIZE, Web3Settings
from ..advisory_lock import MySqlAdvisoryLock
from ..clock import HybridClock
from ..env_signer import EnvKeySigner, recover_personal_sign
from ..mysql_repos import MySqlUnitOfWork
from ..relayer_queue import SingleThreadQueue
from ..scheduler import Job
from ..web3_chain import Web3Chain

log = logging.getLogger('slopee.web3')


class Web3Container:
    def __init__(self, settings, signer, chain, clock, uow_factory, verifier=recover_personal_sign, relayer_queue=None,
                 job_guard=None):
        self.settings, self.signer, self.chain, self.clock = settings, signer, chain, clock
        self.uow_factory = uow_factory
        self.verifier = verifier
        # Hàng đợi relayer PHẢI là một đối tượng duy nhất cho cả tiến trình (DD-06), nên giữ ở container chứ không dựng mỗi lần gọi.
        self.relayer_queue = relayer_queue or SingleThreadQueue()
        self.job_guard = job_guard          # khóa liên tiến trình quanh job gửi giao dịch (Flask + Scheduler dùng chung SHIPPER_KEY)

    def wallet_service(self):
        return WalletService(self.uow_factory, self.verifier, wallet_domain=self.settings.wallet_domain,
                             chain_id=self.settings.chain_id,
                             max_nonces_per_minute=self.settings.nonce_max_per_minute)

    def relayer_service(self):
        return RelayerService(self.uow_factory, self.chain, self.signer, self.relayer_queue, job_guard=self.job_guard)

    def dispute_submit_service(self):
        return DisputeSubmitService(self.uow_factory, self.chain, self.signer, self.clock, self.relayer_service())

    def dispute_admin_service(self):
        return DisputeAdminService(self.uow_factory, self.clock)

    def shipper_service(self):
        return ShipperService(self.uow_factory, self.relayer_service())

    def dispute_service(self):
        return DisputeService(self.uow_factory, self.chain, self.signer, self.clock, token_decimals=self.settings.token_decimals)

    def dispute_note_service(self):
        return DisputeNoteService(self.uow_factory)

    def notification_service(self):
        return NotificationService(self.uow_factory)

    def reconcile_service(self):
        return ReconcileService(self.uow_factory, self.chain, known_tokens=[self.settings.token_address],
                                confirmations=self.settings.confirmations)

    def jobs(self):
        """Danh sách tác vụ nền cho Scheduler (SDD 5.5)."""
        s = self.settings
        sweeper = QuoteExpirySweeper(self.uow_factory, self.chain, self.clock, grace=s.quote_expiry_grace_seconds)
        release = AutoRelease(self.uow_factory, self.chain, self.clock, self.relayer_service())
        reminder = DeliveryTimeoutReminder(self.uow_factory, self.chain, self.clock)
        dispute_expiry = DisputeSigExpiry(self.uow_factory, self.clock)

        def reconcile_snapshot():
            r = self.reconcile_service().run()
            if not r['ok']:
                log.error('ĐỐI SOÁT LỆCH: %s', r['tokens'])
            return {'ok': r['ok'], 'indexer_lag_blocks': r['indexer_lag_blocks']}
        return [Job('QuoteExpirySweeper', s.quote_sweep_seconds, sweeper.run_once),
                Job('AutoRelease', s.auto_release_seconds, release.run_once),
                Job('DeliveryTimeoutReminder', s.timeout_reminder_seconds, reminder.run_once),
                Job('DisputeSigExpiry', s.dispute_expiry_seconds, dispute_expiry.run_once),
                Job('ReconcileSnapshot', s.reconcile_seconds, reconcile_snapshot)]

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
    return Web3Container(settings, signer, chain, HybridClock(chain), lambda: MySqlUnitOfWork(get_connection),
                         job_guard=MySqlAdvisoryLock(get_connection, timeout=settings.relayer_lock_seconds))


def get_container(get_connection):
    global _container
    if _container is None:
        with _lock:
            if _container is None:
                _container = build_container(get_connection)
    return _container
