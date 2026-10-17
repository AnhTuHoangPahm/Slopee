"""Tuần 5 [B] trên CHUỖI THẬT (Anvil + contract do scripts/bootstrap.sh deploy): relayer + tác vụ nền + đối soát.

Chứng minh điều fake không chứng minh được: `Web3Chain.send_tx` + `EnvKeySigner.sign_transaction` gửi được confirmDelivery /
releaseAfterInspection tới contract THẬT bằng SHIPPER_KEY; handler Indexer giải mã đúng log THẬT; AutoRelease chỉ gọi khi contract
cho phép; tiền chia đúng theo feeBps; QuoteExpirySweeper chỉ hết hạn khi contract cũng đã từ chối nạp; đối soát khớp số dư thật.
Tự skip nếu không có Anvil. Chạy: ./scripts/bootstrap.sh --fresh --force-env && pytest -m anvil
LƯU Ý: test tua giờ Anvil TIẾN LÊN vĩnh viễn trên node đang chạy (về giờ thật: bootstrap.sh --fresh).
"""
import pytest
from web3 import Web3

from slopee_web3.adapters.clock import HybridClock
from slopee_web3.adapters.indexer import Indexer
from slopee_web3.adapters.mysql_repos import MySqlUnitOfWork
from slopee_web3.adapters.relayer_queue import SingleThreadQueue
from slopee_web3.application.jobs import AutoRelease, QuoteExpirySweeper
from slopee_web3.application.reconcile_service import ReconcileService
from slopee_web3.application.relayer_service import RelayerService
from slopee_web3.application.shipper_service import ShipperService
from test_w3_chain_anvil import _checkout, _deposit, _fund_and_approve, _mined, _from_msg, _tuple, stack, svc  # noqa: F401
from w3_support import ADDR, connect, user

pytestmark = [pytest.mark.mysql, pytest.mark.anvil]


class Rig:
    def __init__(self, svc):
        self.cur, self.quote, self.signer, self.chain, self.token, self.s = svc
        self.uow = lambda: MySqlUnitOfWork(connect)
        self.clock = HybridClock(self.chain)
        self.queue = SingleThreadQueue('anvil-week5')
        self.relayer = RelayerService(self.uow, self.chain, self.signer, self.queue, receipt_timeout=30, queue_timeout=60)
        self.shipper_svc = ShipperService(self.uow, self.relayer)
        self.release = AutoRelease(self.uow, self.chain, self.clock, self.relayer)
        self.sweeper = QuoteExpirySweeper(self.uow, self.chain, self.clock)
        self.reconcile = ReconcileService(self.uow, self.chain, known_tokens=[self.s.token_address])

    def index(self):
        conn = connect()
        try:
            return Indexer(connect, self.chain, start_block=0).run_once(conn)
        finally:
            conn.close()

    def row(self, sql, *a):
        self.cur.execute(sql, a)
        return self.cur.fetchone()

    def status(self, order_id):
        return self.row("SELECT status FROM order_web3 WHERE order_id=%s", order_id)['status']

    def bal(self, who):
        return self.token.functions.balanceOf(Web3.to_checksum_address(who)).call()

    def travel(self, seconds):
        self.chain.w3.provider.make_request('evm_increaseTime', [int(seconds)])
        self.chain.w3.provider.make_request('evm_mine', [])

    def diff(self):
        return int([t for t in self.reconcile.run()['tokens'] if t['token'] == self.s.token_address.lower()][0]['diff_raw'])

    def locked_order(self, shops=1):
        buyer, out = _checkout(self.cur, self.quote, shops=shops)
        _fund_and_approve(self.chain, self.token, self.s, int(out['total_amount_raw']))
        _deposit(self.chain, out['orders'])
        self.index()
        shipper = user(self.cur, 'shipper')
        admin = user(self.cur, 'admin')
        for o in out['orders']:
            self.shipper_svc.assign(admin, o['order_id'], shipper)
        return buyer, out, shipper


@pytest.fixture
def rig(svc):
    r = Rig(svc)
    for t in ('notifications', 'tx_outbox', 'shipper_assignments', 'pending_balances', 'order_quotes', 'order_web3',
              'checkout_groups', 'orders'):                       # mỗi test bắt đầu sạch (chuỗi thì giữ nguyên, id on-chain không trùng)
        r.cur.execute(f"DELETE FROM {t}")
    yield r
    r.queue.close()


def test_real_chain_deliver_auto_release_exact_payout_and_reconcile(rig):
    base_diff = rig.diff()                                       # chuỗi dùng chung có thể còn tiền của test khác: so ĐỘ LỆCH, không so tuyệt đối
    buyer, out, shipper = rig.locked_order(shops=2)
    a, b = out['orders']
    ida, idb = int(a['onchain_order_id']), int(b['onchain_order_id'])
    assert rig.diff() == base_diff                               # tiền mới vào = đơn mới mở: đối soát vẫn khớp

    # --- Shipper giao đơn A qua relayer THẬT (SHIPPER_KEY ký, contract kiểm role)
    res = rig.shipper_svc.deliver(shipper, a['order_id'])
    assert res['outcome'] == 'SENT' and rig.chain.get_order_state(ida) == 'DELIVERED' and rig.chain.get_order_state(idb) == 'LOCKED'
    ob = rig.row("SELECT kind, status, tx_hash FROM tx_outbox WHERE order_id=%s", a['order_id'])
    assert (ob['kind'], ob['status'], ob['tx_hash']) == ('DELIVER', 'CONFIRMED', res['tx_hash'])
    sent_before = rig.row("SELECT COUNT(*) AS c FROM tx_outbox")['c']
    assert rig.shipper_svc.deliver(shipper, a['order_id'])['outcome'] == 'ALREADY_DELIVERED'   # DB còn LOCKED nhưng chuỗi đã DELIVERED: đọc chuỗi, KHÔNG gửi lại
    assert rig.row("SELECT COUNT(*) AS c FROM tx_outbox")['c'] == sent_before
    assert rig.chain.contract.functions.orders(ida).call()[5] > 0                          # deliveredAt do contract đặt

    rig.index()                                                  # handler OrderDelivered giải mã log THẬT
    r = rig.row("SELECT status, delivered_at FROM order_web3 WHERE order_id=%s", a['order_id'])
    assert r['status'] == 'DELIVERED' and r['delivered_at'] == rig.chain.contract.functions.orders(ida).call()[5]
    assert rig.status(b['order_id']) == 'LOCKED'
    assert rig.row("SELECT COUNT(*) AS c FROM notifications WHERE kind='ORDER_DELIVERED'")['c'] == 1
    assert rig.shipper_svc.deliver(shipper, a['order_id'])['outcome'] == 'ALREADY_DELIVERED'      # DB đã DELIVERED

    # --- chưa hết hạn kiểm tra: AutoRelease không được gửi giao dịch (contract sẽ revert 'Under inspection')
    stats = rig.release.run_once()
    assert stats['released'] == 0 and rig.chain.get_order_state(ida) == 'DELIVERED'

    # --- tua giờ qua hạn kiểm tra: AutoRelease giải ngân; tiền chia ĐÚNG theo feeBps đã khóa
    order = rig.chain.get_order(ida)
    merchant, fee_to = Web3.to_checksum_address(a['quote']['merchant']), rig.chain.contract.functions.feeRecipient().call()
    m0, f0, e0 = rig.bal(merchant), rig.bal(fee_to), rig.bal(rig.chain.address)
    rig.travel(order['inspection_duration'] + 1)
    stats = rig.release.run_once()
    assert stats['released'] == 1 and stats['failed'] == 0
    assert rig.chain.get_order_state(ida) == 'COMPLETED' and rig.chain.get_order_state(idb) == 'LOCKED'
    fee = order['amount'] * order['fee_bps'] // 10000
    assert rig.bal(merchant) - m0 == order['amount'] - fee
    assert rig.bal(fee_to) - f0 == fee and e0 - rig.bal(rig.chain.address) == order['amount']
    kinds = [x['kind'] for x in _all(rig, "SELECT kind FROM tx_outbox ORDER BY id")]
    assert kinds == ['DELIVER', 'RELEASE']

    rig.index()
    r = rig.row("SELECT status, closed_at FROM order_web3 WHERE order_id=%s", a['order_id'])
    assert r['status'] == 'COMPLETED' and r['closed_at'] > 0
    assert rig.release.run_once()['released'] == 0                                    # không gửi lại
    rec = rig.reconcile.run(deep=True)
    assert rec['indexer_lag_blocks'] == 0 and rec['order_mismatches'] == [] and rig.diff() == base_diff   # số dư thật khớp sau cả giao hàng lẫn giải ngân


def _all(rig, sql):
    rig.cur.execute(sql)
    return list(rig.cur.fetchall())


def test_real_chain_buyer_early_release_makes_auto_release_a_noop(rig):
    buyer, out, shipper = rig.locked_order()
    o = out['orders'][0]
    oid = int(o['onchain_order_id'])
    rig.shipper_svc.deliver(shipper, o['order_id'])
    rig.index()
    _mined(rig.chain, rig.chain.contract.functions.earlyRelease(oid).transact({'from': Web3.to_checksum_address(ADDR['buyer'])}))
    rig.travel(rig.chain.get_order(oid)['inspection_duration'] + 1)       # DB còn DELIVERED nên là ứng viên, nhưng chuỗi đã COMPLETED
    assert rig.status(o['order_id']) == 'DELIVERED'
    stats = rig.release.run_once()
    assert stats['released'] == 0 and not _all(rig, "SELECT 1 FROM tx_outbox WHERE kind='RELEASE'")
    rig.index()
    assert rig.status(o['order_id']) == 'COMPLETED'


def test_real_chain_dispute_freezes_funds_and_auto_release_leaves_it_alone(rig):
    base_diff = rig.diff()
    buyer, out, shipper = rig.locked_order()
    o = out['orders'][0]
    oid = int(o['onchain_order_id'])
    rig.shipper_svc.deliver(shipper, o['order_id'])
    _mined(rig.chain, rig.chain.contract.functions.raiseDispute(oid).transact({'from': Web3.to_checksum_address(ADDR['buyer'])}))
    rig.index()
    r = rig.row("SELECT status, disputed_at FROM order_web3 WHERE order_id=%s", o['order_id'])
    assert r['status'] == 'DISPUTED' and r['disputed_at'] == rig.chain.contract.functions.orders(oid).call()[6]
    rig.travel(rig.chain.get_order(oid)['inspection_duration'] * 2)
    assert rig.release.run_once() == {'released': 0, 'skipped': 0, 'failed': 0}
    assert rig.chain.get_order_state(oid) == 'DISPUTED' and rig.diff() == base_diff      # DISPUTED vẫn tính là tiền đang giữ


def test_real_chain_contract_refuses_expired_quote_so_sweeper_expiry_is_safe(rig):
    """Chốt chặn của QuoteExpirySweeper: qua hạn + đệm thì CHÍNH CONTRACT cũng từ chối nạp, nên EXPIRED không thể làm kẹt tiền."""
    buyer, out = _checkout(rig.cur, rig.quote, shops=1)
    o = out['orders'][0]
    _fund_and_approve(rig.chain, rig.token, rig.s, int(out['total_amount_raw']))
    assert rig.sweeper.run_once()['orders_expired'] == 0                                # còn hạn: không đụng
    rig.travel(int(o['quote']['deadline']) - rig.chain.latest_block()['timestamp'] + 31)
    q = _from_msg(o['quote'])
    with pytest.raises(Exception) as e:                                                 # contract thật từ chối báo giá quá hạn
        rig.chain.contract.functions.depositEscrowBatch([_tuple(q)], [bytes.fromhex(o['signature'][2:])]) \
            .call({'from': Web3.to_checksum_address(ADDR['buyer'])})
    assert 'expired' in str(e.value).lower()
    assert rig.sweeper.run_once() == {'groups_expired': 1, 'orders_expired': 1, 'skipped': 0}
    assert rig.status(o['order_id']) == 'EXPIRED'
    assert rig.row("SELECT inStock FROM products WHERE id=(SELECT productId FROM orderLines WHERE orderId=%s LIMIT 1)", o['order_id'])['inStock'] >= 1
    assert rig.chain.get_order_state(int(o['onchain_order_id'])) == 'NONE'


TRANSFER_ABI = [{'type': 'function', 'name': 'transfer', 'stateMutability': 'nonpayable',
                 'inputs': [{'name': 'to', 'type': 'address'}, {'name': 'amount', 'type': 'uint256'}], 'outputs': [{'type': 'bool'}]},
                {'type': 'function', 'name': 'mint', 'stateMutability': 'nonpayable',
                 'inputs': [{'name': 'to', 'type': 'address'}, {'name': 'amount', 'type': 'uint256'}], 'outputs': []}]


def test_real_chain_reconcile_flags_tokens_sent_straight_to_the_contract(rig):
    rig.index()
    base_diff = rig.diff()
    erc20 = rig.chain.w3.eth.contract(address=Web3.to_checksum_address(rig.s.token_address), abi=TRANSFER_ABI)
    buyer = Web3.to_checksum_address(ADDR['buyer'])
    _mined(rig.chain, erc20.functions.mint(buyer, 7_000).transact({'from': buyer}))
    _mined(rig.chain, erc20.functions.transfer(rig.chain.address, 7_000).transact({'from': buyer}))   # ngoài luồng đơn
    rig.index()                                                                       # Indexer đi qua block chứa khoản chuyển
    rec = rig.reconcile.run()
    assert rig.diff() == base_diff + 7_000                                            # lệch ĐÚNG số tiền lạ, dấu dương = contract dư
    assert base_diff + 7_000 != 0 and not rec['ok'] and rec['status'] == 'MISMATCH'
