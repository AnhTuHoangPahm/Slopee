"""Tuần 6 [B] trên CHUỖI THẬT (Anvil + contract do scripts/bootstrap.sh deploy): đề xuất + chữ ký 2/3 EIP-712 + nộp + Indexer.

Chứng minh điều chuỗi giả không chứng minh được: chữ ký Trọng tài do `DisputeService.propose` (khóa ARBITRATOR_KEY) và chữ ký Buyer/Merchant (như
MetaMask) được contract THẬT chấp nhận khi relayer của A nộp `resolveDispute`; `deadline` do B tính luôn nhỏ hơn disputedAt + disputeTimeout trên chuỗi;
tiền chia đúng; Indexer giải mã log THẬT (DisputeResolved, ArbitratorForceResolved) và đặt EXECUTED/CANCELLED; chữ ký cũ không thi hành lại được.
Tự skip nếu không có Anvil. LƯU Ý: test tua giờ Anvil TIẾN LÊN vĩnh viễn (về giờ thật: bootstrap.sh --fresh).
"""
import pytest
from web3 import Web3

from slopee_web3.application.dispute_service import DisputeService
from slopee_web3.application.dispute_submit_service import DisputeSubmitService
from slopee_web3.application.jobs import DisputeSigExpiry
from slopee_web3.domain.errors import DomainError
from test_w3_chain_anvil import _mined, stack, svc  # noqa: F401
from test_w3_week5_anvil import Rig
from w3_support import ADDR, connect, sign_dispute_as, user

pytestmark = [pytest.mark.mysql, pytest.mark.anvil]
DISPUTE_TABLES = ('dispute_signatures', 'dispute_resolutions', 'dispute_notes')


def _wipe(cur):
    for t in DISPUTE_TABLES:
        cur.execute(f"DELETE FROM {t}")


class DRig(Rig):
    def __init__(self, svc):
        super().__init__(svc)
        self.ds = DisputeService(self.uow, self.chain, self.signer, self.clock, token_decimals=6)
        self.sub = DisputeSubmitService(self.uow, self.chain, self.signer, self.clock, self.relayer)
        self.expiry = DisputeSigExpiry(self.uow, self.clock)
        self.admin = user(self.cur, 'admin')

    def disputed(self):
        """LOCKED -> giao (relayer thật) -> Buyer raiseDispute (contract thật) -> Indexer DISPUTED."""
        buyer, out, shipper = self.locked_order()
        o = out['orders'][0]
        oid = int(o['onchain_order_id'])
        self.shipper_svc.deliver(shipper, o['order_id'])
        _mined(self.chain, self.chain.contract.functions.raiseDispute(oid).transact({'from': Web3.to_checksum_address(ADDR['buyer'])}))
        self.index()
        assert self.status(o['order_id']) == 'DISPUTED'
        merchant = self.row("SELECT merchant_user_id AS m FROM order_web3 WHERE order_id=%s", o['order_id'])['m']
        return buyer, merchant, o['order_id'], oid

    def sign(self, key, oid, p):
        return sign_dispute_as(key, oid, p['payout_to'], int(p['amount_raw']), int(p['nonce']), p['deadline'])

    def resolution(self, rid):
        return self.row("SELECT status, submitted_tx_hash FROM dispute_resolutions WHERE id=%s", rid)

    def raw_signatures(self, rid):
        self.cur.execute("SELECT party, signature FROM dispute_signatures WHERE resolution_id=%s ORDER BY id", (rid,))
        return {r['party']: r['signature'] for r in self.cur.fetchall()}

    def resolve_call(self, oid, p, sig1, sig2):
        """Gọi thẳng contract (eth_call) để xem nó chấp nhận hay từ chối bộ chữ ký này."""
        return self.chain.contract.functions.resolveDispute(
            oid, Web3.to_checksum_address(p['payout_to']), p['deadline'], bytes.fromhex(sig1[2:]), bytes.fromhex(sig2[2:])
        ).call({'from': Web3.to_checksum_address(ADDR['buyer'])})


@pytest.fixture
def drig(svc):
    _wipe(svc[0])
    r = DRig(svc)
    for t in ('notifications', 'tx_outbox', 'shipper_assignments', 'pending_balances', 'order_quotes', 'order_web3', 'checkout_groups', 'orders'):
        r.cur.execute(f"DELETE FROM {t}")
    yield r
    _wipe(r.cur)
    r.queue.close()


def test_real_chain_refund_to_buyer_with_arbitrator_and_buyer_signatures(drig):
    r = drig
    base_diff = r.diff()
    buyer, merchant, code, oid = r.disputed()
    on = r.chain.get_order(oid)
    p = r.ds.propose(r.admin, code, 'BUYER', 'Đủ bằng chứng hàng lỗi')

    # deadline do B tính phải thỏa điều kiện CỦA CONTRACT THẬT: nhỏ hơn disputedAt + disputeTimeout (đọc từ chuỗi, không từ MySQL)
    chain_order = r.chain.contract.functions.orders(oid).call()
    assert p['deadline'] < int(chain_order[6]) + int(chain_order[7]) and p['nonce'] == str(r.chain.dispute_nonce(oid)) == '0'
    assert p['amount_raw'] == str(on['amount']) and p['payout_to'] == on['buyer']

    assert r.ds.add_signature(buyer, code, p['resolution_id'], r.sign('buyer', oid, p))['status'] == 'READY'
    sigs = r.raw_signatures(p['resolution_id'])
    assert set(sigs) == {'ARBITRATOR', 'BUYER'}
    r.resolve_call(oid, p, sigs['ARBITRATOR'], sigs['BUYER'])                                 # contract THẬT chấp nhận (eth_call không revert)

    b0, e0 = r.bal(ADDR['buyer']), r.bal(r.chain.address)
    out = r.sub.submit(buyer, 'user', code)                                                   # relayer của A nộp bằng SHIPPER_KEY
    assert out['outcome'] == 'SENT' and r.resolution(p['resolution_id'])['status'] == 'SUBMITTED'
    assert r.chain.get_order_state(oid) == 'REFUNDED' and r.chain.dispute_nonce(oid) == 1
    assert r.bal(ADDR['buyer']) - b0 == on['amount'] and e0 - r.bal(r.chain.address) == on['amount']     # hoàn đủ, không thu phí

    r.index()                                                                                 # handler giải mã log THẬT
    assert r.status(code) == 'REFUNDED' and r.resolution(p['resolution_id'])['status'] == 'EXECUTED'
    assert r.row("SELECT anomaly_flag AS a FROM order_web3 WHERE order_id=%s", code)['a'] == 0
    r.cur.execute("SELECT COUNT(*) AS c FROM notifications WHERE kind='DISPUTE_RESOLVED'")
    assert r.cur.fetchone()['c'] == 2
    assert r.diff() == base_diff and r.reconcile.run(deep=True)['order_mismatches'] == []     # số dư thật khớp sau phán quyết

    # chữ ký cũ không thi hành lại được (nonce đã tăng và đơn không còn DISPUTED): contract từ chối, nên không thể nộp hai lần
    with pytest.raises(Exception):
        r.resolve_call(oid, p, sigs['ARBITRATOR'], sigs['BUYER'])
    assert r.sub.submit(buyer, 'user', code)['outcome'] == 'ALREADY_RESOLVED'


def test_real_chain_payout_to_merchant_splits_the_fee_exactly(drig):
    r = drig
    buyer, merchant, code, oid = r.disputed()
    on = r.chain.get_order(oid)
    p = r.ds.propose(r.admin, code, 'MERCHANT')
    assert r.ds.add_signature(merchant, code, p['resolution_id'], r.sign('merchant1', oid, p))['status'] == 'READY'
    fee_to = r.chain.contract.functions.feeRecipient().call()
    m0, f0 = r.bal(ADDR['merchant1']), r.bal(fee_to)
    assert r.sub.submit(merchant, 'seller', code)['outcome'] == 'SENT'
    fee = on['amount'] * on['fee_bps'] // 10000
    assert r.bal(ADDR['merchant1']) - m0 == on['amount'] - fee and r.bal(fee_to) - f0 == fee
    r.index()
    assert r.status(code) == 'COMPLETED' and r.resolution(p['resolution_id'])['status'] == 'EXECUTED'


def test_real_chain_contract_rejects_what_the_service_rejects(drig):
    """Mỗi lỗi mà DisputeService chặn trước đều là lỗi mà contract thật cũng sẽ revert: hai tầng phòng thủ cùng một luật."""
    r = drig
    buyer, merchant, code, oid = r.disputed()
    p = r.ds.propose(r.admin, code, 'BUYER')
    arb = r.raw_signatures(p['resolution_id'])['ARBITRATOR']
    buyer_sig, merchant_sig = r.sign('buyer', oid, p), r.sign('merchant1', oid, p)

    # (1) bên được lợi ký nội dung khác (đổi bên nhận tiền): service từ chối, contract cũng không coi đó là chữ ký của Buyer cho đề xuất này
    other = dict(p, payout_to=r.chain.get_order(oid)['merchant'])
    bad = r.sign('buyer', oid, other)
    with pytest.raises(DomainError) as e:
        r.ds.add_signature(buyer, code, p['resolution_id'], bad)
    assert e.value.code == 'BAD_SIGNATURE'
    with pytest.raises(Exception):
        r.resolve_call(oid, p, arb, bad)

    # (2) hai chữ ký cùng một bên (Trọng tài + Trọng tài) không đủ 2/3
    with pytest.raises(Exception):
        r.resolve_call(oid, p, arb, arb)
    # (3) Buyer + Merchant cũng đủ 2/3 và được contract nhận (không cần Trọng tài)
    r.resolve_call(oid, p, buyer_sig, merchant_sig)
    # (4) Trọng tài + Buyer được nhận
    r.resolve_call(oid, p, arb, buyer_sig)

    # (5) quá deadline: service báo SIGNATURE_EXPIRED, job chuyển EXPIRED, và contract thật cũng revert 'Signature expired'
    r.travel(p['deadline'] - r.clock.now_chain() + 2)
    with pytest.raises(DomainError) as e:
        r.ds.add_signature(buyer, code, p['resolution_id'], buyer_sig)
    assert e.value.code == 'SIGNATURE_EXPIRED'
    with pytest.raises(Exception):
        r.resolve_call(oid, p, arb, buyer_sig)
    assert r.expiry.run_once() == {'expired': 1} and r.resolution(p['resolution_id'])['status'] == 'EXPIRED'

    # (6) Admin đề xuất lại với nonce/deadline mới và phán quyết đó thi hành được
    q = r.ds.propose(r.admin, code, 'MERCHANT')
    assert q['nonce'] == p['nonce'] and q['deadline'] > p['deadline']
    r.ds.add_signature(merchant, code, q['resolution_id'], r.sign('merchant1', oid, q))
    assert r.sub.submit(merchant, 'seller', code)['outcome'] == 'SENT'
    r.index()
    assert r.status(code) == 'COMPLETED' and r.resolution(q['resolution_id'])['status'] == 'EXECUTED'
    assert r.resolution(p['resolution_id'])['status'] == 'EXPIRED'


def test_real_chain_arbitrator_force_resolve_cancels_the_open_proposal(drig):
    r = drig
    buyer, merchant, code, oid = r.disputed()
    p = r.ds.propose(r.admin, code, 'BUYER')
    r.ds.add_signature(buyer, code, p['resolution_id'], r.sign('buyer', oid, p))
    order = r.chain.contract.functions.orders(oid).call()
    r.travel(int(order[6]) + int(order[7]) - r.clock.now_chain() + 1)                         # qua disputedAt + disputeTimeout
    with pytest.raises(DomainError):                                                          # cửa phán quyết 2/3 đã đóng
        r.ds.propose(r.admin, code, 'BUYER')
    arbitrator = Web3.to_checksum_address(ADDR['arbitrator'])
    on = r.chain.get_order(oid)
    _mined(r.chain, r.chain.contract.functions.arbitratorForceResolve(oid, Web3.to_checksum_address(on['merchant'])).transact({'from': arbitrator}))
    r.index()
    assert r.status(code) == 'COMPLETED' and r.resolution(p['resolution_id'])['status'] == 'CANCELLED'
    assert r.row("SELECT anomaly_flag AS a FROM order_web3 WHERE order_id=%s", code)['a'] == 0
    r.cur.execute("SELECT message FROM notifications WHERE kind='DISPUTE_RESOLVED'")
    assert all('Trọng tài' in m['message'] for m in r.cur.fetchall())
    before = r.row("SELECT COUNT(*) AS c FROM tx_outbox")['c']
    with pytest.raises(DomainError) as e:                                                    # A: đề xuất đã CANCELLED/quá hạn nên không nộp được nữa
        r.sub.submit(buyer, 'user', code)
    assert e.value.code in ('DISPUTE_EXPIRED', 'DISPUTE_STALE', 'INVALID_STATE')
    assert r.row("SELECT COUNT(*) AS c FROM tx_outbox")['c'] == before                       # và không có giao dịch nào được gửi
