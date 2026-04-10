const API_BASE = 'http://localhost:5000/api/payments';

export const fetchPaymentMethodsAPI = async (userId) => {
    const res = await fetch(`${API_BASE}/${userId}`);
    if (!res.ok) throw new Error("Failed to fetch payment methods");
    return await res.json();
};

export const addPaymentMethodAPI = async (data) => {
    const res = await fetch(`${API_BASE}/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};

export const checkoutAPI = async (data) => {
    const res = await fetch(`${API_BASE}/checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};

export const fetchOrdersAPI = async (userId) => {
    const res = await fetch(`${API_BASE}/orders/${userId}`);
    if (!res.ok) throw new Error("Failed to fetch orders");
    return await res.json();
};

export const updateOrderStatusAPI = async (orderId, status) => {
    const res = await fetch(`${API_BASE}/orders/${orderId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status })
    });
    const resData = await res.json();
    if (!res.ok) throw new Error(resData.error);
    return resData;
};
