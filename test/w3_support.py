"""Hỗ trợ test Tuần 3 (UC-00/UC-01/Indexer): khóa thử Anvil, chuỗi giả, seed MySQL, dựng service.

Khóa dưới đây là KHÓA THỬ CÔNG KHAI CỦA ANVIL (giống scripts/gen_eip712_vectors.py): bài quét E-05 (AC-09) phải cho phép.
"""
import json
import os
import threading
import time
import uuid
from pathlib import Path

import pymysql
from eth_account import Account
from eth_account.messages import encode_defunct, encode_typed_data

from slopee_web3.adapters.clock import FixedClock
from slopee_web3.adapters.env_signer import EnvKeySigner, recover_personal_sign
from slopee_web3.adapters.mysql_repos import MySqlUnitOfWork
from slopee_web3.application.order_status_service import OrderStatusService
from slopee_web3.application.quote_service import QuoteService
from slopee_web3.application.wallet_service import WalletService
from slopee_web3.ports.chain_port import ChainTxFailed, ChainUnavailable

ROOT = Path(__file__).resolve().parent.parent
VECTORS = json.loads((ROOT / 'shared' / 'eip712' / 'vectors.json').read_text(encoding='utf-8'))

CHAIN_ID = 31337
ESCROW = VECTORS['domain']['verifyingContract']
TOKEN = '0x5FbDB2315678afecb367f032d93F642f64180aa3'   # MockUSD của bootstrap (deployer #0, nonce 0)

KEYS = {   # khóa mặc định của Anvil
    'shipper': '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d',      # #1
    'arbitrator': '0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a',   # #2
    'quote_signer': '0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6',  # #3
    'buyer': '0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba',        # #5
    'merchant1': '0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e',    # #6
    'merchant2': '0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356',    # #7
    'merchant3': '0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97',    # #8
    'merchant4': '0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6',    # #9
    'merchant5': '0xf214f2b2cd398c806f84e317254e0f2b801d0643303237d97a22a48e01628897',    # #10
    'merchant6': '0x701b615bbdfb9de65240bc28bd21bbc0d996645a3dd57e5b0b1cb4a7bc0e3cb6',    # #11 (cho ca BATCH_TOO_LARGE)
    'stranger': '0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a',     # #12
}
ADDR = {name: Account.from_key(k).address for name, k in KEYS.items()}
DOMAIN = 'localhost:5173'


class FakeChain:
    """ChainPort giả: trần phí, trạng thái đơn theo mã, block mới nhất; có thể 'rớt mạng'."""

    def __init__(self, fee_cap=300, block_ts=1_800_000_000):
        self.fee_cap = fee_cap
        self.block_ts = block_ts
        self.states = {}
        self.available = True
        self.logs = []
        self.blocks = {}      # {số block: {'timestamp', 'hash'}} ghi đè mặc định
        self.head = 0         # block mới nhất

    def _check(self):
        if not self.available:
            raise ChainUnavailable('RPC down (giả lập)')

    def get_order_state(self, onchain_order_id):
        self._check()
        return self.states.get(int(onchain_order_id), 'NONE')

    def default_fee_bps(self):
        self._check()
        return self.fee_cap

    def latest_block(self):
        return self.get_block(self.head)

    def get_block(self, number):
        self._check()
        b = {'number': number, 'timestamp': self.block_ts + number, 'hash': '0x' + format(number, '064x')}
        b.update(self.blocks.get(number, {}))
        return b

    def get_logs(self, from_block, to_block):
        self._check()
        return [e for e in self.logs if from_block <= e['block_number'] <= to_block]

    def has_role(self, role, address):
        return True


class RelayChain:
    """ChainPort giả cho relayer (Tuần 5): trạng thái đơn theo mã, send_tx đo độ song song và nonce, receipt cấu hình được."""

    def __init__(self):
        self.states = {}
        self.sent = []                  # [(fn, args, sender, nonce)]
        self.in_flight = 0
        self.max_in_flight = 0
        self.nonce = 0
        self.send_delay = 0.0
        self.revert = False
        self.down = False
        self.receipt_status = 1
        self.receipt_timeout = False
        self.mine_on_send = True        # gửi xong coi như đã DELIVERED (như contract thật sau khi được đào)
        self._lock = threading.Lock()

    def get_order_state(self, oid):
        if self.down:
            raise ChainUnavailable('RPC down')
        return self.states.get(int(oid), 'NONE')

    def send_tx(self, fn, args, sender, sign):
        if self.down:
            raise ChainUnavailable('RPC down')
        with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            time.sleep(self.send_delay)
            if self.revert:
                raise ChainTxFailed('execution reverted: Invalid state')
            with self._lock:
                n = self.nonce
                self.nonce += 1
            raw = sign({'to': ADDR['quote_signer'], 'value': 0, 'gas': 100000, 'gasPrice': 10 ** 9, 'nonce': n,
                        'chainId': CHAIN_ID, 'data': b''})
            assert isinstance(raw, (bytes, bytearray)) and len(raw) > 0
            self.sent.append((fn, list(args), sender, n))
            if self.mine_on_send:
                self.states[int(args[0])] = 'DELIVERED'
            return '0x' + format(len(self.sent), '064x')
        finally:
            with self._lock:
                self.in_flight -= 1

    def wait_receipt(self, tx_hash, timeout):
        if self.receipt_timeout:
            raise ChainUnavailable('TimeExhausted')
        return {'status': self.receipt_status, 'block_number': 7}


class FakeEscrowChain(FakeChain):
    """Contract Escrow giả (Tuần 5, B): mô hình ĐÚNG máy trạng thái + điều kiện thời gian của SlopeeEscrowMaster, phát log đúng
    hình dạng Web3Chain.get_logs, ghi số dư theo block. Dùng để chạy luồng đầy đủ qua Indexer + relayer + tác vụ nền thật trên MySQL.

    Thời gian: `now` là timestamp của block kế tiếp; mỗi giao dịch đào một block mới có timestamp `now`; `advance(s)` tua `now`
    và đào một block rỗng (như evm_increaseTime + evm_mine) để block mới nhất bắt kịp.
    """

    def __init__(self, now=1_800_000_000, fee_cap=300):
        super().__init__(fee_cap=fee_cap, block_ts=now)
        self.now = now
        self.times = {0: now}
        self.orders = {}               # onchain_id -> dict giống struct Order
        self.balances = [(0, 0)]       # [(block, số dư token của contract)]
        self.pending = {}              # {(token, to): amount} cho PayoutDeferred
        self.eth_balance = 0           # số dư ETH của contract (chỉ để test đối soát nhánh ETH; không theo block)
        self.sent_txs = []
        self.dispute_nonces = {}       # {onchain_id: nonce} như `disputeNonces`
        self.last_msg_sender = None    # địa chỉ khôi phục từ raw tx của lần send_tx gần nhất (= msg.sender trên chuỗi thật)

    # ---- đồng hồ / block
    def get_block(self, number):
        self._check()
        b = {'number': number, 'timestamp': self.times.get(number, self.now), 'hash': '0x' + format(number, '064x')}
        b.update(self.blocks.get(number, {}))          # ghi đè hash để mô phỏng reorg
        return b

    def _mine(self, *evs):
        """Đào MỘT block chứa các sự kiện (name, args) theo thứ tự; trả block number."""
        self.head += 1
        self.times[self.head] = self.now
        for i, (name, args) in enumerate(evs):
            self.logs.append(event(name, self.head, i, **args))
        return self.head

    def advance(self, seconds):
        self.now += int(seconds)
        self._mine()

    def _balance_delta(self, delta):
        self.balances.append((self.head, self.balances[-1][1] + delta))

    # ---- ChainPort đọc
    def get_order_state(self, onchain_order_id):
        self._check()
        return self.orders.get(int(onchain_order_id), {}).get('state', 'NONE')

    def get_order(self, onchain_order_id):
        self._check()
        o = self.orders.get(int(onchain_order_id))
        if o is None:
            return {'state': 'NONE', 'amount': 0, 'created_at': 0, 'delivered_at': 0, 'disputed_at': 0,
                    'dispute_timeout': 0, 'inspection_duration': 0, 'fee_bps': 0, 'buyer': '', 'merchant': '', 'token': ''}
        return dict(o)

    def dispute_nonce(self, onchain_order_id):
        self._check()
        return self.dispute_nonces.get(int(onchain_order_id), 0)

    def balance_of(self, token_address, at_block=None):
        self._check()
        if token_address is None or str(token_address).lower() == '0x' + '0' * 40:
            return self.eth_balance
        if at_block is None:
            return self.balances[-1][1]
        return [b for blk, b in self.balances if blk <= int(at_block)][-1]

    # ---- hành động của người dùng trên chuỗi (test gọi trực tiếp, như MetaMask)
    def deposit(self, quote):
        """Buyer nạp theo báo giá (dict `quote` của API): LOCKED + OrderCreated + tiền vào contract."""
        oid = int(quote['orderId'])
        assert oid not in self.orders, 'Order exists'
        self.orders[oid] = {'state': 'LOCKED', 'buyer': quote['buyer'], 'merchant': quote['merchant'], 'token': quote['token'],
                            'amount': int(quote['amount']), 'created_at': self.now, 'delivered_at': 0, 'disputed_at': 0,
                            'dispute_timeout': int(quote['disputeTimeout']),
                            'inspection_duration': int(quote['inspectionDuration']), 'fee_bps': int(quote['feeBps'])}
        blk = self._mine(('OrderCreated', dict(orderId=oid, buyer=quote['buyer'], merchant=quote['merchant'], token=quote['token'],
                                              amount=int(quote['amount']), inspectionDuration=int(quote['inspectionDuration']),
                                              disputeTimeout=int(quote['disputeTimeout']), docHash=quote['docHash'],
                                              feeBps=int(quote['feeBps']))))
        self._balance_delta(int(quote['amount']))
        return blk

    def _payout(self, oid, o):
        fee = o['amount'] * o['fee_bps'] // 10000
        return o['amount'] - fee, fee

    def early_release(self, oid):
        o = self.orders[int(oid)]
        assert o['state'] == 'DELIVERED', 'Not delivered'
        return self._complete(int(oid), o)

    def _complete(self, oid, o):
        net, fee = self._payout(oid, o)
        o['state'] = 'COMPLETED'
        blk = self._mine(('OrderCompleted', dict(orderId=oid, netPayout=net, feeAmount=fee)))
        self._balance_delta(-o['amount'])
        return blk

    def raise_dispute(self, oid):
        o = self.orders[int(oid)]
        assert o['state'] == 'DELIVERED' and self.now < o['delivered_at'] + o['inspection_duration']
        o['state'], o['disputed_at'] = 'DISPUTED', self.now
        return self._mine(('OrderDisputed', dict(orderId=int(oid), raisedBy=o['buyer'], disputedAt=self.now)))

    def cancel_if_unfulfilled(self, oid):
        o = self.orders[int(oid)]
        assert o['state'] == 'LOCKED' and self.now >= o['created_at'] + 14 * 86400, 'Timeout not reached'
        return self._refund(int(oid), o)

    def _refund(self, oid, o):
        o['state'] = 'REFUNDED'
        blk = self._mine(('OrderRefunded', dict(orderId=oid, to=o['buyer'], amount=o['amount'])))
        self._balance_delta(-o['amount'])
        return blk

    def arbitrator_force_resolve(self, oid, payout_to):
        """UC-07: Trọng tài xử đơn phương, chỉ khi đã qua disputedAt + disputeTimeout. Sự kiện đặt SAU OrderCompleted/OrderRefunded như contract."""
        oid, o = int(oid), self.orders[int(oid)]
        if o['state'] != 'DISPUTED' or self.now < o['disputed_at'] + o['dispute_timeout']:
            raise ChainTxFailed('execution reverted: Dispute timeout not reached')
        if str(payout_to).lower() == o['buyer'].lower():
            self._refund(oid, o)
        else:
            self._complete(oid, o)
        return self._mine(('ArbitratorForceResolved', dict(orderId=oid, payoutTo=payout_to)))

    def defer_payout(self, token, to, amount):
        """ETH: người nhận từ chối -> sổ chờ rút (PayoutDeferred)."""
        self.pending[(token, to)] = self.pending.get((token, to), 0) + int(amount)
        return self._mine(('PayoutDeferred', dict(token=token, to=to, amount=int(amount))))

    def claim_pending(self, token, to):
        amount = self.pending.pop((token, to))
        return self._mine(('PendingClaimed', dict(token=token, to=to, amount=amount)))

    def stray_transfer(self, amount):
        """Token chuyển thẳng vào contract ngoài luồng đơn (đối soát phải báo lệch)."""
        self._mine()
        self._balance_delta(int(amount))

    # ---- relayer: send_tx / wait_receipt như contract thật (revert khi sai trạng thái/chưa tới hạn)
    def send_tx(self, fn, args, sender, sign):
        self._check()
        oid = int(args[0])
        o = self.orders.get(oid)
        if o is None:
            raise ChainTxFailed('execution reverted: no such order')
        raw = sign({'to': ADDR['quote_signer'], 'value': 0, 'gas': 100000, 'gasPrice': 10 ** 9, 'nonce': len(self.sent_txs),
                    'chainId': CHAIN_ID, 'data': b''})          # đi qua đường ký thật của EnvKeySigner
        # `msg.sender` trên chuỗi thật là NGƯỜI KÝ giao dịch (không phải tham số `sender` chỉ dùng để ước lượng gas): khôi phục từ raw tx.
        try:
            self.last_msg_sender = Account.recover_transaction(bytes(raw))
        except Exception:      # noqa: BLE001 - một số test dùng hàm ký giả trả bytes rỗng: không có người ký để khôi phục
            self.last_msg_sender = None
        if fn == 'confirmDelivery':
            if o['state'] != 'LOCKED':
                raise ChainTxFailed('execution reverted: Not locked')
            o['state'], o['delivered_at'] = 'DELIVERED', self.now
            self._mine(('OrderDelivered', dict(orderId=oid, deliveredAt=self.now)))
        elif fn == 'releaseAfterInspection':
            if o['state'] != 'DELIVERED':
                raise ChainTxFailed('execution reverted: Not delivered')
            if self.now < o['delivered_at'] + o['inspection_duration']:
                raise ChainTxFailed('execution reverted: Under inspection')
            self._complete(oid, o)
        elif fn == 'resolveDispute':
            self._resolve_dispute(oid, o, args)
        elif fn == 'arbitratorForceResolve':
            if (self.last_msg_sender or '').lower() != ADDR['arbitrator'].lower():       # onlyRole(ARBITRATOR_ROLE)
                raise ChainTxFailed('execution reverted: AccessControl: account is missing role ARBITRATOR_ROLE')
            self.arbitrator_force_resolve(oid, args[1])
        else:
            raise AssertionError(fn)
        self.sent_txs.append((fn, oid, sender))
        return '0x' + format(len(self.sent_txs), '064x')

    def _resolve_dispute(self, oid, o, args):
        """Mô hình `resolveDispute` của contract: cùng thứ tự kiểm, cùng thông điệp revert; chữ ký khôi phục bằng eth_account trực tiếp."""
        _, payout, deadline, sig1, sig2 = args
        deadline = int(deadline)
        if o['state'] != 'DISPUTED':
            raise ChainTxFailed('execution reverted: Not disputed')
        if str(payout).lower() not in (o['buyer'].lower(), o['merchant'].lower()):
            raise ChainTxFailed('execution reverted: Invalid payout recipient')
        if self.now > deadline:
            raise ChainTxFailed('execution reverted: Signature expired')
        if not deadline < o['disputed_at'] + o['dispute_timeout']:
            raise ChainTxFailed('execution reverted: Deadline must be before dispute timeout')
        nonce = self.dispute_nonces.get(oid, 0)
        parties = {o['buyer'].lower(): 1, o['merchant'].lower(): 2, ADDR['arbitrator'].lower(): 3}
        got = []
        for sig in (sig1, sig2):
            try:
                who = Account.recover_message(encode_typed_data(full_message=dispute_typed_data(oid, payout, o['amount'], nonce, deadline)),
                                              signature=bytes(sig))
            except Exception:
                raise ChainTxFailed('execution reverted: ECDSAInvalidSignature')
            got.append(parties.get(who.lower(), 0))
        if 0 in got or got[0] == got[1]:
            raise ChainTxFailed('execution reverted: Need two distinct parties')
        self.dispute_nonces[oid] = nonce + 1               # chỉ ghi khi KHÔNG revert (revert hoàn tác mức tăng nonce)
        if str(payout).lower() == o['buyer'].lower():
            self._refund(oid, o)
        else:
            self._complete(oid, o)
        self._mine(('DisputeResolved', dict(orderId=oid, payoutTo=payout, amount=o['amount'])))

    def wait_receipt(self, tx_hash, timeout):
        return {'status': 1, 'block_number': self.head}


class MemoryOutbox:
    """Bảng tx_outbox trong bộ nhớ, đúng máy trạng thái của MySqlOutboxRepo (chuyển có điều kiện trạng thái cũ)."""

    def __init__(self):
        self.rows = []
        self.lock = threading.Lock()

    def insert(self, kind, order_id):
        with self.lock:
            self.rows.append({'id': len(self.rows) + 1, 'kind': kind, 'order_id': order_id, 'tx_hash': None,
                              'status': 'PENDING', 'error': None})
            return len(self.rows)

    def _row(self, oid):
        return self.rows[oid - 1]

    def mark_sent(self, oid, tx_hash):
        r = self._row(oid)
        if r['status'] == 'PENDING':
            r.update(status='SENT', tx_hash=tx_hash)

    def mark_confirmed(self, oid):
        r = self._row(oid)
        if r['status'] == 'SENT':
            r['status'] = 'CONFIRMED'

    def mark_failed(self, oid, error):
        r = self._row(oid)
        if r['status'] in ('PENDING', 'SENT'):
            r.update(status='FAILED', error=str(error))

    def recent_for_order(self, order_id, limit=20):
        return [r for r in reversed(self.rows) if r['order_id'] == order_id][:limit]


class MemoryUow:
    def __init__(self, outbox, commits):
        self.outbox, self._commits = outbox, commits

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def commit(self):
        self._commits.append(1)


class MemoryDisputeRepo:
    """DisputeRepo trong bộ nhớ, cùng ngữ nghĩa với MySqlDisputeRepo (chuyển trạng thái có điều kiện trạng thái cũ)."""

    def __init__(self):
        self.orders, self.resolutions, self.sigs = {}, [], {}

    def order_for_dispute(self, order_id, lock=False):
        return self.orders.get(order_id)

    def latest_resolution(self, order_id, lock=False):
        rows = [r for r in self.resolutions if r['order_id'] == order_id]
        return dict(rows[-1]) if rows else None

    def signatures(self, resolution_id):
        return [dict(s) for s in self.sigs.get(resolution_id, [])]

    def transition_resolution(self, resolution_id, from_states, to_status, tx_hash=None):
        r = next(x for x in self.resolutions if x['id'] == resolution_id)
        if r['status'] not in from_states:
            return False
        r['status'] = to_status
        if tx_hash:
            r['submitted_tx_hash'] = tx_hash
        return True

    def open_disputes(self):
        return []

    # --- Tuần 7 (B): nhật ký UC-07 trong bộ nhớ (cùng hình dạng MySqlDisputeRepo)
    def add_force_resolution(self, order_id, onchain_order_id, admin_user_id, payout_side, payout_to, amount_raw, reason_note,
                             outbox_id, tx_hash):
        if getattr(self, 'fail_force_audit', False):
            raise RuntimeError('CSDL hỏng (giả lập)')
        rows = self.__dict__.setdefault('force_rows', [])
        rows.append({'id': len(rows) + 1, 'order_id': order_id, 'onchain_order_id': int(onchain_order_id), 'admin_user_id': admin_user_id,
                     'payout_side': payout_side, 'payout_to': str(payout_to).lower(), 'amount_raw': str(amount_raw),
                     'reason_note': reason_note, 'outbox_id': outbox_id, 'tx_hash': tx_hash})
        return len(rows)

    def force_resolutions(self, order_id):
        return [r for r in reversed(self.__dict__.get('force_rows', [])) if r['order_id'] == order_id]


class MemoryDisputeUow(MemoryUow):
    def __init__(self, outbox, commits, disputes):
        super().__init__(outbox, commits)
        self.disputes = disputes


def dispute_typed_data(order_id, payout_to, amount, nonce, deadline):
    """Thông điệp EIP-712 DisputeResolution dựng thẳng từ shared/eip712/types.json (không qua EnvKeySigner) để test chéo."""
    types = json.loads((ROOT / 'shared' / 'eip712' / 'types.json').read_text(encoding='utf-8'))['types']
    return {
        'types': {'EIP712Domain': [{'name': 'name', 'type': 'string'}, {'name': 'version', 'type': 'string'},
                                   {'name': 'chainId', 'type': 'uint256'}, {'name': 'verifyingContract', 'type': 'address'}],
                  'DisputeResolution': types['DisputeResolution']},
        'primaryType': 'DisputeResolution',
        'domain': {'name': 'SlopeeEscrow', 'version': '1', 'chainId': CHAIN_ID, 'verifyingContract': ESCROW},
        'message': {'orderId': int(order_id), 'payoutTo': payout_to, 'amount': int(amount), 'nonce': int(nonce), 'deadline': int(deadline)},
    }


def sign_dispute_as(key_name, order_id, payout_to, amount, nonce, deadline):
    """Chữ ký phán quyết của Buyer/Merchant/Arbitrator như MetaMask `eth_signTypedData_v4` (khóa thử công khai của Anvil)."""
    signed = Account.sign_message(encode_typed_data(full_message=dispute_typed_data(order_id, payout_to, amount, nonce, deadline)),
                                  KEYS[key_name])
    return with_0x(signed.signature.hex())


def event(name, block, log_index=0, tx=None, **args):
    """Một log đã giải mã (đúng hình dạng Web3Chain.get_logs trả về)."""
    return {'event': name, 'tx_hash': tx or '0x' + format(block * 1000 + log_index + 1, '064x'), 'log_index': log_index,
            'block_number': block, 'block_hash': '0x' + format(block, '064x'), 'args': args}


def make_signer(**over):
    kw = dict(quote_key=KEYS['quote_signer'], arbitrator_key=KEYS['arbitrator'], shipper_key=KEYS['shipper'],
              chain_id=CHAIN_ID, verifying_contract=ESCROW)
    kw.update(over)
    return EnvKeySigner(**kw)


def connect():
    return pymysql.connect(host=os.environ.get('DB_HOST', 'localhost'), user=os.environ.get('DB_USER', 'root'),
                           password=os.environ.get('DB_PASSWORD', ''), database=os.environ['DB_NAME'],
                           cursorclass=pymysql.cursors.DictCursor)


class Env:
    """Gói service + adapter giả dùng chung cho một test MySQL."""

    def __init__(self, *, fee_cap=300, system_now=1_800_000_000, chain_ts=None, max_nonces=5):
        self.chain = FakeChain(fee_cap=fee_cap, block_ts=chain_ts if chain_ts is not None else system_now)
        self.clock = FixedClock(system=system_now, chain=self.chain.block_ts)
        self.signer = make_signer()
        self.uow = lambda: MySqlUnitOfWork(connect)
        self.wallet = WalletService(self.uow, recover_personal_sign, wallet_domain=DOMAIN, chain_id=CHAIN_ID,
                                    max_nonces_per_minute=max_nonces)
        self.quote = QuoteService(self.uow, self.signer, self.chain, self.clock, token_address=TOKEN)
        self.status = OrderStatusService(self.uow, self.clock)


def sign_message(key_name, message):
    return Account.sign_message(encode_defunct(text=message), KEYS[key_name]).signature.hex()


def with_0x(sig):
    return sig if sig.startswith('0x') else '0x' + sig


# ------------------------------------------------------------------ seed MySQL
def user(cur, role='user'):
    uid = str(uuid.uuid4())
    cur.execute("INSERT INTO users (id, role, name, email, phone) VALUES (%s,%s,%s,%s,%s)",
                (uid, role, f"{role}-{uid[:6]}", f"{uid[:12]}@t.io", uid.replace('-', '')[:10]))
    return uid


def link_wallet(cur, uid, key_name):
    cur.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (uid, ADDR[key_name].lower()))


def category(cur, name='c'):
    cur.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
    return cur.lastrowid


def shop_with_product(cur, seller, *, category_id=None, stock=10, price=100_000, name='Áo thun'):
    shop = str(uuid.uuid4())
    cur.execute("INSERT INTO shops (id, sellerId, name) VALUES (%s,%s,%s)", (shop, seller, f"Shop {shop[:4]}"))
    category_id = category_id or category(cur)
    pid = uuid.uuid4().hex[:15]
    cur.execute("INSERT INTO products (id, categoryId, shopId, name, inStock, unitPrice, isActive) VALUES (%s,%s,%s,%s,%s,%s,TRUE)",
                (pid, category_id, shop, name, stock, price))
    return shop, pid


def cart_item(cur, buyer, product_id, qty=1):
    cur.execute("SELECT id FROM carts WHERE userId=%s AND status='active' LIMIT 1", (buyer,))
    row = cur.fetchone()
    if row:
        cart = row['id']
    else:
        cart = str(uuid.uuid4())
        cur.execute("INSERT INTO carts (id, userId) VALUES (%s,%s)", (cart, buyer))
    item = str(uuid.uuid4())
    cur.execute("INSERT INTO cartItems (id, cartId, productId, quantity, selectedVariants) VALUES (%s,%s,%s,%s,'{}')",
                (item, cart, product_id, qty))
    return item

