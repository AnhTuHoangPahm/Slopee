"""Repositories qua SQL tham số hóa (SDD 5.2, 7.5). Không nối chuỗi giá trị; chỉ nối danh sách dấu %s.

Quy ước: `amount_raw` lưu VARCHAR(78) và đọc ra `int`; `fx_vnd_per_token` DECIMAL(18,4) <-> `fx_scaled` (số nguyên x10^4).
Mọi chuyển trạng thái order_web3 dùng UPDATE có điều kiện trạng thái cũ (SDD 7.5).
"""
import json
from decimal import Decimal

import pymysql

from ..domain.order_state import is_valid_transition, to_legacy_status
from ..domain.policy import Policy
from ..domain.reconcile import OPEN_STATES, token_key
from ..domain.release import DELIVERY_TIMEOUT_SECONDS
from ..ports.repositories import DuplicateWallet
from .legacy_sync import sync_legacy_status

ER_DUP_ENTRY = 1062


def _marks(n):
    return ','.join(['%s'] * n)


def _fx_scaled(value):
    return int((Decimal(value) * 10 ** 4).to_integral_value())


class MySqlWalletRepo:
    def __init__(self, cur):
        self.cur = cur

    def active_wallet(self, user_id):
        self.cur.execute("SELECT address, UNIX_TIMESTAMP(linked_at) AS linked_at FROM user_wallets "
                         "WHERE user_id=%s AND is_active=1 LIMIT 1", (user_id,))
        row = self.cur.fetchone()
        return {'address': row['address'], 'linked_at': int(row['linked_at'])} if row else None

    def active_wallets(self, user_ids):
        user_ids = list(dict.fromkeys(user_ids))
        if not user_ids:
            return {}
        self.cur.execute(f"SELECT user_id, address FROM user_wallets WHERE is_active=1 AND user_id IN ({_marks(len(user_ids))})",
                         tuple(user_ids))
        return {r['user_id']: r['address'] for r in self.cur.fetchall()}

    def count_recent_nonces(self, user_id, within_seconds, ttl):
        # nonce cấp trong `within_seconds` gần nhất <=> expires_at > NOW() + (ttl - within_seconds)
        self.cur.execute("SELECT COUNT(*) AS c FROM wallet_nonces WHERE user_id=%s AND expires_at > NOW() + INTERVAL %s SECOND",
                         (user_id, ttl - within_seconds))
        return int(self.cur.fetchone()['c'])

    def insert_nonce(self, nonce, user_id, ttl):
        self.cur.execute("INSERT INTO wallet_nonces (nonce, user_id, expires_at) VALUES (%s, %s, NOW() + INTERVAL %s SECOND)",
                         (nonce, user_id, ttl))
        self.cur.execute("SELECT UNIX_TIMESTAMP(expires_at) AS e FROM wallet_nonces WHERE nonce=%s", (nonce,))
        return int(self.cur.fetchone()['e'])

    def find_nonce(self, user_id, nonce):
        if nonce is not None:
            self.cur.execute("SELECT nonce, UNIX_TIMESTAMP(expires_at) AS e FROM wallet_nonces "
                             "WHERE nonce=%s AND user_id=%s AND used_at IS NULL AND expires_at > NOW()", (nonce, user_id))
        else:   # không gửi nonce: dùng nonce còn hạn mới nhất của chính tài khoản
            self.cur.execute("SELECT nonce, UNIX_TIMESTAMP(expires_at) AS e FROM wallet_nonces "
                             "WHERE user_id=%s AND used_at IS NULL AND expires_at > NOW() ORDER BY expires_at DESC LIMIT 1",
                             (user_id,))
        row = self.cur.fetchone()
        return {'nonce': row['nonce'], 'expires_at': int(row['e'])} if row else None

    def consume_nonce(self, nonce, user_id):
        # Nguyên tử (SDD 5.3g): hai yêu cầu song song chỉ một cái thấy rowcount = 1.
        self.cur.execute("UPDATE wallet_nonces SET used_at = NOW() WHERE nonce=%s AND user_id=%s "
                         "AND used_at IS NULL AND expires_at > NOW()", (nonce, user_id))
        return self.cur.rowcount == 1

    def wallet_by_address(self, address):
        # Đọc KHÔNG khóa: FOR UPDATE trên dòng chưa tồn tại tạo gap lock làm hai INSERT song song deadlock.
        # Đua giữa hai tài khoản được UNIQUE(address) phân xử (DuplicateWallet); đua cùng tài khoản do consume_nonce phân xử.
        self.cur.execute("SELECT id, user_id, is_active, UNIX_TIMESTAMP(linked_at) AS linked_at FROM user_wallets "
                         "WHERE address=%s", (address,))
        row = self.cur.fetchone()
        if not row:
            return None
        return {'id': row['id'], 'user_id': row['user_id'], 'is_active': bool(row['is_active']),
                'linked_at': int(row['linked_at'])}

    def deactivate_user_wallets(self, user_id):
        self.cur.execute("UPDATE user_wallets SET is_active=0 WHERE user_id=%s AND is_active=1", (user_id,))

    def activate_wallet(self, wallet_id):
        self.cur.execute("UPDATE user_wallets SET is_active=1 WHERE id=%s", (wallet_id,))

    def insert_wallet(self, user_id, address):
        try:
            self.cur.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s, %s, 1)", (user_id, address))
        except pymysql.err.IntegrityError as e:
            if e.args and e.args[0] == ER_DUP_ENTRY:
                raise DuplicateWallet()
            raise
        self.cur.execute("SELECT UNIX_TIMESTAMP(linked_at) AS t FROM user_wallets WHERE address=%s", (address,))
        return int(self.cur.fetchone()['t'])


class MySqlSettingsRepo:
    def __init__(self, cur):
        self.cur = cur

    def get_many(self, keys):
        if not keys:
            return {}
        self.cur.execute(f"SELECT setting_key, setting_value FROM platform_settings WHERE setting_key IN ({_marks(len(keys))})",
                         tuple(keys))
        return {r['setting_key']: r['setting_value'] for r in self.cur.fetchall()}


class MySqlPolicyRepo:
    def __init__(self, cur):
        self.cur = cur

    def policies_for_categories(self, category_ids):
        """{category_id: Policy}. Danh mục chưa ánh xạ dùng nhóm is_default = 1; chưa có nhóm mặc định -> None."""
        self.cur.execute("SELECT policy_code, inspection_duration, dispute_timeout FROM category_policies "
                         "WHERE is_default=1 ORDER BY policy_code LIMIT 1")
        d = self.cur.fetchone()
        default = Policy(d['policy_code'], int(d['inspection_duration']), int(d['dispute_timeout'])) if d else None
        mapped = {}
        if category_ids:
            self.cur.execute(
                "SELECT m.category_id, p.policy_code, p.inspection_duration, p.dispute_timeout "
                "FROM category_policy_map m JOIN category_policies p ON p.policy_code = m.policy_code "
                f"WHERE m.category_id IN ({_marks(len(category_ids))})", tuple(category_ids))
            for r in self.cur.fetchall():
                mapped[int(r['category_id'])] = Policy(r['policy_code'], int(r['inspection_duration']), int(r['dispute_timeout']))
        out = {}
        for cid in category_ids:
            p = mapped.get(int(cid), default)
            if p is None:
                return None
            out[cid] = p
        return out


class MySqlCheckoutRepo:
    def __init__(self, cur):
        self.cur = cur

    # ---- đọc + khóa (thứ tự cartItems -> products giống checkout cũ, P0-05)
    def lock_cart_lines(self, user_id, cart_item_ids, lock=True):
        """lock=False: đọc thuần (kiểm tra điều kiện hiển thị), không giữ khóa dòng nào."""
        self.cur.execute(
            "SELECT ci.id AS cartItemId, ci.productId, ci.quantity, ci.selectedVariants FROM cartItems ci "
            f"WHERE ci.id IN ({_marks(len(cart_item_ids))}) AND ci.cartId IN (SELECT id FROM carts WHERE userId=%s) "
            "ORDER BY ci.id" + (" FOR UPDATE" if lock else ""), (*cart_item_ids, user_id))
        return list(self.cur.fetchall())

    def lock_products(self, product_ids, lock=True):
        if not product_ids:
            return {}
        self.cur.execute(
            "SELECT id, name, unitPrice, inStock, isActive, categoryId, shopId FROM products "
            f"WHERE id IN ({_marks(len(product_ids))}) ORDER BY id" + (" FOR UPDATE" if lock else ""), tuple(product_ids))
        return {r['id']: {'name': r['name'], 'unitPrice': int(r['unitPrice']), 'inStock': int(r['inStock']),
                          'isActive': bool(r['isActive']), 'categoryId': int(r['categoryId']), 'shopId': r['shopId']}
                for r in self.cur.fetchall()}

    def get_shops(self, shop_ids):
        self.cur.execute(f"SELECT id, sellerId, name FROM shops WHERE id IN ({_marks(len(shop_ids))})", tuple(shop_ids))
        return {r['id']: {'sellerId': r['sellerId'], 'name': r['name']} for r in self.cur.fetchall()}

    def pending_group_for_products(self, user_id, product_ids):
        # Đọc thường (không khóa => không có khóa khoảng, không deadlock). Đúng đắn nhờ THỨ TỰ trong QuoteService:
        # lock_cart_lines/lock_products (đọc khóa) chạy TRƯỚC mọi đọc thường, mà InnoDB chỉ tạo snapshot ở lần đọc
        # thường đầu tiên => giao dịch đến sau chờ khóa xong mới có snapshot, nên thấy lô vừa được commit.
        self.cur.execute(
            "SELECT w.checkout_group_id FROM order_web3 w JOIN orderLines ol ON ol.orderId = w.order_id "
            f"WHERE w.buyer_user_id=%s AND w.status='PENDING_PAYMENT' AND ol.productId IN ({_marks(len(product_ids))}) "
            "LIMIT 1", (user_id, *product_ids))
        row = self.cur.fetchone()
        return row['checkout_group_id'] if row else None

    # ---- ghi
    def next_onchain_id(self):
        self.cur.execute("INSERT INTO onchain_id_seq () VALUES ()")
        return int(self.cur.lastrowid)       # đơn điệu, không dùng lại, < 2^53 (CHECK ở order_web3)

    def insert_group(self, group_id, buyer_user_id, token_address, total_amount_raw, order_count):
        self.cur.execute("INSERT INTO checkout_groups (group_id, buyer_user_id, token_address, total_amount_raw, order_count) "
                         "VALUES (%s, %s, %s, %s, %s)", (group_id, buyer_user_id, token_address, total_amount_raw, order_count))

    def insert_order(self, order_id, user_id, total_vnd, created_at):
        self.cur.execute("INSERT INTO orders (id, userId, status, totalAmount, created_at) "
                         "VALUES (%s, %s, 'pending', %s, FROM_UNIXTIME(%s))", (order_id, user_id, total_vnd, created_at))

    def insert_order_lines(self, order_id, lines):
        import uuid
        for ln in lines:
            self.cur.execute(
                "INSERT INTO orderLines (id, orderId, productId, selectedVariants, unitPrice, quantity, "
                "snapshotProductName, snapshotShopName) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (str(uuid.uuid4()), order_id, ln['productId'], ln['selectedVariants'], ln['unitPrice'], ln['quantity'],
                 ln['snapshotProductName'], ln['snapshotShopName']))

    def reserve_stock(self, product_id, quantity):
        self.cur.execute("UPDATE products SET inStock = inStock - %s WHERE id=%s AND inStock >= %s",
                         (quantity, product_id, quantity))
        return self.cur.rowcount == 1

    def release_stock(self, product_id, quantity):
        self.cur.execute("UPDATE products SET inStock = inStock + %s WHERE id=%s", (quantity, product_id))

    def insert_order_web3(self, r):
        self.cur.execute(
            "INSERT INTO order_web3 (order_id, onchain_order_id, buyer_user_id, merchant_user_id, shop_id, checkout_group_id, "
            "buyer_wallet, merchant_wallet, token_address, token_symbol, amount_raw, price_vnd, fx_vnd_per_token, "
            "status, policy_code, fee_bps, inspection_duration, dispute_timeout, doc_hash) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING_PAYMENT',%s,%s,%s,%s,%s)",
            (r['order_id'], r['onchain_order_id'], r['buyer_user_id'], r['merchant_user_id'], r['shop_id'],
             r['checkout_group_id'], r['buyer_wallet'], r['merchant_wallet'], r['token_address'], r['token_symbol'],
             r['amount_raw'], r['price_vnd'], Decimal(r['fx_scaled']) / 10 ** 4, r['policy_code'], r['fee_bps'],
             r['inspection_duration'], r['dispute_timeout'], r['doc_hash']))

    def insert_quote(self, order_id, quote_json, signature, deadline):
        self.cur.execute("INSERT INTO order_quotes (order_id, quote_json, signature, deadline) VALUES (%s, %s, %s, %s)",
                         (order_id, json.dumps(quote_json), signature, deadline))

    # ---- lô / cấp lại báo giá
    def get_group(self, group_id, buyer_user_id):
        self.cur.execute("SELECT group_id, total_amount_raw, order_count FROM checkout_groups "
                         "WHERE group_id=%s AND buyer_user_id=%s", (group_id, buyer_user_id))
        row = self.cur.fetchone()
        return {'group_id': row['group_id'], 'total_amount_raw': row['total_amount_raw'],
                'order_count': int(row['order_count'])} if row else None

    def group_orders(self, group_id, lock=False):
        self.cur.execute(
            "SELECT w.order_id, w.onchain_order_id, w.merchant_user_id, w.shop_id, s.name AS shop_name, w.status, "
            "w.amount_raw, w.price_vnd, w.fx_vnd_per_token, w.fee_bps, w.inspection_duration, w.dispute_timeout, "
            "w.doc_hash, w.policy_code, w.deposit_tx_hash FROM order_web3 w LEFT JOIN shops s ON s.id = w.shop_id "
            "WHERE w.checkout_group_id=%s ORDER BY w.onchain_order_id" + (" FOR UPDATE OF w" if lock else ""), (group_id,))
        out = []
        for r in self.cur.fetchall():
            r = dict(r)
            r['amount_raw'] = int(r['amount_raw'])
            r['price_vnd'] = int(r['price_vnd'])
            out.append(r)
        return out

    def order_lines(self, order_id):
        self.cur.execute("SELECT productId, quantity FROM orderLines WHERE orderId=%s", (order_id,))
        return list(self.cur.fetchall())

    def update_order_requote(self, order_id, f):
        # Chỉ ghi khi trạng thái hiện tại cho phép chuyển sang trạng thái mới (SDD 7.5). Dòng đã bị khóa FOR UPDATE
        # từ group_orders(lock=True) nên không ai đổi được giữa SELECT và UPDATE. KHÔNG kiểm rowcount: MySQL trả 0 khi
        # UPDATE không làm đổi giá trị nào (ví dụ cấp lại báo giá với cùng tỷ giá/phí), đó không phải lỗi.
        self.cur.execute("SELECT status FROM order_web3 WHERE order_id=%s FOR UPDATE", (order_id,))
        old = self.cur.fetchone()['status']
        if old != f['status'] and not is_valid_transition(old, f['status']):
            raise RuntimeError(f'Chuyển trạng thái không hợp lệ {old} -> {f["status"]}')
        self.cur.execute(
            "UPDATE order_web3 SET status=%s, amount_raw=%s, fx_vnd_per_token=%s, fee_bps=%s, buyer_wallet=%s, "
            "merchant_wallet=%s WHERE order_id=%s AND status=%s",
            (f['status'], f['amount_raw'], Decimal(f['fx_scaled']) / 10 ** 4, f['fee_bps'], f['buyer_wallet'],
             f['merchant_wallet'], order_id, old))
        # Đồng bộ ngược orders.status trong cùng giao dịch (SDD 7.4)
        self.cur.execute("UPDATE orders SET status=%s WHERE id=%s", (to_legacy_status(f['status']), order_id))

    def update_group_total(self, group_id, total_amount_raw):
        self.cur.execute("UPDATE checkout_groups SET total_amount_raw=%s WHERE group_id=%s", (total_amount_raw, group_id))

    def latest_quote(self, order_id):
        self.cur.execute("SELECT deadline FROM order_quotes WHERE order_id=%s ORDER BY id DESC LIMIT 1", (order_id,))
        row = self.cur.fetchone()
        return {'deadline': int(row['deadline'])} if row else None

    def order_status_row(self, order_id):
        self.cur.execute(
            "SELECT order_id, buyer_user_id, merchant_user_id, status, delivered_at, inspection_duration, disputed_at, "
            "dispute_timeout, anomaly_flag FROM order_web3 WHERE order_id=%s", (order_id,))
        return self.cur.fetchone()


# ------------------------------------------------------------------ dùng chung cho Repo và Indexer (đều chỉ cần con trỏ)
def add_notification(cur, user_id, order_id, kind, message):
    """Idempotent nhờ UNIQUE(user_id, order_id, kind): True nếu vừa tạo, False nếu đã có. Dùng được trong giao dịch của Indexer."""
    cur.execute("INSERT IGNORE INTO notifications (user_id, order_id, kind, message) VALUES (%s, %s, %s, %s)",
                (user_id, order_id, kind, message))
    return cur.rowcount == 1


def _order_stock_lines(cur, order_id):
    """Số lượng theo sản phẩm của đơn, SẮP THEO productId: mọi nơi đổi tồn kho nhiều sản phẩm phải theo cùng thứ tự để không deadlock."""
    cur.execute("SELECT productId, SUM(quantity) AS q FROM orderLines WHERE orderId=%s AND productId IS NOT NULL "
                "GROUP BY productId ORDER BY productId", (order_id,))
    return [(r['productId'], int(r['q'])) for r in cur.fetchall()]


def release_order_stock(cur, order_id):
    """Hoàn tồn kho của đơn Web3 khi EXPIRED/REFUNDED (SDD 7.4). Sản phẩm đã bị xóa (productId NULL) thì bỏ qua."""
    for product_id, qty in _order_stock_lines(cur, order_id):
        cur.execute("UPDATE products SET inStock = inStock + %s WHERE id=%s", (qty, product_id))


def reserve_order_stock(cur, order_id):
    """Giữ lại tồn kho khi một đơn REFUNDED bị reorg đưa về PENDING_PAYMENT (đối xứng với release_order_stock).
    Trả False nếu hàng đã bán hết trong lúc đó (không trừ âm; người gọi ghi log cảnh báo)."""
    ok = True
    for product_id, qty in _order_stock_lines(cur, order_id):
        cur.execute("UPDATE products SET inStock = inStock - %s WHERE id=%s AND inStock >= %s", (qty, product_id, qty))
        ok = ok and cur.rowcount == 1
    return ok


class MySqlShipperRepo:
    def __init__(self, cur):
        self.cur = cur

    def get_user(self, user_id):
        self.cur.execute("SELECT id, role, name FROM users WHERE id=%s", (user_id,))
        return self.cur.fetchone()

    def assigned_orders(self, shipper_user_id, statuses):
        if not statuses:
            return []
        self.cur.execute(
            "SELECT w.order_id, w.onchain_order_id, w.status, w.amount_raw, w.token_symbol, w.price_vnd, "
            "w.inspection_duration, w.chain_created_at, w.delivered_at, s.name AS shop_name, bu.name AS buyer_name, "
            "UNIX_TIMESTAMP(sa.assigned_at) AS assigned_at "
            "FROM shipper_assignments sa JOIN order_web3 w ON w.order_id = sa.order_id "
            "LEFT JOIN shops s ON s.id = w.shop_id LEFT JOIN users bu ON bu.id = w.buyer_user_id "
            f"WHERE sa.shipper_user_id=%s AND w.status IN ({_marks(len(statuses))}) "
            "ORDER BY sa.assigned_at, w.onchain_order_id", (shipper_user_id, *statuses))
        rows = list(self.cur.fetchall())
        items = self._items([r['order_id'] for r in rows])
        for r in rows:
            r['items'] = items.get(r['order_id'], [])
        return rows

    def _items(self, order_ids):
        if not order_ids:
            return {}
        self.cur.execute("SELECT orderId, snapshotProductName AS name, quantity, selectedVariants FROM orderLines "
                         f"WHERE orderId IN ({_marks(len(order_ids))}) ORDER BY orderId, id", tuple(order_ids))
        out = {}
        for r in self.cur.fetchall():
            out.setdefault(r['orderId'], []).append(
                {'name': r['name'], 'quantity': int(r['quantity']), 'variants': r['selectedVariants']})
        return out

    def assigned_order(self, order_id, shipper_user_id, lock=False):
        self.cur.execute(
            "SELECT w.order_id, w.onchain_order_id, w.status FROM shipper_assignments sa "
            "JOIN order_web3 w ON w.order_id = sa.order_id WHERE sa.order_id=%s AND sa.shipper_user_id=%s"
            + (" FOR UPDATE OF w" if lock else ""), (order_id, shipper_user_id))
        return self.cur.fetchone()

    def order_for_assignment(self, order_id, lock=False):
        self.cur.execute("SELECT order_id, onchain_order_id, status FROM order_web3 WHERE order_id=%s"
                         + (" FOR UPDATE" if lock else ""), (order_id,))
        return self.cur.fetchone()

    def assign(self, order_id, shipper_user_id, assigned_by):
        self.cur.execute(
            "INSERT INTO shipper_assignments (order_id, shipper_user_id, assigned_by) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE shipper_user_id=VALUES(shipper_user_id), assigned_by=VALUES(assigned_by), "
            "assigned_at=CURRENT_TIMESTAMP", (order_id, shipper_user_id, assigned_by))


class MySqlOutboxRepo:
    """tx_outbox (SDD 012): chỉ ghi vết giao dịch relayer. Chuyển trạng thái có điều kiện trạng thái cũ (SDD 7.5)."""
    MAX_ERROR = 2000

    def __init__(self, cur):
        self.cur = cur

    def insert(self, kind, order_id):
        self.cur.execute("INSERT INTO tx_outbox (kind, order_id, status) VALUES (%s, %s, 'PENDING')", (kind, order_id))
        return int(self.cur.lastrowid)

    def mark_sent(self, outbox_id, tx_hash):
        self.cur.execute("UPDATE tx_outbox SET status='SENT', tx_hash=%s WHERE id=%s AND status='PENDING'", (tx_hash, outbox_id))

    def mark_confirmed(self, outbox_id):
        self.cur.execute("UPDATE tx_outbox SET status='CONFIRMED' WHERE id=%s AND status='SENT'", (outbox_id,))

    def mark_failed(self, outbox_id, error):
        self.cur.execute("UPDATE tx_outbox SET status='FAILED', error=%s WHERE id=%s AND status IN ('PENDING','SENT')",
                         (str(error)[:self.MAX_ERROR], outbox_id))

    def recent_for_order(self, order_id, limit=20):
        self.cur.execute("SELECT id, kind, tx_hash, status, error, UNIX_TIMESTAMP(created_at) AS created_at "
                         "FROM tx_outbox WHERE order_id=%s ORDER BY id DESC LIMIT %s", (order_id, int(limit)))
        return list(self.cur.fetchall())


class MySqlNotificationRepo:
    def __init__(self, cur):
        self.cur = cur

    def add(self, user_id, order_id, kind, message):
        return add_notification(self.cur, user_id, order_id, kind, message)

    def list_for_user(self, user_id, limit):
        self.cur.execute("SELECT id, order_id, kind, message, UNIX_TIMESTAMP(created_at) AS created_at, "
                         "(read_at IS NOT NULL) AS is_read FROM notifications WHERE user_id=%s ORDER BY id DESC LIMIT %s",
                         (user_id, int(limit)))
        return [{'id': int(r['id']), 'order_id': r['order_id'], 'kind': r['kind'], 'message': r['message'],
                 'created_at': int(r['created_at']), 'read': bool(r['is_read'])} for r in self.cur.fetchall()]


class MySqlJobsRepo:
    def __init__(self, cur):
        self.cur = cur

    def expired_quote_candidates(self, now, grace, limit):
        """Lô có ít nhất một đơn PENDING_PAYMENT mà báo giá MỚI NHẤT đã quá hạn thêm `grace` giây. Chỉ để chọn ứng viên;
        QuoteExpirySweeper kiểm lại từng đơn SAU KHI khóa (đọc này không khóa)."""
        self.cur.execute(
            "SELECT DISTINCT w.checkout_group_id AS group_id FROM order_web3 w "
            "JOIN order_quotes q ON q.id = (SELECT MAX(q2.id) FROM order_quotes q2 WHERE q2.order_id = w.order_id) "
            "WHERE w.status='PENDING_PAYMENT' AND q.deadline < %s ORDER BY w.checkout_group_id LIMIT %s",
            (int(now) - int(grace), int(limit)))
        return [r['group_id'] for r in self.cur.fetchall()]

    def lock_group_orders(self, group_id):
        self.cur.execute(
            "SELECT w.order_id, w.onchain_order_id, w.status, "
            "(SELECT q.deadline FROM order_quotes q WHERE q.order_id = w.order_id ORDER BY q.id DESC LIMIT 1) AS deadline "
            "FROM order_web3 w WHERE w.checkout_group_id=%s ORDER BY w.onchain_order_id FOR UPDATE", (group_id,))
        rows = list(self.cur.fetchall())
        for r in rows:
            r['deadline'] = None if r['deadline'] is None else int(r['deadline'])
        return rows

    def expire_order(self, order_id):
        """PENDING_PAYMENT -> EXPIRED (có điều kiện trạng thái, SDD 7.5), đồng bộ `orders` cũ và hoàn tồn kho cùng giao dịch."""
        self.cur.execute("UPDATE order_web3 SET status='EXPIRED' WHERE order_id=%s AND status='PENDING_PAYMENT'", (order_id,))
        if self.cur.rowcount != 1:
            return False
        sync_legacy_status(self.cur, order_id, 'EXPIRED')
        release_order_stock(self.cur, order_id)
        return True

    def delivered_due(self, now, limit):
        self.cur.execute(
            "SELECT order_id, onchain_order_id, delivered_at, inspection_duration FROM order_web3 "
            "WHERE status='DELIVERED' AND delivered_at IS NOT NULL AND delivered_at + inspection_duration <= %s "
            "ORDER BY delivered_at + inspection_duration, onchain_order_id LIMIT %s", (int(now), int(limit)))
        return list(self.cur.fetchall())

    def locked_past_delivery_timeout(self, now, limit):
        self.cur.execute(
            "SELECT w.order_id, w.onchain_order_id, w.buyer_user_id, w.chain_created_at FROM order_web3 w "
            "WHERE w.status='LOCKED' AND w.chain_created_at IS NOT NULL AND w.chain_created_at + %s <= %s "
            "AND NOT EXISTS (SELECT 1 FROM notifications n WHERE n.user_id = w.buyer_user_id AND n.order_id = w.order_id "
            "AND n.kind='DELIVERY_TIMEOUT') ORDER BY w.chain_created_at, w.onchain_order_id LIMIT %s",
            (DELIVERY_TIMEOUT_SECONDS, int(now), int(limit)))
        return list(self.cur.fetchall())


class MySqlReconcileRepo:
    def __init__(self, cur):
        self.cur = cur

    def indexer_cursor(self):
        self.cur.execute("SELECT last_block, last_block_hash FROM indexer_cursor WHERE name='escrow'")
        row = self.cur.fetchone()
        return {'last_block': int(row['last_block']), 'last_block_hash': row['last_block_hash']} if row else None

    def open_totals(self):
        """Σ amount_raw theo token của đơn đang mở. Cộng bằng int Python (amount_raw là VARCHAR(78), không bao giờ float)."""
        self.cur.execute(f"SELECT token_address, amount_raw FROM order_web3 WHERE status IN ({_marks(len(OPEN_STATES))})",
                         OPEN_STATES)
        totals = {}
        for r in self.cur.fetchall():
            t = totals.setdefault(token_key(r['token_address']), {'token': token_key(r['token_address']), 'orders': 0, 'amount_raw': 0})
            t['orders'] += 1
            t['amount_raw'] += int(r['amount_raw'])
        return list(totals.values())

    def pending_totals(self):
        self.cur.execute("SELECT token_address, amount_raw FROM pending_balances")
        totals = {}
        for r in self.cur.fetchall():
            t = totals.setdefault(token_key(r['token_address']), {'token': token_key(r['token_address']), 'amount_raw': 0})
            t['amount_raw'] += int(r['amount_raw'])
        return list(totals.values())

    def anomaly_orders(self):
        self.cur.execute("SELECT order_id, onchain_order_id, status FROM order_web3 WHERE anomaly_flag=1 "
                         "ORDER BY onchain_order_id LIMIT 100")
        return [{'order_id': r['order_id'], 'onchain_order_id': int(r['onchain_order_id']), 'status': r['status']}
                for r in self.cur.fetchall()]

    def open_orders(self, limit):
        self.cur.execute(f"SELECT order_id, onchain_order_id, status FROM order_web3 WHERE status IN ({_marks(len(OPEN_STATES))}) "
                         "ORDER BY onchain_order_id LIMIT %s", (*OPEN_STATES, int(limit)))
        return [{'order_id': r['order_id'], 'onchain_order_id': int(r['onchain_order_id']), 'status': r['status']}
                for r in self.cur.fetchall()]


class MySqlDisputeNoteRepo:
    def __init__(self, cur):
        self.cur = cur

    def order_for_note(self, order_id, lock=False):
        self.cur.execute("SELECT order_id, buyer_user_id, status FROM order_web3 WHERE order_id=%s"
                         + (" FOR UPDATE" if lock else ""), (order_id,))
        return self.cur.fetchone()

    def has_resolution(self, order_id):
        self.cur.execute("SELECT 1 AS x FROM dispute_resolutions WHERE order_id=%s LIMIT 1", (order_id,))
        return self.cur.fetchone() is not None

    def upsert(self, order_id, buyer_user_id, reason, evidence_url):
        """INSERT ... ON DUPLICATE KEY UPDATE: rowcount 1 = tạo mới, 2 = ghi đè, 0 = y hệt bản cũ (gửi lại không đổi gì)."""
        self.cur.execute(
            "INSERT INTO dispute_notes (order_id, buyer_user_id, reason, evidence_url) VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE reason=VALUES(reason), evidence_url=VALUES(evidence_url)",
            (order_id, buyer_user_id, reason, evidence_url))
        return self.cur.rowcount == 1

    def get(self, order_id):
        self.cur.execute("SELECT order_id, buyer_user_id, reason, evidence_url, UNIX_TIMESTAMP(created_at) AS created_at, "
                         "UNIX_TIMESTAMP(updated_at) AS updated_at FROM dispute_notes WHERE order_id=%s", (order_id,))
        return self.cur.fetchone()


class MySqlDisputeRepo:
    """dispute_resolutions + dispute_signatures (Tuần 6, A: phần đọc/nộp). Số token đọc ra `int`; mốc thời gian là giây UTC."""

    def __init__(self, cur):
        self.cur = cur

    def order_for_dispute(self, order_id, lock=False):
        self.cur.execute(
            "SELECT order_id, onchain_order_id, buyer_user_id, merchant_user_id, buyer_wallet, merchant_wallet, status, "
            "amount_raw, disputed_at, dispute_timeout FROM order_web3 WHERE order_id=%s" + (" FOR UPDATE" if lock else ""),
            (order_id,))
        return self.cur.fetchone()

    @staticmethod
    def _resolution(r):
        r = dict(r)
        r['amount_raw'] = int(r['amount_raw'])
        r['nonce'], r['deadline'] = int(r['nonce']), int(r['deadline'])
        return r

    def latest_resolution(self, order_id, lock=False):
        self.cur.execute(
            "SELECT id, order_id, payout_to, amount_raw, nonce, deadline, status, reason_note, submitted_tx_hash "
            "FROM dispute_resolutions WHERE order_id=%s ORDER BY id DESC LIMIT 1" + (" FOR UPDATE" if lock else ""), (order_id,))
        row = self.cur.fetchone()
        return self._resolution(row) if row else None

    def signatures(self, resolution_id):
        self.cur.execute("SELECT party, signer_address, signature FROM dispute_signatures WHERE resolution_id=%s ORDER BY id",
                         (resolution_id,))
        return list(self.cur.fetchall())

    def transition_resolution(self, resolution_id, from_states, to_status, tx_hash=None):
        """UPDATE có điều kiện trạng thái cũ (SDD 7.5). True nếu chuyển được; False nếu đã bị đổi (Indexer đặt EXECUTED, v.v.)."""
        if not from_states:
            return False
        self.cur.execute(
            "UPDATE dispute_resolutions SET status=%s, submitted_tx_hash=COALESCE(%s, submitted_tx_hash) "
            f"WHERE id=%s AND status IN ({_marks(len(from_states))})", (to_status, tx_hash, resolution_id, *from_states))
        return self.cur.rowcount == 1

    def open_disputes(self):
        self.cur.execute(
            "SELECT w.order_id, w.onchain_order_id, w.amount_raw, w.token_symbol, w.price_vnd, w.buyer_wallet, w.merchant_wallet, "
            "w.disputed_at, w.dispute_timeout, s.name AS shop_name, bu.name AS buyer_name "
            "FROM order_web3 w LEFT JOIN shops s ON s.id = w.shop_id LEFT JOIN users bu ON bu.id = w.buyer_user_id "
            "WHERE w.status='DISPUTED' ORDER BY w.disputed_at, w.onchain_order_id")
        rows = list(self.cur.fetchall())
        ids = [r['order_id'] for r in rows]
        notes, latest, sigs = {}, {}, {}
        if ids:
            self.cur.execute(f"SELECT order_id, reason, evidence_url FROM dispute_notes WHERE order_id IN ({_marks(len(ids))})", tuple(ids))
            notes = {r['order_id']: r for r in self.cur.fetchall()}
            self.cur.execute(
                "SELECT id, order_id, payout_to, amount_raw, nonce, deadline, status, reason_note, submitted_tx_hash "
                f"FROM dispute_resolutions WHERE order_id IN ({_marks(len(ids))}) ORDER BY id", tuple(ids))
            for r in self.cur.fetchall():
                latest[r['order_id']] = self._resolution(r)            # id tăng dần nên bản cuối là mới nhất
            if latest:
                rid = [r['id'] for r in latest.values()]
                self.cur.execute(f"SELECT resolution_id, party FROM dispute_signatures WHERE resolution_id IN ({_marks(len(rid))})",
                                 tuple(rid))
                for r in self.cur.fetchall():
                    sigs.setdefault(r['resolution_id'], []).append(r['party'])
        for r in rows:
            r['amount_raw'], r['price_vnd'] = int(r['amount_raw']), int(r['price_vnd'])
            r['note'] = notes.get(r['order_id'])
            res = latest.get(r['order_id'])
            if res:
                res['signed_by'] = sigs.get(res['id'], [])
            r['resolution'] = res
        return rows


class MySqlUnitOfWork:
    """Một kết nối + một transaction. Thoát khối `with` mà chưa `commit()` thì ROLLBACK (lỗi bất kỳ -> rollback cả lô)."""

    def __init__(self, connection_factory):
        self._factory = connection_factory

    def __enter__(self):
        self.conn = self._factory()
        self._cur_cm = self.conn.cursor()
        self.cur = self._cur_cm.__enter__()
        self.wallets = MySqlWalletRepo(self.cur)
        self.settings = MySqlSettingsRepo(self.cur)
        self.policies = MySqlPolicyRepo(self.cur)
        self.checkout = MySqlCheckoutRepo(self.cur)
        self.shipper = MySqlShipperRepo(self.cur)
        self.outbox = MySqlOutboxRepo(self.cur)
        self.notifications = MySqlNotificationRepo(self.cur)
        self.jobs = MySqlJobsRepo(self.cur)
        self.reconcile = MySqlReconcileRepo(self.cur)
        self.dispute_notes = MySqlDisputeNoteRepo(self.cur)
        self.disputes = MySqlDisputeRepo(self.cur)
        return self

    def commit(self):
        self.conn.commit()

    def __exit__(self, exc_type, exc, tb):
        try:
            self.conn.rollback()       # no-op nếu đã commit; hoàn tác mọi thứ nếu chưa
            self._cur_cm.__exit__(exc_type, exc, tb)
        finally:
            self.conn.close()
