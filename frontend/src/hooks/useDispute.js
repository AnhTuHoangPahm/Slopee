// Đề xuất phán quyết của MỘT đơn qua polling + đồng hồ theo giờ máy chủ (hạn ký). Polling thích ứng: đang có đề xuất cần theo dõi thì
// 3 giây (SDD 2-3 giây), chưa có đề xuất / đã hết hạn (có thể chờ hàng ngày) thì 10 giây. Dừng hẳn khi đơn đã được thi hành.
import { useState } from 'react';
import { fetchDisputeAPI } from '../api/disputes';
import { nextOffset, remainingSec } from '../lib/serverClock';
import { DISPUTE_STATUS } from '../lib/disputeSign';
import { useNow } from './useOrderStatus';
import { usePolling } from './usePolling';

export const FAST_POLL_MS = 3000;
export const SLOW_POLL_MS = 10000;

export const isDisputeFinished = (d) => Boolean(d) && (d.resolution?.status === DISPUTE_STATUS.EXECUTED || ['COMPLETED', 'REFUNDED'].includes(d.order_status));
/** Chu kỳ poll kế tiếp theo dữ liệu vừa nhận. */
export function pollIntervalFor(d, fastMs = FAST_POLL_MS, slowMs = SLOW_POLL_MS) {
    const s = d?.resolution?.status;
    return s === DISPUTE_STATUS.PROPOSED || s === DISPUTE_STATUS.READY || s === DISPUTE_STATUS.SUBMITTED ? fastMs : slowMs;
}

/**
 * @param {string} orderCode
 * @param {{ enabled?: boolean, fetchDispute?: Function, fastMs?: number, slowMs?: number }} [opts]  `fetchDispute`, `fastMs`, `slowMs` chỉ để test
 * @returns {{ data: object|null, error: any, loaded: boolean, stopped: boolean, nowSec: number|null, deadlineRemaining: number|null, refresh: Function }}
 */
export function useDispute(orderCode, { enabled = true, fetchDispute = fetchDisputeAPI, fastMs = FAST_POLL_MS, slowMs = SLOW_POLL_MS } = {}) {
    const [offset, setOffset] = useState(null);
    const [intervalMs, setIntervalMs] = useState(fastMs);
    const poll = usePolling(
        async (signal) => {
            const d = await fetchDispute(orderCode, signal);
            setOffset((prev) => nextOffset(prev, d.server_time, Date.now()));
            setIntervalMs(pollIntervalFor(d, fastMs, slowMs));
            return d;
        },
        { intervalMs, enabled: enabled && Boolean(orderCode), stopWhen: isDisputeFinished },
    );
    const data = poll.data;
    const ticking = Boolean(data) && !poll.stopped;
    const nowMs = useNow(ticking);
    const nowSec = offset === null ? null : nowMs / 1000 + offset;
    return {
        data,
        error: poll.error,
        loaded: Boolean(data),
        stopped: poll.stopped,
        nowSec,
        deadlineRemaining: data?.resolution ? remainingSec(data.resolution.deadline, offset, nowMs) : null,
        refresh: poll.refresh,
    };
}
