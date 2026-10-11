import pytest

SIGNUP = {
    "name": "N", "email": "a@b.c", "phone": "0123456789",
    "username": "someone", "password": "pw123456", "pass_phrase": "123456",
}


@pytest.fixture
def db(mocker):
    mock_get_db = mocker.patch('backend.routes.auth.get_db_connection')
    cursor = mocker.MagicMock()
    mock_get_db.return_value.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = None
    return cursor


def test_signup_rejects_admin_role(client, db):
    r = client.post('/api/auth/signup', json={**SIGNUP, "role": "admin"})
    assert r.status_code == 403
    db.execute.assert_not_called()


def test_signup_rejects_unknown_role(client, db):
    assert client.post('/api/auth/signup', json={**SIGNUP, "role": "root"}).status_code == 403


@pytest.mark.parametrize("role", ["user", "seller"])
def test_signup_allows_user_and_seller(client, db, role):
    assert client.post('/api/auth/signup', json={**SIGNUP, "role": role}).status_code == 201


def test_signup_defaults_to_user(client, db):
    assert client.post('/api/auth/signup', json=SIGNUP).status_code == 201


ADMIN_ROUTES = [
    ('get', '/api/admin/stats'), ('get', '/api/admin/users'),
    ('delete', '/api/admin/users/x'), ('get', '/api/admin/categories'),
    ('post', '/api/admin/categories'), ('put', '/api/admin/categories/1'),
    ('delete', '/api/admin/categories/1'),
]


@pytest.mark.parametrize("method,url", ADMIN_ROUTES)
def test_admin_requires_token(client, method, url):
    assert getattr(client, method)(url).status_code == 401


@pytest.mark.parametrize("role", ["user", "seller"])
@pytest.mark.parametrize("method,url", ADMIN_ROUTES)
def test_admin_forbidden_for_non_admin(client, make_auth_headers, role, method, url):
    r = getattr(client, method)(url, headers=make_auth_headers('u', role))
    assert r.status_code == 403


def test_admin_can_list_users(client, mocker, make_auth_headers):
    conn = mocker.patch('backend.routes.admin.get_db_connection').return_value
    conn.cursor.return_value.__enter__.return_value.fetchall.return_value = []
    r = client.get('/api/admin/users', headers=make_auth_headers('a', 'admin'))
    assert r.status_code == 200


def test_admin_cannot_delete_admin_or_self(client, mocker, make_auth_headers):
    conn = mocker.patch('backend.routes.admin.get_db_connection').return_value
    cur = conn.cursor.return_value.__enter__.return_value
    h = make_auth_headers('admin-1', 'admin')
    assert client.delete('/api/admin/users/admin-1', headers=h).status_code == 403
    cur.fetchone.return_value = {'role': 'admin'}
    assert client.delete('/api/admin/users/admin-2', headers=h).status_code == 403
    cur.fetchone.return_value = {'role': 'user'}
    assert client.delete('/api/admin/users/u-9', headers=h).status_code == 200


def test_new_payment_method_has_zero_balance(client, mocker, auth_headers):
    cur = mocker.patch('backend.routes.payments.get_db_connection').return_value \
        .cursor.return_value.__enter__.return_value
    r = client.post('/api/checkout/', headers=auth_headers, json={"userId": "victim", "providerName": "B"})
    assert r.status_code == 201
    params = cur.execute.call_args[0][1]
    assert params[1] == 'fake-user-id' and params[-1] == 0


def test_seed_admin(mocker):
    from backend.admin_seed import seed_admin
    conn = mocker.MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = None
    uid = seed_admin(conn, 'rootadmin', 'a-very-long-password')
    assert uid
    inserts = [c[0] for c in cur.execute.call_args_list if 'INSERT' in c[0][0]]
    assert "'admin'" in inserts[0][0]
    assert inserts[1][1][2] != 'a-very-long-password'  # lưu hash
    conn.commit.assert_called_once()


@pytest.mark.parametrize("user,pwd", [('ab', 'a-very-long-password'), ('rootadmin', 'short')])
def test_seed_admin_validation(mocker, user, pwd):
    from backend.admin_seed import seed_admin
    with pytest.raises(ValueError):
        seed_admin(mocker.MagicMock(), user, pwd)
