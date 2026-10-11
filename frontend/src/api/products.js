import { API_ORIGIN, authFetch } from '../lib/client';

const API_BASE = `${API_ORIGIN}/api/products`;

export const fetchProductsAPI = async (searchQuery = '') => {
    // Encodes the search term safely into the URL
    const res = await fetch(`${API_BASE}/?search=${encodeURIComponent(searchQuery)}`);
    if (!res.ok) throw new Error("Failed to load products");
    return await res.json(); // returns { time_taken_sec, items }
};
export const fetchCategoriesAPI = async () => {
    const res = await fetch(`${API_BASE}/categories`);
    if (!res.ok) throw new Error("Failed to fetch product categories.");
    return await res.json();
};

export const fetchProductDetailsAPI = async (productId) => {
    const res = await fetch(`${API_BASE}/${productId}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const fetchProductReviewsAPI = async (productId, offset=0, limit=5) => {
    const res = await fetch(`${API_BASE}/${productId}/reviews?offset=${offset}&limit=${limit}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const publishProductReviewAPI = async (productId, reviewData) => {
    const res = await authFetch(`${API_ORIGIN}/api/reviews/${productId}`, {
        method: 'POST',
        body: JSON.stringify(reviewData)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};
