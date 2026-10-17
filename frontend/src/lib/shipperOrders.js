// Hàm thuần cho cổng Shipper (UC-03): tách khỏi ShipperOrders.jsx để kiểm thử không cần dựng giao diện.

/** Trạng thái hiển thị của một đơn trên cổng Shipper. */
export const SHIPPER_STATUS = Object.freeze({
    LOCKED: 'LOCKED',        // tiền đã khóa, chờ giao hàng: được bấm "Xác nhận phát hàng thành công"
    DELIVERED: 'DELIVERED',  // đã xác nhận (Indexer đã ghi nhận): chỉ xem
});

/** Chuẩn hóa một dòng từ API về các trường giao diện dùng (thiếu trường nào thì để null, không đoán). */
export function normalizeShipperOrder(o) {
    const code = o?.order_id ?? o?.code ?? null;
    return {
        code,
        status: o?.status ?? SHIPPER_STATUS.LOCKED,
        shopName: o?.shop_name ?? null,
        buyerName: o?.buyer_name ?? null,
        priceVnd: o?.price_vnd == null ? null : Number(o.price_vnd),
        lockedAt: o?.chain_created_at == null ? null : Number(o.chain_created_at),
        deliveredAt: o?.delivered_at == null ? null : Number(o.delivered_at),
    };
}

/** Đơn nào còn thao tác được: LOCKED và chưa có lượt gửi nào đang chờ Indexer. */
export const canDeliver = (order, local) => order.status === SHIPPER_STATUS.LOCKED && !(local && (local.phase === 'sending' || local.phase === 'sent'));

/** Câu thông báo sau khi bấm xác nhận thành công. `outcome` lấy từ phản hồi của API. */
export function deliverSuccessMessage(result) {
    if (result?.outcome === 'ALREADY_DELIVERED') return 'Đơn này đã được xác nhận giao trước đó.';
    return 'Đã gửi xác nhận giao hàng lên blockchain. Hệ thống đang ghi nhận, người mua sẽ thấy hạn kiểm tra hàng ngay sau đó.';
}

/**
 * Ghép dữ liệu máy chủ với trạng thái thao tác cục bộ. Khi máy chủ báo đơn đã DELIVERED hoặc đơn biến mất khỏi danh sách
 * (đã giao xong), trạng thái cục bộ của đơn đó hết ý nghĩa và bị bỏ: tránh nút kẹt ở "đang chờ" mãi.
 */
export function pruneLocal(local, orders) {
    const byCode = new Map(orders.map((o) => [o.code, o]));
    const next = {};
    for (const [code, st] of Object.entries(local)) {
        const o = byCode.get(code);
        if (st.phase === 'sent' && (!o || o.status !== SHIPPER_STATUS.LOCKED)) continue;   // Indexer đã ghi nhận
        next[code] = st;
    }
    return next;
}
