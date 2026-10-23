"""Tuần 5 [C]: GET /api/payments/orders trả thêm `web3` cho đơn Web3 (SRS 5.1) để MyOrders khóa nút cũ,
hiện đồng hồ kiểm tra và gọi đúng đơn on-chain. Đơn cũ giữ nguyên hình dạng + `web3: null`."""
import pymysql
import pytest


@pytest.fixture
def db(fake_db):
    return fake_db('backend.routes.payments')


def _line(order_id, status='paid', name='Áo'):
    return {'orderId': order_id, 'totalAmount': 399000, 'created_at': '2026-10-16 08:00:00', 'status': status,
            'quantity': 1, 'unitPrice': 399000, 'productName': name, 'shopName': 'Shop A', 'selectedVariants': None}


def _web3_row(order_id, **over):
    row = {'order_id': order_id, 'onchain_order_id': 100001, 'checkout_group_id': 'g1', 'buyer_wallet': '0x9965507d1a55bcc2695c58ba16fb37d819b0a4dc', 'status': 'DELIVERED',
           'chain_created_at': 1_799_000_000, 'delivered_at': 1_800_000_000, 'inspection_duration': 259200, 'disputed_at': None, 'dispute_timeout': 2592000,
           'fee_bps': 300, 'amount_raw': '15960000', 'token_symbol': 'mUSD', 'anomaly_flag': 0}
    row.update(over)
    return row


def _get(client, headers):
    return client.get('/api/checkout/orders', headers=headers)


def test_web3_order_gets_summary_and_legacy_order_gets_null(client, db, auth_headers):
    db.on("FROM orders o", [_line('legacy'), _line('w3', status='shipped')])
    db.on("FROM order_web3", [_web3_row('w3')])
    r = _get(client, auth_headers)
    assert r.status_code == 200
    by_id = {o['orderId']: o for o in r.get_json()['orders']}
    assert by_id['legacy']['web3'] is None
    w = by_id['w3']['web3']
    assert w == {'onchain_order_id': 100001, 'checkout_group_id': 'g1', 'buyer_wallet': '0x9965507d1a55bcc2695c58ba16fb37d819b0a4dc', 'status': 'DELIVERED', 'chain_created_at': 1_799_000_000, 'delivered_at': 1_800_000_000,
                 'inspection_duration': 259200, 'disputed_at': None, 'dispute_timeout': 2592000, 'fee_bps': 300,
                 'amount_raw': '15960000', 'token_symbol': 'mUSD', 'anomaly': False}
    assert by_id['w3']['status'] == 'shipped'      # orders.status cũ vẫn là bản chiếu (SRS 5.1), không bị thay


def test_summary_query_is_one_query_for_all_orders_and_parameterized(client, db, auth_headers):
    db.on("FROM orders o", [_line('a'), _line('b'), _line('b', name='Quần')])
    _get(client, auth_headers)
    q = db.executed("FROM order_web3")
    assert len(q) == 1                                     # không N+1
    sql, params = q[0]
    assert sorted(params) == ['a', 'b'] and "%s,%s" in sql and "WHERE order_id IN" in sql


def test_no_orders_skips_the_web3_query(client, db, auth_headers):
    db.on("FROM orders o", [])
    r = _get(client, auth_headers)
    assert r.get_json() == {'orders': []} and not db.executed("FROM order_web3")


def test_numbers_are_json_numbers_and_amount_stays_string(client, db, auth_headers):
    # pymysql trả BIGINT UNSIGNED/Decimal; amount_raw (uint256) PHẢI là chuỗi để không mất chính xác
    big = '115792089237316195423570985008687907853269984665640564039457584007913129639935'
    db.on("FROM orders o", [_line('w3')])
    db.on("FROM order_web3", [_web3_row('w3', onchain_order_id='123', amount_raw=big, anomaly_flag=1, disputed_at='1800000005')])
    w = _get(client, auth_headers).get_json()['orders'][0]['web3']
    assert w['onchain_order_id'] == 123 and isinstance(w['onchain_order_id'], int)
    assert w['amount_raw'] == big and w['anomaly'] is True and w['disputed_at'] == 1_800_000_005


def test_chain_created_at_is_a_number_or_null(client, db, auth_headers):
    # Tuần 7 [C]: mốc ký quỹ theo block để Buyer biết khi nào hủy được đơn quá 14 ngày (cancelIfUnfulfilled)
    db.on("FROM orders o", [_line('a'), _line('b')])
    db.on("FROM order_web3", [_web3_row('a', status='LOCKED', delivered_at=None, chain_created_at='1799000000'), _web3_row('b', chain_created_at=None)])
    by_id = {o['orderId']: o['web3'] for o in _get(client, auth_headers).get_json()['orders']}
    assert by_id['a']['chain_created_at'] == 1_799_000_000 and isinstance(by_id['a']['chain_created_at'], int)
    assert by_id['b']['chain_created_at'] is None


def test_missing_order_web3_table_means_all_legacy(client, db, auth_headers):
    def boom(sql, params):
        raise pymysql.err.ProgrammingError(1146, "Table 'slopee.order_web3' doesn't exist")
    db.on("FROM orders o", [_line('legacy')])
    db.on("FROM order_web3", boom)
    r = _get(client, auth_headers)
    assert r.status_code == 200 and r.get_json()['orders'][0]['web3'] is None


def test_other_sql_errors_are_not_swallowed(client, db, auth_headers):
    def boom(sql, params):
        raise pymysql.err.ProgrammingError(1064, 'syntax error')
    db.on("FROM orders o", [_line('legacy')])
    db.on("FROM order_web3", boom)
    r = _get(client, auth_headers)
    assert r.status_code == 500 and r.get_json()['code'] == 'internal_error'


def test_main_query_still_scoped_by_token_user(client, db, auth_headers):
    db.on("FROM orders o", [])
    _get(client, auth_headers)
    sql, params = db.executed("FROM orders o")[0]
    assert params == ('fake-user-id',) and "o.userId=%s" in sql
