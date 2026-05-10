import pytest

def test_execute_checkout_success(client, mocker):

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
        {"methodType": "bank", "balance": "100.00"}, # check buyer's payment balance
        {"sellerId": "fake-seller-id"}, # shop_payouts seller ID fetch
        {"id": "seller-bank-id"} # shop_payouts seller bank account fetch
    ]
    
    mock_cursor.fetchall.side_effect = [
        [ # cart items fetch from cart_item_ids
            {"cartItemId": 10, "quantity": 2, "cartId": 1, "selectedVariants": "{}", "productId": 100, "unitPrice": 10.00, "inStock": 5, "shopId": 1, "name": "Item 1", "shopName": "Shop A"},
            {"cartItemId": 11, "quantity": 1, "cartId": 1, "selectedVariants": "{}", "productId": 101, "unitPrice": 20.00, "inStock": 2, "shopId": 1, "name": "Item 2", "shopName": "Shop A"}
        ]
    ]

    response = client.post('/api/checkout/checkout', json={
        "userId": "fake-user-id",
        "paymentMethodId": 1,
        "passPhrase": "123",
        "cartItemIds": [10, 11]
    })

    assert response.status_code == 200
    assert response.get_json()['message'] == "Successfully completed. Receipt generated!"

def test_execute_checkout_out_of_stock(client, mocker):
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
            {"cartItemId": 10, "quantity": 10, "cartId": 1, "selectedVariants": "{}", "productId": 100, "unitPrice": 10.00, "inStock": 2, "shopId": 1, "name": "Item 1", "shopName": "Shop A"}
        ]
    ]

    response = client.post('/api/checkout/checkout', json={
        "userId": "fake-user-id",
        "paymentMethodId": 1,
        "passPhrase": "123",
        "cartItemIds": [10]
    })

    assert response.status_code == 400
    assert "Insufficient stock" in response.get_json()['error']
