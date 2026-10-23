// useOrderStatus: đồng hồ đếm ngược không giật lùi + polling thích ứng (PROGRESS Tuần 5 mục 10, 11). Đồng hồ giả, không chờ thật.
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useOrderStatus } from '../hooks/useOrderStatus';
import { BOOST_MS, POLL_MS } from '../lib/orderTimer';
import { secondsRemaining } from '../lib/web3Checkout';

const T0 = 1_700_000_000_000;                       // giờ máy khách lúc bắt đầu (ms)
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(T0); });
afterEach(() => vi.useRealTimers());
const tick = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

/**
 * Máy chủ giả: giờ chuỗi = giờ máy + `ahead` giây (ahead lớn = Anvil đã tua tiến). `server_time` đi theo nấc block `blockSec` giây (cũ 0..blockSec-1 giây),
 * đúng như HybridClock.now_chain khi chuỗi chạy trước đồng hồ hệ thống (PROGRESS mục 10: đo được dao động 1,5 giây).
 */
function chainServer({ ahead = 0, blockSec = 2, deliveredAgo = 300, duration = 600, status = 'DELIVERED' } = {}) {
    const chainNow = () => Date.now() / 1000 + ahead;
    const deliveredAt = Math.floor(chainNow()) - deliveredAgo;
    const calls = [];
    const state = { status };
    const fetchStatus = vi.fn(async () => {
        calls.push(Date.now() - T0);
        const delivered = state.status === 'LOCKED' ? null : deliveredAt;
        return { order_id: 'o1', status: state.status, delivered_at: delivered, inspection_duration: duration, server_time: Math.floor(chainNow() / blockSec) * blockSec };
    });
    return { fetchStatus, calls, state, chainNow, deadline: deliveredAt + duration };
}

describe('đồng hồ đếm ngược', () => {
    it.each([2, 4])('chuỗi bị tua tiến (server_time theo nấc %i giây): số giây còn lại KHÔNG BAO GIỜ tăng, và tiến theo thời gian thật', async (blockSec) => {
        const srv = chainServer({ ahead: 3 * 86400, blockSec });
        const { result } = renderHook(() => useOrderStatus('o1', { fetchStatus: srv.fetchStatus, intervalMs: 3000 }));
        await tick(0);
        const series = [];
        for (let t = 0; t < 180_000; t += 500) { series.push(result.current.remaining); await tick(500); }
        for (let i = 1; i < series.length; i += 1) {
            expect(series[i]).toBeLessThanOrEqual(series[i - 1]);                 // không giật lùi
            expect(series[i - 1] - series[i]).toBeLessThanOrEqual(blockSec);      // không nhảy cóc quá một nấc block (nhịp tick 0,5 giây + hiệu chỉnh độ lệch)
        }
        const truth = srv.deadline - srv.chainNow();
        expect(Math.abs(result.current.remaining - truth)).toBeLessThanOrEqual(blockSec + 1);   // cũ tối đa một nấc block + làm tròn
        expect(series.every(Number.isInteger)).toBe(true);
    });

    it('ĐỐI CHỨNG: cách cũ (ghi đè mốc neo mỗi lần poll) trên cùng kịch bản thì GIẬT LÙI, nên test trên có ý nghĩa', async () => {
        const srv = chainServer({ ahead: 3 * 86400, blockSec: 4 });
        let anchor = null; let legacyPrev = Infinity; let backwards = 0;
        const { result } = renderHook(() => useOrderStatus('o1', {
            intervalMs: 3000,
            fetchStatus: async (...a) => { const st = await srv.fetchStatus(...a); anchor = { serverTime: st.server_time, receivedAtMs: Date.now() }; return st; },
        }));
        await tick(0);
        for (let t = 0; t < 180_000; t += 500) {
            const legacy = secondsRemaining({ deadline: srv.deadline, ...anchor, nowMs: Date.now() });   // đúng công thức cũ của useOrderStatus
            expect(Number.isFinite(legacy)).toBe(true);                                                 // chống NaN làm phép so sánh luôn sai mà không báo
            if (legacy > legacyPrev) backwards += 1;
            legacyPrev = legacy;
            await tick(500);
        }
        expect(backwards).toBeGreaterThan(0);                                    // cách cũ có lần nhảy lùi
        expect(result.current.remaining).not.toBeNull();
    });

    it('đồng hồ máy người dùng sai nhiều năm vẫn đúng (chỉ dùng chênh lệch, không dùng giờ tuyệt đối)', async () => {
        vi.setSystemTime(new Date('2031-03-03T03:03:03Z'));
        const srv = chainServer({ ahead: -10 * 365 * 86400 });                   // giờ chuỗi cách giờ máy 10 năm
        const { result } = renderHook(() => useOrderStatus('o1', { fetchStatus: srv.fetchStatus, intervalMs: 3000 }));
        await tick(0);
        expect(Math.abs(result.current.remaining - 300)).toBeLessThanOrEqual(2);
        await tick(60_000);
        expect(Math.abs(result.current.remaining - 240)).toBeLessThanOrEqual(3);
    });

    it('mỗi lần render có dữ liệu đã kèm đồng hồ (không có nhịp "có status mà chưa có đồng hồ", nguyên nhân test AdminDisputes từng chập chờn)', async () => {
        const srv = chainServer({ ahead: 86400 });
        const renders = [];
        renderHook(() => { const r = useOrderStatus('o1', { fetchStatus: srv.fetchStatus, intervalMs: 3000 }); renders.push(r); return r; });
        for (let t = 0; t < 20_000; t += 500) await tick(500);          // bước từng nhịp: một tick lớn trong act chỉ gộp thành MỘT lần render
        const withData = renders.filter((r) => r.status);
        expect(withData.length).toBeGreaterThan(20);
        expect(withData.every((r) => r.remaining !== null && r.offset !== null)).toBe(true);
    });

    it('trước lần poll đầu và khi đơn chưa giao thì remaining = null', async () => {
        const srv = chainServer({ status: 'LOCKED' });
        const { result } = renderHook(() => useOrderStatus('o1', { fetchStatus: srv.fetchStatus, intervalMs: 3000 }));
        expect(result.current).toMatchObject({ status: null, remaining: null, offset: null });
        await tick(0);
        expect(result.current.status.status).toBe('LOCKED');
        expect(result.current.remaining).toBeNull();
    });

    it('chuỗi bị tua tiến thêm giữa chừng: đồng hồ hạ ngay xuống mức mới (hết hạn) ở lần poll kế, không chờ nhiều nhịp', async () => {
        let ahead = 0;
        const fetchStatus = vi.fn(async () => ({
            status: 'DELIVERED', delivered_at: Math.floor(T0 / 1000) - 300, inspection_duration: 600, server_time: Math.floor(Date.now() / 1000) + ahead,
        }));
        const { result } = renderHook(() => useOrderStatus('o1', { fetchStatus, intervalMs: 3000 }));
        await tick(0);
        expect(Math.abs(result.current.remaining - 300)).toBeLessThanOrEqual(1);
        ahead = 86400;                                                              // evm_increaseTime một ngày giữa hai lần poll
        await tick(3000);
        expect(result.current.remaining).toBeLessThanOrEqual(0);
    });
});

describe('polling thích ứng', () => {
    it('đơn LOCKED (chờ Shipper): 15 giây/lần', async () => {
        const srv = chainServer({ status: 'LOCKED' });
        renderHook(() => useOrderStatus('o1', { fetchStatus: srv.fetchStatus }));
        await tick(46_000);
        expect(srv.calls).toEqual([0, 15_000, 30_000, 45_000]);
    });

    it('DELIVERED còn nhiều thời gian: 15 giây/lần', async () => {
        const srv = chainServer({ deliveredAgo: 100, duration: 3 * 86400 });
        renderHook(() => useOrderStatus('o1', { fetchStatus: srv.fetchStatus }));
        await tick(31_000);
        expect(srv.calls).toEqual([0, 15_000, 30_000]);
    });

    it('DELIVERED sắp hết hạn: dậy đúng lúc còn 10 giây rồi poll 3 giây/lần, và vẫn poll nhanh sau hạn cho tới khi thấy COMPLETED', async () => {
        const srv = chainServer({ deliveredAgo: 560, duration: 600 });            // còn 40 giây
        const { result } = renderHook(() => useOrderStatus('o1', { fetchStatus: srv.fetchStatus }));
        await tick(0);
        expect(Math.abs(result.current.remaining - 40)).toBeLessThanOrEqual(1);
        await tick(60_000);
        // 0 -> 15 s (còn ~25) -> 30 s (còn ~10) -> rồi mỗi 3 giây
        expect(srv.calls.slice(0, 3)).toEqual([0, 15_000, 30_000]);
        const after = srv.calls.slice(3);
        expect(after.length).toBeGreaterThanOrEqual(8);
        after.forEach((t, i) => expect(t - (i === 0 ? 30_000 : after[i - 1])).toBe(POLL_MS.FAST));
        expect(result.current.remaining).toBeLessThan(0);                          // đã quá hạn mà Indexer chưa ghi: vẫn poll nhanh
        srv.state.status = 'COMPLETED';
        await tick(3_100);
        expect(result.current.status.status).toBe('COMPLETED');
        const n = srv.fetchStatus.mock.calls.length;
        await tick(60_000);
        expect(srv.fetchStatus.mock.calls.length).toBe(n);                         // trạng thái cuối: dừng
        expect(result.current.stopped).toBe(true);
    });

    it('quá hạn quá 120 giây mà vẫn DELIVERED (AutoRelease hỏng): giãn lại 15 giây/lần, không dồn tải', async () => {
        const srv = chainServer({ deliveredAgo: 700, duration: 600 });             // đã quá hạn 100 giây
        renderHook(() => useOrderStatus('o1', { fetchStatus: srv.fetchStatus }));
        await tick(21_000);                                                         // đang trong cửa sổ nhanh (đến quá hạn 120 giây)
        const fastCalls = srv.calls.length;
        expect(fastCalls).toBeGreaterThanOrEqual(6);
        await tick(60_000);                                                         // sau đó
        const lateCalls = srv.calls.filter((t) => t > 40_000);
        lateCalls.slice(1).forEach((t, i) => expect(t - lateCalls[i]).toBe(POLL_MS.SLOW));
    });

    it('boost() sau thao tác ví: hỏi lại NGAY và 3 giây/lần trong BOOST_MS, rồi trở về 15 giây', async () => {
        const srv = chainServer({ status: 'LOCKED' });
        const { result } = renderHook(() => useOrderStatus('o1', { fetchStatus: srv.fetchStatus }));
        await tick(1_000);
        expect(srv.calls).toEqual([0]);
        await act(async () => { result.current.boost(); await vi.advanceTimersByTimeAsync(0); });
        expect(srv.calls).toEqual([0, 1_000]);                                      // hỏi lại tức thì
        await tick(9_000);
        expect(srv.calls.slice(1).every((t, i, a) => i === 0 || t - a[i - 1] === POLL_MS.FAST)).toBe(true);
        expect(srv.calls.length).toBeGreaterThanOrEqual(4);
        await tick(BOOST_MS + 20_000);
        const late = srv.calls.filter((t) => t > 1_000 + BOOST_MS + 3_000);
        late.slice(1).forEach((t, i) => expect(t - late[i]).toBe(POLL_MS.SLOW));    // hết boost: chậm lại
    });

    it('boost(ms) tùy chỉnh thời lượng', async () => {
        const srv = chainServer({ status: 'LOCKED' });
        const { result } = renderHook(() => useOrderStatus('o1', { fetchStatus: srv.fetchStatus }));
        await tick(0);
        await act(async () => { result.current.boost(6_000); await vi.advanceTimersByTimeAsync(0); });
        await tick(30_000);
        const gaps = srv.calls.slice(1).map((t, i) => t - srv.calls[i]);
        expect(gaps.slice(0, 2)).toEqual([0, POLL_MS.FAST]);                         // 0: lần hỏi tức thì do boost
        expect(gaps.includes(POLL_MS.SLOW)).toBe(true);
    });

    it('intervalMs là số: chu kỳ CỐ ĐỊNH bất kể trạng thái (dùng cho test)', async () => {
        const srv = chainServer({ status: 'LOCKED' });
        renderHook(() => useOrderStatus('o1', { fetchStatus: srv.fetchStatus, intervalMs: 1000 }));
        await tick(3_500);
        expect(srv.calls).toEqual([0, 1000, 2000, 3000]);
    });

    it('enabled=false hoặc không có mã đơn: không gọi API', async () => {
        const srv = chainServer();
        renderHook(() => useOrderStatus('o1', { fetchStatus: srv.fetchStatus, enabled: false }));
        renderHook(() => useOrderStatus('', { fetchStatus: srv.fetchStatus }));
        await tick(60_000);
        expect(srv.fetchStatus).not.toHaveBeenCalled();
    });

    it('lỗi mạng không làm mất đồng hồ đã có; hồi phục thì tiếp tục', async () => {
        const srv = chainServer({ deliveredAgo: 100, duration: 3 * 86400 });
        const ok = srv.fetchStatus.getMockImplementation();
        let down = false;
        srv.fetchStatus.mockImplementation(async (...a) => { if (down) throw new Error('mạng'); return ok(...a); });
        const { result } = renderHook(() => useOrderStatus('o1', { fetchStatus: srv.fetchStatus }));
        await tick(0);
        const before = result.current.remaining;
        down = true;
        await tick(20_000);
        expect(result.current.remaining).toBeLessThanOrEqual(before);
        expect(result.current.remaining).toBeGreaterThan(before - 25);
        expect(result.current.status).not.toBeNull();
    });
});

describe('hạn hủy đơn chưa giao (LOCKED, Tuần 7)', () => {
    const lockedServer = ({ createdAgoSec, withCreated = true }) => {
        const nowSec = () => Math.floor(Date.now() / 1000);
        const created = nowSec() - createdAgoSec;
        return vi.fn(async () => ({
            order_id: 'o1', status: 'LOCKED', chain_created_at: withCreated ? created : null, delivered_at: null, inspection_duration: 600, server_time: nowSec(),
        }));
    };

    it('đếm ngược tới mốc chain_created_at + 14 ngày theo giờ máy chủ, giảm đều và hạ về 0 đúng mốc', async () => {
        const fetchStatus = lockedServer({ createdAgoSec: 14 * 86400 - 30 });          // còn 30 giây tới mốc
        const { result } = renderHook(() => useOrderStatus('o1', { fetchStatus, intervalMs: 3000 }));
        await tick(0);
        const first = result.current.deliveryRemaining;
        expect(first).toBeGreaterThanOrEqual(29);
        expect(first).toBeLessThanOrEqual(31);
        expect(result.current.remaining).toBeNull();                                    // chưa giao: chưa có đồng hồ kiểm tra
        await tick(20_000);
        expect(result.current.deliveryRemaining).toBeLessThan(first - 15);              // đồng hồ chạy dù đơn chỉ LOCKED (có tick)
        await tick(15_000);
        expect(result.current.deliveryRemaining).toBeLessThanOrEqual(0);
    });

    it('không bao giờ tăng trở lại khi poll lại (cùng nguyên tắc với đồng hồ kiểm tra)', async () => {
        const fetchStatus = lockedServer({ createdAgoSec: 14 * 86400 - 120 });
        const { result } = renderHook(() => useOrderStatus('o1', { fetchStatus, intervalMs: 3000 }));
        await tick(0);
        let prev = result.current.deliveryRemaining;
        for (let t = 0; t < 60_000; t += 500) {
            await tick(500);
            expect(result.current.deliveryRemaining).toBeLessThanOrEqual(prev);
            prev = result.current.deliveryRemaining;
        }
    });

    it('dữ liệu cũ không có chain_created_at: deliveryRemaining là null (giao diện không hiện nút hủy)', async () => {
        const fetchStatus = lockedServer({ createdAgoSec: 20 * 86400, withCreated: false });
        const { result } = renderHook(() => useOrderStatus('o1', { fetchStatus, intervalMs: 3000 }));
        await tick(10_000);
        expect(result.current.deliveryRemaining).toBeNull();
    });

    it('đơn đã giao: deliveryRemaining theo chain_created_at vẫn tính được nhưng chỉ có ý nghĩa với LOCKED (nút do canCancelUnfulfilled quyết định)', async () => {
        const nowSec = Math.floor(Date.now() / 1000);
        const fetchStatus = vi.fn(async () => ({ order_id: 'o1', status: 'DELIVERED', chain_created_at: nowSec - 20 * 86400, delivered_at: nowSec - 60, inspection_duration: 600, server_time: nowSec }));
        const { result } = renderHook(() => useOrderStatus('o1', { fetchStatus, intervalMs: 3000 }));
        await tick(0);
        expect(result.current.remaining).toBeGreaterThan(0);
        expect(result.current.status.status).toBe('DELIVERED');
    });
});
