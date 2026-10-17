import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useWallet } from '../hooks/useWallet';
import { createWeb3OrderAPI, fetchCheckoutGroupAPI, fetchLinkedWalletAPI, requoteGroupAPI } from '../api/web3';
import { useEscrow } from '../hooks/useEscrow';
import { usePolling } from '../hooks/usePolling';
import TxStepper from './TxStepper';
import { FLOW_ERROR, INDEXER_SLOW_AFTER_MS, STEP, groupIsLocked } from '../lib/depositFlow';
import { Web3ApiError, toUserMessage } from '../lib/errors';
import { formatVND } from '../utils/formatVND';
import { sameAddress } from '../lib/chain';
import { shortAddress } from '../lib/format';
import { describeDuration, formatCountdown, formatFeeBps, formatTokenAmount, quoteStatus, secondsRemaining } from '../lib/web3Checkout';

// Lô không còn ở trạng thái cho phép cấp lại báo giá: không hiện nút thử lại
const TERMINAL_REQUOTE_ERRORS = ['INVALID_STATE', 'GROUP_NOT_FOUND'];
const box = { border: '1px solid #e5e5e5', borderRadius: 8, padding: 16, marginTop: 12 };
const primary = { padding: '10px 18px', borderRadius: 6, border: 'none', background: '#ee4d2d', color: '#fff', cursor: 'pointer', fontWeight: 600 };
const secondary = { ...primary, background: '#fff', color: '#ee4d2d', border: '1px solid #ee4d2d' };

const POLL_INTERVAL_MS = 2500; // SDD 10.2: polling 2-3 giây
const REDIRECT_DELAY_MS = 2000; // cho người dùng thấy dòng "đã khóa tiền" rồi mới chuyển màn hình

/**
 * Khung thanh toán Web3 (SDD 9.3): kiểm tra ví/mạng/liên kết -> tạo đơn + báo giá -> hiển thị từng shop, tổng tiền token,
 * đếm ngược hạn báo giá -> (Tuần 4) hai bước ví: approve tổng, depositEscrowBatch -> chờ Indexer (polling lô) -> LOCKED -> /orders.
 * Giao diện KHÔNG coi biên nhận của ví là LOCKED; chỉ API trả mọi đơn con LOCKED mới là bằng chứng (DD-04, BR-09).
 * @param {{cartItemIds: string[], onLocked?: (group: object) => void, contractsFactory?: Function}} props
 */
export default function Web3CheckoutPanel({ cartItemIds, onLocked, contractsFactory }) {
    const w = useWallet();
    const navigate = useNavigate();
    const escrow = useEscrow(contractsFactory ? { contractsFactory } : undefined);
    const [slow, setSlow] = useState(false);
    const [linked, setLinked] = useState(null);
    const [group, setGroup] = useState(null);
    const [receivedAt, setReceivedAt] = useState(0);
    const [now, setNow] = useState(Date.now());
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null); // Web3ApiError | Error
    const [pendingGroupId, setPendingGroupId] = useState(null); // lô đang chờ do backend báo (PENDING_GROUP_EXISTS); còn thì còn nút "Làm mới"

    useEffect(() => {
        fetchLinkedWalletAPI().then(setLinked).catch(() => setLinked({ linked: false }));
    }, []);

    // Nhận báo giá mới: đặt `receivedAt` và `now` cùng một thời điểm để đồng hồ bắt đầu ĐÚNG từ hạn mới (không giật theo nhịp 1 giây cũ)
    const accept = useCallback((g) => {
        const t = Date.now();
        setPendingGroupId(null);
        setGroup(g);
        setReceivedAt(t);
        setNow(t);
        setError(null);
    }, []);

    // Đếm ngược mỗi giây khi đã có báo giá
    useEffect(() => {
        if (!group) return undefined;
        const t = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(t);
    }, [group]);

    const remaining = useMemo(
        () => (group ? secondsRemaining({ deadline: group.deadline, serverTime: group.server_time, receivedAtMs: receivedAt, nowMs: now }) : 0),
        [group, receivedAt, now],
    );
    const status = group ? quoteStatus(remaining) : null;

    // Chỉ một yêu cầu báo giá được bay tại một thời điểm. `busy` (state) khóa nút khi render lại, còn `inFlight` (ref)
    // chặn cả những cú bấm dồn trong CÙNG một nhịp trước khi React kịp render nút ở trạng thái disabled.
    const inFlight = useRef(false);
    const run = async (fn) => {
        if (inFlight.current) return;
        inFlight.current = true;
        setBusy(true);
        try {
            accept(await fn());
        } catch (e) {
            setError(e);
            if (e instanceof Web3ApiError && e.code === 'PENDING_GROUP_EXISTS' && e.extra?.checkout_group_id) setPendingGroupId(e.extra.checkout_group_id);
            else if (e instanceof Web3ApiError && TERMINAL_REQUOTE_ERRORS.includes(e.code)) setPendingGroupId(null); // lô không còn làm mới được: thử lại vô ích
            // lỗi tạm thời (mạng, chain, hết hàng...) thì GIỮ pendingGroupId để người dùng bấm lại
        } finally { inFlight.current = false; setBusy(false); }
    };
    const create = () => run(() => createWeb3OrderAPI(cartItemIds));
    const requote = () => run(() => requoteGroupAPI(group.checkout_group_id));
    // Lô đang chờ: KHÔNG khôi phục phiên cũ mà xin báo giá MỚI (chữ ký + hạn mới đủ thời hạn) cho chính lô đó, nên nhãn nút nói rõ là "làm mới"

    // ---- Nạp tiền (Tuần 4)
    const dep = escrow.state;
    const depositing = escrow.busy; // CHECKING | APPROVING | DEPOSITING | WAITING_INDEXER
    const settled = dep.step === STEP.LOCKED;

    // Lỗi "Order exists" = lần nạp trước đã vào chuỗi: không nạp lại, chuyển sang chờ API xác nhận
    useEffect(() => {
        if (dep.step === STEP.FAILED && dep.error?.code === FLOW_ERROR.ORDER_EXISTS) escrow.dispatch({ type: 'RESUME_WAITING' });
    }, [dep.step, dep.error, escrow]);

    // Polling lô tới khi mọi đơn con LOCKED (usePolling: không chồng lệnh, dừng khi rời trang / đạt trạng thái cuối)
    const groupId = group?.checkout_group_id;
    const poll = usePolling(() => fetchCheckoutGroupAPI(groupId), {
        intervalMs: POLL_INTERVAL_MS, enabled: dep.step === STEP.WAITING_INDEXER && Boolean(groupId), stopWhen: groupIsLocked,
    });
    useEffect(() => {
        if (dep.step === STEP.WAITING_INDEXER && groupIsLocked(poll.data)) escrow.dispatch({ type: 'INDEXER_LOCKED' });
    }, [dep.step, poll.data, escrow]);

    // Chờ quá 30 giây: nhắc mã giao dịch (SDD 9.3)
    useEffect(() => {
        if (dep.step !== STEP.WAITING_INDEXER) { setSlow(false); return undefined; }
        const t = setTimeout(() => setSlow(true), INDEXER_SLOW_AFTER_MS);
        return () => clearTimeout(t);
    }, [dep.step]);

    // LOCKED: báo thành công rồi tự chuyển màn hình
    useEffect(() => {
        if (!settled) return undefined;
        const t = setTimeout(() => (onLocked ? onLocked(poll.data) : navigate('/orders', { state: { lockedGroupId: groupId } })), REDIRECT_DELAY_MS);
        return () => clearTimeout(t);
    }, [settled]); // eslint-disable-line react-hooks/exhaustive-deps

    const startDeposit = () => escrow.deposit(group, () => secondsRemaining({ deadline: group.deadline, serverTime: group.server_time, receivedAtMs: receivedAt, nowMs: Date.now() }));
    const flowFailed = dep.step === STEP.FAILED && dep.error;
    const needsFreshQuote = flowFailed && ['QUOTE_EXPIRING', 'QUOTE_MISMATCH'].includes(dep.error.code);

    // ---- cổng điều kiện (SDD 9.3: CHECK_WALLET -> CHECK_NETWORK -> đã liên kết)
    let gate = null;
    if (!w.hasProvider) gate = <p role="alert">Không tìm thấy ví. Hãy cài MetaMask rồi tải lại trang.</p>;
    else if (!w.isConnected) gate = <button type="button" style={primary} onClick={w.connect}>Kết nối MetaMask</button>;
    else if (!w.isCorrectChain) gate = <button type="button" style={primary} onClick={w.switchToDeployedChain}>Chuyển sang mạng Anvil</button>;
    else if (linked === null) gate = <p role="status">Đang kiểm tra liên kết ví…</p>;
    else if (!linked.linked) gate = <p role="alert">Bạn chưa liên kết ví với tài khoản. <Link to="/wallet">Liên kết ví</Link></p>;
    else if (!sameAddress(linked.address, w.account)) {
        gate = <p role="alert">Ví đang kết nối ({shortAddress(w.account)}) khác ví đã liên kết ({shortAddress(linked.address)}). <Link to="/wallet">Đổi ví liên kết</Link></p>;
    }

    const canDeposit = !gate && group && status !== 'expired' && !depositing && !settled && !busy;

    const pendingId = !group ? pendingGroupId : null;
    const walletError = error instanceof Web3ApiError && error.code === 'WALLET_NOT_LINKED';
    const merchantUnlinked = walletError && String(error.extra?.party).toLowerCase() === 'merchant'; // Backend gửi 'merchant'; so không phân biệt hoa/thường
    const needsWallet = walletError && !merchantUnlinked; // ví của CHÍNH người mua thì mới dẫn tới /wallet; shop chưa liên kết thì người mua không tự sửa được
    const errorText = merchantUnlinked
        ? (error.extra?.shop_name
            ? `Cửa hàng «${error.extra.shop_name}» chưa liên kết ví nhận tiền nên chưa thể thanh toán Web3 cho đơn này.`
            : 'Có cửa hàng trong đơn hàng chưa liên kết ví nhận tiền nên chưa thể thanh toán Web3 cho đơn này.')
        : error ? toUserMessage(error) : '';

    return (
        <div style={box} data-testid="web3-panel">
            <h4 style={{ marginTop: 0 }}>🦊 Thanh toán Web3 (ký quỹ {group?.symbol ?? 'mUSD'})</h4>
            <p style={{ color: '#666', fontSize: 13 }}>
                Tiền được giữ trong hợp đồng ký quỹ cho tới khi bạn nhận hàng. Chỉ chạy trên mạng thử Anvil, không dùng tiền thật.
            </p>

            {gate}

            {!gate && !group && (
                <button type="button" style={primary} onClick={create} disabled={busy || !cartItemIds.length}>
                    {busy ? 'Đang tạo báo giá…' : 'Tạo báo giá'}
                </button>
            )}

            {error && (
                <div role="alert" style={{ color: '#c0392b', marginTop: 8 }}>
                    <span>{errorText}</span>{' '}
                    {pendingId && <button type="button" style={secondary} onClick={() => run(() => requoteGroupAPI(pendingId))} disabled={busy}>Làm mới báo giá cho lô này</button>}
                    {needsWallet && <Link to="/wallet">Liên kết ví</Link>}
                </div>
            )}

            {group && (
                <div data-testid="quote-result">
                    <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }}>
                        <thead>
                            <tr style={{ textAlign: 'left', borderBottom: '1px solid #eee' }}>
                                <th>Shop</th><th>Giá (VND)</th><th>Số tiền ký quỹ</th><th>Phí sàn</th><th>Thời hạn kiểm tra / khiếu nại</th>
                            </tr>
                        </thead>
                        <tbody>
                            {group.orders.map((o) => (
                                <tr key={o.order_id} data-testid="quote-row" style={{ borderBottom: '1px solid #f3f3f3' }}>
                                    <td>{o.shop_name}</td>
                                    <td>{formatVND(o.price_vnd)}</td>
                                    <td>{formatTokenAmount(o.amount_raw, group.decimals, group.symbol)}</td>
                                    <td>{formatFeeBps(o.fee_bps)}</td>
                                    <td>{describeDuration(o.inspection_duration)} / {describeDuration(o.dispute_timeout)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <p style={{ fontWeight: 700 }} data-testid="quote-total">Tổng: {formatTokenAmount(group.total_amount_raw, group.decimals, group.symbol)}</p>
                    <p style={{ color: '#666', fontSize: 12 }}>Tỷ giá đã chốt: 1 {group.symbol} = {formatVND(Number(group.orders[0]?.fx))}</p>

                    <p data-testid="quote-countdown" role="status" style={{ color: status === 'ok' ? '#2e7d32' : '#c0392b' }}>
                        {status === 'expired' ? 'Báo giá đã hết hạn.' : `Báo giá còn hiệu lực: ${formatCountdown(remaining)}`}
                        {status === 'expiring' && ' — sắp hết hạn, hãy lấy báo giá mới.'}
                    </p>

                    {dep.step !== STEP.IDLE && <TxStepper state={dep} slow={slow} />}

                    {flowFailed && !dep.error.userRejected && (
                        <p data-testid="deposit-error" role="alert" style={{ color: '#c0392b' }}>
                            {dep.error.message}
                            {dep.shortfall && <> Còn thiếu {formatTokenAmount(dep.shortfall, group.decimals, group.symbol)}.</>}
                        </p>
                    )}
                    {flowFailed && dep.error.userRejected && <p data-testid="deposit-cancelled" role="status" style={{ color: '#666' }}>{dep.error.message} Bạn có thể bấm «Ký quỹ» để thử lại.</p>}
                    {settled && <p data-testid="deposit-locked" role="status" style={{ color: '#2e7d32', fontWeight: 600 }}>Đã khóa tiền ký quỹ cho {group.orders.length} đơn. Đang chuyển tới đơn hàng của bạn…</p>}

                    {!settled && (
                        <div style={{ display: 'flex', gap: 8 }}>
                            <button type="button" style={secondary} onClick={requote} disabled={busy || depositing}>Lấy báo giá mới</button>
                            <button type="button" data-testid="deposit-button" style={{ ...primary, opacity: canDeposit ? 1 : 0.5, cursor: canDeposit ? 'pointer' : 'not-allowed' }}
                                disabled={!canDeposit} onClick={startDeposit}
                                title={status === 'expired' ? 'Báo giá đã hết hạn, hãy lấy báo giá mới' : undefined}>
                                {depositing ? 'Đang xử lý…' : flowFailed ? 'Thử lại ký quỹ' : 'Ký quỹ'}
                            </button>
                            {needsFreshQuote && <span style={{ alignSelf: 'center', color: '#b26a00', fontSize: 13 }}>Hãy bấm «Lấy báo giá mới» trước.</span>}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
