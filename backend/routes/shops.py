from flask import Blueprint, request, jsonify
import pymysql
import uuid
import os

shops_bp = Blueprint('shops', __name__)

def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'slopee_db'),
        cursorclass=pymysql.cursors.DictCursor
    )

@shops_bp.route('/', methods=['POST'])
def setup_shop():
    data = request.json
    seller_id = data.get('seller_id')
    name = data.get('name')
    description = data.get('description', '')
    
    if not seller_id or not name:
        return jsonify({"error": "Seller ID and Name required"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT role FROM users WHERE id=%s", (seller_id,))
            user = cursor.fetchone()
            if not user or user['role'] != 'seller':
                return jsonify({"error": "Only sellers can create shops"}), 403
            
            cursor.execute("SELECT id FROM shops WHERE sellerId=%s", (seller_id,))
            if cursor.fetchone():
                return jsonify({"error": "You already have a shop setup!"}), 400
                
            # FEATURE E RESTRICTION: Block shop creation if no active Bank Account exists to accept revenue payouts
            cursor.execute("SELECT id FROM paymentMethods WHERE userId=%s LIMIT 1", (seller_id,))
            if not cursor.fetchone():
                return jsonify({"error": "You must link at least one Bank Account to receive item payouts before activating your shop!"}), 403
                
            shop_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO shops (id, sellerId, name, description) VALUES (%s, %s, %s, %s)",
                (shop_id, seller_id, name, description)
            )
            conn.commit()
            return jsonify({"message": "Shop created successfully!", "shopId": shop_id}), 201
    finally:
        conn.close()

@shops_bp.route('/<seller_id>', methods=['GET'])
def get_shop(seller_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM shops WHERE sellerId=%s", (seller_id,))
            shop = cursor.fetchone()
            if not shop:
                return jsonify({"error": "Shop not found"}), 404
            
            cursor.execute("SELECT * FROM products WHERE shopId=%s ORDER BY name ASC", (shop['id'],))
            shop['products'] = cursor.fetchall()
            return jsonify(shop), 200
    finally:
        conn.close()

@shops_bp.route('/<seller_id>/name', methods=['PUT'])
def update_shop_name(seller_id):
    data = request.json
    new_name = data.get('name')
    if not new_name: return jsonify({"error": "Name required"}), 400
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE shops SET name=%s WHERE sellerId=%s", (new_name, seller_id))
            conn.commit()
            return jsonify({"message": "Shop name updated"}), 200
    finally:
        conn.close()

@shops_bp.route('/products', methods=['POST'])
def add_product():
    data = request.json
    shop_id = data.get('shopId')
    name = data.get('name')
    description = data.get('description', '')
    category_id = data.get('categoryId', 1) 
    in_stock = data.get('inStock', 0)
    unit_price = data.get('unitPrice', 0)
    
    if not all([shop_id, name]): return jsonify({"error": "Shop ID and Product Name required"}), 400
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM categories WHERE id=%s", (category_id,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO categories (name) VALUES ('General')")
                conn.commit()
                cursor.execute("SELECT id FROM categories LIMIT 1")
                category_id = cursor.fetchone()['id']

            prod_id = str(uuid.uuid4())[:15]
            cursor.execute(
                """INSERT INTO products 
                (id, categoryId, shopId, name, description, inStock, unitPrice, isActive) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (prod_id, category_id, shop_id, name, description, in_stock, unit_price, True)
            )
            conn.commit()
            return jsonify({"message": "Product successfully added", "productId": prod_id}), 201
    finally:
        conn.close()

@shops_bp.route('/products/<product_id>', methods=['PUT', 'DELETE'])
def manage_product(product_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'DELETE':
                cursor.execute("DELETE FROM products WHERE id=%s", (product_id,))
                conn.commit()
                return jsonify({"message": "Product deleted"}), 200
            elif request.method == 'PUT':
                data = request.json
                price = float(data.get('unitPrice', 0))
                stock = int(data.get('inStock', 0))
                cursor.execute("UPDATE products SET unitPrice=%s, inStock=%s WHERE id=%s", (price, stock, product_id))
                conn.commit()
                return jsonify({"message": "Product updated"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()
