"""Cổng Merchant (UC-07, Tuần 7 - A): đơn Web3 của shop mình + số dư chờ rút (`claimPending`).

Quyền: chỉ tài khoản role `seller` (route kiểm), và CHỈ đơn có `order_web3.merchant_user_id` = người gọi (lấy từ token).
Merchant không cần gọi gì để nhận tiền: contract tự chuyển khi giải ngân. Số dư chờ rút chỉ phát sinh khi ví nhận ETH từ chối
(`PayoutDeferred`); với MockUSD (ERC-20) luôn là 0. Số dư ở đây là bản DẪN XUẤT từ sự kiện (hiển thị); khi rút, giao diện đọc lại
`pendingWithdrawals` trực tiếp từ contract nên chuỗi mới là nguồn sự thật (BR-09).

Dịch vụ chỉ ĐỌC: không ghi MySQL, không gửi giao dịch. Việc rút tiền do chính Merchant ký bằng ví của mình (non-custodial, BR-01).
"""
from ..domain.money import fee_split
from ..domain.reconcile import ETH, token_key
from ..domain.release import delivery_timeout_at, inspection_ends_at

# Merchant chỉ thấy đơn đã được ký quỹ (PENDING_PAYMENT/EXPIRED chưa có tiền trên chuỗi nên không phải việc của shop).
LISTED_STATES = ('LOCKED', 'DELIVERED', 'DISPUTED', 'COMPLETED', 'REFUNDED')
MAX_ORDERS = 200
ETH_DECIMALS = 18


class MerchantService:
    def __init__(self, uow_factory, tokens=None):
        """`tokens`: {khóa token (xem domain.reconcile.token_key): {'symbol', 'decimals'}} cho token ERC-20 đã biết của sàn."""
        self._uow = uow_factory
        self._tokens = {ETH: {'symbol': 'ETH', 'decimals': ETH_DECIMALS}}
        for key, meta in (tokens or {}).items():
            self._tokens[token_key(key)] = {'symbol': meta['symbol'], 'decimals': int(meta['decimals'])}

    def _meta(self, key, fallback_symbol=None):
        m = self._tokens.get(key)
        if m:
            return m
        return {'symbol': fallback_symbol or 'TOKEN', 'decimals': None}      # token lạ: giao diện hiện số nguyên nhỏ nhất, không đoán số thập phân

    def list_orders(self, merchant_user_id):
        with self._uow() as uow:
            rows = uow.merchant.merchant_orders(merchant_user_id, LISTED_STATES, MAX_ORDERS)
            wallets = uow.merchant.merchant_wallets(merchant_user_id)
            pending_rows = uow.merchant.pending_for_addresses(wallets)
            linked = uow.wallets.active_wallet(merchant_user_id)
        return {
            'wallet': None if linked is None else str(linked['address']).lower(),
            'orders': [self._order(r) for r in rows],
            'pending': self._pending(pending_rows),
        }

    def _order(self, r):
        amount = int(r['amount_raw'])
        net, fee = fee_split(amount, int(r['fee_bps']))
        key = token_key(r['token_address'])
        meta = self._meta(key, r.get('token_symbol'))
        status = r['status']
        created = None if r['chain_created_at'] is None else int(r['chain_created_at'])
        delivered = None if r['delivered_at'] is None else int(r['delivered_at'])
        disputed = None if r['disputed_at'] is None else int(r['disputed_at'])
        closed = None if r.get('closed_at') is None else int(r['closed_at'])
        inspection = int(r['inspection_duration'])
        timeout = int(r['dispute_timeout'])
        return {
            'order_id': r['order_id'], 'onchain_order_id': str(int(r['onchain_order_id'])), 'status': status,
            'buyer_name': r.get('buyer_name'), 'items': r.get('items', []),
            'price_vnd': int(r['price_vnd']),
            # Số token luôn là chuỗi (uint256 có thể vượt 2^53). Thực nhận = amount - phí (cùng công thức làm tròn xuống của contract).
            'amount_raw': str(amount), 'net_amount_raw': str(net), 'fee_amount_raw': str(fee), 'fee_bps': int(r['fee_bps']),
            'token': key, 'symbol': meta['symbol'], 'decimals': meta['decimals'],
            'merchant_wallet': str(r['merchant_wallet']).lower(),
            'inspection_duration': inspection, 'dispute_timeout': timeout,
            'chain_created_at': created, 'delivered_at': delivered, 'disputed_at': disputed, 'closed_at': closed,
            # Các mốc để Merchant biết tiền khi nào về / khi nào có thoát hiểm (tính từ giờ block, không phải giờ máy chủ):
            'delivery_deadline': delivery_timeout_at(created) if status == 'LOCKED' and created is not None else None,
            'release_at': inspection_ends_at(delivered, inspection) if status == 'DELIVERED' and delivered is not None else None,
            'force_resolve_at': disputed + timeout if status == 'DISPUTED' and disputed is not None else None,
        }

    def _pending(self, rows):
        merged = {}
        for r in rows:
            key = token_key(r['token_address'])
            addr = str(r['address']).lower()
            entry = merged.setdefault((key, addr), 0)
            merged[(key, addr)] = entry + int(r['amount_raw'])
        out = []
        for (key, addr), amount in sorted(merged.items(), key=lambda kv: (kv[0][0] != ETH, kv[0][0], kv[0][1])):   # ETH trước, thứ tự ổn định
            if amount <= 0:
                continue
            meta = self._meta(key)
            out.append({'token': key, 'address': addr, 'amount_raw': str(amount), 'symbol': meta['symbol'], 'decimals': meta['decimals']})
        return out
