"""Backend W3 trên CHUỖI THẬT (Anvil + contract deploy bởi scripts/bootstrap.sh): I-02 phía backend.

Chứng minh phần mà test giả không chứng minh được: contract THẬT chấp nhận báo giá do QuoteService ký, và từ chối mọi
báo giá bị sửa/hết hạn/vượt trần phí/sai người nạp; Web3Chain đọc đúng trạng thái; Indexer giải mã đúng log thật.
Tự skip nếu không có Anvil. Chạy: ./scripts/bootstrap.sh --fresh --force-env && pytest -m anvil
"""
import os
import time
from pathlib import Path

import pytest
from dotenv import dotenv_values
from web3 import Web3

from slopee_web3.adapters.clock import HybridClock
from slopee_web3.adapters.env_signer import EnvKeySigner
from slopee_web3.adapters.indexer import Indexer
from slopee_web3.adapters.mysql_repos import MySqlUnitOfWork
from slopee_web3.adapters.web3_chain import Web3Chain
from slopee_web3.application.quote_service import QuoteService
from slopee_web3.domain.errors import DomainError
from slopee_web3.domain.quote import OrderQuote
from slopee_web3.settings import Web3Settings
from w3_support import ADDR, cart_item, connect, shop_with_product, user

pytestmark = [pytest.mark.mysql, pytest.mark.anvil]

ERC20 = [
    {'type': 'function', 'name': 'mint', 'inputs': [{'name': 'to', 'type': 'address'}, {'name': 'amount', 'type': 'uint256'}], 'outputs': [], 'stateMutability': 'nonpayable'},
    {'type': 'function', 'name': 'approve', 'inputs': [{'name': 'spender', 'type': 'address'}, {'name': 'amount', 'type': 'uint256'}], 'outputs': [{'type': 'bool'}], 'stateMutability': 'nonpayable'},
    {'type': 'function', 'name': 'balanceOf', 'inputs': [{'name': 'a', 'type': 'address'}], 'outputs': [{'type': 'uint256'}], 'stateMutability': 'view'},
]


@pytest.fixture(scope='module')
def stack():
    path = Path(__file__).resolve().parents[2] / 'backend' / '.env.web3'
    env = {**dotenv_values(path), **{k: v for k, v in os.environ.items() if k in ('RPC_URL', 'ESCROW_ADDRESS', 'MOCKUSD_ADDRESS', 'QUOTE_SIGNER_KEY', 'CHAIN_ID')}}
    s = Web3Settings.from_env(env)
    required = bool(os.environ.get('REQUIRE_ANVIL'))     # CI bật cờ này: thiếu Anvil phải ĐỎ, không được lặng lẽ skip
    give_up = (lambda m: pytest.fail(m)) if required else (lambda m: pytest.skip(m))
    if s is None:
        give_up('Chưa có backend/.env.web3 (chạy scripts/bootstrap.sh)')
    chain = Web3Chain(s.rpc_url, s.escrow_address, timeout=3)
    try:
        chain.chain_id()
    except Exception as e:   # noqa: BLE001
        give_up(f'Không kết nối được Anvil: {e}')
    token = chain.w3.eth.contract(address=Web3.to_checksum_address(s.token_address), abi=ERC20)
    return s, chain, token


@pytest.fixture
def svc(stack, mysql_db):
    s, chain, token = stack
    conn = connect(); conn.autocommit(True); cur = conn.cursor()
    cur.execute("DELETE FROM user_wallets")
    cur.execute("DELETE FROM chain_events")
    cur.execute("DELETE FROM indexer_cursor")
    # id on-chain không được trùng lần chạy trước trên cùng Anvil (contract từ chối "Order exists")
    cur.execute(f"ALTER TABLE onchain_id_seq AUTO_INCREMENT = {int(time.time() * 1000)}")
    signer = EnvKeySigner.from_settings(s)
    quote = QuoteService(lambda: MySqlUnitOfWork(connect), signer, chain, HybridClock(chain), token_address=s.token_address,
                         token_decimals=s.token_decimals, token_symbol=s.token_symbol)
    yield cur, quote, signer, chain, token, s
    conn.close()


def _tuple(q):
    return (q.orderId, q.buyer, q.merchant, q.token, q.amount, q.inspectionDuration, q.disputeTimeout, q.feeBps,
            bytes.fromhex(q.docHash[2:]), q.deadline)


def _from_msg(m):
    return OrderQuote(orderId=int(m['orderId']), buyer=m['buyer'], merchant=m['merchant'], token=m['token'], amount=int(m['amount']),
                      inspectionDuration=int(m['inspectionDuration']), disputeTimeout=int(m['disputeTimeout']),
                      feeBps=int(m['feeBps']), docHash=m['docHash'], deadline=int(m['deadline']))


def _checkout(cur, quote, shops=2):
    buyer = user(cur)
    cur.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (buyer, ADDR['buyer'].lower()))
    items = []
    for n in range(1, shops + 1):
        seller = user(cur, 'seller')
        cur.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (seller, ADDR[f'merchant{n}'].lower()))
        _, pid = shop_with_product(cur, seller, price=100_000 * n)
        items.append(cart_item(cur, buyer, pid, 1))
    return buyer, quote.create_checkout(buyer, items)


def _mined(chain, tx_hash):
    """Anvil của bootstrap đào theo chu kỳ (block-time): phải chờ receipt rồi mới tin trạng thái / gửi tx kế tiếp."""
    receipt = chain.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
    assert receipt['status'] == 1
    return receipt


def _fund_and_approve(chain, token, s, amount):
    buyer = Web3.to_checksum_address(ADDR['buyer'])
    _mined(chain, token.functions.mint(buyer, amount).transact({'from': buyer}))
    _mined(chain, token.functions.approve(chain.address, amount).transact({'from': buyer}))


def _deposit(chain, orders, sender='buyer', tamper=None):
    quotes = [_from_msg(o['quote']) for o in orders]
    if tamper:
        quotes = [tamper(q) for q in quotes]
    tx = chain.contract.functions.depositEscrowBatch([_tuple(q) for q in quotes], [bytes.fromhex(o['signature'][2:]) for o in orders]) \
        .transact({'from': Web3.to_checksum_address(ADDR[sender])})
    return _mined(chain, tx)


def test_adapters_read_the_real_contract(stack):
    s, chain, _ = stack
    assert chain.chain_id() == s.chain_id
    assert 0 < chain.default_fee_bps() <= 1000
    assert chain.get_order_state(2 ** 52 + 12345) == 'NONE'
    b = chain.latest_block()
    assert b['hash'].startswith('0x') and len(b['hash']) == 66 and b['timestamp'] > 1_700_000_000
    EnvKeySigner.from_settings(s).verify_against_chain(chain)      # khóa .env khớp vai trò đã cấp trên contract


def test_contract_accepts_backend_signed_batch_and_reports_locked(svc):
    cur, quote, signer, chain, token, s = svc
    buyer, out = _checkout(cur, quote, shops=2)
    _fund_and_approve(chain, token, s, int(out['total_amount_raw']))
    _deposit(chain, out['orders'])
    for o in out['orders']:
        assert chain.get_order_state(int(o['onchain_order_id'])) == 'LOCKED'
        on_chain = chain.contract.functions.orders(int(o['onchain_order_id'])).call()
        assert on_chain[3] == int(o['amount_raw']) and on_chain[1] == Web3.to_checksum_address(o['quote']['merchant'])
        assert on_chain[8] == int(o['inspection_duration']) and on_chain[9] == o['fee_bps']
        assert '0x' + on_chain[11].hex() == o['quote']['docHash']
    # cấp lại báo giá cho đơn đã nạp phải bị chặn bằng trạng thái ĐỌC TỪ CHUỖI (Indexer có thể chưa kịp chạy)
    with pytest.raises(DomainError) as e:
        quote.reissue_group_quotes(buyer, out['checkout_group_id'])
    assert e.value.code == 'INVALID_STATE'


def test_requoted_signature_is_also_accepted_by_the_contract(svc):
    cur, quote, signer, chain, token, s = svc
    buyer, first = _checkout(cur, quote, shops=1)
    second = quote.reissue_group_quotes(buyer, first['checkout_group_id'])
    assert second['orders'][0]['onchain_order_id'] == first['orders'][0]['onchain_order_id']
    _fund_and_approve(chain, token, s, int(second['total_amount_raw']))
    _deposit(chain, second['orders'])
    assert chain.get_order_state(int(second['orders'][0]['onchain_order_id'])) == 'LOCKED'


def test_contract_rejects_tampered_amount_wrong_sender_expired_and_excess_fee(svc):
    cur, quote, signer, chain, token, s = svc
    buyer, out = _checkout(cur, quote, shops=1)
    o = out['orders']
    oid = int(o[0]['onchain_order_id'])
    _fund_and_approve(chain, token, s, int(out['total_amount_raw']) * 2)

    def rejected(**kw):
        with pytest.raises(Exception):
            _deposit(chain, o, **kw)
        assert chain.get_order_state(oid) == 'NONE'

    rejected(tamper=lambda q: OrderQuote(**{**q.__dict__, 'amount': q.amount - 1}))          # sửa số tiền
    rejected(tamper=lambda q: OrderQuote(**{**q.__dict__, 'merchant': ADDR['stranger']}))     # đổi người bán
    rejected(sender='stranger')                                                                 # người khác nạp báo giá của buyer
    # báo giá do backend ký nhưng đã quá hạn
    now = chain.latest_block()['timestamp']
    expired = OrderQuote(**{**_from_msg(o[0]['quote']).__dict__, 'deadline': now - 10})
    with pytest.raises(Exception):
        chain.contract.functions.depositEscrow(_tuple(expired), bytes.fromhex(signer.sign_quote(expired)[2:])) \
            .transact({'from': Web3.to_checksum_address(ADDR['buyer'])})
    # phí vượt trần on-chain (backend không bao giờ tự ký thế, nhưng contract phải chặn nếu lỡ có)
    over = OrderQuote(**{**_from_msg(o[0]['quote']).__dict__, 'feeBps': chain.default_fee_bps() + 1})
    with pytest.raises(Exception):
        chain.contract.functions.depositEscrow(_tuple(over), bytes.fromhex(signer.sign_quote(over)[2:])) \
            .transact({'from': Web3.to_checksum_address(ADDR['buyer'])})
    assert chain.get_order_state(oid) == 'NONE'
    _deposit(chain, o)                                                                           # báo giá nguyên vẹn thì được
    assert chain.get_order_state(oid) == 'LOCKED'


def test_indexer_records_real_ordercreated_logs(svc):
    cur, quote, signer, chain, token, s = svc
    buyer, out = _checkout(cur, quote, shops=2)
    _fund_and_approve(chain, token, s, int(out['total_amount_raw']))
    _deposit(chain, out['orders'])
    conn = connect()
    try:
        stats = Indexer(connect, chain, start_block=0).run_once(conn)
        assert stats['new_events'] >= 2
        ids = [int(o['onchain_order_id']) for o in out['orders']]
        cur.execute("SELECT order_id, event_name, block_timestamp, tx_hash FROM chain_events WHERE event_name='OrderCreated' AND order_id IN (%s,%s)", ids)
        rows = list(cur.fetchall())
        assert sorted(r['order_id'] for r in rows) == sorted(ids)
        assert len({r['tx_hash'] for r in rows}) == 1                              # cả lô chung MỘT giao dịch (BR-11)
        assert all(len(r['tx_hash']) == 66 and r['block_timestamp'] > 1_700_000_000 for r in rows)
        again = Indexer(connect, chain, start_block=0).run_once(conn)              # chạy lại: không thêm, không lỗi
        assert again['new_events'] == 0
    finally:
        conn.close()
