"""Seed tài khoản admin bằng CLI (P0-02). Không còn tài khoản admin/admin mặc định."""
import uuid

from werkzeug.security import generate_password_hash

MIN_ADMIN_PASSWORD_LEN = 12


def seed_admin(conn, username, password, name='System Admin', email=None, phone=None):
    """Tạo tài khoản admin. Trả về user_id. Ném ValueError nếu đầu vào không hợp lệ/đã tồn tại."""
    if not username or len(username) <= 3:
        raise ValueError("Username must be longer than 3 characters")
    if not password or len(password) < MIN_ADMIN_PASSWORD_LEN:
        raise ValueError(f"Admin password must be at least {MIN_ADMIN_PASSWORD_LEN} characters")

    user_id = str(uuid.uuid4())
    email = email or f"{username}@slopee.local"
    phone = phone or user_id.replace('-', '')[:10]  # cột phone: char(10) UNIQUE NOT NULL

    with conn.cursor() as cursor:
        cursor.execute("SELECT userId FROM credentials WHERE username=%s", (username,))
        if cursor.fetchone():
            raise ValueError(f"Username '{username}' already exists")
        cursor.execute("SELECT id FROM users WHERE email=%s OR phone=%s", (email, phone))
        if cursor.fetchone():
            raise ValueError("Email or phone already exists")

        cursor.execute(
            "INSERT INTO users (id, role, name, email, phone, bio) VALUES (%s, 'admin', %s, %s, %s, '')",
            (user_id, name, email, phone),
        )
        cursor.execute(
            "INSERT INTO credentials (userId, username, passwordHash, passwordSalt, passPhraseHash) "
            "VALUES (%s, %s, %s, %s, NULL)",
            (user_id, username, generate_password_hash(password), 'werkzeug-managed'),
        )
    conn.commit()
    return user_id
