from flask import Blueprint, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
import re
import uuid
import os

import throttle
from auth_utils import issue_token, get_token_ttl, require_auth
from errors import ApiError, register_blueprint_errors
from validation import json_body, get_str, invalid

auth_bp = Blueprint('auth', __name__)
register_blueprint_errors(auth_bp)

ALLOWED_SIGNUP_ROLES = ('user', 'seller')

# Giới hạn độ dài khớp cột MySQL (tránh lỗi 1406 -> 500 ở strict mode)
MAX_NAME_LEN = 50
MAX_EMAIL_LEN = 50
MAX_USERNAME_LEN = 25
MAX_PASSWORD_LEN = 128
MAX_BIO_LEN = 2000
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_PHONE_RE = re.compile(r'^[0-9]{9,10}$')
_PIN_RE = re.compile(r'^[0-9]{6}$')

# Băm giả để thời gian phản hồi của username không tồn tại ≈ username tồn tại (chống dò tài khoản)
_DUMMY_PASSWORD_HASH = generate_password_hash('slopee-dummy-password')


def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'slopee'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'slopee_db'),
        cursorclass=pymysql.cursors.DictCursor
    )


def _password_failure(cursor, conn, subject, message, code='invalid_credentials'):
    """Ghi nhận một lần sai mật khẩu, commit ngay (không bị rollback), rồi trả lỗi 401 kèm số lần còn lại."""
    failed, _locked_until = throttle.record_failure(cursor, throttle.SCOPE_PASSWORD, subject)
    conn.commit()
    return ApiError(message, code, 401, extra={"attemptsRemaining": throttle.attempts_remaining(failed)})


def _clear_failures(cursor, conn, subject, failed):
    if failed:
        throttle.reset(cursor, throttle.SCOPE_PASSWORD, subject)
        conn.commit()


@auth_bp.route('/signup', methods=['POST'])
def signup():
    data = json_body()
    role = data.get('role', 'user') # chỉ cho phép 'user' hoặc 'seller'
    if role not in ALLOWED_SIGNUP_ROLES:
        return jsonify({"error": "Invalid role. Only 'user' or 'seller' can be registered."}), 403
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')
    username = data.get('username')
    password = data.get('password')
    pass_phrase = data.get('pass_phrase') # 6-digit

    if not all([name, email, phone, username, password, pass_phrase]):
        return jsonify({"error": "All fields are required"}), 400
    if not all(isinstance(v, str) for v in (name, email, phone, username, password, pass_phrase)):
        return jsonify({"error": "All fields must be text"}), 400
    if not _PIN_RE.match(pass_phrase):
        return jsonify({"error": "Passphrase must be exactly a 6-digit number"}), 400
    if len(username) <= 3:
        return jsonify({"error": "Username must be longer than 3 characters"}), 400

    # Kiểm tra định dạng/độ dài (sau các kiểm tra cũ để giữ nguyên thông báo hiện có)
    name = name.strip()
    email = email.strip()
    phone = phone.strip()
    if not name or len(name) > MAX_NAME_LEN:
        raise invalid(f"Name must be 1-{MAX_NAME_LEN} characters")
    if len(username) > MAX_USERNAME_LEN:
        raise invalid(f"Username must be at most {MAX_USERNAME_LEN} characters")
    if len(email) > MAX_EMAIL_LEN or not _EMAIL_RE.match(email):
        raise invalid("Email is not valid")
    if not _PHONE_RE.match(phone):
        raise invalid("Phone number must be 9-10 digits")
    if len(password) > MAX_PASSWORD_LEN:
        raise invalid(f"Password must be at most {MAX_PASSWORD_LEN} characters")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email=%s OR phone=%s", (email, phone))
            if cursor.fetchone():
                return jsonify({"error": "Email or Phone already exists!"}), 400

            cursor.execute("SELECT userId FROM credentials WHERE username=%s", (username,))
            if cursor.fetchone():
                return jsonify({"error": "Username already taken!"}), 400

            user_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO users (id, role, name, email, phone, bio) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, role, name, email, phone, '')
            )

            salt = 'werkzeug-managed'
            pwd_hash = generate_password_hash(password)
            phrase_hash = generate_password_hash(pass_phrase)

            cursor.execute(
                "INSERT INTO credentials (userId, username, passwordHash, passwordSalt, passPhraseHash) VALUES (%s, %s, %s, %s, %s)",
                (user_id, username, pwd_hash, salt, phrase_hash)
            )
        conn.commit()
        return jsonify({"message": "User registered successfully!"}), 201
    except pymysql.err.IntegrityError:
        # Hai request đăng ký trùng chạy song song: ràng buộc UNIQUE của DB chặn lại
        conn.rollback()
        raise ApiError("Email, phone or username already exists!", 'already_exists', 409)
    except Exception:
        conn.rollback()
        raise  # -> handler chung: log chi tiết, client chỉ nhận 500 chung
    finally:
        conn.close()


@auth_bp.route('/login', methods=['POST'])
def login():
    data = json_body()
    username = data.get('username')
    password = data.get('password')

    if not username or not password or not isinstance(username, str) or not isinstance(password, str):
        return jsonify({"error": "Username and password required"}), 400
    if len(username) > 100 or len(password) > MAX_PASSWORD_LEN:
        # không thể là thông tin đăng nhập hợp lệ; không tốn công băm/đếm
        return jsonify({"error": "Invalid username or password"}), 401

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT c.userId, c.passwordHash, u.role, u.name, u.email 
                FROM credentials c 
                JOIN users u ON c.userId = u.id 
                WHERE c.username=%s
            """, (username,))
            user = cursor.fetchone()

            # P0-05 (S-09): khóa tạm sau 5 lần sai; username không tồn tại cũng bị đếm như tài khoản thật
            subject = throttle.password_subject(user['userId'] if user else None, username)
            failed = throttle.check(cursor, throttle.SCOPE_PASSWORD, subject)  # ném 429 nếu đang khóa

            if user:
                ok = check_password_hash(user['passwordHash'], password)
            else:
                check_password_hash(_DUMMY_PASSWORD_HASH, password)
                ok = False

            if ok:
                _clear_failures(cursor, conn, subject, failed)
                return jsonify({
                    "message": "Login successful",
                    "token": issue_token(user['userId'], user['role']),
                    "expiresIn": get_token_ttl(),
                    "user": {
                        "id": user['userId'],
                        "name": user['name'],
                        "username": username,
                        "role": user['role'],
                        "email": user['email']
                    }
                }), 200
            raise _password_failure(cursor, conn, subject, "Invalid username or password")
    finally:
        conn.close()


# Feature H: Deletion Request Pipeline replacing immediate cascade logic
@auth_bp.route('/account/request-deletion', methods=['POST'])
@require_auth
def request_account_deletion():
    data = json_body()
    user_id = g.user_id
    password = data.get('password')

    if not password:
        return jsonify({"error": "Missing authorization vectors."}), 400
    if not isinstance(password, str) or len(password) > MAX_PASSWORD_LEN:
        return jsonify({"error": "Invalid clearance security password."}), 401

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT passwordHash FROM credentials WHERE userId=%s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({"error": "User anomaly detected"}), 404

            subject = throttle.password_subject(user_id)
            failed = throttle.check(cursor, throttle.SCOPE_PASSWORD, subject)

            if check_password_hash(user['passwordHash'], password):
                _clear_failures(cursor, conn, subject, failed)
                cursor.execute("UPDATE users SET deletionRequestedAt = current_timestamp WHERE id=%s", (user_id,))
                conn.commit()
                return jsonify({"message": "Deletion formal request dispatched to Admin division."}), 200
            raise _password_failure(cursor, conn, subject, "Invalid clearance security password.")
    finally:
        conn.close()


# Feature H: Profile Overrides
@auth_bp.route('/profile', methods=['PUT'])
@require_auth
def update_profile():
    data = json_body()
    user_id = g.user_id  # luôn lấy từ token, không tin userId trong body (S-11)
    bio = get_str(data, 'bio', required=False, max_len=MAX_BIO_LEN, label='Bio', strip=False) or ''

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET bio=%s WHERE id=%s", (bio, user_id))
            conn.commit()
            return jsonify({"message": "Bio successfully updated."}), 200
    finally:
        conn.close()


@auth_bp.route('/username', methods=['PUT'])
@require_auth
def update_username():
    data = json_body()
    user_id = g.user_id  # luôn lấy từ token (S-11)
    new_username = data.get('newUsername')

    if not new_username or not isinstance(new_username, str) or len(new_username) <= 3:
        return jsonify({"error": "Username excessively short."}), 400
    if len(new_username) > MAX_USERNAME_LEN:
        raise invalid(f"Username must be at most {MAX_USERNAME_LEN} characters")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT userId FROM credentials WHERE username=%s AND userId != %s", (new_username, user_id))
            if cursor.fetchone():
                return jsonify({"error": "Username structurally collided. Already taken."}), 409

            cursor.execute("UPDATE credentials SET username=%s WHERE userId=%s", (new_username, user_id))
            conn.commit()
            return jsonify({"message": "Username dynamically rebound."}), 200
    except pymysql.err.IntegrityError:
        conn.rollback()
        raise ApiError("Username structurally collided. Already taken.", 'already_exists', 409)
    finally:
        conn.close()


@auth_bp.route('/password', methods=['PUT'])
@require_auth
def update_password():
    data = json_body()
    user_id = g.user_id
    old_password = data.get('oldPassword')
    new_password = data.get('newPassword')

    if not old_password or not new_password:
        return jsonify({"error": "Both security strings required."}), 400
    if not isinstance(old_password, str) or not isinstance(new_password, str):
        return jsonify({"error": "Both security strings required."}), 400
    if len(new_password) > MAX_PASSWORD_LEN:
        raise invalid(f"Password must be at most {MAX_PASSWORD_LEN} characters")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT passwordHash FROM credentials WHERE userId=%s", (user_id,))
            user = cursor.fetchone()

            subject = throttle.password_subject(user_id)
            failed = throttle.check(cursor, throttle.SCOPE_PASSWORD, subject)

            if not user or len(old_password) > MAX_PASSWORD_LEN or not check_password_hash(user['passwordHash'], old_password):
                raise _password_failure(cursor, conn, subject, "Invalid legacy password.")

            _clear_failures(cursor, conn, subject, failed)
            new_hash = generate_password_hash(new_password)
            cursor.execute("UPDATE credentials SET passwordHash=%s WHERE userId=%s", (new_hash, user_id))
            conn.commit()
            return jsonify({"message": "Security matrix password successfully updated."}), 200
    finally:
        conn.close()


@auth_bp.route('/reviews/me', methods=['GET'])
@require_auth
def get_user_reviews():
    user_id = g.user_id
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.id, r.rating, r.comment, r.createdAt, p.name as productName, p.id as productId
                FROM reviews r
                JOIN products p ON r.productId = p.id
                WHERE r.userId = %s
                ORDER BY r.createdAt DESC
            """, (user_id,))
            history = cursor.fetchall()
            return jsonify({"reviews": history}), 200
    finally:
        conn.close()
