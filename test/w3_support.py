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
from eth_account.messages import encode_defunct

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

