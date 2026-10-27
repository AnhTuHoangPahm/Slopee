// API tranh chấp (UC-06, SRS 7, SDD 10.2). Lỗi ném dưới dạng Web3ApiError { code, message, status, extra } như api/web3.js.
// Hai nhóm hàm, cùng một tệp để một nơi duy nhất biết đường dẫn:
//
// ADMIN (A, màn hình AdminDashboard)
//   GET  /api/admin/disputes                        (A, mới ngoài SDD 10.2) -> { disputes: [ ... ], server_time }
//   POST /api/admin/disputes/:code/proposal         (B) body { payout_to: 'BUYER'|'MERCHANT' (đúng tên trường trong SKELETON), reason_note? }
//        -> đề xuất vừa tạo; backend tự ký phiếu Trọng tài. Địa chỉ ví KHÔNG đi qua giao diện: Backend suy ra từ payout_to.
//   POST /api/admin/disputes/:code/force-resolve    (B, UC-07) body { payout_to: 'BUYER'|'MERCHANT', reason_note? }
//        -> { order_id, onchain_order_id, outcome: 'SENT'|'ALREADY_RESOLVED', tx_hash, payout_side, payout_to, amount_raw, force_resolve_at }
//        Chưa tới `force_resolve_at` -> 409 FORCE_RESOLVE_TOO_EARLY (extra: { force_resolve_at, seconds_remaining }), không gửi giao dịch.
//
// BUYER / MERCHANT (C, màn hình pages/Dispute.jsx)
//   GET  /api/disputes/:code  (Buyer, Merchant của đơn; người khác/đơn không có -> 404 ORDER_NOT_FOUND)
//     {
//       order_id, onchain_order_id, order_status,                        // order_status: trạng thái order_web3 (DISPUTED, COMPLETED, REFUNDED, ...)
//       your_party: 'BUYER' | 'MERCHANT',                                // suy từ TOKEN, không do client chọn
//       buyer_wallet, merchant_wallet,                                   // ví đã khóa trong đơn (địa chỉ on-chain)
//       amount_raw (chuỗi), decimals, symbol, fee_bps,
//       disputed_at, dispute_timeout, server_time,                       // giây UTC
//       note: { reason, evidence_url, updated_at } | null,               // ghi chú khiếu nại của Buyer (dispute_notes)
//       resolution: null | {
//         resolution_id, payout_to, amount_raw (chuỗi), nonce, deadline, // đúng 5 trường của typed data DisputeResolution (orderId lấy từ onchain_order_id)
//         status: 'PROPOSED'|'READY'|'SUBMITTED'|'EXECUTED'|'EXPIRED'|'CANCELLED',
//         reason_note, submitted_tx_hash, created_at,
//         signatures: [{ party: 'ARBITRATOR'|'BUYER'|'MERCHANT', signer, signed_at }]   // KHÔNG trả chuỗi chữ ký thô
//       }
//     }
//   POST /api/disputes/:code/signatures  { resolution_id, signature } -> { status }   (PROPOSED | READY)
//
// CHUNG
//   POST /api/disputes/:code/submit                 (A) -> { outcome: 'SENT'|'ALREADY_RESOLVED', tx_hash, resolution_status, payout_side }
//   Lỗi nộp: DISPUTE_NOT_READY (409, extra.signed_by), DISPUTE_STALE (409), DISPUTE_EXPIRED (410), DISPUTE_NOT_FOUND (404),
//            INVALID_STATE (409), CHAIN_TX_FAILED (502), CHAIN_UNAVAILABLE (503).
import { request } from './web3';

export async function fetchAdminDisputesAPI() {
    const data = await request('/api/admin/disputes');
    return { disputes: Array.isArray(data?.disputes) ? data.disputes : [], serverTime: data?.server_time ?? null };
}

export const createDisputeProposalAPI = (orderCode, { payoutSide, reasonNote }) =>
    request(`/api/admin/disputes/${encodeURIComponent(orderCode)}/proposal`, {
        method: 'POST',
        body: { payout_to: payoutSide, ...(reasonNote ? { reason_note: reasonNote } : {}) },
    });

/** UC-07 thoát hiểm timeout: Trọng tài (sàn) xử đơn phương sau `disputeTimeout`. Không thể hoàn tác trên chuỗi. */
export const forceResolveDisputeAPI = (orderCode, { payoutSide, reasonNote }) =>
    request(`/api/admin/disputes/${encodeURIComponent(orderCode)}/force-resolve`, {
        method: 'POST',
        body: { payout_to: payoutSide, ...(reasonNote ? { reason_note: reasonNote } : {}) },
    });

export const fetchDisputeAPI = (orderCode, signal) => request(`/api/disputes/${encodeURIComponent(orderCode)}`, { signal });

export const sendDisputeSignatureAPI = (orderCode, { resolutionId, signature }) =>
    request(`/api/disputes/${encodeURIComponent(orderCode)}/signatures`, { method: 'POST', body: { resolution_id: resolutionId, signature } });

// Giữ `body: {}` của A (api/disputes test của A khẳng định đúng như vậy); backend bỏ qua thân yêu cầu của /submit.
export const submitDisputeAPI = (orderCode) =>
    request(`/api/disputes/${encodeURIComponent(orderCode)}/submit`, { method: 'POST', body: {} });
