import { describe, expect, it } from 'vitest';
import { canDeliver, deliverSuccessMessage, normalizeShipperOrder, pruneLocal, SHIPPER_STATUS } from '../lib/shipperOrders';

describe('normalizeShipperOrder', () => {
    it('ánh xạ trường API sang trường giao diện, thiếu thì null (không đoán)', () => {
        const o = normalizeShipperOrder({ order_id: 'abc', status: 'LOCKED', shop_name: 'Shop A', price_vnd: '125000', chain_created_at: 1800000000 });
        expect(o).toEqual({ code: 'abc', status: 'LOCKED', shopName: 'Shop A', buyerName: null, priceVnd: 125000, lockedAt: 1800000000, deliveredAt: null });
    });
    it('không có status thì coi là LOCKED (API chỉ trả đơn chờ giao)', () => {
        expect(normalizeShipperOrder({ order_id: 'x' }).status).toBe(SHIPPER_STATUS.LOCKED);
    });
});

describe('canDeliver', () => {
    const locked = { status: 'LOCKED' };
    it('đơn LOCKED chưa thao tác -> được bấm', () => expect(canDeliver(locked, undefined)).toBe(true));
    it('đang gửi hoặc đã gửi chờ Indexer -> khóa nút (chống bấm đúp)', () => {
        expect(canDeliver(locked, { phase: 'sending' })).toBe(false);
        expect(canDeliver(locked, { phase: 'sent' })).toBe(false);
    });
    it('lỗi lần trước -> cho thử lại; đơn đã DELIVERED -> không bấm', () => {
        expect(canDeliver(locked, { phase: 'error' })).toBe(true);
        expect(canDeliver({ status: 'DELIVERED' }, undefined)).toBe(false);
    });
});

describe('deliverSuccessMessage', () => {
    it('ALREADY_DELIVERED nói rõ đã giao trước đó, không hứa là vừa gửi', () => {
        expect(deliverSuccessMessage({ outcome: 'ALREADY_DELIVERED' })).toMatch(/trước đó/);
        expect(deliverSuccessMessage({ outcome: 'SENT' })).toMatch(/blockchain/);
    });
});

describe('pruneLocal', () => {
    it('bỏ trạng thái "sent" khi đơn đã DELIVERED hoặc đã khỏi danh sách; giữ trạng thái còn ý nghĩa', () => {
        const local = { a: { phase: 'sent' }, b: { phase: 'sent' }, c: { phase: 'sent' }, d: { phase: 'error', message: 'x' } };
        const orders = [{ code: 'a', status: 'DELIVERED' }, { code: 'b', status: 'LOCKED' }, { code: 'd', status: 'LOCKED' }];
        expect(pruneLocal(local, orders)).toEqual({ b: { phase: 'sent' }, d: { phase: 'error', message: 'x' } });
    });
});
