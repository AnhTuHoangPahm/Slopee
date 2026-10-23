// Luồng ký phán quyết của Buyer/Merchant (UC-06 bước 3): MetaMask `eth_signTypedData_v4` (không tốn gas) -> gửi chữ ký lên sàn.
// Cùng khuôn với depositFlow/orderActions: reducer thuần + hàm nhận signer/API qua tham số (test không cần ví thật).
import { buildDomain, recoverDisputeSigner, signDispute } from './eip712';
import { isUserRejection } from './errors';
import { buildDisputeMessage, sameAddress } from './disputeSign';

export const SIGN_STEP = Object.freeze({ IDLE: 'IDLE', SIGNING: 'SIGNING', SENDING: 'SENDING', DONE: 'DONE', FAILED: 'FAILED' });
const initial = Object.freeze({ step: SIGN_STEP.IDLE, signature: null, error: null });
export const initialSignState = () => ({ ...initial });
export const isSignBusy = (s) => s.step === SIGN_STEP.SIGNING || s.step === SIGN_STEP.SENDING;

/** Sự kiện: START | SIGNED {signature} | DONE | FAIL {error} | RESET. Sự kiện sai thứ tự bị bỏ qua. */
export function signReducer(state, event) {
    switch (event.type) {
        case 'START': return state.step === SIGN_STEP.IDLE || state.step === SIGN_STEP.FAILED ? { ...initial, step: SIGN_STEP.SIGNING } : state; // ký lại từ đầu (bỏ chữ ký cũ)
        case 'SIGNED': return state.step === SIGN_STEP.SIGNING ? { ...state, step: SIGN_STEP.SENDING, signature: event.signature } : state;
        case 'RESEND': return state.step === SIGN_STEP.FAILED && state.signature ? { ...state, step: SIGN_STEP.SENDING, error: null } : state;
        case 'DONE': return state.step === SIGN_STEP.SENDING ? { ...state, step: SIGN_STEP.DONE } : state;
        case 'FAIL': return state.step === SIGN_STEP.SIGNING || state.step === SIGN_STEP.SENDING ? { ...state, step: SIGN_STEP.FAILED, error: event.error } : state;
        case 'RESET': return initialSignState();
        default: return state;
    }
}

/** Lỗi gửi chữ ký có đáng thử lại không: lỗi mạng/5xx thì có (chữ ký còn nguyên, không phải ký lại); 4xx là kết quả cuối. */
export const isRetryableSendError = (err) => err?.code === 'NETWORK_ERROR' || !(Number(err?.status) >= 400 && Number(err?.status) < 500);

function mapSignError(err) {
    if (isUserRejection(err)) return { code: 'USER_REJECTED', message: 'Bạn đã hủy thao tác ký.', userRejected: true, retryable: false, stage: 'SIGN' };
    if (err?.code === -32002) return { code: 'REQUEST_PENDING', message: 'Ví đang chờ bạn xác nhận một yêu cầu khác. Hãy mở ví để xử lý.', userRejected: false, retryable: false, stage: 'SIGN' };
    return { code: err?.code ?? 'SIGN_FAILED', message: 'Không ký được. Hãy kiểm tra ví rồi thử lại.', userRejected: false, retryable: false, stage: 'SIGN' };
}

/**
 * Ký rồi gửi. Kiểm lại trước khi gửi: tài khoản ký đúng là ví của bên mình, và chữ ký khôi phục ra đúng địa chỉ đó
 * (chữ ký sai ví chỉ làm tốn thời gian: backend và contract sẽ từ chối).
 * @param {object} p
 * @param {object} p.view        phản hồi GET /api/disputes/:code
 * @param {object} p.signer      ethers Signer (BrowserProvider.getSigner())
 * @param {object} p.deployment  { chainId, escrow }
 * @param {(code: string, body: {resolutionId: any, signature: string}) => Promise<any>} p.send
 * @param {(e: object) => void} p.dispatch
 * @param {string} p.expectedWallet
 */
export async function signAndSendDispute({ view, signer, deployment, send, dispatch, expectedWallet }) {
    dispatch({ type: 'START' });
    let signature;
    try {
        const account = await signer.getAddress();
        if (!sameAddress(account, expectedWallet)) {
            const e = Object.assign(new Error('account changed'), { code: 'ACCOUNT_CHANGED' });
            throw e;
        }
        const message = buildDisputeMessage(view);
        const domain = buildDomain(deployment);
        signature = await signDispute(signer, domain, message);
        if (!sameAddress(recoverDisputeSigner(domain, message, signature), expectedWallet)) {
            throw Object.assign(new Error('signer mismatch'), { code: 'SIGNER_MISMATCH' });
        }
    } catch (err) {
        const mapped = err?.code === 'ACCOUNT_CHANGED'
            ? { code: 'ACCOUNT_CHANGED', message: 'Bạn vừa đổi tài khoản trong ví. Hãy chọn đúng ví đã liên kết rồi ký lại.', userRejected: false, retryable: false, stage: 'SIGN' }
            : err?.code === 'SIGNER_MISMATCH'
                ? { code: 'SIGNER_MISMATCH', message: 'Chữ ký không khớp với ví đã liên kết, hãy chọn đúng ví rồi ký lại.', userRejected: false, retryable: false, stage: 'SIGN' }
                : mapSignError(err);
        dispatch({ type: 'FAIL', error: mapped });
        throw err;
    }
    dispatch({ type: 'SIGNED', signature });
    return sendSignature({ view, signature, send, dispatch });
}

/** Gửi (hoặc gửi lại) chữ ký đã có, không bật ví nữa. */
export async function sendSignature({ view, signature, send, dispatch }) {
    try {
        const res = await send(view.order_id, { resolutionId: view.resolution.resolution_id, signature });
        dispatch({ type: 'DONE' });
        return res;
    } catch (err) {
        dispatch({
            type: 'FAIL',
            error: { code: err?.code ?? 'SEND_FAILED', message: err?.message || 'Không gửi được chữ ký lên sàn.', userRejected: false, retryable: isRetryableSendError(err), stage: 'SEND' },
        });
        throw err;
    }
}
