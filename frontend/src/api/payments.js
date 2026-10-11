import { authFetch } from './http';

const API_BASE = 'http://localhost:5000/api/payments';

export const fetchPaymentMethodsAPI = async () => {
    const res = await authFetch(`${API_BASE}/`);
    if (!res.ok) throw new Error("Failed to fetch payment methods");
    return await res.json();
};

export const addPaymentMethodAPI = async (data) => {
    const res = await authFetch(`${API_BASE}/`, {
        method: 'POST',
        body: JSON.stringify(data)
    });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};

export const checkoutAPI = async (data) => {
    const res = await authFetch(`${API_BASE}/checkout`, {
        method: 'POST',
        body: JSON.stringify(data)
    });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};

export const fetchOrdersAPI = async () => {
    const res = await authFetch(`${API_BASE}/orders`);
    if (!res.ok) throw new Error("Failed to fetch orders");
    return await res.json();
};

export const updateOrderStatusAPI = async (orderId, status) => {
    const res = await authFetch(`${API_BASE}/orders/${orderId}`, {
        method: 'PUT',
        body: JSON.stringify({ status })
    });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};
