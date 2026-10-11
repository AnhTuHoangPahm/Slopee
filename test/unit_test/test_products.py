import pytest
import uuid

def test_add_product_success(client, mocker, seller_headers):

    mock_get_db = mocker.patch('backend.routes.shops.get_db_connection')
    mock_conn = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Mock getting shop ID for the seller
    mock_cursor.fetchone.return_value = {"id": 1}

    response = client.post('/api/shop/products', headers=seller_headers, json={
        "categoryId": 2,
        "name": "Test Shirt",
        "description": "A very nice shirt"
    })

    assert response.status_code == 201
    assert "Product successfully added" in response.get_json()['message']
    
    assert mock_cursor.execute.call_count == 3  # shop lookup + category check + insert
    insert_query = mock_cursor.execute.call_args[0][0]
    assert "INSERT INTO products" in insert_query

def test_add_product_validation(client, mocker, seller_headers):
    # Missing name and description
    response = client.post('/api/shop/products', headers=seller_headers, json={
        "categoryId": 2
    })

    assert response.status_code == 400
    assert response.get_json()['error'] == "Product Name required"


def test_add_product_forbidden_for_buyer(client, auth_headers):
    response = client.post('/api/shop/products', headers=auth_headers, json={"name": "x"})
    assert response.status_code == 403
    assert response.get_json()['code'] == 'forbidden'


def test_add_product_requires_auth(client):
    response = client.post('/api/shop/products', json={"name": "x"})
    assert response.status_code == 401


@pytest.mark.parametrize("price", [-1, 10.5, "abc", True, 10 ** 15])
def test_add_product_rejects_invalid_vnd_price(client, seller_headers, price):
    r = client.post('/api/shop/products', headers=seller_headers, json={"name": "x", "unitPrice": price})
    assert r.status_code == 400
    assert "unitPrice" in r.get_json()['error']


def test_update_product_rejects_fractional_price(client, mocker, seller_headers):
    mocker.patch('backend.routes.shops.get_db_connection')
    r = client.put('/api/shop/products/p1', headers=seller_headers, json={"unitPrice": "99.5", "inStock": 1})
    assert r.status_code == 400
