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
        )
