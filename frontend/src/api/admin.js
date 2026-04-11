const API_BASE = 'http://localhost:5000/api/admin';

export const getStatsAPI = async () => {
    const res = await fetch(`${API_BASE}/stats`);
    if (!res.ok) throw new Error("Failed to load stats");
    return await res.json();
};

export const getUsersAPI = async () => {
    const res = await fetch(`${API_BASE}/users`);
    if (!res.ok) throw new Error("Failed to load users");
    return await res.json();
};

export const deleteUserAPI = async (userId) => {
    const res = await fetch(`${API_BASE}/users/${userId}`, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const fetchAdminCategoriesAPI = async () => {
    const res = await fetch(`${API_BASE}/categories`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const addCategoryAPI = async (name) => {
    const res = await fetch(`${API_BASE}/categories`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const updateCategoryAPI = async (id, name) => {
    const res = await fetch(`${API_BASE}/categories/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const deleteCategoryAPI = async (id) => {
    const res = await fetch(`${API_BASE}/categories/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};
