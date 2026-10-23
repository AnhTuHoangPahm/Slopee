// Rút khoản chờ rút (`claimPending`, UC-07, BR-05). Cùng nguyên tắc với orderActions: hàm thuần + `runClaimPending` nhận hợp đồng qua tham số
// (test không cần Anvil). Giao diện KHÔNG tự coi là đã rút theo biên nhận của ví: số dư chờ rút chỉ biến mất khi API (Indexer) báo (DD-04, BR-09).
//
// Vì sao có khoản chờ rút: contract chuyển tiền thẳng cho Merchant khi giải ngân. Riêng ETH, nếu ví nhận là contract từ chối nhận thì
// contract không revert (tránh kẹt đơn) mà ghi vào `pendingWithdrawals` + sự kiện `PayoutDeferred`; chủ ví tự rút bằng `claimPending`.
// Với MockUSD (ERC-20) luôn là 0. `claimPending` trả tiền cho `msg.sender`, nên PHẢI gọi bằng đúng ví đang có số dư.
import { isUserRejection } from './errors';
import { revertText } from './depositFlow';

export const ETH_ADDRESS = '0x0000000000000000000000000000000000000000';

export const CLAIM_STEP = Object.freeze({
    IDLE: 'IDLE',
    SIGNING: 'SIGNING',                 // chờ người dùng xác nhận trong ví
    CONFIRMING: 'CONFIRMING',           // đã gửi giao dịch, chờ đào block
    WAITING_INDEXER: 'WAITING_INDEXER', // đã đào xong, chờ API (Indexer) bỏ khoản chờ rút
    DONE: 'DONE',
    FAILED: 'FAILED',
});

const initial = Object.freeze({ step: CLAIM_STEP.IDLE, token: null, address: null, amountRaw: null, txHash: null, error: null });
export const initialClaimState = () => ({ ...initial });
export const isClaimBusy = (s) => [CLAIM_STEP.SIGNING, CLAIM_STEP.CONFIRMING, CLAIM_STEP.WAITING_INDEXER].includes(s.step);

/** Khóa token của API ('ETH' hoặc địa chỉ) -> tham số `_token` của contract (ETH là địa chỉ 0). */
export const tokenParam = (token) => (token === 'ETH' || !token ? ETH_ADDRESS : String(token));

/** Reducer thuần. Sự kiện: START {token,address} | SENT {hash} | MINED | INDEXED | FAIL {error} | RESET. Chuyển không hợp lệ bị bỏ qua. */
export function claimReducer(state, event) {
    switch (event.type) {
        case 'START':
            return state.step === CLAIM_STEP.IDLE || state.step === CLAIM_STEP.FAILED || state.step === CLAIM_STEP.DONE
                ? { ...initial, step: CLAIM_STEP.SIGNING, token: event.token, address: event.address } : state;
        case 'SENT':
            return state.step === CLAIM_STEP.SIGNING ? { ...state, step: CLAIM_STEP.CONFIRMING, txHash: event.hash, amountRaw: event.amountRaw ?? state.amountRaw } : state;
        case 'MINED':
            return state.step === CLAIM_STEP.CONFIRMING ? { ...state, step: CLAIM_STEP.WAITING_INDEXER } : state;
        case 'INDEXED': // Indexer có thể nhanh hơn biên nhận: chấp nhận cả khi còn CONFIRMING
            return state.step === CLAIM_STEP.WAITING_INDEXER || state.step === CLAIM_STEP.CONFIRMING ? { ...state, step: CLAIM_STEP.DONE } : state;
        case 'FAIL':
            if (state.step === CLAIM_STEP.DONE || state.step === CLAIM_STEP.IDLE) return state;
            return { ...state, step: CLAIM_STEP.FAILED, error: event.error ?? null };
        case 'RESET':
            return initialClaimState();
        default:
            return state;
    }
}

// Lý do revert của SlopeeEscrowMaster.claimPending; cụm cụ thể trước.
const REVERT_MESSAGES = [
    [/Nothing to claim/i, 'Không còn khoản nào để rút (có thể bạn đã rút rồi). Hãy tải lại trang.'],
    [/ETH transfer failed/i, 'Ví của bạn từ chối nhận ETH nên giao dịch bị hủy. Khoản chờ rút vẫn còn nguyên; hãy dùng ví có thể nhận ETH (ví thường, không phải hợp đồng từ chối tiền).'],
    [/reentrancy|ReentrancyGuard/i, 'Hợp đồng đang xử lý một giao dịch khác. Hãy thử lại sau ít giây.'],
];

export class ClaimError extends Error {
    constructor(code, message) { super(message); this.name = 'ClaimError'; this.code = code; }
}

/** Lỗi bất kỳ -> { code, message, userRejected }. 4001 là người dùng hủy, không phải lỗi hệ thống. */
export function mapClaimError(err) {
    if (err instanceof ClaimError) return { code: err.code, message: err.message, userRejected: false };
    if (isUserRejection(err)) return { code: 'USER_REJECTED', message: 'Bạn đã hủy thao tác.', userRejected: true };
    if (err?.code === -32002) return { code: 'REQUEST_PENDING', message: 'Ví đang chờ bạn xác nhận một yêu cầu khác. Hãy mở ví để xử lý.', userRejected: false };
    const text = revertText(err);
    for (const [re, message] of REVERT_MESSAGES) if (re.test(text)) return { code: 'TX_REVERTED', message, userRejected: false };
    return { code: 'TX_FAILED', message: 'Giao dịch không thành công, khoản chờ rút của bạn chưa bị thay đổi. Hãy thử lại.', userRejected: false };
}

/**
 * Rút một khoản chờ rút. Đọc LẠI số dư thật trên chuỗi trước (nguồn sự thật, BR-09) để không tốn gas vô ích khi khoản đã được rút
 * (MySQL chỉ là bản dẫn xuất, có thể trễ). Dừng ở MINED: chờ Indexer là việc của polling.
 * @param {object} p
 * @param {string} p.token    khóa token của API ('ETH' | địa chỉ ERC-20)
 * @param {string} p.address  ví sở hữu khoản chờ rút (phải là ví đang kết nối: contract trả cho msg.sender)
 * @param {object} p.escrow   SlopeeEscrowMaster (ethers Contract hoặc đối tượng cùng giao diện)
 * @param {(e: object) => void} p.dispatch
 * @returns {Promise<{hash: string, amountRaw: string}>}  ném lỗi nếu thất bại (đã phát FAIL)
 */
export async function runClaimPending({ token, address, escrow, dispatch }) {
    dispatch({ type: 'START', token, address });
    try {
        const param = tokenParam(token);
        const onchain = BigInt(await escrow.pendingWithdrawals(param, address));
        if (onchain <= 0n) throw new ClaimError('NOTHING_TO_CLAIM', 'Không còn khoản nào để rút (có thể bạn đã rút rồi). Hãy tải lại trang.');
        const tx = await escrow.claimPending(param);
        dispatch({ type: 'SENT', hash: tx.hash, amountRaw: onchain.toString() });
        await tx.wait();
        dispatch({ type: 'MINED' });
        return { hash: tx.hash, amountRaw: onchain.toString() };
    } catch (err) {
        dispatch({ type: 'FAIL', error: mapClaimError(err) });
        throw err;
    }
}

/** Đã Indexer ghi nhận chưa: khoản chờ rút (token, ví) không còn trong danh sách API. */
export const claimIndexed = (pending, { token, address }) =>
    !pending.some((p) => p.token === token && p.address === String(address).toLowerCase());
