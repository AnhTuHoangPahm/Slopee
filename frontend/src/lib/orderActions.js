// Hành động on-chain của Buyer sau khi đơn đã giao (UC-04 kịch bản 1, UC-05): `earlyRelease` ("Đã nhận hàng") và `raiseDispute` ("Khiếu nại").
// Cùng nguyên tắc với depositFlow: hàm thuần + `runOrderAction` nhận hợp đồng qua tham số (test không cần Anvil).
// Giao diện KHÔNG tự đặt COMPLETED/DISPUTED theo biên nhận của ví: chỉ trạng thái do API (Indexer ghi) mới quyết định (DD-04, BR-09).
import { revertText } from './depositFlow';
import { isUserRejection } from './errors';

export const ORDER_ACTION = Object.freeze({
    EARLY_RELEASE: 'EARLY_RELEASE',
    RAISE_DISPUTE: 'RAISE_DISPUTE',
});

/** Trạng thái đơn mà API phải báo thì mới coi là Indexer đã ghi nhận hành động. */
export const TARGET_STATUS = Object.freeze({
    [ORDER_ACTION.EARLY_RELEASE]: 'COMPLETED',
    [ORDER_ACTION.RAISE_DISPUTE]: 'DISPUTED',
});

export const ACTION_STEP = Object.freeze({
    IDLE: 'IDLE',
    SIGNING: 'SIGNING', // chờ người dùng xác nhận trong ví
    CONFIRMING: 'CONFIRMING', // đã gửi giao dịch, chờ đào block
    WAITING_INDEXER: 'WAITING_INDEXER', // đã đào xong, chờ API (Indexer) báo trạng thái mới
    DONE: 'DONE', // API đã báo trạng thái mới
    FAILED: 'FAILED',
});

const initial = Object.freeze({ step: ACTION_STEP.IDLE, kind: null, txHash: null, error: null });
export const initialActionState = () => ({ ...initial });

/** Đang giữa luồng ví: khóa nút, chặn bấm dồn. */
export const isActionBusy = (state) => [ACTION_STEP.SIGNING, ACTION_STEP.CONFIRMING, ACTION_STEP.WAITING_INDEXER].includes(state.step);

/**
 * Reducer thuần. Sự kiện: START {kind} | SENT {hash} | MINED | INDEXED | FAIL {error} | RESET.
 * Chuyển không hợp lệ bị bỏ qua để sự kiện muộn/trùng không làm lùi bước.
 */
export function orderActionReducer(state, event) {
    switch (event.type) {
        case 'START':
            return state.step === ACTION_STEP.IDLE || state.step === ACTION_STEP.FAILED ? { ...initial, step: ACTION_STEP.SIGNING, kind: event.kind } : state;
        case 'SENT':
            return state.step === ACTION_STEP.SIGNING ? { ...state, step: ACTION_STEP.CONFIRMING, txHash: event.hash } : state;
        case 'MINED':
            return state.step === ACTION_STEP.CONFIRMING ? { ...state, step: ACTION_STEP.WAITING_INDEXER } : state;
        case 'INDEXED': // Indexer có thể nhanh hơn biên nhận: chấp nhận cả khi còn CONFIRMING
            return state.step === ACTION_STEP.WAITING_INDEXER || state.step === ACTION_STEP.CONFIRMING ? { ...state, step: ACTION_STEP.DONE } : state;
        case 'FAIL':
            if (state.step === ACTION_STEP.DONE || state.step === ACTION_STEP.IDLE) return state;
            return { ...state, step: ACTION_STEP.FAILED, error: event.error ?? null };
        case 'RESET':
            return initialActionState();
        default:
            return state;
    }
}

// Lý do revert của SlopeeEscrowMaster (SDD 9.5); cụm cụ thể trước.
const REVERT_MESSAGES = [
    [/Not delivered/i, 'Đơn không còn ở trạng thái chờ kiểm tra (có thể đã được giải ngân hoặc đã khiếu nại). Hãy tải lại trang.'],
    [/Only buyer/i, 'Chỉ ví đã ký quỹ đơn này mới thao tác được. Hãy chọn đúng ví trong MetaMask.'],
    [/Expired/i, 'Đã quá thời hạn kiểm tra nên không thể khiếu nại nữa.'],
    [/Under inspection/i, 'Chưa hết thời hạn kiểm tra.'],
];

/** Lỗi bất kỳ -> { code, message, userRejected }. 4001 là người dùng hủy, không phải lỗi hệ thống. */
export function mapOrderActionError(err) {
    if (isUserRejection(err)) return { code: 'USER_REJECTED', message: 'Bạn đã hủy thao tác.', userRejected: true };
    if (err?.code === -32002) return { code: 'REQUEST_PENDING', message: 'Ví đang chờ bạn xác nhận một yêu cầu khác. Hãy mở ví để xử lý.', userRejected: false };
    const text = revertText(err);
    for (const [re, message] of REVERT_MESSAGES) if (re.test(text)) return { code: 'TX_REVERTED', message, userRejected: false };
    return { code: 'TX_FAILED', message: 'Giao dịch không thành công, tiền của bạn chưa bị thay đổi. Hãy thử lại.', userRejected: false };
}

/**
 * Gửi một giao dịch của Buyer rồi chờ biên nhận; phát sự kiện qua `dispatch`. Dừng ở MINED: chờ Indexer là việc của polling.
 * @param {object} p
 * @param {string} p.kind            ORDER_ACTION.*
 * @param {number|string|bigint} p.onchainOrderId   `web3.onchain_order_id` (< 2^53, nhưng truyền vào contract dưới dạng BigInt)
 * @param {object} p.escrow          hợp đồng SlopeeEscrowMaster (ethers Contract hoặc đối tượng cùng giao diện)
 * @param {(e: object) => void} p.dispatch
 * @returns {Promise<{hash: string}>}  ném lỗi nếu thất bại (đã phát FAIL)
 */
export async function runOrderAction({ kind, onchainOrderId, escrow, dispatch }) {
    dispatch({ type: 'START', kind });
    try {
        const id = BigInt(onchainOrderId);
        let tx;
        if (kind === ORDER_ACTION.EARLY_RELEASE) tx = await escrow.earlyRelease(id);
        else if (kind === ORDER_ACTION.RAISE_DISPUTE) tx = await escrow.raiseDispute(id);
        else throw new Error(`Hành động không hỗ trợ: ${String(kind)}`);
        dispatch({ type: 'SENT', hash: tx.hash });
        await tx.wait();
        dispatch({ type: 'MINED' });
        return { hash: tx.hash };
    } catch (err) {
        dispatch({ type: 'FAIL', error: mapOrderActionError(err) });
        throw err;
    }
}

// ---------------------------------------------------------------------------------------------------------------
// Form khiếu nại (UC-05): lý do + đường dẫn bằng chứng (lưu ở sàn, không lên chuỗi)
// ---------------------------------------------------------------------------------------------------------------
export const DISPUTE_REASON_MIN = 10;
export const DISPUTE_REASON_MAX = 1000;
export const EVIDENCE_URL_MAX = 500;

/** URL http/https hợp lệ (chặn javascript:, data:, file:, ...). Dùng cả khi NHẬP và khi HIỂN THỊ liên kết bằng chứng do người khác gửi. */
export function isHttpUrl(value) {
    try {
        const parsed = new URL(String(value).trim());
        return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch { return false; }
}

/** @returns {{ ok: boolean, errors: {reason?: string, evidenceUrl?: string}, value: {reason: string, evidenceUrl: string} }} */
export function validateDisputeForm({ reason = '', evidenceUrl = '' } = {}) {
    const r = String(reason).trim();
    const u = String(evidenceUrl).trim();
    const errors = {};
    if (r.length < DISPUTE_REASON_MIN) errors.reason = `Hãy nêu lý do khiếu nại (tối thiểu ${DISPUTE_REASON_MIN} ký tự).`;
    else if (r.length > DISPUTE_REASON_MAX) errors.reason = `Lý do tối đa ${DISPUTE_REASON_MAX} ký tự.`;
    if (u) {
        // Chỉ nhận http(s), cùng quy tắc validate_url của backend (P0-06): chặn javascript:, data:, file:...
        if (!isHttpUrl(u)) errors.evidenceUrl = 'Đường dẫn bằng chứng phải bắt đầu bằng http:// hoặc https://.';
        else if (u.length > EVIDENCE_URL_MAX) errors.evidenceUrl = `Đường dẫn tối đa ${EVIDENCE_URL_MAX} ký tự.`;
    }
    return { ok: Object.keys(errors).length === 0, errors, value: { reason: r, evidenceUrl: u } };
}

// Lý do khiếu nại chỉ lưu lên sàn SAU khi Indexer ghi DISPUTED (SDD SEQ-02). Giữ bản nháp trong sessionStorage để tải lại trang
// giữa chừng không mất lý do; xóa khi đã lưu hoặc khi khiếu nại không được gửi lên chuỗi. Không chứa dữ liệu nhạy cảm.
const draftKey = (orderCode) => `slopee.disputeNote.${orderCode}`;
export function saveDisputeDraft(orderCode, note, storage = globalThis.sessionStorage) {
    try { storage?.setItem(draftKey(orderCode), JSON.stringify(note)); } catch { /* bộ nhớ đầy/bị chặn: bỏ qua, vẫn gửi từ bộ nhớ */ }
}
export function loadDisputeDraft(orderCode, storage = globalThis.sessionStorage) {
    try {
        const v = JSON.parse(storage?.getItem(draftKey(orderCode)) ?? 'null');
        return v && typeof v.reason === 'string' ? { reason: v.reason, evidenceUrl: typeof v.evidenceUrl === 'string' ? v.evidenceUrl : '' } : null;
    } catch { return null; }
}
export function clearDisputeDraft(orderCode, storage = globalThis.sessionStorage) {
    try { storage?.removeItem(draftKey(orderCode)); } catch { /* bỏ qua */ }
}
