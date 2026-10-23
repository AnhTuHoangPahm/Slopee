import { describe, expect, it } from 'vitest';
import {
    BOOST_MS, NEAR_DEADLINE_SEC, OVERDUE_FAST_SEC, POLL_MS, availableActions, formatInspectionCountdown, inspectionDeadline, inspectionRemainingAt,
    isTerminalStatus, needsPolling, nextPollDelayMs, orderPhase, walletGate,
} from '../lib/orderTimer';

// Tuần 5 [F]: đồng hồ kiểm tra theo giờ MÁY CHỦ (F-06) và quy tắc bật/tắt nút "Đã nhận hàng"/"Khiếu nại" (SDD 9.4).
const DELIVERED = { status: 'DELIVERED', delivered_at: 1_000, inspection_duration: 600 };
const A = '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc';

describe('inspectionRemainingAt (đếm theo độ lệch giờ máy chủ)', () => {
    // offset = server_time - giờ máy (giây). Ở đây máy ở 5 s, server_time 1100 => offset 1095.
    const OFFSET = 1_100 - 5;
    it('= delivered_at + inspection_duration - giờ máy chủ ước lượng', () => {
        expect(inspectionDeadline(DELIVERED)).toBe(1_600);
        expect(inspectionRemainingAt(DELIVERED, OFFSET, 5_000)).toBe(500);
    });
    it('trôi theo đồng hồ máy khách kể từ lúc đo độ lệch', () => {
        expect(inspectionRemainingAt(DELIVERED, OFFSET, 12_000)).toBe(493);
    });
    it('làm tròn XUỐNG: còn 499,5 giây hiển thị 499 (nút Khiếu nại khóa sớm chứ không muộn)', () => {
        expect(inspectionRemainingAt(DELIVERED, OFFSET, 5_500)).toBe(499);
        expect(inspectionRemainingAt(DELIVERED, OFFSET, 1_599_000 - OFFSET * 1000 + 400)).toBe(0);       // còn 0,6 giây: coi như hết
    });
    it('KHÔNG phụ thuộc đồng hồ tuyệt đối của máy người dùng (máy sai giờ vẫn đúng)', () => {
        const wrongClock = 9_999_999_999_000;
        expect(inspectionRemainingAt(DELIVERED, 1_100 - wrongClock / 1000, wrongClock)).toBe(500);
    });
    it('server_time tua nhanh (Anvil evm_increaseTime) thì hết hạn ngay', () => {
        expect(inspectionRemainingAt(DELIVERED, 1_605 - 0, 0)).toBeLessThanOrEqual(0);
    });
    it('null khi chưa giao hoặc chưa có độ lệch (không đoán theo giờ máy khách)', () => {
        expect(inspectionRemainingAt({ status: 'LOCKED', delivered_at: null, inspection_duration: 600 }, OFFSET, 0)).toBeNull();
        expect(inspectionRemainingAt(DELIVERED, null, 0)).toBeNull();
        expect(inspectionRemainingAt(DELIVERED, undefined, 0)).toBeNull();
    });
    it('độ lệch chỉ tăng thì số giây còn lại chỉ giảm (không giật lùi)', () => {
        let prev = Infinity;
        for (let t = 0; t <= 60_000; t += 500) {
            const r = inspectionRemainingAt(DELIVERED, OFFSET + (t > 30_000 ? 2 : 0), 5_000 + t);   // độ lệch tăng 2 giây giữa chừng
            expect(r).toBeLessThanOrEqual(prev);
            prev = r;
        }
    });
});

describe('nextPollDelayMs (polling thích ứng, PROGRESS Tuần 5 mục 11)', () => {
    const { FAST, SLOW } = POLL_MS;
    it('hằng số: nhanh 3 giây, chậm 15 giây; quá hạn vẫn nhanh đủ cho AutoRelease (60 giây) + Indexer (2 giây)', () => {
        expect([FAST, SLOW]).toEqual([3_000, 15_000]);
        expect(OVERDUE_FAST_SEC).toBeGreaterThan(62);
        expect(BOOST_MS).toBeGreaterThanOrEqual(30_000);               // lâu hơn INDEXER_SLOW_AFTER_MS (30 giây)
    });
    it.each([[null, null], [undefined, 5], ['', 5], ['PENDING_PAYMENT', null], ['PENDING_PAYMENT', 99999]])('%s (remaining %s): nhanh', (status, remaining) =>
        expect(nextPollDelayMs(status, remaining)).toBe(FAST));
    it.each(['LOCKED', 'DISPUTED', 'COMPLETED', 'REFUNDED', 'EXPIRED'])('%s: chậm (chờ Shipper/Admin có thể hàng giờ)', (status) =>
        expect(nextPollDelayMs(status, null)).toBe(SLOW));
    it('DELIVERED chưa có đồng hồ: nhanh để có độ lệch sớm', () => expect(nextPollDelayMs('DELIVERED', null)).toBe(FAST));
    it('DELIVERED còn nhiều thời gian: chậm', () => {
        expect(nextPollDelayMs('DELIVERED', 3 * 86400)).toBe(SLOW);
        expect(nextPollDelayMs('DELIVERED', 3600)).toBe(SLOW);
    });
    it('không ngủ quá mốc "sắp hết hạn": dậy đúng lúc để chuyển sang nhanh', () => {
        expect(nextPollDelayMs('DELIVERED', NEAR_DEADLINE_SEC + 8)).toBe(8_000);        // còn 18 giây: dậy sau 8 giây (lúc còn 10)
        expect(nextPollDelayMs('DELIVERED', NEAR_DEADLINE_SEC + 1)).toBe(FAST);         // sàn là chu kỳ nhanh
        expect(nextPollDelayMs('DELIVERED', NEAR_DEADLINE_SEC + 600)).toBe(SLOW);       // trần là chu kỳ chậm
    });
    it('sắp hết hạn và vừa quá hạn: nhanh, để thấy COMPLETED/DISPUTED ngay khi Indexer ghi', () => {
        for (const r of [NEAR_DEADLINE_SEC, 5, 0, -1, -65, -OVERDUE_FAST_SEC]) expect(nextPollDelayMs('DELIVERED', r)).toBe(FAST);
    });
    it('quá hạn quá lâu mà vẫn DELIVERED (AutoRelease hỏng): giãn lại, không dồn tải', () => {
        expect(nextPollDelayMs('DELIVERED', -OVERDUE_FAST_SEC - 1)).toBe(SLOW);
        expect(nextPollDelayMs('DELIVERED', -86400)).toBe(SLOW);
    });
    it('vừa thao tác ví (boosted): nhanh bất kể trạng thái', () => {
        for (const s of ['LOCKED', 'DELIVERED', 'DISPUTED']) expect(nextPollDelayMs(s, 86400, { boosted: true })).toBe(FAST);
    });
    it('cho phép đổi chu kỳ (test)', () => {
        expect(nextPollDelayMs('LOCKED', null, { slow: 100 })).toBe(100);
        expect(nextPollDelayMs('DELIVERED', null, { fast: 7 })).toBe(7);
    });
});

describe('availableActions (SDD 9.4)', () => {
    it('còn hạn: cả hai nút bật', () => expect(availableActions('DELIVERED', 10)).toEqual({ earlyRelease: true, dispute: true }));
    it('hết hạn: khóa Khiếu nại, vẫn cho Đã nhận hàng', () => {
        expect(availableActions('DELIVERED', 0)).toEqual({ earlyRelease: true, dispute: false });
        expect(availableActions('DELIVERED', -5).dispute).toBe(false);
    });
    it('chưa biết đồng hồ: chưa cho khiếu nại', () => expect(availableActions('DELIVERED', null)).toEqual({ earlyRelease: true, dispute: false }));
    it.each(['LOCKED', 'DISPUTED', 'COMPLETED', 'REFUNDED', 'PENDING_PAYMENT', 'EXPIRED'])('%s: không nút nào', (s) =>
        expect(availableActions(s, 100)).toEqual({ earlyRelease: false, dispute: false }));
});

describe('trạng thái', () => {
    it('trạng thái cuối dừng polling', () => {
        for (const s of ['COMPLETED', 'REFUNDED', 'EXPIRED']) expect(isTerminalStatus(s)).toBe(true);
        for (const s of ['LOCKED', 'DELIVERED', 'DISPUTED', 'PENDING_PAYMENT']) expect(isTerminalStatus(s)).toBe(false);
    });
    it('chỉ LOCKED/DELIVERED/DISPUTED cần polling', () => {
        expect(['LOCKED', 'DELIVERED', 'DISPUTED', 'PENDING_PAYMENT', 'COMPLETED'].filter(needsPolling)).toEqual(['LOCKED', 'DELIVERED', 'DISPUTED']);
    });
    it('orderPhase', () => {
        expect(orderPhase('LOCKED', null)).toBe('AWAITING_DELIVERY');
        expect(orderPhase('DELIVERED', null)).toBe('SYNCING');
        expect(orderPhase('DELIVERED', 5)).toBe('INSPECTING');
        expect(orderPhase('DELIVERED', 0)).toBe('INSPECTION_OVER');
        expect(orderPhase('DISPUTED', 5)).toBe('DISPUTED');
    });
});

describe('formatInspectionCountdown', () => {
    it.each([[0, '00:00:00'], [59, '00:00:59'], [90, '00:01:30'], [3_661, '01:01:01'], [86_400, '1 ngày 00:00:00'], [183_909, '2 ngày 03:05:09'], [-7, '00:00:00']])('%s -> %s', (n, out) =>
        expect(formatInspectionCountdown(n)).toBe(out));
});

describe('walletGate', () => {
    const ok = { isConnected: true, isCorrectChain: true, account: A, buyerWallet: A.toLowerCase() };
    it('đúng ví, đúng mạng (không phân biệt hoa/thường)', () => expect(walletGate(ok)).toBe('OK'));
    it('chưa kết nối', () => expect(walletGate({ ...ok, isConnected: false })).toBe('NOT_CONNECTED'));
    it('sai mạng', () => expect(walletGate({ ...ok, isCorrectChain: false })).toBe('WRONG_CHAIN'));
    it('ví khác ví đã ký quỹ', () => expect(walletGate({ ...ok, account: '0x976EA74026E726554dB657fA54763abd0C3a0aa9' })).toBe('WRONG_ACCOUNT'));
    it('không biết ví ký quỹ thì không chặn (contract vẫn kiểm Only buyer)', () => expect(walletGate({ ...ok, buyerWallet: null })).toBe('OK'));
});
