import pytest
import uuid
from werkzeug.security import generate_password_hash

@pytest.fixture
def mock_db_cursor(mocker):
    """Reusable fixture that patches the DB connection and returns a fake cursor."""
    mock_get_db = mocker.patch('backend.routes.auth.get_db_connection')
    mock_conn = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    return mock_cursor


def test_login_success(client, mocker, mock_db_cursor):
    """
    UNIT TEST: Test that the login endpoint succeeds with correct credentials,
    WITHOUT touching the actual MySQL database.
    """
    
    # 2. MOCK THE DATABASE RESPONSE
    # We define exactly what `cursor.fetchone()` should return for this specific test
    fake_password = 'mypassword123'
    fake_hash = generate_password_hash(fake_password) # Real hash so your real check_password_hash logic passes!
    
    mock_db_cursor.fetchone.return_value = {
        'userId': 1,
        'passwordHash': fake_hash, # Your login() function will compare against this
        'role': 'user',
        'name': 'Test User',
        'email': 'test@slopee.com'
    }


    # 3. EXECUTE THE REQUEST
    # We act like a frontend React client and send a JSON POST request
    response = client.post('/api/auth/login', json={
        "username": "testuser",
        "password": fake_password
    })


    # 4. ASSERTIONS
    # Verify the HTTP response is 200 OK
    assert response.status_code == 200
    
    # Verify the JSON payload has the correct data
    data = response.get_json()
    assert data['message'] == "Login successful"
    assert data['user']['name'] == "Test User"
    assert data['user']['role'] == "user"

    # P0-01: login phải trả token ký, giải mã ra đúng danh tính
    from auth_utils import verify_token
    payload = verify_token(data['token'])
    assert payload == {'uid': 1, 'role': 'user'}
    assert data['expiresIn'] > 0
    
    # ADVANCED ASSERTION: Verify the SQL query was actually executed with the correct username!
    mock_db_cursor.execute.assert_called_once()
    query_string = mock_db_cursor.execute.call_args[0][0]
    query_params = mock_db_cursor.execute.call_args[0][1]
    
    assert "SELECT" in query_string
    assert query_params == ("testuser",)


def test_login_invalid_password(client, mocker, mock_db_cursor):
    """Test that login fails with a 401 Unauthorized if password doesn't match hash."""
    
    # Database returns a valid user...
    mock_db_cursor.fetchone.return_value = {
        'userId': 1,
        'passwordHash': generate_password_hash('correctpassword'),
        'role': 'user',
        'name': 'Test User',
        'email': 'test@slopee.com'
    }

    # ...but we send the wrong password!
    response = client.post('/api/auth/login', json={
        "username": "testuser",
        "password": "WRONG_PASSWORD"
    })

    # Assuming your login() returns 401 for bad passwords
    assert response.status_code == 401
    assert response.get_json()['error'] == "Invalid username or password"

def test_signup_success(client, mocker, mock_db_cursor):
    fake_role = "user"
    fake_name = "User A"
    fake_email = "usra@gmail.com"
    fake_phone = "0123456789"
    fake_username = "userA"
    fake_password = "slopee"
    fake_pass_phrase = "123456"

    mock_db_cursor.fetchone.return_value = None

    response = client.post('/api/auth/signup', json = {
        "role": fake_role,
        "name": fake_name,
        "email": fake_email,
        "phone": fake_phone,
        "username": fake_username,
        "password": fake_password,
        "pass_phrase": fake_pass_phrase
    })

    assert response.status_code == 201
    
    data = response.get_json()
    assert data['message'] == "User registered successfully!"

    assert mock_db_cursor.execute.call_count == 4
    # test insert into users
    insert_users_query = mock_db_cursor.execute.call_args_list[2]
    insert_users_query_string = insert_users_query[0][0]
    insert_users_params = insert_users_query[0][1]
    assert "INSERT INTO users" in insert_users_query_string
    assert insert_users_params == (mocker.ANY, fake_role, fake_name, fake_email, fake_phone, '')

    # test insert into credentials
    insert_cred_query = mock_db_cursor.execute.call_args_list[3]
    insert_cred_query_string = insert_cred_query[0][0]
    insert_cred_params = insert_cred_query[0][1]

    assert "INSERT INTO credentials" in insert_cred_query_string
    # hashing randomizes salt every run, use ANY for the hashes 
    assert insert_cred_params == (mocker.ANY, fake_username, mocker.ANY, 'werkzeug-managed', mocker.ANY)

def test_signup_invalid_username(client):
    invalid_username = "ape" # < 3 char
    response = client.post('api/auth/signup', json = {
        "role": "user",
        "name": "any",
        "email": "any",
        "phone": "any",
        "username": invalid_username,
        "password": "any",
        "pass_phrase": "123456"
    })

    assert response.status_code == 400
    assert (response.get_json())["error"] == "Username must be longer than 3 characters"

def test_signup_invalid_pass_phrase(client):
    invalid_pass_phrase = "ape"
    response = client.post('api/auth/signup', json = {
        "role": "user",
        "name": "any",
        "email": "any",
        "phone": "any",
        "username": "fake",
        "password": "any",
        "pass_phrase": invalid_pass_phrase
    })

    assert response.status_code == 400
    assert (response.get_json())["error"] == "Passphrase must be exactly a 6-digit number"

