// Hàm thuần cho cổng Merchant (UC-07): tách khỏi giao diện để kiểm thử không cần dựng React.
// Mọi số tiền token là CHUỖI số nguyên (uint256) và chỉ tính bằng BigInt, không bao giờ float (AI_CONTEXT mục 4).
import { formatTokenAmount } from './web3Checkout';

export const MERCHANT_STATUS = Object.freeze({
    LOCKED: 'LOCKED', DELIVERED: 'DELIVERED', DISPUTED: 'DISPUTED', COMPLETED: 'COMPLETED', REFUNDED: 'REFUNDED',
});

/** Nhãn/màu theo GÓC NHÌN NGƯỜI BÁN (khác lib/orderStatus.js là góc nhìn người mua). */
export const MERCHANT_STATUS_META = Object.freeze({
    LOCKED: { label: 'Chờ giao hàng', color: '#1976d2', bg: '#e3f2fd' },
    DELIVERED: { label: 'Đã giao, chờ người mua kiểm tra', color: '#00796b', bg: '#e0f2f1' },
    DISPUTED: { label: 'Đang tranh chấp', color: '#5c4400', bg: '#fff3cd' },
    COMPLETED: { label: 'Đã nhận tiền', color: '#2e7d32', bg: '#e8f5e9' },
    REFUNDED: { label: 'Đã hoàn tiền cho người mua', color: '#c62828', bg: '#ffebee' },
});

/** Tiền còn nằm trong hợp đồng (chưa về ví Merchant, chưa hoàn Buyer). */
export const IN_ESCROW_STATES = Object.freeze(['LOCKED', 'DELIVERED', 'DISPUTED']);
export const FILTERS = Object.freeze(['ALL', ...Object.keys(MERCHANT_STATUS)]);

const num = (v) => (v === null || v === undefined || v === '' || !Number.isFinite(Number(v)) ? null : Number(v));
const rawOrZero = (v) => { try { return BigInt(v ?? 0).toString(); } catch { return '0'; } };

/** Mốc thời gian (giây UTC theo block) -> chuỗi giờ địa phương. */
export const formatChainTime = (sec) => (num(sec) === null ? '' : new Date(Number(sec) * 1000).toLocaleString('vi-VN'));

/** Số token chính xác; token lạ không rõ số thập phân thì hiện đơn vị nhỏ nhất, không đoán. */
export function formatAmount(raw, decimals, symbol) {
    if (decimals === null || decimals === undefined) return `${rawOrZero(raw)} ${symbol ?? ''} (đơn vị nhỏ nhất)`.trim();
    return formatTokenAmount(raw, decimals, symbol ?? '');
}

export function normalizeMerchantOrder(o) {
    return {
        code: o?.order_id ?? null,
        onchainId: o?.onchain_order_id == null ? null : String(o.onchain_order_id),
        status: o?.status ?? null,
        buyerName: o?.buyer_name ?? null,
        items: Array.isArray(o?.items) ? o.items : [],
        priceVnd: num(o?.price_vnd),
        amountRaw: rawOrZero(o?.amount_raw),
        netRaw: rawOrZero(o?.net_amount_raw),
        feeRaw: rawOrZero(o?.fee_amount_raw),
        feeBps: num(o?.fee_bps),
        token: o?.token ?? null,
        symbol: o?.symbol ?? '',
        decimals: num(o?.decimals),
        merchantWallet: o?.merchant_wallet ?? null,
        lockedAt: num(o?.chain_created_at),
        deliveredAt: num(o?.delivered_at),
        disputedAt: num(o?.disputed_at),
        closedAt: num(o?.closed_at),
        deliveryDeadline: num(o?.delivery_deadline),
        releaseAt: num(o?.release_at),
        forceResolveAt: num(o?.force_resolve_at),
    };
}

export function normalizePending(p) {
    return {
        token: p?.token ?? null,
        address: String(p?.address ?? '').toLowerCase(),
        amountRaw: rawOrZero(p?.amount_raw),
        symbol: p?.symbol ?? '',
        decimals: num(p?.decimals),
    };
}

/** Phản hồi API -> { wallet, orders, pending } sạch. Bỏ đơn không có mã và khoản chờ rút bằng 0 (không có gì để rút). */
export function normalizeMerchantResponse(data) {
    return {
        wallet: data?.wallet ? String(data.wallet).toLowerCase() : null,
        orders: (Array.isArray(data?.orders) ? data.orders : []).map(normalizeMerchantOrder).filter((o) => o.code && o.status),
        pending: (Array.isArray(data?.pending) ? data.pending : []).map(normalizePending).filter((p) => p.token && p.address && BigInt(p.amountRaw) > 0n),
    };
}

export const filterOrders = (orders, filter) => (!filter || filter === 'ALL' ? orders : orders.filter((o) => o.status === filter));

const addTo = (map, o, raw) => {
    const key = o.token ?? o.symbol;
    const cur = map.get(key) ?? { token: o.token, symbol: o.symbol, decimals: o.decimals, raw: 0n };
    cur.raw += BigInt(raw);
    map.set(key, cur);
};
const toList = (map) => [...map.values()].map((v) => ({ token: v.token, symbol: v.symbol, decimals: v.decimals, amountRaw: v.raw.toString() }));

/**
 * Tổng quan cho Merchant: đang ký quỹ (phần SAU PHÍ shop sẽ nhận nếu đơn giải ngân cho shop), đã nhận, và số đơn theo trạng thái.
 * Cộng theo từng loại token riêng (không trộn mUSD với ETH).
 */
export function summarizeOrders(orders) {
    const inEscrow = new Map();
    const received = new Map();
    const counts = Object.fromEntries(Object.keys(MERCHANT_STATUS).map((s) => [s, 0]));
    for (const o of orders) {
        if (o.status in counts) counts[o.status] += 1;
        if (IN_ESCROW_STATES.includes(o.status)) addTo(inEscrow, o, o.netRaw);
        else if (o.status === MERCHANT_STATUS.COMPLETED) addTo(received, o, o.netRaw);
    }
    return { inEscrow: toList(inEscrow), received: toList(received), counts };
}

/** Câu giải thích "chuyện gì sẽ xảy ra tiếp" cho từng trạng thái (mốc thời gian là giờ block, không phải giờ máy). */
export function statusNote(o, fmtTime = formatChainTime) {
    const net = formatAmount(o.netRaw, o.decimals, o.symbol);
    switch (o.status) {
        case MERCHANT_STATUS.LOCKED:
            return o.deliveryDeadline
                ? `Người mua đã ký quỹ. Nếu quá ${fmtTime(o.deliveryDeadline)} mà chưa giao hàng, người mua có quyền hủy đơn và nhận lại tiền.`
                : 'Người mua đã ký quỹ. Hãy giao hàng sớm để nhận tiền.';
        case MERCHANT_STATUS.DELIVERED:
            return o.releaseAt
                ? `Tiền (${net} sau phí) tự chuyển vào ví của bạn sau ${fmtTime(o.releaseAt)} nếu người mua không khiếu nại, hoặc ngay khi họ bấm "Đã nhận hàng".`
                : `Tiền (${net} sau phí) sẽ tự chuyển vào ví của bạn khi hết hạn kiểm tra.`;
        case MERCHANT_STATUS.DISPUTED:
            return o.forceResolveAt
                ? `Tiền đang bị đóng băng chờ phán quyết 2/3 chữ ký. Nếu quá ${fmtTime(o.forceResolveAt)} mà chưa xử xong, Trọng tài có thể xử đơn phương.`
                : 'Tiền đang bị đóng băng chờ phán quyết 2/3 chữ ký.';
        case MERCHANT_STATUS.COMPLETED:
            return `Bạn đã nhận ${net} (phí sàn ${formatAmount(o.feeRaw, o.decimals, o.symbol)}).`;
        case MERCHANT_STATUS.REFUNDED:
            return 'Tiền ký quỹ đã được hoàn lại cho người mua.';
        default:
            return null;
    }
}

/** Đơn tranh chấp thì Merchant vào /disputes/:code để xem đề xuất và ký (lối vào Merchant mà Tuần 6 còn thiếu). */
export const disputePath = (o) => (o.status === MERCHANT_STATUS.DISPUTED ? `/disputes/${encodeURIComponent(o.code)}` : null);
