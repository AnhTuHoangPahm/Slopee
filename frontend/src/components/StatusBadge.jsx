import { STATUS_COLOR, statusLabel } from '../lib/orderStatus';

/** Huy hiệu trạng thái đơn Web3 (SDD 9.1). DISPUTED màu vàng để khác trạng thái thường (SRS 5.1). */
export default function StatusBadge({ status }) {
    const color = STATUS_COLOR[status] ?? '#888';
    const disputed = status === 'DISPUTED';
    return (
        <span
            data-testid="status-badge"
            data-status={status}
            style={{
                display: 'inline-block', padding: '3px 10px', borderRadius: '12px', fontSize: '13px', fontWeight: 'bold',
                color: disputed ? '#5c4400' : color, background: disputed ? '#fff3cd' : `${color}18`, border: `1px solid ${color}`,
            }}
        >
            {statusLabel(status)}
        </span>
    );
}
