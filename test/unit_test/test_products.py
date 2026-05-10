import pytest
import uuid

def test_add_product_success(client, mocker):

    mock_get_db = mocker.patch('backend.routes.shops.get_db_connection')
    mock_conn = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Mock getting shop ID for the seller
    mock_cursor.fetchone.return_value = {"id": 1}

    response = client.post('/api/shop/products', json={
        "shopId": "fake-shop-id",
        "categoryId": 2,
        "name": "Test Shirt",
        "description": "A very nice shirt"
    })

    assert response.status_code == 201
    assert "Product successfully added" in response.get_json()['message']
    
    assert mock_cursor.execute.call_count == 2
    insert_query = mock_cursor.execute.call_args[0][0]
    assert "INSERT INTO products" in insert_query

def test_add_product_validation(client, mocker):
    # Missing name and description
    response = client.post('/api/shop/products', json={
        "categoryId": 2
    })

    assert response.status_code == 400
    assert response.get_json()['error'] == "Shop ID and Product Name required"
