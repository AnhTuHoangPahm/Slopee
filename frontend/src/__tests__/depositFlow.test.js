import { describe, expect, it, vi } from 'vitest';
import {
    FLOW_ERROR, FlowError, STEP, depositReducer, groupIsLocked, initialDepositState, isBusy, mapDepositError, quoteToTuple, runDeposit, validateGroupForDeposit,
} from '../lib/depositFlow';

const BUYER = '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc';
const MUSD = '0x5FbDB2315678afecb367f032d93F642f64180aa3';
const ESCROW = '0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512';
const deployment = { escrow: ESCROW, mockUSD: MUSD };
const HASH = `0x${'ab'.repeat(32)}`;

const order = (i, amount) => ({
    order_id: `o${i}`, amount_raw: String(amount), signature: `0x${'11'.repeat(65)}`,
    quote: { orderId: String(100 + i), buyer: BUYER, merchant: '0x976EA74026E726554dB657fA54763abd0C3a0aa9', token: MUSD, amount: String(amount),
        inspectionDuration: '259200', disputeTimeout: '2592000', feeBps: '300', docHash: HASH, deadline: '2000000000' },
});
const group = (amounts = [15_960_000, 4_800_000]) => ({
    checkout_group_id: 'g1', token_address: MUSD, total_amount_raw: String(amounts.reduce((a, b) => a + b, 0)), orders: amounts.map((a, i) => order(i, a)),
});
const tx = (hash) => ({ hash, wait: vi.fn(async () => ({ status: 1 })) });

describe('depositReducer (máy trạng thái SDD 9.3)', () => {
    const run = (events, from = initialDepositState()) => events.reduce(depositReducer, from);

    it('đường đi đầy đủ: approve rồi nạp gom rồi chờ Indexer; LOCKED chỉ khi có INDEXER_LOCKED', () => {
        let s = run([{ type: 'START' }, { type: 'APPROVE_REQUESTED' }, { type: 'APPROVE_SENT', hash: '0xa' }]);
        expect(s.step).toBe(STEP.APPROVING);
        s = run([{ type: 'APPROVED' }, { type: 'DEPOSIT_REQUESTED' }, { type: 'DEPOSIT_SENT', hash: '0xb' }], s);
        expect(s.step).toBe(STEP.DEPOSITING);
        s = run([{ type: 'DEPOSIT_MINED' }], s);
        expect(s.step).toBe(STEP.WAITING_INDEXER); // biên nhận của ví KHÔNG phải LOCKED
        expect(s.step).not.toBe(STEP.LOCKED);
        expect(run([{ type: 'INDEXER_LOCKED' }], s).step).toBe(STEP.LOCKED);
    });

    it('đủ hạn mức thì bỏ APPROVING', () => {
        const s = run([{ type: 'START' }, { type: 'ALLOWANCE_OK' }, { type: 'DEPOSIT_REQUESTED' }, { type: 'DEPOSIT_SENT', hash: '0xb' }]);
        expect(s.step).toBe(STEP.DEPOSITING);
        expect(s.approveSkipped).toBe(true);
        expect(s.approveTx).toBeNull();
    });

    it('sự kiện sai thứ tự bị bỏ qua, không làm lùi/nhảy bước', () => {
        const s0 = initialDepositState();
        expect(depositReducer(s0, { type: 'INDEXER_LOCKED' })).toBe(s0);
        expect(depositReducer(s0, { type: 'DEPOSIT_MINED' })).toBe(s0);
        const waiting = run([{ type: 'START' }, { type: 'DEPOSIT_REQUESTED' }, { type: 'DEPOSIT_SENT', hash: '0xb' }, { type: 'DEPOSIT_MINED' }]);
        expect(depositReducer(waiting, { type: 'START' })).toBe(waiting); // không bắt đầu lại khi đang chờ
        expect(depositReducer(waiting, { type: 'APPROVE_SENT', hash: '0xz' })).toBe(waiting);
    });

    it('FAIL giữ lỗi, cho START lại; LOCKED không bị FAIL muộn ghi đè', () => {
        const failed = run([{ type: 'START' }, { type: 'FAIL', error: { code: 'X', message: 'm', extra: { shortfall: '5' } } }]);
        expect(failed.step).toBe(STEP.FAILED);
        expect(failed.shortfall).toBe('5');
        expect(run([{ type: 'START' }], failed).step).toBe(STEP.CHECKING);
        const locked = run([{ type: 'START' }, { type: 'DEPOSIT_REQUESTED' }, { type: 'DEPOSIT_SENT', hash: 'h' }, { type: 'DEPOSIT_MINED' }, { type: 'INDEXER_LOCKED' }]);
        expect(depositReducer(locked, { type: 'FAIL', error: {} })).toBe(locked);
    });

    it('FAIL ghi lại bước đang chạy để giao diện đánh dấu đúng chỗ lỗi', () => {
        const atApprove = run([{ type: 'START' }, { type: 'APPROVE_REQUESTED' }, { type: 'FAIL', error: {} }]);
        expect(atApprove.failedStep).toBe(STEP.APPROVING);
        const atDeposit = run([{ type: 'START' }, { type: 'ALLOWANCE_OK' }, { type: 'DEPOSIT_REQUESTED' }, { type: 'FAIL', error: {} }]);
        expect(atDeposit.failedStep).toBe(STEP.DEPOSITING);
    });

    it('RESUME_WAITING chỉ áp dụng cho lỗi Order exists', () => {
        const exists = run([{ type: 'START' }, { type: 'FAIL', error: { code: FLOW_ERROR.ORDER_EXISTS } }]);
        expect(depositReducer(exists, { type: 'RESUME_WAITING' }).step).toBe(STEP.WAITING_INDEXER);
        const other = run([{ type: 'START' }, { type: 'FAIL', error: { code: FLOW_ERROR.TX_REVERTED } }]);
        expect(depositReducer(other, { type: 'RESUME_WAITING' })).toBe(other);
    });

    it('isBusy khóa nút trong mọi bước đang chạy', () => {
        expect(isBusy({ step: STEP.APPROVING })).toBe(true);
        expect(isBusy({ step: STEP.WAITING_INDEXER })).toBe(true);
        expect(isBusy({ step: STEP.IDLE })).toBe(false);
        expect(isBusy({ step: STEP.FAILED })).toBe(false);
    });
});

describe('groupIsLocked', () => {
    it('cần MỌI đơn con LOCKED (hoặc xa hơn); một đơn còn PENDING là chưa', () => {
        expect(groupIsLocked({ orders: [{ status: 'LOCKED' }, { status: 'LOCKED' }] })).toBe(true);
        expect(groupIsLocked({ orders: [{ status: 'LOCKED' }, { status: 'DELIVERED' }] })).toBe(true);
        expect(groupIsLocked({ orders: [{ status: 'LOCKED' }, { status: 'PENDING_PAYMENT' }] })).toBe(false);
        expect(groupIsLocked({ orders: [] })).toBe(false);
        expect(groupIsLocked(null)).toBe(false);
    });
});

describe('quoteToTuple / validateGroupForDeposit', () => {
    it('đúng thứ tự struct Quote, số là BigInt', () => {
        const t = quoteToTuple(order(1, 4_800_000).quote);
        expect(t).toHaveLength(10);
        expect(t[0]).toBe(101n);
        expect(t[4]).toBe(4_800_000n);
        expect(t[9]).toBe(2_000_000_000n);
        expect(t[8]).toBe(HASH);
    });

    it('hợp lệ: trả tổng BigInt + quotes + sigs', () => {
        const r = validateGroupForDeposit(group(), { account: BUYER.toLowerCase(), deployment });
        expect(r.total).toBe(20_760_000n);
        expect(r.quotes).toHaveLength(2);
        expect(r.sigs).toHaveLength(2);
    });

    it.each([
        ['ví khác ví người mua', (g) => g, { account: '0x976EA74026E726554dB657fA54763abd0C3a0aa9' }],
        ['token lô khác token hệ thống', (g) => ({ ...g, token_address: '0x0000000000000000000000000000000000000001' }), {}],
        ['token trong báo giá bị đổi', (g) => { g.orders[0].quote.token = '0x0000000000000000000000000000000000000001'; return g; }, {}],
        ['số tiền báo giá lệch amount_raw', (g) => { g.orders[0].quote.amount = '1'; return g; }, {}],
        ['tổng lô lệch tổng các đơn', (g) => ({ ...g, total_amount_raw: '1' }), {}],
        ['thiếu chữ ký', (g) => { g.orders[1].signature = null; return g; }, {}],
        ['lô rỗng', (g) => ({ ...g, orders: [] }), {}],
    ])('từ chối khi %s', (_, mutate, opts) => {
        const g = mutate(group());
        expect(() => validateGroupForDeposit(g, { account: BUYER, deployment, ...opts })).toThrow(FlowError);
    });

    it('quá 5 shop thì BATCH_TOO_LARGE', () => {
        try { validateGroupForDeposit(group([1, 1, 1, 1, 1, 1]), { account: BUYER, deployment }); throw new Error('phải ném'); } catch (e) { expect(e.code).toBe(FLOW_ERROR.BATCH_TOO_LARGE); }
    });
});

describe('mapDepositError (SDD 9.5)', () => {
    it('4001 là hủy, không phải lỗi hệ thống', () => {
        const m = mapDepositError({ code: 4001 });
        expect(m.userRejected).toBe(true);
        expect(m.message).toBe('Bạn đã hủy thao tác.');
        expect(mapDepositError({ code: 'ACTION_REJECTED' }).userRejected).toBe(true);
    });

    it.each([
        ['Quote expired', /hết hạn/],
        ['Invalid batch size', /tối đa 5 shop/],
        ['Fee exceeds on-chain cap', /Phí sàn đã thay đổi/],
        ['Caller must be quote buyer', /không thuộc ví đang kết nối/],
        ['Bad quote signature', /Chữ ký báo giá/],
    ])('revert "%s" -> thông báo tiếng Việt', (reason, re) => {
        expect(mapDepositError({ reason }).message).toMatch(re);
        expect(mapDepositError({ shortMessage: `execution reverted: "${reason}"` }).message).toMatch(re);
        expect(mapDepositError({ info: { error: { message: `VM Exception: revert ${reason}` } } }).message).toMatch(re);
    });

    it('Order exists có mã riêng để giao diện chuyển sang chờ Indexer', () => {
        const m = mapDepositError({ reason: 'Order exists' });
        expect(m.code).toBe(FLOW_ERROR.ORDER_EXISTS);
        expect(m.message).toBe('Đơn này đã được thanh toán.');
    });

    it('lỗi lạ: thông báo chung nói rõ tiền không bị trừ, không lộ chi tiết kỹ thuật', () => {
        const m = mapDepositError(new Error('0xdeadbeef internal rpc 500'));
        expect(m.message).not.toContain('0xdeadbeef');
        expect(m.message).toContain('không bị trừ');
    });
});

describe('runDeposit', () => {
    const base = () => {
        const calls = [];
        const token = {
            balanceOf: vi.fn(async () => 1_000_000_000n), allowance: vi.fn(async () => 0n),
            approve: vi.fn(async (...a) => { calls.push('approve'); return Object.assign(tx('0xapprove'), { args: a }); }),
        };
        const escrow = { depositEscrowBatch: vi.fn(async () => { calls.push('deposit'); return tx('0xdeposit'); }) };
        const events = [];
        return { calls, token, escrow, events, dispatch: (e) => events.push(e), params: { group: group(), account: BUYER, deployment, remaining: () => 900 } };
    };
    const go = (b, over = {}) => runDeposit({ ...b.params, token: b.token, escrow: b.escrow, dispatch: b.dispatch, ...over });

    it('approve đúng TỔNG của lô cho hợp đồng ký quỹ, rồi nạp gom đúng một lần (thứ tự bắt buộc)', async () => {
        const b = base();
        const r = await go(b);
        expect(b.calls).toEqual(['approve', 'deposit']);
        expect(b.token.approve).toHaveBeenCalledWith(ESCROW, 20_760_000n);
        const [quotes, sigs] = b.escrow.depositEscrowBatch.mock.calls[0];
        expect(quotes).toHaveLength(2);
        expect(sigs).toHaveLength(2);
        expect(r.depositHash).toBe('0xdeposit');
        expect(b.events.map((e) => e.type)).toEqual(['START', 'APPROVE_REQUESTED', 'APPROVE_SENT', 'APPROVED', 'DEPOSIT_REQUESTED', 'DEPOSIT_SENT', 'DEPOSIT_MINED']);
        const final = b.events.reduce(depositReducer, initialDepositState());
        expect(final.step).toBe(STEP.WAITING_INDEXER); // KHÔNG LOCKED
    });

    it('đủ hạn mức thì không approve', async () => {
        const b = base();
        b.token.allowance = vi.fn(async () => 20_760_000n);
        await go(b);
        expect(b.token.approve).not.toHaveBeenCalled();
        expect(b.events.map((e) => e.type)).toEqual(['START', 'ALLOWANCE_OK', 'DEPOSIT_REQUESTED', 'DEPOSIT_SENT', 'DEPOSIT_MINED']);
    });

    it('thiếu số dư: báo số thiếu, KHÔNG gọi ví lần nào', async () => {
        const b = base();
        b.token.balanceOf = vi.fn(async () => 20_000_000n);
        await expect(go(b)).rejects.toMatchObject({ code: FLOW_ERROR.INSUFFICIENT_BALANCE });
        const fail = b.events.find((e) => e.type === 'FAIL');
        expect(fail.error.extra.shortfall).toBe('760000');
        expect(b.token.approve).not.toHaveBeenCalled();
        expect(b.escrow.depositEscrowBatch).not.toHaveBeenCalled();
    });

    it('báo giá còn dưới 60 giây hoặc hết hạn: dừng trước khi bật ví', async () => {
        for (const rem of [59, 0, -5]) {
            const b = base();
            await expect(go(b, { remaining: () => rem })).rejects.toMatchObject({ code: FLOW_ERROR.QUOTE_EXPIRING });
            expect(b.token.balanceOf).not.toHaveBeenCalled();
            expect(b.token.approve).not.toHaveBeenCalled();
        }
    });

    it('hạn cạn trong lúc chờ approve: không bật cửa sổ ví lần hai', async () => {
        const b = base();
        let rem = 900;
        b.token.approve = vi.fn(async () => { rem = 30; return tx('0xapprove'); }); // approve xong thì chỉ còn 30 giây
        await expect(go(b, { remaining: () => rem })).rejects.toMatchObject({ code: FLOW_ERROR.QUOTE_EXPIRING });
        expect(b.escrow.depositEscrowBatch).not.toHaveBeenCalled();
    });

    it('báo giá sai ví/token: không đọc chuỗi, không gửi gì', async () => {
        const b = base();
        const g = group();
        g.orders[0].quote.buyer = '0x976EA74026E726554dB657fA54763abd0C3a0aa9';
        await expect(go(b, { group: g })).rejects.toMatchObject({ code: FLOW_ERROR.QUOTE_MISMATCH });
        expect(b.token.balanceOf).not.toHaveBeenCalled();
    });

    it('người dùng hủy approve (4001): không nạp, phát FAIL userRejected', async () => {
        const b = base();
        b.token.approve = vi.fn(async () => { throw Object.assign(new Error('User denied'), { code: 4001 }); });
        await expect(go(b)).rejects.toMatchObject({ code: 4001 });
        expect(b.escrow.depositEscrowBatch).not.toHaveBeenCalled();
        expect(b.events.at(-1)).toMatchObject({ type: 'FAIL', error: { userRejected: true } });
    });

    it('nạp gom bị revert: cả lô thất bại, thông báo theo lý do', async () => {
        const b = base();
        b.escrow.depositEscrowBatch = vi.fn(async () => { throw Object.assign(new Error('x'), { reason: 'Quote expired' }); });
        await expect(go(b)).rejects.toBeTruthy();
        const fail = b.events.at(-1);
        expect(fail.error.message).toMatch(/hết hạn/);
        expect(b.events.map((e) => e.type)).not.toContain('DEPOSIT_MINED');
    });

    it('giao dịch nạp bị revert khi chờ biên nhận (tx.wait ném lỗi) cũng thành FAIL', async () => {
        const b = base();
        b.escrow.depositEscrowBatch = vi.fn(async () => ({ hash: '0xdeposit', wait: async () => { throw Object.assign(new Error('x'), { reason: 'Invalid batch size' }); } }));
        await expect(go(b)).rejects.toBeTruthy();
        expect(b.events.at(-1).error.message).toMatch(/tối đa 5 shop/);
    });
});

describe('tương thích ABI thật (lib/abi/SlopeeEscrowMaster.json)', () => {
    it('quoteToTuple + chữ ký mã hóa được thành lệnh depositEscrowBatch và giải mã lại đúng', async () => {
        const { Interface } = await import('ethers');
        const abi = (await import('../lib/abi/SlopeeEscrowMaster.json')).default;
        const iface = new Interface(abi);
        const g = group();
        const { quotes, sigs } = validateGroupForDeposit(g, { account: BUYER, deployment });
        const data = iface.encodeFunctionData('depositEscrowBatch', [quotes, sigs]);
        const [dq, ds] = iface.decodeFunctionData('depositEscrowBatch', data);
        expect(dq).toHaveLength(2);
        expect(dq[0].orderId).toBe(100n);
        expect(dq[1].amount).toBe(4_800_000n);
        expect(dq[0].docHash).toBe(HASH);
        expect(ds[0]).toBe(g.orders[0].signature);
    });

    it('MockUSD.approve có trong ABI token (bước 1)', async () => {
        const { Interface } = await import('ethers');
        const abi = (await import('../lib/abi/MockUSD.json')).default;
        expect(() => new Interface(abi).encodeFunctionData('approve', [ESCROW, 20_760_000n])).not.toThrow();
    });
});
