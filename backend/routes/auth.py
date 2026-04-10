from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
import uuid
import os

auth_bp = Blueprint('auth', __name__)

def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'slopee_db'),
        cursorclass=pymysql.cursors.DictCursor
    )

@auth_bp.route('/signup', methods=['POST'])
def signup():
    data = request.json
    role = data.get('role', 'user') # 'user' or 'seller'
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
        return jsonify({"error": "Username must be > 3 chars"}), 400

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
    data = request.json
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

# In-memory tally of failed deletions, maps userId -> int
failed_deletion_attempts = {}

@auth_bp.route('/account', methods=['DELETE'])
def delete_account():
    data = request.json
    user_id = data.get('userId')
    password = data.get('password')
    
    if not user_id or not password:
        return jsonify({"error": "Missing user ID or password"}), 400
        
    attempts = failed_deletion_attempts.get(user_id, 0)
    if attempts >= 5:
        return jsonify({"error": "Too many failed attempts. Account locked from deletion."}), 403

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT passwordHash FROM credentials WHERE userId=%s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return jsonify({"error": "User not found"}), 404
                
            if check_password_hash(user['passwordHash'], password):
                # Password verified, cascade delete user
                cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
                conn.commit()
                if user_id in failed_deletion_attempts:
                    del failed_deletion_attempts[user_id]
                return jsonify({"message": "Account successfully deleted"}), 200
            else:
                failed_deletion_attempts[user_id] = attempts + 1
                return jsonify({"error": f"Invalid password. Attempts left: {5 - failed_deletion_attempts[user_id]}"}), 401
    finally:
        conn.close()
