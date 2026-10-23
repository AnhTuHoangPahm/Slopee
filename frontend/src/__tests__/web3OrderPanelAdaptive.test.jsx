import { configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import MyOrders from '../pages/MyOrders';
import { WalletProvider } from '../hooks/useWallet';
import { parseDeployment } from '../lib/chain';
import * as paymentsApi from '../api/payments';

// Polling THÍCH ỨNG ở mức giao diện (PROGRESS Tuần 5 mục 11): không truyền `pollMs`, nên chu kỳ do lib/orderTimer::nextPollDelayMs quyết định.
// Đơn DELIVERED còn nhiều ngày thì hỏi chậm (15 giây); thao tác ví thì `boost()` hỏi lại NGAY và hỏi nhanh (3 giây) tới khi thấy trạng thái đích.
configure({ asyncUtilTimeout: 6000 });
vi.setConfig({ testTimeout: 20000 });
vi.mock('../api/payments', () => ({ fetchOrdersAPI: vi.fn(), updateOrderStatusAPI: vi.fn() }));

const BUYER = '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc';
const OTHER = '0x976EA74026E726554dB657fA54763abd0C3a0aa9';
const deployment = parseDeployment({
    chainId: 31337, escrow: '0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512', mockUSD: '0x5FbDB2315678afecb367f032d93F642f64180aa3',
    deployBlock: 1, token: { symbol: 'MUSD', decimals: 6 },
});
const provider = (account = BUYER, chainId = '0x7a69') => ({
    request: vi.fn(async ({ method }) => {
        if (method === 'eth_requestAccounts') return [account];
        if (method === 'eth_accounts') return [];
        if (method === 'eth_chainId') return chainId;
        throw Object.assign(new Error(`unhandled ${method}`), { code: -32601 });
    }),
    on: vi.fn(), removeListener: vi.fn(),
});

const NOW = 1_800_000_000;
const web3 = (over = {}) => ({
    onchain_order_id: 100001, checkout_group_id: 'g1', buyer_wallet: BUYER.toLowerCase(), status: 'DELIVERED', delivered_at: NOW,
    inspection_duration: 259200, disputed_at: null, dispute_timeout: 2592000, fee_bps: 300, amount_raw: '15960000', token_symbol: 'MUSD', anomaly: false, ...over,
});
const order = (id, w3, over = {}) => ({
    orderId: id, totalAmount: 399000, created_at: '2026-10-16T08:00:00Z', status: 'paid',
    items: [{ productName: `Áo ${id}`, quantity: 1, unitPrice: 399000, shopName: `Shop ${id}`, selectedVariants: null }], web3: w3, ...over,
});
const apiStatus = (o) => ({ order_id: 'x', status: 'DELIVERED', delivered_at: NOW, inspection_duration: 259200, disputed_at: null, dispute_timeout: 2592000, anomaly: false, server_time: NOW + 60, ...o });
const tx = (hash = `0x${'e1'.repeat(32)}`) => ({ hash, wait: vi.fn(async () => ({ status: 1 })) });

/** Trạng thái "máy chủ" thay đổi được giữa các lần poll, theo từng mã đơn. */
function serverState(initial = {}) {
    const st = { ...initial };
    const fetchStatus = vi.fn(async (code) => apiStatus(st[code] ?? {}));
    return { st, fetchStatus };
}

async function show(orders, { fetchStatus, account = BUYER, chainId, escrow, saveNote, connect = true } = {}) {
    paymentsApi.fetchOrdersAPI.mockResolvedValue({ orders });
    const escrowFactory = vi.fn(async () => escrow);
    render(
        <MemoryRouter><WalletProvider provider={provider(account, chainId)} deployment={deployment}>
            <MyOrders hideNavbar escrowFactory={escrowFactory} fetchStatus={fetchStatus} saveNote={saveNote} />
        </WalletProvider></MemoryRouter>,
    );
    await screen.findAllByTestId('order-card');
    if (connect) fireEvent.click((await screen.findAllByTestId('gate-connect'))[0]);
    return { escrowFactory };
}
const panel = (code) => document.querySelector(`[data-order="${code}"]`);
const inPanel = (code) => within(panel(code));

beforeEach(() => {
    sessionStorage.setItem('token', 't');
    sessionStorage.setItem('user', JSON.stringify({ id: 'u1', name: 'An', role: 'user' }));
    vi.spyOn(window, 'confirm').mockReturnValue(true);
});
afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

describe('Web3OrderPanel: polling thích ứng + tăng tốc khi thao tác ví', () => {
    it('đơn DELIVERED còn nhiều ngày: KHÔNG hỏi dồn (không còn 3 giây/lần suốt thời hạn kiểm tra)', async () => {
        const srv = serverState();
        await show([order('o1', web3())], { fetchStatus: srv.fetchStatus, escrow: { earlyRelease: vi.fn(), raiseDispute: vi.fn() } });
        await waitFor(() => expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(false));
        const calls = srv.fetchStatus.mock.calls.length;
        expect(calls).toBeGreaterThanOrEqual(1);
        await new Promise((r) => setTimeout(r, 400));                       // chu kỳ cố định cũ sẽ hỏi ~2 lần mỗi 400 ms ở test, hoặc 3 giây ở thật
        expect(srv.fetchStatus.mock.calls.length).toBe(calls);
    });

    it('bấm "Đã nhận hàng": hỏi lại NGAY dù đang ở chu kỳ chậm, rồi thấy COMPLETED trong vài giây (không phải chờ 15 giây)', async () => {
        const srv = serverState();
        const escrow = { earlyRelease: vi.fn(async () => tx()), raiseDispute: vi.fn() };
        await show([order('o1', web3())], { fetchStatus: srv.fetchStatus, escrow });
        await waitFor(() => expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(false));
        const before = srv.fetchStatus.mock.calls.length;
        await new Promise((r) => setTimeout(r, 200));
        expect(srv.fetchStatus.mock.calls.length).toBe(before);              // đang chậm

        fireEvent.click(inPanel('o1').getByTestId('receive-btn'));
        await waitFor(() => expect(escrow.earlyRelease).toHaveBeenCalledWith(100001n));
        await waitFor(() => expect(srv.fetchStatus.mock.calls.length).toBeGreaterThan(before), { timeout: 2000 });   // boost: hỏi lại tức thì

        srv.st.o1 = { status: 'COMPLETED' };                                 // Indexer ghi OrderCompleted
        const started = Date.now();
        await waitFor(() => expect(inPanel('o1').getByTestId('status-badge').dataset.status).toBe('COMPLETED'), { timeout: 5000 });
        expect(Date.now() - started).toBeLessThan(4500);                     // chu kỳ nhanh 3 giây, không phải 15 giây
        const calls = srv.fetchStatus.mock.calls.length;
        await new Promise((r) => setTimeout(r, 300));
        expect(srv.fetchStatus.mock.calls.length).toBe(calls);               // trạng thái cuối: polling dừng hẳn
    });
});
