import { authFetch } from './http';

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

export const requestDeletionAPI = async (password) => {
    const res = await authFetch(`${API_BASE}/account/request-deletion`, {
        method: 'POST',
        body: JSON.stringify({ password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const updateProfileAPI = async (bio) => {
    const res = await authFetch(`${API_BASE}/profile`, {
        method: 'PUT',
        body: JSON.stringify({ bio })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const updateUsernameAPI = async (newUsername) => {
    const res = await authFetch(`${API_BASE}/username`, {
        method: 'PUT',
        body: JSON.stringify({ newUsername })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const updatePasswordAPI = async (oldPassword, newPassword) => {
    const res = await authFetch(`${API_BASE}/password`, {
        method: 'PUT',
        body: JSON.stringify({ oldPassword, newPassword })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};

export const fetchUserReviewsAPI = async () => {
    const res = await authFetch(`${API_BASE}/reviews/me`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data;
};
