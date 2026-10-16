import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { fetchCartAPI, updateCartItemAPI, removeCartItemAPI } from '../api/carts';
import '../assets/cart.css';
import { getUser } from '../api/http';
import { formatVND } from '../utils/formatVND';

export default function Cart() {
    const navigate = useNavigate();
    const user = getUser();

    const [items, setItems] = useState([]);
    const [selectedItems, setSelectedItems] = useState(new Set());
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!user) {
            navigate('/login');
            return;
        }
        loadCart();
    }, []);

    const loadCart = async () => {
        if (!user) return;
        try {
            const data = await fetchCartAPI();
            setItems(data.items || []);
        } catch (err) {
            console.error(err);
        }
        setLoading(false);
    };

    const handleUpdateQty = async (item, newQty) => {
        // Enforce user's 0-quantity prompt requirement
        if (newQty <= 0) {
            if (window.confirm(`Do you want to remove ${item.name} from your cart?`)) {
                await removeCartItemAPI(item.cartItemId);
                setSelectedItems(prev => {
                    const next = new Set(prev);
                    next.delete(item.cartItemId);
                    return next;
                });
                loadCart();
            } else {
                // Restore to 1 implicitly by doing nothing (since input defaults to 1 when blocked)
                return;
            }
            return;
        }

        if (newQty > item.inStock) {
            alert(`Limit reached.`);
            return;
        }

        // OPTIMISTIC UPDATE: Update UI instantly using the cached inStock parameters!
        setItems(prevItems => prevItems.map(i =>
            i.cartItemId === item.cartItemId ? { ...i, quantity: newQty } : i
        ));

        try {
            await updateCartItemAPI(item.cartItemId, newQty);
            // We intentionally do NOT call loadCart() here, which drastically speeds up the UX!
        } catch (err) {
            alert(err.message);
            loadCart(); // Rollback if backend constraint failed wildly
        }
    };

    const handleDelete = async (itemId) => {
        const confirmDelete = window.confirm("Do you want to remove this item from your cart?");
        if (confirmDelete) {
            try {
                await removeCartItemAPI(itemId);
                setSelectedItems(prev => {
                    const next = new Set(prev);
                    next.delete(itemId);
                    return next;
                });
                loadCart();
            } catch (err) { alert(err.message); }
        }
    }

    const handleSelectAll = (e) => {
        if (e.target.checked) {
            const allId = items.map(i => i.cartItemId);
            setSelectedItems(new Set(allId));
        } else {
            setSelectedItems(new Set());
        }
    };

    const toggleSelectItem = (itemId) => {
        setSelectedItems(prev => {
            const next = new Set(prev);
            if (next.has(itemId)) next.delete(itemId);
            else next.add(itemId);
            return next;
        });
    };

    const calculateTotal = () => {
        return items.reduce((sum, item) => {
            if (selectedItems.has(item.cartItemId)) {
                return sum + (item.unitPrice * item.quantity);
            }
            return sum;
        }, 0);
    };

    if (loading) return <div className="cart-layout"><Navbar /><div style={{ textAlign: 'center', marginTop: '50px' }}>Loading...</div></div>;

    return (
        <div className="cart-layout">
            <Navbar />
            <div className="cart-wrapper">
                <div className="cart-header-title">
                    <span style={{ fontSize: '30px' }}>🛒</span> My Cart
                </div>

                <div className="cart-table-header">
                    <div>
                        <input
                            type="checkbox"
                            checked={items.length > 0 && selectedItems.size === items.length}
                            onChange={handleSelectAll}
                        />
                    </div>
                    <div>Details</div>
                    <div style={{ textAlign: 'center' }}>Unit Price</div>
                    <div style={{ textAlign: 'center' }}>Quantity</div>
                    <div style={{ textAlign: 'center' }}>Total</div>
                    <div style={{ textAlign: 'center' }}>Action</div>
                </div>

                {items.length === 0 ? (
                    <div style={{ background: '#fff', padding: '80px', textAlign: 'center', color: '#888', fontSize: '18px' }}>
                        Your shopping cart is currently empty. Feel like browsing at Home page?
                    </div>
                ) : (
                    items.map(it => (
                        <div key={it.cartItemId} className="cart-item-row">
                            <div>
                                <input
                                    type="checkbox"
                                    checked={selectedItems.has(it.cartItemId)}
                                    onChange={() => toggleSelectItem(it.cartItemId)}
                                />
                            </div>
                            <div className="cart-item-product">
                                <div className="cart-img-placeholder">THUMBNAIL</div>
                                <div>
                                    <div style={{ fontWeight: '500' }}>{it.name}</div>
                                    <div style={{ fontSize: '12px', color: '#888', marginTop: '5px' }}>Shop: {it.shopName}</div>
                                    {it.selectedVariants && Object.keys(it.selectedVariants).length > 0 && (
                                        <div style={{ fontSize: '12px', color: '#ee4d2d', marginTop: '3px', fontWeight: '500' }}>
                                            Variant: {Object.entries(it.selectedVariants).map(([k, v]) => `${k}: ${v}`).join(', ')}
                                        </div>
                                    )}
                                </div>
                            </div>
                            <div style={{ textAlign: 'center' }}>{formatVND(it.unitPrice)}</div>
                            <div style={{ display: 'flex', justifyContent: 'center' }}>
                                <div className="cart-qty-controls">
                                    <button className="cart-qty-btn" onClick={() => handleUpdateQty(it, it.quantity - 1)}>-</button>
                                    <input className="cart-qty-input" type="text" readOnly value={it.quantity} />
                                    {/* Greys out native increment if strict stock boundary hits */}
                                    <button className="cart-qty-btn"
                                        onClick={() => handleUpdateQty(it, it.quantity + 1)}
                                        disabled={it.quantity >= it.inStock}
                                        title={it.quantity >= it.inStock ? "Maximum Stock Threshold Reached" : ""}
                                    >+</button>
                                </div>
                                {it.quantity >= it.inStock && <div style={{ color: 'red', fontSize: '10px', marginLeft: '5px', marginTop: '10px' }}>Max Limit</div>}
                            </div>
                            <div style={{ color: '#ee4d2d', textAlign: 'center', fontWeight: 'bold' }}>{formatVND(it.unitPrice * it.quantity)}</div>
                            <div style={{ textAlign: 'center' }}>
                                <button onClick={() => handleDelete(it.cartItemId)} style={{ background: 'transparent', border: 'none', color: '#333', cursor: 'pointer', padding: '5px' }}>Delete</button>
                            </div>
                        </div>
                    ))
                )}

                {items.length > 0 && (
                    <div className="cart-bottom-bar">
                        <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
                            <label style={{ cursor: 'pointer' }}>
                                <input
                                    type="checkbox"
                                    checked={items.length > 0 && selectedItems.size === items.length}
                                    onChange={handleSelectAll}
                                />
                                <span style={{ marginLeft: '8px' }}>Select All ({items.length})</span>
                            </label>

                        </div>
                        <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
                            <div>
                                Selected Gross ({selectedItems.size} items): <span style={{ color: '#ee4d2d', fontSize: '24px', fontWeight: '500', marginLeft: '10px' }}>{formatVND(calculateTotal())}</span>
                            </div>
                            <button
                                className="cart-checkout-btn"
                                onClick={() => {
                                    if (selectedItems.size === 0) return alert('Select at least one item to checkout');
                                    const selectedPayload = items.filter(it => selectedItems.has(it.cartItemId));
                                    navigate('/checkout', { state: { items: selectedPayload } });
                                }}
                            >
                                Proceed to checkout
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
