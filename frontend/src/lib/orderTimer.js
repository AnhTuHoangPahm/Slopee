// Hàm thuần cho màn hình đơn Web3 của Buyer (SDD 9.3, 9.4, SRS 8). Không I/O, không đọc đồng hồ máy ngầm định.
// Mốc thời gian lấy từ GET /api/orders/:code/status: delivered_at, inspection_duration, server_time (= now_chain()).
// Đếm ngược tính theo ĐỒNG HỒ MÁY CHỦ (F-06) nên đúng cả khi đồng hồ máy người dùng sai hoặc Anvil bị tua thời gian.
import { secondsRemaining } from './web3Checkout';

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
 * Số giây còn lại của thời hạn kiểm tra theo đồng hồ máy chủ; null khi chưa giao hoặc chưa có đồng hồ (chưa poll lần nào).
 * `clock` = { serverTime, receivedAtMs } của LẦN POLL GẦN NHẤT.
 */
export function inspectionRemaining(status, clock, nowMs = Date.now()) {
    const deadline = inspectionDeadline(status);
    if (deadline === null || !clock || clock.serverTime == null) return null;
    return secondsRemaining({ deadline, serverTime: clock.serverTime, receivedAtMs: clock.receivedAtMs, nowMs });
}

/** 'AWAITING_DELIVERY' | 'SYNCING' | 'INSPECTING' | 'INSPECTION_OVER' | 'DISPUTED' | 'COMPLETED' | 'REFUNDED' | 'PENDING_PAYMENT' | 'EXPIRED' */
export function orderPhase(statusName, remaining) {
    switch (statusName) {
        case ORDER_STATUS.LOCKED: return 'AWAITING_DELIVERY';
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
