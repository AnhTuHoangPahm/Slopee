// API tranh chấp phía Admin (UC-06). Lỗi ném dưới dạng Web3ApiError { code, message, status, extra } như api/web3.js.
// Hợp đồng với Backend:
//   GET  /api/admin/disputes                        (A, mới ngoài SDD 10.2) -> { disputes: [ ... ], server_time }
//   POST /api/admin/disputes/:code/proposal         (B) body { payout_to: 'BUYER'|'MERCHANT' (đúng tên trường trong SKELETON), reason_note? }
//        -> đề xuất vừa tạo; backend tự ký phiếu Trọng tài. Địa chỉ ví KHÔNG đi qua giao diện: Backend suy ra từ payout_to.
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

export const submitDisputeAPI = (orderCode) =>
    request(`/api/disputes/${encodeURIComponent(orderCode)}/submit`, { method: 'POST', body: {} });
