import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Navbar from '../components/Navbar';
import { deliverShipperOrderAPI, fetchShipperOrdersAPI } from '../api/shipper';
import { usePolling } from '../hooks/usePolling';
import { toUserMessage } from '../lib/errors';
import { formatVND, shortHash } from '../lib/format';
import { canDeliver, deliverSuccessMessage, normalizeShipperOrder, pruneLocal, SHIPPER_STATUS } from '../lib/shipperOrders';

const POLL_MS = 5000;
const card = { background: '#fff', border: '1px solid #e5e5e5', borderRadius: 8, padding: 16, marginBottom: 12 };
const btn = { padding: '10px 16px', borderRadius: 6, border: 'none', background: '#ee4d2d', color: '#fff', cursor: 'pointer', fontWeight: 600 };
const btnGhost = { ...btn, background: '#fff', color: '#555', border: '1px solid #ccc' };
const badge = (bg, fg) => ({ display: 'inline-block', padding: '2px 8px', borderRadius: 10, fontSize: 12, background: bg, color: fg });

const formatTime = (sec) => (sec ? new Date(sec * 1000).toLocaleString('vi-VN') : '');

/**
 * UC-03: cổng Shipper. Shipper KHÔNG cần ví: bấm "Xác nhận phát hàng thành công" thì Backend (relayer) gửi `confirmDelivery`
 * bằng khóa của sàn. Trạng thái đơn chỉ đổi khi Indexer thấy sự kiện trên chuỗi (BR-09), nên sau khi bấm giao diện hiện
 * "đang chờ hệ thống ghi nhận" cho tới khi danh sách do máy chủ trả về cho thấy đơn đã sang DELIVERED.
 */
export default function ShipperOrders() {
    const { data, error, refresh } = usePolling((signal) => { void signal; return fetchShipperOrdersAPI(); }, { intervalMs: POLL_MS });
    const [local, setLocal] = useState({});       // { [code]: { phase: 'confirm'|'sending'|'sent'|'error', message?, txHash? } }
    const busy = useRef(new Set());               // chặn bấm đúp: cờ đồng bộ, không chờ setState

    const orders = useMemo(() => (data ? data.map(normalizeShipperOrder).filter((o) => o.code) : null), [data]);

    useEffect(() => {
        if (orders) setLocal((cur) => pruneLocal(cur, orders));
    }, [orders]);

    const setPhase = useCallback((code, st) => setLocal((cur) => ({ ...cur, [code]: st })), []);

    const deliver = useCallback(async (code) => {
        if (busy.current.has(code)) return;
        busy.current.add(code);
        setPhase(code, { phase: 'sending' });
        try {
            const res = await deliverShipperOrderAPI(code);
            setPhase(code, { phase: 'sent', message: deliverSuccessMessage(res), txHash: res?.tx_hash ?? null });
        } catch (e) {
            setPhase(code, { phase: 'error', message: toUserMessage(e) });
        } finally {
            busy.current.delete(code);
            refresh();            // đọc lại ngay thay vì chờ chu kỳ tiếp theo (lỗi INVALID_STATE thường nghĩa là danh sách đã cũ)
        }
    }, [refresh, setPhase]);

    return (
        <div>
            <Navbar />
            <main style={{ maxWidth: 760, margin: '24px auto', padding: '0 16px' }}>
                <h2>Đơn cần giao</h2>
                <p style={{ color: '#666' }}>
                    Các đơn đã được người mua ký quỹ và gán cho bạn. Sau khi giao hàng, bấm xác nhận: hệ thống gửi giao dịch thay bạn,
                    bạn không cần ví và không mất phí.
                </p>

                {error && <p role="alert" style={{ color: '#c0392b' }}>{toUserMessage(error)} (đang tự thử lại)</p>}
                {orders === null && !error && <p role="status">Đang tải…</p>}
                {orders && orders.length === 0 && <p data-testid="shipper-empty">Hiện chưa có đơn nào được gán cho bạn.</p>}

                {orders && orders.map((o) => {
                    const st = local[o.code];
                    return (
                        <section key={o.code} style={card} aria-label={`Đơn ${o.code}`} data-testid={`order-${o.code}`}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                                <strong title={o.code}>Đơn {String(o.code).slice(0, 8)}</strong>
                                {o.status === SHIPPER_STATUS.DELIVERED
                                    ? <span style={badge('#e8f5e9', '#2e7d32')}>Đã giao, chờ người mua kiểm tra</span>
                                    : <span style={badge('#fff3e0', '#b26a00')}>Chờ giao hàng</span>}
                            </div>
                            <div style={{ color: '#555', fontSize: 14, marginTop: 6 }}>
                                {o.shopName && <div>Shop: {o.shopName}</div>}
                                {o.buyerName && <div>Người nhận: {o.buyerName}</div>}
                                {o.priceVnd != null && <div>Giá trị đơn: {formatVND(o.priceVnd)}</div>}
                                {o.lockedAt && <div>Đã ký quỹ lúc: {formatTime(o.lockedAt)}</div>}
                                {o.deliveredAt && <div>Giao lúc: {formatTime(o.deliveredAt)}</div>}
                            </div>

                            {st?.phase === 'sent' && (
                                <p role="status" data-testid={`sent-${o.code}`} style={{ color: '#2e7d32' }}>
                                    {st.message}{st.txHash ? ` (giao dịch ${shortHash(st.txHash)})` : ''}
                                </p>
                            )}
                            {st?.phase === 'error' && <p role="alert" style={{ color: '#c0392b' }}>{st.message}</p>}

                            {o.status === SHIPPER_STATUS.LOCKED && (
                                <div style={{ marginTop: 10 }}>
                                    {st?.phase === 'confirm' ? (
                                        <>
                                            <span style={{ marginRight: 10 }}>Bạn đã giao hàng thành công cho người nhận?</span>
                                            <button type="button" style={btn} onClick={() => deliver(o.code)}>Đúng, xác nhận</button>{' '}
                                            <button type="button" style={btnGhost} onClick={() => setPhase(o.code, undefined)}>Chưa</button>
                                        </>
                                    ) : (
                                        <button type="button" style={btn} disabled={!canDeliver(o, st)}
                                            onClick={() => setPhase(o.code, { phase: 'confirm' })}>
                                            {st?.phase === 'sending' ? 'Đang gửi lên blockchain…'
                                                : st?.phase === 'sent' ? 'Đang chờ hệ thống ghi nhận…'
                                                    : 'Xác nhận phát hàng thành công'}
                                        </button>
                                    )}
                                </div>
                            )}
                        </section>
                    );
                })}
            </main>
        </div>
    );
}
