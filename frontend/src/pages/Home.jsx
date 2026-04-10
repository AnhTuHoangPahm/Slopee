import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchProductsAPI } from '../api/products';
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

    useEffect(() => {
        // Any time the URL's "?search=" parameter shifts, trigger a fast backend lookup
        loadProducts(dynamicSearchTerm);
    }, [dynamicSearchTerm]);

    return (
        <div style={{ backgroundColor: '#f5f5f5', minHeight: '100vh', fontFamily: 'Arial, sans-serif' }}>
            <Navbar />
            
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
                                    <div className="product-placeholder">Product Image</div>
                                </div>
                                <div className="product-info">
                                    <h4 className="product-title">{p.name}</h4>
                                    <div className="product-price">${p.unitPrice}</div>
                                    <div className="product-meta">
                                        Sold by {p.shopName}
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
