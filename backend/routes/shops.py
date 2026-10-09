from flask import Blueprint, request, jsonify
import pymysql
import uuid
import os

shops_bp = Blueprint('shops', __name__)

def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=int(os.environ.get('DB_PORT') or 3306),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'slopee_db'),
        cursorclass=pymysql.cursors.DictCursor
    )

@shops_bp.route('/migrate', methods=['GET'])
def run_migration():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Update Enum
            try: cursor.execute("ALTER TABLE orders MODIFY COLUMN status enum('pending', 'paid', 'shipped', 'received', 'cancelled') NOT NULL default 'pending'")
            except: pass
            
            cursor.execute("SELECT CONSTRAINT_NAME, TABLE_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA='slopee_db' AND COLUMN_NAME='productId' AND REFERENCED_TABLE_NAME='products'")
            res = cursor.fetchall()
            cart_c = next((r['CONSTRAINT_NAME'] for r in res if r['TABLE_NAME'].lower() == 'cartitems'), 'cartitems_ibfk_2')
            ord_c = next((r['CONSTRAINT_NAME'] for r in res if r['TABLE_NAME'].lower() == 'orderlines'), 'orderlines_ibfk_2')
            
            # 2. Add columns
            try: cursor.execute("ALTER TABLE orderLines ADD COLUMN snapshotProductName varchar(255)")
            except: pass
            try: cursor.execute("ALTER TABLE orderLines ADD COLUMN snapshotShopName varchar(100)")
            except: pass
            
            # 3. Backfill
            cursor.execute("UPDATE orderLines ol JOIN products p ON ol.productId = p.id JOIN shops s ON p.shopId = s.id SET ol.snapshotProductName = p.name, ol.snapshotShopName = s.name WHERE ol.snapshotProductName IS NULL")
            
            # 4. Alter restrictions
            try:
                cursor.execute(f"ALTER TABLE cartItems DROP FOREIGN KEY {cart_c}")
                cursor.execute("ALTER TABLE cartItems ADD CONSTRAINT fk_cart_products FOREIGN KEY (productId) REFERENCES products(id) ON DELETE CASCADE")
            except: pass
            
            try:
                cursor.execute(f"ALTER TABLE orderLines DROP FOREIGN KEY {ord_c}")
                cursor.execute("ALTER TABLE orderLines MODIFY productId varchar(15) NULL")
                cursor.execute("ALTER TABLE orderLines ADD CONSTRAINT fk_orders_products FOREIGN KEY (productId) REFERENCES products(id) ON DELETE SET NULL")
            except: pass
            
            conn.commit()
            return "Migration Executed Successfully"
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()

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

@shops_bp.route('/products/<product_id>', methods=['DELETE'])
def delete_product(product_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM products WHERE id=%s", (product_id,))
            conn.commit()
            return jsonify({"message": "Product totally physically removed!"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@shops_bp.route('/products/<product_id>', methods=['PUT'])
def update_product(product_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
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

# --- PHASE 1 FEATURE F: PRODUCT RICHNESS APIS ---

@shops_bp.route('/products/<product_id>/images', methods=['POST'])
def add_product_image(product_id):
    data = request.json
    url = data.get('imageUrl')
    is_primary = data.get('isPrimary', False)
    if not url: return jsonify({"error": "Missing imageUrl"}), 400
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
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
def delete_product_image(image_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM productImages WHERE id=%s", (image_id,))
            conn.commit()
            return jsonify({"message": "Image dynamically detached"}), 200
    finally:
        conn.close()

@shops_bp.route('/products/<product_id>/variants', methods=['POST'])
def add_product_variant(product_id):
    data = request.json
    name = data.get('variantName')
    val = data.get('variantValue')
    if not name or not val: return jsonify({"error": "Variant configurations accurately required"}), 400
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            v_id = str(uuid.uuid4())
            cursor.execute("INSERT INTO productVariants (id, productId, variantName, variantValue) VALUES (%s, %s, %s, %s)",
                           (v_id, product_id, name, val))
            conn.commit()
            return jsonify({"message": "Variant established seamlessly", "variantId": v_id}), 201
    finally:
        conn.close()

@shops_bp.route('/products/variants/<variant_id>', methods=['DELETE'])
def delete_product_variant(variant_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM productVariants WHERE id=%s", (variant_id,))
            conn.commit()
            return jsonify({"message": "Variant successfully removed"}), 200
    finally:
        conn.close()
