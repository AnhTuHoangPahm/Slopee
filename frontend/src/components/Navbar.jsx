import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { fetchCartAPI } from '../api/carts';
import '../assets/navbar.css';

export default function Navbar() {
    const navigate = useNavigate();
    const user = JSON.parse(localStorage.getItem('user'));
    const [searchTerm, setSearchTerm] = useState('');

    // Cart Hover State
    const [cartItems, setCartItems] = useState([]);
    const [isCartHovered, setIsCartHovered] = useState(false);

    useEffect(() => {
        // Dynamically fetch fresh cart details the moment the user hovers over the icon
        if (user && isCartHovered) {
            fetchCartAPI(user.id).then(data => setCartItems(data.items || [])).catch(() => null);
        }
    }, [isCartHovered, user]);

    const handleSearchSubmit = (e) => {
        e.preventDefault();
        // Shift search queries globally into the URL so any page can execute a search and return home cleanly
        navigate(searchTerm ? `/?search=${encodeURIComponent(searchTerm)}` : '/');
    };

    const handleLogout = () => {
        localStorage.removeItem('user');
        navigate('/');
    };

    const resetHome = () => {
        setSearchTerm('');
    };

    return (
        <header className="slopee-navbar">
            <div className="nav-container">
                <Link to="/" className="nav-logo" onClick={resetHome}>
                    Slopee
                </Link>

                <form className="nav-search" onSubmit={handleSearchSubmit}>
                    <input
                        type="text"
                        placeholder="Search for items, brands and shops..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                    <button type="submit">🔍</button>
                </form>

                <div className="nav-links">
                    {user ? (
                        <>
                            <span>Hi, {user.name}</span>
                            <Link to="/play/tetris" className="nav-icon">Game</Link>
                            <Link to="/settings" className="nav-icon">⚙️ My Account</Link>

                            <div
                                style={{ position: 'relative' }}
                                onMouseEnter={() => setIsCartHovered(true)}
                                onMouseLeave={() => setIsCartHovered(false)}
                            >
                                <Link to="/cart" className="nav-icon">🛒 Cart</Link>

                                {/* CSS Popover Dropdown matching Shopee, utilizing a wrapper with padding to bridge the gap! */}
                                {isCartHovered && (
                                    <div style={{ position: 'absolute', top: '100%', right: '0', paddingTop: '15px', zIndex: 1000 }}>
                                        <div style={{ background: '#fff', color: '#333', width: '380px', boxShadow: '0 2px 10px rgba(0,0,0,0.1)', padding: '10px', borderRadius: '2px' }}>
                                            <div style={{ color: '#aaa', fontSize: '13px', marginBottom: '10px' }}>Recently Added Products</div>
                                            {cartItems.length === 0 ? (
                                                <div style={{ textAlign: 'center', padding: '20px', color: '#888' }}>Empty cart...</div>
                                            ) : (
                                                <div style={{ maxHeight: '250px', overflowY: 'auto' }}>
                                                    {cartItems.slice(0, 5).map(item => (
                                                        <div key={item.cartItemId} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                                                <div style={{ width: '40px', height: '40px', background: '#f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', color: '#999' }}>IMG</div>
                                                                <div style={{ fontSize: '12px', maxWidth: '200px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.name}</div>
                                                            </div>
                                                            <div style={{ color: '#ee4d2d', fontSize: '13px' }}>${item.unitPrice}</div>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px', paddingTop: '10px', borderTop: '1px solid #f2f2f2' }}>
                                                <span style={{ fontSize: '12px', color: '#888' }}>{cartItems.length} items total</span>
                                                <button onClick={() => navigate('/cart')} style={{ background: '#ee4d2d', color: '#fff', border: 'none', padding: '8px 15px', cursor: 'pointer', fontWeight: 'bold' }}>View My Shopping Cart</button>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {user.role === 'seller' && (
                                <Link to="/seller" className="nav-seller-btn">Manage Shop</Link>
                            )}

                            <button onClick={handleLogout} className="nav-logout">Log Out</button>
                        </>
                    ) : (
                        <>
                            <Link to="/signup">Sign Up</Link>
                            <Link to="/login">Log In</Link>
                        </>
                    )}
                </div>
            </div>
        </header>
    );
}
