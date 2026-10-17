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
