"""SignerPort qua khóa trong biến môi trường (SDD 5.2, 5.6). Phase 2: thay bằng KMS/HSM mà không đổi cổng.

- Khóa đọc MỘT LẦN lúc khởi động, giữ trong thuộc tính riêng; `repr()` không lộ khóa; không có phương thức trả khóa.
- Ba khóa vai trò (báo giá, trọng tài, shipper) phải cho ba địa chỉ KHÁC NHAU, sai thì dừng khởi động.
- Kiểu EIP-712 đọc từ shared/eip712/types.json (nguồn sự thật duy nhất, SDD 8.1).
"""
import json
import os
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_defunct, encode_typed_data
from eth_utils import keccak, to_checksum_address

from ..domain.quote import QUOTE_FIELDS, OrderQuote

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TYPES_PATH = REPO_ROOT / 'shared' / 'eip712' / 'types.json'
ROLE_BY_NAME = {'quote_signer': 'QUOTE_SIGNER_ROLE', 'arbitrator': 'ARBITRATOR_ROLE', 'shipper': 'SHIPPER_ROLE'}


def load_eip712_types(path=None):
    path = Path(path or os.environ.get('EIP712_TYPES_PATH') or DEFAULT_TYPES_PATH)
    return json.loads(path.read_text(encoding='utf-8'))['types']


def recover_personal_sign(message, signature):
    """Khôi phục địa chỉ (chữ thường) từ chữ ký personal_sign. Chữ ký hỏng -> ValueError."""
    try:
        return Account.recover_message(encode_defunct(text=message), signature=signature).lower()
    except Exception as e:     # eth_keys/eth_account ném nhiều loại lỗi tùy dạng chữ ký hỏng
        raise ValueError('chữ ký không khôi phục được') from e


class EnvKeySigner:
    def __init__(self, *, quote_key, chain_id, verifying_contract, arbitrator_key='', shipper_key='', types_path=None):
        self._keys = {'quote_signer': quote_key}
        if arbitrator_key:
            self._keys['arbitrator'] = arbitrator_key
        if shipper_key:
            self._keys['shipper'] = shipper_key
        self._addr = {}
        for role, key in self._keys.items():
            try:
                self._addr[role] = Account.from_key(key).address
            except Exception:
                raise RuntimeError(f"Khóa của vai trò '{role}' không hợp lệ (không in giá trị khóa ra log).")
        if len({a.lower() for a in self._addr.values()}) != len(self._addr):
            raise RuntimeError('Các khóa vai trò (báo giá, trọng tài, shipper) phải cho địa chỉ khác nhau.')
        types = load_eip712_types(types_path)
        if tuple(f['name'] for f in types['OrderQuote']) != QUOTE_FIELDS:
            raise RuntimeError('Thứ tự trường OrderQuote trong types.json lệch với domain/quote.py.')
        self._types = types
        self._domain = {'name': 'SlopeeEscrow', 'version': '1', 'chainId': int(chain_id),
                        'verifyingContract': to_checksum_address(verifying_contract)}

    @classmethod
    def from_settings(cls, s):
        return cls(quote_key=s.quote_signer_key, arbitrator_key=s.arbitrator_key, shipper_key=s.shipper_key,
                   chain_id=s.chain_id, verifying_contract=s.escrow_address)

    def __repr__(self):
        return f"<EnvKeySigner quote_signer={self._addr['quote_signer']}>"

    def verify_against_chain(self, chain):
        """Địa chỉ khóa phải đúng vai trò đã cấp trên contract (SDD 5.6); sai là dừng khởi động."""
        for role, addr in self._addr.items():
            if not chain.has_role(ROLE_BY_NAME[role], addr):
                raise RuntimeError(f"Địa chỉ {addr} chưa được cấp {ROLE_BY_NAME[role]} trên contract. "
                                   "Chạy lại scripts/bootstrap.sh --fresh --force-env.")

    # ---- SignerPort
    def sign_quote(self, quote: OrderQuote):
        full = {
            'types': {'EIP712Domain': [{'name': 'name', 'type': 'string'}, {'name': 'version', 'type': 'string'},
                                       {'name': 'chainId', 'type': 'uint256'},
                                       {'name': 'verifyingContract', 'type': 'address'}],
                      'OrderQuote': self._types['OrderQuote']},
            'primaryType': 'OrderQuote', 'domain': self._domain,
            'message': {name: getattr(quote, name) for name in QUOTE_FIELDS},
        }
        signed = Account.sign_message(encode_typed_data(full_message=full), self._keys['quote_signer'])
        sig = signed.signature.hex()
        return sig if sig.startswith('0x') else '0x' + sig

    def sender_address(self, role):
        return self._addr[role]

    def keccak(self, data):
        return keccak(data)

    def to_checksum(self, address):
        return to_checksum_address(address)
