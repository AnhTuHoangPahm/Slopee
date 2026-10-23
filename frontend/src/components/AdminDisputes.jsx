import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createDisputeProposalAPI, fetchAdminDisputesAPI, submitDisputeAPI } from '../api/disputes';
import { usePolling } from '../hooks/usePolling';
import { createServerClock } from '../lib/serverClock';
import { Web3ApiError, toUserMessage } from '../lib/errors';
import { formatVND, shortHash } from '../lib/format';
import { REASON_NOTE_MAX, PAYOUT_SIDES, STAGE, canPropose, canResubmit, canSubmit, disputeStage, notReadyMessage, safeEvidenceUrl,
    signatureRemaining, submitMessage, validateProposalForm } from '../lib/adminDisputes';
import { describeDuration, formatTokenAmount } from '../lib/web3Checkout';

const POLL_MS = 8000;
const TOKEN_DECIMALS = 6;
const dark = { card: '#262626', border: '#3a3a3a', muted: '#999', warn: '#f5c542' };
const btn = { padding: '8px 14px', borderRadius: 4, border: 'none', background: '#ee4d2d', color: '#fff', cursor: 'pointer', fontWeight: 700 };
const btnGhost = { ...btn, background: 'transparent', color: '#ddd', border: '1px solid #666' };
const STAGE_TEXT = {
    [STAGE.NO_PROPOSAL]: ['Chưa có đề xuất', '#999'],
    [STAGE.WAITING_SIGNATURE]: ['Chờ Buyer/Merchant ký', '#f5c542'],
    [STAGE.READY]: ['Đủ chữ ký, sẵn sàng thi hành', '#4caf50'],
    [STAGE.SUBMITTED]: ['Đã nộp, chờ hệ thống ghi nhận', '#4caf50'],
    [STAGE.EXPIRED]: ['Hết hạn chữ ký, cần đề xuất mới', '#ef5350'],
};
const PARTY_NAME = { ARBITRATOR: 'Trọng tài (sàn)', BUYER: 'Buyer', MERCHANT: 'Merchant' };

/** Hộp thoại xác nhận bằng React (không dùng window.confirm trong luồng Web3: Firefox có thể ngắt hộp thoại gốc). */
function Modal({ title, children, onCancel, confirmLabel, onConfirm, confirmDisabled, danger = true }) {
    const titleId = useId();
    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
            <div role="dialog" aria-modal="true" aria-labelledby={titleId} data-testid="admin-dialog"
                style={{ background: '#1e1e1e', color: '#e0e0e0', border: '1px solid #444', borderRadius: 8, padding: 20, width: 'min(520px, 92vw)' }}>
                <h3 id={titleId} style={{ marginTop: 0, color: '#fff' }}>{title}</h3>
                {children}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 16 }}>
                    <button type="button" style={btnGhost} onClick={onCancel}>Hủy</button>
                    <button type="button" data-testid="dialog-confirm" style={{ ...btn, background: danger ? '#ee4d2d' : '#388e3c' }}
                        onClick={onConfirm} disabled={confirmDisabled}>{confirmLabel}</button>
                </div>
            </div>
        </div>
    );
}

function ProposalDialog({ dispute, busy, onCancel, onSubmit }) {
    const [payoutSide, setPayoutSide] = useState('');
    const [reasonNote, setReasonNote] = useState('');
    const [touched, setTouched] = useState(false);
    const check = validateProposalForm({ payoutSide, reasonNote });
    const confirm = () => {
        setTouched(true);
        if (check.ok) onSubmit(check.value);
    };
    return (
        <Modal title="Tạo đề xuất phán quyết" onCancel={onCancel} onConfirm={confirm} confirmLabel={busy ? 'Đang tạo…' : 'Tạo đề xuất và ký'} confirmDisabled={busy}>
            <p style={{ color: dark.muted, fontSize: 13, marginTop: 0 }}>
                Đơn {String(dispute.order_id).slice(0, 8)} · {formatTokenAmount(dispute.amount_raw, TOKEN_DECIMALS, dispute.symbol)}
            </p>
            <div style={{ background: '#3b3212', border: `1px solid ${dark.warn}`, borderRadius: 4, padding: '8px 10px', fontSize: 13, marginBottom: 12 }}>
                Hệ thống sẽ ký phiếu Trọng tài ngay. Chỉ cần Buyer hoặc Merchant ký thêm, <strong>bất kỳ ai cũng có thể thi hành</strong> và
                không thể hoàn tác trên blockchain. Hãy xem kỹ bằng chứng trước khi chọn.
            </div>
            <fieldset style={{ border: 'none', padding: 0, margin: '0 0 12px' }}>
                <legend style={{ fontSize: 14, marginBottom: 6 }}>Phán quyết</legend>
                {Object.entries(PAYOUT_SIDES).map(([key, v]) => (
                    <label key={key} style={{ display: 'block', marginBottom: 6, cursor: 'pointer' }}>
                        <input type="radio" name="payout" value={key} checked={payoutSide === key} onChange={() => setPayoutSide(key)} />{' '}
                        <strong>{v.label}</strong> <span style={{ color: dark.muted, fontSize: 12 }}>{v.detail}</span>
                    </label>
                ))}
                {touched && check.errors.payoutSide && <div role="alert" style={{ color: '#ef5350', fontSize: 12 }}>{check.errors.payoutSide}</div>}
            </fieldset>
            <label style={{ display: 'block', fontSize: 14 }}>
                Ghi chú thẩm định (không bắt buộc)
                <textarea data-testid="proposal-note" value={reasonNote} onChange={(e) => setReasonNote(e.target.value)} rows={3} maxLength={REASON_NOTE_MAX + 200}
                    style={{ width: '100%', boxSizing: 'border-box', marginTop: 4, background: '#121212', color: '#eee', border: '1px solid #555', borderRadius: 4, padding: 8, fontFamily: 'inherit' }} />
            </label>
            {touched && check.errors.reasonNote && <div role="alert" style={{ color: '#ef5350', fontSize: 12 }}>{check.errors.reasonNote}</div>}
        </Modal>
    );
}

function SubmitDialog({ dispute, busy, onCancel, onConfirm }) {
    const res = dispute.resolution;
    const side = PAYOUT_SIDES[res.payout_side];
    return (
        <Modal title="Thi hành phán quyết lên blockchain" onCancel={onCancel} onConfirm={onConfirm} confirmLabel={busy ? 'Đang gửi…' : 'Thi hành'} confirmDisabled={busy}>
            <p style={{ marginTop: 0 }}>
                <strong>{side?.label ?? res.payout_side}</strong> · {formatTokenAmount(dispute.amount_raw, TOKEN_DECIMALS, dispute.symbol)}
            </p>
            <p style={{ color: dark.muted, fontSize: 13 }}>
                Hệ thống gửi giao dịch thay bạn (không cần ví, không mất phí). Giao dịch đã vào chuỗi thì <strong>không thể thu hồi</strong>.
            </p>
        </Modal>
    );
}

/** UC-06 phía Admin: các đơn đang tranh chấp, bằng chứng của Buyer, tạo đề xuất phán quyết và thi hành khi đủ chữ ký. */
export default function AdminDisputes() {
    const clockRef = useRef(null);
    if (clockRef.current === null) clockRef.current = createServerClock();
    // Đồng hồ được tính NGAY TRONG hàm poll, cùng nhịp với danh sách: không có lần render nào có dữ liệu mà chưa có đồng hồ (trước đây `clock` được đặt
    // trong một useEffect SAU render nên có một nhịp thiếu "mốc thoát hiểm"). Độ lệch chỉ tăng (lib/serverClock) nên mốc không giật lùi khi poll trễ.
    const { data, error, refresh } = usePolling(async () => {
        const res = await fetchAdminDisputesAPI();
        const receivedAtMs = Date.now();
        const offset = res.serverTime == null ? clockRef.current.offset : clockRef.current.observe(Number(res.serverTime), receivedAtMs);
        return { ...res, clock: offset == null ? null : { serverTime: receivedAtMs / 1000 + offset, receivedAtMs } };
    }, { intervalMs: POLL_MS });
    const clock = data?.clock ?? null;                         // { serverTime, receivedAtMs } của lần poll gần nhất (đã làm mượt)
    const [dialog, setDialog] = useState(null);               // { kind: 'propose' | 'submit', code }
    const [busy, setBusy] = useState(false);
    const [notice, setNotice] = useState({});                 // { [code]: { kind: 'ok'|'error', text } }
    const [, tick] = useState(0);
    const inFlight = useRef(false);                           // cờ đồng bộ chống bấm đúp

    useEffect(() => {                                         // làm tươi đếm ngược mỗi 30 giây (hiển thị theo phút/giờ nên không cần dày hơn)
        const id = setInterval(() => tick((n) => n + 1), 30000);
        return () => clearInterval(id);
    }, []);

    const disputes = data?.disputes ?? null;
    const current = dialog ? disputes?.find((d) => d.order_id === dialog.code) : null;
    const say = useCallback((code, kind, text) => setNotice((n) => ({ ...n, [code]: { kind, text } })), []);

    const run = useCallback(async (code, action, onOk) => {
        if (inFlight.current) return;
        inFlight.current = true;
        setBusy(true);
        try {
            say(code, 'info', '');
            const res = await action();
            say(code, 'ok', onOk(res));
            setDialog(null);
        } catch (e) {
            say(code, 'error', e instanceof Web3ApiError && e.code === 'DISPUTE_NOT_READY' ? notReadyMessage(e) : toUserMessage(e));
            setDialog(null);
        } finally {
            inFlight.current = false;
            setBusy(false);
            refresh();
        }
    }, [refresh, say]);

    const propose = (code, value) => run(code, () => createDisputeProposalAPI(code, value), () => 'Đã tạo đề xuất và ký phiếu Trọng tài. Chờ Buyer hoặc Merchant ký.');
    const submit = (code) => run(code, () => submitDisputeAPI(code), submitMessage);

    return (
        <div className="admin-table-container" style={{ marginBottom: 30 }} data-testid="admin-disputes">
            <h2>Tranh chấp đang mở {disputes ? `(${disputes.length})` : ''}</h2>
            {error && <p role="alert" style={{ color: '#ef5350' }}>{toUserMessage(error)} (đang tự thử lại)</p>}
            {disputes === null && !error && <p role="status" style={{ color: dark.muted }}>Đang tải…</p>}
            {disputes && disputes.length === 0 && <p data-testid="disputes-empty" style={{ color: dark.muted }}>Không có đơn nào đang tranh chấp.</p>}

            {disputes && disputes.map((d) => {
                const stage = disputeStage(d, clock);
                const res = d.resolution;
                const [stageLabel, stageColor] = STAGE_TEXT[stage];
                const evidence = safeEvidenceUrl(d.note?.evidence_url);
                const remaining = signatureRemaining(d, clock);
                const forceIn = clock ? d.force_resolve_at - (clock.serverTime + Math.floor((Date.now() - clock.receivedAtMs) / 1000)) : null;
                const n = notice[d.order_id];
                return (
                    <section key={d.order_id} aria-label={`Tranh chấp ${d.order_id}`} data-testid={`dispute-${d.order_id}`}
                        style={{ background: dark.card, border: `1px solid ${dark.border}`, borderRadius: 6, padding: 14, marginBottom: 12 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                            <strong title={d.order_id}>Đơn {String(d.order_id).slice(0, 8)} · {d.shop_name ?? 'Shop'}</strong>
                            <span data-testid={`stage-${d.order_id}`} style={{ color: stageColor, fontWeight: 700 }}>{stageLabel}</span>
                        </div>
                        <div style={{ fontSize: 13, color: '#bbb', marginTop: 6 }}>
                            <div>Người mua: {d.buyer_name ?? '—'} · Giá trị: {formatTokenAmount(d.amount_raw, TOKEN_DECIMALS, d.symbol)} ({formatVND(d.price_vnd)})</div>
                            {forceIn !== null && (
                                <div>
                                    {forceIn > 0
                                        ? `Trọng tài có quyền xử đơn phương sau ${describeDuration(forceIn)} (thoát hiểm timeout).`
                                        : 'Đã quá thời hạn tranh chấp: Trọng tài có quyền xử đơn phương (UC-07).'}
                                </div>
                            )}
                        </div>

                        <div style={{ marginTop: 10, fontSize: 14 }}>
                            <div style={{ color: dark.muted, fontSize: 12 }}>LÝ DO CỦA BUYER</div>
                            {d.note
                                ? (<>
                                    <p data-testid={`note-${d.order_id}`} style={{ margin: '4px 0', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{d.note.reason}</p>
                                    {evidence
                                        ? <a href={evidence} target="_blank" rel="noopener noreferrer nofollow" style={{ color: '#64b5f6' }}>Xem bằng chứng</a>
                                        : d.note.evidence_url && <span style={{ color: dark.muted }}>Đường dẫn bằng chứng không hợp lệ, đã ẩn.</span>}
                                </>)
                                : <p style={{ margin: '4px 0', color: dark.muted }}>Buyer chưa gửi lý do hoặc bằng chứng.</p>}
                        </div>

                        {res && (
                            <div style={{ marginTop: 10, fontSize: 14 }} data-testid={`resolution-${d.order_id}`}>
                                <div style={{ color: dark.muted, fontSize: 12 }}>ĐỀ XUẤT PHÁN QUYẾT</div>
                                <div><strong>{PAYOUT_SIDES[res.payout_side]?.label ?? res.payout_side}</strong></div>
                                <div style={{ color: '#bbb' }}>
                                    Đã ký: {res.signed_by.length ? res.signed_by.map((p) => PARTY_NAME[p] ?? p).join(', ') : 'chưa ai'}
                                    {(stage === STAGE.WAITING_SIGNATURE || stage === STAGE.READY) && remaining !== null && remaining > 0 && ` · còn ${describeDuration(remaining)} để ký`}
                                </div>
                                {res.reason_note && <div style={{ color: dark.muted, fontSize: 12, overflowWrap: 'anywhere' }}>Ghi chú: {res.reason_note}</div>}
                                {res.submitted_tx_hash && <div style={{ color: dark.muted, fontSize: 12 }}>Giao dịch: {shortHash(res.submitted_tx_hash)}</div>}
                            </div>
                        )}

                        {n?.text && <p role={n.kind === 'error' ? 'alert' : 'status'} data-testid={`notice-${d.order_id}`}
                            style={{ color: n.kind === 'error' ? '#ef5350' : '#81c784' }}>{n.text}</p>}

                        <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                            {canPropose(stage) && (
                                <button type="button" style={btn} onClick={() => setDialog({ kind: 'propose', code: d.order_id })}>
                                    {stage === STAGE.EXPIRED ? 'Tạo đề xuất mới' : 'Tạo đề xuất phán quyết'}
                                </button>
                            )}
                            {canSubmit(stage) && (
                                <button type="button" style={{ ...btn, background: '#388e3c' }} onClick={() => setDialog({ kind: 'submit', code: d.order_id })}>Thi hành phán quyết</button>
                            )}
                            {canResubmit(stage) && (
                                <button type="button" style={btnGhost} onClick={() => setDialog({ kind: 'submit', code: d.order_id })}>Nộp lại</button>
                            )}
                        </div>
                    </section>
                );
            })}

            {dialog?.kind === 'propose' && current && (
                <ProposalDialog dispute={current} busy={busy} onCancel={() => !busy && setDialog(null)} onSubmit={(v) => propose(current.order_id, v)} />
            )}
            {dialog?.kind === 'submit' && current?.resolution && (
                <SubmitDialog dispute={current} busy={busy} onCancel={() => !busy && setDialog(null)} onConfirm={() => submit(current.order_id)} />
            )}
        </div>
    );
}
