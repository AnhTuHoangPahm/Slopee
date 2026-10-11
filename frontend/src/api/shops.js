import { authFetch } from './http';

const API_BASE = 'http://localhost:5000/api/shops';

export const setupShopAPI = async (sellerData) => {
    const res = await authFetch(`${API_BASE}/`, {
        method: 'POST',
        body: JSON.stringify(sellerData)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const getShopAPI = async () => {
    const res = await authFetch(`${API_BASE}/me`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to fetch shop");
    return data;
};

export const addProductAPI = async (productData) => {
    const res = await authFetch(`${API_BASE}/products`, {
        method: 'POST',
        body: JSON.stringify(productData)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const updateShopNameAPI = async (name) => {
    const res = await authFetch(`${API_BASE}/me/name`, {
        method: 'PUT',
        body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const updateProductAPI = async (productId, updateData) => {
    const res = await authFetch(`${API_BASE}/products/${productId}`, {
        method: 'PUT',
        body: JSON.stringify(updateData)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const deleteProductAPI = async (productId) => {
    const res = await authFetch(`${API_BASE}/products/${productId}`, { method: 'DELETE' });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};

// --- PHASE 1 FEATURE F: PRODUCT RICHNESS DATA BINDINGS ---

export const addProductImageAPI = async (productId, imageUrl, isPrimary) => {
    const res = await authFetch(`${API_BASE}/products/${productId}/images`, {
        method: 'POST',
        body: JSON.stringify({ imageUrl, isPrimary })
    });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};

export const deleteProductImageAPI = async (imageId) => {
    const res = await authFetch(`${API_BASE}/products/images/${imageId}`, { method: 'DELETE' });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};

export const addProductVariantAPI = async (productId, variantName, variantValue) => {
    const res = await authFetch(`${API_BASE}/products/${productId}/variants`, {
        method: 'POST',
        body: JSON.stringify({ variantName, variantValue })
    });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};

export const deleteProductVariantAPI = async (variantId) => {
    const res = await authFetch(`${API_BASE}/products/variants/${variantId}`, { method: 'DELETE' });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};
