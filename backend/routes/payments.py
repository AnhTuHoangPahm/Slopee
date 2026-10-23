from flask import Blueprint, jsonify, g
from werkzeug.security import check_password_hash
import json
import pymysql
import re
import uuid
import os

import throttle
from auth_utils import require_auth
from errors import ApiError, register_blueprint_errors
from guards import is_web3_order
from money import to_vnd, format_vnd, InvalidMoney
from validation import json_body, get_str, get_enum, invalid

payments_bp = Blueprint('payments', __name__)
register_blueprint_errors(payments_bp)

_PIN_RE = re.compile(r'^[0-9]{6}$')
MAX_CHECKOUT_ITEMS = 100
ER_LOCK_DEADLOCK = 1213
ER_LOCK_WAIT_TIMEOUT = 1205
ER_NO_SUCH_TABLE = 1146

# P0-03 (S-05): bảng chuyển trạng thái hợp lệ cho đường ghi trạng thái đơn cũ
ORDER_TRANSITIONS = {
    'received': ('paid', 'shipped'),
    'cancelled': ('pending', 'paid'),
}

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
    data = json_body()
    user_id = g.user_id
    method_type = get_enum(data, 'methodType', ('bank', 'credit_card', 'cash'), default='bank', label='methodType')
    provider_name = get_str(data, 'providerName', required=False, max_len=100, label='providerName') or 'Default Bank'
    account_number = get_str(data, 'accountNumber', required=False, max_len=50, label='accountNumber') or 'xxxx0000'

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


def _placeholders(n):
    return ','.join(['%s'] * n)


def _parse_cart_item_ids(raw):
    if not isinstance(raw, list) or not raw:
        raise ApiError("No items completely selected for checkout", 'no_items', 400)
    if len(raw) > MAX_CHECKOUT_ITEMS:
        raise invalid(f"At most {MAX_CHECKOUT_ITEMS} items per checkout", 'too_many_items')
    for v in raw:
        if isinstance(v, bool) or not isinstance(v, (str, int)):
            raise invalid("cartItemIds must be a list of ids")
    return list(dict.fromkeys(raw))  # bỏ trùng, giữ thứ tự


def _verify_pin(conn, cursor, user_id, pass_phrase):
    """P0-05: PIN chưa thiết lập -> 401 (không còn 500); sai quá 5 lần -> khóa tạm (429).
    Bộ đếm được commit riêng, trước giao dịch tiền, nên không bị rollback theo đơn hàng."""
    cursor.execute("SELECT passPhraseHash FROM credentials WHERE userId=%s", (user_id,))
    cred = cursor.fetchone()
    if not cred or not cred['passPhraseHash']:
        raise ApiError("No payment passphrase is set for this account.", 'pin_not_set', 401)
    subject = throttle.pin_subject(user_id)
    failed = throttle.check(cursor, throttle.SCOPE_PIN, subject)  # 429 nếu đang khóa
    if not check_password_hash(cred['passPhraseHash'], pass_phrase):
        failed, _locked_until = throttle.record_failure(cursor, throttle.SCOPE_PIN, subject)
        conn.commit()
        raise ApiError("Invalid 6-Digit Payment Passphrase!", 'invalid_pin', 401,
                       extra={"attemptsRemaining": throttle.attempts_remaining(failed)})
    if failed:
        throttle.reset(cursor, throttle.SCOPE_PIN, subject)
    conn.commit()  # kết thúc giao dịch kiểm tra PIN; giao dịch tiền bắt đầu từ câu lệnh tiếp theo


@payments_bp.route('/checkout', methods=['POST'])
@require_auth
def execute_checkout():
    data = json_body()
    user_id = g.user_id
    payment_method_id = data.get('paymentMethodId')
    pass_phrase = data.get('passPhrase')
    cart_item_ids = _parse_cart_item_ids(data.get('cartItemIds'))
    if payment_method_id is not None and (isinstance(payment_method_id, bool)
                                          or not isinstance(payment_method_id, (str, int))):
        raise invalid("paymentMethodId is not valid")
    if not isinstance(pass_phrase, str) or not _PIN_RE.match(pass_phrase):
        raise invalid("Passphrase must be exactly a 6-digit number", 'invalid_pin_format')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Verify Passphrase 6-digit PIN (có giới hạn số lần thử)
            _verify_pin(conn, cursor, user_id, pass_phrase)

            # ---- Giao dịch tiền bắt đầu. Thứ tự khóa cố định: cartItems -> products -> paymentMethods,
            # mỗi nhóm khóa theo ORDER BY id để hai giao dịch song song không khóa chéo (deadlock). ----

            # 2a. Khóa các dòng giỏ thuộc CHÍNH người mua (chặn bấm thanh toán 2 lần cho cùng giỏ)
            cursor.execute(f"""
                SELECT ci.id AS cartItemId, ci.quantity, ci.cartId, ci.selectedVariants, ci.productId
                FROM cartItems ci
                WHERE ci.id IN ({_placeholders(len(cart_item_ids))})
                  AND ci.cartId IN (SELECT id FROM carts WHERE userId=%s)
                ORDER BY ci.id
                FOR UPDATE
            """, tuple(cart_item_ids) + (user_id,))
            cart_items = cursor.fetchall()
            if len(cart_items) != len(cart_item_ids):
                raise ApiError("Failed to map some cart entities securely.", 'cart_mismatch', 400)

            # 2b. Khóa sản phẩm và đọc giá/tồn kho MỚI NHẤT dưới khóa (giá tính tiền = giá đã khóa)
            product_ids = sorted({ci['productId'] for ci in cart_items}, key=str)
            cursor.execute(f"""
                SELECT id AS productId, unitPrice, inStock, shopId, name
                FROM products
                WHERE id IN ({_placeholders(len(product_ids))}) AND isActive = TRUE
                ORDER BY id
                FOR UPDATE
            """, tuple(product_ids))
            products = {p['productId']: p for p in cursor.fetchall()}
            if len(products) != len(product_ids):
                raise ApiError("Some items are no longer available.", 'product_unavailable', 400)

            shop_ids = sorted({p['shopId'] for p in products.values()}, key=str)
            cursor.execute(f"SELECT id AS shopId, name AS shopName, sellerId FROM shops "
                           f"WHERE id IN ({_placeholders(len(shop_ids))})", tuple(shop_ids))
            shops = {s['shopId']: s for s in cursor.fetchall()}

            # 2c. Tính tiền bằng số nguyên VND (không float)
            total_sum = 0
            needed = {}        # productId -> tổng số lượng cần (nhiều dòng giỏ có thể cùng sản phẩm)
            shop_payouts = {}  # shopId -> VND
            lines = []
            for ci in cart_items:
                p = products[ci['productId']]
                qty = int(ci['quantity'])
                cost = to_vnd(p['unitPrice']) * qty
                total_sum += cost
                needed[p['productId']] = needed.get(p['productId'], 0) + qty
                shop_payouts[p['shopId']] = shop_payouts.get(p['shopId'], 0) + cost
                lines.append((ci, p, qty))
            for pid, qty in needed.items():
                if products[pid]['inStock'] < qty:
                    raise ApiError(f"Insufficient stock for Product #{pid} during checkout race!", 'insufficient_stock', 400)

            # 3. Phương thức thanh toán của người mua
            if not payment_method_id:
                raise ApiError("Payment Method Required", 'payment_method_required', 400)
            is_cod = payment_method_id == 'CASH_ON_DELIVERY'

            seller_bank_ids = {}  # shopId -> paymentMethodId của người bán (nếu có)
            for shop_id in shop_payouts:
                shop = shops.get(shop_id)
                if not shop:
                    continue
                cursor.execute("SELECT id FROM paymentMethods WHERE userId=%s ORDER BY id LIMIT 1", (shop['sellerId'],))
                bank = cursor.fetchone()
                if bank:
                    seller_bank_ids[shop_id] = bank['id']

            # Khóa tất cả phương thức thanh toán liên quan trong MỘT câu, theo thứ tự id
            lock_ids = set(seller_bank_ids.values())
            if not is_cod:
                lock_ids.add(payment_method_id)
            pm_rows = {}
            if lock_ids:
                lock_ids = sorted(lock_ids, key=str)
                cursor.execute(f"SELECT id, userId, methodType, balance FROM paymentMethods "
                               f"WHERE id IN ({_placeholders(len(lock_ids))}) ORDER BY id FOR UPDATE", tuple(lock_ids))
                pm_rows = {r['id']: r for r in cursor.fetchall()}

            buyer_method_type = 'cash'
            charge_buyer = False
            if not is_cod:
                pm = pm_rows.get(payment_method_id)
                if not pm or pm['userId'] != user_id:
                    raise ApiError("Select payment method does not exist.", 'payment_method_not_found', 404)
                buyer_method_type = pm['methodType']
                if buyer_method_type != 'cash':
                    charge_buyer = True
                    buyer_balance = to_vnd(pm['balance'])
                    if buyer_balance < total_sum:
                        raise ApiError(f"Insufficient funds. You require {format_vnd(total_sum)} but your balance is only {format_vnd(buyer_balance)}!",
                                       'insufficient_funds', 400)
            order_payment_method_id = None if is_cod else payment_method_id  # COD: FK null, bỏ qua kiểm tra số dư

            # --- Ghi dữ liệu: mọi UPDATE đều có điều kiện bảo vệ, kiểm rowcount ---

            # A. Trừ tiền người mua (chỉ khi đủ số dư, cùng chủ)
            if charge_buyer:
                cursor.execute("UPDATE paymentMethods SET balance = balance - %s WHERE id=%s AND userId=%s AND balance >= %s",
                               (total_sum, payment_method_id, user_id, total_sum))
                if cursor.rowcount != 1:
                    raise ApiError("Insufficient funds.", 'insufficient_funds', 400)

            # Cộng tiền cho người bán CHỈ KHI người mua thực sự bị trừ tiền. COD và phương thức 'cash' không đi qua số dư
            # hệ thống (tiền mặt trao tay), nếu vẫn cộng cho người bán thì tạo ra tiền từ hư không (quyết định nhóm, S-04/S-05).
            credited_to = {}  # shopId -> paymentMethodId của người bán đã được cộng
            if charge_buyer:
                for shop_id, payout in shop_payouts.items():
                    bank_id = seller_bank_ids.get(shop_id)
                    if bank_id:
                        cursor.execute("UPDATE paymentMethods SET balance = balance + %s WHERE id=%s", (payout, bank_id))
                        credited_to[shop_id] = bank_id

            # B. Trừ tồn kho nguyên tử: UPDATE ... WHERE inStock >= qty
            for pid, qty in needed.items():
                cursor.execute("UPDATE products SET inStock = inStock - %s WHERE id=%s AND inStock >= %s", (qty, pid, qty))
                if cursor.rowcount != 1:
                    raise ApiError(f"Insufficient stock for Product #{pid} during checkout race!", 'insufficient_stock', 400)

            # C. Create Order + OrderLines
            order_id = str(uuid.uuid4())
            cursor.execute("INSERT INTO orders (id, userId, paymentMethodId, status, totalAmount) VALUES (%s, %s, %s, 'paid', %s)",
                           (order_id, user_id, order_payment_method_id, total_sum))

            for ci, p, qty in lines:
                shop = shops.get(p['shopId'], {})
                seller_pm = credited_to.get(p['shopId'])  # để hủy đơn có thể thu lại đúng khoản đã cộng
                cursor.execute("INSERT INTO orderLines (id, orderId, productId, unitPrice, quantity, snapshotProductName, snapshotShopName, selectedVariants, sellerPaymentMethodId, sellerCredit) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                               (str(uuid.uuid4()), order_id, p['productId'], p['unitPrice'], qty, p['name'], shop.get('shopName'), ci['selectedVariants'],
                                seller_pm, (to_vnd(p['unitPrice']) * qty) if seller_pm else 0))

            # D. Delete CartItems
            cursor.execute(f"DELETE FROM cartItems WHERE id IN ({_placeholders(len(cart_item_ids))})", tuple(cart_item_ids))

            conn.commit()
            return jsonify({"message": "Successfully completed. Receipt generated!"}), 200

    except ApiError:
        conn.rollback()
        raise
    except InvalidMoney as e:
        conn.rollback()
        raise ApiError(str(e), 'invalid_amount', 400)
    except pymysql.err.OperationalError as e:
        conn.rollback()
        if e.args and e.args[0] in (ER_LOCK_DEADLOCK, ER_LOCK_WAIT_TIMEOUT):
            raise ApiError("The store is busy. Please try again.", 'checkout_conflict', 409)
        raise
    except Exception:
        conn.rollback()
        raise  # -> handler chung: log chi tiết, client chỉ nhận 500 chung
    finally:
        conn.close()


def _settle_cancelled_paid_order(cursor, order_id, buyer_id):
    """Hủy đơn `paid` (S-05, quyết định nhóm): hoàn kho, hoàn tiền người mua và THU LẠI khoản đã cộng cho người bán.

    Không bao giờ tạo ra tiền: người mua chỉ được hoàn khi trước đó bị trừ tiền (phương thức không phải 'cash'),
    và khoản hoàn được thu lại từ đúng phương thức của người bán đã nhận (orderLines.sellerPaymentMethodId).
    Thứ tự khóa giống checkout: products -> paymentMethods (mỗi nhóm ORDER BY id) để không deadlock.
    Trả về số VND đã hoàn cho người mua.
    """
    cursor.execute("SELECT id, orderId, productId, quantity, sellerPaymentMethodId, sellerCredit FROM orderLines WHERE orderId=%s ORDER BY id",
                   (order_id,))
    lines = cursor.fetchall()

    restock = {}
    clawback = {}
    for ln in lines:
        if ln['productId']:  # sản phẩm đã bị xóa thì không còn kho để hoàn
            restock[ln['productId']] = restock.get(ln['productId'], 0) + int(ln['quantity'])
        credit = to_vnd(ln['sellerCredit'] or 0)
        if credit > 0 and ln['sellerPaymentMethodId']:  # tài khoản người bán đã xóa -> không còn gì để thu lại
            clawback[ln['sellerPaymentMethodId']] = clawback.get(ln['sellerPaymentMethodId'], 0) + credit

    if restock:
        pids = sorted(restock, key=str)
        cursor.execute(f"SELECT id FROM products WHERE id IN ({_placeholders(len(pids))}) ORDER BY id FOR UPDATE", tuple(pids))
        for pid in pids:
            cursor.execute("UPDATE products SET inStock = inStock + %s WHERE id=%s", (restock[pid], pid))

    cursor.execute("SELECT o.paymentMethodId, o.totalAmount, pm.methodType FROM orders o "
                   "LEFT JOIN paymentMethods pm ON pm.id = o.paymentMethodId WHERE o.id=%s", (order_id,))
    head = cursor.fetchone()
    refund = 0
    buyer_pm = None
    if head and head['paymentMethodId'] and head['methodType'] and head['methodType'] != 'cash':
        buyer_pm = head['paymentMethodId']
        refund = to_vnd(head['totalAmount'])

    lock_ids = sorted(set(clawback) | ({buyer_pm} if buyer_pm else set()), key=str)
    if lock_ids:
        cursor.execute(f"SELECT id FROM paymentMethods WHERE id IN ({_placeholders(len(lock_ids))}) ORDER BY id FOR UPDATE", tuple(lock_ids))

    for pm_id in sorted(clawback, key=str):
        cursor.execute("UPDATE paymentMethods SET balance = balance - %s WHERE id=%s AND balance >= %s",
                       (clawback[pm_id], pm_id, clawback[pm_id]))
        if cursor.rowcount != 1:
            raise ApiError("The seller cannot cover this refund right now. Please contact support.", 'refund_unavailable', 409)

    if refund:
        cursor.execute("UPDATE paymentMethods SET balance = balance + %s WHERE id=%s AND userId=%s", (refund, buyer_pm, buyer_id))
    return refund


@payments_bp.route('/orders/<order_id>', methods=['PUT'])
@require_auth
def update_order_status(order_id):
    data = json_body()
    new_status = data.get('status')
    if not isinstance(new_status, str) or new_status not in ORDER_TRANSITIONS:
        return jsonify({"error": "Invalid order status transformation."}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # P0-03 (S-05): chỉ chủ đơn; đơn của người khác trả 404 như thể không tồn tại. Khóa dòng để kiểm trạng thái an toàn.
            cursor.execute("SELECT id, status FROM orders WHERE id=%s AND userId=%s FOR UPDATE", (order_id, g.user_id))
            order = cursor.fetchone()
            if not order:
                raise ApiError("Order not found.", 'not_found', 404)

            # SRS 5.1: đơn Web3 chỉ được đổi trạng thái bởi hàm đồng bộ của Indexer
            if is_web3_order(cursor, order_id):
                raise ApiError("This order is managed by the escrow contract and cannot be changed here.",
                               'WEB3_ORDER_MANAGED', 409)

            if order['status'] not in ORDER_TRANSITIONS[new_status]:
                raise ApiError(f"Cannot change an order from '{order['status']}' to '{new_status}'.", 'INVALID_STATE', 409)

            cursor.execute("UPDATE orders SET status=%s WHERE id=%s AND userId=%s AND status=%s",
                           (new_status, order_id, g.user_id, order['status']))
            if cursor.rowcount != 1:
                raise ApiError("Order was modified by another request. Please reload.", 'INVALID_STATE', 409)

            refunded = 0
            if new_status == 'cancelled' and order['status'] == 'paid':
                refunded = _settle_cancelled_paid_order(cursor, order_id, g.user_id)  # hoàn kho + hoàn tiền (S-05)
            conn.commit()
            return jsonify({"message": f"Order status successfully changed to {new_status}!", "refunded": refunded}), 200
    except ApiError:
        conn.rollback()
        raise
    finally:
        conn.close()


WEB3_SUMMARY_COLUMNS = (
    "order_id, onchain_order_id, checkout_group_id, buyer_wallet, status, chain_created_at, delivered_at, inspection_duration, disputed_at, "
    "dispute_timeout, fee_bps, amount_raw, token_symbol, anomaly_flag"
)


def _web3_summaries(cursor, order_ids):
    """{order_id: tóm tắt Web3} cho các đơn có dòng order_web3 (SRS 5.1: LEFT JOIN trong GET /orders).

    Đơn không có dòng order_web3 là đơn cũ (không xuất hiện trong kết quả). DB chưa áp migration Web3 (bảng chưa tồn tại,
    lỗi 1146) thì coi như không có đơn Web3 nào, giống guards.is_web3_order. Trạng thái ở đây do Indexer ghi (BR-09);
    giao diện dùng nó để biết đơn nào là Web3 và cần onchain_order_id nào để gọi contract.
    """
    if not order_ids:
        return {}
    try:
        cursor.execute(
            f"SELECT {WEB3_SUMMARY_COLUMNS} FROM order_web3 WHERE order_id IN ({_placeholders(len(order_ids))})",
            tuple(order_ids))
    except pymysql.err.ProgrammingError as e:
        if e.args and e.args[0] == ER_NO_SUCH_TABLE:
            return {}
        raise

    def opt(v):
        return None if v is None else int(v)
    out = {}
    for r in cursor.fetchall():
        out[r['order_id']] = {
            'onchain_order_id': int(r['onchain_order_id']),
            'checkout_group_id': r['checkout_group_id'],
            'buyer_wallet': r['buyer_wallet'],      # ví đã ký quỹ: chỉ ví này gọi được earlyRelease/raiseDispute (giao diện kiểm trước khi bật ví)
            'status': r['status'],
            'chain_created_at': opt(r['chain_created_at']),   # giây UTC theo block lúc ký quỹ: Buyer hủy được khi now_chain >= mốc này + 14 ngày (cancelIfUnfulfilled)
            'delivered_at': opt(r['delivered_at']),
            'inspection_duration': int(r['inspection_duration']),
            'disputed_at': opt(r['disputed_at']),
            'dispute_timeout': int(r['dispute_timeout']),
            'fee_bps': int(r['fee_bps']),
            'amount_raw': str(r['amount_raw']),
            'token_symbol': r['token_symbol'],
            'anomaly': bool(r['anomaly_flag']),
        }
    return out


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
                
            # Đơn Web3: thêm `web3` (null với đơn cũ) để giao diện khóa nút cũ, hiện đồng hồ kiểm tra và gọi đúng đơn on-chain
            web3 = _web3_summaries(cursor, list(orders_map))
            for o_id, order in orders_map.items():
                order["web3"] = web3.get(o_id)
            return jsonify({"orders": list(orders_map.values())}), 200
            
    finally:
        conn.close()
