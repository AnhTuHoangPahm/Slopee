import { describe, expect, it } from 'vitest';
import { availableActions, formatInspectionCountdown, inspectionDeadline, inspectionRemaining, isTerminalStatus, needsPolling, orderPhase, walletGate } from '../lib/orderTimer';

// Tuần 5 [F]: đồng hồ kiểm tra theo giờ MÁY CHỦ (F-06) và quy tắc bật/tắt nút "Đã nhận hàng"/"Khiếu nại" (SDD 9.4).
const DELIVERED = { status: 'DELIVERED', delivered_at: 1_000, inspection_duration: 600 };
const A = '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc';

describe('inspectionRemaining', () => {
    it('= delivered_at + inspection_duration - server_time', () => {
        expect(inspectionDeadline(DELIVERED)).toBe(1_600);
        expect(inspectionRemaining(DELIVERED, { serverTime: 1_100, receivedAtMs: 5_000 }, 5_000)).toBe(500);
    });
    it('trôi theo đồng hồ máy khách kể từ lần poll gần nhất', () => {
        expect(inspectionRemaining(DELIVERED, { serverTime: 1_100, receivedAtMs: 5_000 }, 12_000)).toBe(493);
    });
    it('KHÔNG phụ thuộc đồng hồ tuyệt đối của máy người dùng (máy sai giờ vẫn đúng)', () => {
        const wrongClock = 9_999_999_999_000;
        expect(inspectionRemaining(DELIVERED, { serverTime: 1_100, receivedAtMs: wrongClock }, wrongClock)).toBe(500);
    });
    it('server_time tua nhanh (Anvil evm_increaseTime) thì hết hạn ngay', () => {
        expect(inspectionRemaining(DELIVERED, { serverTime: 1_600 + 5, receivedAtMs: 0 }, 0)).toBeLessThanOrEqual(0);
    });
    it('null khi chưa giao hoặc chưa có đồng hồ máy chủ (không đoán theo giờ máy khách)', () => {
        expect(inspectionRemaining({ status: 'LOCKED', delivered_at: null, inspection_duration: 600 }, { serverTime: 1, receivedAtMs: 0 })).toBeNull();
        expect(inspectionRemaining(DELIVERED, null)).toBeNull();
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
