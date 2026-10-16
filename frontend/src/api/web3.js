// API Web3 (SRS 7): ví, tạo đơn + báo giá, lô thanh toán. Mọi lỗi được ném dưới dạng Web3ApiError { code, message, status, extra }.
import { API_ORIGIN, authFetch } from '../lib/client';
import { ERROR_MESSAGES, Web3ApiError } from '../lib/errors';

async function request(path, { method = 'GET', body } = {}) {
    let res;
    try {
        res = await authFetch(`${API_ORIGIN}${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch {
        throw new Web3ApiError({ code: 'NETWORK_ERROR', message: ERROR_MESSAGES.NETWORK_ERROR });
    }
    let data = null;
    try {
        data = await res.json();
    } catch {
        /* thân không phải JSON: xử lý ở dưới */
    }
    if (!res.ok) {
        const code = data?.code ?? `HTTP_${res.status}`;
        throw new Web3ApiError({ code, message: data?.message ?? data?.error ?? ERROR_MESSAGES[code], status: res.status, extra: data ?? {} });
    }
    return data;
}

// ---- UC-00
/** Backend cần địa chỉ để dựng thông điệp SIWE (SDD 10.2 ghi "không có đầu vào", nhưng thông điệp chứa địa chỉ). */
export const requestWalletNonceAPI = (address) => request('/api/wallet/nonce', { method: 'POST', body: { address } });
export const linkWalletAPI = ({ address, signature, nonce }) => request('/api/wallet/link', { method: 'POST', body: { address, signature, nonce } });
export const fetchLinkedWalletAPI = () => request('/api/wallet');

// ---- UC-01
/** Chỉ đọc: shop nào trong giỏ chưa liên kết ví nhận tiền → { all_linked, shops: [{shop_id, shop_name, wallet_linked}] }. */
export const fetchWeb3EligibilityAPI = (cartItemIds) => request('/api/orders/eligibility', { method: 'POST', body: { cart_item_ids: cartItemIds } });
export const createWeb3OrderAPI = (cartItemIds) => request('/api/orders', { method: 'POST', body: { cart_item_ids: cartItemIds } });
export const requoteGroupAPI = (groupId) => request(`/api/checkout-groups/${encodeURIComponent(groupId)}/quote`, { method: 'POST', body: {} });
export const fetchCheckoutGroupAPI = (groupId) => request(`/api/checkout-groups/${encodeURIComponent(groupId)}`);
