import { describe, it, expect, vi } from 'vitest';
import {
    QUOTE_MIN_REMAINING, describeDuration, formatCountdown, formatFeeBps, formatTokenAmount, quoteStatus, secondsRemaining, sumRaw,
} from '../lib/web3Checkout';
import { ERROR_MESSAGES, Web3ApiError, isUserRejection, toUserMessage } from '../lib/errors';
import { LINK_STEP, linkState, runLinkFlow } from '../lib/walletLink';
import { shortAddress } from '../lib/format';

describe('formatTokenAmount (BigInt, không float)', () => {
    it.each([
        ['15960000', 6, 'mUSD', '15,96 mUSD'],
        ['1000000', 6, 'mUSD', '1,00 mUSD'],
        ['40', 6, 'mUSD', '0,00004 mUSD'],
        ['0', 6, 'mUSD', '0,00 mUSD'],
        ['1234567890123', 6, 'mUSD', '1.234.567,890123 mUSD'],
        ['999999999999999999999999999999', 6, 'mUSD', '999.999.999.999.999.999.999.999,999999 mUSD'], // > 2^53 vẫn đúng từng chữ số
        ['-1500000', 6, 'mUSD', '-1,50 mUSD'],
        ['5', 0, 'x', '5 x'],
    ])('%s (%i) -> %s', (raw, dec, sym, out) => expect(formatTokenAmount(raw, dec, sym)).toBe(out));

    it('đầu vào rác trả dấu gạch, không ném lỗi', () => {
        expect(formatTokenAmount('abc')).toBe('—');
        expect(formatTokenAmount(undefined)).toBe('—');
        expect(formatTokenAmount('1.5')).toBe('—');
    });

    it('sumRaw cộng chuỗi lớn chính xác', () => {
        expect(sumRaw(['8000000', '12000000'])).toBe('20000000');
        expect(sumRaw([String(2n ** 200n), '1'])).toBe(String(2n ** 200n + 1n));
        expect(sumRaw([])).toBe('0');
    });
});

describe('hạn báo giá theo đồng hồ máy chủ', () => {
    it('đúng khi đồng hồ máy người dùng lệch 1 giờ', () => {
        const received = 1_000_000_000_000; // ms phía client lúc nhận
        const clientWrongBy = 3600_000; // client chạy nhanh 1 giờ so với máy chủ
        const serverTime = (received - clientWrongBy) / 1000;
        const deadline = serverTime + 900;
        // 10 giây sau khi nhận, vẫn còn 890 giây dù đồng hồ client sai
        expect(secondsRemaining({ deadline, serverTime, receivedAtMs: received, nowMs: received + 10_000 })).toBe(890);
    });

    it('quoteStatus: ok / expiring / expired theo ngưỡng 60 giây', () => {
        expect(QUOTE_MIN_REMAINING).toBe(60);
        expect(quoteStatus(61)).toBe('ok');
        expect(quoteStatus(60)).toBe('ok');
        expect(quoteStatus(59)).toBe('expiring');
        expect(quoteStatus(1)).toBe('expiring');
        expect(quoteStatus(0)).toBe('expired');
        expect(quoteStatus(-5)).toBe('expired');
    });

    it('formatCountdown', () => {
        expect(formatCountdown(900)).toBe('15:00');
        expect(formatCountdown(61)).toBe('01:01');
        expect(formatCountdown(-3)).toBe('00:00');
    });
});

describe('hiển thị thời hạn và phí', () => {
    it.each([[259200, '3 ngày'], [2592000, '30 ngày'], [7200, '2 giờ'], [5400, '1 giờ 30 phút'], [90000, '1 ngày 1 giờ'], [1800, '30 phút'],
        [0, '—'], [-1, '—'], ['x', '—']])('%s -> %s', (s, out) => expect(describeDuration(s)).toBe(out));

    it('formatFeeBps', () => {
        expect(formatFeeBps(300)).toBe('3%');
        expect(formatFeeBps(250)).toBe('2,5%');
        expect(formatFeeBps(0)).toBe('0%');
    });
});

describe('thông báo lỗi', () => {
    it('ưu tiên message tiếng Việt của backend, dự phòng bằng bảng mã', () => {
        expect(toUserMessage(new Web3ApiError({ code: 'WALLET_TAKEN', message: 'Từ máy chủ' }))).toBe('Từ máy chủ');
        expect(toUserMessage(new Web3ApiError({ code: 'WALLET_TAKEN' }))).toBe(ERROR_MESSAGES.WALLET_TAKEN);
        expect(new Web3ApiError({ code: 'ZZZ' }).message).toBe('Đã có lỗi, vui lòng thử lại.');
    });

    it('lỗi ví: hủy (4001 / ACTION_REJECTED) là "Bạn đã hủy thao tác", không phải lỗi hệ thống', () => {
        expect(toUserMessage({ code: 4001 })).toBe('Bạn đã hủy thao tác.');
        expect(toUserMessage({ code: 'ACTION_REJECTED' })).toBe('Bạn đã hủy thao tác.');
        expect(isUserRejection({ code: 4001 })).toBe(true);
        expect(isUserRejection(new Web3ApiError({ code: 'NONCE_INVALID' }))).toBe(false);
    });

    it('mọi mã lỗi backend (domain/errors.py) đều có thông báo tiếng Việt', () => {
        const backendCodes = ['WALLET_NOT_LINKED', 'WALLET_TAKEN', 'NONCE_INVALID', 'BAD_SIGNATURE', 'INVALID_ADDRESS', 'RATE_LIMITED', 'QUOTE_EXPIRED',
            'INVALID_STATE', 'POLICY_OUT_OF_RANGE', 'BATCH_TOO_LARGE', 'EMPTY_CART', 'CART_ITEM_NOT_FOUND', 'GROUP_NOT_FOUND', 'PRODUCT_UNAVAILABLE',
            'OUT_OF_STOCK', 'SELF_PURCHASE', 'INVALID_AMOUNT', 'PENDING_GROUP_EXISTS', 'SETTING_INVALID', 'POLICY_NOT_CONFIGURED',
            'CHAIN_UNAVAILABLE', 'WEB3_NOT_CONFIGURED'];
        backendCodes.forEach((c) => expect(ERROR_MESSAGES[c], c).toBeTruthy());
    });

    it('lỗi lạ trả thông báo chung, không lộ chi tiết', () => {
        expect(toUserMessage(new Error('SELECT * FROM users'))).toBe('Đã có lỗi, vui lòng thử lại.');
        expect(toUserMessage(null)).toBe('Đã có lỗi, vui lòng thử lại.');
    });
});

describe('runLinkFlow (UC-00)', () => {
    const ADDR = '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc';
    const make = (over = {}) => {
        const calls = [];
        const api = {
            requestWalletNonceAPI: vi.fn(async (a) => { calls.push(['nonce', a]); return { nonce: 'n1', message: 'MSG' }; }),
            linkWalletAPI: vi.fn(async (p) => { calls.push(['link', p]); return { address: p.address.toLowerCase() }; }),
            ...over.api,
        };
        const signer = { signMessage: vi.fn(async (m) => { calls.push(['sign', m]); return '0xSIG'; }), getAddress: async () => ADDR, ...over.signer };
        return { api, signer, calls };
    };

    it('nonce -> ký đúng thông điệp của backend -> gửi chữ ký kèm nonce, theo đúng thứ tự', async () => {
        const { api, signer, calls } = make();
        const steps = [];
        const out = await runLinkFlow({ address: ADDR, signer, api, onStep: (s) => steps.push(s) });
        expect(calls).toEqual([['nonce', ADDR], ['sign', 'MSG'], ['link', { address: ADDR, signature: '0xSIG', nonce: 'n1' }]]);
        expect(steps).toEqual([LINK_STEP.REQUESTING_NONCE, LINK_STEP.AWAITING_SIGNATURE, LINK_STEP.LINKING, LINK_STEP.DONE]);
        expect(out.address).toBe(ADDR.toLowerCase());
    });

    it('người dùng hủy ký: ném lại lỗi ví và KHÔNG gọi link', async () => {
        const { api, signer } = make({ signer: { signMessage: async () => { throw Object.assign(new Error('x'), { code: 4001 }); } } });
        await expect(runLinkFlow({ address: ADDR, signer, api })).rejects.toMatchObject({ code: 4001 });
        expect(api.linkWalletAPI).not.toHaveBeenCalled();
    });

    it('đổi tài khoản trong ví giữa chừng: dừng sớm với ACCOUNT_CHANGED', async () => {
        const { api, signer } = make({ signer: { getAddress: async () => '0x1111111111111111111111111111111111111111' } });
        await expect(runLinkFlow({ address: ADDR, signer, api })).rejects.toMatchObject({ code: 'ACCOUNT_CHANGED' });
        expect(api.linkWalletAPI).not.toHaveBeenCalled();
        expect(toUserMessage({ code: 'ACCOUNT_CHANGED' })).toBe(ERROR_MESSAGES.ACCOUNT_CHANGED);
    });

    it('lỗi backend (nonce hết hạn) được ném nguyên, không nuốt', async () => {
        const boom = new Web3ApiError({ code: 'NONCE_INVALID' });
        const { api, signer } = make({ api: { linkWalletAPI: async () => { throw boom; } } });
        await expect(runLinkFlow({ address: ADDR, signer, api })).rejects.toBe(boom);
    });

    it('không lấy được nonce thì không đòi ký', async () => {
        const { api, signer } = make({ api: { requestWalletNonceAPI: async () => { throw new Web3ApiError({ code: 'RATE_LIMITED' }); } } });
        await expect(runLinkFlow({ address: ADDR, signer, api })).rejects.toMatchObject({ code: 'RATE_LIMITED' });
        expect(signer.signMessage).not.toHaveBeenCalled();
    });
});

describe('linkState / shortAddress', () => {
    const A = '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc';
    it('4 trạng thái', () => {
        expect(linkState({ linked: null, account: null })).toBe('NO_ACCOUNT');
        expect(linkState({ linked: { linked: false }, account: A })).toBe('NOT_LINKED');
        expect(linkState({ linked: { linked: true, address: A.toLowerCase() }, account: A })).toBe('LINKED_THIS'); // không phân biệt hoa/thường
        expect(linkState({ linked: { linked: true, address: '0x2222222222222222222222222222222222222222' }, account: A })).toBe('LINKED_OTHER');
    });
    it('shortAddress', () => {
        expect(shortAddress(A)).toBe('0x9965…A4dc');
        expect(shortAddress('')).toBe('');
        expect(shortAddress(null)).toBe('');
    });
});
