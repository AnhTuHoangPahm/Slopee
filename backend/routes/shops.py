from flask import Blueprint, jsonify, g
import pymysql
import uuid
import os

from auth_utils import require_auth
from errors import ApiError, register_blueprint_errors
from money import to_vnd, InvalidMoney
from validation import json_body, get_str, get_int, get_bool, validate_url, invalid

shops_bp = Blueprint('shops', __name__)
register_blueprint_errors(shops_bp)

MAX_STOCK = 1000000


def _not_found(what):
    # P0-03: tài nguyên của người khác trả 404 y như không tồn tại (không lộ sự tồn tại)
    return ApiError(f"{what} not found", 'not_found', 404)


def _require_own_product(cursor, product_id):
    """Sản phẩm phải thuộc shop của seller đang đăng nhập (S-06)."""
    cursor.execute(
        "SELECT p.id FROM products p JOIN shops s ON p.shopId = s.id WHERE p.id=%s AND s.sellerId=%s",
        (product_id, g.user_id))
    if not cursor.fetchone():
        raise _not_found("Product")

def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'slopee_db'),
        cursorclass=pymysql.cursors.DictCursor
    )

@shops_bp.route('/', methods=['POST'])
@require_auth('seller')
def setup_shop():
    data = json_body()
    seller_id = g.user_id
    name = get_str(data, 'name', max_len=100, label='Shop name', required_msg="Shop name required")
    description = get_str(data, 'description', required=False, max_len=5000, label='description', strip=False) or ''

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

@shops_bp.route('/me', methods=['GET'])
@require_auth('seller')
def get_shop():
    seller_id = g.user_id
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM shops WHERE sellerId=%s", (seller_id,))
            shop = cursor.fetchone()
            if not shop:
                return jsonify({"error": "Shop not found"}), 404
            
            cursor.execute("SELECT * FROM products WHERE shopId=%s ORDER BY name ASC", (shop['id'],))
            prods = cursor.fetchall()
            
            # Hydrate with Phase 1 Product Richness architectures
            for p in prods:
                cursor.execute("SELECT * FROM productImages WHERE productId=%s", (p['id'],))
                p['images'] = cursor.fetchall()
                cursor.execute("SELECT * FROM productVariants WHERE productId=%s", (p['id'],))
                p['variants'] = cursor.fetchall()

            shop['products'] = prods
            return jsonify(shop), 200
    finally:
        conn.close()

@shops_bp.route('/me/name', methods=['PUT'])
@require_auth('seller')
def update_shop_name():
    seller_id = g.user_id
    data = json_body()
    new_name = get_str(data, 'name', max_len=100, label='Name', required_msg="Name required")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE shops SET name=%s WHERE sellerId=%s", (new_name, seller_id))
            conn.commit()
            return jsonify({"message": "Shop name updated"}), 200
    finally:
        conn.close()

@shops_bp.route('/products', methods=['POST'])
@require_auth('seller')
def add_product():
    data = json_body()
    name = get_str(data, 'name', max_len=255, label='Product Name', required_msg="Product Name required")
    description = get_str(data, 'description', required=False, max_len=5000, label='description', strip=False) or ''
    category_id = get_int(data, 'categoryId', default=1, label='categoryId', minimum=1)
    in_stock = get_int(data, 'inStock', default=0, label='inStock', minimum=0, maximum=MAX_STOCK)
    try:
        unit_price = to_vnd(data.get('unitPrice', 0))
    except InvalidMoney as e:
        return jsonify({"error": f"unitPrice: {e}"}), 400
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Shop được xác định từ token của seller, không nhận shopId từ client
            cursor.execute("SELECT id FROM shops WHERE sellerId=%s", (g.user_id,))
            shop = cursor.fetchone()
            if not shop:
                return jsonify({"error": "You must set up your shop first."}), 403
            shop_id = shop['id']

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

@shops_bp.route('/products/<product_id>', methods=['DELETE'])
@require_auth('seller')
def delete_product(product_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            _require_own_product(cursor, product_id)  # S-06
            cursor.execute("DELETE FROM products WHERE id=%s", (product_id,))
            conn.commit()
            return jsonify({"message": "Product totally physically removed!"}), 200
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@shops_bp.route('/products/<product_id>', methods=['PUT'])
@require_auth('seller')
def update_product(product_id):
    data = json_body()
    try:
        price = to_vnd(data.get('unitPrice', 0))
    except InvalidMoney as e:
        return jsonify({"error": f"unitPrice: {e}"}), 400
    stock = get_int(data, 'inStock', default=0, label='inStock', minimum=0, maximum=MAX_STOCK)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            _require_own_product(cursor, product_id)  # S-06
            cursor.execute("UPDATE products SET unitPrice=%s, inStock=%s WHERE id=%s", (price, stock, product_id))
            conn.commit()
            return jsonify({"message": "Product updated"}), 200
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# --- PHASE 1 FEATURE F: PRODUCT RICHNESS APIS ---

@shops_bp.route('/products/<product_id>/images', methods=['POST'])
@require_auth('seller')
def add_product_image(product_id):
    data = json_body()
    if not data.get('imageUrl'):
        return jsonify({"error": "Missing imageUrl"}), 400
    url = validate_url(data.get('imageUrl'), 'imageUrl')
    is_primary = get_bool(data, 'isPrimary', False)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            _require_own_product(cursor, product_id)  # S-06
            if is_primary:
                cursor.execute("UPDATE productImages SET isPrimary=FALSE WHERE productId=%s", (product_id,))
            img_id = str(uuid.uuid4())
            cursor.execute("INSERT INTO productImages (id, productId, imageUrl, isPrimary) VALUES (%s, %s, %s, %s)",
                           (img_id, product_id, url, is_primary))
            conn.commit()
            return jsonify({"message": "Image successfully attached", "imageId": img_id}), 201
    finally:
        conn.close()

@shops_bp.route('/products/images/<image_id>', methods=['DELETE'])
@require_auth('seller')
def delete_product_image(image_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                DELETE pi FROM productImages pi
                JOIN products p ON pi.productId = p.id
                JOIN shops s ON p.shopId = s.id
                WHERE pi.id=%s AND s.sellerId=%s
            """, (image_id, g.user_id))
            if cursor.rowcount == 0:
                raise _not_found("Image")
            conn.commit()
            return jsonify({"message": "Image dynamically detached"}), 200
    finally:
        conn.close()

@shops_bp.route('/products/<product_id>/variants', methods=['POST'])
@require_auth('seller')
def add_product_variant(product_id):
    data = json_body()
    if not data.get('variantName') or not data.get('variantValue'):
        return jsonify({"error": "Variant configurations accurately required"}), 400
    name = get_str(data, 'variantName', max_len=100, label='variantName')
    val = get_str(data, 'variantValue', max_len=100, label='variantValue')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            _require_own_product(cursor, product_id)  # S-06
            v_id = str(uuid.uuid4())
            cursor.execute("INSERT INTO productVariants (id, productId, variantName, variantValue) VALUES (%s, %s, %s, %s)",
                           (v_id, product_id, name, val))
            conn.commit()
            return jsonify({"message": "Variant established seamlessly", "variantId": v_id}), 201
    finally:
        conn.close()

@shops_bp.route('/products/variants/<variant_id>', methods=['DELETE'])
@require_auth('seller')
def delete_product_variant(variant_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                DELETE pv FROM productVariants pv
                JOIN products p ON pv.productId = p.id
                JOIN shops s ON p.shopId = s.id
                WHERE pv.id=%s AND s.sellerId=%s
            """, (variant_id, g.user_id))
            if cursor.rowcount == 0:
                raise _not_found("Variant")
            conn.commit()
            return jsonify({"message": "Variant successfully removed"}), 200
    finally:
        conn.close()
