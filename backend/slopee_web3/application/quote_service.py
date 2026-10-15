"""QuoteService (MOD-03, UC-01): tạo lô thanh toán Web3, ký báo giá, cấp lại báo giá (SDD 5.3e/f)."""
import uuid
from collections import OrderedDict

from ..domain import money
from ..domain import quote as q
from ..domain.errors import DomainError
from ..domain.policy import pick_durations
from ..ports.chain_port import ChainUnavailable

SETTING_KEYS = ('FX_VND_PER_TOKEN', 'QUOTE_TTL_SECONDS', 'PLATFORM_FEE_BPS')
REQUOTABLE = ('PENDING_PAYMENT', 'EXPIRED')


def _int_setting(raw, key, minimum, maximum=None):
    try:
        v = int(str(raw).strip())
    except (TypeError, ValueError):
        v = None
    if v is None or v < minimum or (maximum is not None and v > maximum):
        raise DomainError('SETTING_INVALID', f'Tham số {key} không hợp lệ, hãy báo quản trị viên.')
    return v


class QuoteService:
    def __init__(self, uow_factory, signer, chain, clock, *, token_address, token_decimals=6,
                 token_symbol='mUSD', max_batch=5):
        self._uow = uow_factory
        self._signer = signer
        self._chain = chain
        self._clock = clock
        self._token = token_address.lower()
        self._decimals = token_decimals
        self._symbol = token_symbol
        self._max_batch = max_batch

    # ------------------------------------------------------------------ đầu vào dùng chung
    def _chain_inputs(self):
        """Đọc chuỗi TRƯỚC khi mở giao dịch DB (không giữ khóa dòng trong lúc chờ mạng)."""
        try:
            return self._chain.default_fee_bps(), self._clock.now_chain()
        except ChainUnavailable:
            raise DomainError('CHAIN_UNAVAILABLE', 'Không kết nối được blockchain, hãy thử lại sau ít phút.')

    def _settings(self, uow):
        raw = uow.settings.get_many(list(SETTING_KEYS))
        for k in SETTING_KEYS:
            if k not in raw:
                raise DomainError('SETTING_INVALID', f'Thiếu tham số {k}, hãy báo quản trị viên.')
        return (money.parse_fx_scaled(raw['FX_VND_PER_TOKEN']),
                _int_setting(raw['QUOTE_TTL_SECONDS'], 'QUOTE_TTL_SECONDS', 60),
                _int_setting(raw['PLATFORM_FEE_BPS'], 'PLATFORM_FEE_BPS', 0, 1000))

    def _build_quote(self, *, onchain_id, buyer, merchant, price_vnd, fx_scaled, fee_bps, inspection,
                     dispute, doc_hash, deadline):
        quote = q.OrderQuote(
            orderId=onchain_id,
            buyer=self._signer.to_checksum(buyer),
            merchant=self._signer.to_checksum(merchant),
            token=self._signer.to_checksum(self._token),
            amount=money.vnd_to_token(price_vnd, self._decimals, fx_scaled),
            inspectionDuration=inspection, disputeTimeout=dispute, feeBps=fee_bps,
            docHash=doc_hash, deadline=deadline)
        q.validate_quote(quote)
        return quote, self._signer.sign_quote(quote)

    def _order_payload(self, *, order_id, shop_id, shop_name, quote, signature, price_vnd, fx_scaled, policy_code):
        return {
            'order_id': order_id, 'shop_id': shop_id, 'shop_name': shop_name,
            'onchain_order_id': str(quote.orderId),
            'quote': quote.message(), 'signature': signature,
            'amount_raw': str(quote.amount), 'price_vnd': int(price_vnd), 'fx': money.fx_to_str(fx_scaled),
            'inspection_duration': quote.inspectionDuration, 'dispute_timeout': quote.disputeTimeout,
            'fee_bps': quote.feeBps, 'policy_code': policy_code,
        }

    def _group_payload(self, group_id, orders, deadline, server_time):
        total = sum(int(o['amount_raw']) for o in orders)   # tổng các amount đã làm tròn LÊN riêng từng shop
        return {
            'checkout_group_id': group_id, 'total_amount_raw': str(total), 'decimals': self._decimals,
            'symbol': self._symbol, 'token_address': self._signer.to_checksum(self._token),
            'deadline': deadline, 'server_time': server_time, 'orders': orders,
        }

    # ------------------------------------------------------------------ UC-01
    def create_checkout(self, user_id, cart_item_ids):
        ids = list(dict.fromkeys(cart_item_ids))     # bỏ trùng, giữ thứ tự
        if not ids:
            raise DomainError('EMPTY_CART', 'Chưa chọn sản phẩm nào để thanh toán.')
        fee_cap, now_chain = self._chain_inputs()

        with self._uow() as uow:
            # THỨ TỰ BẮT BUỘC: đọc KHÓA (giỏ -> sản phẩm, giống checkout cũ, P0-05) trước mọi đọc thường. InnoDB chỉ
            # tạo snapshot ở lần đọc thường đầu tiên; nhờ vậy yêu cầu đến sau (bấm đúp, hai tab) chờ khóa xong rồi
            # mới đọc và thấy lô của yêu cầu trước, không giữ chỗ tồn kho hai lần.
            lines = uow.checkout.lock_cart_lines(user_id, ids)
            if len(lines) != len(ids):
                raise DomainError('CART_ITEM_NOT_FOUND', 'Có sản phẩm không còn trong giỏ hàng của bạn.')
            products = uow.checkout.lock_products(sorted({l['productId'] for l in lines}))

            buyer = uow.wallets.active_wallet(user_id)
            if buyer is None:
                raise DomainError('WALLET_NOT_LINKED', 'Bạn cần liên kết ví trước khi thanh toán Web3.',
                                  {'party': 'buyer'})

            qty_by_product = {}
            for l in lines:
                p = products.get(l['productId'])
                if p is None or not p['isActive']:
                    raise DomainError('PRODUCT_UNAVAILABLE', 'Có sản phẩm đã ngừng bán.', {'product_id': l['productId']})
                qty_by_product[l['productId']] = qty_by_product.get(l['productId'], 0) + int(l['quantity'])
            for pid, qty in qty_by_product.items():
                if qty > int(products[pid]['inStock']):
                    raise DomainError('OUT_OF_STOCK', f"Sản phẩm '{products[pid]['name']}' không đủ hàng.",
                                      {'product_id': pid})

            # Nhóm theo shop theo thứ tự xuất hiện của cart_item_ids
            by_id = {l['cartItemId']: l for l in lines}
            groups = OrderedDict()
            for cid in ids:
                l = by_id[cid]
                groups.setdefault(products[l['productId']]['shopId'], []).append(l)
            if len(groups) > self._max_batch:
                raise DomainError('BATCH_TOO_LARGE', 'Mỗi lần thanh toán tối đa 5 shop, hãy bỏ bớt sản phẩm.',
                                  {'max': self._max_batch, 'shops': len(groups)})

            shops = uow.checkout.get_shops(list(groups))
            for sid in groups:
                if sid not in shops:
                    raise DomainError('PRODUCT_UNAVAILABLE', 'Có shop không còn hoạt động.', {'shop_id': sid})
                if shops[sid]['sellerId'] == user_id:
                    raise DomainError('SELF_PURCHASE', 'Bạn không thể mua sản phẩm của chính shop mình.',
                                      {'shop_id': sid})
            merchant_wallets = uow.wallets.active_wallets([shops[s]['sellerId'] for s in groups])
            for sid in groups:
                if shops[sid]['sellerId'] not in merchant_wallets:
                    raise DomainError('WALLET_NOT_LINKED', f"Cửa hàng «{shops[sid]['name']}» chưa liên kết ví nhận tiền.",
                                      {'party': 'merchant', 'shop_id': sid, 'shop_name': shops[sid]['name']})

            pending = uow.checkout.pending_group_for_products(user_id, list(qty_by_product))
            if pending:   # tránh giữ chỗ tồn kho hai lần cho cùng sản phẩm khi bấm thanh toán lại
                raise DomainError('PENDING_GROUP_EXISTS',
                                  'Bạn đang có lô thanh toán chưa hoàn tất cho sản phẩm này, hãy hoàn tất hoặc lấy báo giá mới.',
                                  {'checkout_group_id': pending})

            fx_scaled, ttl, platform_fee = self._settings(uow)
            fee_bps = min(platform_fee, fee_cap)       # R-01: không vượt trần on-chain
            deadline = now_chain + ttl
            category_ids = sorted({products[l['productId']]['categoryId'] for l in lines})
            policy_map = uow.policies.policies_for_categories(category_ids)
            if policy_map is None:
                raise DomainError('POLICY_NOT_CONFIGURED', 'Chưa cấu hình nhóm hàng mặc định, hãy báo quản trị viên.')
            created_at = self._clock.now_system()

            group_id = str(uuid.uuid4())
            built = []
            for sid, shop_lines in groups.items():
                order_id = str(uuid.uuid4())
                items = [{'product_id': l['productId'], 'quantity': l['quantity'],
                          'unit_price_vnd': int(products[l['productId']]['unitPrice'])} for l in shop_lines]
                price_vnd = sum(i['quantity'] * i['unit_price_vnd'] for i in items)
                inspection, dispute, dominant = pick_durations(
                    [policy_map[products[l['productId']]['categoryId']] for l in shop_lines])
                summary = q.build_summary(order_id, items, price_vnd, created_at)
                onchain_id = uow.checkout.next_onchain_id()
                quote, signature = self._build_quote(
                    onchain_id=onchain_id, buyer=buyer['address'], merchant=merchant_wallets[shops[sid]['sellerId']],
                    price_vnd=price_vnd, fx_scaled=fx_scaled, fee_bps=fee_bps, inspection=inspection, dispute=dispute,
                    doc_hash=q.doc_hash(summary, self._signer.keccak), deadline=deadline)
                built.append((sid, shop_lines, order_id, price_vnd, quote, signature, dominant.code))

            total = sum(b[4].amount for b in built)
            uow.checkout.insert_group(group_id, user_id, self._token, str(total), len(built))
            payload_orders = []
            for sid, shop_lines, order_id, price_vnd, quote, signature, policy_code in built:
                uow.checkout.insert_order(order_id, user_id, price_vnd, created_at)
                uow.checkout.insert_order_lines(order_id, [
                    {'productId': l['productId'], 'selectedVariants': l['selectedVariants'], 'quantity': l['quantity'],
                     'unitPrice': int(products[l['productId']]['unitPrice']),
                     'snapshotProductName': products[l['productId']]['name'], 'snapshotShopName': shops[sid]['name']}
                    for l in shop_lines])
                reserve = {}
                for l in shop_lines:
                    reserve[l['productId']] = reserve.get(l['productId'], 0) + int(l['quantity'])
                for pid, qty in reserve.items():     # UPDATE ... WHERE inStock >= qty, kiểm rowcount
                    if not uow.checkout.reserve_stock(pid, qty):
                        raise DomainError('OUT_OF_STOCK', 'Sản phẩm vừa hết hàng, hãy thử lại.', {'product_id': pid})
                uow.checkout.insert_order_web3({
                    'order_id': order_id, 'onchain_order_id': quote.orderId, 'buyer_user_id': user_id,
                    'merchant_user_id': shops[sid]['sellerId'], 'shop_id': sid, 'checkout_group_id': group_id,
                    'buyer_wallet': buyer['address'], 'merchant_wallet': merchant_wallets[shops[sid]['sellerId']],
                    'token_address': self._token, 'token_symbol': self._symbol, 'amount_raw': str(quote.amount),
                    'price_vnd': price_vnd, 'fx_scaled': fx_scaled, 'policy_code': policy_code,
                    'fee_bps': quote.feeBps, 'inspection_duration': quote.inspectionDuration,
                    'dispute_timeout': quote.disputeTimeout, 'doc_hash': quote.docHash})
                uow.checkout.insert_quote(order_id, quote.message(), signature, deadline)
                payload_orders.append(self._order_payload(
                    order_id=order_id, shop_id=sid, shop_name=shops[sid]['name'], quote=quote, signature=signature,
                    price_vnd=price_vnd, fx_scaled=fx_scaled, policy_code=policy_code))
            uow.commit()
        return self._group_payload(group_id, payload_orders, deadline, now_chain)

    # ------------------------------------------------------------------ điều kiện hiển thị cho Checkout
    def check_web3_eligibility(self, user_id, cart_item_ids):
        """Giao diện hỏi trước khi cho chọn "Thanh toán Web3": mọi shop trong giỏ đã liên kết ví nhận tiền chưa (BR-07).

        CHỈ ĐỌC, không khóa dòng, không ghi gì; chỉ trả tên shop và cờ đã/chưa liên kết (không lộ địa chỉ ví).
        Ví của chính người mua do màn hình ví/panel xử lý nên không nằm ở đây. Quyết định cuối cùng vẫn là
        create_checkout (kiểm lại trong giao dịch), kết quả này chỉ để không mời người dùng vào ngõ cụt."""
        ids = list(dict.fromkeys(cart_item_ids))
        if not ids:
            raise DomainError('EMPTY_CART', 'Chưa chọn sản phẩm nào để thanh toán.')
        with self._uow() as uow:
            lines = uow.checkout.lock_cart_lines(user_id, ids, lock=False)
            if len(lines) != len(ids):
                raise DomainError('CART_ITEM_NOT_FOUND', 'Có sản phẩm không còn trong giỏ hàng của bạn.')
            products = uow.checkout.lock_products(sorted({l['productId'] for l in lines}), lock=False)
            by_id = {l['cartItemId']: l for l in lines}
            shop_ids = list(OrderedDict.fromkeys(                       # theo thứ tự yêu cầu, như create_checkout
                products[by_id[cid]['productId']]['shopId'] for cid in ids if by_id[cid]['productId'] in products))
            shops = uow.checkout.get_shops(shop_ids)
            linked = uow.wallets.active_wallets([shops[s]['sellerId'] for s in shop_ids if s in shops])
        out = [{'shop_id': s, 'shop_name': shops[s]['name'], 'wallet_linked': shops[s]['sellerId'] in linked}
               for s in shop_ids if s in shops]
        return {'all_linked': all(x['wallet_linked'] for x in out), 'shops': out}

    # ------------------------------------------------------------------ cấp lại báo giá cho cả lô
    def reissue_group_quotes(self, user_id, group_id):
        fee_cap, now_chain = self._chain_inputs()
        with self._uow() as uow:
            group = uow.checkout.get_group(group_id, user_id)
            if group is None:                    # không phải chủ lô -> như không tồn tại (404, không lộ sự tồn tại)
                raise DomainError('GROUP_NOT_FOUND', 'Không tìm thấy lô thanh toán.')
            orders = uow.checkout.group_orders(group_id, lock=True)
            if any(o['status'] not in REQUOTABLE for o in orders):
                raise DomainError('INVALID_STATE', 'Lô thanh toán này không còn ở trạng thái chờ thanh toán.')
            # Giữ nguyên onchain_order_id CHỈ khi contract trả NONE cho từng mã (kiểm trực tiếp trên chuỗi).
            try:
                states = [self._chain.get_order_state(int(o['onchain_order_id'])) for o in orders]
            except ChainUnavailable:
                raise DomainError('CHAIN_UNAVAILABLE', 'Không kết nối được blockchain, hãy thử lại sau ít phút.')
            if any(s != 'NONE' for s in states):
                raise DomainError('INVALID_STATE',
                                  'Đơn đã có trên blockchain, hãy chờ hệ thống đồng bộ trạng thái.')

            buyer = uow.wallets.active_wallet(user_id)
            if buyer is None:
                raise DomainError('WALLET_NOT_LINKED', 'Bạn cần liên kết ví trước khi thanh toán Web3.',
                                  {'party': 'buyer'})
            merchant_wallets = uow.wallets.active_wallets([o['merchant_user_id'] for o in orders])
            for o in orders:
                if o['merchant_user_id'] not in merchant_wallets:
                    raise DomainError('WALLET_NOT_LINKED', f"Cửa hàng «{o.get('shop_name')}» chưa liên kết ví nhận tiền.",
                                      {'party': 'merchant', 'shop_id': o['shop_id'], 'shop_name': o.get('shop_name')})

            fx_scaled, ttl, platform_fee = self._settings(uow)
            fee_bps = min(platform_fee, fee_cap)       # đọc lại trần phí (FEE_CAP_CHANGED -> phí mới)
            deadline = now_chain + ttl

            if any(o['status'] == 'EXPIRED' for o in orders):
                # Lô đã hết hạn thì tồn kho đã được trả lại; giữ chỗ lại, thiếu hàng thì từ chối cả lô.
                for o in orders:
                    need = {}
                    for ln in uow.checkout.order_lines(o['order_id']):
                        if ln['productId'] is not None:
                            need[ln['productId']] = need.get(ln['productId'], 0) + int(ln['quantity'])
                    for pid in sorted(need):
                        if not uow.checkout.reserve_stock(pid, need[pid]):
                            raise DomainError('OUT_OF_STOCK', 'Sản phẩm vừa hết hàng, không thể lấy báo giá mới.',
                                              {'product_id': pid})

            payload_orders = []
            for o in orders:
                # Giữ nguyên thời hạn, docHash và giá VND đã chốt; chỉ làm mới tỷ giá/phí/ví/hạn dùng.
                quote, signature = self._build_quote(
                    onchain_id=int(o['onchain_order_id']), buyer=buyer['address'],
                    merchant=merchant_wallets[o['merchant_user_id']], price_vnd=int(o['price_vnd']),
                    fx_scaled=fx_scaled, fee_bps=fee_bps, inspection=int(o['inspection_duration']),
                    dispute=int(o['dispute_timeout']), doc_hash=o['doc_hash'], deadline=deadline)
                uow.checkout.update_order_requote(o['order_id'], {
                    'status': 'PENDING_PAYMENT', 'amount_raw': str(quote.amount), 'fx_scaled': fx_scaled,
                    'fee_bps': quote.feeBps, 'buyer_wallet': buyer['address'],
                    'merchant_wallet': merchant_wallets[o['merchant_user_id']]})
                uow.checkout.insert_quote(o['order_id'], quote.message(), signature, deadline)
                payload_orders.append(self._order_payload(
                    order_id=o['order_id'], shop_id=o['shop_id'], shop_name=o.get('shop_name'), quote=quote,
                    signature=signature, price_vnd=o['price_vnd'], fx_scaled=fx_scaled, policy_code=o['policy_code']))
            payload = self._group_payload(group_id, payload_orders, deadline, now_chain)
            uow.checkout.update_group_total(group_id, payload['total_amount_raw'])
            uow.commit()
        return payload

    # ------------------------------------------------------------------ đọc lô (polling ở Tuần 4)
    def get_group(self, user_id, group_id):
        server_time = self._clock.now_chain()
        with self._uow() as uow:
            group = uow.checkout.get_group(group_id, user_id)
            if group is None:
                raise DomainError('GROUP_NOT_FOUND', 'Không tìm thấy lô thanh toán.')
            orders = uow.checkout.group_orders(group_id)
            deadline = 0
            out = []
            for o in orders:
                latest = uow.checkout.latest_quote(o['order_id'])
                dl = latest['deadline'] if latest else 0
                deadline = max(deadline, dl)
                out.append({
                    'order_id': o['order_id'], 'shop_id': o['shop_id'], 'shop_name': o.get('shop_name'),
                    'onchain_order_id': str(o['onchain_order_id']), 'status': o['status'],
                    'amount_raw': str(o['amount_raw']), 'price_vnd': int(o['price_vnd']),
                    'deposit_tx_hash': o.get('deposit_tx_hash'), 'quote_deadline': dl,
                    'inspection_duration': int(o['inspection_duration']), 'dispute_timeout': int(o['dispute_timeout']),
                    'fee_bps': int(o['fee_bps']),
                })
        statuses = {o['status'] for o in out}
        return {
            'checkout_group_id': group_id, 'total_amount_raw': str(group['total_amount_raw']),
            'decimals': self._decimals, 'symbol': self._symbol, 'deadline': deadline,
            'status': next(iter(statuses)) if len(statuses) == 1 else 'MIXED',
            'server_time': server_time, 'orders': out,
        }
