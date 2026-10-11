// P0-07: định dạng tiền VND dùng chung toàn app. Không dùng ký hiệu $ hay toFixed(2).
const vndFormatter = new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'VND',
    maximumFractionDigits: 0,
});

export const formatVND = (value) => {
    const n = Number(value);
    return vndFormatter.format(Number.isFinite(n) ? Math.round(n) : 0);
};
