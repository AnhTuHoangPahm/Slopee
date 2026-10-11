from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
import uuid
import os

from auth_utils import issue_token, get_token_ttl, require_auth

auth_bp = Blueprint('auth', __name__)

ALLOWED_SIGNUP_ROLES = ('user', 'seller')

def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'slopee'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'slopee_db'),
        cursorclass=pymysql.cursors.DictCursor
    )

@auth_bp.route('/signup', methods=['POST'])
def signup():
    data = request.get_json(silent=True) or {}
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
    if len(pass_phrase) != 6 or not pass_phrase.isdigit():
        return jsonify({"error": "Passphrase must be exactly a 6-digit number"}), 400
    if len(username) <= 3:
        return jsonify({"error": "Username must be longer than 3 characters"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check duplicates
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
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

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
            
            if user and check_password_hash(user['passwordHash'], password):
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
            else:
                return jsonify({"error": "Invalid username or password"}), 401
    finally:
        conn.close()

# Feature H: Deletion Request Pipeline replacing immediate cascade logic
@auth_bp.route('/account/request-deletion', methods=['POST'])
@require_auth
def request_account_deletion():
    data = request.get_json(silent=True) or {}
    user_id = g.user_id
    password = data.get('password')
    
    if not password:
        return jsonify({"error": "Missing authorization vectors."}), 400
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT passwordHash FROM credentials WHERE userId=%s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({"error": "User anomaly detected"}), 404
                
            if check_password_hash(user['passwordHash'], password):
                # Request structurally flagged
                cursor.execute("UPDATE users SET deletionRequestedAt = current_timestamp WHERE id=%s", (user_id,))
                conn.commit()
                return jsonify({"message": "Deletion formal request dispatched to Admin division."}), 200
            else:
                return jsonify({"error": "Invalid clearance security password."}), 401
    finally:
        conn.close()

# Feature H: Profile Overrides
@auth_bp.route('/profile', methods=['PUT'])
@require_auth
def update_profile():
    data = request.get_json(silent=True) or {}
    user_id = g.user_id
    bio = data.get('bio', '')
    
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
    data = request.get_json(silent=True) or {}
    user_id = g.user_id
    new_username = data.get('newUsername')
    
    if not new_username or len(new_username) <= 3:
        return jsonify({"error": "Username excessively short."}), 400
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check collision
            cursor.execute("SELECT userId FROM credentials WHERE username=%s AND userId != %s", (new_username, user_id))
            if cursor.fetchone():
                return jsonify({"error": "Username structurally collided. Already taken."}), 409
                
            cursor.execute("UPDATE credentials SET username=%s WHERE userId=%s", (new_username, user_id))
            conn.commit()
            return jsonify({"message": "Username dynamically rebound."}), 200
    finally:
        conn.close()

@auth_bp.route('/password', methods=['PUT'])
@require_auth
def update_password():
    data = request.get_json(silent=True) or {}
    user_id = g.user_id
    old_password = data.get('oldPassword')
    new_password = data.get('newPassword')
    
    if not old_password or not new_password:
        return jsonify({"error": "Both security strings required."}), 400
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT passwordHash FROM credentials WHERE userId=%s", (user_id,))
            user = cursor.fetchone()
            
            if not user or not check_password_hash(user['passwordHash'], old_password):
                return jsonify({"error": "Invalid legacy password."}), 401
                
            new_hash = generate_password_hash(new_password)
            cursor.execute("UPDATE credentials SET passwordHash=%s WHERE userId=%s", (new_hash, user_id))
            conn.commit()
            return jsonify({"message": "Security matrix password successfully updated."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
