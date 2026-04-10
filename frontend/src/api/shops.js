const API_BASE = 'http://localhost:5000/api/shops';

export const setupShopAPI = async (sellerData) => {
    const res = await fetch(`${API_BASE}/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sellerData)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const getShopAPI = async (sellerId) => {
    const res = await fetch(`${API_BASE}/${sellerId}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to fetch shop");
    return data;
};

export const addProductAPI = async (productData) => {
    const res = await fetch(`${API_BASE}/products`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(productData)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};
