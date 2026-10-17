import { useId, useState } from 'react';
import { DISPUTE_REASON_MAX, EVIDENCE_URL_MAX, validateDisputeForm } from '../lib/orderActions';

/**
 * Hộp thoại khiếu nại (UC-05): lý do + đường dẫn bằng chứng (tùy chọn). Chỉ thu thập và kiểm tra dữ liệu; cha gửi giao dịch ví.
 * Tiền bị đóng băng ngay khi khiếu nại lên chuỗi nên có cảnh báo rõ trước khi gửi.
 */
export default function DisputeDialog({ onSubmit, onCancel }) {
    const [reason, setReason] = useState('');
    const [evidenceUrl, setEvidenceUrl] = useState('');
    const [touched, setTouched] = useState(false);
    const titleId = useId();
    const check = validateDisputeForm({ reason, evidenceUrl });

    const submit = (e) => {
        e.preventDefault();
        setTouched(true);
        if (check.ok) onSubmit(check.value);
    };
    const field = { width: '100%', boxSizing: 'border-box', padding: '8px', border: '1px solid #ccc', borderRadius: '3px', fontFamily: 'inherit' };
    const errStyle = { color: '#d32f2f', fontSize: '12px', marginTop: '3px' };

    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
            <form noValidate role="dialog" aria-modal="true" aria-labelledby={titleId} onSubmit={submit} data-testid="dispute-dialog"
                style={{ background: '#fff', borderRadius: '6px', padding: '20px', width: 'min(480px, 92vw)', boxShadow: '0 4px 24px rgba(0,0,0,0.25)' }}>
                <h3 id={titleId} style={{ marginTop: 0 }}>Yêu cầu trả hàng / Khiếu nại</h3>
                <div style={{ background: '#fff3cd', border: '1px solid #e0c36a', borderRadius: '4px', padding: '8px 10px', fontSize: '13px', marginBottom: '12px' }}>
                    Khi gửi khiếu nại, tiền ký quỹ của đơn này bị đóng băng cho tới khi có phán quyết. Bạn chỉ khiếu nại được trong thời hạn kiểm tra hàng.
                </div>
                <label style={{ display: 'block', marginBottom: '12px', fontSize: '14px' }}>
                    Lý do khiếu nại
                    <textarea data-testid="dispute-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={4} maxLength={DISPUTE_REASON_MAX + 200}
                        aria-invalid={touched && Boolean(check.errors.reason)} style={{ ...field, marginTop: '4px', resize: 'vertical' }} />
                    {touched && check.errors.reason && <div role="alert" style={errStyle}>{check.errors.reason}</div>}
                </label>
                <label style={{ display: 'block', marginBottom: '16px', fontSize: '14px' }}>
                    Đường dẫn bằng chứng (ảnh/video, không bắt buộc)
                    <input data-testid="dispute-evidence" type="url" inputMode="url" value={evidenceUrl} onChange={(e) => setEvidenceUrl(e.target.value)} maxLength={EVIDENCE_URL_MAX + 100}
                        placeholder="https://" aria-invalid={touched && Boolean(check.errors.evidenceUrl)} style={{ ...field, marginTop: '4px' }} />
                    {touched && check.errors.evidenceUrl && <div role="alert" style={errStyle}>{check.errors.evidenceUrl}</div>}
                </label>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                    <button type="button" onClick={onCancel} style={{ background: '#fff', border: '1px solid #bbb', padding: '8px 14px', borderRadius: '3px', cursor: 'pointer' }}>Đóng</button>
                    <button type="submit" data-testid="dispute-submit" style={{ background: '#d32f2f', color: '#fff', border: 'none', padding: '8px 14px', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold' }}>Gửi khiếu nại</button>
                </div>
            </form>
        </div>
    );
}
