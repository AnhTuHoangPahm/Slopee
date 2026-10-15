"""WalletService (MOD-01, UC-00): cấp nonce, xác minh chữ ký liên kết ví, đổi ví."""
import secrets

from ..domain import wallet as w
from ..domain.errors import DomainError
from ..ports.repositories import DuplicateWallet


class WalletService:
    def __init__(self, uow_factory, verifier, *, wallet_domain, chain_id, max_nonces_per_minute=5):
        """verifier(message: str, signature: str) -> địa chỉ khôi phục (chữ thường); ném ValueError nếu chữ ký hỏng."""
        self._uow = uow_factory
        self._verify = verifier
        self._domain = wallet_domain
        self._chain_id = chain_id
        self._max_per_minute = max_nonces_per_minute

    def issue_nonce(self, user_id, address):
        address = w.normalize_address(address)
        with self._uow() as uow:
            # Giới hạn tần suất theo tài khoản (SDD 10.2): đếm nonce còn hạn được cấp trong 60 giây gần nhất.
            if uow.wallets.count_recent_nonces(user_id, 60, w.NONCE_TTL_SECONDS) >= self._max_per_minute:
                raise DomainError('RATE_LIMITED', 'Bạn yêu cầu quá nhanh, hãy thử lại sau ít phút.')
            nonce = secrets.token_hex(16)
            expires_at = uow.wallets.insert_nonce(nonce, user_id, w.NONCE_TTL_SECONDS)
            uow.commit()
        message = w.build_link_message(self._domain, address, user_id, nonce, self._chain_id,
                                       expires_at - w.NONCE_TTL_SECONDS, expires_at)
        return {'nonce': nonce, 'message': message, 'expires_at': expires_at}

    def link_wallet(self, user_id, address, signature, nonce=None):
        address = w.normalize_address(address)
        signature = w.normalize_signature(signature)
        if nonce is not None and not w.is_valid_nonce(nonce):
            raise DomainError('NONCE_INVALID', 'Mã xác thực đã hết hạn hoặc đã được dùng, hãy thử lại.')
        with self._uow() as uow:
            row = uow.wallets.find_nonce(user_id, nonce)
            if row is None:
                raise DomainError('NONCE_INVALID', 'Mã xác thực đã hết hạn hoặc đã được dùng, hãy thử lại.')
            # Backend tự dựng lại thông điệp từ dữ liệu của mình, không tin thông điệp do client gửi.
            message = w.build_link_message(self._domain, address, user_id, row['nonce'], self._chain_id,
                                           row['expires_at'] - w.NONCE_TTL_SECONDS, row['expires_at'])
            try:
                recovered = self._verify(message, signature)
            except ValueError:
                raise DomainError('BAD_SIGNATURE', 'Chữ ký không hợp lệ.')
            if recovered.lower() != address:
                raise DomainError('BAD_SIGNATURE', 'Chữ ký không khớp với ví đã chọn.')

            # Từ đây mới ghi. Mọi lỗi sau điểm này rollback cả việc tiêu thụ nonce.
            existing = uow.wallets.wallet_by_address(address)
            if existing is not None and existing['user_id'] != user_id:
                raise DomainError('WALLET_TAKEN', 'Ví này đã được liên kết với một tài khoản khác.')
            if not uow.wallets.consume_nonce(row['nonce'], user_id):
                raise DomainError('NONCE_INVALID', 'Mã xác thực đã hết hạn hoặc đã được dùng, hãy thử lại.')

            if existing is not None and existing['is_active']:
                linked_at = existing['linked_at']            # liên kết lại đúng ví đang dùng: idempotent
            else:
                # Đổi ví: ví cũ -> is_active = 0. Chỉ UPDATE khi thật sự có ví đang dùng: UPDATE không khớp dòng nào
                # vẫn khóa khoảng trên idx_wallet_user và làm hai tài khoản mới liên kết song song deadlock.
                if uow.wallets.active_wallet(user_id) is not None:
                    uow.wallets.deactivate_user_wallets(user_id)
                if existing is not None:                      # ví cũ của chính mình được bật lại
                    uow.wallets.activate_wallet(existing['id'])
                    linked_at = existing['linked_at']
                else:
                    try:
                        linked_at = uow.wallets.insert_wallet(user_id, address)
                    except DuplicateWallet:
                        raise DomainError('WALLET_TAKEN', 'Ví này đã được liên kết với một tài khoản khác.')
            uow.commit()
        return {'address': address, 'linked_at': linked_at}

    def get_wallet(self, user_id):
        with self._uow() as uow:
            row = uow.wallets.active_wallet(user_id)
        if row is None:
            return {'linked': False, 'address': None, 'linked_at': None}
        return {'linked': True, 'address': row['address'], 'linked_at': row['linked_at']}
