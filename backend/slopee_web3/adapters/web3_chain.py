"""ChainPort qua web3.py vào Anvil (SDD 5.2). Mọi lỗi mạng/RPC -> ChainUnavailable."""
import json
from pathlib import Path

from eth_utils import keccak, to_checksum_address
from web3 import Web3
from web3.exceptions import ContractLogicError

from ..ports.chain_port import ORDER_STATES, ChainTxFailed, ChainUnavailable

ABI_PATH = Path(__file__).resolve().parents[3] / 'shared' / 'abi' / 'SlopeeEscrowMaster.json'


def load_abi(path=None):
    raw = json.loads(Path(path or ABI_PATH).read_text(encoding='utf-8'))
    return raw['abi'] if isinstance(raw, dict) and 'abi' in raw else raw


def _hex(v):
    """HexBytes/bytes/str -> chuỗi '0x…' (hexbytes mới trả .hex() KHÔNG có tiền tố 0x)."""
    if isinstance(v, str):
        return v if v.startswith('0x') else '0x' + v
    return '0x' + bytes(v).hex()


def _unavailable(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except (ChainUnavailable, ChainTxFailed):
            raise
        except Exception as e:      # ConnectionError, Timeout, ProviderConnectionError, ContractLogicError...
            raise ChainUnavailable(f'{type(e).__name__}: {e}') from e
    wrapper.__name__ = fn.__name__
    return wrapper


class Web3Chain:
    def __init__(self, rpc_url, escrow_address, abi=None, timeout=5.0):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': timeout}))
        self.address = to_checksum_address(escrow_address)
        self.abi = abi or load_abi()
        self.contract = self.w3.eth.contract(address=self.address, abi=self.abi)
        self._events = {e['name']: e for e in self.abi if e['type'] == 'event'}
        self._topic0 = {'0x' + keccak(text=f"{e['name']}({','.join(i['type'] for i in e['inputs'])})").hex(): e['name']
                        for e in self._events.values()}

    @_unavailable
    def get_order_state(self, onchain_order_id):
        return ORDER_STATES[int(self.contract.functions.orders(int(onchain_order_id)).call()[10])]

    @_unavailable
    def default_fee_bps(self):
        return int(self.contract.functions.defaultFeeBps().call())

    @_unavailable
    def chain_id(self):
        return int(self.w3.eth.chain_id)

    @_unavailable
    def latest_block(self):
        b = self.w3.eth.get_block('latest')
        return {'number': int(b['number']), 'timestamp': int(b['timestamp']), 'hash': _hex(b['hash'])}

    @_unavailable
    def get_block(self, number):
        b = self.w3.eth.get_block(int(number))
        return {'number': int(b['number']), 'timestamp': int(b['timestamp']), 'hash': _hex(b['hash'])}

    @_unavailable
    def has_role(self, role, address):
        role_id = getattr(self.contract.functions, role)().call()
        return bool(self.contract.functions.hasRole(role_id, to_checksum_address(address)).call())

    @_unavailable
    def get_logs(self, from_block, to_block):
        """Log của Escrow trong [from_block, to_block], đã giải mã, sắp theo (blockNumber, logIndex)."""
        raw = self.w3.eth.get_logs({'fromBlock': int(from_block), 'toBlock': int(to_block), 'address': self.address})
        out = []
        for log in raw:
            name = self._topic0.get(_hex(log['topics'][0])) if log['topics'] else None
            if name is None:
                continue                      # sự kiện lạ (ví dụ của OpenZeppelin ngoài ABI) -> bỏ qua
            ev = getattr(self.contract.events, name)().process_log(log)
            out.append({
                'event': name, 'tx_hash': _hex(ev['transactionHash']),
                'log_index': int(ev['logIndex']), 'block_number': int(ev['blockNumber']),
                'block_hash': _hex(ev['blockHash']),
                'args': {k: (_hex(v) if isinstance(v, (bytes, bytearray)) else v) for k, v in dict(ev['args']).items()},
            })
        out.sort(key=lambda e: (e['block_number'], e['log_index']))
        return out

    # ---- relayer (Tuần 5). Người gọi PHẢI tuần tự hóa (hàng đợi một luồng, DD-06): nonce lấy từ 'pending' ở đây
    # chỉ đúng khi không có giao dịch nào khác của cùng tài khoản đang được dựng song song.
    GAS_MARGIN = 1.2

    @_unavailable
    def send_tx(self, fn_name, args, sender, sign):
        fn = getattr(self.contract.functions, fn_name)(*args)
        sender = to_checksum_address(sender)
        try:
            gas = fn.estimate_gas({'from': sender})
        except ContractLogicError as e:         # revert khi mô phỏng: nghiệp vụ sai, không phải RPC hỏng
            raise ChainTxFailed(str(e)) from e
        tx = fn.build_transaction({
            'from': sender, 'gas': int(gas * self.GAS_MARGIN) + 1,
            'nonce': self.w3.eth.get_transaction_count(sender, 'pending'), 'chainId': int(self.w3.eth.chain_id),
        })
        return _hex(self.w3.eth.send_raw_transaction(sign(tx)))

    @_unavailable
    def wait_receipt(self, tx_hash, timeout):
        r = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout, poll_latency=0.2)
        return {'status': int(r['status']), 'block_number': int(r['blockNumber'])}
