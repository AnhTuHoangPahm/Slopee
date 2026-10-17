import { describe, expect, it } from 'vitest';
import { groupOrders } from '../lib/groupOrders';

const o = (orderId, gid) => ({ orderId, web3: gid === undefined ? null : { checkout_group_id: gid } });

describe('groupOrders (BR-11)', () => {
    it('đơn cùng checkout_group_id gom một lô, giữ thứ tự xuất hiện', () => {
        const g = groupOrders([o('a', 'g1'), o('legacy'), o('b', 'g1'), o('c', 'g2')]);
        expect(g.map((x) => [x.key, x.orders.map((i) => i.orderId)])).toEqual([['g:g1', ['a', 'b']], ['o:legacy', ['legacy']], ['g:g2', ['c']]]);
    });
    it('đơn cũ không bao giờ bị gom với nhau', () => expect(groupOrders([o('x'), o('y')])).toHaveLength(2));
    it('rỗng/undefined', () => { expect(groupOrders([])).toEqual([]); expect(groupOrders(undefined)).toEqual([]); });
});
