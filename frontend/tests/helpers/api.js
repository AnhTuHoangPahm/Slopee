/* global process */
// Tuần 8 [C] — dữ liệu và thao tác phía máy chủ cho E2E, đi qua REST THẬT của backend (không chạm CSDL trực tiếp).
// Mỗi bài test tự tạo người dùng/shop/sản phẩm mới (tên duy nhất) nên không phụ thuộc thứ tự chạy và không cần dọn dữ liệu.
import { request as pwRequest } from '@playwright/test';
import { API_URL } from './anvil.js';

export const PASSWORD = 'SecurePass123!';
export const PIN = '123456';

let seq = 0;
const uid = () => `${Date.now().toString(36)}${(seq++).toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;
const phone = () => `0${String(Math.floor(Math.random() * 1e9)).padStart(9, '0')}`; // 10 chữ số (SRS: 9-10)

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const newApi = () => pwRequest.newContext({ baseURL: API_URL });
const bearer = (token) => (token ? { Authorization: `Bearer ${token}` } : {});

/** Gọi API và ném lỗi dễ đọc (kèm thân phản hồi) nếu không thành công. */
export async function call(api, method, url, { token, data, expect = [200, 201] } = {}) {
    const res = await api.fetch(url, { method, headers: bearer(token), data });
    const text = await res.text();
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch { body = text; }
    if (!expect.includes(res.status())) throw new Error(`${method} ${url} -> ${res.status()}: ${text.slice(0, 400)}`);
    return { status: res.status(), body };
}

// ---------------------------------------------------------------- tài khoản
export async function signupAndLogin(api, { role = 'user', label = 'u' } = {}) {
    const username = `e2e_${label}_${uid()}`;
    const creds = { username, password: PASSWORD, pass_phrase: PIN, name: `E2E ${label}`, email: `${username}@example.com`, role };
    for (let attempt = 0; ; attempt++) { // số điện thoại ngẫu nhiên có thể trùng: thử lại vài lần
        try {
            await call(api, 'POST', '/api/auth/signup', { data: { ...creds, phone: phone() } });
            break;
        } catch (e) {
            if (attempt >= 4 || !/already exists/i.test(String(e.message))) throw e;
        }
    }
    return { ...(await login(api, username, PASSWORD)), username, password: PASSWORD };
}

export async function login(api, username, password) {
    const { body } = await call(api, 'POST', '/api/auth/login', { data: { username, password } });
    return { token: body.token, user: body.user };
}

// Tài khoản admin/shipper không đăng ký được qua API (P0-02): được gieo bằng CLI (scripts/e2e_stack.sh seed)
export const adminCreds = () => ({ username: process.env.E2E_ADMIN_USER ?? 'e2e_admin', password: process.env.E2E_ADMIN_PASSWORD ?? 'E2eAdminPass#2026' });
export const shipperCreds = () => ({ username: process.env.E2E_SHIPPER_USER ?? 'e2e_shipper', password: process.env.E2E_SHIPPER_PASSWORD ?? 'E2eShipperPass#2026' });
export const loginAdmin = (api) => login(api, adminCreds().username, adminCreds().password);
export const loginShipper = (api) => login(api, shipperCreds().username, shipperCreds().password);

// ---------------------------------------------------------------- ví (UC-00) cho các tài khoản KHÔNG dùng trình duyệt (Merchant)
export async function linkWalletViaApi(api, token, wallet) {
    const address = wallet.address.toLowerCase();
    const { body } = await call(api, 'POST', '/api/wallet/nonce', { token, data: { address } });
    const signature = await wallet.signMessage(body.message);
    await call(api, 'POST', '/api/wallet/link', { token, data: { address, signature, nonce: body.nonce } });
}

// ---------------------------------------------------------------- shop + sản phẩm
/**
 * Tạo Merchant với một shop, các sản phẩm và (tùy chọn) ví nhận tiền đã liên kết.
 * @param {{ shopName?: string, products?: Array<{name: string, price: number, stock?: number}>, wallet?: import('ethers').Wallet }} opts
 */
export async function createMerchant(api, { shopName, products = [{ name: 'Áo thun E2E', price: 400000 }], wallet } = {}) {
    const session = await signupAndLogin(api, { role: 'seller', label: 'shop' });
    const { token } = session;
    // Shop chỉ được mở khi có phương thức nhận tiền (luồng cũ); số dư luôn bắt đầu bằng 0
    await call(api, 'POST', '/api/payments/', { token, data: { methodType: 'bank', providerName: 'E2E Bank', accountNumber: '0001' } });
    const name = shopName ?? `E2E Shop ${uid()}`;
    const { body: shop } = await call(api, 'POST', '/api/shops/', { token, data: { name, description: 'Shop kiểm thử E2E' } });
    const created = [];
    for (const p of products) {
        const { body } = await call(api, 'POST', '/api/shops/products', { token, data: { name: p.name, description: 'E2E', categoryId: 1, inStock: p.stock ?? 20, unitPrice: p.price } });
        created.push({ id: body.productId, name: p.name, price: p.price });
    }
    if (wallet) await linkWalletViaApi(api, token, wallet);
    return { ...session, shopId: shop.shopId, shopName: name, products: created, wallet };
}

export const addToCart = (api, token, productId, quantity = 1) => call(api, 'POST', '/api/carts/items', { token, data: { productId, quantity } });

// ---------------------------------------------------------------- đơn Web3
/** Đơn của Buyer kèm tóm tắt Web3: [{ orderId, shopName, web3: { onchain_order_id, status, checkout_group_id, ... } }]. */
export async function buyerOrders(api, token) {
    const { body } = await call(api, 'GET', '/api/payments/orders', { token });
    return (body.orders ?? []).map((o) => ({ ...o, shopName: o.items?.[0]?.shopName ?? null }));
}
export async function orderStatus(api, token, code) {
    return (await call(api, 'GET', `/api/orders/${encodeURIComponent(code)}/status`, { token })).body;
}
/** Đợi Indexer ghi đúng trạng thái (BR-09: chỉ Indexer đổi trạng thái; test không bao giờ tự đoán theo biên nhận ví). */
export async function waitForStatus(api, token, code, wanted, { timeoutMs = 90_000, everyMs = 1000 } = {}) {
    const deadline = Date.now() + timeoutMs;
    let last = null;
    while (Date.now() < deadline) {
        last = (await orderStatus(api, token, code)).status;
        if (last === wanted) return last;
        await sleep(everyMs);
    }
    throw new Error(`Đơn ${code}: chờ ${wanted} quá ${timeoutMs} ms, trạng thái hiện tại ${last}`);
}

// ---------------------------------------------------------------- Shipper / Admin
/** Admin gán đơn cho Shipper rồi Shipper xác nhận giao (relayer gửi confirmDelivery bằng khóa Shipper của sàn). */
export async function assignAndDeliver(api, { adminToken, shipper, code }) {
    await call(api, 'PUT', `/api/admin/orders/${encodeURIComponent(code)}/shipper`, { token: adminToken, data: { shipper_user_id: shipper.user.id } });
    return (await call(api, 'POST', `/api/shipper/orders/${encodeURIComponent(code)}/deliver`, { token: shipper.token })).body;
}
export const adminPropose = (api, adminToken, code, payoutTo, reasonNote = 'E2E') =>
    call(api, 'POST', `/api/admin/disputes/${encodeURIComponent(code)}/proposal`, { token: adminToken, data: { payout_to: payoutTo, reason_note: reasonNote } });
export const adminForceResolve = (api, adminToken, code, payoutTo, reasonNote = 'E2E timeout', expect) =>
    call(api, 'POST', `/api/admin/disputes/${encodeURIComponent(code)}/force-resolve`, { token: adminToken, data: { payout_to: payoutTo, reason_note: reasonNote }, expect });
export const getDispute = (api, token, code) => call(api, 'GET', `/api/disputes/${encodeURIComponent(code)}`, { token });
