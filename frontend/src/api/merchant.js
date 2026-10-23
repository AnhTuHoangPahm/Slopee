// API cổng Merchant (UC-07, Tuần 7). Lỗi ném dưới dạng Web3ApiError { code, message, status, extra } như api/web3.js.
// Hợp đồng với Backend (Thành viên A cũng làm phần máy chủ; mới ngoài SDD 10.2, chờ nhóm xác nhận):
//   GET /api/merchant/orders (role seller, chỉ đơn của shop mình; danh tính lấy từ token)
//     -> { wallet: '0x…'|null,                       ví đang liên kết của tài khoản (chữ thường)
//          orders: [ { order_id, onchain_order_id (chuỗi), status: LOCKED|DELIVERED|DISPUTED|COMPLETED|REFUNDED,
//                      buyer_name, items:[{name, quantity, variants}], price_vnd,
//                      amount_raw, net_amount_raw, fee_amount_raw (chuỗi số nguyên), fee_bps,
//                      token ('ETH'|địa chỉ), symbol, decimals (số|null), merchant_wallet,
//                      inspection_duration, dispute_timeout,
//                      chain_created_at, delivered_at, disputed_at, closed_at,
//                      delivery_deadline (chỉ LOCKED), release_at (chỉ DELIVERED), force_resolve_at (chỉ DISPUTED) } ],
//          pending: [ { token, address, amount_raw (chuỗi), symbol, decimals } ] }      số dư chờ rút (dẫn xuất từ sự kiện; chỉ > 0)
import { request } from './web3';

export const fetchMerchantOrdersAPI = (signal) => request('/api/merchant/orders', { signal });
