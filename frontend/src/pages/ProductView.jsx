import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { fetchProductDetailsAPI, fetchProductReviewsAPI, publishProductReviewAPI } from '../api/products';
import { addToCartAPI } from '../api/carts';
import Navbar from '../components/Navbar';

export default function ProductView() {
    const { id } = useParams();
    const navigate = useNavigate();
    const user = JSON.parse(localStorage.getItem('user'));

    const [product, setProduct] = useState(null);
    const [loading, setLoading] = useState(true);
    const [selectedVariant, setSelectedVariant] = useState(null);
    
    const [activeImage, setActiveImage] = useState('');

    // --- Reviews State ---
    const [reviews, setReviews] = useState([]);
    const [stats, setStats] = useState({ average: 0, total: 0 });
    const [reviewPage, setReviewPage] = useState(0);
    const [hasMoreReviews, setHasMoreReviews] = useState(true);
    
    const [reviewLoading, setReviewLoading] = useState(false);

    // --- Write Review State ---
    const [writeRating, setWriteRating] = useState(5);
    const [writeComment, setWriteComment] = useState('');
    const [writeError, setWriteError] = useState('');

    const loadCoreData = async () => {
        try {
            const data = await fetchProductDetailsAPI(id);
            setProduct(data.product);
            
            // Fallback for primary image
            const primary = data.product.images?.find(i => i.isPrimary) || data.product.images?.[0];
            if (primary) setActiveImage(primary.imageUrl);

        } catch (err) {
            console.error(err);
        }
        setLoading(false);
    };

    const loadReviewsBatch = async (page) => {
        setReviewLoading(true);
        try {
            const res = await fetchProductReviewsAPI(id, page * 5, 5);
            setReviews(prev => {
                // Ensure no duplicates in strict mode
                const existingIds = new Set(prev.map(r => r.id));
                const newReviews = res.reviews.filter(r => !existingIds.has(r.id));
                return [...prev, ...newReviews];
            });
            setStats(res.stats);
            if (res.reviews.length < 5) setHasMoreReviews(false);
        } catch (err) { }
        setReviewLoading(false);
    };

    useEffect(() => {
        loadCoreData();
    }, [id]);

    useEffect(() => {
        loadReviewsBatch(reviewPage);
    }, [reviewPage, id]);

    // INFINITE SCROLL OBSERVER PATTERN
    const observer = useRef();
    const lastReviewElementRef = useCallback(node => {
        if (reviewLoading) return;
        if (observer.current) observer.current.disconnect();
        observer.current = new IntersectionObserver(entries => {
            if (entries[0].isIntersecting && hasMoreReviews) {
                setReviewPage(prev => prev + 1);
            }
        });
        if (node) observer.current.observe(node);
    }, [reviewLoading, hasMoreReviews]);


    const handleAddToCart = async () => {
        if (!user) {
            navigate('/login');
            return;
        }
        // Force variant selection mathematically if they exist
        if (product.variants?.length > 0 && !selectedVariant) {
            alert("Please explicitly select a Variation before adding to cart!");
            return;
        }

        try {
            await addToCartAPI(user.id, product.id, 1, selectedVariant?.id);
            alert("Successfully appended to Cart!");
        } catch (err) {
            alert("Failed to add to cart: " + err.message);
        }
    };

    const handlePublishReview = async (e) => {
        e.preventDefault();
        try {
            setWriteError('');
            await publishProductReviewAPI(product.id, {
                userId: user.id,
                rating: writeRating,
                comment: writeComment,
                images: [] // Future extension: uploading actual blobs to S3
            });
            alert("Review successfully established!");
            
            // Hot reload reviews
            setReviewPage(0);
            setReviews([]);
            setHasMoreReviews(true);
            setWriteComment('');
        } catch (err) {
            setWriteError(err.message);
        }
    }


    if (loading) return <div style={{padding: '50px', textAlign:'center'}}><Navbar />Loading Product Architecture...</div>;
    if (!product) return <div style={{padding: '50px', textAlign:'center'}}><Navbar /><h2 style={{color: 'red'}}>Product not found or suspended.</h2></div>;

    const hasVariants = product.variants && product.variants.length > 0;

    return (
        <div style={{ backgroundColor: '#f5f5f5', minHeight: '100vh', fontFamily: 'Inter, sans-serif' }}>
            <Navbar />
            
            <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '20px' }}>
                
                {/* 1. THE FOLD: MEDIA & CONTEXT SPLIT */}
                <div style={{ display: 'flex', gap: '30px', background: '#fff', padding: '30px', borderRadius: '4px', boxShadow: '0 2px 10px rgba(0,0,0,0.05)' }}>
                    
                    {/* LEFT HALF: MEDIA */}
                    <div style={{ flex: '1', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        <div style={{ width: '100%', aspectRatio: '1/1', background: '#f9f9f9', border: '1px solid #eee' }}>
                            {activeImage ? (
                                <img src={activeImage} alt={product.name} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                            ) : (
                                <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#ccc' }}>No Image Included</div>
                            )}
                        </div>
                        {/* Thumbnail Carousel */}
                        <div style={{ display: 'flex', gap: '10px', overflowX: 'auto', paddingBottom: '5px' }}>
                            {product.images?.map(img => (
                                <img 
                                    key={img.id} 
                                    src={img.imageUrl} 
                                    onClick={() => setActiveImage(img.imageUrl)}
                                    style={{ 
                                        width: '80px', height: '80px', objectFit: 'cover', cursor: 'pointer',
                                        border: activeImage === img.imageUrl ? '2px solid #ee4d2d' : '1px solid #ddd' 
                                    }} 
                                />
                            ))}
                        </div>
                    </div>

                    {/* RIGHT HALF: BUSINESS ACTION */}
                    <div style={{ flex: '1.2', display: 'flex', flexDirection: 'column' }}>
                        <h1 style={{ fontSize: '24px', margin: '0 0 10px 0', color: '#111' }}>{product.name}</h1>
                        
                        <div style={{ display: 'flex', gap: '15px', alignItems: 'center', fontSize: '14px', marginBottom: '20px' }}>
                            <span style={{ color: '#ee4d2d', fontWeight: 'bold' }}>★ {stats.average.toFixed(1)}</span>
                            <span style={{ color: '#777' }}>|</span>
                            <span style={{ color: '#333' }}>{stats.total} Ratings</span>
                            <span style={{ color: '#777' }}>|</span>
                            <span style={{ color: '#333', background: '#e3f2fd', color: '#1565c0', padding: '2px 8px', borderRadius: '12px' }}>{product.categoryName}</span>
                        </div>

                        <div style={{ background: '#fafafa', padding: '20px', display: 'flex', alignItems: 'center', marginBottom: '25px', borderRadius:'2px' }}>
                            <span style={{ fontSize: '32px', color: '#ee4d2d', fontWeight: 'bold', marginRight: '15px' }}>${product.unitPrice}</span>
                        </div>

                        {/* Variants Logic */}
                        {hasVariants && (
                            <div style={{ marginBottom: '30px' }}>
                                <label style={{ display: 'block', marginBottom: '10px', color: '#555', fontSize: '14px' }}><strong>AVAILABLE CONFIGURATIONS</strong></label>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                                    {product.variants.map(v => (
                                        <button 
                                            key={v.id} 
                                            onClick={() => setSelectedVariant(v)}
                                            style={{
                                                padding: '8px 16px', background: '#fff', cursor: 'pointer', borderRadius: '4px',
                                                border: selectedVariant?.id === v.id ? '2px solid #ee4d2d' : '1px solid #cbd5e1',
                                                color: selectedVariant?.id === v.id ? '#ee4d2d' : '#333',
                                                fontWeight: selectedVariant?.id === v.id ? 'bold' : 'normal'
                                            }}
                                        >
                                            {v.variantName}: {v.variantValue}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div style={{ marginTop: 'auto', display: 'flex', gap: '20px', alignItems: 'center' }}>
                            <button 
                                onClick={handleAddToCart}
                                style={{ 
                                    background: '#ffeee8', color: '#ee4d2d', border: '1px solid #ee4d2d',
                                    padding: '16px 32px', fontSize: '16px', fontWeight: 'bold', cursor: 'pointer', flex: 1
                                }}
                            >
                                🛒 Add To Cart
                            </button>
                            <span style={{color: '#666', fontSize:'14px'}}>{product.inStock} pieces available</span>
                        </div>
                    </div>
                </div>

                {/* 2. THE HOOK: SHOP INTERLOCK */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#fff', padding: '25px', borderRadius: '4px', margin: '20px 0', boxShadow: '0 1px 5px rgba(0,0,0,0.05)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                        <div style={{ width: '60px', height: '60px', borderRadius: '50%', background: '#eee', overflow: 'hidden' }}>
                            {product.shopAvatarUrl ? <img src={product.shopAvatarUrl} style={{width:'100%', height:'100%', objectFit:'cover'}} /> : <div style={{textAlign:'center', lineHeight:'60px'}}>Shop</div>}
                        </div>
                        <div>
                            <div style={{ fontSize: '16px', fontWeight: 'bold' }}>{product.shopName}</div>
                            <div style={{ fontSize: '12px', color: '#666', marginTop: '4px' }}>Verified Slopee Merchant</div>
                        </div>
                    </div>
                    <div>
                        <button style={{ padding: '8px 20px', border: '1px solid #ccc', background: '#fff', cursor: 'pointer', marginRight: '10px' }}>💬 Chat Now</button>
                        <button onClick={() => navigate(`/?search=${encodeURIComponent(product.shopName)}`)} style={{ padding: '8px 20px', border: '1px solid #ccc', background: '#fafafa', cursor: 'pointer' }}>🏪 Go To Shop</button>
                    </div>
                </div>

                {/* 3. PRODUCT DESCRIPTION */}
                <div style={{ background: '#fff', padding: '30px', borderRadius: '4px', marginBottom: '20px' }}>
                    <h3 style={{ margin: '0 0 20px 0', background: '#fafafa', padding: '15px', color: '#333' }}>Product Specifications</h3>
                    <p style={{ whiteSpace: 'pre-wrap', color: '#444', lineHeight: '1.6' }}>
                        {product.description || "No specific details provided by the seller."}
                    </p>
                </div>

                {/* 4. THE FEEDBACK ENGINE */}
                <div style={{ background: '#fff', padding: '30px', borderRadius: '4px' }}>
                    <h3 style={{ margin: '0 0 20px 0' }}>Product Ratings ({stats.total})</h3>
                    
                    {user && (
                        <div style={{ background: '#f5f5f5', padding: '20px', borderRadius: '4px', marginBottom: '30px' }}>
                            <h4 style={{margin: '0 0 10px 0'}}>Had this product delivered? Leave a verified review!</h4>
                            <form onSubmit={handlePublishReview} style={{display: 'flex', flexDirection: 'column', gap: '15px'}}>
                                <select value={writeRating} onChange={e=>setWriteRating(Number(e.target.value))} style={{padding: '10px', width: '150px'}}>
                                    <option value={5}>⭐⭐⭐⭐⭐ (5/5)</option>
                                    <option value={4}>⭐⭐⭐⭐ (4/5)</option>
                                    <option value={3}>⭐⭐⭐ (3/5)</option>
                                    <option value={2}>⭐⭐ (2/5)</option>
                                    <option value={1}>⭐ (1/5)</option>
                                </select>
                                <textarea 
                                    required
                                    placeholder="Write your truthful feedback regarding product quality..." 
                                    value={writeComment} 
                                    onChange={e=>setWriteComment(e.target.value)}
                                    style={{padding: '15px', height: '80px', fontFamily: 'inherit'}}
                                />
                                {writeError && <div style={{color: '#d32f2f'}}>{writeError}</div>}
                                <button type="submit" style={{width: '200px', padding: '10px', background: '#ee4d2d', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 'bold'}}>Publish Feedback</button>
                            </form>
                        </div>
                    )}

                    <div>
                        {reviews.length === 0 ? (
                            <p style={{color: '#777', fontStyle: 'italic'}}>No authorized reviews have been published for this item yet.</p>
                        ) : (
                            reviews.map((r, index) => {
                                const isLast = reviews.length === index + 1;
                                return (
                                    <div 
                                        key={r.id} 
                                        ref={isLast ? lastReviewElementRef : null}
                                        style={{ borderBottom: '1px solid #eee', padding: '20px 0', display: 'flex', gap: '20px' }}
                                    >
                                        <div style={{width: '40px', height: '40px', borderRadius: '50%', background: '#ccc', flexShrink: 0}} />
                                        <div style={{flex: 1}}>
                                            <div style={{fontSize: '13px', fontWeight: 'bold'}}>{r.userName}</div>
                                            <div style={{color: '#ee4d2d', fontSize: '12px', margin: '5px 0'}}>{'★'.repeat(r.rating)}{'☆'.repeat(5-r.rating)}</div>
                                            <div style={{fontSize: '11px', color: '#999'}}>{new Date(r.createdAt).toLocaleString()}</div>
                                            <p style={{marginTop: '10px', color: '#333', whiteSpace: 'pre-wrap'}}>{r.comment}</p>
                                            
                                            {Array.isArray(r.reviewImages) && r.reviewImages.map((img, i) => (
                                                <img key={i} src={img.url} alt="review auth" style={{width: '80px', height: '80px', objectFit: 'cover', border: '1px solid #eee', marginRight: '10px', marginTop: '10px'}} />
                                            ))}
                                        </div>
                                    </div>
                                )
                            })
                        )}
                        {reviewLoading && <div style={{padding: '20px', textAlign: 'center'}}>Retrieving Historical Archives...</div>}
                    </div>
                </div>

            </div>
        </div>
    );
}
