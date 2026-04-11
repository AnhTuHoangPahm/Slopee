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
            cursor.execute("SELECT id, role, name, email, phone, deletionRequestedAt FROM users ORDER BY role")
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

# --- Global Category Management APIs ---

@admin_bp.route('/categories', methods=['GET'])
def get_admin_categories():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Join with products to get product count per category
            cursor.execute("""
                SELECT c.id, c.name, COUNT(p.id) as productCount
                FROM categories c
                LEFT JOIN products p ON c.id = p.categoryId
                GROUP BY c.id, c.name
                ORDER BY c.name ASC
            """)
            categories = cursor.fetchall()
            return jsonify({"categories": categories}), 200
    finally:
        conn.close()

@admin_bp.route('/categories', methods=['POST'])
def create_category():
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({"error": "Category name required"}), 400
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
            conn.commit()
            return jsonify({"message": "Category securely logged."}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@admin_bp.route('/categories/<int:cat_id>', methods=['PUT'])
def rename_category(cat_id):
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({"error": "Category name required"}), 400
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE categories SET name=%s WHERE id=%s", (name, cat_id))
            conn.commit()
            return jsonify({"message": "Category renamed."}), 200
    finally:
        conn.close()

@admin_bp.route('/categories/<int:cat_id>', methods=['DELETE'])
def delete_category(cat_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Integrity Check - DO NOT CASCADE WIPE!
            cursor.execute("SELECT count(*) as count FROM products WHERE categoryId=%s", (cat_id,))
            count = cursor.fetchone()['count']
            if count > 0:
                return jsonify({"error": f"Deletion Blocked: {count} active products are currently utilizing this category tag."}), 409
                
            cursor.execute("DELETE FROM categories WHERE id=%s", (cat_id,))
            conn.commit()
            return jsonify({"message": "Global category permanently eliminated."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
