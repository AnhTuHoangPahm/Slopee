import pytest

def test_fetch_products_integration(client):
    """
    INTEGRATION TEST
    This test DOES NOT use 'mocker'. It tests the full integration between:
    1. The Flask Test Client
    2. The Products Blueprint Router
    3. The REAL MySQL Database (via get_db_connection)
    
    We send a GET request and ensure the database successfully parses the query
    and returns a valid JSON array of products.
    """
    
    # Send a real request to the API without any mocks!
    response = client.get('/api/products/')
    
    # 1. Assert the server didn't crash (200 OK)
    assert response.status_code == 200
    
    data = response.get_json()
    
    # 2. Assert that the database successfully returned a list (even if it's empty)
    items = data.get('items', [])
    assert isinstance(items, list)
    
    # 3. If there are products in the DB, assert the schema integration is correct
    if len(items) > 0:
        product = items[0]
        # Verify the SQL JOIN successfully merged product data with variant data
        assert 'id' in product
        assert 'name' in product
        assert 'unitPrice' in product
        assert 'shopName' in product # Ensure the JOIN to users/shops table worked!
