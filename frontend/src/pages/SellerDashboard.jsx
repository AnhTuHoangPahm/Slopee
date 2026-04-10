import React, { useState, useEffect } from 'react';
import { getShopAPI, setupShopAPI, addProductAPI, updateShopNameAPI, updateProductAPI, deleteProductAPI } from '../api/shops';
import { fetchPaymentMethodsAPI, addPaymentMethodAPI } from '../api/payments';
import Navbar from '../components/Navbar';

export default function SellerDashboard() {
    const user = JSON.parse(localStorage.getItem('user'));
    
    const [shop, setShop] = useState(null);
    const [methods, setMethods] = useState([]);
    const [loading, setLoading] = useState(true);
    
    // Auth vars
    const [methodName, setMethodName] = useState('');
    
    // Shop vars
    const [shopName, setShopName] = useState('');
    const [shopDesc, setShopDesc] = useState('');
    
    const [prodName, setProdName] = useState('');
    const [prodPrice, setProdPrice] = useState(0);
    const [prodStock, setProdStock] = useState(0);

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
        } catch (err) { console.error(err) }
        
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
        return <h2 style={{padding: '20px'}}>Access Denied. Only registered Sellers can access this dashboard.</h2>;
    }
    if (loading) return <div style={{padding: '20px'}}><Navbar />Loading secure dashboard...</div>;

    // FEATURE E RESTRICTION: Sellers must link a bank first
    if (methods.length === 0) {
        return (
            <div style={{ backgroundColor: '#f5f5f5', minHeight: '100vh' }}>
                <Navbar />
                <div style={{ padding: '60px', fontFamily: 'Inter, sans-serif', maxWidth: '900px', margin: '0 auto' }}>
                    <h2>Welcome, future Slopee Seller {user.name}!</h2>
                    <div style={{background: '#ffebee', color: '#c62828', padding: '20px', borderRadius: '4px', marginBottom: '20px', border: '1px solid #f2bac9'}}>
                        <h3 style={{margin: '0 0 10px 0'}}>Mandatory Requirement</h3>
                        You must strictly link at least one Bank Account to safely receive your sales revenue payouts before you can activate your online shop!
                    </div>
                    <form onSubmit={handleAddMethod} style={{ background: '#fff', padding: '30px', borderRadius: '4px', display: 'flex', gap: '15px', alignItems: 'center', boxShadow: '0 2px 10px rgba(0,0,0,0.05)' }}>
                        <input required placeholder="E.g., Virtual Chase Bank, Stripe Checkout, etc." value={methodName} onChange={e=>setMethodName(e.target.value)} style={{ padding: '12px', flex: 1, fontSize: '15px', border: '1px solid #ccc' }} />
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
        } catch(err) { alert(err.message); }
    }

    const handleEditShopName = async () => {
        const newName = prompt("Enter new shop name:", shop.name);
        if(newName && newName.trim() !== '') {
            try {
                await updateShopNameAPI(user.id, newName);
                loadData();
            } catch (err) { alert(err.message); }
        }
    }

    const handleAddProduct = async (e) => {
        e.preventDefault();
        try {
            await addProductAPI({ shopId: shop.id, name: prodName, unitPrice: prodPrice, inStock: prodStock });
            setProdName(''); setProdPrice(0); setProdStock(0);
            loadData();
        } catch(err) { alert(err.message); }
    }

    const handleEditProduct = async (prod) => {
        const newPrice = prompt(`Enter new price for ${prod.name}:`, prod.unitPrice);
        if (newPrice === null) return;
        const newStock = prompt(`Enter new stock for ${prod.name}:`, prod.inStock);
        if (newStock === null) return;
        
        try {
            await updateProductAPI(prod.id, { unitPrice: newPrice, inStock: newStock });
            loadData();
        } catch(err) { alert(err.message); }
    }

    const handleDeleteProduct = async (prodId) => {
        if(!window.confirm("Are you sure you want to permanently delete this product?")) return;
        try {
            await deleteProductAPI(prodId);
            loadData();
        } catch(err) { alert(err.message); }
    }

    if (!shop) {
        return (
            <div style={{ backgroundColor: '#f5f5f5', minHeight: '100vh' }}>
                <Navbar />
                <div style={{ padding: '40px', fontFamily: 'Inter, sans-serif', maxWidth: '900px', margin: '0 auto' }}>
                    <div style={{background: '#e8f5e9', color: '#2e7d32', padding: '15px', borderRadius: '4px', marginBottom: '30px', border: '1px solid #a5d6a7'}}>
                        ✅ Bank Account linked successfully! You are now cleared to build your shop schema.
                    </div>
                    <h2>Welcome, {user.name}!</h2>
                    <p style={{marginBottom: '20px', color: '#555'}}>You haven't initialized your Shop Profile yet. Setup yours below to start selling!</p>
                    <form onSubmit={handleSetupShop} style={{ display: 'flex', flexDirection: 'column', width: '350px', gap: '10px' }}>
                        <input type="text" placeholder="Your Shop's Custom Name" required onChange={e=>setShopName(e.target.value)} style={{padding:'10px'}}/>
                        <textarea placeholder="Describe your shop..." onChange={e=>setShopDesc(e.target.value)} style={{padding:'10px', height: '100px'}} />
                        <button type="submit" style={{ background: '#ee4d2d', color:'#fff', padding: '12px', border:'none', cursor:'pointer' }}>Activate My Shop</button>
                    </form>
                </div>
            </div>
        );
    }

    return (
        <div style={{ backgroundColor: '#f5f5f5', minHeight: '100vh' }}>
            <Navbar />
            <div style={{ padding: '40px', fontFamily: 'Inter, sans-serif', maxWidth: '900px', margin: '0 auto' }}>
                <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between'}}>
                    <div>
                        <h1 style={{color: '#ee4d2d', margin: 0, display: 'inline-block'}}>🏪 {shop.name}</h1>
                        <button onClick={handleEditShopName} style={{marginLeft: '15px', padding: '5px 10px', fontSize: '12px'}}>Edit Shop Name</button>
                    </div>
                </div>
                
                <p style={{color: '#666', fontStyle: 'italic', marginTop: '10px'}}>{shop.description}</p>
                <hr style={{margin: '20px 0'}}/>
                
                <div style={{ background: '#f9f9f9', padding: '20px', borderRadius: '5px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                    <h3 style={{marginTop: 0}}>List a New Product</h3>
                    <form onSubmit={handleAddProduct} style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
                        <input type="text" placeholder="Product Name" value={prodName} required onChange={e=>setProdName(e.target.value)} style={{padding:'8px', width:'250px'}}/>
                        <input type="number" placeholder="Price ($)" value={prodPrice} required onChange={e=>setProdPrice(e.target.value)} style={{padding:'8px', width:'100px'}}/>
                        <input type="number" placeholder="Stock Qty" value={prodStock} required onChange={e=>setProdStock(e.target.value)} style={{padding:'8px', width:'100px'}}/>
                        <button type="submit" style={{ background: '#ee4d2d', color: '#fff', border:'none', padding:'10px 20px', cursor:'pointer' }}>Publish to Shop</button>
                    </form>
                </div>

                <h3 style={{marginTop: '30px'}}>Your Live Online Inventory ({shop.products ? shop.products.length : 0} items)</h3>
                <ul style={{listStyle: 'none', padding: 0}}>
                    {shop.products && shop.products.map(p => (
                        <li key={p.id} style={{padding: '15px', border: '1px solid #ddd', marginBottom: '10px', borderRadius: '4px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#fff'}}>
                            <div>
                                <strong>{p.name}</strong> <br/>
                                <span style={{color: '#ee4d2d'}}>${p.unitPrice}</span> •  
                                <span style={{color: p.inStock > 0 ? 'green' : 'red', marginLeft: '5px'}}>
                                    {p.inStock > 0 ? `${p.inStock} in stock` : 'Out of Stock'}
                                </span>
                            </div>
                            <div>
                                <button onClick={() => handleEditProduct(p)} style={{padding: '6px 12px', marginRight: '10px', background: '#fafafa', border: '1px solid #ccc', cursor: 'pointer'}}>Edit Pricing/Stock</button>
                                <button onClick={() => handleDeleteProduct(p.id)} style={{padding: '6px 12px', background: '#b71c1c', color: '#fff', border: 'none', cursor: 'pointer'}}>Take Down</button>
                            </div>
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    );
}
