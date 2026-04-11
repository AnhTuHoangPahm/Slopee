const API_BASE = 'http://localhost:5000/api/products';

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
