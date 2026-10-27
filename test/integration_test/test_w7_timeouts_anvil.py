"""Tuần 7 [B + Q] E-04 (AC-07, M3 "không có tiền kẹt vĩnh viễn") trên CHUỖI THẬT: Anvil + contract thật + MySQL + tua giờ `evm_increaseTime`.

Hai lối thoát timeout, mỗi lối chạy qua đường mã THẬT của sàn rồi để Indexer giải mã log thật:
  * Dispute timeout (B): Trọng tài xử đơn phương sau disputedAt + disputeTimeout, với từng giá trị 7/30/90 ngày (AC-07); relayer ký bằng ARBITRATOR_KEY thật,
    tiền chia đúng (hoàn 100% hoặc giải ngân trừ phí), nhật ký UC-07, đối soát khớp. Trước mốc: dịch vụ từ chối VÀ contract thật cũng revert (hai bên đồng ý).
  * Delivery timeout (C ở giao diện, ở đây phần chuỗi + Indexer): đơn LOCKED không ai giao, sau 14 ngày Buyer `cancelIfUnfulfilled` hoàn 100%.
Cuối cùng `scripts/reconcile.py --deep --events` trên chuỗi thật phải trả mã 0 (E-06): không còn đồng nào kẹt.
Tự skip nếu không có Anvil. LƯU Ý: test tua giờ Anvil TIẾN LÊN vĩnh viễn (về giờ thật: scripts/bootstrap.sh --fresh).
"""
import importlib.util
import io
from pathlib import Path

import pytest
from web3 import Web3
from web3.exceptions import ContractCustomError, ContractLogicError

from slopee_web3.application.dispute_force_service import DisputeForceResolveService
from slopee_web3.domain.errors import DomainError
from test_w3_chain_anvil import _mined, stack, svc  # noqa: F401
from test_w3_dispute_b_anvil import DRig
from w3_support import ADDR, connect

pytestmark = [pytest.mark.mysql, pytest.mark.anvil]
DAY = 86400
TABLES = ('dispute_force_resolutions', 'dispute_signatures', 'dispute_resolutions', 'dispute_notes')

_spec = importlib.util.spec_from_file_location('reconcile_script', Path(__file__).resolve().parents[2] / 'scripts' / 'reconcile.py')
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


class TRig(DRig):
    def __init__(self, svc):
        super().__init__(svc)
        self.force = DisputeForceResolveService(self.uow, self.chain, self.clock, self.relayer)

    def set_dispute_timeout(self, seconds):
        self.cur.execute("UPDATE category_policies SET dispute_timeout=%s WHERE is_default=1", (int(seconds),))

    def chain_order(self, oid):
        return self.chain.get_order(oid)

    def to(self, ts):
        """Tua tới `ts` (giờ block) nếu chưa tới."""
        gap = int(ts) - self.clock.now_chain()
        if gap > 0:
            self.travel(gap)

    def audit(self, code):
        self.cur.execute("SELECT * FROM dispute_force_resolutions WHERE order_id=%s", (code,))
        return list(self.cur.fetchall())

    def script(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        return script.main(list(argv), service=self.reconcile, out=out, err=err, sleep=lambda s: None), out.getvalue()


def _wipe(cur):
    for t in TABLES:
        cur.execute(f"DELETE FROM {t}")


@pytest.fixture
def trig(svc):
    _wipe(svc[0])
    r = TRig(svc)
    for t in ('notifications', 'tx_outbox', 'shipper_assignments', 'pending_balances', 'order_quotes', 'order_web3', 'checkout_groups', 'orders'):
        r.cur.execute(f"DELETE FROM {t}")
    r.cur.execute("SELECT dispute_timeout FROM category_policies WHERE is_default=1")
    saved = r.cur.fetchone()['dispute_timeout']
    yield r
    r.cur.execute("UPDATE category_policies SET dispute_timeout=%s WHERE is_default=1", (saved,))
    _wipe(r.cur)
    r.queue.close()


ACCESS_DENIED = '0xe2517d3f'         # selector của lỗi OpenZeppelin v5 AccessControlUnauthorizedAccount(address,bytes32)


def assert_reconciled(r, base_diff, *oids):
    """Chuỗi Anvil dùng chung còn tiền/sự kiện của test khác nên không đòi `ok` tuyệt đối: đòi ĐỘ LỆCH TIỀN không đổi so với trước test,
    không đơn mở nào lệch trạng thái, và tập đơn mở theo `chain_events` khớp CSDL cho CHÍNH các đơn của test này."""
    rec = r.reconcile.run(deep=True, events=True)
    tok = [t for t in rec['tokens'] if t['token'] == r.s.token_address.lower()][0]
    assert int(tok['diff_raw']) == base_diff and rec['order_mismatches'] == []
    assert [d for d in rec['event_order_drift'] if d['onchain_order_id'] in oids] == []


def _contract_force_call(r, oid, to, sender):
    """eth_call thẳng contract thật: revert nếu sai người ký hoặc chưa tới mốc."""
    return r.chain.contract.functions.arbitratorForceResolve(oid, Web3.to_checksum_address(to)).call({'from': Web3.to_checksum_address(sender)})


@pytest.mark.parametrize('days', [7, 30, 90])
@pytest.mark.parametrize('payout', ['BUYER', 'MERCHANT'])
def test_real_chain_dispute_timeout_force_resolve_for_each_timeout(trig, days, payout):
    r = trig
    r.set_dispute_timeout(days * DAY)
    base_diff = r.diff()
    buyer, merchant, code, oid = r.disputed()
    on = r.chain_order(oid)
    assert on['dispute_timeout'] == days * DAY                                                  # chính sách thật đã vào báo giá và contract
    at = on['disputed_at'] + on['dispute_timeout']

    # --- trước mốc: dịch vụ từ chối và contract thật cũng từ chối (hai bên nhất trí), không giao dịch nào được gửi
    r.to(at - 120)
    with pytest.raises(DomainError) as e:
        r.force.force_resolve(r.admin, code, payout)
    assert e.value.code == 'FORCE_RESOLVE_TOO_EARLY' and 0 < e.value.extra['seconds_remaining'] <= 120 + 60
    with pytest.raises(ContractLogicError, match='timeout not reached'):
        _contract_force_call(r, oid, on['buyer'], ADDR['arbitrator'])
    assert r.cur.execute("SELECT 1 FROM tx_outbox WHERE kind='FORCE_RESOLVE'") == 0               # không giao dịch nào được gửi
    assert r.chain.get_order_state(oid) == 'DISPUTED'

    # --- khóa SHIPPER không có quyền Trọng tài: contract thật từ chối bất kể thời gian (chặn lỗi dùng nhầm khóa)
    r.to(at + 5)
    with pytest.raises(ContractCustomError, match=ACCESS_DENIED):
        _contract_force_call(r, oid, on['buyer'], ADDR['shipper'])

    # --- sau mốc: Admin xử đơn phương
    side_addr = on['buyer'] if payout == 'BUYER' else on['merchant']
    b0, m0, e0 = r.bal(on['buyer']), r.bal(on['merchant']), r.bal(r.chain.address)
    out = r.force.force_resolve(r.admin, code, payout, f'Không phản hồi sau {days} ngày')
    assert out['outcome'] == 'SENT' and out['payout_to'].lower() == side_addr.lower()
    amount, fee = on['amount'], on['amount'] * on['fee_bps'] // 10_000
    if payout == 'BUYER':
        assert r.chain.get_order_state(oid) == 'REFUNDED' and r.bal(on['buyer']) - b0 == amount and r.bal(on['merchant']) == m0
    else:
        assert r.chain.get_order_state(oid) == 'COMPLETED' and r.bal(on['merchant']) - m0 == amount - fee and r.bal(on['buyer']) == b0
    assert e0 - r.bal(r.chain.address) == amount                                                # contract hết đúng khoản của đơn

    r.index()                                                                                    # Indexer giải mã log THẬT (ArbitratorForceResolved)
    assert r.status(code) == ('REFUNDED' if payout == 'BUYER' else 'COMPLETED')
    assert r.row("SELECT anomaly_flag AS a FROM order_web3 WHERE order_id=%s", code)['a'] == 0
    r.cur.execute("SELECT COUNT(*) AS c FROM notifications WHERE kind='DISPUTE_RESOLVED'")
    assert r.cur.fetchone()['c'] == 2
    a = r.audit(code)
    assert len(a) == 1 and a[0]['admin_user_id'] == r.admin and a[0]['tx_hash'] == out['tx_hash'] and a[0]['payout_side'] == payout
    assert r.diff() == base_diff
    assert_reconciled(r, base_diff, oid)

    # --- lặp lại là idempotent, chọn ngược lại bị từ chối, không tốn thêm gas
    assert r.force.force_resolve(r.admin, code, payout)['outcome'] == 'ALREADY_RESOLVED'
    with pytest.raises(DomainError) as e2:
        r.force.force_resolve(r.admin, code, 'MERCHANT' if payout == 'BUYER' else 'BUYER')
    assert e2.value.code == 'INVALID_STATE' and len(r.audit(code)) == 1


def test_real_chain_delivery_timeout_buyer_cancels_after_14_days_and_is_refunded(trig):
    r = trig
    base_diff = r.diff()
    buyer, out, shipper = r.locked_order()                                                       # LOCKED, shipper đã được gán nhưng KHÔNG giao
    o = out['orders'][0]
    oid, code = int(o['onchain_order_id']), o['order_id']
    on = r.chain_order(oid)
    due = on['created_at'] + 14 * DAY
    buyer_addr = Web3.to_checksum_address(ADDR['buyer'])

    r.to(due - 120)
    with pytest.raises(ContractLogicError, match='Timeout not reached'):                         # đúng thông báo giao diện của C dịch sang tiếng Việt
        r.chain.contract.functions.cancelIfUnfulfilled(oid).call({'from': buyer_addr})
    r.to(due + 5)
    with pytest.raises(ContractLogicError, match='Unauthorized'):                                # người lạ không hủy hộ được
        r.chain.contract.functions.cancelIfUnfulfilled(oid).call({'from': Web3.to_checksum_address(ADDR['stranger'])})

    b0, e0 = r.bal(ADDR['buyer']), r.bal(r.chain.address)
    _mined(r.chain, r.chain.contract.functions.cancelIfUnfulfilled(oid).transact({'from': buyer_addr}))
    assert r.bal(ADDR['buyer']) - b0 == on['amount'] and e0 - r.bal(r.chain.address) == on['amount']      # hoàn 100%, không thu phí
    r.index()
    assert r.status(code) == 'REFUNDED' and r.row("SELECT anomaly_flag AS a FROM order_web3 WHERE order_id=%s", code)['a'] == 0
    assert r.row("SELECT status FROM orders WHERE id=%s", code)['status'] == 'cancelled'
    assert r.diff() == base_diff
    assert_reconciled(r, base_diff, oid)


def test_real_chain_nothing_is_left_stuck_after_both_timeout_paths(trig):
    """E-06 / M3: sau cả hai lối thoát, đối soát (script) trên chuỗi thật không thêm lệch nào, không đơn nào còn mở, hai đơn đều REFUNDED."""
    r = trig
    r.set_dispute_timeout(7 * DAY)
    base_diff = r.diff()
    base_exit, _ = r.script('--deep')                              # chuỗi dùng chung có thể đã lệch từ test khác (tiền chuyển lạ): so với mốc này
    buyer, merchant, code, oid = r.disputed()
    on = r.chain_order(oid)
    r.to(on['disputed_at'] + on['dispute_timeout'] + 5)
    r.force.force_resolve(r.admin, code, 'BUYER')
    r.cur.execute("DELETE FROM user_wallets")                      # `_checkout` dựng lại ví Buyer/Merchant (UNIQUE theo địa chỉ)
    buyer2, out, shipper = r.locked_order()
    o2 = out['orders'][0]
    oid2 = int(o2['onchain_order_id'])
    r.to(r.chain_order(oid2)['created_at'] + 14 * DAY + 5)
    _mined(r.chain, r.chain.contract.functions.cancelIfUnfulfilled(oid2).transact({'from': Web3.to_checksum_address(ADDR['buyer'])}))
    r.index()
    code_exit, report = r.script('--deep', '--events')
    assert (code_exit == 0) == (base_exit == 0) or base_exit != 0                               # sạch khi chuỗi sạch; không tệ hơn mốc khi chuỗi đã dơ
    assert 'KẾT QUẢ' in report
    assert r.status(code) == 'REFUNDED' and r.status(o2['order_id']) == 'REFUNDED'
    assert r.diff() == base_diff
    assert_reconciled(r, base_diff, oid, oid2)
    r.cur.execute("SELECT COUNT(*) AS c FROM order_web3 WHERE status IN ('LOCKED','DELIVERED','DISPUTED')")
    assert r.cur.fetchone()['c'] == 0
