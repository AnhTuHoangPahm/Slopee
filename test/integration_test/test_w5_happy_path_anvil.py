"""Tuần 5 [Q] (Thành viên C): kịch bản tích hợp Happy Path trên CHUỖI THẬT (Anvil + contract của bootstrap.sh) + MySQL thật.

  E-01  Ký quỹ gom -> Indexer ghi LOCKED -> Shipper giao (confirmDelivery) -> Buyer "Đã nhận hàng" (earlyRelease) -> chia tiền.
        Mỗi shop là một đơn độc lập (BR-11): giải ngân đơn A không đụng tới đơn B.
  I-05  Đồng hồ máy chủ bám Anvil khi bị tua giờ (evm_increaseTime): HybridClock/server_time nhảy theo, hết hạn kiểm tra thì
        contract chặn Khiếu nại ("Expired") và cho giải ngân sau kiểm tra, còn trước hạn thì chặn ("Under inspection").
  Thêm: Khiếu nại trong hạn đóng băng tiền; người lạ không thao tác được đơn của Buyer.

Các lý do revert ở đây là CHUỖI THẬT mà giao diện (lib/orderActions.js::mapOrderActionError) phải dịch đúng.

Bước DB sau LOCKED (DELIVERED/COMPLETED) cần handler Indexer của Thành viên B (hiện HANDLERS chỉ có OrderCreated): phần đó
`xfail` có lý do và CHỈ chạy sau khi mọi kiểm tra trên chuỗi đã xong; B thêm handler thì tự thành PASS (bỏ phần xfail cho gọn).

Tự skip nếu không có Anvil/MySQL. Chạy: ./scripts/bootstrap.sh --fresh --force-env && pytest -m anvil test/integration_test/test_w5_happy_path_anvil.py
Lưu ý: I-05 TUA GIỜ Anvil tiến lên vĩnh viễn trên node đang chạy; muốn trả về giờ thật hãy chạy lại bootstrap.sh --fresh.
"""
import pytest
from web3 import Web3
from web3.exceptions import ContractLogicError

from slopee_web3.adapters.clock import HybridClock
from slopee_web3.adapters.indexer import Indexer
from slopee_web3.adapters.indexer.handlers import HANDLERS
from slopee_web3.application.order_status_service import OrderStatusService
from slopee_web3.adapters.mysql_repos import MySqlUnitOfWork
from slopee_web3.ports.chain_port import ORDER_STATES
from w3_support import ADDR, connect
from test_w3_chain_anvil import _checkout, _deposit, _fund_and_approve, _mined, stack, svc  # noqa: F401  (fixture dùng chung)

pytestmark = [pytest.mark.mysql, pytest.mark.anvil]

STATE = {name: i for i, name in enumerate(ORDER_STATES)}


@pytest.fixture(scope='module', autouse=True)
def _restore_onchain_id_seq(mysql_db):
    """Fixture `svc` (test_w3_chain_anvil) đẩy AUTO_INCREMENT của onchain_id_seq lên mili-giây hiện tại để id on-chain không
    trùng lần chạy trước trên cùng Anvil, nhưng DB test dùng chung cả phiên. Trả về 100001 (như schema.sql) khi xong module,
    nếu không test_web3_migrations (so lược đồ nâng cấp với lược đồ mới) có thể đỏ tùy thứ tự chạy. Bảng không có khóa ngoại."""
    yield
    conn = connect()
    try:
        conn.autocommit(True)
        cur = conn.cursor()
        cur.execute('DELETE FROM onchain_id_seq')
        cur.execute('ALTER TABLE onchain_id_seq AUTO_INCREMENT = 100001')
    finally:
        conn.close()


# ---------------------------------------------------------------------------------------------------------------------
# tiện ích
# ---------------------------------------------------------------------------------------------------------------------
def _send(chain, fn, oid, who):
    """Gọi contract bằng tài khoản mở khóa sẵn của Anvil và chờ block (Anvil --block-time 2)."""
    tx = getattr(chain.contract.functions, fn)(int(oid)).transact({'from': Web3.to_checksum_address(ADDR[who])})
    return _mined(chain, tx)


def _reverts(chain, fn, oid, who, reason):
    """Contract THẬT phải từ chối với đúng lý do. web3.py mô phỏng trước khi gửi nên không tốn block."""
    with pytest.raises(ContractLogicError, match=reason):
        getattr(chain.contract.functions, fn)(int(oid)).transact({'from': Web3.to_checksum_address(ADDR[who])})


def _order(chain, oid):
    o = chain.contract.functions.orders(int(oid)).call()
    return {'state': o[10], 'amount': o[3], 'delivered_at': o[5], 'disputed_at': o[6], 'inspection': o[8], 'fee_bps': o[9]}


def _bal(token, who):
    return token.functions.balanceOf(Web3.to_checksum_address(who)).call()


def _time_travel(chain, seconds):
    chain.w3.provider.make_request('evm_increaseTime', [int(seconds)])
    chain.w3.provider.make_request('evm_mine', [])


def _db_status(buyer_id, order_code, clock):
    return OrderStatusService(lambda: MySqlUnitOfWork(connect), clock).get_status(buyer_id, 'user', order_code)


def _index(chain):
    conn = connect()
    try:
        return Indexer(connect, chain, start_block=0).run_once(conn)
    finally:
        conn.close()


def _locked_orders(svc, shops=1):
    """Checkout thật -> nạp thật -> trả (buyer_id, các đơn đã LOCKED trên chuỗi)."""
    cur, quote, signer, chain, token, s = svc
    buyer_id, out = _checkout(cur, quote, shops=shops)
    _fund_and_approve(chain, token, s, int(out['total_amount_raw']))
    _deposit(chain, out['orders'])
    for o in out['orders']:
        assert chain.get_order_state(int(o['onchain_order_id'])) == 'LOCKED'
    return buyer_id, out['orders']


# ---------------------------------------------------------------------------------------------------------------------
# E-01 — Happy Path
# ---------------------------------------------------------------------------------------------------------------------
def test_e01_happy_path_lock_deliver_early_release_and_orders_are_independent(svc):
    cur, quote, signer, chain, token, s = svc
    clock = HybridClock(chain)
    buyer_id, orders = _locked_orders(svc, shops=2)
    a, b = orders
    ida, idb = int(a['onchain_order_id']), int(b['onchain_order_id'])
    seen = {}

    # --- Indexer ghi LOCKED vào DB (đã có từ Tuần 3-4): đây là điều giao diện polling đọc được
    _index(chain)
    seen['locked'] = [_db_status(buyer_id, o['order_id'], clock)['status'] for o in orders]

    # --- trước khi giao: Buyer chưa thể "Đã nhận hàng" (nút chỉ bật ở DELIVERED)
    _reverts(chain, 'earlyRelease', ida, 'buyer', 'Not delivered')

    # --- Shipper giao đơn A (việc của relayer): chỉ A chuyển DELIVERED, B vẫn LOCKED (BR-11)
    _send(chain, 'confirmDelivery', ida, 'shipper')
    assert chain.get_order_state(ida) == 'DELIVERED' and chain.get_order_state(idb) == 'LOCKED'
    da = _order(chain, ida)
    assert da['delivered_at'] > 0 and da['inspection'] == int(a['inspection_duration'])
    _index(chain)
    seen['delivered'] = _db_status(buyer_id, a['order_id'], clock)

    # --- người không phải Buyer không giải ngân hộ được (giao diện cũng khóa theo ví đã ký quỹ)
    _reverts(chain, 'earlyRelease', ida, 'merchant2', 'Only buyer')

    # --- Buyer "Đã nhận hàng": tiền chia đúng theo phí đã khóa lúc ký quỹ
    amount, bps = int(a['amount_raw']), int(a['fee_bps'])
    fee_to = chain.contract.functions.feeRecipient().call()
    merchant_before, fee_before = _bal(token, a['quote']['merchant']), _bal(token, fee_to)
    escrow_before = _bal(token, chain.address)
    _send(chain, 'earlyRelease', ida, 'buyer')
    assert chain.get_order_state(ida) == 'COMPLETED' and chain.get_order_state(idb) == 'LOCKED'
    fee = amount * bps // 10_000
    assert _bal(token, a['quote']['merchant']) - merchant_before == amount - fee
    assert _bal(token, fee_to) - fee_before == fee
    assert escrow_before - _bal(token, chain.address) == amount           # escrow chỉ giảm đúng đơn A (đơn B vẫn bị khóa)
    # giải ngân xong thì không giải ngân/khiếu nại lại được
    _reverts(chain, 'earlyRelease', ida, 'buyer', 'Not delivered')
    _reverts(chain, 'raiseDispute', ida, 'buyer', 'Not delivered')
    _index(chain)
    seen['completed'] = _db_status(buyer_id, a['order_id'], clock)

    # --- khẳng định phía DB: LOCKED chắc chắn có; DELIVERED/COMPLETED cần handler của B
    assert seen['locked'] == ['LOCKED', 'LOCKED']
    missing = [e for e in ('OrderDelivered', 'OrderCompleted') if e not in HANDLERS]
    if missing:
        pytest.xfail(f'Indexer chưa có handler {missing} (việc của Thành viên B, Tuần 5): chuỗi đã đúng, DB chưa theo kịp')
    assert seen['delivered']['status'] == 'DELIVERED' and seen['delivered']['delivered_at'] == da['delivered_at']
    assert seen['completed']['status'] == 'COMPLETED'
    assert _db_status(buyer_id, b['order_id'], clock)['status'] == 'LOCKED'


def test_dispute_inside_the_window_freezes_the_order(svc):
    cur, quote, signer, chain, token, s = svc
    buyer_id, (o,) = _locked_orders(svc)
    oid = int(o['onchain_order_id'])
    _send(chain, 'confirmDelivery', oid, 'shipper')
    _reverts(chain, 'raiseDispute', oid, 'merchant2', 'Only buyer')       # người lạ không khiếu nại hộ được
    escrow_before = _bal(token, chain.address)
    _send(chain, 'raiseDispute', oid, 'buyer')
    st = _order(chain, oid)
    assert st['state'] == STATE['DISPUTED'] and st['disputed_at'] >= st['delivered_at']
    assert _bal(token, chain.address) == escrow_before                       # tiền đóng băng, không ai rút được
    _reverts(chain, 'earlyRelease', oid, 'buyer', 'Not delivered')            # đã khiếu nại thì không "Đã nhận hàng" nữa
    _reverts(chain, 'releaseAfterInspection', oid, 'merchant2', 'Not delivered')   # không tự giải ngân khi đang tranh chấp


# ---------------------------------------------------------------------------------------------------------------------
# I-05 — đồng hồ máy chủ bám Anvil khi tua giờ
# ---------------------------------------------------------------------------------------------------------------------
def test_i05_server_time_follows_time_travel_and_locks_the_dispute_button(svc):
    cur, quote, signer, chain, token, s = svc
    clock = HybridClock(chain)
    buyer_id, (o,) = _locked_orders(svc)
    oid = int(o['onchain_order_id'])
    _send(chain, 'confirmDelivery', oid, 'shipper')
    st = _order(chain, oid)
    deadline = st['delivered_at'] + st['inspection']

    # Còn hạn: giao diện hiện đồng hồ dương, nút Khiếu nại bật; contract không cho giải ngân sau kiểm tra sớm
    before = clock.now_chain()
    assert 0 < deadline - before <= st['inspection'] + 5
    _reverts(chain, 'releaseAfterInspection', oid, 'merchant2', 'Under inspection')

    # Tua quá hạn kiểm tra: server_time (HybridClock) phải NHẢY theo chuỗi dù đồng hồ hệ thống không đổi
    _time_travel(chain, st['inspection'] + 60)
    after = clock.now_chain()
    assert after >= deadline + 1 and after - before >= st['inspection']      # = đúng điều giao diện cần để đồng hồ về 0
    assert after >= int(chain.latest_block()['timestamp'])
    _index(chain)
    if 'OrderDelivered' in HANDLERS:
        status = _db_status(buyer_id, o['order_id'], clock)
        assert status['server_time'] >= deadline and status['status'] == 'DELIVERED'

    # Hết hạn: Khiếu nại bị contract chặn, còn "Đã nhận hàng" và giải ngân sau kiểm tra vẫn hợp lệ (đúng quy tắc nút ở SDD 9.4)
    _reverts(chain, 'raiseDispute', oid, 'buyer', 'Expired')
    _send(chain, 'releaseAfterInspection', oid, 'merchant2')               # bất kỳ ai gọi được (AutoRelease của B dùng đường này)
    assert chain.get_order_state(oid) == 'COMPLETED'

    # Sau khi tua giờ, báo giá MỚI vẫn chuẩn: hạn tính theo đồng hồ chuỗi (không rơi vào quá khứ của block), contract nhận nạp
    cur_, quote_ = svc[0], svc[1]
    cur_.execute('DELETE FROM user_wallets')                                 # helper _checkout luôn gắn cùng ví Buyer (UNIQUE address)
    _, out = _checkout(cur_, quote_, shops=1)
    head = int(chain.latest_block()['timestamp'])
    assert int(out['orders'][0]['quote']['deadline']) > head + 600          # còn dư hạn đáng kể so với block hiện tại (TTL 15 phút)
    _fund_and_approve(chain, token, s, int(out['total_amount_raw']))
    _deposit(chain, out['orders'])
    assert chain.get_order_state(int(out['orders'][0]['onchain_order_id'])) == 'LOCKED'


def test_i05_early_release_is_still_valid_after_the_inspection_window(svc):
    cur, quote, signer, chain, token, s = svc
    buyer_id, (o,) = _locked_orders(svc)
    oid = int(o['onchain_order_id'])
    _send(chain, 'confirmDelivery', oid, 'shipper')
    _time_travel(chain, _order(chain, oid)['inspection'] + 60)
    _reverts(chain, 'raiseDispute', oid, 'buyer', 'Expired')
    _send(chain, 'earlyRelease', oid, 'buyer')                              # nút "Đã nhận hàng" không bị khóa khi hết hạn
    assert chain.get_order_state(oid) == 'COMPLETED'
