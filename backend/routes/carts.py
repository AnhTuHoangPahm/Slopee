from flask import Blueprint, request, jsonify
import pymysql
import uuid
import os
import json

carts_bp = Blueprint('carts', __name__)

def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'slopee_db'),
        cursorclass=pymysql.cursors.DictCursor
    )

def get_or_create_cart(cursor, user_id):
    cursor.execute("SELECT id FROM carts WHERE userId=%s AND status='active'", (user_id,))
    cart = cursor.fetchone()
    if cart:
        return cart['id']
    cart_id = str(uuid.uuid4())
    cursor.execute("INSERT INTO carts (id, userId) VALUES (%s, %s)", (cart_id, user_id))
    return cart_id

@carts_bp.route('/<user_id>', methods=['GET'])
def fetch_cart(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cart_id = get_or_create_cart(cursor, user_id)
            conn.commit()
            
            query = """
                SELECT ci.id as cartItemId, ci.quantity, ci.selectedVariants,
                       p.id as productId, p.name, p.unitPrice, p.inStock,
                       s.name as shopName
                FROM cartItems ci
                JOIN products p ON ci.productId = p.id
                JOIN shops s ON p.shopId = s.id
                WHERE ci.cartId = %s
                ORDER BY ci.id DESC
            """
            cursor.execute(query, (cart_id,))
            raw_items = cursor.fetchall()
            
            # Deserialize JSON block for accurate frontend routing
            items = []
            for i in raw_items:
                if i['selectedVariants']:
                    try:
                        i['selectedVariants'] = json.loads(i['selectedVariants'])
                    except:
                        i['selectedVariants'] = {}
                else:
                    i['selectedVariants'] = {}
                items.append(i)
            
            return jsonify({"cartId": cart_id, "items": items}), 200
    finally:
        conn.close()

@carts_bp.route('/items', methods=['POST'])
def add_to_cart():
    data = request.json
    user_id = data.get('userId')
    product_id = data.get('productId')
    quantity = int(data.get('quantity', 1))
    selected_variants = data.get('selectedVariants', {})
    
    # Deterministic sorting for variant string matching
    variants_json = json.dumps(selected_variants, sort_keys=True)

    if quantity <= 0:
        return jsonify({"error": "Quantity must be greater than 0"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT inStock FROM products WHERE id=%s AND isActive=TRUE", (product_id,))
            product = cursor.fetchone()
            if not product:
                return jsonify({"error": "Product not found or inactive"}), 404
            if product['inStock'] < quantity:
                return jsonify({"error": f"Only {product['inStock']} items left in stock!"}), 400

            cart_id = get_or_create_cart(cursor, user_id)
            
            cursor.execute("SELECT id, quantity FROM cartItems WHERE cartId=%s AND productId=%s AND selectedVariants=%s", (cart_id, product_id, variants_json))
            existing_item = cursor.fetchone()
            
            if existing_item:
                new_qty = existing_item['quantity'] + quantity
                if product['inStock'] < new_qty:
                    return jsonify({"error": f"Cannot add more! You already have {existing_item['quantity']} in cart and only {product['inStock']} exist."}), 400
                cursor.execute("UPDATE cartItems SET quantity=%s WHERE id=%s", (new_qty, existing_item['id']))
            else:
                item_id = str(uuid.uuid4())
                cursor.execute("INSERT INTO cartItems (id, cartId, productId, quantity, selectedVariants) VALUES (%s, %s, %s, %s, %s)", 
                               (item_id, cart_id, product_id, quantity, variants_json))
                
            conn.commit()
            return jsonify({"message": "Successfully added to cart!"}), 200
    finally:
        conn.close()

@carts_bp.route('/items/<item_id>', methods=['PUT', 'DELETE'])
def manage_cart_item(item_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'DELETE':
                cursor.execute("DELETE FROM cartItems WHERE id=%s", (item_id,))
                conn.commit()
                return jsonify({"message": "Item deleted."}), 200
                
            elif request.method == 'PUT':
                data = request.json
                new_qty = int(data.get('quantity', 1))
                if new_qty <= 0:
                    return jsonify({"error": "Quantity must be > 0"}), 400
                    
                cursor.execute("""
                    SELECT p.inStock FROM cartItems ci 
                    JOIN products p ON ci.productId = p.id 
                    WHERE ci.id=%s
                """, (item_id,))
                prod = cursor.fetchone()
                if not prod:
                    return jsonify({"error": "Item not found"}), 404
                    
                if new_qty > prod['inStock']:
                    return jsonify({"error": "Exceeds available stock!"}), 400
                    
                cursor.execute("UPDATE cartItems SET quantity=%s WHERE id=%s", (new_qty, item_id))
                conn.commit()
                return jsonify({"message": "Quantity updated"}), 200
    finally:
        conn.close()
