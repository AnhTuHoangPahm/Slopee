"""Tuần 6 [Q] (Thành viên C), E-03 phía backend: giải quyết tranh chấp bằng 2/3 chữ ký EIP-712 trên CHUỖI THẬT + MySQL thật.

  Ký quỹ -> Shipper giao -> Buyer khiếu nại -> Indexer ghi DISPUTED -> "Admin" đề xuất (đọc nonce, deadline < disputedAt + timeout)
  -> Trọng tài + một bên ký -> relayer nộp `resolveDispute` -> tiền đi đúng chỗ -> Indexer ghi REFUNDED / COMPLETED.

Hai hướng: HOÀN TIỀN BUYER (100%, không phí) và GIẢI NGÂN MERCHANT (trừ phí theo BR-02). Mỗi đơn con độc lập (BR-11).

`DisputeService` của Thành viên B (đề xuất + chữ ký Trọng tài) chưa có ở thời điểm viết, nên các bước "Admin" dưới đây TỰ LÀM đúng quy tắc
SRS UC-06 bằng khóa Trọng tài của Anvil và `shared/eip712/types.json` (cùng cách `EnvKeySigner.sign_quote` ký báo giá). Khi B làm xong,
thay hàm `_propose` bằng lời gọi dịch vụ thật; phần còn lại giữ nguyên. Handler `DisputeResolved` của Indexer là việc của B (Tuần 6):
test chỉ kiểm trạng thái đơn do `OrderRefunded`/`OrderCompleted` ghi (đã có).

Tự skip nếu không có Anvil/MySQL. Chạy: ./scripts/bootstrap.sh --fresh --force-env && pytest -m anvil test/integration_test/test_w6_dispute_resolution_anvil.py
"""
import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3
from web3.exceptions import ContractLogicError

from slopee_web3.adapters.clock import HybridClock
from slopee_web3.adapters.env_signer import load_eip712_types
from w3_support import ADDR, CHAIN_ID, ESCROW, KEYS
from test_w3_chain_anvil import stack, svc  # noqa: F401  (fixture dùng chung)
from test_w5_happy_path_anvil import _bal, _db_status, _index, _locked_orders, _restore_onchain_id_seq, _send  # noqa: F401

pytestmark = [pytest.mark.mysql, pytest.mark.anvil]

SEVEN_DAYS = 7 * 86400
ORDER_FIELDS = ['buyer', 'merchant', 'token', 'amount', 'createdAt', 'deliveredAt', 'disputedAt', 'disputeTimeout', 'inspectionDuration', 'feeBps', 'state', 'docHash']
STATE = {'NONE': 0, 'LOCKED': 1, 'DELIVERED': 2, 'DISPUTED': 3, 'COMPLETED': 4, 'REFUNDED': 5}


def _order(chain, oid):
    return dict(zip(ORDER_FIELDS, chain.contract.functions.orders(int(oid)).call()))


def _sign_dispute(key_name, *, order_id, payout_to, amount, nonce, deadline):
    """Chữ ký EIP-712 `DisputeResolution` bằng khóa của `key_name` (đúng thứ tự trường của shared/eip712/types.json)."""
    full = {
        'types': {'EIP712Domain': [{'name': 'name', 'type': 'string'}, {'name': 'version', 'type': 'string'},
                                   {'name': 'chainId', 'type': 'uint256'}, {'name': 'verifyingContract', 'type': 'address'}],
                  'DisputeResolution': load_eip712_types()['DisputeResolution']},
        'primaryType': 'DisputeResolution',
        'domain': {'name': 'SlopeeEscrow', 'version': '1', 'chainId': CHAIN_ID, 'verifyingContract': Web3.to_checksum_address(ESCROW)},
        'message': {'orderId': int(order_id), 'payoutTo': Web3.to_checksum_address(payout_to), 'amount': int(amount), 'nonce': int(nonce), 'deadline': int(deadline)},
    }
    sig = Account.sign_message(encode_typed_data(full_message=full), KEYS[key_name]).signature.hex()
    return bytes.fromhex(sig[2:] if sig.startswith('0x') else sig)


def _propose(chain, clock, oid, payout_to, *, ttl=SEVEN_DAYS, deadline=None):
    """Việc của Admin (SRS UC-06 bước 1-2): đọc nonce từ contract, deadline = min(now_chain + ttl, disputedAt + timeout - 1)."""
    o = _order(chain, oid)
    nonce = chain.contract.functions.disputeNonces(int(oid)).call()
    dl = deadline if deadline is not None else min(clock.now_chain() + ttl, o['disputedAt'] + o['disputeTimeout'] - 1)
    msg = {'order_id': oid, 'payout_to': payout_to, 'amount': o['amount'], 'nonce': nonce, 'deadline': dl}
    return {**msg, 'arbitrator_sig': _sign_dispute('arbitrator', **msg)}


def _resolve(chain, oid, p, sigs, *, payout_to=None, deadline=None, by='shipper'):
    """Relayer/bất kỳ ai nộp. `by` là tài khoản mở khóa sẵn của Anvil."""
    return chain.contract.functions.resolveDispute(
        int(oid), Web3.to_checksum_address(payout_to or p['payout_to']), int(deadline if deadline is not None else p['deadline']), sigs[0], sigs[1],
    ).transact({'from': Web3.to_checksum_address(ADDR[by])})


def _mine(chain, tx):
    r = chain.w3.eth.wait_for_transaction_receipt(tx, timeout=30)
    assert r['status'] == 1
    return r


def _disputed(svc, shops=1):
    """Checkout + nạp thật, rồi đơn ĐẦU giao hàng và bị khiếu nại. Trả (buyer_id, orders, clock)."""
    cur, quote, signer, chain, token, s = svc
    buyer_id, orders = _locked_orders(svc, shops=shops)
    oid = int(orders[0]['onchain_order_id'])
    _send(chain, 'confirmDelivery', oid, 'shipper')
    _send(chain, 'raiseDispute', oid, 'buyer')
    assert chain.get_order_state(oid) == 'DISPUTED'
    return buyer_id, orders, HybridClock(chain)


# ---------------------------------------------------------------------------------------------------------------------
def test_e03_refund_buyer_full_flow_and_other_shop_order_is_untouched(svc):
    cur, quote, signer, chain, token, s = svc
    buyer_id, (a, b), clock = _disputed(svc, shops=2)
    ida, idb = int(a['onchain_order_id']), int(b['onchain_order_id'])

    _index(chain)
    st = _db_status(buyer_id, a['order_id'], clock)
    assert st['status'] == 'DISPUTED' and st['disputed_at'] == _order(chain, ida)['disputedAt']   # Indexer ghi đúng mốc từ chuỗi

    # Admin đề xuất hoàn tiền cho Buyer; Trọng tài ký; Buyer ký
    p = _propose(chain, clock, ida, ADDR['buyer'])
    limit = _order(chain, ida)['disputedAt'] + _order(chain, ida)['disputeTimeout']
    assert clock.now_chain() < p['deadline'] < limit                                    # SRS: chữ ký hết hạn TRƯỚC khi Trọng tài có quyền đơn phương
    sigs = [p['arbitrator_sig'], _sign_dispute('buyer', **{k: p[k] for k in ('order_id', 'payout_to', 'amount', 'nonce', 'deadline')})]

    amount = _order(chain, ida)['amount']
    before = {k: _bal(token, ADDR[k]) for k in ('buyer', 'merchant1')}
    escrow_before = _bal(token, chain.address)
    _mine(chain, _resolve(chain, ida, p, sigs))

    assert chain.get_order_state(ida) == 'REFUNDED' and chain.get_order_state(idb) == 'LOCKED'      # BR-11
    assert _bal(token, ADDR['buyer']) - before['buyer'] == amount                       # hoàn 100%, KHÔNG trừ phí
    assert _bal(token, ADDR['merchant1']) == before['merchant1']
    assert escrow_before - _bal(token, chain.address) == amount
    assert chain.contract.functions.disputeNonces(ida).call() == 1

    _index(chain)
    done = _db_status(buyer_id, a['order_id'], clock)
    # Test này nộp resolveDispute THẲNG lên chuỗi, không qua đề xuất của sàn (không có dòng dispute_resolutions): chữ ký Trọng tài chỉ máy chủ có,
    # nên một phán quyết xuất hiện ngoài sàn là điều Admin phải được cảnh báo ⇒ handler DisputeResolved của B gắn anomaly_flag (đơn vẫn REFUNDED/COMPLETED).
    # Luồng ĐÚNG qua sàn (propose -> ký -> submit -> EXECUTED, không anomaly) do test_w3_dispute_b_anvil.py kiểm.
    assert done['status'] == 'REFUNDED' and done['anomaly'] is True
    assert _db_status(buyer_id, b['order_id'], clock)['status'] == 'LOCKED'

    # phát lại chữ ký không chuyển tiền lần hai
    with pytest.raises(ContractLogicError, match='Not disputed'):
        _resolve(chain, ida, p, sigs)


def test_e03_pay_merchant_full_flow_charges_the_fee(svc):
    cur, quote, signer, chain, token, s = svc
    buyer_id, (o,), clock = _disputed(svc)
    oid = int(o['onchain_order_id'])
    _index(chain)
    assert _db_status(buyer_id, o['order_id'], clock)['status'] == 'DISPUTED'

    p = _propose(chain, clock, oid, ADDR['merchant1'])
    sigs = [p['arbitrator_sig'], _sign_dispute('merchant1', **{k: p[k] for k in ('order_id', 'payout_to', 'amount', 'nonce', 'deadline')})]
    od = _order(chain, oid)
    fee_to = chain.contract.functions.feeRecipient().call()
    m_before, f_before, b_before = _bal(token, ADDR['merchant1']), _bal(token, fee_to), _bal(token, ADDR['buyer'])
    _mine(chain, _resolve(chain, oid, p, sigs))

    fee = od['amount'] * od['feeBps'] // 10_000
    assert fee > 0
    assert chain.get_order_state(oid) == 'COMPLETED'
    assert _bal(token, ADDR['merchant1']) - m_before == od['amount'] - fee              # giải ngân trừ phí (BR-02)
    assert _bal(token, fee_to) - f_before == fee
    assert _bal(token, ADDR['buyer']) == b_before                                       # Buyer không được hoàn

    _index(chain)
    done = _db_status(buyer_id, o['order_id'], clock)
    # Test này nộp resolveDispute THẲNG lên chuỗi, không qua đề xuất của sàn (không có dòng dispute_resolutions): chữ ký Trọng tài chỉ máy chủ có,
    # nên một phán quyết xuất hiện ngoài sàn là điều Admin phải được cảnh báo ⇒ handler DisputeResolved của B gắn anomaly_flag (đơn vẫn REFUNDED/COMPLETED).
    # Luồng ĐÚNG qua sàn (propose -> ký -> submit -> EXECUTED, không anomaly) do test_w3_dispute_b_anvil.py kiểm.
    assert done['status'] == 'COMPLETED' and done['anomaly'] is True


def test_e03_deadline_exactly_one_second_before_the_dispute_timeout_is_accepted(svc):
    cur, quote, signer, chain, token, s = svc
    _, (o,), clock = _disputed(svc)
    oid = int(o['onchain_order_id'])
    od = _order(chain, oid)
    p = _propose(chain, clock, oid, ADDR['buyer'], deadline=od['disputedAt'] + od['disputeTimeout'] - 1)   # biên trên hợp lệ
    sigs = [p['arbitrator_sig'], _sign_dispute('buyer', **{k: p[k] for k in ('order_id', 'payout_to', 'amount', 'nonce', 'deadline')})]
    _mine(chain, _resolve(chain, oid, p, sigs))
    assert chain.get_order_state(oid) == 'REFUNDED'


def test_e03_contract_rejections_leave_the_order_disputed(svc):
    cur, quote, signer, chain, token, s = svc
    _, (o,), clock = _disputed(svc)
    oid = int(o['onchain_order_id'])
    od = _order(chain, oid)
    p = _propose(chain, clock, oid, ADDR['buyer'])
    fields = ('order_id', 'payout_to', 'amount', 'nonce', 'deadline')
    arb, buyer = p['arbitrator_sig'], _sign_dispute('buyer', **{k: p[k] for k in fields})
    stranger = _sign_dispute('stranger', **{k: p[k] for k in fields})

    cases = [
        ('hai chữ ký cùng một bên', [buyer, buyer], {}, 'Need two distinct parties'),
        ('hai chữ ký cùng Trọng tài', [arb, arb], {}, 'Need two distinct parties'),
        ('chữ ký của người ngoài bộ ba', [arb, stranger], {}, 'Need two distinct parties'),
        ('payoutTo là người lạ', [arb, buyer], {'payout_to': ADDR['stranger']}, 'Invalid payout recipient'),
        ('đổi payoutTo sau khi ký', [arb, buyer], {'payout_to': ADDR['merchant1']}, 'Need two distinct parties'),
        ('deadline = disputedAt + timeout', [arb, buyer], {'deadline': od['disputedAt'] + od['disputeTimeout']}, 'Deadline must be before dispute timeout'),
    ]
    for name, sigs, over, reason in cases:
        with pytest.raises(ContractLogicError, match=reason):
            _resolve(chain, oid, p, sigs, **over)
        assert chain.get_order_state(oid) == 'DISPUTED', name
        assert chain.contract.functions.disputeNonces(oid).call() == 0, name           # revert hoàn tác mức tăng nonce

    # sai số tiền / sai nonce trong chữ ký
    for bad in ({**p, 'amount': p['amount'] - 1}, {**p, 'nonce': p['nonce'] + 1}):
        sigs = [_sign_dispute('arbitrator', **{k: bad[k] for k in fields}), _sign_dispute('buyer', **{k: bad[k] for k in fields})]
        with pytest.raises(ContractLogicError, match='Need two distinct parties'):
            _resolve(chain, oid, p, sigs)

    # chữ ký hợp lệ vẫn dùng được sau tất cả các lần bị từ chối (nonce không bị "đốt")
    _mine(chain, _resolve(chain, oid, p, [arb, buyer]))
    assert chain.get_order_state(oid) == 'REFUNDED'


def test_e03_expired_signature_is_rejected_and_admin_can_issue_a_new_proposal(svc):
    cur, quote, signer, chain, token, s = svc
    from test_w5_happy_path_anvil import _time_travel
    _, (o,), clock = _disputed(svc)
    oid = int(o['onchain_order_id'])
    fields = ('order_id', 'payout_to', 'amount', 'nonce', 'deadline')

    p1 = _propose(chain, clock, oid, ADDR['buyer'], ttl=30)
    sigs1 = [p1['arbitrator_sig'], _sign_dispute('buyer', **{k: p1[k] for k in fields})]
    _time_travel(chain, 120)                                                            # chữ ký hết hạn (UC-06 luồng thay thế)
    with pytest.raises(ContractLogicError, match='Signature expired'):
        _resolve(chain, oid, p1, sigs1)
    assert chain.get_order_state(oid) == 'DISPUTED'

    p2 = _propose(chain, clock, oid, ADDR['buyer'])                                     # Admin tạo đề xuất mới: nonce vẫn 0 (chưa thi hành)
    assert p2['nonce'] == p1['nonce'] and p2['deadline'] > clock.now_chain()
    sigs2 = [p2['arbitrator_sig'], _sign_dispute('buyer', **{k: p2[k] for k in fields})]
    _mine(chain, _resolve(chain, oid, p2, sigs2))
    assert chain.get_order_state(oid) == 'REFUNDED'
