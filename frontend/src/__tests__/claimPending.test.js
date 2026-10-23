import { describe, expect, it, vi } from 'vitest';
import {
    CLAIM_STEP, ETH_ADDRESS, claimIndexed, claimReducer, initialClaimState, isClaimBusy, mapClaimError, runClaimPending, tokenParam,
} from '../lib/claimPending';

const OWNER = '0x9965507d1a55bcc2695c58ba16fb37d819b0a4dc';
const tx = (hash = '0xaa') => ({ hash, wait: vi.fn(async () => ({ status: 1 })) });
const run = (escrow, token = 'ETH') => {
    const events = [];
    const p = runClaimPending({ token, address: OWNER, escrow, dispatch: (e) => events.push(e) });
    return { events, p };
};

describe('claimReducer', () => {
    const steps = (...evs) => evs.reduce(claimReducer, initialClaimState());
    it('luồng đầy đủ', () => {
        expect(steps({ type: 'START', token: 'ETH', address: OWNER }, { type: 'SENT', hash: '0x1', amountRaw: '5' }, { type: 'MINED' }, { type: 'INDEXED' }))
            .toMatchObject({ step: CLAIM_STEP.DONE, token: 'ETH', address: OWNER, txHash: '0x1', amountRaw: '5' });
    });
    it('sự kiện sai thứ tự bị bỏ qua', () => {
        expect(steps({ type: 'MINED' }).step).toBe(CLAIM_STEP.IDLE);
        expect(steps({ type: 'START', token: 'ETH', address: OWNER }, { type: 'MINED' }).step).toBe(CLAIM_STEP.SIGNING);
        expect(steps({ type: 'INDEXED' }).step).toBe(CLAIM_STEP.IDLE);
    });
    it('START lần hai khi đang bận bị bỏ qua (không mở hai luồng ví)', () => {
        const s = steps({ type: 'START', token: 'ETH', address: OWNER }, { type: 'START', token: 'X', address: '0x2' });
        expect(s.token).toBe('ETH');
        expect(isClaimBusy(s)).toBe(true);
    });
    it('FAIL rồi START lại được; DONE không bị FAIL muộn đè', () => {
        expect(steps({ type: 'START', token: 'ETH', address: OWNER }, { type: 'FAIL', error: { message: 'x' } }, { type: 'START', token: 'ETH', address: OWNER }).step).toBe(CLAIM_STEP.SIGNING);
        expect(steps({ type: 'START', token: 'ETH', address: OWNER }, { type: 'SENT', hash: '1' }, { type: 'INDEXED' }, { type: 'FAIL', error: {} }).step).toBe(CLAIM_STEP.DONE);
    });
});

describe('tokenParam / claimIndexed', () => {
    it('ETH là địa chỉ 0, ERC-20 giữ nguyên', () => {
        expect(tokenParam('ETH')).toBe(ETH_ADDRESS);
        expect(tokenParam('0xabc')).toBe('0xabc');
    });
    it('đã Indexer khi khoản (token, ví) không còn; khoản khác không ảnh hưởng', () => {
        const pending = [{ token: 'ETH', address: '0xother' }, { token: '0xtok', address: OWNER }];
        expect(claimIndexed(pending, { token: 'ETH', address: OWNER.toUpperCase().replace('0X', '0x') })).toBe(true);
        expect(claimIndexed(pending, { token: '0xtok', address: OWNER })).toBe(false);
    });
});

describe('runClaimPending', () => {
    it('đường vui: đọc số dư thật -> claimPending(ETH=0x0) -> SENT -> MINED, dừng ở MINED', async () => {
        const escrow = { pendingWithdrawals: vi.fn(async () => 7000n), claimPending: vi.fn(async () => tx('0xca')) };
        const { events, p } = run(escrow);
        await expect(p).resolves.toEqual({ hash: '0xca', amountRaw: '7000' });
        expect(escrow.pendingWithdrawals).toHaveBeenCalledWith(ETH_ADDRESS, OWNER);
        expect(escrow.claimPending).toHaveBeenCalledWith(ETH_ADDRESS);
        expect(events.map((e) => e.type)).toEqual(['START', 'SENT', 'MINED']);
    });
    it('số dư thật trên chuỗi đã bằng 0: KHÔNG gửi giao dịch (khỏi tốn gas), báo rõ', async () => {
        const escrow = { pendingWithdrawals: vi.fn(async () => 0n), claimPending: vi.fn() };
        const { events, p } = run(escrow);
        await expect(p).rejects.toBeTruthy();
        expect(escrow.claimPending).not.toHaveBeenCalled();
        expect(events.at(-1)).toMatchObject({ type: 'FAIL', error: { code: 'NOTHING_TO_CLAIM', userRejected: false } });
    });
    it('ERC-20 dùng địa chỉ token thật', async () => {
        const escrow = { pendingWithdrawals: vi.fn(async () => 1n), claimPending: vi.fn(async () => tx()) };
        await run(escrow, '0xtok').p;
        expect(escrow.claimPending).toHaveBeenCalledWith('0xtok');
    });
    it('hủy trong MetaMask là thông báo nhẹ', async () => {
        const escrow = { pendingWithdrawals: async () => 1n, claimPending: vi.fn(async () => { throw Object.assign(new Error('r'), { code: 4001 }); }) };
        const { events, p } = run(escrow);
        await expect(p).rejects.toBeTruthy();
        expect(events.at(-1)).toMatchObject({ type: 'FAIL', error: { code: 'USER_REJECTED', userRejected: true } });
    });
    it('revert được dịch: ví từ chối ETH, hết khoản chờ', async () => {
        expect(mapClaimError({ reason: 'ETH transfer failed' }).message).toMatch(/từ chối nhận ETH/);
        expect(mapClaimError({ shortMessage: 'execution reverted: "Nothing to claim"' }).message).toMatch(/Không còn khoản nào/);
        expect(mapClaimError(new Error('boom'))).toMatchObject({ code: 'TX_FAILED', userRejected: false });
        expect(mapClaimError({ code: -32002 }).code).toBe('REQUEST_PENDING');
    });
    it('lỗi khi chờ biên nhận cũng phát FAIL', async () => {
        const escrow = { pendingWithdrawals: async () => 1n, claimPending: async () => ({ hash: '0x1', wait: async () => { throw new Error('dropped'); } }) };
        const { events, p } = run(escrow);
        await expect(p).rejects.toBeTruthy();
        expect(events.map((e) => e.type)).toEqual(['START', 'SENT', 'FAIL']);
    });
});
