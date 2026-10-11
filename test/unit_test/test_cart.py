import pytest
from flask import Flask

def test_add_to_cart_success(client, mocker, auth_headers):
    # Mock Database
    mock_get_db = mocker.patch('backend.routes.carts.get_db_connection')
    mock_conn = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Mock the get_or_create_cart helper
    mocker.patch('backend.routes.carts.get_or_create_cart', return_value="fake-cart-id")
    
    # Mock checking if item exists (returns None, meaning it's a new item)
    mock_cursor.fetchone.side_effect = [
        {"inStock": 100},
        None,
    ]

    response = client.post('/api/cart/items', headers=auth_headers, json={
        "productId": "fake-product-id",
        "quantity": 2
    })

    assert response.status_code == 200
    assert response.get_json()['message'] == "Successfully added to cart!"
    
    # Verify the SQL was executed
    assert mock_cursor.execute.call_count == 3
    insert_query = mock_cursor.execute.call_args[0][0]
    assert "INSERT INTO cartItems" in insert_query

def test_add_to_cart_invalid_qty(client, auth_headers):
    response = client.post('/api/cart/items', headers=auth_headers, json={
        "productId": "fake-product-id",
        "quantity": -5
    })

    assert response.status_code == 400


def test_add_to_cart_requires_auth(client):
    response = client.post('/api/cart/items', json={"productId": "p", "quantity": 1})
    assert response.status_code == 401
    assert response.get_json()['code'] == 'auth_required'


def test_add_to_cart_ignores_user_id_in_body(client, mocker, auth_headers):
    """userId trong body phải bị bỏ qua: giỏ hàng luôn thuộc về chủ token."""
    mock_get_db = mocker.patch('backend.routes.carts.get_db_connection')
    mock_cursor = mocker.MagicMock()
    mock_get_db.return_value.cursor.return_value.__enter__.return_value = mock_cursor
    get_cart = mocker.patch('backend.routes.carts.get_or_create_cart', return_value="fake-cart-id")
    mock_cursor.fetchone.side_effect = [{"inStock": 100}, None]

    response = client.post('/api/cart/items', headers=auth_headers, json={
        "userId": "victim-user-id", "productId": "p", "quantity": 1
    })

    assert response.status_code == 200
    assert get_cart.call_args[0][1] == "fake-user-id"
