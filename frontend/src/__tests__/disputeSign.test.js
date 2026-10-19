import { describe, expect, it } from 'vitest';
import {
    OUTCOME, buildDisputeMessage, describeOutcome, disputePhase, expectedWallet, hasSigned, mySignature, outcomeOf, payoutBreakdown, proposalProblems, signGate,
} from '../lib/disputeSign';
import { ADDR, NOW, makeView } from './helpers/disputeFixtures';

const ok = { isConnected: true, isCorrectChain: true, account: ADDR.buyer };

describe('outcomeOf — kết quả suy từ ĐỊA CHỈ, không tin nhãn máy chủ', () => {
    it('nhận diện Buyer/Merchant (không phân biệt hoa thường), lạ thì UNKNOWN', () => {
        expect(outcomeOf({ payoutTo: ADDR.buyer.toLowerCase(), buyerWallet: ADDR.buyer, merchantWallet: ADDR.merchant })).toBe(OUTCOME.REFUND_BUYER);
        expect(outcomeOf({ payoutTo: ADDR.merchant, buyerWallet: ADDR.buyer, merchantWallet: ADDR.merchant })).toBe(OUTCOME.PAY_MERCHANT);
        expect(outcomeOf({ payoutTo: ADDR.stranger, buyerWallet: ADDR.buyer, merchantWallet: ADDR.merchant })).toBe(OUTCOME.UNKNOWN);
        expect(outcomeOf({ payoutTo: null, buyerWallet: ADDR.buyer, merchantWallet: ADDR.merchant })).toBe(OUTCOME.UNKNOWN);
    });
});

describe('describeOutcome (số tiền chính xác bằng BigInt)', () => {
    it('hoàn tiền: Buyer nhận 100%', () => {
        const d = describeOutcome(makeView());
        expect(d).toMatchObject({ outcome: OUTCOME.REFUND_BUYER, headline: 'Hoàn tiền cho Buyer', recipient: ADDR.buyer });
        expect(d.transfer).toBe('25,00 mUSD');
    });
    it('giải ngân: Merchant nhận amount - phí theo fee_bps đã khóa', () => {
        const d = describeOutcome(makeView({}, { payout_to: ADDR.merchant }));
        expect(d.headline).toBe('Giải ngân cho Merchant');
        expect(d.transfer).toBe('24,25 mUSD'); // 25 - 3% = 24,25
        expect(d.note).toMatch(/0,75 mUSD/);
    });
    it('địa chỉ lạ: đánh dấu không hợp lệ', () => expect(describeOutcome(makeView({}, { payout_to: ADDR.stranger })).outcome).toBe(OUTCOME.UNKNOWN));
    it('payoutBreakdown làm tròn xuống như contract (amount*bps/10000)', () => {
        expect(payoutBreakdown({ amount_raw: '333', fee_bps: 300 })).toEqual({ amount: 333n, fee: 9n, merchantNet: 324n });
    });
});

describe('buildDisputeMessage — đúng 5 trường của DisputeResolution', () => {
    it('lấy orderId on-chain, các số là BigInt', () => {
        expect(buildDisputeMessage(makeView())).toEqual({ orderId: 100501n, payoutTo: ADDR.buyer, amount: 25000000n, nonce: 0n, deadline: BigInt(NOW + 7 * 86400) });
    });
    it('số lớn không mất chính xác (uint256)', () => {
        const big = '115792089237316195423570985008687907853269984665640564039457584007913129639935';
        expect(buildDisputeMessage(makeView({}, { amount_raw: big })).amount).toBe(BigInt(big));
    });
});

describe('proposalProblems — chặn ký đề xuất mà hợp đồng sẽ từ chối', () => {
    it('đề xuất hợp lệ: không vấn đề', () => expect(proposalProblems(makeView(), NOW)).toEqual([]));
    it('không có đề xuất', () => expect(proposalProblems(makeView({ resolution: null }), NOW)).toEqual(['NO_PROPOSAL']));
    it('đơn không còn DISPUTED', () => expect(proposalProblems(makeView({ order_status: 'COMPLETED' }), NOW)).toContain('ORDER_NOT_DISPUTED'));
    it('payoutTo không phải Buyer/Merchant', () => expect(proposalProblems(makeView({}, { payout_to: ADDR.stranger }), NOW)).toContain('BAD_PAYOUT'));
    it('số tiền đề xuất khác số tiền ký quỹ', () => expect(proposalProblems(makeView({}, { amount_raw: '24999999' }), NOW)).toContain('AMOUNT_MISMATCH'));
    it('deadline không nhỏ hơn disputedAt + disputeTimeout (contract revert)', () => {
        const v = makeView();
        const limit = v.disputed_at + v.dispute_timeout;
        expect(proposalProblems(makeView({}, { deadline: limit }), NOW)).toContain('DEADLINE_AFTER_TIMEOUT');
        expect(proposalProblems(makeView({}, { deadline: limit - 1 }), NOW)).not.toContain('DEADLINE_AFTER_TIMEOUT');
    });
    it('đã quá hạn theo giờ máy chủ', () => expect(proposalProblems(makeView(), NOW + 8 * 86400)).toContain('EXPIRED'));
    it('dữ liệu hỏng (nonce không phải số)', () => expect(proposalProblems(makeView({}, { nonce: 'abc' }), NOW)).toContain('MALFORMED'));
    it('chưa có đồng hồ (nowSec null) thì chưa kết luận hết hạn', () => expect(proposalProblems(makeView({}, { deadline: 1 }), null)).not.toContain('EXPIRED'));
});

describe('disputePhase', () => {
    const cases = [
        ['chưa tải', null, NOW, 'LOADING'],
        ['không có đề xuất, đơn DISPUTED', makeView({ resolution: null }), NOW, 'AWAITING_PROPOSAL'],
        ['không có đề xuất, đơn không DISPUTED', makeView({ resolution: null, order_status: 'LOCKED' }), NOW, 'NOT_DISPUTED'],
        ['đề xuất hợp lệ, mình chưa ký', makeView(), NOW, 'CAN_SIGN'],
        ['đề xuất lỗi dữ liệu', makeView({}, { payout_to: ADDR.stranger }), NOW, 'BLOCKED'],
        ['READY', makeView({}, { status: 'READY' }), NOW, 'READY'],
        ['SUBMITTED', makeView({}, { status: 'SUBMITTED' }), NOW, 'SUBMITTED'],
        ['EXECUTED', makeView({}, { status: 'EXECUTED' }), NOW, 'EXECUTED'],
        ['đơn đã REFUNDED (Indexer ghi)', makeView({ order_status: 'REFUNDED' }), NOW, 'EXECUTED'],
        ['EXPIRED theo máy chủ', makeView({}, { status: 'EXPIRED' }), NOW, 'EXPIRED'],
        ['quá hạn theo đồng hồ dù máy chủ chưa cập nhật', makeView(), NOW + 8 * 86400, 'EXPIRED'],
        ['CANCELLED', makeView({}, { status: 'CANCELLED' }), NOW, 'CANCELLED'],
    ];
    it.each(cases)('%s -> %s', (_n, view, now, want) => expect(disputePhase(view, now)).toBe(want));
    it('mình đã ký (PROPOSED nhưng có chữ ký của mình) coi như READY, không cho ký lại', () => {
        const v = makeView({}, { signatures: [{ party: 'ARBITRATOR' }, { party: 'BUYER' }] });
        expect(disputePhase(v, NOW)).toBe('READY');
    });
});

describe('ví và chữ ký của bên mình', () => {
    it('expectedWallet theo vai trò', () => {
        expect(expectedWallet(makeView())).toBe(ADDR.buyer);
        expect(expectedWallet(makeView({ your_party: 'MERCHANT' }))).toBe(ADDR.merchant);
        expect(expectedWallet(makeView({ your_party: 'ADMIN' }))).toBeNull();
    });
    it('signGate', () => {
        expect(signGate(makeView(), ok)).toBe('OK');
        expect(signGate(makeView(), { ...ok, isConnected: false })).toBe('NOT_CONNECTED');
        expect(signGate(makeView(), { ...ok, isCorrectChain: false })).toBe('WRONG_CHAIN');
        expect(signGate(makeView(), { ...ok, account: ADDR.merchant })).toBe('WRONG_ACCOUNT'); // Buyer không ký bằng ví Merchant
        expect(signGate(makeView({ your_party: 'ADMIN' }), ok)).toBe('NOT_A_PARTY');
    });
    it('hasSigned / mySignature', () => {
        const v = makeView({}, { signatures: [{ party: 'ARBITRATOR' }, { party: 'MERCHANT', signer: 'x' }] });
        expect(hasSigned(v, 'ARBITRATOR')).toBe(true);
        expect(hasSigned(v, 'BUYER')).toBe(false);
        expect(mySignature(v)).toBeNull();
        expect(mySignature({ ...v, your_party: 'MERCHANT' })).toMatchObject({ signer: 'x' });
    });
});
