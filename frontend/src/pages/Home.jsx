import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { fetchProductsAPI } from '../api/products';
import { addToCartAPI } from '../api/carts';
import Navbar from '../components/Navbar';
import '../assets/home.css';

export default function Home() {
    const [products, setProducts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [searchMetrics, setSearchMetrics] = useState(null);
    const [searchParams] = useSearchParams();

    // Pull the active search term directly from the URL dynamically
    const dynamicSearchTerm = searchParams.get('search') || '';

    const loadProducts = async (term = '') => {
        setLoading(true);
        try {
            const data = await fetchProductsAPI(term);
            setProducts(data.items);
            setSearchMetrics(data.time_taken_sec);
        } catch (err) {
            console.error(err);
        }
        setLoading(false);
    };

    const navigate = useNavigate();
    const user = JSON.parse(localStorage.getItem('user'));

    const [toasts, setToasts] = useState([]);

    const showToast = (msg, isError = false) => {
        const id = Date.now() + Math.random();
        setToasts(prev => [...prev, { id, msg, isError }]);
        setTimeout(() => {
            setToasts(prev => prev.filter(t => t.id !== id));
        }, 3000);
    };

    useEffect(() => {
        // Any time the URL's "?search=" parameter shifts, trigger a fast backend lookup
        loadProducts(dynamicSearchTerm);
    }, [dynamicSearchTerm]);

    return (
        <div style={{ backgroundColor: '#f5f5f5', minHeight: '100vh', fontFamily: 'Inter, sans-serif' }}>
            <Navbar />

            {/* Custom Stackable Toast Overlay Container */}
            <div style={{ position: 'fixed', top: '80px', right: '30px', zIndex: 9999, display: 'flex', flexDirection: 'column', gap: '10px', pointerEvents: 'none' }}>
                {toasts.map(t => (
                    <div key={t.id} style={{
                        background: t.isError ? '#d32f2f' : '#333',
                        color: '#fff',
                        padding: '16px 24px',
                        borderRadius: '4px',
                        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                        fontSize: '14px',
                        transition: 'opacity 0.3s ease-in-out'
                    }}>
                        {t.msg}
                    </div>
                ))}
            </div>

            <div className="home-container">
                {searchMetrics !== null && (
                    <div className="search-metrics">
                        Query processed in <strong>{searchMetrics}s</strong>. ({products.length} items found)
                    </div>
                )}

                {dynamicSearchTerm && [...new Set(products.map(p => p.shopName))].length === 1 && [...new Set(products.map(p => p.shopName))][0].toLowerCase().includes(dynamicSearchTerm.toLowerCase()) && (
                    <div style={{ background: 'linear-gradient(90deg, #f53d2d, #ff6633)', color: '#fff', padding: '40px 30px', borderRadius: '4px', marginBottom: '30px', display: 'flex', alignItems: 'center', gap: '25px', boxShadow: '0 4px 15px rgba(238, 77, 45, 0.2)' }}>
                        <div style={{ width: '80px', height: '80px', borderRadius: '50%', background: '#fff', color: '#ee4d2d', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '36px', fontWeight: 'bold', boxShadow: '0 2px 10px rgba(0,0,0,0.1)' }}>🏪</div>
                        <div>
                            <h2 style={{ margin: '0 0 8px 0', fontSize: '32px', letterSpacing: '0.5px' }}>{products[0].shopName}</h2>
                            <div style={{ opacity: 0.95, fontSize: '16px' }}>Welcome to {products[0].shopName}.</div>
                        </div>
                    </div>
                )}

                {loading ? (
                    <h2 style={{ textAlign: 'center', marginTop: '50px', color: '#ee4d2d' }}>Loading...</h2>
                ) : (
                    <div className="product-grid">
                        {products.map(p => (
                            <div key={p.id} className="product-card" onClick={() => navigate(`/product/${p.id}`)} style={{ cursor: 'pointer' }}>
                                <div className="product-image-container">
                                    {p.primaryImage ? (
                                        <img src={p.primaryImage} alt={p.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                    ) : (
                                        <div className="product-placeholder">No IMG</div>
                                    )}
                                </div>
                                <div className="product-info">
                                    <h4 className="product-title">{p.name}</h4>
                                    <div className="product-price">${p.unitPrice}</div>
                                    <div className="product-meta">
                                        <span style={{ color: '#ee4d2d', fontWeight: 'bold' }}>{p.averageRating > 0 ? `★ ${p.averageRating}` : 'No Ratings'}</span>
                                        <span>Sold by {p.shopName}</span>
                                    </div>
                                </div>
                            </div>
                        ))}
                        {products.length === 0 && <h3 style={{ color: '#555', textAlign: 'center', gridColumn: '1 / -1' }}>No products found. Try rephrasing your search, or search for something else.</h3>}
                    </div>
                )}
            </div>
        </div>
    );
}
