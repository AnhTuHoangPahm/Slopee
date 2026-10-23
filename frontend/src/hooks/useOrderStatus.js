// Trạng thái một đơn Web3 qua polling (SDD 9.1, 9.4, DD-04) + đồng hồ đếm ngược theo giờ MÁY CHỦ (F-06).
//
// Đồng hồ (PROGRESS Tuần 5 mục 10): mỗi lần poll nhận `server_time`, nhưng KHÔNG ghi đè mốc neo. `lib/serverClock` chỉ giữ độ lệch lớn nhất
// giữa `server_time` và giờ máy (server_time luôn cũ hơn giờ thật 0-2 giây, nên mẫu lớn nhất là ước lượng tốt nhất), nhờ đó đếm ngược không giật
// lùi dù `server_time` có răng cưa (Anvil đã tua giờ) hay độ trễ mạng biến thiên; đồng hồ máy người dùng sai cũng không ảnh hưởng.
// Độ lệch được cập nhật NGAY TRONG hàm poll, cùng nhịp với dữ liệu.
//
// Chu kỳ poll (mục 11): thích ứng theo trạng thái, xem `nextPollDelayMs`. `intervalMs` là số thì cố định (dùng cho test). Dừng khi đơn tới trạng
// thái cuối hoặc khi rời trang.
import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchOrderStatusAPI } from '../api/web3';
import { createServerClock } from '../lib/serverClock';
import { BOOST_MS, inspectionRemainingAt, isTerminalStatus, nextPollDelayMs } from '../lib/orderTimer';
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

// Tick 2 lần/giây: số giây nguyên hiển thị đổi đúng lúc qua mốc thật (không bỏ sót, không lặp) kể cả khi setInterval trễ nhịp.
const TICK_MS = 500;

/**
 * @param {string} orderCode  `orders.id`
 * @param {object} [opts]
 * @param {boolean} [opts.enabled=true]
 * @param {number}  [opts.intervalMs]  số: chu kỳ cố định (test); bỏ trống: thích ứng theo trạng thái
 * @param {Function} [opts.fetchStatus]  thay cho fetchOrderStatusAPI (chỉ dùng khi test)
 * @returns {{ status: object|null, error, stopped: boolean, offset: number|null, remaining: number|null, boost: Function, refresh: Function }}
 *   `remaining`: số giây nguyên còn của hạn kiểm tra, null khi chưa giao hoặc chưa có lần poll nào.
 *   `boost(ms?)`: gọi ngay sau thao tác ví (earlyRelease, raiseDispute) để poll nhanh trong `ms` (mặc định BOOST_MS) và hỏi lại tức thì.
 */
export function useOrderStatus(orderCode, { enabled = true, intervalMs, fetchStatus = fetchOrderStatusAPI } = {}) {
    const clockRef = useRef(null);
    if (clockRef.current === null) clockRef.current = createServerClock();
    const boostUntilRef = useRef(0);
    const [sample, setSample] = useState({ offset: null, atMs: 0 });   // cùng nhịp với `data` (cùng một lô cập nhật)

    const delay = useCallback((st) => {
        if (typeof intervalMs === 'number') return intervalMs;
        const now = Date.now();
        return nextPollDelayMs(st?.status, st ? inspectionRemainingAt(st, clockRef.current.offset, now) : null, { boosted: now < boostUntilRef.current });
    }, [intervalMs]);

    const poll = usePolling(
        async (signal) => {
            const st = await fetchStatus(orderCode, signal);
            const atMs = Date.now();
            if (st?.server_time != null) setSample({ offset: clockRef.current.observe(Number(st.server_time), atMs), atMs });
            return st;
        },
        { intervalMs: delay, enabled: enabled && Boolean(orderCode), stopWhen: (st) => isTerminalStatus(st?.status) },
    );
    const { refresh } = poll;
    const boost = useCallback((ms = BOOST_MS) => {
        boostUntilRef.current = Date.now() + ms;
        return refresh();
    }, [refresh]);

    const status = poll.data;
    const ticking = Boolean(status) && status.delivered_at != null && !poll.stopped;
    const nowMs = useNow(ticking, TICK_MS);
    return {
        status,
        error: poll.error,
        stopped: poll.stopped,
        offset: sample.offset,
        // nowMs có thể "cũ" hơn lần poll gần nhất (vừa bật tick): không để thời gian trôi âm làm đếm ngược nhảy lên
        remaining: status ? inspectionRemainingAt(status, sample.offset, Math.max(nowMs, sample.atMs)) : null,
        boost,
        refresh,
    };
}
