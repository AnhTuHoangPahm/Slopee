import { useCallback, useEffect, useRef, useState } from 'react';
import { saveDisputeNoteAPI } from '../api/web3';
import CountdownTimer from './CountdownTimer';
import DisputeDialog from './DisputeDialog';
import StatusBadge from './StatusBadge';
import { useOrderActions } from '../hooks/useOrderActions';
import { useOrderStatus } from '../hooks/useOrderStatus';
import { useWallet } from '../hooks/useWallet';
import { toUserMessage } from '../lib/errors';
import { INDEXER_SLOW_AFTER_MS } from '../lib/depositFlow';
import { formatTokenAmount } from '../lib/web3Checkout';
import { shortAddress, shortHash } from '../lib/format';
import { ACTION_STEP, ORDER_ACTION, TARGET_STATUS, clearDisputeDraft, loadDisputeDraft, saveDisputeDraft } from '../lib/orderActions';
import { ORDER_STATUS, availableActions, isTerminalStatus, orderPhase, walletGate } from '../lib/orderTimer';

const btn = { padding: '6px 12px', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold', border: 'none' };
const disabledStyle = { opacity: 0.5, cursor: 'not-allowed' };

const PHASE_TEXT = {
    PENDING_PAYMENT: 'Chưa ký quỹ. Hãy hoàn tất thanh toán ở trang Thanh toán.',
    EXPIRED: 'Báo giá đã hết hạn nên đơn này không được tạo.',
    AWAITING_DELIVERY: 'Tiền đã được khóa an toàn trong hợp đồng. Đang chờ Shipper giao hàng.',
    INSPECTION_OVER: 'Đã hết hạn kiểm tra. Hệ thống sẽ tự giải ngân cho cửa hàng.',
    DISPUTED: 'Khiếu nại đang được xử lý. Tiền bị đóng băng cho tới khi có phán quyết.',
    COMPLETED: 'Đã giải ngân cho cửa hàng.',
    REFUNDED: 'Tiền ký quỹ đã được hoàn lại cho bạn.',
};
const ACTION_TITLE = { [ORDER_ACTION.EARLY_RELEASE]: 'Đã nhận hàng', [ORDER_ACTION.RAISE_DISPUTE]: 'Khiếu nại' };

/** Bật cờ sau `ms` kể từ lúc `active` chuyển true (dùng cho gợi ý "Indexer chậm" sau 30 giây, SDD 9.3). */
function useDelayedFlag(active, ms) {
    const [flag, setFlag] = useState(false);
    useEffect(() => {
        if (!active) return undefined;
        const id = setTimeout(() => setFlag(true), ms);
        return () => { clearTimeout(id); setFlag(false); };
    }, [active, ms]);
    return flag;
}

/**
 * Một đơn con Web3 của Buyer (SDD 9.3, 9.4; SRS 8): trạng thái theo polling, đồng hồ kiểm tra riêng, "Đã nhận hàng" và "Khiếu nại".
 * Mỗi đơn có luồng ví riêng nên thao tác trên đơn của shop này không đổi đơn của shop khác (BR-11).
 *
 * @param {object} props
 * @param {string} props.orderCode       `orders.id`
 * @param {object} props.web3            tóm tắt từ GET /api/payments/orders (xem backend/routes/payments.py::_web3_summaries)
 * @param {Function} [props.escrowFactory]  chỉ dùng khi test
 * @param {Function} [props.fetchStatus]    chỉ dùng khi test
 * @param {Function} [props.saveNote]       chỉ dùng khi test
 * @param {number} [props.pollMs=3000]      chu kỳ polling trạng thái (SDD: 2-3 giây); test đặt nhỏ
 */
export default function Web3OrderPanel({ orderCode, web3, escrowFactory, fetchStatus, saveNote = saveDisputeNoteAPI, pollMs = 3000 }) {
    const w = useWallet();
    const live = web3.status !== ORDER_STATUS.PENDING_PAYMENT && !isTerminalStatus(web3.status);
    const { status: polled, error: pollError, remaining } = useOrderStatus(orderCode, { enabled: live, fetchStatus, intervalMs: pollMs });
    const statusName = polled?.status ?? web3.status;
    const phase = orderPhase(statusName, remaining);
    const can = availableActions(statusName, remaining);

    const { state, run, markIndexed, reset, busy } = useOrderActions(escrowFactory ? { escrowFactory } : {});
    const gate = walletGate({ isConnected: w.isConnected, isCorrectChain: w.isCorrectChain, account: w.account, buyerWallet: web3.buyer_wallet });
    const canPress = gate === 'OK' && !busy;

    // Biên nhận của ví KHÔNG phải trạng thái mới: chỉ khi API (Indexer) báo đúng trạng thái đích mới coi là xong (DD-04, BR-09)
    useEffect(() => {
        const target = TARGET_STATUS[state.kind];
        if (target && statusName === target && (state.step === ACTION_STEP.CONFIRMING || state.step === ACTION_STEP.WAITING_INDEXER)) markIndexed();
    }, [statusName, state.kind, state.step, markIndexed]);
    const slow = useDelayedFlag(state.step === ACTION_STEP.WAITING_INDEXER, INDEXER_SLOW_AFTER_MS);

    // ---- Khiếu nại: lý do chỉ lưu lên sàn SAU khi Indexer ghi DISPUTED (SEQ-02)
    const [dialogOpen, setDialogOpen] = useState(false);
    const [draft, setDraft] = useState(() => loadDisputeDraft(orderCode));
    const [note, setNote] = useState({ status: 'idle', error: null }); // idle | saving | saved | failed
    const noteInFlight = useRef(false);

    const sendNote = useCallback(async () => {
        if (!draft || noteInFlight.current) return;
        noteInFlight.current = true;
        setNote({ status: 'saving', error: null });
        try {
            await saveNote(orderCode, draft);
            clearDisputeDraft(orderCode);
            setDraft(null);
            setNote({ status: 'saved', error: null });
        } catch (e) {
            setNote({ status: 'failed', error: toUserMessage(e) });
        } finally {
            noteInFlight.current = false;
        }
    }, [draft, orderCode, saveNote]);

    useEffect(() => {
        if (statusName === ORDER_STATUS.DISPUTED && draft && note.status === 'idle') sendNote();
    }, [statusName, draft, note.status, sendNote]);

    // Khiếu nại không lên được chuỗi (hủy ví, quá hạn...) thì không giữ lý do nháp
    useEffect(() => {
        if (state.step === ACTION_STEP.FAILED && state.kind === ORDER_ACTION.RAISE_DISPUTE) {
            clearDisputeDraft(orderCode);
            setDraft(null);
        }
    }, [state.step, state.kind, orderCode]);

    const onReceived = () => {
        if (!window.confirm('Xác nhận bạn đã nhận hàng? Tiền ký quỹ sẽ được giải ngân ngay cho cửa hàng và không thể hoàn lại.')) return;
        run(ORDER_ACTION.EARLY_RELEASE, web3.onchain_order_id);
    };
    const onDisputeSubmit = (value) => {
        saveDisputeDraft(orderCode, value);
        setDraft(value);
        setNote({ status: 'idle', error: null });
        setDialogOpen(false);
        run(ORDER_ACTION.RAISE_DISPUTE, web3.onchain_order_id);
    };

    const showActions = statusName === ORDER_STATUS.DELIVERED;
    const decimals = w.deployment?.token?.decimals ?? 6;

    return (
        <div data-testid="web3-panel" data-order={orderCode} style={{ borderTop: '1px dashed #ddd', marginTop: '10px', paddingTop: '10px', fontSize: '14px' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                    <StatusBadge status={statusName} />
                    <span style={{ color: '#666' }}>Ký quỹ: <strong>{formatTokenAmount(web3.amount_raw, decimals, web3.token_symbol)}</strong></span>
                </div>
                {statusName === ORDER_STATUS.DELIVERED && <CountdownTimer remaining={remaining} />}
            </div>

            {PHASE_TEXT[phase] && <p data-testid="phase-text" style={{ margin: '8px 0 0', color: '#555' }}>{PHASE_TEXT[phase]}</p>}
            {phase === 'INSPECTING' && (
                <p style={{ margin: '8px 0 0', color: '#555' }}>
                    Nếu hàng có vấn đề, hãy khiếu nại trước khi hết giờ. Hết giờ mà không khiếu nại, tiền sẽ tự động giải ngân cho cửa hàng.
                </p>
            )}
            {(polled?.anomaly || web3.anomaly) && <p style={{ margin: '8px 0 0', color: '#b8860b' }}>Hệ thống phát hiện sai lệch dữ liệu ở đơn này, quản trị viên sẽ kiểm tra.</p>}
            {pollError && !polled && <p role="status" style={{ margin: '8px 0 0', color: '#888' }}>Chưa cập nhật được trạng thái đơn, đang thử lại…</p>}

            {showActions && (
                <div style={{ marginTop: '10px' }}>
                    <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
                        <button type="button" data-testid="receive-btn" disabled={!can.earlyRelease || !canPress} onClick={onReceived}
                            style={{ ...btn, background: '#4caf50', color: '#fff', ...(!can.earlyRelease || !canPress ? disabledStyle : null) }}>
                            ✔ Đã nhận hàng
                        </button>
                        <button type="button" data-testid="dispute-btn" disabled={!can.dispute || !canPress} onClick={() => setDialogOpen(true)}
                            title={!can.dispute && statusName === ORDER_STATUS.DELIVERED ? 'Đã quá thời hạn kiểm tra nên không thể khiếu nại' : undefined}
                            style={{ ...btn, background: '#fff', color: '#d32f2f', border: '1px solid #d32f2f', ...(!can.dispute || !canPress ? disabledStyle : null) }}>
                            Khiếu nại
                        </button>
                        {gate === 'NOT_CONNECTED' && <button type="button" data-testid="gate-connect" onClick={w.connect} style={{ ...btn, background: '#ee4d2d', color: '#fff' }}>Kết nối MetaMask để thao tác</button>}
                        {gate === 'WRONG_CHAIN' && <button type="button" data-testid="gate-switch" onClick={w.switchToDeployedChain} style={{ ...btn, background: '#ee4d2d', color: '#fff' }}>Chuyển sang mạng Anvil</button>}
                    </div>
                    {gate === 'WRONG_ACCOUNT' && (
                        <p data-testid="gate-wrong-account" role="alert" style={{ margin: '8px 0 0', color: '#b8860b' }}>
                            Ví đang chọn không phải ví đã ký quỹ đơn này ({shortAddress(web3.buyer_wallet)}). Hãy chọn đúng ví trong MetaMask.
                        </p>
                    )}
                </div>
            )}

            {state.step !== ACTION_STEP.IDLE && (
                <div data-testid="action-progress" data-step={state.step} role="status" style={{ marginTop: '10px', padding: '8px 10px', background: '#f7f7f7', borderRadius: '4px' }}>
                    {state.step === ACTION_STEP.SIGNING && <span>Hãy xác nhận «{ACTION_TITLE[state.kind]}» trong MetaMask…</span>}
                    {state.step === ACTION_STEP.CONFIRMING && <span>Đang chờ giao dịch được ghi vào chuỗi{state.txHash ? ` (${shortHash(state.txHash)})` : ''}…</span>}
                    {state.step === ACTION_STEP.WAITING_INDEXER && (
                        <span>
                            Giao dịch đã vào chuỗi, đang chờ hệ thống xác nhận…
                            {slow && <> Việc này lâu hơn bình thường. Mã giao dịch: <code>{state.txHash}</code>. Hãy báo quản trị viên kiểm tra Indexer.</>}
                        </span>
                    )}
                    {state.step === ACTION_STEP.DONE && <span style={{ color: '#2e7d32' }}>Hệ thống đã ghi nhận «{ACTION_TITLE[state.kind]}».</span>}
                    {state.step === ACTION_STEP.FAILED && (
                        <span style={{ color: state.error?.userRejected ? '#666' : '#d32f2f' }}>
                            {state.error?.message}{' '}
                            <button type="button" data-testid="action-retry" onClick={reset} style={{ ...btn, padding: '2px 8px', background: '#fff', border: '1px solid #bbb', fontWeight: 'normal' }}>Đóng</button>
                        </span>
                    )}
                </div>
            )}

            {statusName === ORDER_STATUS.DISPUTED && (note.status === 'saving' || note.status === 'saved' || note.status === 'failed') && (
                <div data-testid="dispute-note-status" data-state={note.status} style={{ marginTop: '10px', fontSize: '13px' }}>
                    {note.status === 'saving' && <span>Đang gửi lý do và bằng chứng khiếu nại…</span>}
                    {note.status === 'saved' && <span style={{ color: '#2e7d32' }}>Đã gửi lý do và bằng chứng cho sàn.</span>}
                    {note.status === 'failed' && (
                        <span style={{ color: '#d32f2f' }}>
                            Khiếu nại đã được ghi nhận nhưng chưa gửi được lý do: {note.error}{' '}
                            <button type="button" data-testid="note-retry" onClick={() => setNote({ status: 'idle', error: null })} style={{ ...btn, padding: '2px 8px', background: '#fff', border: '1px solid #bbb', fontWeight: 'normal' }}>Gửi lại lý do</button>
                        </span>
                    )}
                </div>
            )}

            {dialogOpen && <DisputeDialog onSubmit={onDisputeSubmit} onCancel={() => setDialogOpen(false)} />}
        </div>
    );
}
