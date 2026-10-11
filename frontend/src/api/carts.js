import { authFetch } from './http';

const API_BASE = 'http://localhost:5000/api/carts';

export const fetchCartAPI = async () => {
    const res = await authFetch(`${API_BASE}/`);
    if (!res.ok) throw new Error("Failed to fetch cart");
    return await res.json();
};

export const addToCartAPI = async (productId, quantity = 1, selectedVariants = {}) => {
    const res = await authFetch(`${API_BASE}/items`, {
        method: 'POST',
        body: JSON.stringify({ productId, quantity, selectedVariants })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const updateCartItemAPI = async (itemId, quantity) => {
    const res = await authFetch(`${API_BASE}/items/${itemId}`, {
        method: 'PUT',
        body: JSON.stringify({ quantity })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const removeCartItemAPI = async (itemId) => {
    const res = await authFetch(`${API_BASE}/items/${itemId}`, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};
