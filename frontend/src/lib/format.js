// Định dạng dùng chung (SDD 9.1). `formatVND` là NƠI DUY NHẤT định dạng tiền (P0-07): không dùng $ hay toFixed(2).
const vndFormatter = new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'VND',
    maximumFractionDigits: 0,
});

export const formatVND = (value) => {
    const n = Number(value);
    return vndFormatter.format(Number.isFinite(n) ? Math.round(n) : 0);
};

/** Rút gọn địa chỉ ví để hiển thị: 0x9965…A4dc. Giữ nguyên nếu không đúng định dạng địa chỉ. */
export const shortAddress = (address) =>
    typeof address === 'string' && /^0x[0-9a-fA-F]{40}$/.test(address)
        ? `${address.slice(0, 6)}…${address.slice(-4)}`
        : (address ?? '');
