import { STEP } from '../lib/depositFlow';
import { shortHash } from '../lib/format';

const ORDER = [STEP.CHECKING, STEP.APPROVING, STEP.DEPOSITING, STEP.WAITING_INDEXER, STEP.LOCKED];

/**
 * Thanh tiến trình nạp tiền (SDD 9.8 `TxStepper`): kiểm tra -> approve -> nạp gom -> chờ xác nhận.
 * Chỉ hiển thị; mọi quyết định nằm ở depositReducer. `slow`: chờ Indexer quá 30 giây thì nhắc mã giao dịch.
 */
export default function TxStepper({ state, slow = false }) {
    const { step, approveSkipped, approved, approveTx, depositTx, failedStep } = state;
    const at = ORDER.indexOf(step);
    // Bước đã thất bại: theo bước đang chạy lúc lỗi; lỗi ở CHECKING sau khi approve xong (hết hạn giữa chừng) tính là trước bước nạp
    const failedAt = step !== STEP.FAILED ? -1 : failedStep === STEP.APPROVING ? 1 : failedStep === STEP.DEPOSITING ? 2 : (approved ? 2 : 0);
    const items = [
        { key: 'check', label: 'Kiểm tra báo giá và số dư', idx: 0 },
        { key: 'approve', label: approveSkipped ? 'Cho phép hợp đồng dùng mUSD (đã đủ hạn mức, bỏ qua)' : 'Bước 1/2 — Cho phép hợp đồng dùng mUSD (approve)', idx: 1 },
        { key: 'deposit', label: 'Bước 2/2 — Ký quỹ cho tất cả shop trong một giao dịch', idx: 2 },
        { key: 'wait', label: 'Chờ hệ thống xác nhận khóa tiền', idx: 3 },
    ];
    const mark = (i) => {
        if (step === STEP.LOCKED) return '✅';
        if (step === STEP.FAILED) return i < failedAt ? '✅' : i === failedAt ? '❌' : '○';
        if (i === 1 && approveSkipped && at > 0) return '✅';
        // CHECKING xuất hiện lại sau approve: bước approve đã xong
        if (step === STEP.CHECKING && approved && i <= 1) return '✅';
        if (i < at) return '✅';
        return i === at ? '⏳' : '○';
    };
    return (
        <ol data-testid="tx-stepper" aria-label="Tiến trình ký quỹ" style={{ listStyle: 'none', padding: 0, margin: '12px 0' }}>
            {items.map((it) => (
                <li key={it.key} data-testid={`tx-step-${it.key}`} data-mark={mark(it.idx)} style={{ padding: '4px 0', color: mark(it.idx) === '○' ? '#999' : '#222' }}>
                    <span aria-hidden="true">{mark(it.idx)}</span> {it.label}
                    {it.key === 'approve' && approveTx && <small style={{ color: '#888' }}> · tx {shortHash(approveTx)}</small>}
                    {it.key === 'deposit' && depositTx && <small style={{ color: '#888' }}> · tx {shortHash(depositTx)}</small>}
                </li>
            ))}
            {slow && step === STEP.WAITING_INDEXER && (
                <li data-testid="indexer-slow" role="status" style={{ color: '#b26a00', paddingTop: 6 }}>
                    Chờ hơi lâu hơn dự kiến. Giao dịch đã gửi lên chuỗi (mã {shortHash(depositTx)}); nếu vẫn chưa xong, hãy nhờ quản trị viên kiểm tra tiến trình Indexer.
                </li>
            )}
        </ol>
    );
}
