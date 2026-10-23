// Hàm thuần cho màn hình Admin quản lý tranh chấp (UC-06, BR-04). Không I/O; đồng hồ lấy từ server_time của lần poll gần nhất.
import { secondsRemaining } from './web3Checkout';

export const REASON_NOTE_MAX = 2000;
export const PAYOUT_SIDES = Object.freeze({
    BUYER: { label: 'Hoàn tiền cho Buyer', short: 'Hoàn tiền Buyer', detail: 'Buyer nhận lại 100% số tiền ký quỹ.' },
    MERCHANT: { label: 'Giải ngân cho Merchant', short: 'Giải ngân Merchant', detail: 'Merchant nhận tiền sau khi trừ phí sàn (BR-02).' },
});

/** 'NO_PROPOSAL' | 'WAITING_SIGNATURE' | 'READY' | 'SUBMITTED' | 'EXPIRED' — giai đoạn của MỘT tranh chấp. */
export const STAGE = Object.freeze({
    NO_PROPOSAL: 'NO_PROPOSAL', WAITING_SIGNATURE: 'WAITING_SIGNATURE', READY: 'READY', SUBMITTED: 'SUBMITTED', EXPIRED: 'EXPIRED',
});

/** Còn bao nhiêu giây tới hạn chữ ký theo đồng hồ máy chủ; null nếu chưa có đề xuất hoặc chưa có đồng hồ. */
export function signatureRemaining(dispute, clock, nowMs = Date.now()) {
    const res = dispute?.resolution;
    if (!res || !clock || clock.serverTime == null) return null;
    return secondsRemaining({ deadline: res.deadline, serverTime: clock.serverTime, receivedAtMs: clock.receivedAtMs, nowMs });
}

/** Đủ chữ ký để thi hành: Trọng tài + một bên, hoặc Buyer + Merchant (contract chỉ cần hai bên KHÁC NHAU). */
export function hasEnoughSignatures(signedBy = []) {
    const s = new Set(signedBy);
    return (s.has('ARBITRATOR') && (s.has('BUYER') || s.has('MERCHANT'))) || (s.has('BUYER') && s.has('MERCHANT'));
}

export function disputeStage(dispute, clock, nowMs = Date.now()) {
    const res = dispute?.resolution;
    if (!res) return STAGE.NO_PROPOSAL;
    if (res.status === 'EXPIRED' || res.status === 'CANCELLED') return STAGE.EXPIRED;
    if (res.status === 'SUBMITTED' || res.status === 'EXECUTED') return STAGE.SUBMITTED;
    const remaining = signatureRemaining(dispute, clock, nowMs);
    if (res.expired || (remaining !== null && remaining <= 0)) return STAGE.EXPIRED;       // hết hạn chữ ký: cần đề xuất mới
    return hasEnoughSignatures(res.signed_by) ? STAGE.READY : STAGE.WAITING_SIGNATURE;
}

export const canPropose = (stage) => stage === STAGE.NO_PROPOSAL || stage === STAGE.EXPIRED;
export const canSubmit = (stage) => stage === STAGE.READY;
/** Đã nộp mà đơn vẫn DISPUTED (giao dịch trước chưa vào chuỗi / bị hoàn tác): nộp lại an toàn vì backend idempotent. */
export const canResubmit = (stage) => stage === STAGE.SUBMITTED;

/** Chỉ http/https mới được thành liên kết bấm được (phòng `javascript:` dù backend đã chặn). Trả null nếu không an toàn. */
export function safeEvidenceUrl(url) {
    if (typeof url !== 'string' || !url.trim()) return null;
    try {
        const u = new URL(url.trim());
        return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : null;
    } catch {
        return null;
    }
}

export function validateProposalForm({ payoutSide, reasonNote }) {
    const errors = {};
    if (!PAYOUT_SIDES[payoutSide]) errors.payoutSide = 'Hãy chọn hoàn tiền cho Buyer hoặc giải ngân cho Merchant.';
    const note = (reasonNote ?? '').trim();
    if (note.length > REASON_NOTE_MAX) errors.reasonNote = `Ghi chú tối đa ${REASON_NOTE_MAX} ký tự.`;
    return { ok: Object.keys(errors).length === 0, errors, value: { payoutSide, reasonNote: note } };
}

/** Câu thông báo sau khi nộp. `outcome` lấy từ phản hồi API. */
export function submitMessage(result) {
    if (result?.outcome === 'ALREADY_RESOLVED') return 'Phán quyết này đã được thi hành trên blockchain.';
    return 'Đã gửi phán quyết lên blockchain. Hệ thống đang ghi nhận, đơn sẽ rời danh sách khi hoàn tất.';
}

/** Thông báo riêng cho lỗi chưa đủ chữ ký: nói rõ bên nào đã ký. */
export function notReadyMessage(err) {
    const signed = err?.extra?.signed_by;
    const names = { ARBITRATOR: 'Trọng tài (sàn)', BUYER: 'Buyer', MERCHANT: 'Merchant' };
    const who = Array.isArray(signed) && signed.length ? signed.map((p) => names[p] ?? p).join(', ') : 'chưa ai';
    return `Chưa đủ chữ ký để thi hành. Đã có chữ ký của: ${who}. Cần thêm chữ ký của Buyer hoặc Merchant.`;
}
