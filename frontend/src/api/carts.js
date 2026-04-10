const API_BASE = 'http://localhost:5000/api/carts';

export const fetchCartAPI = async (userId) => {
    const res = await fetch(`${API_BASE}/${userId}`);
    if (!res.ok) throw new Error("Failed to fetch cart");
    return await res.json();
};

export const addToCartAPI = async (userId, productId, quantity = 1) => {
    const res = await fetch(`${API_BASE}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, productId, quantity })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const updateCartItemAPI = async (itemId, quantity) => {
    const res = await fetch(`${API_BASE}/items/${itemId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ quantity })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const removeCartItemAPI = async (itemId) => {
    const res = await fetch(`${API_BASE}/items/${itemId}`, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};
