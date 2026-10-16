// API cổng Shipper (SRS 7, UC-03). Lỗi ném dưới dạng Web3ApiError { code, message, status, extra } như api/web3.js.
// Hợp đồng với Backend (Thành viên B, Tuần 5):
//   GET  /api/shipper/orders                  -> { orders: [ { order_id, status, shop_name, buyer_name, price_vnd, chain_created_at, delivered_at } ] }
//                                                (đơn được gán cho Shipper đăng nhập; chấp nhận cả dạng mảng trần)
//   POST /api/shipper/orders/:code/deliver    -> { outcome: 'SENT' | 'ALREADY_DELIVERED', tx_hash }
//   Lỗi: INVALID_STATE (409), ORDER_NOT_FOUND (404, kể cả đơn không được gán), CHAIN_TX_FAILED (502), CHAIN_UNAVAILABLE (503), forbidden (403).
import { request } from './web3';

export async function fetchShipperOrdersAPI() {
    const data = await request('/api/shipper/orders');
    if (Array.isArray(data)) return data;
    return Array.isArray(data?.orders) ? data.orders : [];
}

export const deliverShipperOrderAPI = (orderCode) =>
    request(`/api/shipper/orders/${encodeURIComponent(orderCode)}/deliver`, { method: 'POST', body: {} });
