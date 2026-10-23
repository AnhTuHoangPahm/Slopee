import { configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import MerchantWeb3Panel from '../components/MerchantWeb3Panel';
import { WalletProvider } from '../hooks/useWallet';
import { parseDeployment } from '../lib/chain';

// Tuần 7 [A] (UC-07): khung đơn Web3 + "Khoản chờ rút" của Merchant. Ví/hợp đồng/API được giả (không cần Anvil).
configure({ asyncUtilTimeout: 6000 });
vi.setConfig({ testTimeout: 20000 });

const SELLER = '0x976EA74026E726554dB657fA54763abd0C3a0aa9';
const OTHER = '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc';
const TOKEN = '0x5FbDB2315678afecb367f032d93F642f64180aa3';
const deployment = parseDeployment({ chainId: 31337, escrow: '0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512', mockUSD: TOKEN, deployBlock: 1, token: { symbol: 'MUSD', decimals: 6 } });
const provider = (account = SELLER, chainId = '0x7a69') => ({
    request: vi.fn(async ({ method }) => {
        if (method === 'eth_requestAccounts') return [account];
        if (method === 'eth_accounts') return [];
        if (method === 'eth_chainId') return chainId;
        throw Object.assign(new Error(`unhandled ${method}`), { code: -32601 });
    }),
    on: vi.fn(), removeListener: vi.fn(),
});
const order = (id, status, over = {}) => ({
    order_id: id, onchain_order_id: '1001', status, buyer_name: 'Nguyễn An', items: [{ name: 'Áo thun', quantity: 2, variants: null }], price_vnd: 399000,
    amount_raw: '15960000', net_amount_raw: '15481200', fee_amount_raw: '478800', fee_bps: 300, token: TOKEN.toLowerCase(), symbol: 'mUSD', decimals: 6,
    merchant_wallet: SELLER.toLowerCase(), chain_created_at: 1_800_000_000, delivered_at: null, disputed_at: null, closed_at: null,
    delivery_deadline: null, release_at: null, force_resolve_at: null, ...over,
});
const PENDING = { token: 'ETH', address: SELLER.toLowerCase(), amount_raw: '5000000000000000', symbol: 'ETH', decimals: 18 };
const body = (over = {}) => ({ wallet: SELLER.toLowerCase(), orders: [], pending: [], ...over });
const tx = (hash = `0x${'c1'.repeat(32)}`) => ({ hash, wait: vi.fn(async () => ({ status: 1 })) });

async function show(data, { account = SELLER, chainId, escrow, connect = true } = {}) {
    const state = { data };
    const fetchOrders = vi.fn(async () => state.data);
    const escrowFactory = vi.fn(async () => escrow);
    render(
        <MemoryRouter><WalletProvider provider={provider(account, chainId)} deployment={deployment}>
            <MerchantWeb3Panel fetchOrders={fetchOrders} escrowFactory={escrowFactory} pollMs={25} />
        </WalletProvider></MemoryRouter>,
    );
    await screen.findByTestId('pending-section');
    if (connect) {
        const c = screen.queryByTestId('gate-connect');
        if (c) fireEvent.click(c);
    }
    return { state, fetchOrders, escrowFactory };
}
afterEach(() => vi.restoreAllMocks());

describe('MerchantWeb3Panel — danh sách đơn', () => {
    it('đơn rỗng: báo chưa có đơn, không có khoản chờ rút, giải thích tiền tự về ví', async () => {
        await show(body(), { connect: false });
        expect(screen.getByTestId('merchant-empty')).toBeTruthy();
        expect(screen.getByTestId('pending-empty').textContent).toMatch(/tự chuyển vào ví/);
    });

    it('hiện từng đơn với trạng thái theo góc nhìn người bán, số tiền sau phí và câu giải thích', async () => {
        await show(body({ orders: [order('o-locked-1', 'LOCKED', { delivery_deadline: 1_801_209_600 }), order('o-done-22', 'COMPLETED', { closed_at: 1_800_100_000 })] }), { connect: false });
        const locked = within(screen.getByTestId('merchant-order-o-locked-1'));
        expect(locked.getByTestId('merchant-status').textContent).toBe('Chờ giao hàng');
        expect(locked.getByTestId('merchant-note').textContent).toMatch(/người mua có quyền hủy/);
        expect(screen.getByTestId('merchant-order-o-locked-1').textContent).toMatch(/15,96 mUSD/);
        expect(screen.getByTestId('merchant-order-o-locked-1').textContent).toMatch(/15,4812 mUSD/);
        expect(screen.getByTestId('merchant-order-o-locked-1').textContent).toMatch(/Nguyễn An/);
        expect(within(screen.getByTestId('merchant-order-o-done-22')).getByTestId('merchant-note').textContent).toMatch(/Bạn đã nhận 15,4812 mUSD/);
        expect(screen.getByTestId('sum-escrow').textContent).toBe('15,4812 mUSD');
        expect(screen.getByTestId('sum-received').textContent).toBe('15,4812 mUSD');
    });

    it('đơn tranh chấp có liên kết sang trang phán quyết, đơn khác thì không', async () => {
        await show(body({ orders: [order('o-disp', 'DISPUTED', { force_resolve_at: 1_802_592_000 }), order('o-lock', 'LOCKED')] }), { connect: false });
        expect(within(screen.getByTestId('merchant-order-o-disp')).getByTestId('dispute-link').getAttribute('href')).toBe('/disputes/o-disp');
        expect(within(screen.getByTestId('merchant-order-o-lock')).queryByTestId('dispute-link')).toBeNull();
    });

    it('bộ lọc theo trạng thái', async () => {
        await show(body({ orders: [order('a-lock', 'LOCKED'), order('b-ref', 'REFUNDED')] }), { connect: false });
        fireEvent.change(screen.getByLabelText('Lọc theo trạng thái'), { target: { value: 'REFUNDED' } });
        expect(screen.queryByTestId('merchant-order-a-lock')).toBeNull();
        expect(screen.getByTestId('merchant-order-b-ref')).toBeTruthy();
        fireEvent.change(screen.getByLabelText('Lọc theo trạng thái'), { target: { value: 'DELIVERED' } });
        expect(screen.getByTestId('merchant-filter-empty')).toBeTruthy();
    });

    it('chưa liên kết ví: cảnh báo kèm đường dẫn /wallet', async () => {
        await show(body({ wallet: null }), { connect: false });
        expect(within(screen.getByTestId('no-wallet')).getByRole('link').getAttribute('href')).toBe('/wallet');
    });

    it('tên người mua chứa HTML hiển thị như chữ', async () => {
        await show(body({ orders: [order('x-html', 'LOCKED', { buyer_name: '<img src=x onerror=alert(1)>' })] }), { connect: false });
        expect(document.querySelector('img')).toBeNull();
        expect(screen.getByTestId('merchant-order-x-html').textContent).toContain('<img src=x');
    });

    it('lỗi tải: báo lỗi nhưng không xóa dữ liệu đã có và tự thử lại', async () => {
        const state = { fail: false };
        const fetchOrders = vi.fn(async () => { if (state.fail) throw Object.assign(new Error('x'), { code: 'CHAIN_UNAVAILABLE', message: 'Mất kết nối' }); return body({ orders: [order('keep-1', 'LOCKED')] }); });
        render(<MemoryRouter><WalletProvider provider={provider()} deployment={deployment}><MerchantWeb3Panel fetchOrders={fetchOrders} pollMs={25} /></WalletProvider></MemoryRouter>);
        await screen.findByTestId('merchant-order-keep-1');
        state.fail = true;
        await screen.findByRole('alert');
        expect(screen.getByTestId('merchant-order-keep-1')).toBeTruthy();
    });
});

describe('MerchantWeb3Panel — rút khoản chờ rút (claimPending)', () => {
    it('đường vui: kết nối -> Rút -> đúng hàm ETH -> chỉ xong khi API bỏ khoản chờ rút', async () => {
        const escrow = { pendingWithdrawals: vi.fn(async () => 5_000_000_000_000_000n), claimPending: vi.fn(async () => tx()) };
        const { state } = await show(body({ pending: [PENDING] }), { escrow });
        expect(screen.getByTestId('pending-ETH').textContent).toMatch(/0,005 ETH/);
        const btn = await screen.findByTestId('claim-button');
        fireEvent.click(btn);
        await waitFor(() => expect(escrow.claimPending).toHaveBeenCalledWith('0x0000000000000000000000000000000000000000'));
        await waitFor(() => expect(screen.getByTestId('claim-button').textContent).toMatch(/chờ hệ thống ghi nhận/));
        expect(screen.queryByTestId('claim-done')).toBeNull();            // biên nhận đã có nhưng API vẫn còn khoản: chưa coi là xong (DD-04, BR-09)
        expect(screen.getByTestId('claim-button').disabled).toBe(true);

        state.data = body({ pending: [] });                               // Indexer ghi PendingClaimed
        await screen.findByTestId('claim-done');
        expect(screen.queryByTestId('claim-button')).toBeNull();
    });

    it('bấm dồn chỉ gửi MỘT giao dịch', async () => {
        let release;
        const escrow = { pendingWithdrawals: async () => 1n, claimPending: vi.fn(() => new Promise((r) => { release = () => r(tx()); })) };
        await show(body({ pending: [PENDING] }), { escrow });
        const btn = await screen.findByTestId('claim-button');
        fireEvent.click(btn); fireEvent.click(btn); fireEvent.click(btn);
        await waitFor(() => expect(escrow.claimPending).toHaveBeenCalledTimes(1));
        release();
    });

    it('số dư thật trên chuỗi đã bằng 0: không gửi giao dịch, báo rõ', async () => {
        const escrow = { pendingWithdrawals: vi.fn(async () => 0n), claimPending: vi.fn() };
        await show(body({ pending: [PENDING] }), { escrow });
        fireEvent.click(await screen.findByTestId('claim-button'));
        expect((await screen.findByTestId('claim-error')).textContent).toMatch(/Không còn khoản nào/);
        expect(escrow.claimPending).not.toHaveBeenCalled();
    });

    it('hủy trong MetaMask: thông báo nhẹ, đóng được, bấm lại được', async () => {
        const escrow = { pendingWithdrawals: async () => 1n, claimPending: vi.fn(async () => { throw Object.assign(new Error('r'), { code: 4001 }); }) };
        await show(body({ pending: [PENDING] }), { escrow });
        fireEvent.click(await screen.findByTestId('claim-button'));
        expect((await screen.findByTestId('claim-error')).textContent).toMatch(/Bạn đã hủy thao tác/);
        expect(screen.getByTestId('claim-button').disabled).toBe(false);
    });

    it('sai ví: không có nút Rút, nói rõ ví nào mới rút được', async () => {
        const escrow = { pendingWithdrawals: vi.fn(), claimPending: vi.fn() };
        await show(body({ pending: [PENDING] }), { escrow, account: OTHER });
        expect(await screen.findByTestId('gate-wrong-account')).toBeTruthy();
        expect(screen.queryByTestId('claim-button')).toBeNull();
        expect(escrow.claimPending).not.toHaveBeenCalled();
    });

    it('sai mạng: có nút chuyển mạng, không có nút Rút', async () => {
        await show(body({ pending: [PENDING] }), { chainId: '0x1' });
        expect(await screen.findByTestId('gate-switch')).toBeTruthy();
        expect(screen.queryByTestId('claim-button')).toBeNull();
    });

    it('chưa kết nối ví: có nút Kết nối, chưa có nút Rút', async () => {
        await show(body({ pending: [PENDING] }), { connect: false });
        expect(screen.getByTestId('gate-connect')).toBeTruthy();
        expect(screen.queryByTestId('claim-button')).toBeNull();
    });

    it('hai khoản ở hai token: mỗi khoản một khối riêng', async () => {
        const mUsd = { token: TOKEN.toLowerCase(), address: SELLER.toLowerCase(), amount_raw: '2500000', symbol: 'mUSD', decimals: 6 };
        await show(body({ pending: [PENDING, mUsd] }), { connect: false });
        expect(screen.getByTestId('pending-ETH')).toBeTruthy();
        expect(screen.getByTestId(`pending-${TOKEN.toLowerCase()}`).textContent).toMatch(/2,50 mUSD/);
    });
});
