"""Quyết định nhóm sau Phase 0 (FakeCursor, không cần MySQL; bản MySQL thật nằm ở test_p0_mysql.py):
1. hủy đơn `paid` hoàn tiền + hoàn kho + thu lại từ người bán (không tạo tiền)
2. COD / 'cash' không cộng tiền cho người bán
3. giữ FK RESTRICT; xóa user đã có đơn trả 409 `user_has_orders` (không 500)
"""
import pytest

from checkout_helpers import BODY, ITEMS, USER, setup_checkout

CHECKOUT = '/api/checkout/checkout'


@pytest.fixture
def pay_db(fake_db, mocker):
    mocker.patch('backend.routes.payments.check_password_hash', return_value=True)
    return fake_db('backend.routes.payments')


def _seller_balance_updates(cur):
    return [c for c in cur.executed("UPDATE paymentMethods SET balance = balance + %s") if c[1][1] == 'seller-bank']


# ------------------------------------------------------------------ (2) COD / cash
def test_bank_checkout_credits_seller_and_records_it_on_lines(client, pay_db, auth_headers):
    setup_checkout(pay_db, ITEMS)
    assert client.post(CHECKOUT, headers=auth_headers, json=BODY).status_code == 200
    assert _seller_balance_updates(pay_db)[0][1] == (450000, 'seller-bank')
    lines = pay_db.executed("INSERT INTO orderLines")
    assert [(p[8], p[9]) for _, p in lines] == [('seller-bank', 200000), ('seller-bank', 250000)]


def test_cod_checkout_does_not_credit_seller(client, pay_db, auth_headers):
    setup_checkout(pay_db, ITEMS)
    r = client.post(CHECKOUT, headers=auth_headers, json={**BODY, "paymentMethodId": "CASH_ON_DELIVERY"})
    assert r.status_code == 200
    assert not pay_db.executed("UPDATE paymentMethods")           # không trừ người mua, không cộng người bán
    assert all(p[8] is None and p[9] == 0 for _, p in pay_db.executed("INSERT INTO orderLines"))


def test_cash_method_checkout_does_not_credit_seller(client, pay_db, auth_headers):
    setup_checkout(pay_db, ITEMS, pm_type='cash')
    assert client.post(CHECKOUT, headers=auth_headers, json=BODY).status_code == 200
    assert not pay_db.executed("UPDATE paymentMethods")


# ------------------------------------------------------------------ (1) hủy đơn paid
def _cancel(client, headers, pay_db, *, lines, pm_type='bank', total=450000, buyer_pm='buyer-pm'):
    pay_db.on("FROM orders WHERE id", [{"id": "o1", "status": "paid"}])
    pay_db.on("FROM order_web3", [])
    pay_db.on("FROM orderLines", lines)
    pay_db.on("FROM orders o", [{"paymentMethodId": buyer_pm, "totalAmount": total, "methodType": pm_type}])
    return client.put('/api/checkout/orders/o1', headers=headers, json={"status": "cancelled"})


LINES = [
    {"id": "l1", "orderId": "o1", "productId": "p1", "quantity": 2, "sellerPaymentMethodId": "seller-bank", "sellerCredit": 200000},
    {"id": "l2", "orderId": "o1", "productId": "p2", "quantity": 1, "sellerPaymentMethodId": "seller-bank", "sellerCredit": 250000},
]


def test_cancel_paid_bank_order_restocks_refunds_buyer_and_claws_back_seller(client, pay_db, auth_headers):
    r = _cancel(client, auth_headers, pay_db, lines=LINES)
    assert r.status_code == 200 and r.get_json()['refunded'] == 450000
    restock = {p[1]: p[0] for _, p in pay_db.executed("UPDATE products SET inStock = inStock + %s")}
    assert restock == {'p1': 2, 'p2': 1}
    claw = pay_db.executed("balance = balance - %s")
    assert [c[1] for c in claw] == [(450000, 'seller-bank', 450000)]                    # thu lại từ người bán, có điều kiện đủ số dư
    refund = pay_db.executed("balance = balance + %s")
    assert [c[1] for c in refund] == [(450000, 'buyer-pm', USER)]                       # hoàn đúng cho phương thức đã trừ
    pay_db.conn.commit.assert_called()


def test_cancel_refund_total_equals_what_was_clawed_back(client, pay_db, auth_headers):
    """Bảo toàn tiền: tổng hoàn cho người mua = tổng thu lại từ người bán."""
    _cancel(client, auth_headers, pay_db, lines=LINES)
    clawed = sum(c[1][0] for c in pay_db.executed("balance = balance - %s"))
    refunded = sum(c[1][0] for c in pay_db.executed("balance = balance + %s"))
    assert clawed == refunded == 450000


def test_cancel_fails_cleanly_if_seller_cannot_cover_refund(client, pay_db, auth_headers):
    pay_db.on("balance = balance - %s", rowcount=0)                                      # người bán không đủ số dư
    r = _cancel(client, auth_headers, pay_db, lines=LINES)
    assert r.status_code == 409 and r.get_json()['code'] == 'refund_unavailable'
    pay_db.conn.rollback.assert_called()
    pay_db.conn.commit.assert_not_called()
    assert not pay_db.executed("balance = balance + %s")                                 # chưa hoàn tiền cho ai


def test_cancel_paid_cod_order_only_restocks(client, pay_db, auth_headers):
    cod_lines = [{**ln, "sellerPaymentMethodId": None, "sellerCredit": 0} for ln in LINES]
    r = _cancel(client, auth_headers, pay_db, lines=cod_lines, pm_type=None, buyer_pm=None)
    assert r.status_code == 200 and r.get_json()['refunded'] == 0
    assert len(pay_db.executed("UPDATE products SET inStock = inStock + %s")) == 2
    assert not pay_db.executed("UPDATE paymentMethods")


def test_cancel_cash_method_order_has_no_refund(client, pay_db, auth_headers):
    cash_lines = [{**ln, "sellerPaymentMethodId": None, "sellerCredit": 0} for ln in LINES]
    r = _cancel(client, auth_headers, pay_db, lines=cash_lines, pm_type='cash')
    assert r.get_json()['refunded'] == 0 and not pay_db.executed("UPDATE paymentMethods")


def test_cancel_skips_deleted_product_and_deleted_seller_account(client, pay_db, auth_headers):
    lines = [{"id": "l1", "orderId": "o1", "productId": None, "quantity": 1, "sellerPaymentMethodId": None, "sellerCredit": 100000}]
    r = _cancel(client, auth_headers, pay_db, lines=lines, total=100000)
    assert r.status_code == 200 and r.get_json()['refunded'] == 100000
    assert not pay_db.executed("UPDATE products")                                        # sản phẩm đã xóa: không còn kho
    assert not pay_db.executed("balance = balance - %s")                                 # tài khoản người bán đã xóa: không còn gì để thu


def test_cancel_pending_order_has_no_money_side_effects(client, pay_db, auth_headers):
    pay_db.on("FROM orders WHERE id", [{"id": "o1", "status": "pending"}])
    pay_db.on("FROM order_web3", [])
    assert client.put('/api/checkout/orders/o1', headers=auth_headers, json={"status": "cancelled"}).status_code == 200
    assert not pay_db.executed("UPDATE products") and not pay_db.executed("UPDATE paymentMethods")


def test_receive_does_not_touch_money_or_stock(client, pay_db, auth_headers):
    pay_db.on("FROM orders WHERE id", [{"id": "o1", "status": "paid"}])
    pay_db.on("FROM order_web3", [])
    assert client.put('/api/checkout/orders/o1', headers=auth_headers, json={"status": "received"}).status_code == 200
    assert not pay_db.executed("UPDATE products") and not pay_db.executed("UPDATE paymentMethods")


def test_cancel_locks_products_before_payment_methods(client, pay_db, auth_headers):
    """Cùng thứ tự khóa với checkout (products -> paymentMethods) để hai luồng không deadlock chéo."""
    _cancel(client, auth_headers, pay_db, lines=LINES)
    order = [("products" if "FROM products" in sql else "pm") for sql, _ in pay_db.calls if "FOR UPDATE" in sql and "FROM orders" not in sql]
    assert order == ["products", "pm"]


# ------------------------------------------------------------------ (3) xóa user đã có đơn
def test_admin_delete_user_with_orders_returns_409_not_500(client, mocker, make_auth_headers):
    cur = mocker.patch('backend.routes.admin.get_db_connection').return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [{'role': 'user'}, {'x': 1}]                               # có user; có đơn
    r = client.delete('/api/admin/users/u-9', headers=make_auth_headers('admin-1', 'admin'))
    assert r.status_code == 409 and r.get_json()['code'] == 'user_has_orders'
    assert not [c for c in cur.execute.call_args_list if 'DELETE FROM users' in c.args[0]]


def test_admin_delete_user_maps_fk_restrict_error_to_409(client, mocker, make_auth_headers):
    import pymysql
    cur = mocker.patch('backend.routes.admin.get_db_connection').return_value.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [{'role': 'user'}, None]

    def execute(sql, params=None):
        if 'DELETE FROM users' in sql:
            raise pymysql.err.IntegrityError(1451, "Cannot delete or update a parent row")
    cur.execute.side_effect = execute
    r = client.delete('/api/admin/users/u-9', headers=make_auth_headers('admin-1', 'admin'))
    assert r.status_code == 409 and r.get_json()['code'] == 'user_has_orders'
