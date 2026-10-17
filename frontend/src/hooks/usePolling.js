// Polling cho trạng thái do máy chủ quyết định (SDD 9.1, 9.8). Không dùng thư viện ngoài.
// Hợp đồng (SDD 9.8): `usePolling(fn, {intervalMs, stopWhen})` dừng khi rời trang, KHÔNG chồng lệnh gọi, dừng khi đạt trạng thái cuối.
import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * @param {(signal: AbortSignal) => Promise<any>} fn   lấy dữ liệu; nhận AbortSignal để hủy khi rời trang
 * @param {object}   [opts]
 * @param {number}   [opts.intervalMs=2500]   chờ giữa HAI lần gọi (tính từ lúc lần trước KẾT THÚC, nên không bao giờ chồng nhau)
 * @param {(data:any)=>boolean} [opts.stopWhen]  trả true thì dừng hẳn (trạng thái cuối)
 * @param {boolean}  [opts.enabled=true]      false: không chạy (ví dụ chưa nạp xong)
 * @param {number}   [opts.maxConsecutiveErrors=Infinity]  quá số lỗi LIÊN TIẾP này thì dừng và báo `error`
 * @returns {{ data:any, error:any, stopped:boolean, polling:boolean, refresh:()=>Promise<void> }}
 *   `error` là lỗi của lần gọi gần nhất (xóa khi lần sau thành công): lỗi mạng tạm thời KHÔNG dừng polling.
 */
export function usePolling(fn, { intervalMs = 2500, stopWhen, enabled = true, maxConsecutiveErrors = Infinity } = {}) {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [stopped, setStopped] = useState(false);
    const [polling, setPolling] = useState(false);

    // Luôn dùng bản fn/stopWhen MỚI NHẤT mà không khởi động lại vòng lặp mỗi lần render
    const fnRef = useRef(fn);
    const stopRef = useRef(stopWhen);
    useEffect(() => { fnRef.current = fn; stopRef.current = stopWhen; });

    const inFlight = useRef(false);
    const kick = useRef(null); // gọi ngay một lượt (cho refresh)

    useEffect(() => {
        if (!enabled) return undefined;
        let cancelled = false;
        let timer = null;
        let errors = 0;
        const controller = new AbortController();
        setStopped(false);
        setPolling(true);

        const tick = async () => {
            if (cancelled || inFlight.current) return;
            inFlight.current = true;
            let done = false;
            try {
                const result = await fnRef.current(controller.signal);
                if (cancelled) return;
                errors = 0;
                setData(result);
                setError(null);
                if (stopRef.current?.(result)) done = true;
            } catch (e) {
                if (cancelled || e?.name === 'AbortError') return;
                errors += 1;
                setError(e);
                if (errors >= maxConsecutiveErrors) done = true;
            } finally {
                inFlight.current = false;
            }
            if (cancelled) return;
            if (done) {
                setStopped(true);
                setPolling(false);
                return;
            }
            timer = setTimeout(tick, intervalMs);
        };

        kick.current = () => {
            if (inFlight.current || cancelled) return Promise.resolve();
            clearTimeout(timer);
            return tick();
        };
        tick();

        return () => {
            cancelled = true;
            clearTimeout(timer);
            controller.abort();
            inFlight.current = false;
            kick.current = null;
            setPolling(false);
        };
    }, [enabled, intervalMs, maxConsecutiveErrors]);

    const refresh = useCallback(() => (kick.current ? kick.current() : Promise.resolve()), []);
    return { data, error, stopped, polling, refresh };
}
