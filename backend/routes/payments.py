from flask import Blueprint, request, jsonify, g
from werkzeug.security import check_password_hash
import pymysql
import uuid
import os

from auth_utils import require_auth
from money import to_vnd, format_vnd, InvalidMoney

payments_bp = Blueprint('payments', __name__)

def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'slopee_db'),
        cursorclass=pymysql.cursors.DictCursor
    )

@payments_bp.route('/', methods=['GET'])
@require_auth
def get_payment_methods():
    user_id = g.user_id
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM paymentMethods WHERE userId=%s", (user_id,))
            methods = cursor.fetchall()
            return jsonify({"methods": methods}), 200
    finally:
        conn.close()

@payments_bp.route('/', methods=['POST'])
@require_auth
def add_payment_method():
    data = request.get_json(silent=True) or {}
    user_id = g.user_id
    method_type = data.get('methodType', 'bank')
    provider_name = data.get('providerName', 'Default Bank')
    account_number = data.get('accountNumber', 'xxxx0000')

    method_id = str(uuid.uuid4())
    # S-04: không còn cấp số dư giả lập; phương thức mới luôn bắt đầu với số dư 0.
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO paymentMethods (id, userId, methodType, providerName, accountNumber, balance) VALUES (%s, %s, %s, %s, %s, %s)",
                (method_id, user_id, method_type, provider_name, account_number, 0)
            )
            conn.commit()
            return jsonify({"message": "Payment method added successfully!"}), 201
    finally:
        conn.close()

@payments_bp.route('/checkout', methods=['POST'])
@require_auth
def execute_checkout():
    data = request.get_json(silent=True) or {}
    user_id = g.user_id
    payment_method_id = data.get('paymentMethodId')
    pass_phrase = data.get('passPhrase')
    cart_item_ids = data.get('cartItemIds', [])
    
    if not cart_item_ids:
        return jsonify({"error": "No items completely selected for checkout"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Verify Passphrase 6-digit PIN Match
            cursor.execute("SELECT passPhraseHash FROM credentials WHERE userId=%s", (user_id,))
            cred = cursor.fetchone()
            if not cred or not check_password_hash(cred['passPhraseHash'], pass_phrase):
                return jsonify({"error": "Invalid 6-Digit Payment Passphrase!"}), 401
                
            # 2. Lock items and calculate totals, grouping items by Seller Shop effectively
            total_sum = 0  # VND, số nguyên
            items_payload = []
            
            # Use placeholders for querying multiple items natively
            format_strings = ','.join(['%s'] * len(cart_item_ids))
            cursor.execute(f"""
                SELECT ci.id as cartItemId, ci.quantity, ci.cartId, ci.selectedVariants,
                       p.id as productId, p.unitPrice, p.inStock, p.shopId, p.name as name, s.name as shopName
                FROM cartItems ci
                JOIN products p ON p.id = ci.productId
                JOIN shops s ON p.shopId = s.id
                WHERE ci.id IN ({format_strings}) AND ci.cartId IN (SELECT id FROM carts WHERE userId=%s)
            """, tuple(cart_item_ids) + (user_id,))
            
            cart_items = cursor.fetchall()
            
            if len(cart_items) != len(cart_item_ids):
                return jsonify({"error": "Failed to map some cart entities securely."}), 400
                
            for item in cart_items:
                if item['inStock'] < item['quantity']:
                    return jsonify({"error": f"Insufficient stock for Product #{item['productId']} during checkout race!"}), 400
                total_sum += to_vnd(item['unitPrice']) * int(item['quantity'])
                items_payload.append(item)
                
            # 3. Check Buyer's Payment Balance
            buyer_balance = 0  # VND, số nguyên
            buyer_method_type = 'bank'
            if payment_method_id:
                if payment_method_id == 'CASH_ON_DELIVERY':
                    buyer_method_type = 'cash'
                    payment_method_id = None    # Set FK to null logically; COD bỏ qua kiểm tra số dư
                else:
                    cursor.execute("SELECT methodType, balance FROM paymentMethods WHERE id=%s AND userId=%s", (payment_method_id, user_id))
                    pm = cursor.fetchone()
                    if not pm:
                        return jsonify({"error": "Select payment method does not exist."}), 404
                    buyer_balance = to_vnd(pm['balance'])
                    buyer_method_type = pm['methodType']
                
                if buyer_method_type != 'cash' and buyer_balance < total_sum:
                    return jsonify({"error": f"Insufficient funds. You require {format_vnd(total_sum)} but your balance is only {format_vnd(buyer_balance)}!"}), 400
            else:
                return jsonify({"error": "Payment Method Required"}), 400
                
            # --- START TRANSACTION MANIPULATIONS ---
            
            # A. Deduct from Buyer (unless cash)
            if buyer_method_type != 'cash':
                cursor.execute("UPDATE paymentMethods SET balance = balance - %s WHERE id=%s", (total_sum, payment_method_id))
                
            # Group distributions to Sellers safely
            shop_payouts = {}
            for item in items_payload:
                cost = to_vnd(item['unitPrice']) * int(item['quantity'])
                shop_payouts[item['shopId']] = shop_payouts.get(item['shopId'], 0) + cost
                
            for shop_id, payout in shop_payouts.items():
                cursor.execute("SELECT sellerId FROM shops WHERE id=%s", (shop_id,))
                seller_res = cursor.fetchone()
                if seller_res:
                    seller_id = seller_res['sellerId']
                    # Look up seller's primary bank account to distribute to
                    cursor.execute("SELECT id FROM paymentMethods WHERE userId=%s LIMIT 1", (seller_id,))
                    seller_bank = cursor.fetchone()
                    if seller_bank:
                        cursor.execute("UPDATE paymentMethods SET balance = balance + %s WHERE id=%s", (payout, seller_bank['id']))

            # B. Deplete Stock safely natively via DB computation 
            for item in items_payload:
                cursor.execute("UPDATE products SET inStock = inStock - %s WHERE id=%s", (item['quantity'], item['productId']))

            # C. Create Order + OrderLines
            order_id = str(uuid.uuid4())
            cursor.execute("INSERT INTO orders (id, userId, paymentMethodId, status, totalAmount) VALUES (%s, %s, %s, 'paid', %s)",
                           (order_id, user_id, payment_method_id, total_sum))
                           
            for item in items_payload:
                line_id = str(uuid.uuid4())
                cursor.execute("INSERT INTO orderLines (id, orderId, productId, unitPrice, quantity, snapshotProductName, snapshotShopName, selectedVariants) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                               (line_id, order_id, item['productId'], item['unitPrice'], item['quantity'], item['name'], item['shopName'], item['selectedVariants']))
                               
            # D. Delete CartItems natively
            cursor.execute(f"DELETE FROM cartItems WHERE id IN ({format_strings})", tuple(cart_item_ids))

            conn.commit()
            return jsonify({"message": f"Successfully completed. Receipt generated!"}), 200
            
    except InvalidMoney as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        conn.rollback()
        return jsonify({"error": "Transaction Failed: " + str(e)}), 500
    finally:
        conn.close()

@payments_bp.route('/orders/<order_id>', methods=['PUT'])
@require_auth
def update_order_status(order_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get('status')
    if new_status not in ['cancelled', 'received']:
        return jsonify({"error": "Invalid order status transformation."}), 400
        
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE orders SET status=%s WHERE id=%s", (new_status, order_id))
            conn.commit()
            return jsonify({"message": f"Order status successfully changed to {new_status}!"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@payments_bp.route('/orders', methods=['GET'])
@require_auth
def get_orders():
    user_id = g.user_id
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Fetch structured receipt tree natively via hardcoded snapshots
            cursor.execute("""
                SELECT o.id as orderId, o.totalAmount, o.created_at, o.status,
                       ol.quantity, ol.unitPrice, ol.snapshotProductName as productName, ol.snapshotShopName as shopName, ol.selectedVariants
                FROM orders o
                JOIN orderLines ol ON o.id = ol.orderId
                WHERE o.userId=%s
                ORDER BY o.created_at DESC
            """, (user_id,))
            lines = cursor.fetchall()

            # Group them by orderId completely
            orders_map = {}
            for line in lines:
                o_id = line['orderId']
                if o_id not in orders_map:
                    orders_map[o_id] = {
                        "orderId": o_id,
                        "totalAmount": line['totalAmount'],
                        "created_at": line['created_at'],
                        "status": line['status'],
                        "items": []
                    }
                import json
                try:
                    variants_json = json.loads(line['selectedVariants']) if line['selectedVariants'] else {}
                except:
                    variants_json = {}
                    
                orders_map[o_id]["items"].append({
                    "productName": line['productName'],
                    "shopName": line['shopName'],
                    "quantity": line['quantity'],
                    "unitPrice": line['unitPrice'],
                    "selectedVariants": variants_json
                })
                
            return jsonify({"orders": list(orders_map.values())}), 200
            
    finally:
        conn.close()
