import { describe, expect, it, vi } from 'vitest';
import { buildDomain, recoverDisputeSigner } from '../lib/eip712';
import { SIGN_STEP, initialSignState, isRetryableSendError, sendSignature, signAndSendDispute, signReducer } from '../lib/disputeFlow';
import { buildDisputeMessage } from '../lib/disputeSign';
import { ADDR, DEPLOYMENT, WALLET, makeView } from './helpers/disputeFixtures';

const collect = () => { const events = []; return { events, dispatch: (e) => events.push(e) }; };
const run = (events) => events.reduce(signReducer, initialSignState());

describe('signReducer', () => {
    it('đường vui IDLE -> SIGNING -> SENDING -> DONE', () => {
        expect(run([{ type: 'START' }]).step).toBe(SIGN_STEP.SIGNING);
        expect(run([{ type: 'START' }, { type: 'SIGNED', signature: '0x1' }])).toMatchObject({ step: SIGN_STEP.SENDING, signature: '0x1' });
        expect(run([{ type: 'START' }, { type: 'SIGNED', signature: '0x1' }, { type: 'DONE' }]).step).toBe(SIGN_STEP.DONE);
    });
    it('sự kiện sai thứ tự bị bỏ qua', () => {
        expect(run([{ type: 'DONE' }]).step).toBe(SIGN_STEP.IDLE);
        expect(run([{ type: 'SIGNED', signature: 'x' }]).step).toBe(SIGN_STEP.IDLE);
        expect(run([{ type: 'START' }, { type: 'START' }]).step).toBe(SIGN_STEP.SIGNING);
    });
    it('gửi lỗi giữ chữ ký; RESEND gửi lại không cần ký lại; START ký lại từ đầu', () => {
        const failed = run([{ type: 'START' }, { type: 'SIGNED', signature: '0xabc' }, { type: 'FAIL', error: { retryable: true } }]);
        expect(failed).toMatchObject({ step: SIGN_STEP.FAILED, signature: '0xabc' });
        expect(signReducer(failed, { type: 'RESEND' })).toMatchObject({ step: SIGN_STEP.SENDING, signature: '0xabc', error: null });
        expect(signReducer(failed, { type: 'START' })).toMatchObject({ step: SIGN_STEP.SIGNING, signature: null });
    });
    it('FAIL không đè DONE', () => expect(run([{ type: 'START' }, { type: 'SIGNED', signature: 's' }, { type: 'DONE' }, { type: 'FAIL', error: {} }]).step).toBe(SIGN_STEP.DONE));
});

describe('signAndSendDispute (ví ethers THẬT ký typed data)', () => {
    const base = (over = {}) => ({ view: makeView(), signer: WALLET.buyer, deployment: DEPLOYMENT, expectedWallet: ADDR.buyer, ...over });

    it('ký đúng typed data và gửi chữ ký khôi phục ra đúng ví của Buyer', async () => {
        const send = vi.fn(async () => ({ status: 'READY' }));
        const { events, dispatch } = collect();
        const res = await signAndSendDispute({ ...base(), send, dispatch });
        expect(res).toEqual({ status: 'READY' });
        expect(events.map((e) => e.type)).toEqual(['START', 'SIGNED', 'DONE']);
        const [code, body] = send.mock.calls[0];
        expect(code).toBe('ord-1');
        expect(body.resolutionId).toBe(7);
        expect(body.signature).toMatch(/^0x[0-9a-f]{130}$/);
        expect(recoverDisputeSigner(buildDomain(DEPLOYMENT), buildDisputeMessage(makeView()), body.signature)).toBe(ADDR.buyer);
    });
    it('Merchant ký bằng ví Merchant', async () => {
        const send = vi.fn(async () => ({ status: 'READY' }));
        const view = makeView({ your_party: 'MERCHANT' }, { payout_to: ADDR.merchant });
        await signAndSendDispute({ view, signer: WALLET.merchant, deployment: DEPLOYMENT, expectedWallet: ADDR.merchant, send, dispatch: () => {} });
        expect(recoverDisputeSigner(buildDomain(DEPLOYMENT), buildDisputeMessage(view), send.mock.calls[0][1].signature)).toBe(ADDR.merchant);
    });
    it('đổi nội dung đề xuất (số tiền/nonce) thì chữ ký khác: không tái dùng được cho đề xuất khác', async () => {
        const sigs = [];
        for (const nonce of [0, 1]) {
            await signAndSendDispute({ ...base({ view: makeView({}, { nonce }) }), send: async (_c, b) => sigs.push(b.signature), dispatch: () => {} });
        }
        expect(sigs[0]).not.toBe(sigs[1]);
    });
    it('sai tài khoản ví: KHÔNG ký, KHÔNG gửi, báo ACCOUNT_CHANGED', async () => {
        const send = vi.fn();
        const spy = vi.spyOn(WALLET.stranger, 'signTypedData');
        const { events, dispatch } = collect();
        await expect(signAndSendDispute({ ...base({ signer: WALLET.stranger }), send, dispatch })).rejects.toBeTruthy();
        expect(spy).not.toHaveBeenCalled();
        expect(send).not.toHaveBeenCalled();
        expect(events.at(-1).error).toMatchObject({ code: 'ACCOUNT_CHANGED', retryable: false });
        spy.mockRestore();
    });
    it('hủy trong MetaMask (4001): thông báo nhẹ, không gửi gì', async () => {
        const signer = { getAddress: async () => ADDR.buyer, signTypedData: async () => { throw Object.assign(new Error('rejected'), { code: 4001 }); } };
        const send = vi.fn();
        const { events, dispatch } = collect();
        await expect(signAndSendDispute({ ...base({ signer }), send, dispatch })).rejects.toBeTruthy();
        expect(events.at(-1).error).toMatchObject({ code: 'USER_REJECTED', userRejected: true });
        expect(send).not.toHaveBeenCalled();
    });
    it('ví trả chữ ký của người khác: bị chặn trước khi gửi (SIGNER_MISMATCH)', async () => {
        const signer = { getAddress: async () => ADDR.buyer, signTypedData: (...a) => WALLET.stranger.signTypedData(...a) };
        const send = vi.fn();
        const { events, dispatch } = collect();
        await expect(signAndSendDispute({ ...base({ signer }), send, dispatch })).rejects.toBeTruthy();
        expect(events.at(-1).error.code).toBe('SIGNER_MISMATCH');
        expect(send).not.toHaveBeenCalled();
    });
    it('gửi lỗi mạng: giữ chữ ký, cho gửi lại KHÔNG cần ký lại', async () => {
        const send = vi.fn().mockRejectedValueOnce(Object.assign(new Error('mạng lỗi'), { code: 'NETWORK_ERROR', status: 0 })).mockResolvedValue({ status: 'READY' });
        const { events, dispatch } = collect();
        await expect(signAndSendDispute({ ...base(), send, dispatch })).rejects.toBeTruthy();
        expect(events.at(-1).error).toMatchObject({ retryable: true, stage: 'SEND' });
        const signature = events.find((e) => e.type === 'SIGNED').signature;
        const spy = vi.spyOn(WALLET.buyer, 'signTypedData');
        await sendSignature({ view: makeView(), signature, send, dispatch });
        expect(spy).not.toHaveBeenCalled();
        expect(send.mock.calls[1][1].signature).toBe(signature);
        spy.mockRestore();
    });
    it('máy chủ từ chối (4xx) là kết quả cuối, không tự thử lại', async () => {
        const send = vi.fn().mockRejectedValue(Object.assign(new Error('Chữ ký không hợp lệ'), { code: 'BAD_SIGNATURE', status: 422 }));
        const { events, dispatch } = collect();
        await expect(signAndSendDispute({ ...base(), send, dispatch })).rejects.toBeTruthy();
        expect(events.at(-1).error).toMatchObject({ code: 'BAD_SIGNATURE', retryable: false });
        expect(send).toHaveBeenCalledTimes(1);
    });
});

describe('isRetryableSendError', () => {
    it.each([[{ code: 'NETWORK_ERROR', status: 0 }, true], [{ status: 502 }, true], [{ status: 500 }, true], [{ status: 404 }, false], [{ status: 409 }, false], [{ status: 422 }, false]])('%j -> %s', (e, want) =>
        expect(isRetryableSendError(e)).toBe(want));
});
