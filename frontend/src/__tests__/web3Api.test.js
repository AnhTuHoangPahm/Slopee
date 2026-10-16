import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
    createWeb3OrderAPI, fetchCheckoutGroupAPI, fetchLinkedWalletAPI, fetchWeb3EligibilityAPI, linkWalletAPI, requestWalletNonceAPI, requoteGroupAPI,
} from '../api/web3';
import { Web3ApiError } from '../lib/errors';
import { installWeb3Mock } from '../mocks/web3Mock';

const res = (status, body) => new Response(typeof body === 'string' ? body : JSON.stringify(body), { status });

describe('api/web3 (fetch giả)', () => {
    let calls;
    beforeEach(() => {
        sessionStorage.setItem('token', 'tok123');
        calls = [];
    });
    afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });
    const stub = (r) => vi.stubGlobal('fetch', vi.fn(async (url, init) => { calls.push({ url, init }); return typeof r === 'function' ? r() : r; }));

    it('gửi đúng đường dẫn, method, thân và header Authorization', async () => {
        stub(() => res(200, { ok: 1 }));
        await requestWalletNonceAPI('0xabc');
        await linkWalletAPI({ address: '0xabc', signature: '0xsig', nonce: 'n' });
        await fetchLinkedWalletAPI();
        await createWeb3OrderAPI(['c1', 'c2']);
        await requoteGroupAPI('g 1');
        await fetchCheckoutGroupAPI('g/2');
        await fetchWeb3EligibilityAPI(['c1']);
        expect(calls.map((c) => [c.init.method, c.url.replace(/^https?:\/\/[^/]+/, '')])).toEqual([
            ['POST', '/api/wallet/nonce'], ['POST', '/api/wallet/link'], ['GET', '/api/wallet'], ['POST', '/api/orders'],
            ['POST', '/api/checkout-groups/g%201/quote'], ['GET', '/api/checkout-groups/g%2F2'], ['POST', '/api/orders/eligibility'],
        ]);
        expect(JSON.parse(calls[6].init.body)).toEqual({ cart_item_ids: ['c1'] });
        expect(JSON.parse(calls[0].init.body)).toEqual({ address: '0xabc' });
        expect(JSON.parse(calls[1].init.body)).toEqual({ address: '0xabc', signature: '0xsig', nonce: 'n' });
        expect(JSON.parse(calls[3].init.body)).toEqual({ cart_item_ids: ['c1', 'c2'] });
        expect(calls.every((c) => c.init.headers.Authorization === 'Bearer tok123')).toBe(true);
        expect(calls[2].init.body).toBeUndefined();
    });

    it('lỗi {code, message} của backend trở thành Web3ApiError giữ nguyên mã, status và trường phụ', async () => {
        stub(() => res(409, { code: 'PENDING_GROUP_EXISTS', message: 'Đang có lô', checkout_group_id: 'g9' }));
        const err = await createWeb3OrderAPI(['c']).catch((e) => e);
        expect(err).toBeInstanceOf(Web3ApiError);
        expect(err).toMatchObject({ code: 'PENDING_GROUP_EXISTS', status: 409, message: 'Đang có lô' });
        expect(err.extra.checkout_group_id).toBe('g9');
    });

    it('lỗi dạng cũ {error, code} (require_auth) vẫn đọc được', async () => {
        stub(() => res(403, { error: 'Forbidden', code: 'forbidden' }));
        await expect(fetchLinkedWalletAPI()).rejects.toMatchObject({ code: 'forbidden', message: 'Forbidden', status: 403 });
    });

    it('thân không phải JSON: vẫn ra lỗi có mã HTTP_xxx', async () => {
        stub(() => res(502, '<html>Bad gateway</html>'));
        await expect(fetchLinkedWalletAPI()).rejects.toMatchObject({ code: 'HTTP_502', status: 502 });
    });

    it('mất mạng: NETWORK_ERROR với thông báo tiếng Việt', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
        const err = await fetchLinkedWalletAPI().catch((e) => e);
        expect(err.code).toBe('NETWORK_ERROR');
        expect(err.message).toMatch(/máy chủ/);
    });
});

describe('mocks/web3Mock bám đúng hợp đồng API', () => {
    let mock;
    const A = '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc';
    beforeEach(() => { sessionStorage.setItem('token', 't'); mock = installWeb3Mock({ latencyMs: 0 }); });
    afterEach(() => { mock.uninstall(); sessionStorage.clear(); });

    it('liên kết ví: nonce dùng một lần, sai địa chỉ bị từ chối', async () => {
        expect(await fetchLinkedWalletAPI()).toMatchObject({ linked: false, address: null });
        await expect(requestWalletNonceAPI('xyz')).rejects.toMatchObject({ code: 'INVALID_ADDRESS' });
        const { nonce, message } = await requestWalletNonceAPI(A);
        expect(message).toContain(nonce);
        await expect(linkWalletAPI({ address: '0x1111111111111111111111111111111111111111', signature: 's', nonce })).rejects.toMatchObject({ code: 'BAD_SIGNATURE' });
        const n2 = await requestWalletNonceAPI(A);
        expect(await linkWalletAPI({ address: A, signature: 's', nonce: n2.nonce })).toMatchObject({ address: A.toLowerCase() });
        await expect(linkWalletAPI({ address: A, signature: 's', nonce: n2.nonce })).rejects.toMatchObject({ code: 'NONCE_INVALID' });
        expect(await fetchLinkedWalletAPI()).toMatchObject({ linked: true, address: A.toLowerCase() });
    });

    it('tạo đơn cần ví; lô đang chờ chặn lần tạo thứ hai; báo giá mới giữ mã on-chain', async () => {
        await expect(createWeb3OrderAPI(['c1'])).rejects.toMatchObject({ code: 'WALLET_NOT_LINKED' });
        const n = await requestWalletNonceAPI(A);
        await linkWalletAPI({ address: A, signature: 's', nonce: n.nonce });
        await expect(createWeb3OrderAPI([])).rejects.toMatchObject({ code: 'EMPTY_CART' });
        const g = await createWeb3OrderAPI(['c1']);
        expect(g.orders).toHaveLength(2);
        expect(g.total_amount_raw).toBe(String(g.orders.reduce((a, o) => a + BigInt(o.amount_raw), 0n)));
        expect(g.orders[0].amount_raw).toBe('15960000'); // 399000 VND / 25000 = 15,96
        const dup = await createWeb3OrderAPI(['c1']).catch((e) => e);
        expect(dup).toMatchObject({ code: 'PENDING_GROUP_EXISTS' });
        expect(dup.extra.checkout_group_id).toBe(g.checkout_group_id);
        const g2 = await requoteGroupAPI(g.checkout_group_id);
        expect(g2.orders.map((o) => o.onchain_order_id)).toEqual(g.orders.map((o) => o.onchain_order_id));
        expect((await fetchCheckoutGroupAPI(g.checkout_group_id)).status).toBe('PENDING_PAYMENT');
        await expect(fetchCheckoutGroupAPI('nope')).rejects.toMatchObject({ code: 'GROUP_NOT_FOUND', status: 404 });
    });

    it('eligibility: mô phỏng BR-07 (shop chưa liên kết ví) và tạo đơn bị chặn nêu đích danh shop', async () => {
        const ok = await fetchWeb3EligibilityAPI(['c1']);
        expect(ok).toEqual({ all_linked: true, shops: [expect.objectContaining({ wallet_linked: true }), expect.objectContaining({ wallet_linked: true })] });
        await expect(fetchWeb3EligibilityAPI([])).rejects.toMatchObject({ code: 'EMPTY_CART' });
        mock.state.unlinkedShopIds.add('mock-shop-2');
        const blocked = await fetchWeb3EligibilityAPI(['c1']);
        expect(blocked.all_linked).toBe(false);
        expect(blocked.shops.filter((s) => !s.wallet_linked).map((s) => s.shop_name)).toEqual(['Cửa hàng Mẫu B']);
        const n = await requestWalletNonceAPI(A);
        await linkWalletAPI({ address: A, signature: 's', nonce: n.nonce });
        const err = await createWeb3OrderAPI(['c1']).catch((e) => e);
        expect(err).toMatchObject({ code: 'WALLET_NOT_LINKED', status: 409 });
        expect(err.extra).toMatchObject({ party: 'merchant', shop_id: 'mock-shop-2', shop_name: 'Cửa hàng Mẫu B' });
    });

    it('API khác đi qua fetch thật', async () => {
        const real = vi.fn(async () => res(200, { passthrough: true }));
        mock.uninstall();
        vi.stubGlobal('fetch', real);
        mock = installWeb3Mock({ latencyMs: 0 });
        const r = await fetch('http://localhost:5000/api/products');
        expect(await r.json()).toEqual({ passthrough: true });
        mock.uninstall();
        vi.unstubAllGlobals();
    });
});
