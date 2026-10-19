// Quy tắc cho màn hình ký phán quyết (UC-06, SDD 9.7, SRS 6). Hàm thuần: không I/O, không đọc đồng hồ ngầm định.
// NGUYÊN TẮC AN TOÀN: giao diện không tin nhãn do máy chủ gán. "Hoàn tiền hay giải ngân" được SUY RA từ địa chỉ nhận so với ví
// Buyer/Merchant, và đề xuất chỉ được ký khi các trường khớp những gì contract sẽ chấp nhận (nếu không, contract sẽ revert).
import { formatTokenAmount } from './web3Checkout';
import { walletGate } from './orderTimer';

export const DISPUTE_STATUS = Object.freeze({
    PROPOSED: 'PROPOSED', READY: 'READY', SUBMITTED: 'SUBMITTED', EXECUTED: 'EXECUTED', EXPIRED: 'EXPIRED', CANCELLED: 'CANCELLED',
});
export const PARTY = Object.freeze({ BUYER: 'BUYER', MERCHANT: 'MERCHANT', ARBITRATOR: 'ARBITRATOR', ADMIN: 'ADMIN' });
export const OUTCOME = Object.freeze({ REFUND_BUYER: 'REFUND_BUYER', PAY_MERCHANT: 'PAY_MERCHANT', UNKNOWN: 'UNKNOWN' });

/** Đoạn cảnh báo bắt buộc ngay trước nút ký (SRS UC-06 bước 4, SDD 9.7, R-06). Không đổi chữ khi chưa sửa nguồn SDD. */
export const SIGN_WARNING_TEXT = 'Lưu ý: Sàn đã ký phê duyệt đề xuất này. Sau khi bạn ký xác nhận, bất kỳ ai (kể cả relayer tự động của sàn) cũng có thể nộp chữ ký lên blockchain để chuyển tiền ngay lập tức.';

export const sameAddress = (a, b) => Boolean(a) && Boolean(b) && String(a).toLowerCase() === String(b).toLowerCase();

/** Kết quả phán quyết suy từ địa chỉ nhận tiền. */
export function outcomeOf({ payoutTo, buyerWallet, merchantWallet }) {
    if (sameAddress(payoutTo, buyerWallet)) return OUTCOME.REFUND_BUYER;
    if (sameAddress(payoutTo, merchantWallet)) return OUTCOME.PAY_MERCHANT;
    return OUTCOME.UNKNOWN;
}

/** Phần Merchant thực nhận khi giải ngân (trừ phí theo `fee_bps` đã khóa lúc ký quỹ, BR-02); Buyer được hoàn 100%. */
export function payoutBreakdown(view) {
    const amount = BigInt(view.amount_raw);
    const feeBps = BigInt(view.fee_bps ?? 0);
    const fee = (amount * feeBps) / 10000n;
    return { amount, fee, merchantNet: amount - fee };
}

/** Trình bày kết quả cho người dùng: tiêu đề, số tiền thực chuyển, địa chỉ nhận. */
export function describeOutcome(view) {
    const r = view.resolution;
    const outcome = outcomeOf({ payoutTo: r?.payout_to, buyerWallet: view.buyer_wallet, merchantWallet: view.merchant_wallet });
    const { amount, fee, merchantNet } = payoutBreakdown(view);
    const fmt = (v) => formatTokenAmount(v.toString(), view.decimals ?? 6, view.symbol ?? 'mUSD');
    if (outcome === OUTCOME.REFUND_BUYER) {
        return { outcome, headline: 'Hoàn tiền cho Buyer', recipient: r.payout_to, transfer: fmt(amount), note: 'Buyer được hoàn 100% số tiền ký quỹ.' };
    }
    if (outcome === OUTCOME.PAY_MERCHANT) {
        return { outcome, headline: 'Giải ngân cho Merchant', recipient: r.payout_to, transfer: fmt(merchantNet), note: `Đã trừ phí sàn ${fmt(fee)} (${Number(view.fee_bps ?? 0) / 100}%).` };
    }
    return { outcome, headline: 'Đề xuất không hợp lệ', recipient: r?.payout_to ?? null, transfer: null, note: 'Địa chỉ nhận không phải ví của Buyer hay Merchant.' };
}

/** Typed data của `DisputeResolution` lấy từ ĐỀ XUẤT máy chủ (thứ tự/trường theo shared/eip712/types.json). */
export function buildDisputeMessage(view) {
    const r = view.resolution;
    return {
        orderId: BigInt(view.onchain_order_id),
        payoutTo: r.payout_to,
        amount: BigInt(r.amount_raw),
        nonce: BigInt(r.nonce),
        deadline: BigInt(r.deadline),
    };
}

/**
 * Kiểm đề xuất TRƯỚC khi cho ký: trả danh sách lý do không ký được (rỗng = ký được). `nowSec` theo giờ máy chủ.
 * Mọi điều kiện ở đây là điều contract sẽ kiểm lại; chặn sớm để người dùng không ký một chữ ký vô dụng (hoặc nguy hiểm).
 */
export function proposalProblems(view, nowSec) {
    const problems = [];
    const r = view?.resolution;
    if (!r) return ['NO_PROPOSAL'];
    if (view.order_status !== 'DISPUTED') problems.push('ORDER_NOT_DISPUTED');
    if (outcomeOf({ payoutTo: r.payout_to, buyerWallet: view.buyer_wallet, merchantWallet: view.merchant_wallet }) === OUTCOME.UNKNOWN) problems.push('BAD_PAYOUT');
    try {
        if (BigInt(r.amount_raw) !== BigInt(view.amount_raw)) problems.push('AMOUNT_MISMATCH');
        BigInt(r.nonce);
    } catch { problems.push('MALFORMED'); }
    const limit = Number(view.disputed_at) + Number(view.dispute_timeout);
    if (!(Number(r.deadline) < limit)) problems.push('DEADLINE_AFTER_TIMEOUT'); // contract: _deadline < disputedAt + disputeTimeout
    if (nowSec !== null && nowSec !== undefined && Number(r.deadline) < nowSec) problems.push('EXPIRED');
    return problems;
}

/** Chữ ký của chính bên đang xem (nếu có). */
export const mySignature = (view) => view?.resolution?.signatures?.find((s) => s.party === view.your_party) ?? null;
export const hasSigned = (view, party) => Boolean(view?.resolution?.signatures?.some((s) => s.party === party));

/** Ví mà bên đang xem PHẢI dùng để ký (ví đã liên kết, UC-00). */
export const expectedWallet = (view) => (view?.your_party === PARTY.BUYER ? view.buyer_wallet : view?.your_party === PARTY.MERCHANT ? view.merchant_wallet : null);

/** Cổng ví cho việc ký: giống cổng của màn hình đơn, nhưng ví đúng là ví của bên mình. 'NOT_A_PARTY' nếu không phải Buyer/Merchant. */
export function signGate(view, wallet) {
    const want = expectedWallet(view);
    if (!want) return 'NOT_A_PARTY';
    return walletGate({ isConnected: wallet.isConnected, isCorrectChain: wallet.isCorrectChain, account: wallet.account, buyerWallet: want });
}

/**
 * Giai đoạn hiển thị của màn hình. `nowSec` theo giờ máy chủ (null nếu chưa có độ lệch).
 * 'LOADING' | 'NOT_DISPUTED' | 'AWAITING_PROPOSAL' | 'CAN_SIGN' | 'BLOCKED' | 'READY' | 'SUBMITTED' | 'EXECUTED' | 'EXPIRED' | 'CANCELLED'
 */
export function disputePhase(view, nowSec) {
    if (!view) return 'LOADING';
    const r = view.resolution;
    if (['COMPLETED', 'REFUNDED'].includes(view.order_status) || r?.status === DISPUTE_STATUS.EXECUTED) return 'EXECUTED';
    if (!r) return view.order_status === 'DISPUTED' ? 'AWAITING_PROPOSAL' : 'NOT_DISPUTED';
    if (r.status === DISPUTE_STATUS.SUBMITTED) return 'SUBMITTED';
    if (r.status === DISPUTE_STATUS.CANCELLED) return 'CANCELLED';
    const pastDeadline = nowSec !== null && nowSec !== undefined && Number(r.deadline) < nowSec;
    if (r.status === DISPUTE_STATUS.EXPIRED || pastDeadline) return 'EXPIRED';
    if (r.status === DISPUTE_STATUS.READY) return 'READY';
    // PROPOSED
    if (hasSigned(view, view.your_party) && view.your_party !== PARTY.ADMIN) return 'READY';
    return proposalProblems(view, nowSec).length === 0 ? 'CAN_SIGN' : 'BLOCKED';
}

export const PROBLEM_TEXT = Object.freeze({
    NO_PROPOSAL: 'Chưa có đề xuất phán quyết.',
    ORDER_NOT_DISPUTED: 'Đơn không còn ở trạng thái khiếu nại.',
    BAD_PAYOUT: 'Địa chỉ nhận tiền không phải ví của Buyer hay Merchant.',
    AMOUNT_MISMATCH: 'Số tiền trong đề xuất không khớp số tiền ký quỹ của đơn.',
    MALFORMED: 'Dữ liệu đề xuất không hợp lệ.',
    DEADLINE_AFTER_TIMEOUT: 'Hạn của chữ ký vượt quá thời hạn tranh chấp của đơn nên hợp đồng sẽ từ chối.',
    EXPIRED: 'Đề xuất đã hết hạn ký.',
});
