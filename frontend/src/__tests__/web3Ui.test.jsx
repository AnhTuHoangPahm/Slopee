import { act, configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Wallet as EthersWallet, toUtf8String, verifyMessage } from 'ethers';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Wallet from '../pages/Wallet';
import Navbar from '../components/Navbar';
import Web3CheckoutPanel from '../components/Web3CheckoutPanel';
import Checkout from '../pages/Checkout';
import { WalletProvider } from '../hooks/useWallet';
import { parseDeployment } from '../lib/chain';
import { installWeb3Mock } from '../mocks/web3Mock';
import { fetchLinkedWalletAPI, linkWalletAPI, requestWalletNonceAPI } from '../api/web3';

// Máy chậm/CI đông tải: ký ethers lần đầu có thể mất vài giây. Chỉ nới thời gian CHỜ; test sai vẫn đỏ, chỉ đỏ chậm hơn.
configure({ asyncUtilTimeout: 8000 });
vi.setConfig({ testTimeout: 20000 });

const KEY = '0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba'; // khóa thử công khai của Anvil #5
const signerWallet = new EthersWallet(KEY);
const ACCOUNT = signerWallet.address; // 0x9965…A4dc
const OTHER = '0x976EA74026E726554dB657fA54763abd0C3a0aa9';
const deployment = parseDeployment({
    chainId: 31337, escrow: '0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512', mockUSD: '0x5FbDB2315678afecb367f032d93F642f64180aa3',
    deployBlock: 1, token: { symbol: 'MUSD', decimals: 6 },
});

/** Ví EIP-1193 giả KÝ THẬT bằng khóa Anvil: để kiểm chữ ký gửi lên khôi phục đúng địa chỉ. */
function fakeProvider({ chainId = '0x7a69', onSign } = {}) {
    const signed = [];
    let granted = false; // chưa cấp quyền cho tới khi người dùng bấm "Kết nối" (eth_accounts không bật cửa sổ xác nhận)
    return {
        signed,
        request: vi.fn(async ({ method, params }) => {
            if (method === 'eth_requestAccounts') { granted = true; return [ACCOUNT]; }
            if (method === 'eth_accounts') return granted ? [ACCOUNT] : [];
            if (method === 'eth_chainId') return chainId;
            if (method === 'net_version') return String(parseInt(chainId, 16));
            if (method === 'wallet_switchEthereumChain') return null;
            if (method === 'personal_sign') {
                const message = toUtf8String(params[0]);
                signed.push(message);
                if (onSign) await onSign(message);
                return signerWallet.signMessage(message);
            }
            throw Object.assign(new Error(`unhandled ${method}`), { code: -32601 });
        }),
        on: vi.fn(),
        removeListener: vi.fn(),
    };
}

const mountWith = (ui, provider) => render(
    <MemoryRouter><WalletProvider provider={provider} deployment={deployment}>{ui}</WalletProvider></MemoryRouter>,
);

let mock;
let fetchLog;
beforeEach(() => {
    sessionStorage.setItem('token', 't');
    sessionStorage.setItem('user', JSON.stringify({ id: 'u1', name: 'An', role: 'user' }));
    mock = installWeb3Mock({ latencyMs: 0 });
    const inner = globalThis.fetch;
    fetchLog = [];
    globalThis.fetch = vi.fn(async (url, init) => {
        fetchLog.push({ url: String(url), body: init?.body ? JSON.parse(init.body) : undefined });
        if (/\/api\/carts\/?$/.test(String(url))) return new Response(JSON.stringify({ cartItems: [], items: [] }), { status: 200 }); // Navbar
        if (/\/api\/payments\/?$/.test(String(url)) && (init?.method ?? 'GET') === 'GET') { // trang Checkout cũ: không để rơi ra mạng thật
            return new Response(JSON.stringify({ methods: [{ id: 'm1', providerName: 'Bank', accountNumber: 'xxxx-1234', balance: 5_000_000 }] }), { status: 200 });
        }
        return inner(url, init);
    });
});
afterEach(() => { mock.uninstall(); sessionStorage.clear(); vi.useRealTimers(); });

const connect = async () => {
    fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
    await screen.findByTestId('connected-address');
};

describe('trang Wallet (UC-00)', () => {
    it('kết nối -> liên kết: chữ ký gửi lên khôi phục đúng địa chỉ và gắn với đúng nonce', async () => {
        const provider = fakeProvider();
        mountWith(<Wallet />, provider);
        await connect();
        expect(await screen.findByText('Tài khoản chưa liên kết ví nào.')).toBeTruthy();

        fireEvent.click(screen.getByRole('button', { name: 'Liên kết ví này' }));
        expect(await screen.findByTestId('link-ok')).toBeTruthy();
        expect(screen.getByText('Đã liên kết ví với tài khoản của bạn.')).toBeTruthy();
        expect(screen.getByTestId('linked-address').title.toLowerCase()).toBe(ACCOUNT.toLowerCase());

        const link = fetchLog.find((c) => c.url.endsWith('/api/wallet/link')).body;
        expect(link.address).toBe(ACCOUNT);
        expect(provider.signed).toHaveLength(1);
        expect(provider.signed[0]).toContain(link.nonce); // thông điệp ký chính là thông điệp backend phát cho nonce này
        expect(verifyMessage(provider.signed[0], link.signature)).toBe(ACCOUNT);
        expect(screen.queryByRole('button', { name: 'Liên kết ví này' })).toBeNull(); // đã liên kết thì không còn nút
    });

    it('hiện hướng dẫn chờ ký trong ví, rồi tắt khi xong', async () => {
        let release;
        const gate = new Promise((r) => { release = r; });
        mountWith(<Wallet />, fakeProvider({ onSign: () => gate }));
        await connect();
        fireEvent.click(await screen.findByRole('button', { name: 'Liên kết ví này' }));
        // chờ đúng bước "đợi ký" (findBy có thể bắt trúng bước lấy nonce ngay trước đó)
        await waitFor(() => expect(screen.getByTestId('link-progress').textContent).toMatch(/bấm "Ký"/));
        expect(screen.getByRole('button', { name: 'Liên kết ví này' }).disabled).toBe(true); // chống bấm đúp
        release();
        await screen.findByTestId('link-ok');
        expect(screen.queryByTestId('link-progress')).toBeNull();
    });

    it('hủy ký trong ví: thông báo trung tính (không phải lỗi), không liên kết, bấm lại được', async () => {
        let reject = true;
        mountWith(<Wallet />, fakeProvider({ onSign: () => { if (reject) throw Object.assign(new Error('denied'), { code: 4001 }); } }));
        await connect();
        fireEvent.click(await screen.findByRole('button', { name: 'Liên kết ví này' }));
        const note = await screen.findByText('Bạn đã hủy thao tác.');
        expect(note.getAttribute('role')).toBe('status'); // không phải role="alert"
        expect((await fetchLinkedWalletAPI()).linked).toBe(false);
        reject = false;
        fireEvent.click(screen.getByRole('button', { name: 'Liên kết ví này' }));
        await screen.findByTestId('link-ok');
    });

    it('ví đang kết nối khác ví đã liên kết: cảnh báo và cho đổi ví', async () => {
        const n = await requestWalletNonceAPI(OTHER);
        await linkWalletAPI({ address: OTHER, signature: 's', nonce: n.nonce });
        mountWith(<Wallet />, fakeProvider());
        await connect();
        expect((await screen.findByRole('alert', {})).textContent).toBeTruthy();
        await screen.findByText(/khác ví đã liên kết/);
        fireEvent.click(screen.getByRole('button', { name: 'Đổi sang ví này' }));
        await screen.findByTestId('link-ok');
        expect((await fetchLinkedWalletAPI()).address).toBe(ACCOUNT.toLowerCase());
    });

    it('sai mạng: chặn liên kết và gợi ý chuyển mạng', async () => {
        const provider = fakeProvider({ chainId: '0x1' });
        mountWith(<Wallet />, provider);
        await connect();
        const link = await screen.findByRole('button', { name: 'Liên kết ví này' });
        expect(link.disabled).toBe(true);
        expect(screen.getByRole('button', { name: 'Chuyển sang mạng Anvil' })).toBeTruthy();
        expect(provider.signed).toHaveLength(0);
    });

    it('lỗi backend khi liên kết hiện thông báo tiếng Việt của máy chủ', async () => {
        const inner = globalThis.fetch;
        globalThis.fetch = vi.fn(async (url, init) => (String(url).endsWith('/api/wallet/link')
            ? new Response(JSON.stringify({ code: 'WALLET_TAKEN', message: 'Ví này đã được liên kết với một tài khoản khác.' }), { status: 409 })
            : inner(url, init)));
        mountWith(<Wallet />, fakeProvider());
        await connect();
        fireEvent.click(await screen.findByRole('button', { name: 'Liên kết ví này' }));
        expect((await screen.findByText('Ví này đã được liên kết với một tài khoản khác.')).getAttribute('role')).toBe('alert');
    });

    it('không có MetaMask: hướng dẫn cài đặt', async () => {
        mountWith(<Wallet />, null);
        expect(await screen.findAllByText(/Không tìm thấy ví/)).not.toHaveLength(0);
        expect(screen.queryByRole('button', { name: /Kết nối MetaMask/ })).toBeNull();
    });
});

describe('Web3CheckoutPanel (UC-01, khung Tuần 3)', () => {
    const linkAccount = async (address = ACCOUNT) => {
        const n = await requestWalletNonceAPI(address);
        await linkWalletAPI({ address, signature: 's', nonce: n.nonce });
    };

    it('chưa kết nối ví -> nút kết nối; chưa tạo báo giá', async () => {
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider());
        expect(await screen.findByRole('button', { name: /Kết nối MetaMask/ })).toBeTruthy();
        expect(screen.queryByRole('button', { name: 'Tạo báo giá' })).toBeNull();
    });

    it('chưa liên kết ví với tài khoản -> dẫn tới /wallet', async () => {
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider());
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        const alert = await screen.findByRole('alert');
        expect(alert.textContent).toMatch(/chưa liên kết ví/);
        expect(within(alert).getByRole('link', { name: 'Liên kết ví' }).getAttribute('href')).toBe('/wallet');
    });

    it('ví khác ví đã liên kết -> cảnh báo, không cho tạo báo giá', async () => {
        await linkAccount(OTHER);
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider());
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        expect((await screen.findByRole('alert')).textContent).toMatch(/khác ví đã liên kết/);
        expect(screen.queryByRole('button', { name: 'Tạo báo giá' })).toBeNull();
    });

    it('sai mạng -> nút chuyển mạng', async () => {
        await linkAccount();
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider({ chainId: '0x1' }));
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        expect(await screen.findByRole('button', { name: 'Chuyển sang mạng Anvil' })).toBeTruthy();
    });

    it('tạo báo giá: từng shop, tổng token, tỷ giá, thời hạn; nút Ký quỹ bật khi báo giá còn hạn', async () => {
        await linkAccount();
        mountWith(<Web3CheckoutPanel cartItemIds={['c1', 'c2']} />, fakeProvider());
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Tạo báo giá' }));
        await screen.findByTestId('quote-result');
        const rows = screen.getAllByTestId('quote-row');
        expect(rows).toHaveLength(2);
        expect(rows[0].textContent).toContain('Cửa hàng Mẫu A');
        expect(rows[0].textContent).toContain('15,96 mUSD'); // 399.000 VND / 25.000
        expect(rows[0].textContent).toContain('3%');
        expect(rows[0].textContent).toContain('3 ngày / 30 ngày');
        expect(screen.getByTestId('quote-total').textContent).toContain('20,76 mUSD'); // 15,96 + 4,80
        expect(screen.getByTestId('quote-countdown').textContent).toContain('15:00');
        expect(screen.getByTestId('deposit-button').disabled).toBe(false); // Tuần 4: nút đã hoạt động
        expect(fetchLog.find((c) => c.url.endsWith('/api/orders')).body).toEqual({ cart_item_ids: ['c1', 'c2'] });
    });

    it('đếm ngược theo giờ máy chủ, báo sắp hết hạn dưới 60 giây rồi hết hạn; lấy báo giá mới thì đếm lại', async () => {
        await linkAccount();
        vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider());
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Tạo báo giá' }));
        await screen.findByTestId('quote-result');

        await act(async () => {});

        await act(async () => { vi.advanceTimersByTime(300_000); });
        expect(screen.getByTestId('quote-countdown').textContent).toContain('10:00');
        await act(async () => { vi.advanceTimersByTime(545_000); });
        expect(screen.getByTestId('quote-countdown').textContent).toMatch(/00:55.*sắp hết hạn/);
        await act(async () => { vi.advanceTimersByTime(60_000); });
        expect(screen.getByTestId('quote-countdown').textContent).toBe('Báo giá đã hết hạn.');

        fireEvent.click(screen.getByRole('button', { name: 'Lấy báo giá mới' }));
        await waitFor(() => expect(screen.getByTestId('quote-countdown').textContent).toContain('15:00'));
        expect(fetchLog.some((c) => /\/api\/checkout-groups\/.+\/quote$/.test(c.url))).toBe(true);
    });

    it('đã có lô đang chờ: báo lỗi và cho "Tiếp tục lô đang chờ" bằng báo giá mới của chính lô đó', async () => {
        await linkAccount();
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider());
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Tạo báo giá' }));
        await screen.findByTestId('quote-result');
        const firstGroup = [...mock.state.groups.keys()][0];
        // mô phỏng người dùng tải lại trang: panel mới, lô cũ vẫn chờ trên máy chủ
        document.body.innerHTML = '';
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider());
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Tạo báo giá' }));
        const resume = await screen.findByRole('button', { name: 'Làm mới báo giá cho lô này' });
        expect(screen.getByRole('alert').textContent).toMatch(/lô thanh toán chưa hoàn tất/);
        fireEvent.click(resume);
        await screen.findByTestId('quote-result');
        expect(fetchLog.at(-1).url).toContain(`/api/checkout-groups/${firstGroup}/quote`);
        expect(screen.queryByRole('alert')).toBeNull();
    });
});

describe('Web3CheckoutPanel: làm mới báo giá của lô đang chờ + chống bấm dồn (F-07)', () => {
    const linkAccount = async () => {
        const n = await requestWalletNonceAPI(ACCOUNT);
        await linkWalletAPI({ address: ACCOUNT, signature: 's', nonce: n.nonce });
    };
    const groupPayload = (serverTime, id = 'g-pending') => ({
        checkout_group_id: id, total_amount_raw: '15960000', decimals: 6, symbol: 'mUSD', token_address: '0x5FbDB2315678afecb367f032d93F642f64180aa3',
        deadline: serverTime + 900, server_time: serverTime,
        orders: [{ order_id: 'o1', shop_id: 's1', shop_name: 'Cửa hàng Mẫu A', onchain_order_id: '100001', price_vnd: 399000, amount_raw: '15960000',
            fx: '25000.0000', fee_bps: 300, inspection_duration: 259200, dispute_timeout: 2592000 }],
    });
    /** Chèn phản hồi giả cho đúng hai điểm cuối; còn lại đi qua mock. `quote` là hàm trả Promise<Response> do test điều khiển. */
    const intercept = ({ quote }) => {
        const inner = globalThis.fetch;
        const quoteCalls = [];
        globalThis.fetch = vi.fn(async (url, init) => {
            const u = String(url);
            if (u.endsWith('/api/orders') && init?.method === 'POST') {
                return new Response(JSON.stringify({ code: 'PENDING_GROUP_EXISTS', message: 'Bạn đang có lô thanh toán chưa hoàn tất cho sản phẩm này.', checkout_group_id: 'g-pending' }), { status: 409 });
            }
            if (u.endsWith('/api/checkout-groups/g-pending/quote')) { quoteCalls.push(u); return quote(); }
            return inner(url, init);
        });
        return quoteCalls;
    };
    const openPending = async () => {
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider());
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Tạo báo giá' }));
        return screen.findByRole('button', { name: 'Làm mới báo giá cho lô này' });
    };

    it('F-07: nút nói rõ là làm mới, bị khóa trong lúc gọi API, rồi đồng hồ bắt đầu lại từ 15:00', async () => {
        await linkAccount();
        let release;
        const calls = intercept({ quote: () => new Promise((r) => { release = () => r(new Response(JSON.stringify(groupPayload(Math.floor(Date.now() / 1000))), { status: 200 })); }) });
        const refresh = await openPending();
        expect(screen.getByRole('alert').textContent).toMatch(/lô thanh toán chưa hoàn tất/);
        expect(screen.queryByRole('button', { name: 'Tiếp tục lô đang chờ' })).toBeNull(); // nhãn cũ gây hiểu nhầm là "khôi phục phiên"
        expect(refresh.disabled).toBe(false);

        fireEvent.click(refresh);
        await waitFor(() => expect(calls).toHaveLength(1));
        expect(screen.getByRole('button', { name: 'Làm mới báo giá cho lô này' }).disabled).toBe(true); // khóa ngay khi bắt đầu gửi

        release();
        await screen.findByTestId('quote-result');
        expect(screen.queryByRole('alert')).toBeNull();
        expect(screen.getByTestId('quote-countdown').textContent).toContain('15:00');
        expect(screen.getAllByTestId('quote-row')).toHaveLength(1);
        expect(screen.getByRole('button', { name: 'Lấy báo giá mới' }).disabled).toBe(false); // khôi phục sau khi xong
    });

    it('bấm dồn 5 lần liên tiếp chỉ gửi MỘT yêu cầu cấp lại báo giá', async () => {
        await linkAccount();
        const calls = intercept({ quote: async () => new Response(JSON.stringify(groupPayload(Math.floor(Date.now() / 1000))), { status: 200 }) });
        const refresh = await openPending();
        for (let i = 0; i < 5; i += 1) fireEvent.click(refresh);
        await screen.findByTestId('quote-result');
        expect(calls).toHaveLength(1);
    });

    it('đồng hồ không giật: sau khi nhận báo giá mới luôn bắt đầu đúng 15:00, kể cả khi nhịp đếm cũ đã lệch gần 1 giây', async () => {
        await linkAccount();
        vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
        const calls = intercept({ quote: async () => new Response(JSON.stringify(groupPayload(Math.floor(Date.now() / 1000))), { status: 200 }) });
        const refresh = await openPending();
        await act(async () => { vi.advanceTimersByTime(950); }); // chưa tới nhịp 1 giây kế tiếp: state `now` cũ hơn đồng hồ thật ~0,95 giây
        fireEvent.click(refresh);
        // Chờ ĐÚNG tín hiệu "báo giá mới đã commit": gọi API xong và đồng hồ đã hiện. Không chờ `quote-result` vì phần tử này có thể đã có
        // sẵn; khi đó test tua giả 1000ms TRƯỚC khi `group` mới được commit (setInterval mới chưa được tạo) nên tick bị bỏ lỡ và đồng hồ
        // đứng ở 15:00. Lỗi chỉ lộ khi CPU chậm (CI): đã tái hiện 1/12 lần dưới tải, `waitFor` ở cuối KHÔNG cứu được vì nó không tua đồng hồ giả.
        await waitFor(() => expect(calls).toHaveLength(1));
        await screen.findByTestId('quote-countdown');
        await act(async () => { await Promise.resolve(); }); // xả effect còn treo (tạo lại setInterval cho `group` mới) trước khi tua
        expect(screen.getByTestId('quote-countdown').textContent).toContain('15:00'); // không phải 15:01
        await act(async () => { vi.advanceTimersByTime(1000); });
        await waitFor(() => expect(screen.getByTestId('quote-countdown').textContent).toContain('14:59'));
    });

    it('lỗi tạm thời khi làm mới (chain/mạng): hiện lỗi, nút vẫn còn và dùng lại được, không kẹt ở trạng thái đang tải', async () => {
        await linkAccount();
        let fail = true;
        const calls = intercept({ quote: async () => (fail
            ? new Response(JSON.stringify({ code: 'CHAIN_UNAVAILABLE', message: 'Không kết nối được blockchain, hãy thử lại sau ít phút.' }), { status: 503 })
            : new Response(JSON.stringify(groupPayload(Math.floor(Date.now() / 1000))), { status: 200 })) });
        const refresh = await openPending();
        fireEvent.click(refresh);
        expect(await screen.findByText('Không kết nối được blockchain, hãy thử lại sau ít phút.')).toBeTruthy();
        const again = screen.getByRole('button', { name: 'Làm mới báo giá cho lô này' });
        expect(again.disabled).toBe(false);
        fail = false;
        fireEvent.click(again);
        await screen.findByTestId('quote-result');
        expect(calls).toHaveLength(2);
        expect(screen.queryByRole('button', { name: 'Làm mới báo giá cho lô này' })).toBeNull(); // đã có báo giá: nút dành cho lô chờ biến mất
    });

    it('lô không còn làm mới được (INVALID_STATE): hiện lỗi và KHÔNG mời thử lại', async () => {
        await linkAccount();
        intercept({ quote: async () => new Response(JSON.stringify({ code: 'INVALID_STATE', message: 'Lô thanh toán này không còn ở trạng thái chờ thanh toán.' }), { status: 409 }) });
        fireEvent.click(await openPending());
        expect(await screen.findByText('Lô thanh toán này không còn ở trạng thái chờ thanh toán.')).toBeTruthy();
        expect(screen.queryByRole('button', { name: 'Làm mới báo giá cho lô này' })).toBeNull();
    });

    it('"Lấy báo giá mới" và "Tạo báo giá" cũng không gửi trùng khi bấm dồn', async () => {
        await linkAccount();
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider());
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        const create = await screen.findByRole('button', { name: 'Tạo báo giá' });
        for (let i = 0; i < 4; i += 1) fireEvent.click(create);
        await screen.findByTestId('quote-result');
        expect(fetchLog.filter((c) => c.url.endsWith('/api/orders'))).toHaveLength(1);
        const requote = screen.getByRole('button', { name: 'Lấy báo giá mới' });
        for (let i = 0; i < 4; i += 1) fireEvent.click(requote);
        await waitFor(() => expect(fetchLog.filter((c) => /\/quote$/.test(c.url))).toHaveLength(1));
    });
});

describe('Web3CheckoutPanel: shop chưa liên kết ví nhận tiền (BR-07)', () => {
    const linkAccount = async () => {
        const n = await requestWalletNonceAPI(ACCOUNT);
        await linkWalletAPI({ address: ACCOUNT, signature: 's', nonce: n.nonce });
    };

    it('nêu đích danh shop và KHÔNG dẫn người mua tới /wallet (họ không tự sửa được)', async () => {
        await linkAccount();
        mock.state.unlinkedShopIds.add('mock-shop-2');
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider());
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Tạo báo giá' }));
        const alert = await screen.findByRole('alert');
        expect(alert.textContent).toContain('Cửa hàng «Cửa hàng Mẫu B» chưa liên kết ví nhận tiền');
        expect(within(alert).queryByRole('link', { name: 'Liên kết ví' })).toBeNull();
        expect(screen.queryByTestId('quote-result')).toBeNull();
    });

    it.each(['merchant', 'MERCHANT', 'Merchant'])('nhận diện bên vi phạm không phân biệt hoa/thường (%s)', async (party) => {
        await linkAccount();
        const inner = globalThis.fetch;
        globalThis.fetch = vi.fn(async (url, init) => (String(url).endsWith('/api/orders') && init?.method === 'POST'
            ? new Response(JSON.stringify({ code: 'WALLET_NOT_LINKED', message: 'x', party, shop_id: 's9', shop_name: 'Shop Chín' }), { status: 409 })
            : inner(url, init)));
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider());
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Tạo báo giá' }));
        expect((await screen.findByRole('alert')).textContent).toContain('Cửa hàng «Shop Chín» chưa liên kết ví nhận tiền');
    });

    it('thiếu tên shop thì dùng câu chung, vẫn không dẫn tới /wallet', async () => {
        await linkAccount();
        const inner = globalThis.fetch;
        globalThis.fetch = vi.fn(async (url, init) => (String(url).endsWith('/api/orders') && init?.method === 'POST'
            ? new Response(JSON.stringify({ code: 'WALLET_NOT_LINKED', message: 'x', party: 'merchant' }), { status: 409 })
            : inner(url, init)));
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider());
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Tạo báo giá' }));
        const alert = await screen.findByRole('alert');
        expect(alert.textContent).toContain('Có cửa hàng trong đơn hàng chưa liên kết ví nhận tiền');
        expect(within(alert).queryByRole('link')).toBeNull();
    });

    it('ví của CHÍNH người mua chưa liên kết (party = buyer) thì vẫn dẫn tới /wallet', async () => {
        await linkAccount();
        const inner = globalThis.fetch;
        globalThis.fetch = vi.fn(async (url, init) => (String(url).endsWith('/api/orders') && init?.method === 'POST'
            ? new Response(JSON.stringify({ code: 'WALLET_NOT_LINKED', message: 'Bạn cần liên kết ví trước khi thanh toán Web3.', party: 'buyer' }), { status: 409 })
            : inner(url, init)));
        mountWith(<Web3CheckoutPanel cartItemIds={['c1']} />, fakeProvider());
        fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
        fireEvent.click(await screen.findByRole('button', { name: 'Tạo báo giá' }));
        const alert = await screen.findByRole('alert');
        expect(alert.textContent).toContain('Bạn cần liên kết ví trước khi thanh toán Web3.');
        expect(within(alert).getByRole('link', { name: 'Liên kết ví' }).getAttribute('href')).toBe('/wallet');
    });
});

describe('Trang Checkout: ẩn/khóa lựa chọn Web3 khi có shop chưa liên kết ví (F-08)', () => {
    const items = [
        { cartItemId: 'c1', productId: 'p1', name: 'Áo thun', quantity: 1, unitPrice: 399000, shopName: 'Cửa hàng Mẫu A' },
        { cartItemId: 'c2', productId: 'p2', name: 'Quần', quantity: 2, unitPrice: 60000, shopName: 'Cửa hàng Mẫu B' },
    ];
    const WARNING = 'Phương thức Thanh toán Web3 tạm thời không khả dụng vì có cửa hàng trong đơn hàng chưa liên kết ví nhận tiền.';
    const renderCheckout = () => render(
        <MemoryRouter initialEntries={[{ pathname: '/checkout', state: { items } }]}>
            <WalletProvider provider={fakeProvider()} deployment={deployment}><Checkout /></WalletProvider>
        </MemoryRouter>,
    );
    const web3Radio = async () => within(await screen.findByTestId('web3-method')).getByRole('radio');
    const eligibilityCalls = () => fetchLog.filter((c) => c.url.endsWith('/api/orders/eligibility'));

    it('có shop chưa liên kết: radio Web3 bị vô hiệu hóa, hiện đúng cảnh báo + tên shop, không mở được panel', async () => {
        mock.state.unlinkedShopIds.add('mock-shop-2');
        renderCheckout();
        const radio = await web3Radio();
        await waitFor(() => expect(radio.disabled).toBe(true));
        expect((await screen.findByTestId('web3-unavailable')).textContent).toContain(WARNING);
        expect(screen.getByTestId('web3-unavailable').textContent).toContain('Cửa hàng chưa liên kết: Cửa hàng Mẫu B.');
        expect(screen.getByTestId('web3-method').getAttribute('aria-disabled')).toBe('true');
        fireEvent.click(radio);
        expect(screen.queryByTestId('web3-panel')).toBeNull();
        expect(eligibilityCalls()[0].body).toEqual({ cart_item_ids: ['c1', 'c2'] });
    });

    it('luồng thanh toán cũ không bị ảnh hưởng khi Web3 bị khóa (chọn COD vẫn ra khung nhập PIN)', async () => {
        mock.state.unlinkedShopIds.add('mock-shop-1');
        renderCheckout();
        await waitFor(async () => expect((await web3Radio()).disabled).toBe(true));
        expect(screen.getByText('Enter 6-Digit PIN:')).toBeTruthy();
        fireEvent.click(screen.getByText(/Cash on Delivery/));
        expect(screen.getByText('Enter 6-Digit PIN:')).toBeTruthy();
        expect(screen.getByRole('button', { name: 'PROCESS PAYMENT' })).toBeTruthy();
    });

    it('mọi shop đã liên kết: không cảnh báo, radio dùng được và mở panel Web3', async () => {
        renderCheckout();
        const radio = await web3Radio();
        await waitFor(() => expect(eligibilityCalls()).toHaveLength(1));
        await waitFor(() => expect(radio.disabled).toBe(false));
        expect(screen.queryByTestId('web3-unavailable')).toBeNull();
        fireEvent.click(radio);
        expect(await screen.findByTestId('web3-panel')).toBeTruthy();
        expect(screen.queryByText('Enter 6-Digit PIN:')).toBeNull();
    });

    it('lỡ chọn Web3 trước khi có kết quả rồi bị chặn: tự chuyển về phương thức khác, không kẹt ở ngõ cụt', async () => {
        mock.state.unlinkedShopIds.add('mock-shop-2');
        const inner = globalThis.fetch;
        let release;
        globalThis.fetch = vi.fn(async (url, init) => {
            if (String(url).endsWith('/api/orders/eligibility')) await new Promise((r) => { release = r; }); // trả lời chậm
            return inner(url, init);
        });
        renderCheckout();
        const radio = await web3Radio();
        await waitFor(() => expect(radio.disabled).toBe(false)); // đang kiểm tra: chưa khóa
        fireEvent.click(radio);
        expect(await screen.findByTestId('web3-panel')).toBeTruthy();
        await waitFor(() => expect(release).toBeTypeOf('function'));
        release();
        await waitFor(() => expect(screen.queryByTestId('web3-panel')).toBeNull());
        expect(radio.disabled).toBe(true);
        expect(radio.checked).toBe(false);
        expect(screen.getByText('Enter 6-Digit PIN:')).toBeTruthy(); // quay lại luồng thường
    });

    it('không hỏi được điều kiện (lỗi mạng/máy chủ): KHÔNG chặn, để panel báo lỗi thật ở bước tạo báo giá', async () => {
        const inner = globalThis.fetch;
        globalThis.fetch = vi.fn(async (url, init) => (String(url).endsWith('/api/orders/eligibility')
            ? new Response(JSON.stringify({ code: 'internal_error', message: 'x' }), { status: 500 })
            : inner(url, init)));
        renderCheckout();
        const radio = await web3Radio();
        await waitFor(() => expect(eligibilityCalls().length + fetchLog.length).toBeGreaterThan(0));
        await new Promise((r) => setTimeout(r, 30));
        expect(radio.disabled).toBe(false);
        expect(screen.queryByTestId('web3-unavailable')).toBeNull();
    });

    it('máy chủ chưa cấu hình Web3 (503 WEB3_NOT_CONFIGURED): khóa với thông báo riêng, không đổ lỗi cho cửa hàng', async () => {
        const inner = globalThis.fetch;
        globalThis.fetch = vi.fn(async (url, init) => (String(url).endsWith('/api/orders/eligibility')
            ? new Response(JSON.stringify({ code: 'WEB3_NOT_CONFIGURED', message: 'x' }), { status: 503 })
            : inner(url, init)));
        renderCheckout();
        const radio = await web3Radio();
        await waitFor(() => expect(radio.disabled).toBe(true));
        const note = screen.getByTestId('web3-unavailable').textContent;
        expect(note).toContain('hiện chưa khả dụng trên máy chủ');
        expect(note).not.toContain('chưa liên kết ví nhận tiền');
    });
});

describe('Navbar có liên kết Ví đúng vai trò', () => {
    const renderNav = () => render(<MemoryRouter><Navbar /></MemoryRouter>);
    it.each([['user', true], ['seller', true], ['admin', false]])('%s -> %s', (role, shown) => {
        sessionStorage.setItem('user', JSON.stringify({ id: 'x', name: 'N', role }));
        renderNav();
        expect(Boolean(screen.queryByRole('link', { name: /Ví/ }))).toBe(shown);
    });
    it('chưa đăng nhập: không có', () => {
        sessionStorage.clear();
        renderNav();
        expect(screen.queryByRole('link', { name: /Ví/ })).toBeNull();
    });
});
