import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { fetchPaymentMethodsAPI, addPaymentMethodAPI, checkoutAPI } from '../api/payments';

export default function Checkout() {
    const location = useLocation();
    const navigate = useNavigate();
    const user = JSON.parse(localStorage.getItem('user'));

    // Items passed directly from Cart via Router state extraction securely
    const checkoutItems = location.state?.items || [];

    const [methods, setMethods] = useState([]);
    const [selectedMethodId, setSelectedMethodId] = useState('');
    const [passPhrase, setPassPhrase] = useState('');
    const [loading, setLoading] = useState(false);

    // Add Method Form State
    const [showAddForm, setShowAddForm] = useState(false);
    const [newMethodName, setNewMethodName] = useState('');

    useEffect(() => {
        if (!user || checkoutItems.length === 0) {
            navigate('/cart');
            return;
        }
        loadMethods();
    }, []);

    const loadMethods = async () => {
        try {
            const data = await fetchPaymentMethodsAPI(user.id);
            setMethods(data.methods);
            if (data.methods.length > 0 && !selectedMethodId) setSelectedMethodId(data.methods[0].id);
        } catch (err) { console.error(err); }
    };

    const handleAddMethod = async (e) => {
        e.preventDefault();
        try {
            await addPaymentMethodAPI({
                userId: user.id,
                methodType: 'bank',
                providerName: newMethodName,
                accountNumber: 'xxxx-' + Math.floor(1000 + Math.random() * 9000)
            });
            setShowAddForm(false);
            setNewMethodName('');
            loadMethods();
            alert("Bank Account successfully linked! You have $10,000 in your account.");
        } catch (err) { alert(err.message); }
    };

    const handleCheckout = async () => {
        if (!selectedMethodId) return alert("Select a valid payment method.");
        if (passPhrase.length !== 6) return alert("You must enter your 6-digit passphrase.");

        setLoading(true);
        try {
            const ids = checkoutItems.map(i => i.cartItemId);
            await checkoutAPI({
                userId: user.id,
                paymentMethodId: selectedMethodId,
                passPhrase: passPhrase,
                cartItemIds: ids
            });
            alert("Transaction successful.");
            navigate('/orders'); // Route to newly requested My Orders panel!
        } catch (err) {
            alert("Transaction Denied: " + err.message);
        }
        setLoading(false);
    };

    const totalSum = checkoutItems.reduce((acc, i) => acc + (i.unitPrice * i.quantity), 0);

    return (
        <div style={{ background: '#f5f5f5', minHeight: '100vh', fontFamily: 'Inter, sans-serif' }}>
            <Navbar />
            <div style={{ maxWidth: '900px', margin: '40px auto', padding: '0 20px' }}>
                <h2 style={{ color: '#ee4d2d' }}>Secure Checkout Hub</h2>

                {/* Items Box */}
                <div style={{ background: '#fff', padding: '20px', borderRadius: '4px', marginBottom: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                    <h3>Order Ledger</h3>
                    {checkoutItems.map(it => (
                        <div key={it.productId} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid #f2f2f2' }}>
                            <div>
                                <strong style={{ display: 'block' }}>{it.name}</strong>
                                <span style={{ fontSize: '12px', color: '#888' }}>Requested Quantity: {it.quantity} | Fulfillment Shop: {it.shopName}</span>
                            </div>
                            <div style={{ color: '#ee4d2d', fontWeight: '500' }}>
                                ${(it.unitPrice * it.quantity).toFixed(2)}
                            </div>
                        </div>
                    ))}
                    <div style={{ textAlign: 'right', marginTop: '20px', fontSize: '18px' }}>
                        Gross Cost Assessment: <span style={{ color: '#ee4d2d', fontWeight: 'bold' }}>${totalSum.toFixed(2)}</span>
                    </div>
                </div>

                {/* Payment Methods Box */}
                <div style={{ background: '#fff', padding: '20px', borderRadius: '4px', marginBottom: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
                        <h3 style={{ margin: 0 }}>Financial Routing Platform</h3>
                        <button onClick={() => setShowAddForm(!showAddForm)} style={{ background: '#fff', border: '1px solid #ee4d2d', color: '#ee4d2d', padding: '8px 12px', cursor: 'pointer', borderRadius: '2px', fontWeight: '500' }}>+ Link New Bank Account</button>
                    </div>

                    {showAddForm && (
                        <form onSubmit={handleAddMethod} style={{ background: '#fcfcfc', padding: '15px', marginTop: '15px', border: '1px solid #e8e8e8', display: 'flex', gap: '10px', alignItems: 'center' }}>
                            <input required placeholder="E.g., Virtual Chase Bank, Stripe, etc." value={newMethodName} onChange={e => setNewMethodName(e.target.value)} style={{ padding: '10px', flex: 1 }} />
                            <button type="submit" style={{ background: '#ee4d2d', color: '#fff', border: 'none', padding: '10px 20px', cursor: 'pointer', fontWeight: '500' }}>Authenticate Link</button>
                        </form>
                    )}

                    <div style={{ marginTop: '20px' }}>
                        {methods.length === 0 && (
                            <div style={{ color: '#888', fontStyle: 'italic', padding: '10px' }}>No bank accounts detected. You can link one above, or simply select Cash on Delivery.</div>
                        )}
                        {methods.map(m => (
                            <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: '15px', padding: '15px', border: selectedMethodId === m.id ? '2px solid #ee4d2d' : '1px solid #ddd', borderRadius: '4px', marginBottom: '10px', cursor: 'pointer', transition: 'all 0.2s ease-in-out' }}>
                                <input type="radio" name="paymentMethod" checked={selectedMethodId === m.id} onChange={() => setSelectedMethodId(m.id)} style={{ transform: 'scale(1.2)' }} />
                                <div>
                                    <div style={{ fontWeight: '500', fontSize: '15px' }}>{m.providerName} (...{m.accountNumber.slice(-4)})</div>
                                    <div style={{ fontSize: '12px', color: m.balance >= totalSum ? '#4caf50' : '#d32f2f', marginTop: '2px' }}>
                                        Available Vault Balance: ${m.balance} {m.balance < totalSum && "(Insufficient Funds!)"}
                                    </div>
                                </div>
                            </label>
                        ))}

                        <label style={{ display: 'flex', alignItems: 'center', gap: '15px', padding: '15px', border: selectedMethodId === 'CASH_ON_DELIVERY' ? '2px solid #ee4d2d' : '1px solid #ddd', borderRadius: '4px', marginBottom: '10px', cursor: 'pointer', transition: 'all 0.2s ease-in-out' }}>
                            <input type="radio" name="paymentMethod" checked={selectedMethodId === 'CASH_ON_DELIVERY'} onChange={() => setSelectedMethodId('CASH_ON_DELIVERY')} style={{ transform: 'scale(1.2)' }} />
                            <div>
                                <div style={{ fontWeight: '500', fontSize: '15px' }}>💵 Cash on Delivery</div>
                                <div style={{ fontSize: '12px', color: '#4caf50', marginTop: '2px' }}>
                                    Pay physically when the items arrive at your doorstep.
                                </div>
                            </div>
                        </label>
                    </div>
                </div>

                {/* Final Passphrase Validation Box */}
                <div style={{ background: '#fff', padding: '20px', borderRadius: '4px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginBottom: '20px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                        <span style={{ color: '#555' }}>Authenticate 6-Digit Payment PIN:</span>
                        <input type="password" maxLength="6" placeholder="******" value={passPhrase} onChange={e => setPassPhrase(e.target.value)} style={{ padding: '10px', width: '120px', textAlign: 'center', fontSize: '20px', letterSpacing: '8px', border: '1px solid #ccc', borderRadius: '3px' }} />
                    </div>
                    <button
                        onClick={handleCheckout}
                        disabled={loading || !selectedMethodId || passPhrase.length !== 6}
                        style={{ background: loading || !selectedMethodId || passPhrase.length !== 6 ? '#ccc' : '#ee4d2d', color: '#fff', border: 'none', padding: '15px 40px', fontSize: '16px', fontWeight: 'bold', cursor: loading || !selectedMethodId || passPhrase.length !== 6 ? 'not-allowed' : 'pointer', borderRadius: '3px' }}
                    >
                        {loading ? "Decrypting Hash..." : "PROCESS SECURE PAYMENT"}
                    </button>
                </div>
            </div>
        </div>
    );
}
