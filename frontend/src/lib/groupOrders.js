// Gom đơn hiển thị ở "Đơn của tôi" (SDD 9.8, BR-11): các đơn Web3 cùng `checkout_group_id` nằm chung một lô
// (mỗi shop một thẻ đơn độc lập); đơn cũ và đơn Web3 lẻ đứng riêng. Giữ nguyên thứ tự API trả về (mới nhất trước).
/** @returns {Array<{ key: string, groupId: string|null, orders: object[] }>} */
export function groupOrders(orders) {
    const groups = [];
    const byGroup = new Map();
    for (const o of orders ?? []) {
        const gid = o?.web3?.checkout_group_id ?? null;
        if (gid === null) {
            groups.push({ key: `o:${o.orderId}`, groupId: null, orders: [o] });
        } else if (byGroup.has(gid)) {
            byGroup.get(gid).orders.push(o);
        } else {
            const g = { key: `g:${gid}`, groupId: gid, orders: [o] };
            byGroup.set(gid, g);
            groups.push(g);
        }
    }
    return groups;
}
