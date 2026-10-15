// Hàm thuần cho màn hình thanh toán Web3 (SDD 9.3, 9.7). KHÔNG dùng số thực cho tiền token: amount_raw là chuỗi số nguyên.
const GROUP_VN = new Intl.NumberFormat('vi-VN');

export const QUOTE_MIN_REMAINING = 60; // giây: còn dưới mức này thì coi là sắp hết hạn, yêu cầu báo giá mới (SDD 9.3 CHECK_QUOTE)

/** "15960000", 6, "mUSD" -> "15,96 mUSD". Chính xác tuyệt đối nhờ BigInt; bỏ số 0 thừa nhưng giữ tối thiểu 2 chữ số lẻ. */
export function formatTokenAmount(amountRaw, decimals = 6, symbol = 'mUSD') {
    let raw;
    try {
        raw = BigInt(amountRaw);
    } catch {
        return '—';
    }
    const negative = raw < 0n;
    if (negative) raw = -raw;
    const base = 10n ** BigInt(decimals);
    const whole = raw / base;
    let frac = (raw % base).toString().padStart(decimals, '0').replace(/0+$/, '');
    if (frac.length < Math.min(2, decimals)) frac = frac.padEnd(Math.min(2, decimals), '0');
    const text = `${negative ? '-' : ''}${GROUP_VN.format(whole)}${frac ? `,${frac}` : ''}`;
    return symbol ? `${text} ${symbol}` : text;
}

/** Tổng hai số tiền dạng chuỗi (BigInt). */
export const sumRaw = (values) => values.reduce((acc, v) => acc + BigInt(v), 0n).toString();

/**
 * Số giây còn lại tới hạn báo giá, tính theo ĐỒNG HỒ MÁY CHỦ để không lệch khi đồng hồ máy người dùng sai:
 * offset = server_time - thời điểm client nhận phản hồi; còn lại = deadline - (now_client + offset).
 */
export function secondsRemaining({ deadline, serverTime, receivedAtMs, nowMs = Date.now() }) {
    const offset = Number(serverTime) - receivedAtMs / 1000;
    return Math.floor(Number(deadline) - (nowMs / 1000 + offset));
}

/** 'ok' | 'expiring' (< 60 giây) | 'expired'. */
export function quoteStatus(remaining) {
    if (remaining <= 0) return 'expired';
    if (remaining < QUOTE_MIN_REMAINING) return 'expiring';
    return 'ok';
}

export function formatCountdown(remaining) {
    const s = Math.max(0, Math.floor(remaining));
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

/** 259200 -> "3 ngày", 7200 -> "2 giờ", 5400 -> "1 giờ 30 phút". */
export function describeDuration(seconds) {
    const s = Number(seconds);
    if (!Number.isFinite(s) || s <= 0) return '—';
    const days = Math.floor(s / 86400);
    const hours = Math.floor((s % 86400) / 3600);
    const minutes = Math.floor((s % 3600) / 60);
    if (days && !hours) return `${days} ngày`;
    if (days) return `${days} ngày ${hours} giờ`;
    if (hours && !minutes) return `${hours} giờ`;
    if (hours) return `${hours} giờ ${minutes} phút`;
    return `${minutes} phút`;
}

/** Phí sàn: 300 -> "3%", 250 -> "2,5%". */
export const formatFeeBps = (bps) => `${GROUP_VN.format(Number(bps) / 100)}%`;
