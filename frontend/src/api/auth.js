const API_BASE = 'http://localhost:5000/api/auth';

export const loginAPI = async (username, password) => {
    const res = await fetch(`${API_BASE}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const signupAPI = async (userData) => {
    const res = await fetch(`${API_BASE}/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(userData)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const requestDeletionAPI = async (userId, password) => {
    const res = await fetch(`${API_BASE}/account/request-deletion`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const updateProfileAPI = async (userId, bio) => {
    const res = await fetch(`${API_BASE}/profile`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, bio })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const updateUsernameAPI = async (userId, newUsername) => {
    const res = await fetch(`${API_BASE}/username`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, newUsername })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const updatePasswordAPI = async (userId, oldPassword, newPassword) => {
    const res = await fetch(`${API_BASE}/password`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, oldPassword, newPassword })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const fetchUserReviewsAPI = async (userId) => {
    const res = await fetch(`${API_BASE}/reviews/${userId}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};
