// Hàm thuần cho màn hình đơn Web3 của Buyer (SDD 9.3, 9.4, SRS 8). Không I/O, không đọc đồng hồ máy ngầm định.
// Mốc thời gian lấy từ GET /api/orders/:code/status: delivered_at, inspection_duration, server_time (= now_chain()).
// Đếm ngược tính theo ĐỒNG HỒ MÁY CHỦ (F-06) nên đúng cả khi đồng hồ máy người dùng sai hoặc Anvil bị tua thời gian.
import { remainingSec } from './serverClock';

export const ORDER_STATUS = Object.freeze({
    PENDING_PAYMENT: 'PENDING_PAYMENT',
    EXPIRED: 'EXPIRED',
    LOCKED: 'LOCKED',
    DELIVERED: 'DELIVERED',
    DISPUTED: 'DISPUTED',
    COMPLETED: 'COMPLETED',
    REFUNDED: 'REFUNDED',
});

/** Trạng thái cuối: polling dừng hẳn (F-05). */
export const isTerminalStatus = (s) => s === ORDER_STATUS.COMPLETED || s === ORDER_STATUS.REFUNDED || s === ORDER_STATUS.EXPIRED;
/** Có chuyển trạng thái do chuỗi/Shipper/Indexer gây ra nên cần polling. PENDING_PAYMENT thuộc màn hình thanh toán. */
export const needsPolling = (s) => s === ORDER_STATUS.LOCKED || s === ORDER_STATUS.DELIVERED || s === ORDER_STATUS.DISPUTED;

/** Hạn kiểm tra (giây UTC) = delivered_at + inspection_duration; null nếu chưa giao. */
export function inspectionDeadline(status) {
    if (status?.delivered_at == null || status?.inspection_duration == null) return null;
    return Number(status.delivered_at) + Number(status.inspection_duration);
}

/**
 * Số giây NGUYÊN còn lại của thời hạn kiểm tra theo đồng hồ máy chủ ước lượng (`offset` của lib/serverClock: chỉ tăng nên kết quả không
 * giật lùi); null khi chưa giao hoặc chưa có độ lệch (chưa poll lần nào). Làm tròn XUỐNG để nút "Khiếu nại" khóa sớm chứ không muộn.
 */
export function inspectionRemainingAt(status, offset, nowMs = Date.now()) {
    const deadline = inspectionDeadline(status);
    if (deadline === null) return null;
    const r = remainingSec(deadline, offset, nowMs);
    return r === null ? null : Math.floor(r);
}

// ---- Hủy đơn quá hạn giao hàng (UC-07 kịch bản 1, BR-05, T-14) --------------------------------------------------------------------------
// Contract: `cancelIfUnfulfilled` chỉ chạy khi đơn còn LOCKED và `block.timestamp >= createdAt + DELIVERY_TIMEOUT` (14 ngày), do Buyer (hoặc Admin) gọi.
// `createdAt` của contract = giờ block lúc ký quỹ = `order_web3.chain_created_at` (API trạng thái và tóm tắt đơn đều trả về).
export const DELIVERY_TIMEOUT_SEC = 14 * 24 * 3600;   // = SlopeeEscrowMaster.DELIVERY_TIMEOUT

/** Mốc (giây UTC) từ đó Buyer được hủy đơn chưa giao; null nếu chưa biết `chain_created_at`. */
export function deliveryDeadline(source) {
    const created = source?.chain_created_at;
    if (created === null || created === undefined) return null;
    const n = Number(created);
    return Number.isFinite(n) && n > 0 ? n + DELIVERY_TIMEOUT_SEC : null;
}

/**
 * Số giây NGUYÊN còn tới mốc hủy theo đồng hồ máy chủ ước lượng (cùng `offset` với đồng hồ kiểm tra); null khi chưa biết mốc hoặc chưa có độ lệch.
 * Làm tròn LÊN (ngược với `inspectionRemainingAt`): nút "Hủy đơn" chỉ bật khi chắc chắn contract đã chấp nhận (`>=` mốc), không bật sớm một giây.
 */
export function deliveryRemainingAt(source, offset, nowMs = Date.now()) {
    const deadline = deliveryDeadline(source);
    if (deadline === null) return null;
    const r = remainingSec(deadline, offset, nowMs);
    return r === null ? null : Math.ceil(r);
}

/** Nút "Hủy đơn" bật khi đơn còn LOCKED và đã tới mốc 14 ngày (`deliveryRemaining <= 0`). Chưa biết đồng hồ thì chưa bật (không đoán theo giờ máy khách). */
export function canCancelUnfulfilled(statusName, deliveryRemaining) {
    return statusName === ORDER_STATUS.LOCKED && deliveryRemaining !== null && deliveryRemaining !== undefined && deliveryRemaining <= 0;
}

// ---- Polling thích ứng (PROGRESS Tuần 5 mục 11) -------------------------------------------------------------------------------------------
// Thời hạn kiểm tra kéo dài 1-3 ngày nên không cần hỏi 3 giây/lần suốt thời gian đó; nhưng khi sắp/đã hết hạn thì phải bắt chuyển trạng thái ngay.
// Sau hạn, đơn không sang COMPLETED tức thì: tác vụ AutoRelease chạy mỗi AUTO_RELEASE_SECONDS (mặc định 60 giây) rồi Indexer cần ~2 giây,
// nên từ lúc `remaining = 0` đến COMPLETED có thể mất tới ~65 giây.
export const POLL_MS = Object.freeze({ FAST: 3000, SLOW: 15000 });
export const NEAR_DEADLINE_SEC = 10;       // còn ≤ chừng này giây thì poll nhanh
export const OVERDUE_FAST_SEC = 120;       // quá hạn tới chừng này giây vẫn poll nhanh (65 giây + dự phòng); lâu hơn thì giãn lại, tránh dồn tải khi AutoRelease hỏng
export const BOOST_MS = 60_000;            // sau thao tác ví của người dùng: poll nhanh chừng này mili giây

/**
 * Chờ bao lâu (ms) trước lần poll kế tiếp. Hàm thuần, `remaining` tính tại thời điểm xếp lịch.
 *  - vừa thao tác ví (`boosted`), chưa có dữ liệu, hoặc đơn chưa ổn định (PENDING_PAYMENT): nhanh;
 *  - DELIVERED còn nhiều thời gian: chậm, nhưng không ngủ quá mốc `NEAR_DEADLINE_SEC` trước hạn (dậy đúng lúc để chuyển sang nhanh);
 *  - DELIVERED sắp/đã hết hạn (tới OVERDUE_FAST_SEC): nhanh để thấy COMPLETED/DISPUTED ngay khi Indexer ghi;
 *  - LOCKED/DISPUTED (chờ Shipper/Admin, có thể hàng giờ): chậm.
 */
export function nextPollDelayMs(statusName, remaining, { boosted = false, fast = POLL_MS.FAST, slow = POLL_MS.SLOW } = {}) {
    if (boosted || !statusName || statusName === ORDER_STATUS.PENDING_PAYMENT) return fast;
    if (statusName !== ORDER_STATUS.DELIVERED) return slow;
    if (remaining === null || remaining === undefined) return fast;               // chưa đồng bộ giờ: hỏi nhanh để có độ lệch
    if (remaining > NEAR_DEADLINE_SEC) return Math.min(slow, Math.max(fast, (remaining - NEAR_DEADLINE_SEC) * 1000));
    return remaining >= -OVERDUE_FAST_SEC ? fast : slow;
}

/** 'AWAITING_DELIVERY' | 'DELIVERY_OVERDUE' (LOCKED quá 14 ngày chưa giao, Buyer hủy được) | 'SYNCING' | 'INSPECTING' | 'INSPECTION_OVER' | 'DISPUTED' | 'COMPLETED' | 'REFUNDED' | 'PENDING_PAYMENT' | 'EXPIRED' */
export function orderPhase(statusName, remaining, deliveryRemaining = null) {
    switch (statusName) {
        case ORDER_STATUS.LOCKED: return canCancelUnfulfilled(statusName, deliveryRemaining) ? 'DELIVERY_OVERDUE' : 'AWAITING_DELIVERY';
        case ORDER_STATUS.DELIVERED:
            if (remaining === null || remaining === undefined) return 'SYNCING';
            return remaining > 0 ? 'INSPECTING' : 'INSPECTION_OVER';
        default: return statusName;
    }
}

/**
 * Nút nào được bật (SDD 9.4): "Đã nhận hàng" (earlyRelease) hợp lệ suốt trạng thái DELIVERED (contract không đòi còn hạn);
 * "Khiếu nại" (raiseDispute) chỉ khi còn hạn kiểm tra: đếm về 0 thì khóa nút, nhưng contract vẫn là bên quyết định cuối.
 * Chưa biết đồng hồ (remaining = null) thì chưa cho khiếu nại, tránh bật nút theo đồng hồ máy khách.
 */
export function availableActions(statusName, remaining) {
    const delivered = statusName === ORDER_STATUS.DELIVERED;
    return {
        earlyRelease: delivered,
        dispute: delivered && remaining !== null && remaining !== undefined && remaining > 0,
    };
}

const pad = (n) => String(n).padStart(2, '0');

/** 90 -> "00:01:30"; 183909 -> "2 ngày 03:05:09". Số âm coi như 0. */
export function formatInspectionCountdown(remaining) {
    const s = Math.max(0, Math.floor(Number(remaining) || 0));
    const days = Math.floor(s / 86400);
    const hms = `${pad(Math.floor((s % 86400) / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
    return days > 0 ? `${days} ngày ${hms}` : hms;
}

/**
 * Cổng ví cho thao tác on-chain của Buyer (giống cổng của màn thanh toán): chỉ ví ĐÃ KÝ QUỸ đơn này mới gọi được
 * earlyRelease/raiseDispute (contract: "Only buyer"). Kiểm trước để không tốn một giao dịch rồi mới nhận revert.
 * @returns 'OK' | 'NOT_CONNECTED' | 'WRONG_CHAIN' | 'WRONG_ACCOUNT'
 */
export function walletGate({ isConnected, isCorrectChain, account, buyerWallet }) {
    if (!isConnected || !account) return 'NOT_CONNECTED';
    if (!isCorrectChain) return 'WRONG_CHAIN';
    if (buyerWallet && account.toLowerCase() !== String(buyerWallet).toLowerCase()) return 'WRONG_ACCOUNT';
    return 'OK';
}
