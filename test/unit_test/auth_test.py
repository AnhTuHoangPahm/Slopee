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


def _user_row(password, user_id=1):
    return {'userId': user_id, 'passwordHash': generate_password_hash(password),
            'role': 'user', 'name': 'Test User', 'email': 'test@slopee.com'}


def test_login_success(client, fake_db):
    """Đăng nhập đúng trả token ký, KHÔNG chạm MySQL thật."""
    cur = fake_db('backend.routes.auth')
    cur.on("FROM credentials c", [_user_row('mypassword123')])

    response = client.post('/api/auth/login', json={"username": "testuser", "password": "mypassword123"})

    assert response.status_code == 200
    data = response.get_json()
    assert data['message'] == "Login successful"
    assert data['user']['name'] == "Test User"
    assert data['user']['role'] == "user"

    # P0-01: login phải trả token ký, giải mã ra đúng danh tính
    from auth_utils import verify_token
    assert verify_token(data['token']) == {'uid': 1, 'role': 'user'}
    assert data['expiresIn'] > 0

    # Câu SQL đầu tiên là truy vấn đăng nhập với đúng username
    query, params = cur.calls[0]
    assert "SELECT" in query and params == ("testuser",)


def test_login_invalid_password(client, fake_db):
    """Sai mật khẩu -> 401 (P0-05: và được đếm để khóa tạm)."""
    cur = fake_db('backend.routes.auth')
    cur.on("FROM credentials c", [_user_row('correctpassword')])

    response = client.post('/api/auth/login', json={"username": "testuser", "password": "WRONG_PASSWORD"})

    assert response.status_code == 401
    assert response.get_json()['error'] == "Invalid username or password"
    assert cur.executed("UPDATE authAttempts")  # lần sai đã được ghi nhận

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

