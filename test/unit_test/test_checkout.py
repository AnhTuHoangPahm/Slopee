import pytest

def test_execute_checkout_success(client, mocker, auth_headers):

    # Mock check_password_hash so passphrase validates correctly
    mocker.patch('backend.routes.payments.check_password_hash', return_value=True)

    mock_get_db = mocker.patch('backend.routes.payments.get_db_connection')
    mock_conn = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Setup the mock database to return a cart, items, stock, and payment methods
    mock_cursor.fetchone.side_effect = [
        {"passPhraseHash": "dummy-hash"}, # Verify Passphrase 6-digit PIN Match
        {"methodType": "bank", "balance": "1000000"}, # check buyer's payment balance
        {"sellerId": "fake-seller-id"}, # shop_payouts seller ID fetch
        {"id": "seller-bank-id"} # shop_payouts seller bank account fetch
    ]
    
    mock_cursor.fetchall.side_effect = [
        [ # cart items fetch from cart_item_ids
            {"cartItemId": 10, "quantity": 2, "cartId": 1, "selectedVariants": "{}", "productId": 100, "unitPrice": 100000, "inStock": 5, "shopId": 1, "name": "Item 1", "shopName": "Shop A"},
            {"cartItemId": 11, "quantity": 1, "cartId": 1, "selectedVariants": "{}", "productId": 101, "unitPrice": 250000, "inStock": 2, "shopId": 1, "name": "Item 2", "shopName": "Shop A"}
        ]
    ]

    response = client.post('/api/checkout/checkout', headers=auth_headers, json={
        "paymentMethodId": 1,
        "passPhrase": "123",
        "cartItemIds": [10, 11]
    })

    assert response.status_code == 200
    assert response.get_json()['message'] == "Successfully completed. Receipt generated!"

def test_execute_checkout_out_of_stock(client, mocker, auth_headers):
    mocker.patch('backend.routes.payments.check_password_hash', return_value=True)

    mock_get_db = mocker.patch('backend.routes.payments.get_db_connection')
    mock_conn = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Database setup where stock is insufficient
    mock_cursor.fetchone.side_effect = [
        {"passPhraseHash": "dummy-hash"}
    ]
    
    mock_cursor.fetchall.side_effect = [
        [ # cart items fetch
            {"cartItemId": 10, "quantity": 10, "cartId": 1, "selectedVariants": "{}", "productId": 100, "unitPrice": 100000, "inStock": 2, "shopId": 1, "name": "Item 1", "shopName": "Shop A"}
        ]
    ]

    response = client.post('/api/checkout/checkout', headers=auth_headers, json={
        "paymentMethodId": 1,
        "passPhrase": "123",
        "cartItemIds": [10]
    })

    assert response.status_code == 400
    assert "Insufficient stock" in response.get_json()['error']


def test_checkout_requires_auth(client):
    response = client.post('/api/checkout/checkout', json={"cartItemIds": [1], "passPhrase": "123456"})
    assert response.status_code == 401


def _mock_cursor(mocker):
    mock_get_db = mocker.patch('backend.routes.payments.get_db_connection')
    cur = mocker.MagicMock()
    mock_get_db.return_value.cursor.return_value.__enter__.return_value = cur
    return cur


def test_checkout_total_is_integer_vnd(client, mocker, auth_headers):
    """Tổng tiền tính bằng số nguyên VND, không float: 2*100.000 + 1*250.000 = 450.000."""
    mocker.patch('backend.routes.payments.check_password_hash', return_value=True)
    cur = _mock_cursor(mocker)
    cur.fetchone.side_effect = [
        {"passPhraseHash": "h"}, {"methodType": "bank", "balance": "1000000"},
        {"sellerId": "s"}, {"id": "seller-bank"},
    ]
    cur.fetchall.side_effect = [[
        {"cartItemId": 10, "quantity": 2, "cartId": 1, "selectedVariants": "{}", "productId": 100, "unitPrice": 100000, "inStock": 5, "shopId": 1, "name": "A", "shopName": "S"},
        {"cartItemId": 11, "quantity": 1, "cartId": 1, "selectedVariants": "{}", "productId": 101, "unitPrice": 250000, "inStock": 2, "shopId": 1, "name": "B", "shopName": "S"},
    ]]
    r = client.post('/api/checkout/checkout', headers=auth_headers,
                    json={"paymentMethodId": 1, "passPhrase": "123456", "cartItemIds": [10, 11]})
    assert r.status_code == 200
    deduct = [c for c in cur.execute.call_args_list if "balance - %s" in c[0][0]][0]
    assert deduct[0][1][0] == 450000 and isinstance(deduct[0][1][0], int)
    order_insert = [c for c in cur.execute.call_args_list if "INSERT INTO orders " in c[0][0]][0]
    assert order_insert[0][1][-1] == 450000


def test_checkout_insufficient_funds_message_in_vnd(client, mocker, auth_headers):
    mocker.patch('backend.routes.payments.check_password_hash', return_value=True)
    cur = _mock_cursor(mocker)
    cur.fetchone.side_effect = [{"passPhraseHash": "h"}, {"methodType": "bank", "balance": "50000"}]
    cur.fetchall.side_effect = [[
        {"cartItemId": 10, "quantity": 1, "cartId": 1, "selectedVariants": "{}", "productId": 100, "unitPrice": 1234567, "inStock": 5, "shopId": 1, "name": "A", "shopName": "S"},
    ]]
    r = client.post('/api/checkout/checkout', headers=auth_headers,
                    json={"paymentMethodId": 1, "passPhrase": "123456", "cartItemIds": [10]})
    assert r.status_code == 400
    err = r.get_json()['error']
    assert "$" not in err and "1.234.567 ₫" in err and "50.000 ₫" in err


def test_checkout_cod_skips_balance_check(client, mocker, auth_headers):
    mocker.patch('backend.routes.payments.check_password_hash', return_value=True)
    cur = _mock_cursor(mocker)
    cur.fetchone.side_effect = [{"passPhraseHash": "h"}, {"sellerId": "s"}, {"id": "seller-bank"}]
    cur.fetchall.side_effect = [[
        {"cartItemId": 10, "quantity": 1, "cartId": 1, "selectedVariants": "{}", "productId": 100, "unitPrice": 999999999999, "inStock": 5, "shopId": 1, "name": "A", "shopName": "S"},
    ]]
    r = client.post('/api/checkout/checkout', headers=auth_headers,
                    json={"paymentMethodId": "CASH_ON_DELIVERY", "passPhrase": "123456", "cartItemIds": [10]})
    assert r.status_code == 200
    assert not any("balance - %s" in c[0][0] for c in cur.execute.call_args_list)
