"""Seed tài khoản Shipper bằng CLI (migration 0020: Shipper không đăng ký công khai, chỉ tạo bằng CLI/Admin)."""
import uuid

from werkzeug.security import generate_password_hash

MIN_SHIPPER_PASSWORD_LEN = 12


def seed_shipper(conn, username, password, name='Shipper', email=None, phone=None):
    """Tạo tài khoản role `shipper`. Trả về user_id. Ném ValueError nếu đầu vào không hợp lệ/đã tồn tại."""
    if not username or len(username) <= 3:
        raise ValueError("Username must be longer than 3 characters")
    if not password or len(password) < MIN_SHIPPER_PASSWORD_LEN:
        raise ValueError(f"Shipper password must be at least {MIN_SHIPPER_PASSWORD_LEN} characters")
    user_id = str(uuid.uuid4())
    email = email or f"{username}@slopee.local"
    phone = phone or user_id.replace('-', '')[:10]
    with conn.cursor() as cursor:
        cursor.execute("SELECT userId FROM credentials WHERE username=%s", (username,))
        if cursor.fetchone():
            raise ValueError(f"Username '{username}' already exists")
        cursor.execute("SELECT id FROM users WHERE email=%s OR phone=%s", (email, phone))
        if cursor.fetchone():
            raise ValueError("Email or phone already exists")
        cursor.execute("INSERT INTO users (id, role, name, email, phone, bio) VALUES (%s, 'shipper', %s, %s, %s, '')",
                       (user_id, name, email, phone))
        cursor.execute("INSERT INTO credentials (userId, username, passwordHash, passwordSalt, passPhraseHash) "
                       "VALUES (%s, %s, %s, %s, NULL)", (user_id, username, generate_password_hash(password), 'werkzeug-managed'))
    conn.commit()
    return user_id
