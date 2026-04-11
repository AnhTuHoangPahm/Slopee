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

    const handleAddToCart = async (e, p) => {
        e.stopPropagation(); 
        if (!user) {
            // Forward cart intent dynamically through URL state
            navigate('/login', { state: { pendingCartItem: p.id } });
            return;
        }
        try {
            await addToCartAPI(user.id, p.id, 1);
            showToast(`✅ Successfully embedded into Cart: ${p.name}`);
        } catch (err) {
            showToast(`❌ Cannot Add: ${err.message}`, true);
        }
    };

    useEffect(() => {
        // Any time the URL's "?search=" parameter shifts, trigger a fast backend lookup
        loadProducts(dynamicSearchTerm);
    }, [dynamicSearchTerm]);

    return (
        <div style={{ backgroundColor: '#f5f5f5', minHeight: '100vh', fontFamily: 'Inter, sans-serif' }}>
            <Navbar />
            
            {/* Custom Stackable Toast Overlay Container */}
            <div style={{position: 'fixed', top: '80px', right: '30px', zIndex: 9999, display: 'flex', flexDirection: 'column', gap: '10px', pointerEvents: 'none'}}>
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
                
                {loading ? (
                    <h2 style={{ textAlign:'center', marginTop: '50px', color: '#ee4d2d' }}>Loading Slopee Catalog...</h2>
                ) : (
                    <div className="product-grid">
                        {products.map(p => (
                            <div key={p.id} className="product-card">
                                <div className="product-image-container">
                                    {p.primaryImage ? (
                                        <img src={p.primaryImage} alt={p.name} style={{width:'100%', height:'100%', objectFit:'cover'}} />
                                    ) : (
                                        <div className="product-placeholder">No IMG</div>
                                    )}
                                </div>
                                <div className="product-info">
                                    <h4 className="product-title">{p.name}</h4>
                                    <div className="product-price">${p.unitPrice}</div>
                                    <div className="product-meta">
                                        Sold by {p.shopName}
                                    </div>
                                    <div style={{marginTop: '10px'}}>
                                        <button 
                                            onClick={(e) => handleAddToCart(e, p)} 
                                            style={{background: '#fff', border:'1px solid #ee4d2d', color:'#ee4d2d', padding:'6px', width:'100%', cursor:'pointer', display:'flex', justifyContent:'center', alignItems:'center', gap:'5px', borderRadius: '2px', fontWeight: '500'}}
                                            onMouseOver={(e) => { e.target.style.background = '#ee4d2d'; e.target.style.color = '#fff'; }}
                                            onMouseOut={(e) => { e.target.style.background = '#fff'; e.target.style.color = '#ee4d2d'; }}
                                        >
                                            🛒 Add to Cart
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                        {products.length === 0 && <h3 style={{color: '#555', textAlign: 'center', gridColumn: '1 / -1'}}>No products found matching your search.</h3>}
                    </div>
                )}
            </div>
        </div>
    );
}
