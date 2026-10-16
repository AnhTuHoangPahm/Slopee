import pytest

from checkout_helpers import setup_checkout, ITEMS, BODY


@pytest.fixture
def pay(fake_db, mocker):
    mocker.patch('backend.routes.payments.check_password_hash', return_value=True)
    return fake_db('backend.routes.payments')


def test_execute_checkout_success(client, pay, auth_headers):
    setup_checkout(pay, ITEMS)
    response = client.post('/api/checkout/checkout', headers=auth_headers, json=BODY)
    assert response.status_code == 200
    assert response.get_json()['message'] == "Successfully completed. Receipt generated!"
    pay.conn.commit.assert_called()


def test_execute_checkout_out_of_stock(client, pay, auth_headers):
    setup_checkout(pay, [{"cartItemId": 10, "quantity": 10, "productId": 100, "unitPrice": 100000, "inStock": 2}])
    response = client.post('/api/checkout/checkout', headers=auth_headers,
                           json={**BODY, "cartItemIds": [10]})
    assert response.status_code == 400
    assert "Insufficient stock" in response.get_json()['error']
    assert not pay.executed("INSERT INTO orders")
    pay.conn.rollback.assert_called()


def test_checkout_requires_auth(client):
    response = client.post('/api/checkout/checkout', json={"cartItemIds": [1], "passPhrase": "123456"})
    assert response.status_code == 401


def test_checkout_total_is_integer_vnd(client, pay, auth_headers):
    """Tổng tiền tính bằng số nguyên VND, không float: 2*100.000 + 1*250.000 = 450.000."""
    setup_checkout(pay, ITEMS)
    r = client.post('/api/checkout/checkout', headers=auth_headers, json=BODY)
    assert r.status_code == 200
    deduct = pay.executed("balance - %s")[0]
    assert deduct[1][0] == 450000 and isinstance(deduct[1][0], int)
    order_insert = pay.executed("INSERT INTO orders ")[0]
    assert order_insert[1][-1] == 450000
    credit = pay.executed("balance + %s")[0]
    assert credit[1][0] == 450000 and credit[1][1] == 'seller-bank'


def test_checkout_insufficient_funds_message_in_vnd(client, pay, auth_headers):
    setup_checkout(pay, [{"cartItemId": 10, "quantity": 1, "productId": 100, "unitPrice": 1234567, "inStock": 5}],
                   balance=50000)
    r = client.post('/api/checkout/checkout', headers=auth_headers, json={**BODY, "cartItemIds": [10]})
    assert r.status_code == 400
    err = r.get_json()['error']
    assert "$" not in err and "1.234.567 ₫" in err and "50.000 ₫" in err


def test_checkout_cod_skips_balance_check(client, pay, auth_headers):
    setup_checkout(pay, [{"cartItemId": 10, "quantity": 1, "productId": 100, "unitPrice": 999999999999, "inStock": 5}])
    r = client.post('/api/checkout/checkout', headers=auth_headers,
                    json={**BODY, "paymentMethodId": "CASH_ON_DELIVERY", "cartItemIds": [10]})
    assert r.status_code == 200
    assert not pay.executed("balance - %s")
    assert pay.executed("INSERT INTO orders ")[0][1][2] is None  # COD: paymentMethodId = NULL
