import React, { useState, useEffect } from 'react';
import { getShopAPI, setupShopAPI, addProductAPI, updateShopNameAPI, updateProductAPI, deleteProductAPI, addProductImageAPI, addProductVariantAPI } from '../api/shops';
import { fetchCategoriesAPI } from '../api/products';
import { fetchPaymentMethodsAPI, addPaymentMethodAPI } from '../api/payments';
import Navbar from '../components/Navbar';

export default function SellerDashboard() {
    const user = JSON.parse(localStorage.getItem('user'));

    const [shop, setShop] = useState(null);
    const [methods, setMethods] = useState([]);
    const [categories, setCategories] = useState([]);
    const [loading, setLoading] = useState(true);

    // Auth vars
    const [methodName, setMethodName] = useState('');

    // Shop vars
    const [shopName, setShopName] = useState('');
    const [shopDesc, setShopDesc] = useState('');

    // Phase 2: Product Overhaul Vars
    const [prodName, setProdName] = useState('');
    const [prodPrice, setProdPrice] = useState('');
    const [prodStock, setProdStock] = useState('');
    const [prodCategoryText, setProdCategoryText] = useState('');

    const [variants, setVariants] = useState([]);
    const [vName, setVName] = useState('');
    const [vValue, setVValue] = useState('');

    const [images, setImages] = useState([]);
    const [imgUrl, setImgUrl] = useState('');

    const loadData = async () => {
        try {
            const data = await getShopAPI(user.id);
            setShop(data);
        } catch (err) {
            setShop(null);
        }

        try {
            const pmData = await fetchPaymentMethodsAPI(user.id);
            setMethods(pmData.methods);
        } catch (err) { console.error(err); }

        try {
            const catData = await fetchCategoriesAPI();
            setCategories(catData.categories);
        } catch (err) { console.error(err); }

        setLoading(false);
    }

    useEffect(() => {
        if (user && user.role === 'seller') loadData();
        else setLoading(false);
    }, []);

    const handleAddMethod = async (e) => {
        e.preventDefault();
        try {
            await addPaymentMethodAPI({
                userId: user.id,
                methodType: 'bank',
                providerName: methodName,
                accountNumber: 'xxxx-' + Math.floor(1000 + Math.random() * 9000)
            });
            loadData();
        } catch (err) { alert(err.message); }
    }

    if (!user || user.role !== 'seller') {
        return <h2 style={{ padding: '20px' }}>Access Denied. Only registered Sellers can access this dashboard.</h2>;
    }
    if (loading) return <div><Navbar />Loading secure dashboard...</div>;

    if (methods.length === 0) {
        return (
            <div style={{ backgroundColor: '#f5f5f5', minHeight: '100vh' }}>
                <Navbar />
                <div style={{ padding: '60px', fontFamily: 'Inter, sans-serif', maxWidth: '900px', margin: '0 auto' }}>
                    <h2>Welcome, future Slopee Seller {user.name}!</h2>
                    <div style={{ background: '#ffebee', color: '#c62828', padding: '20px', borderRadius: '4px', marginBottom: '20px', border: '1px solid #f2bac9' }}>
                        <h3 style={{ margin: '0 0 10px 0' }}>Mandatory Requirement</h3>
                        You must link at least one Bank Account to receive your sales revenue payouts before you can activate your online shop!
                    </div>
                    <form onSubmit={handleAddMethod} style={{ background: '#fff', padding: '30px', borderRadius: '4px', display: 'flex', gap: '15px', alignItems: 'center', boxShadow: '0 2px 10px rgba(0,0,0,0.05)' }}>
                        <input required placeholder="E.g., Virtual Chase Bank, Stripe Checkout, etc." value={methodName} onChange={e => setMethodName(e.target.value)} style={{ padding: '12px', flex: 1, fontSize: '15px', border: '1px solid #ccc' }} />
                        <button type="submit" style={{ background: '#ee4d2d', color: '#fff', border: 'none', padding: '14px 24px', cursor: 'pointer', fontWeight: 'bold', fontSize: '15px' }}>Link Bank Account & Unlock Shop!</button>
                    </form>
                </div>
            </div>
        );
    }

    const handleSetupShop = async (e) => {
        e.preventDefault();
        try {
            await setupShopAPI({ seller_id: user.id, name: shopName, description: shopDesc });
            loadData();
        } catch (err) { alert(err.message); }
    }

    const handleEditShopName = async () => {
        const newName = prompt("Enter new shop name:", shop.name);
        if (newName && newName.trim() !== '') {
            try {
                await updateShopNameAPI(user.id, newName);
                loadData();
            } catch (err) { alert(err.message); }
        }
    }

    const handleAddProduct = async (e) => {
        e.preventDefault();
        // Resolve Category String to ID seamlessly
        const matchingCat = categories.find(c => c.name.toLowerCase() === prodCategoryText.toLowerCase());
        const catId = matchingCat ? matchingCat.id : 1;

        try {
            const res = await addProductAPI({ shopId: shop.id, name: prodName, unitPrice: Number(prodPrice), inStock: Number(prodStock), categoryId: catId });

            if (res.productId) {
                // Upload Rich Metadata Sequentially
                for (let v of variants) {
                    await addProductVariantAPI(res.productId, v.name, v.value);
                }
                for (let i = 0; i < images.length; i++) {
                    await addProductImageAPI(res.productId, images[i], i === 0);
                }
            }

            // Clean up
            setProdName(''); setProdPrice(''); setProdStock(''); setProdCategoryText('');
            setVariants([]); setImages([]);
            loadData();
        } catch (err) { alert(err.message); }
    }

    const handleEditProduct = async (prod) => {
        const newPrice = prompt(`Enter new price for ${prod.name}:`, prod.unitPrice);
        if (newPrice === null) return;
        const newStock = prompt(`Enter new stock for ${prod.name}:`, prod.inStock);
        if (newStock === null) return;

        try {
            await updateProductAPI(prod.id, { unitPrice: newPrice, inStock: newStock });
            loadData();
        } catch (err) { alert(err.message); }
    }

    const handleDeleteProduct = async (prodId) => {
        if (!window.confirm("Are you sure you want to permanently delete this product?")) return;
        try {
            await deleteProductAPI(prodId);
            loadData();
        } catch (err) { alert(err.message); }
    }

    if (!shop) {
        return (
            <div style={{ backgroundColor: '#f5f5f5', minHeight: '100vh' }}>
                <Navbar />
                <div style={{ padding: '40px', fontFamily: 'Inter, sans-serif', maxWidth: '900px', margin: '0 auto' }}>
                    <div style={{ background: '#e8f5e9', color: '#2e7d32', padding: '15px', borderRadius: '4px', marginBottom: '30px', border: '1px solid #a5d6a7' }}>
                        ✅ Bank Account linked successfully! You are now cleared to build your shop schema.
                    </div>
                    <h2>Welcome, {user.name}!</h2>
                    <p style={{ marginBottom: '20px', color: '#555' }}>You haven't initialized your Shop Profile yet. Setup yours below to start selling!</p>
                    <form onSubmit={handleSetupShop} style={{ display: 'flex', flexDirection: 'column', width: '350px', gap: '10px' }}>
                        <input type="text" placeholder="Your Shop's Custom Name" required onChange={e => setShopName(e.target.value)} style={{ padding: '10px' }} />
                        <textarea placeholder="Describe your shop..." onChange={e => setShopDesc(e.target.value)} style={{ padding: '10px', height: '100px' }} />
                        <button type="submit" style={{ background: '#ee4d2d', color: '#fff', padding: '12px', border: 'none', cursor: 'pointer' }}>Activate My Shop</button>
                    </form>
                </div>
            </div>
        );
    }

    const getCatName = (id) => {
        const c = categories.find(cat => cat.id === id);
        return c ? c.name : 'General';
    };

    return (
        <div style={{ backgroundColor: '#f5f5f5', minHeight: '100vh', paddingBottom: '100px' }}>
            <Navbar />
            <div style={{ padding: '40px', fontFamily: 'Inter, sans-serif', maxWidth: '1000px', margin: '0 auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div>
                        <h1 style={{ color: '#ee4d2d', margin: 0, display: 'inline-block' }}>🏪 {shop.name}</h1>
                        <button onClick={handleEditShopName} style={{ marginLeft: '15px', padding: '5px 10px', fontSize: '12px' }}>Edit Shop Name</button>
                    </div>
                </div>

                <p style={{ color: '#666', fontStyle: 'italic', marginTop: '10px' }}>{shop.description}</p>
                <hr style={{ margin: '20px 0' }} />

                <div style={{ background: '#fff', padding: '30px', borderRadius: '8px', boxShadow: '0 4px 12px rgba(0,0,0,0.05)', borderTop: '4px solid #ee4d2d' }}>
                    <h2 style={{ marginTop: 0, color: '#333' }}>List a New Component</h2>

                    <form onSubmit={handleAddProduct} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

                        <div style={{ display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
                            <div style={{ flex: 2, minWidth: '250px' }}>
                                <label style={{ fontSize: '12px', color: '#666', fontWeight: 'bold' }}>PRODUCT NAME</label>
                                <input type="text" placeholder="E.g., Wireless Mouse" value={prodName} required onChange={e => setProdName(e.target.value)} style={{ padding: '10px', width: '100%', boxSizing: 'border-box', border: '1px solid #ccc', borderRadius: '4px' }} />
                            </div>
                            <div style={{ flex: 1, minWidth: '150px' }}>
                                <label style={{ fontSize: '12px', color: '#666', fontWeight: 'bold' }}>CATEGORY TAG</label>
                                <input list="category-options" placeholder="Search categories..." value={prodCategoryText} onChange={e => setProdCategoryText(e.target.value)} required style={{ padding: '10px', width: '100%', boxSizing: 'border-box', border: '1px solid #ccc', borderRadius: '4px' }} />
                                <datalist id="category-options">
                                    {categories.map(c => <option key={c.id} value={c.name} />)}
                                </datalist>
                            </div>
                            <div style={{ flex: 1, minWidth: '100px' }}>
                                <label style={{ fontSize: '12px', color: '#666', fontWeight: 'bold' }}>PRICE ($)</label>
                                <input type="number" step="0.01" value={prodPrice} required onChange={e => setProdPrice(e.target.value)} style={{ padding: '10px', width: '100%', boxSizing: 'border-box', border: '1px solid #ccc', borderRadius: '4px' }} />
                            </div>
                            <div style={{ flex: 1, minWidth: '100px' }}>
                                <label style={{ fontSize: '12px', color: '#666', fontWeight: 'bold' }}>STOCK (QTY)</label>
                                <input type="number" value={prodStock} required onChange={e => setProdStock(e.target.value)} style={{ padding: '10px', width: '100%', boxSizing: 'border-box', border: '1px solid #ccc', borderRadius: '4px' }} />
                            </div>
                        </div>

                        <hr style={{ borderTop: '1px dashed #eee' }} />

                        <div style={{ display: 'flex', gap: '40px', flexWrap: 'wrap' }}>
                            {/* Images Section */}
                            <div style={{ flex: 1 }}>
                                <h4 style={{ margin: '0 0 10px 0', color: '#444' }}>🖼️ Photo Gallery ({images.length})</h4>
                                <div style={{ display: 'flex', gap: '5px', marginBottom: '10px' }}>
                                    <input type="text" placeholder="Image HTTPS URL..." value={imgUrl} onChange={e => setImgUrl(e.target.value)} style={{ padding: '8px', flex: 1, border: '1px solid #ccc', borderRadius: '4px' }} />
                                    <button type="button" onClick={() => { if (imgUrl) { setImages([...images, imgUrl]); setImgUrl(''); } }} style={{ background: '#f0f0f0', border: '1px solid #ccc', cursor: 'pointer', padding: '0 15px' }}>+</button>
                                </div>
                                <div style={{ display: 'flex', gap: '10px', overflowX: 'auto' }}>
                                    {images.map((img, idx) => (
                                        <div key={idx} style={{ position: 'relative', width: '60px', height: '60px', borderRadius: '4px', overflow: 'hidden', border: idx === 0 ? '2px solid #ee4d2d' : '1px solid #ddd' }}>
                                            <img src={img} alt="preview" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                            {idx === 0 && <span style={{ position: 'absolute', bottom: 0, background: 'rgba(238, 77, 45, 0.9)', color: '#fff', fontSize: '9px', width: '100%', textAlign: 'center' }}>PRIMARY</span>}
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* Variants Section */}
                            <div style={{ flex: 1 }}>
                                <h4 style={{ margin: '0 0 10px 0', color: '#444' }}>⚙️ Product Variants ({variants.length})</h4>
                                <div style={{ display: 'flex', gap: '5px', marginBottom: '10px' }}>
                                    <input type="text" placeholder="E.g. Color" value={vName} onChange={e => setVName(e.target.value)} style={{ padding: '8px', width: '80px', border: '1px solid #ccc', borderRadius: '4px' }} />
                                    <input type="text" placeholder="E.g. Red" value={vValue} onChange={e => setVValue(e.target.value)} style={{ padding: '8px', flex: 1, border: '1px solid #ccc', borderRadius: '4px' }} />
                                    <button type="button" onClick={() => { if (vName && vValue) { setVariants([...variants, { name: vName, value: vValue }]); setVName(''); setVValue(''); } }} style={{ background: '#f0f0f0', border: '1px solid #ccc', cursor: 'pointer', padding: '0 15px' }}>+</button>
                                </div>
                                <div style={{ display: 'flex', gap: '5px', flexWrap: 'wrap' }}>
                                    {variants.map((v, idx) => (
                                        <span key={idx} style={{ background: '#e3f2fd', color: '#1565c0', padding: '4px 8px', borderRadius: '12px', fontSize: '12px', border: '1px solid #bbdefb' }}>
                                            {v.name}: {v.value}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        </div>

                        <button type="submit" style={{ background: '#ee4d2d', color: '#fff', border: 'none', padding: '15px', cursor: 'pointer', fontSize: '16px', fontWeight: 'bold', borderRadius: '4px', marginTop: '10px' }}>Publish Product to Web Store</button>
                    </form>
                </div>

                <h3 style={{ marginTop: '40px' }}>Your Live Online Inventory ({shop.products ? shop.products.length : 0} items)</h3>
                <ul style={{ listStyle: 'none', padding: 0 }}>
                    {shop.products && shop.products.map(p => (
                        <li key={p.id} style={{ padding: '20px', border: '1px solid #eee', marginBottom: '15px', borderRadius: '8px', display: 'flex', gap: '20px', alignItems: 'center', background: '#fff', boxShadow: '0 2px 5px rgba(0,0,0,0.02)' }}>
                            <div style={{ width: '80px', height: '80px', background: '#f9f9f9', borderRadius: '4px', overflow: 'hidden', flexShrink: 0 }}>
                                {p.images && p.images.length > 0 ? (
                                    <img src={p.images.find(img => img.isPrimary)?.imageUrl || p.images[0].imageUrl} alt={p.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                ) : (
                                    <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#ccc', fontSize: '12px' }}>No IMG</div>
                                )}
                            </div>

                            <div style={{ flex: 1 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                    <strong style={{ fontSize: '18px' }}>{p.name}</strong>
                                    <span style={{ background: '#f5f5f5', color: '#666', padding: '2px 6px', borderRadius: '3px', fontSize: '11px' }}>{getCatName(p.categoryId)}</span>
                                </div>

                                <div style={{ marginTop: '8px', display: 'flex', gap: '5px', flexWrap: 'wrap' }}>
                                    {p.variants && p.variants.map(v => (
                                        <span key={v.id} style={{ fontSize: '11px', background: '#e8f0fe', color: '#1967d2', padding: '2px 6px', borderRadius: '10px' }}>{v.variantName}: {v.variantValue}</span>
                                    ))}
                                </div>

                                <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '15px', fontSize: '14px' }}>
                                    <span style={{ color: '#ee4d2d', fontWeight: 'bold' }}>${p.unitPrice}</span>
                                    <span style={{ color: p.inStock > 0 ? '#2e7d32' : '#d32f2f', fontWeight: '500' }}>
                                        {p.inStock > 0 ? `${p.inStock} in stock` : 'Out of Stock!'}
                                    </span>
                                </div>
                            </div>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <button onClick={() => handleEditProduct(p)} style={{ padding: '8px 15px', background: '#fafafa', border: '1px solid #ccc', cursor: 'pointer', borderRadius: '4px' }}>Edit Allocation</button>
                                <button onClick={() => handleDeleteProduct(p.id)} style={{ padding: '8px 15px', background: '#b71c1c', color: '#fff', border: 'none', cursor: 'pointer', borderRadius: '4px' }}>Take Down</button>
                            </div>
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    );
}
