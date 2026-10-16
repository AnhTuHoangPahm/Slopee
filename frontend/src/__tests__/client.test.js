import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { API_ORIGIN, authFetch, clearSession, getToken, getUser, setSession } from '../lib/client';

// F-04: client API chung tự gắn Authorization; tự xóa phiên và chuyển trang khi token không còn hợp lệ
const jsonResponse = (status, body) => ({
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
    clone() {
        return jsonResponse(status, body);
    },
});

describe('lib/client', () => {
    let assign;

    beforeEach(() => {
        sessionStorage.clear();
        assign = vi.fn();
        vi.stubGlobal('location', { pathname: '/orders', assign });
    });
    afterEach(() => vi.unstubAllGlobals());

    it('API_ORIGIN mặc định là backend local, không có dấu / ở cuối', () => {
        expect(API_ORIGIN).toBe('http://localhost:5000');
    });

    it('lưu phiên ở sessionStorage, không dùng localStorage', () => {
        setSession('tok', { id: 'u1', role: 'user' });
        expect(getToken()).toBe('tok');
        expect(getUser()).toEqual({ id: 'u1', role: 'user' });
        expect(localStorage.getItem('token')).toBeNull();
        clearSession();
        expect(getToken()).toBeNull();
        expect(getUser()).toBeNull();
    });

    it('tự gắn header Authorization khi có token', async () => {
        setSession('abc', { id: 'u1' });
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
        vi.stubGlobal('fetch', fetchMock);
        await authFetch('http://x/api', { method: 'POST', body: '{}' });
        const [, opts] = fetchMock.mock.calls[0];
        expect(opts.headers.Authorization).toBe('Bearer abc');
        expect(opts.headers['Content-Type']).toBe('application/json');
    });

    it('không gắn Authorization khi chưa đăng nhập', async () => {
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
        vi.stubGlobal('fetch', fetchMock);
        await authFetch('http://x/api');
        expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined();
    });

    it.each(['auth_required', 'token_expired', 'token_invalid'])('mã %s: xóa phiên và chuyển về /login', async (code) => {
        setSession('old', { id: 'u1' });
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, { code })));
        await authFetch('http://x/api');
        expect(getToken()).toBeNull();
        expect(assign).toHaveBeenCalledWith('/login');
    });

    it('401 vì sai PIN/mật khẩu (mã khác) KHÔNG xóa phiên', async () => {
        setSession('keep', { id: 'u1' });
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, { error: 'Wrong PIN' })));
        await authFetch('http://x/api');
        expect(getToken()).toBe('keep');
        expect(assign).not.toHaveBeenCalled();
    });

    it('đang ở /login thì không chuyển trang lặp lại', async () => {
        vi.stubGlobal('location', { pathname: '/login', assign });
        setSession('old', { id: 'u1' });
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, { code: 'token_expired' })));
        await authFetch('http://x/api');
        expect(assign).not.toHaveBeenCalled();
    });
});
