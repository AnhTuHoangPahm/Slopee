// Luồng nạp tiền ký quỹ của Buyer (SDD 9.3, SEQ-01): approve tổng -> depositEscrowBatch -> chờ Indexer.
// Tệp này CHỈ chứa hàm thuần + `runDeposit` nhận hợp đồng ethers qua tham số (dễ giả lập khi test).
// Giao diện KHÔNG tự đặt LOCKED theo biên nhận của ví: chỉ API (do Indexer ghi) mới quyết định (DD-04, BR-09).
import { sameAddress } from './chain';
import { QUOTE_MIN_REMAINING } from './web3Checkout';
import { isUserRejection } from './errors';

export const MAX_BATCH_SIZE = 5; // trùng SlopeeEscrowMaster.MAX_BATCH_SIZE
export const INDEXER_SLOW_AFTER_MS = 30_000; // SDD 9.3: quá 30 giây thì hiện mã giao dịch + gợi ý kiểm tra Indexer

export const STEP = Object.freeze({
    IDLE: 'IDLE',
    CHECKING: 'CHECKING', // CHECK_QUOTE + CHECK_ALLOWANCE (đọc chuỗi, chưa cần ví xác nhận)
    APPROVING: 'APPROVING',
    DEPOSITING: 'DEPOSITING',
    WAITING_INDEXER: 'WAITING_INDEXER',
    LOCKED: 'LOCKED', // chỉ đặt khi API báo mọi đơn con LOCKED
    FAILED: 'FAILED',
});

/** Mã lỗi nội bộ của luồng (không phải mã API). */
export const FLOW_ERROR = Object.freeze({
    QUOTE_EXPIRING: 'QUOTE_EXPIRING', // còn < 60 giây hoặc đã hết hạn: phải lấy báo giá mới
    INSUFFICIENT_BALANCE: 'INSUFFICIENT_BALANCE',
    QUOTE_MISMATCH: 'QUOTE_MISMATCH', // báo giá không khớp ví/token/tổng: KHÔNG gửi gì lên ví
    BATCH_TOO_LARGE: 'BATCH_TOO_LARGE',
    TX_REVERTED: 'TX_REVERTED',
    ORDER_EXISTS: 'ORDER_EXISTS', // contract báo đơn đã tồn tại: nhiều khả năng lần nạp trước ĐÃ thành công, chỉ cần chờ Indexer
    USER_REJECTED: 'USER_REJECTED', // mã 4001: hủy, không phải lỗi hệ thống
});

export class FlowError extends Error {
    constructor(code, message, extra = {}) {
        super(message);
        this.name = 'FlowError';
        this.code = code;
        this.extra = extra;
    }
}

const initial = Object.freeze({ step: STEP.IDLE, approveTx: null, depositTx: null, error: null, shortfall: null, approveSkipped: false, approved: false, failedStep: null });
export const initialDepositState = () => ({ ...initial });

/**
 * Reducer thuần cho máy trạng thái 9.3. Sự kiện:
 *  START | ALLOWANCE_OK (đủ hạn mức, bỏ APPROVING) | APPROVE_REQUESTED (cửa sổ ví mở) | APPROVE_SENT {hash} | APPROVED
 *  | DEPOSIT_REQUESTED | DEPOSIT_SENT {hash} | DEPOSIT_MINED
 *  | INDEXER_LOCKED | FAIL {error} | RESET
 * Chuyển không hợp lệ bị bỏ qua (trả nguyên state) để một sự kiện muộn/trùng không làm lùi bước.
 */
export function depositReducer(state, event) {
    switch (event.type) {
        case 'START':
            return state.step === STEP.IDLE || state.step === STEP.FAILED ? { ...initial, step: STEP.CHECKING } : state;
        case 'ALLOWANCE_OK':
            return state.step === STEP.CHECKING ? { ...state, approveSkipped: true, approved: true } : state;
        case 'APPROVE_REQUESTED':
            return state.step === STEP.CHECKING ? { ...state, step: STEP.APPROVING } : state;
        case 'APPROVE_SENT':
            return state.step === STEP.APPROVING ? { ...state, approveTx: event.hash } : state;
        case 'APPROVED':
            return state.step === STEP.APPROVING ? { ...state, step: STEP.CHECKING, approved: true } : state; // quay lại để gửi bước 2
        case 'DEPOSIT_REQUESTED':
            return state.step === STEP.CHECKING ? { ...state, step: STEP.DEPOSITING } : state;
        case 'DEPOSIT_SENT':
            return state.step === STEP.DEPOSITING ? { ...state, depositTx: event.hash } : state;
        case 'DEPOSIT_MINED':
            return state.step === STEP.DEPOSITING ? { ...state, step: STEP.WAITING_INDEXER } : state;
        case 'INDEXER_LOCKED':
            return state.step === STEP.WAITING_INDEXER ? { ...state, step: STEP.LOCKED } : state;
        case 'RESUME_WAITING': // lỗi "Order exists": coi như đã nạp, chuyển sang chờ API xác nhận (không bao giờ tự đặt LOCKED)
            return state.step === STEP.FAILED && state.error?.code === FLOW_ERROR.ORDER_EXISTS ? { ...state, step: STEP.WAITING_INDEXER, error: null } : state;
        case 'FAIL':
            if (state.step === STEP.LOCKED || state.step === STEP.IDLE) return state;
            return { ...state, step: STEP.FAILED, failedStep: state.step, error: event.error ?? null, shortfall: event.error?.extra?.shortfall ?? null };
        case 'RESET':
            return initialDepositState();
        default:
            return state;
    }
}

/** Đang có thao tác dở dang với ví/chuỗi: khóa nút, cảnh báo khi rời trang. */
/** Mọi đơn con đã được Indexer ghi nhận (LOCKED hoặc xa hơn, phòng Shipper giao rất nhanh). */
const LOCKED_OR_LATER = ['LOCKED', 'DELIVERED', 'DISPUTED', 'COMPLETED', 'REFUNDED'];
export const groupIsLocked = (g) => Array.isArray(g?.orders) && g.orders.length > 0 && g.orders.every((o) => LOCKED_OR_LATER.includes(o.status));

export const isBusy = (state) => [STEP.CHECKING, STEP.APPROVING, STEP.DEPOSITING, STEP.WAITING_INDEXER].includes(state.step);

// ---------------------------------------------------------------------------------------------------------------
// Báo giá -> tham số contract
// ---------------------------------------------------------------------------------------------------------------

/** `order.quote` (chuỗi số, từ API) -> tuple đúng thứ tự struct Quote. Số tiền là BigInt, KHÔNG bao giờ là Number. */
export function quoteToTuple(q) {
    return [
        BigInt(q.orderId), q.buyer, q.merchant, q.token, BigInt(q.amount),
        BigInt(q.inspectionDuration), BigInt(q.disputeTimeout), BigInt(q.feeBps), q.docHash, BigInt(q.deadline),
    ];
}

/**
 * Kiểm tra báo giá trước khi gửi lên ví. Backend đã ký, nhưng Frontend không gửi tiền theo dữ liệu chưa đối chiếu:
 * sai ví/token/tổng ở đây nghĩa là dữ liệu bị lệch hoặc bị can thiệp -> dừng, không bật cửa sổ ví.
 * Ném FlowError; trả về { total: BigInt, quotes, sigs } khi hợp lệ.
 */
export function validateGroupForDeposit(group, { account, deployment }) {
    const orders = group?.orders ?? [];
    if (orders.length === 0) throw new FlowError(FLOW_ERROR.QUOTE_MISMATCH, 'Lô thanh toán không có đơn nào.');
    if (orders.length > MAX_BATCH_SIZE) throw new FlowError(FLOW_ERROR.BATCH_TOO_LARGE, 'Mỗi lần thanh toán tối đa 5 shop, hãy bỏ bớt sản phẩm.');
    if (!sameAddress(group.token_address, deployment.mockUSD)) {
        throw new FlowError(FLOW_ERROR.QUOTE_MISMATCH, 'Token trong báo giá không phải token ký quỹ của hệ thống. Hãy lấy báo giá mới.');
    }
    let total = 0n;
    const quotes = [];
    const sigs = [];
    for (const o of orders) {
        const q = o.quote;
        if (!q || !o.signature) throw new FlowError(FLOW_ERROR.QUOTE_MISMATCH, 'Thiếu báo giá hoặc chữ ký của một đơn. Hãy lấy báo giá mới.');
        if (!sameAddress(q.buyer, account)) throw new FlowError(FLOW_ERROR.QUOTE_MISMATCH, 'Báo giá này không thuộc ví đang kết nối.');
        if (!sameAddress(q.token, deployment.mockUSD)) throw new FlowError(FLOW_ERROR.QUOTE_MISMATCH, 'Token trong báo giá không khớp hệ thống. Hãy lấy báo giá mới.');
        if (String(q.amount) !== String(o.amount_raw)) throw new FlowError(FLOW_ERROR.QUOTE_MISMATCH, 'Số tiền trong báo giá không khớp. Hãy lấy báo giá mới.');
        quotes.push(quoteToTuple(q));
        sigs.push(o.signature);
        total += BigInt(q.amount);
    }
    if (total !== BigInt(group.total_amount_raw)) {
        throw new FlowError(FLOW_ERROR.QUOTE_MISMATCH, 'Tổng tiền không khớp tổng các đơn. Hãy lấy báo giá mới.');
    }
    return { total, quotes, sigs };
}

// ---------------------------------------------------------------------------------------------------------------
// Lỗi contract/ví -> thông báo (SDD 9.5)
// ---------------------------------------------------------------------------------------------------------------

// Khớp theo lý do revert của SlopeeEscrowMaster/OpenZeppelin; thứ tự quan trọng (cụm cụ thể trước).
const REVERT_MESSAGES = [
    [/Quote expired/i, 'Báo giá đã hết hạn, hãy lấy báo giá mới.'],
    [/Order exists/i, 'Đơn này đã được thanh toán.', FLOW_ERROR.ORDER_EXISTS],
    [/Invalid batch size/i, 'Mỗi lần thanh toán tối đa 5 shop, hãy bỏ bớt sản phẩm.'],
    [/Fee exceeds on-chain cap/i, 'Phí sàn đã thay đổi, hãy lấy báo giá mới.'],
    [/Caller must be quote buyer/i, 'Báo giá này không thuộc ví đang kết nối.'],
    [/Bad quote signature/i, 'Chữ ký báo giá không hợp lệ, hãy lấy báo giá mới.'],
    [/Mixed tokens unsupported/i, 'Lô thanh toán chứa nhiều loại token, hãy lấy báo giá mới.'],
    [/Arbitrator cannot trade/i, 'Tài khoản trọng tài không được giao dịch.'],
    [/Invalid merchant/i, 'Ví của cửa hàng không hợp lệ, hãy báo quản trị viên.'],
    [/ERC20InsufficientBalance|transfer amount exceeds balance/i, 'Số dư mUSD không đủ để thanh toán.'],
    [/ERC20InsufficientAllowance|insufficient allowance/i, 'Hạn mức approve chưa đủ, hãy thử lại từ bước approve.'],
    [/Length mismatch|Zero amount|Invalid duration|Invalid dispute timeout/i, 'Báo giá không hợp lệ, hãy lấy báo giá mới.'],
];

/** Gom mọi chỗ ethers/ví có thể giấu lý do revert thành một chuỗi để so khớp. */
export function revertText(err) {
    const parts = [
        err?.reason, err?.shortMessage, err?.revert?.name, ...(Array.isArray(err?.revert?.args) ? err.revert.args : []),
        err?.info?.error?.message, err?.error?.message, err?.data?.message, err?.message,
    ];
    return parts.filter((p) => typeof p === 'string').join(' | ');
}

/** Lỗi bất kỳ trong luồng nạp -> { code, message, userRejected }. 4001 là hủy, không phải lỗi hệ thống. */
export function mapDepositError(err) {
    if (err instanceof FlowError) return { code: err.code, message: err.message, userRejected: false, extra: err.extra };
    if (isUserRejection(err)) return { code: FLOW_ERROR.USER_REJECTED, message: 'Bạn đã hủy thao tác.', userRejected: true, extra: {} };
    if (err?.code === -32002) return { code: 'REQUEST_PENDING', message: 'Ví đang chờ bạn xác nhận một yêu cầu khác. Hãy mở ví để xử lý.', userRejected: false, extra: {} };
    const text = revertText(err);
    for (const [re, message, code] of REVERT_MESSAGES) if (re.test(text)) return { code: code ?? FLOW_ERROR.TX_REVERTED, message, userRejected: false, extra: {} };
    return { code: FLOW_ERROR.TX_REVERTED, message: 'Giao dịch không thành công. Cả lô chưa được tạo, tiền của bạn không bị trừ. Hãy thử lại.', userRejected: false, extra: {} };
}

// ---------------------------------------------------------------------------------------------------------------
// Điều phối hai bước ví
// ---------------------------------------------------------------------------------------------------------------

/**
 * Chạy CHECK_QUOTE -> CHECK_ALLOWANCE -> APPROVING -> DEPOSITING cho một lô, phát sự kiện qua `dispatch`.
 * Dừng ở DEPOSIT_MINED; WAITING_INDEXER là việc của polling (usePolling) vì chỉ API mới được quyết định LOCKED.
 *
 * @param {object} p
 * @param {object} p.group        phản hồi POST /api/orders hoặc /quote
 * @param {string} p.account      ví đang kết nối
 * @param {object} p.deployment   từ deployments/local.json
 * @param {object} p.token        hợp đồng MockUSD (ethers Contract hoặc đối tượng cùng giao diện)
 * @param {object} p.escrow       hợp đồng SlopeeEscrowMaster
 * @param {() => number} p.remaining   số giây còn lại tới hạn báo giá, theo đồng hồ máy chủ (đọc LẠI ngay trước mỗi bước ví)
 * @param {(e: object) => void} p.dispatch
 * @returns {Promise<{depositHash: string}>}  ném FlowError/lỗi ví nếu thất bại (đã phát FAIL)
 */
export async function runDeposit({ group, account, deployment, token, escrow, remaining, dispatch }) {
    const requireTime = () => {
        if (remaining() < QUOTE_MIN_REMAINING) {
            throw new FlowError(FLOW_ERROR.QUOTE_EXPIRING, remaining() <= 0 ? 'Báo giá đã hết hạn, hãy lấy báo giá mới.' : 'Báo giá sắp hết hạn, hãy lấy báo giá mới rồi thử lại.');
        }
    };
    dispatch({ type: 'START' });
    try {
        const { total, quotes, sigs } = validateGroupForDeposit(group, { account, deployment });
        requireTime(); // CHECK_QUOTE

        const [balance, allowance] = await Promise.all([token.balanceOf(account), token.allowance(account, deployment.escrow)]);
        if (balance < total) {
            const shortfall = total - balance;
            throw new FlowError(FLOW_ERROR.INSUFFICIENT_BALANCE, 'Số dư mUSD không đủ để thanh toán.', { shortfall: shortfall.toString(), total: total.toString(), balance: balance.toString() });
        }

        if (allowance >= total) {
            dispatch({ type: 'ALLOWANCE_OK' }); // CHECK_ALLOWANCE: đủ hạn mức thì bỏ APPROVING
        } else {
            requireTime();
            dispatch({ type: 'APPROVE_REQUESTED' });
            const tx = await token.approve(deployment.escrow, total); // đúng tổng của lô, không approve vô hạn
            dispatch({ type: 'APPROVE_SENT', hash: tx.hash });
            await tx.wait();
            dispatch({ type: 'APPROVED' });
        }

        requireTime(); // approve có thể mất thời gian: kiểm lại hạn trước khi bật cửa sổ ví lần hai
        dispatch({ type: 'DEPOSIT_REQUESTED' });
        const dep = await escrow.depositEscrowBatch(quotes, sigs);
        dispatch({ type: 'DEPOSIT_SENT', hash: dep.hash });
        await dep.wait();
        dispatch({ type: 'DEPOSIT_MINED' });
        return { depositHash: dep.hash };
    } catch (err) {
        dispatch({ type: 'FAIL', error: mapDepositError(err) });
        throw err;
    }
}
