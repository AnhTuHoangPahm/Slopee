"""Cấu hình Web3 đọc từ biến môi trường (SDD 12.2). Tỷ giá/hạn báo giá/phí nằm ở `platform_settings`, KHÔNG ở đây."""
import os
from dataclasses import dataclass

MAX_BATCH_SIZE = 5


@dataclass(frozen=True)
class Web3Settings:
    rpc_url: str
    chain_id: int
    escrow_address: str
    token_address: str
    token_decimals: int = 6
    token_symbol: str = 'mUSD'
    quote_signer_key: str = ''
    arbitrator_key: str = ''
    shipper_key: str = ''
    wallet_domain: str = 'localhost:5173'     # tên miền trong thông điệp SIWE (origin của frontend)
    nonce_max_per_minute: int = 5
    poll_seconds: float = 2.0
    confirmations: int = 0
    reorg_depth: int = 20
    indexer_start_block: int = 0
    rpc_timeout: float = 5.0
    # Tác vụ nền (SDD 5.5), giây; đặt qua biến môi trường để demo/test rút ngắn
    quote_sweep_seconds: float = 60.0
    auto_release_seconds: float = 60.0
    timeout_reminder_seconds: float = 3600.0
    reconcile_seconds: float = 600.0
    quote_expiry_grace_seconds: int = 30
    relayer_lock_seconds: int = 30            # chờ khóa GET_LOCK của relayer tối đa chừng này giây

    @classmethod
    def from_env(cls, env=None):
        """Trả None nếu chưa cấu hình Web3 (chưa chạy bootstrap) — ứng dụng cũ vẫn chạy bình thường."""
        env = os.environ if env is None else env
        if not (env.get('ESCROW_ADDRESS') and env.get('MOCKUSD_ADDRESS') and env.get('QUOTE_SIGNER_KEY')):
            return None
        return cls(
            rpc_url=env.get('RPC_URL', 'http://127.0.0.1:8545'),
            chain_id=int(env.get('CHAIN_ID', 31337)),
            escrow_address=env['ESCROW_ADDRESS'],
            token_address=env['MOCKUSD_ADDRESS'],
            token_decimals=int(env.get('TOKEN_DECIMALS', 6)),
            token_symbol=env.get('TOKEN_SYMBOL', 'mUSD'),
            quote_signer_key=env['QUOTE_SIGNER_KEY'],
            arbitrator_key=env.get('ARBITRATOR_KEY', ''),
            shipper_key=env.get('SHIPPER_KEY', ''),
            wallet_domain=env.get('WALLET_LINK_DOMAIN', 'localhost:5173'),
            nonce_max_per_minute=int(env.get('WALLET_NONCE_MAX_PER_MINUTE', 5)),
            poll_seconds=float(env.get('POLL_SECONDS', 2)),
            confirmations=int(env.get('CONFIRMATIONS', 0)),
            reorg_depth=int(env.get('REORG_DEPTH', 20)),
            indexer_start_block=int(env.get('INDEXER_START_BLOCK', 0)),
            quote_sweep_seconds=float(env.get('QUOTE_SWEEP_SECONDS', 60)),
            auto_release_seconds=float(env.get('AUTO_RELEASE_SECONDS', 60)),
            timeout_reminder_seconds=float(env.get('TIMEOUT_REMINDER_SECONDS', 3600)),
            reconcile_seconds=float(env.get('RECONCILE_SECONDS', 600)),
            quote_expiry_grace_seconds=int(env.get('QUOTE_EXPIRY_GRACE_SECONDS', 30)),
            relayer_lock_seconds=int(env.get('RELAYER_LOCK_SECONDS', 30)),
        )
