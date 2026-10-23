import { describe, expect, it } from 'vitest';
import {
    disputePath, filterOrders, formatAmount, normalizeMerchantOrder, normalizeMerchantResponse, statusNote, summarizeOrders,
} from '../lib/merchantOrders';

const raw = (o = {}) => ({
    order_id: 'o1', onchain_order_id: '100001', status: 'LOCKED', buyer_name: 'An', items: [{ name: 'Áo', quantity: 2 }], price_vnd: 399000,
    amount_raw: '15960000', net_amount_raw: '15481200', fee_amount_raw: '478800', fee_bps: 300, token: '0xtok', symbol: 'mUSD', decimals: 6,
    merchant_wallet: '0xabc', chain_created_at: 1_800_000_000, delivered_at: null, disputed_at: null, closed_at: null,
    delivery_deadline: 1_801_209_600, release_at: null, force_resolve_at: null, ...o,
});
const norm = (o) => normalizeMerchantOrder(raw(o));
const T = (s) => `T${s}`;

describe('normalizeMerchantResponse', () => {
    it('chuẩn hóa, bỏ đơn thiếu mã/trạng thái và khoản chờ rút bằng 0', () => {
        const r = normalizeMerchantResponse({
            wallet: '0xABC', orders: [raw(), { status: 'LOCKED' }, { order_id: 'x' }],
            pending: [{ token: 'ETH', address: '0xAA', amount_raw: '5', symbol: 'ETH', decimals: 18 }, { token: 'ETH', address: '0xBB', amount_raw: '0' }],
        });
        expect(r.wallet).toBe('0xabc');
        expect(r.orders.map((o) => o.code)).toEqual(['o1']);
        expect(r.pending).toEqual([{ token: 'ETH', address: '0xaa', amountRaw: '5', symbol: 'ETH', decimals: 18 }]);
    });
    it('phản hồi hỏng/rỗng không làm vỡ', () => {
        for (const bad of [null, undefined, {}, { orders: 'x', pending: 5 }]) expect(normalizeMerchantResponse(bad)).toEqual({ wallet: null, orders: [], pending: [] });
    });
    it('số tiền giữ nguyên dạng chuỗi chính xác kể cả vượt 2^53', () => {
        const big = (10n ** 30n + 7n).toString();
        expect(norm({ amount_raw: big, net_amount_raw: big }).amountRaw).toBe(big);
        expect(norm({ amount_raw: 'abc' }).amountRaw).toBe('0');
    });
    it('mốc thời gian thiếu là null, không phải 0', () => {
        const o = norm({ delivered_at: undefined, release_at: '' });
        expect(o.deliveredAt).toBeNull();
        expect(o.releaseAt).toBeNull();
    });
});

describe('formatAmount', () => {
    it('token đã biết số thập phân', () => expect(formatAmount('15481200', 6, 'mUSD')).toBe('15,4812 mUSD'));
    it('ETH 18 số thập phân chính xác', () => expect(formatAmount('5000000000000000', 18, 'ETH')).toBe('0,005 ETH'));
    it('token lạ không đoán số thập phân', () => expect(formatAmount('123', null, 'XYZ')).toBe('123 XYZ (đơn vị nhỏ nhất)'));
});

describe('statusNote', () => {
    it('mỗi trạng thái nói đúng điều sắp xảy ra', () => {
        expect(statusNote(norm({ status: 'LOCKED' }), T)).toMatch(/T1801209600.*hủy đơn/);
        expect(statusNote(norm({ status: 'DELIVERED', release_at: 5 }), T)).toMatch(/T5.*không khiếu nại/);
        expect(statusNote(norm({ status: 'DISPUTED', force_resolve_at: 9 }), T)).toMatch(/T9.*Trọng tài/);
        expect(statusNote(norm({ status: 'COMPLETED' }), T)).toMatch(/Bạn đã nhận 15,4812 mUSD/);
        expect(statusNote(norm({ status: 'REFUNDED' }), T)).toMatch(/hoàn lại cho người mua/);
    });
    it('thiếu mốc thì vẫn có câu hợp lý, không in "null"', () => {
        for (const s of ['LOCKED', 'DELIVERED', 'DISPUTED']) expect(statusNote(norm({ status: s, delivery_deadline: null }), T)).not.toMatch(/null|undefined|NaN/);
    });
});

describe('summarizeOrders', () => {
    const orders = [
        norm({ order_id: 'a', status: 'LOCKED', net_amount_raw: '100' }),
        norm({ order_id: 'b', status: 'DELIVERED', net_amount_raw: '200' }),
        norm({ order_id: 'c', status: 'DISPUTED', net_amount_raw: '50' }),
        norm({ order_id: 'd', status: 'COMPLETED', net_amount_raw: '700' }),
        norm({ order_id: 'e', status: 'REFUNDED', net_amount_raw: '999' }),
        norm({ order_id: 'f', status: 'LOCKED', net_amount_raw: '1', token: 'ETH', symbol: 'ETH', decimals: 18 }),
    ];
    const s = summarizeOrders(orders);
    it('đang ký quỹ = LOCKED+DELIVERED+DISPUTED, cộng theo từng token, không tính REFUNDED', () => {
        expect(s.inEscrow).toEqual([
            { token: '0xtok', symbol: 'mUSD', decimals: 6, amountRaw: '350' },
            { token: 'ETH', symbol: 'ETH', decimals: 18, amountRaw: '1' },
        ]);
    });
    it('đã nhận chỉ tính COMPLETED', () => expect(s.received).toEqual([{ token: '0xtok', symbol: 'mUSD', decimals: 6, amountRaw: '700' }]));
    it('đếm theo trạng thái', () => expect(s.counts).toEqual({ LOCKED: 2, DELIVERED: 1, DISPUTED: 1, COMPLETED: 1, REFUNDED: 1 }));
    it('cộng chính xác số rất lớn', () => {
        const big = 10n ** 30n;
        const r = summarizeOrders([norm({ status: 'LOCKED', net_amount_raw: big.toString() }), norm({ order_id: 'z', status: 'LOCKED', net_amount_raw: '1' })]);
        expect(r.inEscrow[0].amountRaw).toBe((big + 1n).toString());
    });
    it('danh sách rỗng', () => expect(summarizeOrders([])).toMatchObject({ inEscrow: [], received: [] }));
});

describe('filter và liên kết tranh chấp', () => {
    const orders = [norm({ status: 'LOCKED' }), norm({ order_id: 'x', status: 'DISPUTED' })];
    it('lọc theo trạng thái', () => {
        expect(filterOrders(orders, 'ALL')).toHaveLength(2);
        expect(filterOrders(orders, 'DISPUTED').map((o) => o.code)).toEqual(['x']);
    });
    it('chỉ đơn DISPUTED có liên kết, mã được mã hóa', () => {
        expect(disputePath(orders[0])).toBeNull();
        expect(disputePath({ ...orders[1], code: 'a/b?c' })).toBe('/disputes/a%2Fb%3Fc');
    });
});
