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
