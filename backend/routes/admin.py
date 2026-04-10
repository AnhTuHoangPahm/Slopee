from flask import Blueprint, request, jsonify
import pymysql
import os

admin_bp = Blueprint('admin', __name__)

def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'slopee_db'),
        cursorclass=pymysql.cursors.DictCursor
    )

@admin_bp.route('/stats', methods=['GET'])
def get_stats():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT count(*) as count FROM users")
            users_count = cursor.fetchone()['count']
            
            cursor.execute("SELECT count(*) as count FROM shops")
            shops_count = cursor.fetchone()['count']
            
            cursor.execute("SELECT count(*) as count FROM products")
            products_count = cursor.fetchone()['count']
            
            return jsonify({
                "users": users_count,
                "shops": shops_count,
                "products": products_count
            }), 200
    finally:
        conn.close()

@admin_bp.route('/users', methods=['GET'])
def get_users():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, role, name, email, phone FROM users ORDER BY role")
            users = cursor.fetchall()
            return jsonify(users), 200
    finally:
        conn.close()

@admin_bp.route('/users/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Prevent deleting the master admin
            cursor.execute("SELECT email FROM users WHERE id=%s", (user_id,))
            u = cursor.fetchone()
            if u and u['email'] == '0':
                return jsonify({"error": "Cannot delete the Master System Admin!"}), 403
                
            cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
            conn.commit()
            return jsonify({"message": "User permanently eradicated"}), 200
    finally:
        conn.close()
