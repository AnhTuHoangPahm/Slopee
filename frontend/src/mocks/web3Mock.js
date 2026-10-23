// Mock fetch cho API Web3 (SDD 9.6): dựng giao diện khi Backend/chuỗi chưa sẵn sàng. Bật bằng VITE_WEB3_MOCK=true.
// Hình dạng phản hồi BÁM ĐÚNG hợp đồng API thật (backend/slopee_web3/adapters/flask_api/routes.py). Chữ ký là GIẢ
// (không dùng được trên contract): mock chỉ để xem giao diện, không để thử nạp tiền thật.
const TOKEN = '0x5FbDB2315678afecb367f032d93F642f64180aa3';
const hex = (n) => Array.from({ length: n }, () => Math.floor(Math.random() * 16).toString(16)).join('');

const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const err = (status, code, message, extra = {}) => json(status, { code, message, ...extra });

/**
 * @param {object} opts
 * @param {number} opts.ttlSeconds  hạn báo giá (mặc định 900)
 * @param {number} opts.latencyMs   độ trễ giả
 * @param {Array}  opts.shops       [{ shop_id, shop_name, price_vnd }] của lô giả
 * @param {Array}  opts.unlinkedShopIds  shop_id của các shop "chưa liên kết ví" (mô phỏng BR-07); sửa được lúc chạy qua state.unlinkedShopIds
 * @returns {{ uninstall: Function, state: object }}
 */
export function installWeb3Mock({ ttlSeconds = 900, latencyMs = 120, shops, fxVndPerToken = 25000, unlinkedShopIds = [] } = {}) {
    const realFetch = globalThis.fetch;
    const state = { linked: null, nonces: new Map(), groups: new Map(), unlinkedShopIds: new Set(unlinkedShopIds), now: () => Math.floor(Date.now() / 1000) };
    // Dữ liệu mẫu cho SellerDashboard (VITE_WEB3_MOCK=true): 1 đơn đang chờ giao, 1 đơn đã giao, 1 khoản chờ rút ETH
    const sellerWallet = `0x${'6'.repeat(40)}`;
    const mockOrder = (i, status, extra = {}) => ({
        order_id: `mock-merchant-order-${i}`, onchain_order_id: String(100100 + i), status, buyer_name: 'Nguyễn An',
        items: [{ name: 'Áo thun', quantity: 2, variants: null }], price_vnd: 399000, amount_raw: '15960000', net_amount_raw: '15481200',
        fee_amount_raw: '478800', fee_bps: 300, token: TOKEN.toLowerCase(), symbol: 'mUSD', decimals: 6, merchant_wallet: sellerWallet,
        inspection_duration: 259200, dispute_timeout: 2592000, chain_created_at: 1_800_000_000, delivered_at: null, disputed_at: null,
        closed_at: null, delivery_deadline: null, release_at: null, force_resolve_at: null, ...extra,
    });
    state.merchant = {
        wallet: sellerWallet,
        orders: [
            mockOrder(2, 'DELIVERED', { delivered_at: 1_800_100_000, release_at: 1_800_359_200 }),
            mockOrder(1, 'LOCKED', { delivery_deadline: 1_800_000_000 + 14 * 86400 }),
        ],
        pending: [{ token: 'ETH', address: sellerWallet, amount_raw: '5000000000000000', symbol: 'ETH', decimals: 18 }],
    };
    const lots = shops ?? [
        { shop_id: 'mock-shop-1', shop_name: 'Cửa hàng Mẫu A', price_vnd: 399000 },
        { shop_id: 'mock-shop-2', shop_name: 'Cửa hàng Mẫu B', price_vnd: 120000 },
    ];
    const amountRaw = (vnd) => String((BigInt(vnd) * 10n ** 6n + BigInt(fxVndPerToken) - 1n) / BigInt(fxVndPerToken));

    const buildGroup = (groupId, previous) => {
        const deadline = state.now() + ttlSeconds;
        const orders = lots.map((s, i) => {
            const prev = previous?.orders[i];
            const onchain = prev?.onchain_order_id ?? String(100001 + state.groups.size * 10 + i);
            const amount = amountRaw(s.price_vnd);
            return {
                order_id: prev?.order_id ?? crypto.randomUUID(), shop_id: s.shop_id, shop_name: s.shop_name,
                onchain_order_id: onchain, signature: `0x${hex(130)}`, amount_raw: amount, price_vnd: s.price_vnd,
                fx: `${fxVndPerToken}.0000`, inspection_duration: 259200, dispute_timeout: 2592000, fee_bps: 300, policy_code: 'GENERAL',
                quote: { orderId: onchain, buyer: state.linked?.address ?? '0x0', merchant: `0x${hex(40)}`, token: TOKEN, amount,
                    inspectionDuration: '259200', disputeTimeout: '2592000', feeBps: '300', docHash: `0x${hex(64)}`, deadline: String(deadline) },
            };
        });
        const total = orders.reduce((a, o) => a + BigInt(o.amount_raw), 0n).toString();
        return { checkout_group_id: groupId, total_amount_raw: total, decimals: 6, symbol: 'mUSD', token_address: TOKEN, deadline,
            server_time: state.now(), orders };
    };

    const handle = async (path, method, body) => {
        if (path === '/api/wallet' && method === 'GET') {
            return json(200, state.linked ? { linked: true, ...state.linked } : { linked: false, address: null, linked_at: null });
        }
        if (path === '/api/wallet/nonce' && method === 'POST') {
            if (!/^0x[0-9a-fA-F]{40}$/.test(body?.address ?? '')) return err(400, 'INVALID_ADDRESS', 'Địa chỉ ví không hợp lệ.');
            const nonce = hex(32);
            const expires = state.now() + 300;
            state.nonces.set(nonce, body.address.toLowerCase());
            return json(200, { nonce, expires_at: expires, message: `localhost:5173 wants you to link your wallet to a Slopee account.\n\nAddress: ${body.address.toLowerCase()}\nNonce: ${nonce}\n(MOCK)` });
        }
        if (path === '/api/wallet/link' && method === 'POST') {
            const owner = state.nonces.get(body?.nonce);
            if (!owner) return err(400, 'NONCE_INVALID', 'Mã xác thực đã hết hạn hoặc đã được dùng, hãy thử lại.');
            state.nonces.delete(body.nonce);
            if (owner !== String(body.address).toLowerCase()) return err(400, 'BAD_SIGNATURE', 'Chữ ký không khớp với ví đã chọn.');
            state.linked = { address: owner, linked_at: state.now() };
            return json(200, { address: owner, linked_at: state.linked.linked_at });
        }
        if (path === '/api/orders/eligibility' && method === 'POST') {
            if (!body?.cart_item_ids?.length) return err(400, 'EMPTY_CART', 'Chưa chọn sản phẩm nào để thanh toán.');
            const list = lots.map((s) => ({ shop_id: s.shop_id, shop_name: s.shop_name, wallet_linked: !state.unlinkedShopIds.has(s.shop_id) }));
            return json(200, { all_linked: list.every((x) => x.wallet_linked), shops: list });
        }
        if (path === '/api/orders' && method === 'POST') {
            const bad = lots.find((s) => state.unlinkedShopIds.has(s.shop_id));
            if (state.linked && bad) {
                return err(409, 'WALLET_NOT_LINKED', `Cửa hàng «${bad.shop_name}» chưa liên kết ví nhận tiền.`, { party: 'merchant', shop_id: bad.shop_id, shop_name: bad.shop_name });
            }
            if (!state.linked) return err(409, 'WALLET_NOT_LINKED', 'Bạn cần liên kết ví trước khi thanh toán Web3.', { party: 'buyer' });
            if (!body?.cart_item_ids?.length) return err(400, 'EMPTY_CART', 'Chưa chọn sản phẩm nào để thanh toán.');
            const pending = [...state.groups.values()].find((g) => g.status === 'PENDING_PAYMENT');
            if (pending) return err(409, 'PENDING_GROUP_EXISTS', 'Bạn đang có lô thanh toán chưa hoàn tất cho sản phẩm này.', { checkout_group_id: pending.group.checkout_group_id });
            const id = crypto.randomUUID();
            const group = buildGroup(id);
            state.groups.set(id, { status: 'PENDING_PAYMENT', group });
            return json(201, group);
        }
        if (path === '/api/merchant/orders' && method === 'GET') {   // UC-07 (Tuần 7): sửa được lúc chạy qua state.merchant
            return json(200, state.merchant);
        }
        const m = path.match(/^\/api\/checkout-groups\/([^/]+)(\/quote)?$/);
        if (m) {
            const entry = state.groups.get(decodeURIComponent(m[1]));
            if (!entry) return err(404, 'GROUP_NOT_FOUND', 'Không tìm thấy lô thanh toán.');
            if (m[2] && method === 'POST') {
                entry.group = buildGroup(entry.group.checkout_group_id, entry.group);
                return json(200, entry.group);
            }
            if (!m[2] && method === 'GET') {
                return json(200, { ...entry.group, status: entry.status, orders: entry.group.orders.map((o) => ({ ...o, status: entry.status, quote_deadline: entry.group.deadline })) });
            }
        }
        return null;
    };

    globalThis.fetch = async (input, init = {}) => {
        const url = new URL(typeof input === 'string' ? input : input.url, globalThis.location?.origin ?? 'http://localhost');
        const method = (init.method ?? 'GET').toUpperCase();
        let body;
        try { body = init.body ? JSON.parse(init.body) : undefined; } catch { body = undefined; }
        if (/^\/api\/(wallet|orders|checkout-groups|merchant)/.test(url.pathname)) {
            await new Promise((r) => setTimeout(r, latencyMs));
            const res = await handle(url.pathname, method, body);
            if (res) return res;
        }
        return realFetch(input, init); // mọi API khác (đăng nhập, giỏ hàng...) vẫn gọi backend thật
    };
    // Mô phỏng Indexer: chuyển mọi đơn con của lô sang LOCKED (chỉ để dựng giao diện / test; thật thì do Indexer ghi sau khi có OrderCreated)
    state.lock = (groupId) => { const e = state.groups.get(groupId); if (e) e.status = 'LOCKED'; };
    return { uninstall: () => { globalThis.fetch = realFetch; }, state };
}
