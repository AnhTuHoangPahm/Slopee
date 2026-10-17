// Trạng thái một đơn Web3 qua polling 2-3 giây (SDD 9.1, 9.4, DD-04) + đồng hồ đếm ngược theo giờ MÁY CHỦ.
// Mỗi lần poll trả `server_time`; hook nhớ thời điểm máy khách nhận để tính độ lệch, nên đồng hồ máy người dùng sai
// hay Anvil bị tua thời gian đều không làm lệch đếm ngược (F-06). Dừng khi đơn tới trạng thái cuối hoặc khi rời trang.
import { useEffect, useState } from 'react';
import { fetchOrderStatusAPI } from '../api/web3';
import { isTerminalStatus, inspectionRemaining } from '../lib/orderTimer';
import { usePolling } from './usePolling';

/** Đồng hồ máy khách nhảy mỗi `everyMs` khi `active`, để giao diện đếm từng giây. */
export function useNow(active, everyMs = 1000) {
    const [nowMs, setNowMs] = useState(() => Date.now());
    useEffect(() => {
        if (!active) return undefined;
        const id = setInterval(() => setNowMs(Date.now()), everyMs);
        return () => clearInterval(id);
    }, [active, everyMs]);
    return nowMs;
}

/**
 * @param {string} orderCode  `orders.id`
 * @param {object} [opts]
 * @param {boolean} [opts.enabled=true]
 * @param {number}  [opts.intervalMs=3000]
 * @param {Function} [opts.fetchStatus]  thay cho fetchOrderStatusAPI (chỉ dùng khi test)
 * @returns {{ status: object|null, error, stopped: boolean, clock: {serverTime:number, receivedAtMs:number}|null, remaining: number|null, refresh: Function }}
 *   `remaining`: số giây còn của hạn kiểm tra, null khi chưa giao hoặc chưa có lần poll nào.
 */
export function useOrderStatus(orderCode, { enabled = true, intervalMs = 3000, fetchStatus = fetchOrderStatusAPI } = {}) {
    const [clock, setClock] = useState(null);
    const poll = usePolling(
        async (signal) => {
            const st = await fetchStatus(orderCode, signal);
            setClock({ serverTime: Number(st.server_time), receivedAtMs: Date.now() });
            return st;
        },
        { intervalMs, enabled: enabled && Boolean(orderCode), stopWhen: (st) => isTerminalStatus(st?.status) },
    );
    const status = poll.data;
    const ticking = Boolean(status) && status.delivered_at != null && !poll.stopped;
    const nowMs = useNow(ticking);
    return {
        status,
        error: poll.error,
        stopped: poll.stopped,
        clock,
        // nowMs có thể "cũ" hơn lần poll gần nhất (vừa bật tick): không để thời gian trôi âm làm đếm ngược nhảy lên
        remaining: status ? inspectionRemaining(status, clock, Math.max(nowMs, clock?.receivedAtMs ?? 0)) : null,
        refresh: poll.refresh,
    };
}
