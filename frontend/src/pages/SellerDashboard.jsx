import React, { useState, useEffect } from 'react';
import { getShopAPI, setupShopAPI, addProductAPI } from '../api/shops';

export default function SellerDashboard() {
    const user = JSON.parse(localStorage.getItem('user'));
    const [shop, setShop] = useState(null);
    const [loading, setLoading] = useState(true);
    
    // Shop setup form
    const [shopName, setShopName] = useState('');
    const [shopDesc, setShopDesc] = useState('');
    
    // Product insert form
    const [prodName, setProdName] = useState('');
    const [prodPrice, setProdPrice] = useState(0);
    const [prodStock, setProdStock] = useState(0);

    const loadShop = async () => {
        try {
            const data = await getShopAPI(user.id);
            setShop(data);
        } catch (err) {
            setShop(null);
        }
        setLoading(false);
    }

    useEffect(() => {
        if (user && user.role === 'seller') loadShop();
        else setLoading(false);
    }, []);

    if (!user || user.role !== 'seller') {
        return <h2 style={{padding: '20px'}}>Access Denied. Only registered Sellers can access this dashboard.</h2>;
    }
    if (loading) return <div style={{padding: '20px'}}>Loading dashboard...</div>;

    const handleSetupShop = async (e) => {
        e.preventDefault();
        try {
            await setupShopAPI({ seller_id: user.id, name: shopName, description: shopDesc });
            alert("Shop successfully activated! You can now list items.");
            loadShop();
        } catch(err) { alert(err.message); }
    }

    const handleAddProduct = async (e) => {
        e.preventDefault();
        try {
            await addProductAPI({ shopId: shop.id, name: prodName, unitPrice: prodPrice, inStock: prodStock });
            alert("Product published entirely successfully!");
            // Reset fields
            setProdName('');
            setProdPrice(0);
            setProdStock(0);
            loadShop();
        } catch(err) { alert(err.message); }
    }

    if (!shop) {
        return (
            <div style={{ padding: '40px', fontFamily: 'Arial' }}>
                <h2>Welcome, {user.name}!</h2>
                <p style={{marginBottom: '20px', color: '#555'}}>You haven't initialized your Shop Profile yet. Setup yours below to start selling!</p>
                <form onSubmit={handleSetupShop} style={{ display: 'flex', flexDirection: 'column', width: '350px', gap: '10px' }}>
                    <input type="text" placeholder="Your Shop's Custom Name" required onChange={e=>setShopName(e.target.value)} style={{padding:'10px'}}/>
                    <textarea placeholder="Describe your shop..." onChange={e=>setShopDesc(e.target.value)} style={{padding:'10px', height: '100px'}} />
                    <button type="submit" style={{ background: '#ee4d2d', color:'#fff', padding: '12px', border:'none', cursor:'pointer' }}>Activate My Shop</button>
                </form>
            </div>
        );
    }

    return (
        <div style={{ padding: '40px', fontFamily: 'Arial' }}>
            <h1 style={{color: '#ee4d2d'}}>🏪 {shop.name}</h1>
            <p style={{color: '#666', fontStyle: 'italic'}}>{shop.description}</p>
            <hr style={{margin: '20px 0'}}/>
            
            <div style={{ background: '#f9f9f9', padding: '20px', borderRadius: '5px' }}>
                <h3 style={{marginTop: 0}}>List a New Product</h3>
                <form onSubmit={handleAddProduct} style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                    <input type="text" placeholder="Product Name" value={prodName} required onChange={e=>setProdName(e.target.value)} style={{padding:'8px', width:'250px'}}/>
                    <input type="number" placeholder="Price ($)" value={prodPrice} required onChange={e=>setProdPrice(e.target.value)} style={{padding:'8px', width:'100px'}}/>
                    <input type="number" placeholder="Stock Qty" value={prodStock} required onChange={e=>setProdStock(e.target.value)} style={{padding:'8px', width:'100px'}}/>
                    <button type="submit" style={{ background: '#ee4d2d', color: '#fff', border:'none', padding:'10px 20px', cursor:'pointer' }}>Publish to Shop</button>
                </form>
            </div>

            <h3 style={{marginTop: '30px'}}>Your Live Online Inventory ({shop.products ? shop.products.length : 0} items)</h3>
            <ul style={{listStyle: 'none', padding: 0}}>
                {shop.products && shop.products.map(p => (
                    <li key={p.id} style={{padding: '15px', border: '1px solid #ddd', marginBottom: '10px', borderRadius: '4px'}}>
                        <strong>{p.name}</strong> • ${p.unitPrice} 
                        <span style={{float: 'right', color: p.inStock > 0 ? 'green' : 'red'}}>
                            {p.inStock > 0 ? `${p.inStock} in stock` : 'Out of Stock'}
                        </span>
                    </li>
                ))}
            </ul>
        </div>
    );
}
