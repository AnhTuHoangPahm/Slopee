import { describe, expect, it } from 'vitest';
import { createServerClock, nextOffset, remainingSec, serverNowSec } from '../lib/serverClock';

// Khuyến nghị của B (GHI_CHU_MUC_10_11): giữ độ lệch LỚN NHẤT giữa server_time và giờ máy; server_time chỉ có thể CŨ, không bao giờ mới hơn giờ chuỗi.
describe('nextOffset', () => {
    it('mẫu đầu tiên là độ lệch ban đầu', () => expect(nextOffset(null, 1000, 5_000_000 - 4_000_000)).toBeCloseTo(1000 - 1000, 5));
    it('chỉ tăng: mẫu thấp hơn (trễ/răng cưa) không kéo đồng hồ lùi', () => {
        const a = nextOffset(null, 1000, 1_000_000); // 0
        expect(nextOffset(a, 998, 1_000_000)).toBe(a); // server_time cũ 2 giây
        expect(nextOffset(a, 1001, 1_000_000)).toBeCloseTo(1, 5); // mẫu mới hơn: tăng
    });
    it('trôi thật quá resetAfterSec (ví dụ Anvil dựng lại) thì neo lại', () => {
        const a = nextOffset(null, 1000, 1_000_000);
        expect(nextOffset(a, 900, 1_000_000)).toBeCloseTo(-100, 5);
        expect(nextOffset(a, 980, 1_000_000)).toBe(a); // chỉ lệch 20 giây < 30: giữ
    });
    it('dữ liệu rác thì giữ nguyên', () => {
        expect(nextOffset(5, 'abc', 1000)).toBe(5);
        expect(nextOffset(null, undefined, 1000)).toBeNull();
    });
});

describe('remainingSec', () => {
    it('= deadline - (now + offset)', () => expect(remainingSec(2000, 0, 1_500_000)).toBe(500));
    it('null khi chưa có độ lệch/hạn', () => { expect(remainingSec(2000, null, 0)).toBeNull(); expect(remainingSec(null, 0, 0)).toBeNull(); });
    it('đồng hồ máy khách sai giờ vẫn đúng nhờ độ lệch', () => {
        const wrongNowMs = 9_999_999_000;                 // máy khách sai
        const off = nextOffset(null, 1000, wrongNowMs);   // lần poll đầu ghi nhận độ lệch
        expect(remainingSec(1600, off, wrongNowMs)).toBeCloseTo(600, 5);
    });
    it('server_time răng cưa (block 2 giây, đo trên Anvil đã tua giờ): đếm ngược KHÔNG BAO GIỜ tăng lại', () => {
        const t0 = 1_000_000; // ms
        let offset = null;
        let prev = Infinity;
        for (let ms = 0; ms <= 60_000; ms += 500) {
            const nowMs = t0 + ms;
            const trueChain = 5000 + ms / 1000 + 1.3;           // giờ chuỗi thật
            if (ms % 3000 === 0) offset = nextOffset(offset, Math.floor(trueChain / 2) * 2, nowMs); // poll 3 giây/lần, server_time tụt 0-2 giây
            const rem = remainingSec(5100, offset, nowMs);
            expect(rem).toBeLessThanOrEqual(prev + 1e-9);
            prev = rem;
        }
    });
});

describe('serverNowSec', () => {
    it('= giờ máy + độ lệch; null khi chưa có độ lệch', () => {
        expect(serverNowSec(1000, 5_000)).toBe(1005);
        expect(serverNowSec(null, 5_000)).toBeNull();
        expect(serverNowSec(undefined, 5_000)).toBeNull();
        expect(serverNowSec(0, 0)).toBe(0);                                   // 0 là độ lệch hợp lệ, không phải "chưa có"
    });
});

describe('createServerClock (đồng hồ có trạng thái cho một nguồn polling)', () => {
    it('chưa có mẫu: mọi phép đo trả null', () => {
        const c = createServerClock({ now: () => 0 });
        expect(c.offset).toBeNull();
        expect(c.nowSec(1_000)).toBeNull();
        expect(c.remaining(5_000, 1_000)).toBeNull();
    });

    it('observe nhận lúc NHẬN phản hồi; đo còn lại = deadline - (giờ máy + độ lệch)', () => {
        const c = createServerClock();
        expect(c.observe(1_100, 5_000)).toBe(1_095);
        expect(c.nowSec(5_000)).toBe(1_100);
        expect(c.remaining(1_600, 5_000)).toBe(500);
        expect(c.remaining(1_600, 12_000)).toBe(493);                          // 7 giây trôi theo giờ máy
    });

    it('chuỗi mẫu răng cưa + độ trễ mạng thay đổi: số giây còn lại KHÔNG BAO GIỜ tăng', () => {
        const c = createServerClock();
        let truth = 1_000_000;                                               // giờ thật của chuỗi (giây), máy khách chạy cùng nhịp
        let prev = Infinity;
        let minRemaining = Infinity;
        for (let step = 0; step < 400; step += 1) {                          // 400 mẫu cách nhau 3 giây
            const stale = [0, 1, 2, 1, 0, 2][step % 6];                      // server_time cũ 0-2 giây (block 2 giây)
            const latencyMs = [50, 300, 120, 250, 80, 20][step % 6];         // trễ mạng 20-300 ms
            const nowMs = truth * 1000 + latencyMs;
            c.observe(truth - stale, nowMs);
            for (let k = 0; k < 6; k += 1) {                                 // giao diện đếm 2 lần/giây giữa hai lần poll
                const r = c.remaining(1_100_000, nowMs + k * 500);
                expect(r).toBeLessThanOrEqual(prev + 1e-9);
                prev = r;
                minRemaining = Math.min(minRemaining, r);
            }
            truth += 3;
        }
        // ước lượng không lệch quá 3 giây so với thực tế (cũ nhiều nhất 2 giây + trễ mạng + làm tròn)
        expect(Math.abs(c.remaining(1_100_000, truth * 1000) - (1_100_000 - truth))).toBeLessThan(3);
    });

    it('server_time bị tua tiến (Anvil evm_increaseTime): đồng hồ nhảy tiến ngay, không chờ', () => {
        const c = createServerClock();
        c.observe(1_000, 1_000_000);
        const before = c.remaining(260_000, 1_000_000);
        c.observe(1_000 + 3 * 86400, 1_003_000);
        expect(c.remaining(260_000, 1_003_000)).toBeLessThan(before - 3 * 86400 + 5);
    });

    it('chuỗi bị dựng lại (lệch ngược quá resetAfterSec): neo lại thay vì chạy trước mãi', () => {
        const c = createServerClock({ resetAfterSec: 30 });
        c.observe(1_000 + 86400, 1_000_000);
        expect(c.observe(1_000, 1_003_000)).toBeCloseTo(1_000 - 1_003, 3);
        const c2 = createServerClock({ resetAfterSec: 30 });
        const a = c2.observe(2_000, 1_000_000);
        expect(c2.observe(2_000 - 10, 1_000_000)).toBe(a);                    // lệch ngược dưới ngưỡng: giữ
    });

    it('mẫu hỏng (NaN/undefined) bị bỏ qua, không phá độ lệch đang có', () => {
        const c = createServerClock();
        const a = c.observe(1_100, 5_000);
        expect(c.observe(undefined, 6_000)).toBe(a);
        expect(c.observe('abc', 6_000)).toBe(a);
        expect(c.offset).toBe(a);
        expect(createServerClock().observe(NaN, 1)).toBeNull();
    });

    it('reset() xóa độ lệch; hai đồng hồ độc lập nhau', () => {
        const a = createServerClock();
        const b = createServerClock();
        a.observe(1_100, 5_000);
        expect(b.offset).toBeNull();
        a.reset();
        expect(a.offset).toBeNull();
    });

    it('mặc định lấy giờ từ `now` được tiêm vào (test không phụ thuộc đồng hồ thật)', () => {
        let t = 7_000;
        const c = createServerClock({ now: () => t });
        c.observe(1_100);
        t = 9_000;
        expect(c.nowSec()).toBe(1_102);
        expect(c.remaining(1_600)).toBe(498);
    });
});

