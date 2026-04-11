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

export const updateShopNameAPI = async (sellerId, name) => {
    const res = await fetch(`${API_BASE}/${sellerId}/name`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const updateProductAPI = async (productId, updateData) => {
    const res = await fetch(`${API_BASE}/products/${productId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updateData)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const deleteProductAPI = async (productId) => {
    const res = await fetch(`${API_BASE}/products/${productId}`, { method: 'DELETE' });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};

// --- PHASE 1 FEATURE F: PRODUCT RICHNESS DATA BINDINGS ---

export const addProductImageAPI = async (productId, imageUrl, isPrimary) => {
    const res = await fetch(`${API_BASE}/products/${productId}/images`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ imageUrl, isPrimary })
    });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};

export const deleteProductImageAPI = async (imageId) => {
    const res = await fetch(`${API_BASE}/products/images/${imageId}`, { method: 'DELETE' });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};

export const addProductVariantAPI = async (productId, variantName, variantValue) => {
    const res = await fetch(`${API_BASE}/products/${productId}/variants`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variantName, variantValue })
    });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};

export const deleteProductVariantAPI = async (variantId) => {
    const res = await fetch(`${API_BASE}/products/variants/${variantId}`, { method: 'DELETE' });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};
