import React, { useState, useEffect } from 'react';
import { fetchOrdersAPI, updateOrderStatusAPI } from '../api/payments';
import Navbar from '../components/Navbar';
import Web3OrderPanel from '../components/Web3OrderPanel';
import { getUser } from '../api/http';
import { formatVND } from '../utils/formatVND';
import { groupOrders } from '../lib/groupOrders';

// `escrowFactory`, `fetchStatus`, `saveNote` chỉ để test thay thế ví/API (giống Web3CheckoutPanel).
export default function MyOrders({ hideNavbar = false, escrowFactory, fetchStatus, saveNote, pollMs }) {
    const user = getUser();
    const [orders, setOrders] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (user) {
            fetchOrdersAPI()
                .then(data => setOrders(data.orders))
                .catch(console.error)
                .finally(() => setLoading(false));
        } else {
            setLoading(false);
        }
    }, [user?.id]);

    const handleStatusChange = async (orderId, status) => {
        if (!window.confirm(`Are you sure you want to mark this order as '${status.toUpperCase()}'?`)) return;
        try {
            await updateOrderStatusAPI(orderId, status);
            // Refresh
            const data = await fetchOrdersAPI();
            setOrders(data.orders);
        } catch (err) {
            alert(err.message);
        }
    };

    if (!user) return <div style={{ padding: '20px' }}>Please log in.</div>;

    const renderOrder = (o) => (
        <div key={o.orderId} data-testid="order-card" data-web3={o.web3 ? 'true' : 'false'} style={{ background: '#fff', padding: '20px', borderRadius: '4px', marginBottom: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #eee', paddingBottom: '10px', marginBottom: '10px', alignItems: 'center' }}>
                <span style={{ color: '#888', fontSize: '13px' }}>Order Hash: {o.orderId} <br /> Date: {new Date(o.created_at).toLocaleString()}</span>
                {/* Đơn Web3: trạng thái thật do Indexer ghi nên hiện ở khung Web3 bên dưới; nút cũ bị khóa (WEB3_ORDER_MANAGED) */}
                {!o.web3 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                        <span style={{ color: o.status === 'cancelled' ? '#d32f2f' : '#26aa99', textTransform: 'uppercase', fontSize: '16px', fontWeight: 'bold' }}>{o.status}</span>
                        {o.status === 'paid' && (
                            <div style={{ display: 'flex', gap: '10px' }}>
                                <button onClick={() => handleStatusChange(o.orderId, 'received')} style={{ background: '#4caf50', color: '#fff', padding: '6px 12px', border: 'none', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold' }}>✔ Mark Received</button>
                                <button onClick={() => handleStatusChange(o.orderId, 'cancelled')} style={{ background: '#fff', color: '#d32f2f', border: '1px solid #d32f2f', padding: '6px 12px', borderRadius: '3px', cursor: 'pointer' }}>Cancel Order</button>
                            </div>
                        )}
                    </div>
                )}
            </div>
            {o.items.map((it, idx) => (
                <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '15px' }}>
                    <div style={{ display: 'flex', gap: '15px' }}>
                        <div style={{ width: '60px', height: '60px', background: '#f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', color: '#999' }}>IMG</div>
                        <div>
                            <strong style={{ fontSize: '16px' }}>{it.productName}</strong> <br />
                            <span style={{ fontSize: '13px', color: '#666' }}>Ordered: x{it.quantity} | Fulfilled by {it.shopName}</span>
                            {it.selectedVariants && Object.keys(it.selectedVariants).length > 0 && (
                                <div style={{ fontSize: '12px', color: '#ee4d2d', marginTop: '3px', fontWeight: '500' }}>
                                    Variant: {Object.entries(it.selectedVariants).map(([k, v]) => `${k}: ${v}`).join(', ')}
                                </div>
                            )}
                        </div>
                    </div>
                    <div style={{ color: '#ee4d2d', fontWeight: '500' }}>{formatVND(it.unitPrice * it.quantity)}</div>
                </div>
            ))}
            <div style={{ textAlign: 'right', borderTop: '1px solid #eee', paddingTop: '15px', marginTop: '10px' }}>
                Settled Payment Amount: <strong style={{ color: '#ee4d2d', fontSize: '24px', marginLeft: '10px' }}>{formatVND(o.totalAmount)}</strong>
            </div>
            {o.web3 && <Web3OrderPanel orderCode={o.orderId} web3={o.web3} escrowFactory={escrowFactory} fetchStatus={fetchStatus} saveNote={saveNote} pollMs={pollMs} />}
        </div>
    );

    return (
        <div style={{ width: '100%', fontFamily: 'Inter, sans-serif' }}>
            {!hideNavbar && <Navbar />}

            <div style={{ padding: '20px' }}>
                <h2 style={{ color: '#ee4d2d', marginTop: '0' }}>Past Purchases</h2>

                {loading ? (
                    <div style={{ textAlign: 'center', marginTop: '50px' }}>Fetching...</div>
                ) : orders.length === 0 ? (
                    <div style={{ background: '#fff', padding: '80px', textAlign: 'center', color: '#888', borderRadius: '4px' }}>
                        You have not made any purchases yet! Start shopping.
                    </div>
                ) : (
                    groupOrders(orders).map(group => (
                        group.orders.length > 1 ? (
                            <section key={group.key} data-testid="order-group" aria-label="Lô thanh toán" style={{ border: '1px solid #f1c6bd', background: '#fff8f6', borderRadius: '6px', padding: '12px 12px 0', marginBottom: '20px' }}>
                                <div style={{ color: '#ee4d2d', fontWeight: 'bold', marginBottom: '10px' }}>
                                    Lô thanh toán · {group.orders.length} cửa hàng · mỗi đơn được xử lý độc lập
                                </div>
                                {group.orders.map(renderOrder)}
                            </section>
                        ) : renderOrder(group.orders[0])
                    ))
                )}
            </div>
        </div>
    );
}
