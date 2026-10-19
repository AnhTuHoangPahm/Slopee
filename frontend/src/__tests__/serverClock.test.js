import { describe, expect, it } from 'vitest';
import { nextOffset, remainingSec } from '../lib/serverClock';

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
