"""Tuần 3: miền thuần (tiền, chính sách, báo giá/docHash, liên kết ví, máy trạng thái) — không cần DB/chuỗi."""
import json

import pytest
from eth_utils import keccak

from slopee_web3.domain import money, order_state, policy, quote, wallet
from slopee_web3.domain.errors import DomainError, http_status
from w3_support import ROOT, VECTORS, ADDR


# ---------------------------------------------------------------- tiền (BR-08)
def test_vnd_to_token_matches_srs_example():
    fx = money.parse_fx_scaled('25000')
    assert money.vnd_to_token(399_000, 6, fx) == 15_960_000          # 15,96 mUSD


def test_vnd_to_token_rounds_up_never_down():
    fx = money.parse_fx_scaled('25000')
    assert money.vnd_to_token(1, 6, fx) == 40                         # 1 VND = 0,00004 mUSD
    assert money.vnd_to_token(25_001, 6, fx) == 1_000_040             # chia hết, không dư
    fx3 = money.parse_fx_scaled('3')
    assert money.vnd_to_token(10, 6, fx3) == 3_333_334                # 3.333333.. làm tròn LÊN


def test_vnd_to_token_never_uses_float_and_rejects_bad_input():
    with pytest.raises(ValueError):
        money.vnd_to_token(1.5, 6, 10 ** 8)
    with pytest.raises(ValueError):
        money.vnd_to_token(True, 6, 10 ** 8)
    with pytest.raises(ValueError):
        money.vnd_to_token(-1, 6, 10 ** 8)
    with pytest.raises(ValueError):
        money.vnd_to_token(1, 6, 0)


@pytest.mark.parametrize('bad', ['0', '-5', 'abc', '', 'NaN', 'Infinity', '1.00001', None])
def test_parse_fx_rejects_invalid(bad):
    with pytest.raises(DomainError) as e:
        money.parse_fx_scaled(bad)
    assert e.value.code == 'SETTING_INVALID'


def test_fx_roundtrip_and_fee_split():
    assert money.parse_fx_scaled('25000.5') == 250_005_000
    assert money.fx_to_str(250_005_000) == '25000.5000'
    assert money.fx_to_str(money.parse_fx_scaled('25000')) == '25000.0000'
    assert money.fee_split(16_500_000, 300) == (16_005_000, 495_000)
    assert money.fee_split(1, 300) == (1, 0)                          # fee làm tròn xuống như contract


def test_huge_amount_has_no_precision_loss():
    fx = money.parse_fx_scaled('0.0001')
    big = money.vnd_to_token(10 ** 15, 18, fx)
    assert big == 10 ** 15 * 10 ** 18 * 10 ** 4 // 1 // 1 and isinstance(big, int)


# ---------------------------------------------------------------- chính sách (BR-10)
def test_pick_durations_takes_max_of_each_independently():
    p1 = policy.Policy('A', 3600, 7_776_000)
    p2 = policy.Policy('B', 2_592_000, 604_800)
    insp, disp, dominant = policy.pick_durations([p1, p2])
    assert (insp, disp) == (2_592_000, 7_776_000)
    assert dominant.code == 'B'                                       # theo thời hạn kiểm tra lớn nhất


def test_pick_durations_deterministic_tie_break():
    a, b = policy.Policy('B', 86400, 604_800), policy.Policy('A', 86400, 604_800)
    assert policy.pick_durations([a, b])[2].code == 'A'
    assert policy.pick_durations([b, a])[2].code == 'A'


@pytest.mark.parametrize('insp,disp', [(3599, 604_800), (2_592_001, 604_800), (3600, 604_799), (3600, 7_776_001)])
def test_pick_durations_out_of_range(insp, disp):
    with pytest.raises(DomainError) as e:
        policy.pick_durations([policy.Policy('X', insp, disp)])
    assert e.value.code == 'POLICY_OUT_OF_RANGE'


def test_pick_durations_boundaries_ok_and_empty_rejected():
    assert policy.pick_durations([policy.Policy('X', 3600, 604_800)])[:2] == (3600, 604_800)
    assert policy.pick_durations([policy.Policy('X', 2_592_000, 7_776_000)])[:2] == (2_592_000, 7_776_000)
    with pytest.raises(DomainError) as e:
        policy.pick_durations([])
    assert e.value.code == 'POLICY_NOT_CONFIGURED'


# ---------------------------------------------------------------- báo giá + docHash (vector chéo ngôn ngữ)
@pytest.mark.parametrize('v', VECTORS['docHash'], ids=lambda v: v['name'])
def test_canonical_json_and_dochash_match_shared_vectors(v):
    assert quote.canonical_json(v['summary']) == v['canonicalJson']
    assert quote.doc_hash(v['summary'], keccak) == v['docHash']


def test_canonical_json_rejects_float_and_bool():
    for bad in ({'a': 1.5}, {'a': True}, {'a': [1, {'b': 2.0}]}):
        with pytest.raises(ValueError):
            quote.canonical_json(bad)


def test_build_summary_is_order_independent():
    items = [{'product_id': 'b', 'quantity': 1, 'unit_price_vnd': 5}, {'product_id': 'a', 'quantity': 2, 'unit_price_vnd': 7}]
    s1 = quote.build_summary('X', items, 19, 100)
    s2 = quote.build_summary('X', list(reversed(items)), 19, 100)
    assert quote.doc_hash(s1, keccak) == quote.doc_hash(s2, keccak)


def test_quote_field_order_matches_types_json():
    types = json.loads((ROOT / 'shared' / 'eip712' / 'types.json').read_text(encoding='utf-8'))['types']['OrderQuote']
    assert tuple(f['name'] for f in types) == quote.QUOTE_FIELDS


def test_quote_message_stringifies_uint256_but_not_addresses():
    q = quote.OrderQuote(orderId=1001, buyer=ADDR['buyer'], merchant=ADDR['merchant1'], token=ADDR['buyer'], amount=2 ** 200,
                         inspectionDuration=3600, disputeTimeout=604800, feeBps=300, docHash='0x' + '11' * 32, deadline=10)
    m = q.message()
    assert m['orderId'] == '1001' and m['amount'] == str(2 ** 200) and m['buyer'] == ADDR['buyer']


def test_validate_quote_rejects_zero_amount_and_fee_over_cap():
    base = dict(orderId=1, buyer='a', merchant='b', token='c', amount=1, inspectionDuration=3600,
                disputeTimeout=604800, feeBps=0, docHash='0x', deadline=1)
    quote.validate_quote(quote.OrderQuote(**base))
    with pytest.raises(DomainError):
        quote.validate_quote(quote.OrderQuote(**{**base, 'amount': 0}))
    with pytest.raises(DomainError):
        quote.validate_quote(quote.OrderQuote(**{**base, 'feeBps': 1001}))


# ---------------------------------------------------------------- liên kết ví (UC-00)
def test_normalize_address():
    a = '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc'
    assert wallet.normalize_address(a) == a.lower()
    for bad in ('', '0x123', 'x' * 42, '0x' + 'g' * 40, None, 123, '0x' + 'a' * 41):
        with pytest.raises(DomainError) as e:
            wallet.normalize_address(bad)
        assert e.value.code == 'INVALID_ADDRESS'


def test_normalize_signature_v_values():
    base = '0x' + 'ab' * 64
    assert wallet.normalize_signature(base + '00').endswith('1b')
    assert wallet.normalize_signature(base + '01').endswith('1c')
    assert wallet.normalize_signature(base + '1b').endswith('1b')
    for bad in (base + '02', base + '1d', '0x12', None, base + '1'):
        with pytest.raises(DomainError) as e:
            wallet.normalize_signature(bad)
        assert e.value.code == 'BAD_SIGNATURE'


def test_link_message_is_deterministic_and_binds_every_field():
    args = ('localhost:5173', ADDR['buyer'], 'user-1', 'a' * 32, 31337, 1_800_000_000, 1_800_000_300)
    m = wallet.build_link_message(*args)
    assert m == wallet.build_link_message(*args)
    assert ADDR['buyer'].lower() in m and 'user-1' in m and 'a' * 32 in m and 'Chain ID: 31337' in m
    assert 'localhost:5173' in m and '2027-01-15T08:00:00Z' in m and '2027-01-15T08:05:00Z' in m
    # đổi bất kỳ trường nào đều đổi thông điệp (chống chữ ký bị dùng lại sai ngữ cảnh)
    for i, alt in enumerate(['other:80', ADDR['merchant1'], 'user-2', 'b' * 32, 1, 1_800_000_001, 1_800_000_301]):
        changed = list(args)
        changed[i] = alt
        assert wallet.build_link_message(*changed) != m


def test_nonce_format():
    assert wallet.is_valid_nonce('a' * 32)
    for bad in ('A' * 32, 'a' * 31, 'g' * 32, None, 5):
        assert not wallet.is_valid_nonce(bad)


# ---------------------------------------------------------------- máy trạng thái + lỗi
@pytest.mark.parametrize('old,new', [
    ('PENDING_PAYMENT', 'LOCKED'), ('PENDING_PAYMENT', 'EXPIRED'), ('EXPIRED', 'PENDING_PAYMENT'), ('LOCKED', 'DELIVERED'),
    ('LOCKED', 'REFUNDED'), ('DELIVERED', 'COMPLETED'), ('DELIVERED', 'DISPUTED'), ('DISPUTED', 'COMPLETED'),
    ('DISPUTED', 'REFUNDED')])
def test_valid_transitions(old, new):
    assert order_state.is_valid_transition(old, new)


@pytest.mark.parametrize('old,new', [
    ('COMPLETED', 'LOCKED'), ('REFUNDED', 'LOCKED'), ('LOCKED', 'COMPLETED'), ('PENDING_PAYMENT', 'DELIVERED'),
    ('DELIVERED', 'REFUNDED'), ('EXPIRED', 'LOCKED'), ('LOCKED', 'PENDING_PAYMENT')])
def test_invalid_transitions(old, new):
    assert not order_state.is_valid_transition(old, new)


def test_legacy_status_mapping_covers_every_state():
    assert {s: order_state.to_legacy_status(s) for s in order_state.STATES} == {
        'PENDING_PAYMENT': 'pending', 'LOCKED': 'paid', 'DELIVERED': 'shipped', 'DISPUTED': 'shipped',
        'COMPLETED': 'received', 'EXPIRED': 'cancelled', 'REFUNDED': 'cancelled'}
    with pytest.raises(KeyError):
        order_state.to_legacy_status('BOGUS')


def test_http_status_mapping():
    assert http_status('WALLET_NOT_LINKED') == 409 and http_status('QUOTE_EXPIRED') == 410
    assert http_status('RATE_LIMITED') == 429 and http_status('CHAIN_UNAVAILABLE') == 503
    assert http_status('UNKNOWN_CODE') == 400


# ---------------------------------------------------------------- vector liên kết ví dùng chung (Python <-> JS)
@pytest.mark.parametrize('v', VECTORS['walletLink'], ids=lambda v: v['name'])
def test_wallet_link_message_matches_shared_vector_byte_for_byte(v):
    from slopee_web3.adapters.env_signer import recover_personal_sign
    built = wallet.build_link_message(v['domain'], v['address'], v['userId'], v['nonce'], v['chainId'], v['issuedAt'], v['expiresAt'])
    assert built == v['message']
    assert recover_personal_sign(v['message'], v['signature']) == v['signer'].lower()
    assert wallet.normalize_signature(v['signature']) == v['signature']       # v đã là 27/28
