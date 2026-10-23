import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { usePolling } from '../hooks/usePolling';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());
const tick = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

describe('usePolling (SDD 9.8)', () => {
    it('gọi ngay, rồi lặp theo chu kỳ; trả dữ liệu mới nhất', async () => {
        let n = 0;
        const fn = vi.fn(async () => ++n);
        const { result } = renderHook(() => usePolling(fn, { intervalMs: 1000 }));
        await tick(0);
        expect(result.current.data).toBe(1);
        await tick(1000);
        expect(result.current.data).toBe(2);
        await tick(2000);
        expect(fn).toHaveBeenCalledTimes(4);
    });

    it('dừng khi stopWhen đúng (trạng thái cuối) và không gọi thêm', async () => {
        let n = 0;
        const fn = vi.fn(async () => ({ status: ++n >= 3 ? 'LOCKED' : 'PENDING' }));
        const { result } = renderHook(() => usePolling(fn, { intervalMs: 1000, stopWhen: (d) => d.status === 'LOCKED' }));
        await tick(5000);
        expect(fn).toHaveBeenCalledTimes(3);
        expect(result.current.stopped).toBe(true);
        expect(result.current.data.status).toBe('LOCKED');
        await tick(10_000);
        expect(fn).toHaveBeenCalledTimes(3);
    });

    it('KHÔNG chồng lệnh: lần gọi chậm hơn chu kỳ thì chờ xong mới đếm giờ cho lần sau', async () => {
        let running = 0; let maxRunning = 0;
        const fn = vi.fn(async () => {
            running += 1; maxRunning = Math.max(maxRunning, running);
            await new Promise((r) => setTimeout(r, 3000));
            running -= 1;
            return 1;
        });
        renderHook(() => usePolling(fn, { intervalMs: 1000 }));
        await tick(10_000);
        expect(maxRunning).toBe(1);
    });

    it('dừng khi rời trang (unmount): hủy timer và báo hủy qua AbortSignal', async () => {
        let signal;
        const fn = vi.fn(async (s) => { signal = s; return 1; });
        const { unmount } = renderHook(() => usePolling(fn, { intervalMs: 1000 }));
        await tick(0);
        unmount();
        expect(signal.aborted).toBe(true);
        await tick(10_000);
        expect(fn).toHaveBeenCalledTimes(1);
    });

    it('lỗi tạm thời không dừng polling; lần sau thành công thì xóa lỗi', async () => {
        let n = 0;
        const fn = vi.fn(async () => { if (++n === 2) throw new Error('mạng'); return n; });
        const { result } = renderHook(() => usePolling(fn, { intervalMs: 1000 }));
        await tick(1000);
        expect(result.current.error?.message).toBe('mạng');
        expect(result.current.stopped).toBe(false);
        await tick(1000);
        expect(result.current.error).toBeNull();
        expect(result.current.data).toBe(3);
    });

    it('maxConsecutiveErrors: quá số lỗi liên tiếp thì dừng và giữ lỗi', async () => {
        const fn = vi.fn(async () => { throw new Error('down'); });
        const { result } = renderHook(() => usePolling(fn, { intervalMs: 1000, maxConsecutiveErrors: 3 }));
        await tick(10_000);
        expect(fn).toHaveBeenCalledTimes(3);
        expect(result.current.stopped).toBe(true);
        expect(result.current.error.message).toBe('down');
    });

    it('enabled=false thì không gọi; bật lên mới chạy', async () => {
        const fn = vi.fn(async () => 1);
        const { rerender } = renderHook(({ on }) => usePolling(fn, { intervalMs: 1000, enabled: on }), { initialProps: { on: false } });
        await tick(5000);
        expect(fn).not.toHaveBeenCalled();
        rerender({ on: true });
        await tick(0);
        expect(fn).toHaveBeenCalledTimes(1);
    });
});

describe('usePolling: chu kỳ động (intervalMs là hàm)', () => {
    it('hàm được gọi lúc xếp lịch với dữ liệu thành công gần nhất (null ở lần đầu) và quyết định chu kỳ kế', async () => {
        let n = 0;
        const fn = vi.fn(async () => ++n);
        const seen = [];
        const interval = vi.fn((d) => { seen.push(d); return d === null ? 100 : d < 3 ? 1000 : 5000; });
        renderHook(() => usePolling(fn, { intervalMs: interval }));
        await tick(0);                      // lần 1 ngay lập tức
        await tick(99);
        expect(fn).toHaveBeenCalledTimes(1);
        expect(seen[0]).toBe(1);            // đã gọi sau lần 1 với data = 1 (<3) => chờ 1000 ms
        await tick(1000);
        expect(fn).toHaveBeenCalledTimes(2);
        await tick(1000);
        expect(fn).toHaveBeenCalledTimes(3);
        // đang ở t = 2099 ms, lần 3 chạy lúc t = 2000 với data = 3 => chờ 5000 ms => lần 4 lúc t = 7000
        await tick(4900);                   // t = 6999
        expect(fn).toHaveBeenCalledTimes(3);
        await tick(1);                      // t = 7000
        expect(fn).toHaveBeenCalledTimes(4);
    });

    it('lần gọi đầu thất bại: hàm nhận null (chưa có dữ liệu)', async () => {
        const fn = vi.fn(async () => { throw new Error('mạng'); });
        const interval = vi.fn(() => 200);
        renderHook(() => usePolling(fn, { intervalMs: interval, maxConsecutiveErrors: 50 }));
        await tick(0);
        expect(interval).toHaveBeenCalledWith(null);
        await tick(200);
        expect(fn).toHaveBeenCalledTimes(2);
    });

    it('hàm đổi danh tính mỗi lần render KHÔNG khởi động lại vòng lặp (không có lần gọi dư)', async () => {
        const fn = vi.fn(async () => 1);
        const { rerender } = renderHook(() => usePolling(fn, { intervalMs: () => 1000 }));   // hàm mới ở mỗi render
        await tick(0);
        expect(fn).toHaveBeenCalledTimes(1);
        for (let i = 0; i < 5; i += 1) rerender();
        await tick(500);
        expect(fn).toHaveBeenCalledTimes(1);                                                  // vẫn chỉ 1: không restart
        await tick(500);
        expect(fn).toHaveBeenCalledTimes(2);
    });

    it('hàm đọc giá trị MỚI NHẤT (qua ref) mà không cần khởi động lại', async () => {
        const fn = vi.fn(async () => 1);
        let ms = 1000;
        renderHook(() => usePolling(fn, { intervalMs: () => ms }));
        await tick(0);
        ms = 200;                                                                              // đổi chu kỳ giữa chừng
        await tick(1000);                                                                      // lần 2 theo chu kỳ cũ (đã xếp lịch)
        expect(fn).toHaveBeenCalledTimes(2);
        await tick(200);                                                                       // từ đây theo chu kỳ mới
        expect(fn).toHaveBeenCalledTimes(3);
    });

    it.each([[NaN], [-5], [undefined], [null], ['abc'], [Infinity]])('giá trị chu kỳ hỏng (%s) quay về mặc định 2500 ms, không quay với chu kỳ 0', async (bad) => {
        const fn = vi.fn(async () => 1);
        renderHook(() => usePolling(fn, { intervalMs: () => bad }));
        await tick(0);
        await tick(2400);
        expect(fn).toHaveBeenCalledTimes(1);
        await tick(100);
        expect(fn).toHaveBeenCalledTimes(2);
    });

    it('chu kỳ là số vẫn hoạt động như cũ', async () => {
        const fn = vi.fn(async () => 1);
        renderHook(() => usePolling(fn, { intervalMs: 700 }));
        await tick(0);
        await tick(700);
        await tick(700);
        expect(fn).toHaveBeenCalledTimes(3);
    });
});

