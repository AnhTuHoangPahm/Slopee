// Client API dùng chung (SDD 9.8). Vị trí chuẩn: `lib/client.js`; `api/http.js` chỉ còn là lớp re-export để không vỡ import cũ.
// P0-01: phiên đăng nhập lưu ở sessionStorage (mất khi đóng tab), token gửi qua header Authorization.
const TOKEN_KEY = 'token';
const USER_KEY = 'user';

// Địa chỉ backend. Thứ tự: VITE_API_BASE trong frontend/.env (không có dấu / ở cuối) > tự suy ra từ địa chỉ trang:
//  - http://localhost|127.0.0.1 (máy chủ, test, Playwright): gọi thẳng http://localhost:5000
//  - IP LAN/VPN hoặc HTTPS: gọi CÙNG ORIGIN ('' -> /api/...); Vite proxy sang Flask ở 127.0.0.1:5000
//    (không CORS, không mixed content, backend không cần mở ra mạng).
const LOOPBACK = new Set(['localhost', '127.0.0.1', '[::1]', '::1']);
const guessApiOrigin = () => {
    const loc = globalThis.location;
    if (!loc) return 'http://localhost:5000';
    return loc.protocol === 'http:' && LOOPBACK.has(loc.hostname) ? 'http://localhost:5000' : '';
};
export const API_ORIGIN = (import.meta.env?.VITE_API_BASE || guessApiOrigin()).replace(/\/+$/, '');

export const getToken = () => sessionStorage.getItem(TOKEN_KEY);

export const getUser = () => {
    try {
        return JSON.parse(sessionStorage.getItem(USER_KEY));
    } catch {
        return null;
    }
};

export const setSession = (token, user) => {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
};

export const updateStoredUser = (user) => sessionStorage.setItem(USER_KEY, JSON.stringify(user));

export const clearSession = () => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
};

// Mã lỗi backend trả về khi phiên không còn hợp lệ (xem backend/auth_utils.py).
// Không dựa vào status 401 vì một số API dùng 401 cho "sai mật khẩu/PIN".
export const SESSION_ERROR_CODES = ['auth_required', 'token_expired', 'token_invalid'];

export const authFetch = async (url, options = {}) => {
    const headers = { ...(options.headers || {}) };
    if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(url, { ...options, headers });

    if (res.status === 401) {
        const body = await res.clone().json().catch(() => ({}));
        if (SESSION_ERROR_CODES.includes(body.code)) {
            clearSession();
            if (window.location.pathname !== '/login') window.location.assign('/login');
        }
    }
    return res;
};
