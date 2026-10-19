import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { submitDisputeAPI } from '../api/disputes';
import Navbar from '../components/Navbar';
import StatusBadge from '../components/StatusBadge';
import { useDispute } from '../hooks/useDispute';
import { useSignDispute } from '../hooks/useSignDispute';
import { useWallet } from '../hooks/useWallet';
import {
    PARTY, PROBLEM_TEXT, SIGN_WARNING_TEXT, describeOutcome, disputePhase, expectedWallet, hasSigned, outcomeOf, OUTCOME, proposalProblems, signGate,
} from '../lib/disputeSign';
import { SIGN_STEP } from '../lib/disputeFlow';
import { toUserMessage } from '../lib/errors';
import { shortAddress, shortHash } from '../lib/format';
import { isHttpUrl } from '../lib/orderActions';
import { formatInspectionCountdown } from '../lib/orderTimer';
import { formatTokenAmount } from '../lib/web3Checkout';

const card = { background: '#fff', padding: '18px 20px', borderRadius: '4px', marginBottom: '16px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' };
const btn = { padding: '10px 18px', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold', border: 'none', fontSize: '15px' };
const disabledStyle = { opacity: 0.5, cursor: 'not-allowed' };
const PARTY_LABEL = { ARBITRATOR: 'Sàn (Trọng tài)', BUYER: 'Buyer', MERCHANT: 'Merchant' };
const fmtTime = (sec) => new Date(Number(sec) * 1000).toLocaleString('vi-VN');

function Evidence({ url }) {
    if (!url) return <span style={{ color: '#888' }}>Không có.</span>;
    // Đường dẫn do Buyer nhập: chỉ mở khi là http(s) (chặn javascript:, data:...), và không để trang kia truy cập cửa sổ này
    if (!isHttpUrl(url)) return <span style={{ color: '#b8860b' }}>Đường dẫn không an toàn nên không được mở: <code>{url}</code></span>;
    return <a href={url} target="_blank" rel="noopener noreferrer nofollow" style={{ wordBreak: 'break-all' }}>{url}</a>;
}

function Signatures({ view }) {
    const rows = [PARTY.ARBITRATOR, PARTY.BUYER, PARTY.MERCHANT];
    return (
        <ul data-testid="signatures" style={{ listStyle: 'none', padding: 0, margin: '8px 0 0' }}>
            {rows.map((p) => {
                const signed = hasSigned(view, p);
                return (
                    <li key={p} data-party={p} data-signed={signed} style={{ padding: '4px 0', color: signed ? '#2e7d32' : '#888' }}>
                        {signed ? '✔' : '○'} {PARTY_LABEL[p]}{p === view.your_party ? ' (bạn)' : ''}: {signed ? 'đã ký' : 'chưa ký'}
                    </li>
                );
            })}
        </ul>
    );
}

/**
 * Màn hình ký phán quyết của Buyer/Merchant (UC-06, SDD 9.7). Mọi tiền bạc quyết ở hợp đồng; trang này chỉ cho ký một đề xuất ĐÃ ĐƯỢC KIỂM
 * khớp những gì hợp đồng chấp nhận, kèm cảnh báo bắt buộc (R-06) ngay trước nút ký.
 * `fetchDispute`, `send`, `submit` chỉ để test thay thế; `pollMs` rút ngắn chu kỳ poll khi test.
 */
export default function Dispute({ hideNavbar = false, fetchDispute, send, submit = submitDisputeAPI, pollMs }) {
    const { code } = useParams();
    const w = useWallet();
    const dispute = useDispute(code, { fetchDispute, ...(pollMs ? { fastMs: pollMs, slowMs: pollMs } : {}) });
    const { data: view, error, loaded, nowSec, deadlineRemaining, refresh } = dispute;
    const { state: signState, sign, resend, reset, busy } = useSignDispute({ send, onSent: refresh });
    const [ack, setAck] = useState(false);
    const [exec, setExec] = useState({ status: 'idle', message: null });

    const phase = disputePhase(view, nowSec);
    const gate = view ? signGate(view, { isConnected: w.isConnected, isCorrectChain: w.isCorrectChain, account: w.account }) : 'NOT_A_PARTY';
    const decimals = view?.decimals ?? 6;
    const symbol = view?.symbol ?? 'mUSD';

    const onExecute = async () => {
        setExec({ status: 'sending', message: null });
        try {
            await submit(code);
            setExec({ status: 'sent', message: null });
            refresh();
        } catch (e) {
            setExec({ status: 'failed', message: toUserMessage(e) });
        }
    };

    const body = () => {
        if (!loaded) {
            if (error) return <div style={card} role="alert">{toUserMessage(error)}</div>;
            return <div style={card}>Đang tải đề xuất phán quyết…</div>;
        }
        const outcome = view.resolution ? describeOutcome(view) : null;
        const problems = view.resolution ? proposalProblems(view, nowSec) : [];
        const canAct = view.your_party === PARTY.BUYER || view.your_party === PARTY.MERCHANT;
        // Kết quả cuối: ưu tiên trạng thái đơn do Indexer ghi; chỉ khi chưa có thì suy từ địa chỉ nhận của đề xuất
        const refunded = view.order_status === 'REFUNDED' ? true : view.order_status === 'COMPLETED' ? false
            : outcomeOf({ payoutTo: view.resolution?.payout_to, buyerWallet: view.buyer_wallet, merchantWallet: view.merchant_wallet }) === OUTCOME.REFUND_BUYER;

        return (
            <>
                <section style={card} data-testid="complaint">
                    <h3 style={{ marginTop: 0 }}>Khiếu nại của Buyer</h3>
                    {view.note ? (
                        <>
                            <p style={{ whiteSpace: 'pre-wrap', margin: '6px 0' }} data-testid="complaint-reason">{view.note.reason}</p>
                            <div>Bằng chứng: <Evidence url={view.note.evidence_url} /></div>
                        </>
                    ) : <p style={{ color: '#888' }}>Buyer chưa gửi lý do khiếu nại.</p>}
                    <div style={{ marginTop: '8px', color: '#666', fontSize: '13px' }}>
                        Số tiền ký quỹ: <strong>{formatTokenAmount(view.amount_raw, decimals, symbol)}</strong> · Buyer {shortAddress(view.buyer_wallet)} · Merchant {shortAddress(view.merchant_wallet)}
                    </div>
                </section>

                {phase === 'NOT_DISPUTED' && <div style={card} data-testid="phase-not-disputed">Đơn này không có khiếu nại đang xử lý.</div>}
                {phase === 'AWAITING_PROPOSAL' && <div style={card} data-testid="phase-awaiting">Quản trị viên đang thẩm định bằng chứng. Khi có đề xuất phán quyết, bạn sẽ thấy ngay tại đây.</div>}

                {view.resolution && phase !== 'EXECUTED' && (
                    <section style={card} data-testid="proposal">
                        <h3 style={{ marginTop: 0 }}>Đề xuất phán quyết</h3>
                        <div data-testid="outcome" data-outcome={outcome.outcome} style={{ fontSize: '18px', fontWeight: 'bold', color: outcome.outcome === OUTCOME.UNKNOWN ? '#d32f2f' : '#ee4d2d' }}>{outcome.headline}</div>
                        {outcome.transfer && <div style={{ marginTop: '6px' }}>Số tiền chuyển đi: <strong data-testid="outcome-amount">{outcome.transfer}</strong></div>}
                        <div style={{ color: '#666' }}>{outcome.note}</div>
                        <div style={{ marginTop: '6px' }}>Địa chỉ nhận: <code data-testid="outcome-recipient" title={outcome.recipient}>{outcome.recipient}</code></div>
                        {view.resolution.reason_note && <div style={{ marginTop: '6px', color: '#555' }}>Ghi chú thẩm định: {view.resolution.reason_note}</div>}
                        <div style={{ marginTop: '6px' }} data-testid="deadline">
                            {phase === 'EXPIRED' || (deadlineRemaining !== null && deadlineRemaining <= 0)
                                ? <span style={{ color: '#d32f2f' }}>Đề xuất đã hết hạn ký.</span>
                                : deadlineRemaining === null ? <span style={{ color: '#888' }}>Đang đồng bộ giờ với máy chủ…</span>
                                    : <>Hạn ký còn <strong>{formatInspectionCountdown(deadlineRemaining)}</strong> (đến {fmtTime(view.resolution.deadline)})</>}
                        </div>
                        <div style={{ marginTop: '8px', fontWeight: 'bold' }}>Chữ ký</div>
                        <Signatures view={view} />
                    </section>
                )}

                {phase === 'BLOCKED' && (
                    <div style={{ ...card, border: '1px solid #d32f2f' }} role="alert" data-testid="phase-blocked">
                        <strong>Không thể ký đề xuất này.</strong>
                        <ul>{problems.map((p) => <li key={p}>{PROBLEM_TEXT[p] ?? p}</li>)}</ul>
                        Hãy liên hệ quản trị viên.
                    </div>
                )}

                {phase === 'CAN_SIGN' && canAct && (
                    <section style={card} data-testid="sign-section">
                        <div role="note" data-testid="sign-warning" style={{ background: '#fff3cd', border: '1px solid #e0c36a', color: '#5c4400', borderRadius: '4px', padding: '10px 12px', marginBottom: '12px' }}>
                            ⚠ {SIGN_WARNING_TEXT}
                        </div>
                        <label style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', marginBottom: '12px', fontSize: '14px' }}>
                            <input type="checkbox" data-testid="ack" checked={ack} onChange={(e) => setAck(e.target.checked)} disabled={busy} />
                            <span>
                                Tôi đã đọc lưu ý trên và đồng ý: <strong>{outcome.headline}</strong>{outcome.transfer ? `, chuyển ${outcome.transfer}` : ''} đến {shortAddress(outcome.recipient)}.
                            </span>
                        </label>
                        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
                            <button type="button" data-testid="sign-btn" disabled={gate !== 'OK' || !ack || busy} onClick={() => sign(view)}
                                style={{ ...btn, background: '#ee4d2d', color: '#fff', ...(gate !== 'OK' || !ack || busy ? disabledStyle : null) }}>
                                Ký xác nhận (không tốn gas)
                            </button>
                            {gate === 'NOT_CONNECTED' && <button type="button" data-testid="gate-connect" onClick={w.connect} style={{ ...btn, background: '#fff', border: '1px solid #ee4d2d', color: '#ee4d2d' }}>Kết nối MetaMask</button>}
                            {gate === 'WRONG_CHAIN' && <button type="button" data-testid="gate-switch" onClick={w.switchToDeployedChain} style={{ ...btn, background: '#fff', border: '1px solid #ee4d2d', color: '#ee4d2d' }}>Chuyển sang mạng Anvil</button>}
                        </div>
                        {gate === 'WRONG_ACCOUNT' && (
                            <p data-testid="gate-wrong-account" role="alert" style={{ color: '#b8860b' }}>
                                Ví đang chọn không phải ví đã liên kết của bạn ({shortAddress(expectedWallet(view))}). Hãy chọn đúng ví trong MetaMask.
                            </p>
                        )}
                        {signState.step !== SIGN_STEP.IDLE && (
                            <div data-testid="sign-progress" data-step={signState.step} role="status" style={{ marginTop: '10px', padding: '8px 10px', background: '#f7f7f7', borderRadius: '4px' }}>
                                {signState.step === SIGN_STEP.SIGNING && <span>Hãy xác nhận chữ ký trong MetaMask (không tốn gas)…</span>}
                                {signState.step === SIGN_STEP.SENDING && <span>Đang gửi chữ ký lên sàn…</span>}
                                {signState.step === SIGN_STEP.DONE && <span style={{ color: '#2e7d32' }}>Sàn đã nhận chữ ký của bạn.</span>}
                                {signState.step === SIGN_STEP.FAILED && (
                                    <span style={{ color: signState.error?.userRejected ? '#666' : '#d32f2f' }}>
                                        {signState.error?.message}{' '}
                                        {signState.error?.retryable && signState.signature
                                            ? <button type="button" data-testid="resend" onClick={() => resend(view)} style={{ ...btn, padding: '2px 10px', fontSize: '13px', background: '#fff', border: '1px solid #bbb' }}>Gửi lại chữ ký</button>
                                            : <button type="button" data-testid="sign-reset" onClick={reset} style={{ ...btn, padding: '2px 10px', fontSize: '13px', background: '#fff', border: '1px solid #bbb' }}>Đóng</button>}
                                    </span>
                                )}
                            </div>
                        )}
                    </section>
                )}

                {phase === 'READY' && (
                    <section style={card} data-testid="phase-ready">
                        <strong>Đã đủ chữ ký để thi hành.</strong>
                        <p style={{ margin: '6px 0' }}>Bất kỳ ai cũng có thể nộp chữ ký lên blockchain. Bạn có thể nhờ sàn nộp giúp (không tốn gas).</p>
                        {canAct && (
                            <button type="button" data-testid="execute-btn" disabled={exec.status === 'sending' || exec.status === 'sent' || (deadlineRemaining !== null && deadlineRemaining <= 0)} onClick={onExecute}
                                style={{ ...btn, background: '#2e7d32', color: '#fff', ...(exec.status !== 'idle' && exec.status !== 'failed' ? disabledStyle : null) }}>
                                {exec.status === 'sending' ? 'Đang gửi…' : 'Thi hành ngay'}
                            </button>
                        )}
                        {exec.status === 'failed' && <p role="alert" style={{ color: '#d32f2f' }}>{exec.message}</p>}
                    </section>
                )}

                {phase === 'SUBMITTED' && (
                    <section style={card} data-testid="phase-submitted" role="status">
                        Giao dịch thi hành đã được gửi{view.resolution.submitted_tx_hash ? ` (${shortHash(view.resolution.submitted_tx_hash)})` : ''}. Đang chờ hệ thống xác nhận…
                    </section>
                )}

                {phase === 'EXPIRED' && (
                    <section style={{ ...card, border: '1px solid #e0c36a' }} data-testid="phase-expired">
                        <strong>Đề xuất đã hết hạn.</strong> Quản trị viên có thể tạo đề xuất mới; trang này sẽ tự cập nhật.
                        <div style={{ color: '#666', marginTop: '6px' }}>
                            Nếu bế tắc kéo dài đến {fmtTime(Number(view.disputed_at) + Number(view.dispute_timeout))}, Trọng tài được xử đơn phương theo quy định.
                        </div>
                    </section>
                )}

                {phase === 'CANCELLED' && <section style={card} data-testid="phase-cancelled">Đề xuất này đã bị hủy. Hãy chờ quản trị viên tạo đề xuất mới.</section>}

                {phase === 'EXECUTED' && (
                    <section style={{ ...card, border: '1px solid #a5d6a7', background: '#f1f8e9' }} data-testid="phase-executed" role="status">
                        <strong style={{ fontSize: '18px' }}>
                            {refunded ? 'Đã hoàn tiền cho Buyer.' : 'Đã giải ngân cho Merchant.'}
                        </strong>
                        <div style={{ color: '#555', marginTop: '6px' }}>Tranh chấp đã được giải quyết trên blockchain.</div>
                    </section>
                )}
            </>
        );
    };

    return (
        <div style={{ width: '100%', fontFamily: 'Inter, sans-serif' }}>
            {!hideNavbar && <Navbar />}
            <div style={{ padding: '20px', maxWidth: '760px', margin: '0 auto' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                    <h2 style={{ color: '#ee4d2d', margin: '0 0 12px' }}>Phán quyết tranh chấp</h2>
                    {view && <StatusBadge status={view.order_status} />}
                </div>
                <div style={{ color: '#888', fontSize: '13px', marginBottom: '14px' }}>Đơn {code} · <Link to="/orders">Quay lại đơn hàng</Link></div>
                {body()}
            </div>
        </div>
    );
}
