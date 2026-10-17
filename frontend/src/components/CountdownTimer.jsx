import { formatInspectionCountdown } from '../lib/orderTimer';

const WARN_UNDER_SECONDS = 3600; // còn dưới 1 giờ: đổi màu cảnh báo

/**
 * Đồng hồ đếm ngược thời hạn kiểm tra hàng của MỘT đơn (SDD 9.4, F-06). Thuần hiển thị: số giây còn lại do cha tính
 * theo giờ máy chủ (useOrderStatus). `remaining` null = chưa có đồng hồ máy chủ, không đoán theo giờ máy người dùng.
 * Không đặt aria-live để trình đọc màn hình không đọc lại mỗi giây.
 */
export default function CountdownTimer({ remaining }) {
    if (remaining === null || remaining === undefined) {
        return <span data-testid="countdown" data-state="syncing" style={{ color: '#888' }}>Đang đồng bộ giờ với máy chủ…</span>;
    }
    if (remaining <= 0) {
        return <span data-testid="countdown" data-state="over" style={{ color: '#d32f2f', fontWeight: 'bold' }}>Đã hết hạn kiểm tra</span>;
    }
    const warn = remaining < WARN_UNDER_SECONDS;
    return (
        <span data-testid="countdown" data-state={warn ? 'warning' : 'running'} role="timer">
            Còn <strong style={{ color: warn ? '#e65100' : '#26aa99', fontVariantNumeric: 'tabular-nums' }}>{formatInspectionCountdown(remaining)}</strong> để kiểm tra hàng
        </span>
    );
}
