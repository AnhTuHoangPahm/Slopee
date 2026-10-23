import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchMerchantOrdersAPI } from '../api/merchant';
import { useClaimPending } from '../hooks/useClaimPending';
import { usePolling } from '../hooks/usePolling';
import { useWallet } from '../hooks/useWallet';
import { CLAIM_STEP, claimIndexed } from '../lib/claimPending';
import { toUserMessage } from '../lib/errors';
import { formatVND, shortAddress, shortHash } from '../lib/format';
import { walletGate } from '../lib/orderTimer';
import {
    FILTERS, MERCHANT_STATUS_META, disputePath, filterOrders, formatAmount, formatChainTime, normalizeMerchantResponse, statusNote, summarizeOrders,
} from '../lib/merchantOrders';

const POLL_MS = 10000;
const FAST_POLL_MS = 3000;     // trong lúc chờ Indexer ghi nhận khoản vừa rút
const card = { background: '#fff', border: '1px solid #e5e5e5', borderRadius: 8, padding: 16, marginBottom: 12 };
const btn = { padding: '8px 14px', borderRadius: 6, border: 'none', background: '#ee4d2d', color: '#fff', cursor: 'pointer', fontWeight: 600 };
const btnGhost = { ...btn, background: '#fff', color: '#555', border: '1px solid #ccc' };
const badge = (m) => ({ display: 'inline-block', padding: '2px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600, color: m.color, background: m.bg, border: `1px solid ${m.color}` });
const FILTER_LABEL = { ALL: 'Tất cả', ...Object.fromEntries(Object.entries(MERCHANT_STATUS_META).map(([k, v]) => [k, v.label])) };

const GATE_TEXT = {
    WRONG_ACCOUNT: (addr) => `Hãy chọn ví ${shortAddress(addr)} trong MetaMask: khoản chờ rút chỉ ví này mới rút được.`,
};

/**
 * UC-07 phía Merchant (SDD 9.2): danh sách đơn Web3 của shop + khoản chờ rút (`claimPending`).
 * Merchant KHÔNG cần làm gì để nhận tiền: contract tự chuyển khi giải ngân. Khoản chờ rút chỉ có khi ví nhận ETH từ chối (BR-05);
 * với mUSD luôn trống. Trạng thái đơn và số dư chỉ do Indexer ghi (BR-09): giao diện không tự đoán theo biên nhận của ví.
 *
 * @param {object} [props]
 * @param {Function} [props.fetchOrders]    chỉ dùng khi test
 * @param {Function} [props.escrowFactory]  chỉ dùng khi test
 * @param {number}   [props.pollMs]         chu kỳ polling (mặc định 10 giây)
 */
export default function MerchantWeb3Panel({ fetchOrders = fetchMerchantOrdersAPI, escrowFactory, pollMs = POLL_MS }) {
    const w = useWallet();
    const claim = useClaimPending({ escrowFactory });
    const [filter, setFilter] = useState('ALL');
    const { data, error, refresh } = usePolling((signal) => fetchOrders(signal), { intervalMs: claim.busy ? Math.min(FAST_POLL_MS, pollMs) : pollMs });
    const view = useMemo(() => (data ? normalizeMerchantResponse(data) : null), [data]);

    // Khoản vừa rút biến mất khỏi API => Indexer đã ghi nhận
    const lastKey = useRef(null);
    const { state: claimState, markIndexed } = claim;
    useEffect(() => {
        if (!view || (claimState.step !== CLAIM_STEP.WAITING_INDEXER && claimState.step !== CLAIM_STEP.CONFIRMING)) return;
        if (claimIndexed(view.pending, claimState)) markIndexed();
    }, [view, claimState, markIndexed]);
    useEffect(() => {
        if (claimState.step === CLAIM_STEP.WAITING_INDEXER && lastKey.current !== claimState.txHash) {
            lastKey.current = claimState.txHash;
            refresh();             // hỏi lại NGAY khi giao dịch đã được đào, thay vì chờ chu kỳ tiếp theo
        }
    }, [claimState.step, claimState.txHash, refresh]);

    const summary = useMemo(() => (view ? summarizeOrders(view.orders) : null), [view]);
    const shown = useMemo(() => (view ? filterOrders(view.orders, filter) : []), [view, filter]);

    return (
        <section aria-label="Đơn Web3 của shop" data-testid="merchant-web3" style={{ marginBottom: 32 }}>
            <h2 style={{ marginTop: 0, color: '#333' }}>Đơn thanh toán Web3</h2>
            <p style={{ color: '#666', marginTop: 0 }}>
                Người mua ký quỹ tiền vào hợp đồng; khi giao hàng thành công và hết hạn kiểm tra, tiền tự chuyển vào ví nhận tiền của bạn.
                Bạn không cần thao tác gì để nhận tiền.
            </p>

            {error && <p role="alert" style={{ color: '#c0392b' }}>{toUserMessage(error)} (đang tự thử lại)</p>}
            {view === null && !error && <p role="status">Đang tải đơn Web3…</p>}

            {view && !view.wallet && (
                <div role="alert" data-testid="no-wallet" style={{ ...card, background: '#fff8e1', borderColor: '#ffe082' }}>
                    Shop chưa có ví nhận tiền nên người mua chưa thể thanh toán Web3 cho bạn. <Link to="/wallet">Liên kết ví ngay</Link>.
                </div>
            )}

            {view && <PendingSection view={view} claim={claim} wallet={w} />}

            {view && summary && (
                <div data-testid="merchant-summary" style={{ ...card, display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                    <div>
                        <div style={{ color: '#666', fontSize: 13 }}>Đang ký quỹ (shop sẽ nhận, sau phí)</div>
                        <strong data-testid="sum-escrow">{summary.inEscrow.length ? summary.inEscrow.map((t) => formatAmount(t.amountRaw, t.decimals, t.symbol)).join(' · ') : '—'}</strong>
                    </div>
                    <div>
                        <div style={{ color: '#666', fontSize: 13 }}>Đã nhận</div>
                        <strong data-testid="sum-received">{summary.received.length ? summary.received.map((t) => formatAmount(t.amountRaw, t.decimals, t.symbol)).join(' · ') : '—'}</strong>
                    </div>
                    <div style={{ color: '#555', fontSize: 14 }}>
                        {Object.entries(summary.counts).filter(([, n]) => n > 0).map(([s, n]) => `${MERCHANT_STATUS_META[s].label}: ${n}`).join(' · ') || 'Chưa có đơn nào'}
                    </div>
                </div>
            )}

            {view && view.orders.length > 0 && (
                <label style={{ display: 'block', marginBottom: 10 }}>
                    Lọc theo trạng thái:{' '}
                    <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Lọc theo trạng thái">
                        {FILTERS.map((f) => <option key={f} value={f}>{FILTER_LABEL[f]}</option>)}
                    </select>
                </label>
            )}
            {view && view.orders.length === 0 && <p data-testid="merchant-empty">Chưa có đơn Web3 nào được người mua ký quỹ.</p>}
            {view && view.orders.length > 0 && shown.length === 0 && <p data-testid="merchant-filter-empty">Không có đơn nào ở trạng thái này.</p>}

            {shown.map((o) => <OrderCard key={o.code} o={o} />)}
        </section>
    );
}

function OrderCard({ o }) {
    const meta = MERCHANT_STATUS_META[o.status];
    const dispute = disputePath(o);
    return (
        <article style={card} aria-label={`Đơn ${o.code}`} data-testid={`merchant-order-${o.code}`} data-status={o.status}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <strong title={o.code}>Đơn {String(o.code).slice(0, 8)}</strong>
                <span data-testid="merchant-status" style={badge(meta)}>{meta.label}</span>
            </div>
            <div style={{ color: '#555', fontSize: 14, marginTop: 6 }}>
                {o.buyerName && <div>Người mua: {o.buyerName}</div>}
                {o.items.map((it, i) => <div key={i}>{it.name} × {it.quantity}</div>)}
                {o.priceVnd != null && <div>Giá trị đơn: {formatVND(o.priceVnd)}</div>}
                <div>Ký quỹ: <strong>{formatAmount(o.amountRaw, o.decimals, o.symbol)}</strong> · Bạn nhận (sau phí {((o.feeBps ?? 0) / 100).toLocaleString('vi-VN')}%): <strong>{formatAmount(o.netRaw, o.decimals, o.symbol)}</strong></div>
                {o.lockedAt && <div>Ký quỹ lúc: {formatChainTime(o.lockedAt)}</div>}
                {o.deliveredAt && <div>Giao lúc: {formatChainTime(o.deliveredAt)}</div>}
            </div>
            <p style={{ margin: '10px 0 0', fontSize: 14 }} data-testid="merchant-note">{statusNote(o)}</p>
            {dispute && <p style={{ margin: '8px 0 0' }}><Link to={dispute} data-testid="dispute-link">Xem đề xuất phán quyết và ký</Link></p>}
        </article>
    );
}

function PendingSection({ view, claim, wallet }) {
    const { state } = claim;
    return (
        <div data-testid="pending-section" id="web3-pending" style={card}>
            <h3 style={{ marginTop: 0 }}>Khoản chờ rút</h3>
            {view.pending.length === 0 && state.step !== CLAIM_STEP.DONE && state.step !== CLAIM_STEP.WAITING_INDEXER && (
                <p data-testid="pending-empty" style={{ margin: 0, color: '#555' }}>
                    Không có khoản nào đang chờ rút. Khi đơn được giải ngân, tiền tự chuyển vào ví nhận tiền của bạn.
                </p>
            )}
            {view.pending.map((p) => {
                const key = `${p.token}:${p.address}`;
                const mine = state.token === p.token && state.address === p.address;
                const gate = walletGate({ isConnected: wallet.isConnected, isCorrectChain: wallet.isCorrectChain, account: wallet.account, buyerWallet: p.address });
                const working = claim.busy;
                return (
                    <div key={key} data-testid={`pending-${p.token}`} style={{ borderTop: '1px solid #eee', paddingTop: 10, marginTop: 10 }}>
                        <div>
                            Có thể rút: <strong>{formatAmount(p.amountRaw, p.decimals, p.symbol)}</strong> về ví <code title={p.address}>{shortAddress(p.address)}</code>
                        </div>
                        <p style={{ color: '#666', fontSize: 13, margin: '4px 0 8px' }}>
                            Khoản này phát sinh vì ví nhận từ chối nhận ETH lúc giải ngân. Hợp đồng đã giữ hộ để đơn không bị kẹt; chỉ ví này rút được.
                        </p>
                        {gate === 'NOT_CONNECTED' && <button type="button" style={btn} data-testid="gate-connect" onClick={wallet.connect}>Kết nối ví</button>}
                        {gate === 'WRONG_CHAIN' && <button type="button" style={btn} data-testid="gate-switch" onClick={wallet.switchToDeployedChain}>Chuyển sang mạng Anvil</button>}
                        {gate === 'WRONG_ACCOUNT' && <p role="alert" data-testid="gate-wrong-account" style={{ color: '#b26a00', margin: 0 }}>{GATE_TEXT.WRONG_ACCOUNT(p.address)}</p>}
                        {gate === 'OK' && (
                            <button type="button" style={{ ...btn, ...(working ? { opacity: 0.5, cursor: 'not-allowed' } : {}) }} disabled={working}
                                data-testid="claim-button" onClick={() => claim.run(p.token, p.address)}>
                                {mine && state.step === CLAIM_STEP.SIGNING ? 'Hãy xác nhận trong ví…'
                                    : mine && state.step === CLAIM_STEP.CONFIRMING ? 'Đang chờ giao dịch được đào…'
                                        : mine && state.step === CLAIM_STEP.WAITING_INDEXER ? 'Đang chờ hệ thống ghi nhận…'
                                            : 'Rút về ví'}
                            </button>
                        )}
                    </div>
                );
            })}
            <ClaimStatus state={state} onReset={claim.reset} />
        </div>
    );
}

function ClaimStatus({ state, onReset }) {
    if (state.step === CLAIM_STEP.DONE) {
        return (
            <p role="status" data-testid="claim-done" style={{ color: '#2e7d32', marginBottom: 0 }}>
                Đã rút xong{state.txHash ? ` (giao dịch ${shortHash(state.txHash)})` : ''}. Tiền đã về ví của bạn.{' '}
                <button type="button" style={btnGhost} onClick={onReset}>Đóng</button>
            </p>
        );
    }
    if (state.step === CLAIM_STEP.FAILED && state.error) {
        return (
            <p role="alert" data-testid="claim-error" style={{ color: state.error.userRejected ? '#666' : '#c0392b', marginBottom: 0 }}>
                {state.error.message}{' '}<button type="button" style={btnGhost} onClick={onReset}>Đóng</button>
            </p>
        );
    }
    if (state.step === CLAIM_STEP.CONFIRMING && state.txHash) {
        return <p role="status" data-testid="claim-sent" style={{ color: '#555', marginBottom: 0 }}>Đã gửi giao dịch {shortHash(state.txHash)}, đang chờ blockchain xác nhận…</p>;
    }
    return null;
}
