import { configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import MyOrders from '../pages/MyOrders';
import { WalletProvider } from '../hooks/useWallet';
import { parseDeployment } from '../lib/chain';
import * as paymentsApi from '../api/payments';

// Tuần 5 [F] (UC-04, UC-05): "Đơn của tôi" với đơn Web3: đồng hồ kiểm tra, "Đã nhận hàng" (earlyRelease), "Khiếu nại" (raiseDispute).
// Ví/hợp đồng/API trạng thái được giả bằng đối tượng cùng giao diện (không cần Anvil); chuỗi thật kiểm ở test tích hợp.
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
            <MyOrders hideNavbar escrowFactory={escrowFactory} fetchStatus={fetchStatus} saveNote={saveNote} pollMs={25} />
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

describe('MyOrders — đơn cũ không đổi', () => {
    it('đơn cũ giữ nút Mark Received/Cancel và không có khung Web3', async () => {
        paymentsApi.fetchOrdersAPI.mockResolvedValue({ orders: [order('legacy', null)] });
        render(<MemoryRouter><WalletProvider provider={provider()} deployment={deployment}><MyOrders hideNavbar /></WalletProvider></MemoryRouter>);
        expect(await screen.findByText(/Mark Received/)).toBeTruthy();
        expect(screen.getByText(/Cancel Order/)).toBeTruthy();
        expect(screen.queryByTestId('web3-panel')).toBeNull();
    });
});

describe('MyOrders — đơn Web3 đang kiểm tra (DELIVERED)', () => {
    it('khóa nút cũ, hiện đồng hồ theo giờ máy chủ và số tiền ký quỹ', async () => {
        const { fetchStatus } = serverState({ o1: { server_time: NOW + 60 } });
        await show([order('o1', web3())], { fetchStatus });
        expect(screen.queryByText(/Mark Received/)).toBeNull();
        expect(screen.queryByText(/Cancel Order/)).toBeNull();
        const t = await inPanel('o1').findByTestId('countdown');
        await waitFor(() => expect(t.textContent).toMatch(/Còn 2 ngày 23:59:\d\d để kiểm tra hàng/));
        expect(inPanel('o1').getByText(/15,96 MUSD|15\.96 MUSD/)).toBeTruthy();
        expect(inPanel('o1').getByTestId('status-badge').dataset.status).toBe('DELIVERED');
    });

    it('chưa kết nối ví: nút bị khóa và có nút kết nối; kết nối xong mới bật', async () => {
        const { fetchStatus } = serverState();
        await show([order('o1', web3())], { fetchStatus, connect: false });
        expect((await inPanel('o1').findByTestId('receive-btn')).disabled).toBe(true);
        fireEvent.click(inPanel('o1').getByTestId('gate-connect'));
        await waitFor(() => expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(false));
        expect(inPanel('o1').queryByTestId('gate-connect')).toBeNull();
    });

    it('ví khác ví đã ký quỹ: cảnh báo, không bật nút', async () => {
        const { fetchStatus } = serverState();
        await show([order('o1', web3())], { fetchStatus, account: OTHER });
        expect(await inPanel('o1').findByTestId('gate-wrong-account')).toBeTruthy();
        expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(true);
        expect(inPanel('o1').getByTestId('dispute-btn').disabled).toBe(true);
    });

    it('sai mạng: có nút chuyển mạng', async () => {
        const { fetchStatus } = serverState();
        await show([order('o1', web3())], { fetchStatus, chainId: '0x1' });
        expect(await inPanel('o1').findByTestId('gate-switch')).toBeTruthy();
        expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(true);
    });

    it('hết hạn kiểm tra: đồng hồ báo hết, khóa Khiếu nại, vẫn cho Đã nhận hàng', async () => {
        const { fetchStatus } = serverState({ o1: { server_time: NOW + 259200 + 5 } });
        await show([order('o1', web3())], { fetchStatus });
        await waitFor(() => expect(inPanel('o1').getByTestId('countdown').dataset.state).toBe('over'));
        expect(inPanel('o1').getByTestId('dispute-btn').disabled).toBe(true);
        expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(false);
    });
});

describe('MyOrders — "Đã nhận hàng" (earlyRelease)', () => {
    it('đường vui: gọi earlyRelease đúng id on-chain, chờ Indexer, chỉ COMPLETED khi API báo', async () => {
        const srv = serverState();
        const escrow = { earlyRelease: vi.fn(async () => tx()), raiseDispute: vi.fn() };
        await show([order('o1', web3())], { fetchStatus: srv.fetchStatus, escrow });
        await waitFor(() => expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(false));
        fireEvent.click(inPanel('o1').getByTestId('receive-btn'));

        await waitFor(() => expect(escrow.earlyRelease).toHaveBeenCalledWith(100001n));
        await waitFor(() => expect(inPanel('o1').getByTestId('action-progress').dataset.step).toBe('WAITING_INDEXER'));
        // biên nhận đã có nhưng API vẫn DELIVERED: KHÔNG được tự coi là hoàn tất (DD-04)
        expect(inPanel('o1').getByTestId('status-badge').dataset.status).toBe('DELIVERED');
        expect(inPanel('o1').getByTestId('action-progress').textContent).toMatch(/chờ hệ thống xác nhận/);
        expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(true);        // khóa trong lúc chờ: không bấm dồn

        srv.st.o1 = { status: 'COMPLETED' };                                             // Indexer ghi OrderCompleted
        await waitFor(() => expect(inPanel('o1').getByTestId('status-badge').dataset.status).toBe('COMPLETED'));
        await waitFor(() => expect(inPanel('o1').getByTestId('action-progress').dataset.step).toBe('DONE'));
        expect(inPanel('o1').queryByTestId('receive-btn')).toBeNull();
        const calls = srv.fetchStatus.mock.calls.length;
        await new Promise((r) => setTimeout(r, 120));
        expect(srv.fetchStatus.mock.calls.length).toBe(calls);                          // trạng thái cuối: polling dừng hẳn
    });

    it('không xác nhận (confirm = hủy): không gọi ví', async () => {
        window.confirm.mockReturnValue(false);
        const escrow = { earlyRelease: vi.fn(async () => tx()) };
        await show([order('o1', web3())], { fetchStatus: serverState().fetchStatus, escrow });
        await waitFor(() => expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(false));
        fireEvent.click(inPanel('o1').getByTestId('receive-btn'));
        await new Promise((r) => setTimeout(r, 60));
        expect(escrow.earlyRelease).not.toHaveBeenCalled();
        expect(inPanel('o1').queryByTestId('action-progress')).toBeNull();
    });

    it('người dùng hủy trong MetaMask: thông báo nhẹ, nút bật lại để thử tiếp', async () => {
        const escrow = { earlyRelease: vi.fn(async () => { throw Object.assign(new Error('rejected'), { code: 4001 }); }) };
        await show([order('o1', web3())], { fetchStatus: serverState().fetchStatus, escrow });
        await waitFor(() => expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(false));
        fireEvent.click(inPanel('o1').getByTestId('receive-btn'));
        await waitFor(() => expect(inPanel('o1').getByTestId('action-progress').dataset.step).toBe('FAILED'));
        expect(inPanel('o1').getByTestId('action-progress').textContent).toMatch(/Bạn đã hủy thao tác/);
        expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(false);
    });

    it('revert "Not delivered": báo đơn không còn ở trạng thái chờ kiểm tra', async () => {
        const escrow = { earlyRelease: vi.fn(async () => tx('0x1')) };
        escrow.earlyRelease.mockImplementation(async () => ({ hash: '0x1', wait: async () => { throw Object.assign(new Error('x'), { reason: 'Not delivered' }); } }));
        await show([order('o1', web3())], { fetchStatus: serverState().fetchStatus, escrow });
        await waitFor(() => expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(false));
        fireEvent.click(inPanel('o1').getByTestId('receive-btn'));
        await waitFor(() => expect(inPanel('o1').getByTestId('action-progress').textContent).toMatch(/không còn ở trạng thái chờ kiểm tra/));
    });

    it('bấm dồn nhanh chỉ gửi MỘT giao dịch', async () => {
        let release;
        const escrow = { earlyRelease: vi.fn(() => new Promise((r) => { release = () => r(tx()); })) };
        await show([order('o1', web3())], { fetchStatus: serverState().fetchStatus, escrow });
        await waitFor(() => expect(inPanel('o1').getByTestId('receive-btn').disabled).toBe(false));
        const b = inPanel('o1').getByTestId('receive-btn');
        fireEvent.click(b); fireEvent.click(b); fireEvent.click(b);
        await waitFor(() => expect(escrow.earlyRelease).toHaveBeenCalledTimes(1));
        release();
    });
});

describe('MyOrders — "Khiếu nại" (raiseDispute, UC-05)', () => {
    const fill = (reason = 'Hàng bị vỡ khi nhận, đã chụp ảnh', url = 'https://img.example.com/a.jpg') => {
        fireEvent.change(screen.getByTestId('dispute-reason'), { target: { value: reason } });
        fireEvent.change(screen.getByTestId('dispute-evidence'), { target: { value: url } });
    };
    const open = async () => {
        await waitFor(() => expect(inPanel('o1').getByTestId('dispute-btn').disabled).toBe(false));
        fireEvent.click(inPanel('o1').getByTestId('dispute-btn'));
    };

    it('form không hợp lệ: báo lỗi, KHÔNG gọi ví', async () => {
        const escrow = { raiseDispute: vi.fn(async () => tx()) };
        await show([order('o1', web3())], { fetchStatus: serverState().fetchStatus, escrow });
        await open();
        fill('ngắn', 'javascript:alert(1)');
        fireEvent.click(screen.getByTestId('dispute-submit'));
        expect(await screen.findByText(/tối thiểu 10 ký tự/)).toBeTruthy();
        expect(screen.getByText(/phải bắt đầu bằng http/)).toBeTruthy();
        expect(escrow.raiseDispute).not.toHaveBeenCalled();
    });

    it('đường vui: raiseDispute -> chờ Indexer ghi DISPUTED -> mới gửi lý do + bằng chứng cho sàn', async () => {
        const srv = serverState();
        const escrow = { raiseDispute: vi.fn(async () => tx()) };
        const saveNote = vi.fn(async () => ({ ok: true }));
        await show([order('o1', web3())], { fetchStatus: srv.fetchStatus, escrow, saveNote });
        await open();
        fill();
        fireEvent.click(screen.getByTestId('dispute-submit'));

        await waitFor(() => expect(escrow.raiseDispute).toHaveBeenCalledWith(100001n));
        await waitFor(() => expect(inPanel('o1').getByTestId('action-progress').dataset.step).toBe('WAITING_INDEXER'));
        expect(saveNote).not.toHaveBeenCalled();                                         // chưa DISPUTED thì chưa lưu lý do (SEQ-02)

        srv.st.o1 = { status: 'DISPUTED', disputed_at: NOW + 70 };
        await waitFor(() => expect(saveNote).toHaveBeenCalledTimes(1));
        expect(saveNote).toHaveBeenCalledWith('o1', { reason: 'Hàng bị vỡ khi nhận, đã chụp ảnh', evidenceUrl: 'https://img.example.com/a.jpg' });
        await waitFor(() => expect(inPanel('o1').getByTestId('dispute-note-status').dataset.state).toBe('saved'));
        expect(inPanel('o1').getByTestId('status-badge').dataset.status).toBe('DISPUTED');
        expect(inPanel('o1').queryByTestId('dispute-btn')).toBeNull();
        expect(sessionStorage.getItem('slopee.disputeNote.o1')).toBeNull();               // đã lưu thì xóa bản nháp
    });

    it('lưu lý do lỗi: báo rõ và cho "Gửi lại lý do", không gửi lặp khi chưa bấm', async () => {
        const srv = serverState();
        const escrow = { raiseDispute: vi.fn(async () => tx()) };
        const saveNote = vi.fn().mockRejectedValueOnce(new Error('mạng lỗi')).mockResolvedValue({ ok: true });
        await show([order('o1', web3())], { fetchStatus: srv.fetchStatus, escrow, saveNote });
        await open(); fill();
        fireEvent.click(screen.getByTestId('dispute-submit'));
        await waitFor(() => expect(escrow.raiseDispute).toHaveBeenCalled());
        srv.st.o1 = { status: 'DISPUTED' };
        await waitFor(() => expect(inPanel('o1').getByTestId('dispute-note-status').dataset.state).toBe('failed'));
        await new Promise((r) => setTimeout(r, 120));
        expect(saveNote).toHaveBeenCalledTimes(1);                                         // không tự thử lại vô hạn
        expect(sessionStorage.getItem('slopee.disputeNote.o1')).not.toBeNull();            // giữ bản nháp để gửi lại
        fireEvent.click(inPanel('o1').getByTestId('note-retry'));
        await waitFor(() => expect(inPanel('o1').getByTestId('dispute-note-status').dataset.state).toBe('saved'));
        expect(saveNote).toHaveBeenCalledTimes(2);
    });

    it('hủy trong ví: không giữ bản nháp lý do và không gửi gì cho sàn', async () => {
        const escrow = { raiseDispute: vi.fn(async () => { throw Object.assign(new Error('r'), { code: 4001 }); }) };
        const saveNote = vi.fn();
        await show([order('o1', web3())], { fetchStatus: serverState().fetchStatus, escrow, saveNote });
        await open(); fill();
        fireEvent.click(screen.getByTestId('dispute-submit'));
        await waitFor(() => expect(inPanel('o1').getByTestId('action-progress').dataset.step).toBe('FAILED'));
        expect(sessionStorage.getItem('slopee.disputeNote.o1')).toBeNull();
        expect(saveNote).not.toHaveBeenCalled();
    });

    it('tải lại trang giữa chừng: bản nháp trong sessionStorage vẫn được gửi khi đơn đã DISPUTED', async () => {
        sessionStorage.setItem('slopee.disputeNote.o1', JSON.stringify({ reason: 'Lý do đã nhập trước đó', evidenceUrl: '' }));
        const saveNote = vi.fn(async () => ({ ok: true }));
        await show([order('o1', web3({ status: 'DISPUTED', disputed_at: NOW + 5 }))], { fetchStatus: serverState({ o1: { status: 'DISPUTED' } }).fetchStatus, saveNote, connect: false });
        await waitFor(() => expect(saveNote).toHaveBeenCalledWith('o1', { reason: 'Lý do đã nhập trước đó', evidenceUrl: '' }));
    });
});

describe('MyOrders — nhóm theo lô (BR-11)', () => {
    it('hai shop cùng lô: có tiêu đề lô, mỗi đơn độc lập (thao tác đơn này không động tới đơn kia)', async () => {
        const srv = serverState();
        const escrow = { earlyRelease: vi.fn(async () => tx()) };
        const orders = [order('a', web3({ onchain_order_id: 111 })), order('b', web3({ onchain_order_id: 222 }), { items: [{ productName: 'Quần', quantity: 1, unitPrice: 1, shopName: 'Shop B' }] })];
        await show(orders, { fetchStatus: srv.fetchStatus, escrow });
        expect(screen.getByTestId('order-group').textContent).toMatch(/Lô thanh toán · 2 cửa hàng/);
        await waitFor(() => expect(inPanel('b').getByTestId('receive-btn').disabled).toBe(false));
        fireEvent.click(inPanel('b').getByTestId('receive-btn'));
        await waitFor(() => expect(escrow.earlyRelease).toHaveBeenCalledWith(222n));
        expect(escrow.earlyRelease).toHaveBeenCalledTimes(1);
        await waitFor(() => expect(inPanel('b').getByTestId('action-progress')).toBeTruthy());
        expect(inPanel('a').queryByTestId('action-progress')).toBeNull();
        expect(inPanel('a').getByTestId('receive-btn').disabled).toBe(false);              // đơn của shop A vẫn thao tác được
    });

    it('một đơn COMPLETED, đơn kia vẫn DELIVERED: hiển thị riêng từng đơn', async () => {
        const srv = serverState({ a: { status: 'COMPLETED' } });
        const orders = [order('a', web3({ status: 'COMPLETED' })), order('b', web3({ onchain_order_id: 222 }))];
        await show(orders, { fetchStatus: srv.fetchStatus });
        expect(inPanel('a').getByTestId('status-badge').dataset.status).toBe('COMPLETED');
        await waitFor(() => expect(inPanel('b').getByTestId('status-badge').dataset.status).toBe('DELIVERED'));
        expect(srv.fetchStatus.mock.calls.some(([code]) => code === 'a')).toBe(false);      // đơn đã xong không bị poll
    });
});

describe('MyOrders — các trạng thái khác', () => {
    it('LOCKED: nói đang chờ Shipper, không có nút, không có đồng hồ', async () => {
        await show([order('o1', web3({ status: 'LOCKED', delivered_at: null }))], { fetchStatus: serverState({ o1: { status: 'LOCKED', delivered_at: null } }).fetchStatus, connect: false });
        expect(await inPanel('o1').findByText(/chờ Shipper giao hàng/)).toBeTruthy();
        expect(inPanel('o1').queryByTestId('receive-btn')).toBeNull();
        expect(inPanel('o1').queryByTestId('countdown')).toBeNull();
    });
    it('DISPUTED: có liên kết sang màn hình phán quyết /disputes/:code; trạng thái khác thì không', async () => {
        await show([order('o1', web3({ status: 'DISPUTED', disputed_at: NOW + 5 })), order('o2', web3({ onchain_order_id: 2 }))],
            { fetchStatus: serverState({ o1: { status: 'DISPUTED' } }).fetchStatus, connect: false, saveNote: vi.fn(async () => ({})) });
        const link = await inPanel('o1').findByTestId('dispute-link');
        expect(link.getAttribute('href')).toBe('/disputes/o1');
        expect(inPanel('o2').queryByTestId('dispute-link')).toBeNull();
    });
    it('PENDING_PAYMENT: không poll, hướng dẫn hoàn tất thanh toán', async () => {
        const srv = serverState();
        await show([order('o1', web3({ status: 'PENDING_PAYMENT', delivered_at: null }))], { fetchStatus: srv.fetchStatus, connect: false });
        expect(await inPanel('o1').findByText(/Chưa ký quỹ/)).toBeTruthy();
        await new Promise((r) => setTimeout(r, 80));
        expect(srv.fetchStatus).not.toHaveBeenCalled();
    });
    it('API trạng thái lỗi: vẫn hiển thị theo dữ liệu danh sách và báo đang thử lại', async () => {
        const fetchStatus = vi.fn(async () => { throw new Error('down'); });
        await show([order('o1', web3({ status: 'LOCKED', delivered_at: null }))], { fetchStatus, connect: false });
        expect(await inPanel('o1').findByText(/đang thử lại/)).toBeTruthy();
        expect(inPanel('o1').getByTestId('status-badge').dataset.status).toBe('LOCKED');
    });
});

// ---- Tuần 7 [C] (UC-07, BR-05): "Hủy đơn & nhận lại tiền" khi đơn LOCKED quá 14 ngày chưa giao (cancelIfUnfulfilled) -----------------------
describe('MyOrders — Hủy đơn chưa giao quá 14 ngày (cancelIfUnfulfilled, UC-07)', () => {
    const DAY = 86400;
    // server_time mặc định của apiStatus = NOW + 60. created = NOW - 15 ngày => đã quá mốc; NOW - 10 ngày => còn ~4 ngày.
    const locked = (createdAgoDays, over = {}) => ({ status: 'LOCKED', delivered_at: null, chain_created_at: NOW - createdAgoDays * DAY, ...over });
    const lockedWeb3 = (createdAgoDays, over = {}) => web3({ status: 'LOCKED', delivered_at: null, chain_created_at: NOW - createdAgoDays * DAY, ...over });
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));

    it('chưa tới 14 ngày: hiện đồng hồ giao hàng, nút Hủy đơn bị khóa, không có Đã nhận hàng/Khiếu nại', async () => {
        const { fetchStatus } = serverState({ o1: locked(10) });
        const escrow = { cancelIfUnfulfilled: vi.fn(async () => tx()) };
        await show([order('o1', lockedWeb3(10))], { fetchStatus, escrow });
        const t = await inPanel('o1').findByTestId('delivery-countdown');
        await waitFor(() => expect(t.textContent).toMatch(/3 ngày 23:5\d:\d\d/));
        expect(inPanel('o1').getByTestId('cancel-btn').disabled).toBe(true);
        expect(inPanel('o1').queryByTestId('receive-btn')).toBeNull();
        expect(inPanel('o1').queryByTestId('dispute-btn')).toBeNull();
        fireEvent.click(inPanel('o1').getByTestId('cancel-btn'));
        expect(inPanel('o1').queryByTestId('cancel-confirm-box')).toBeNull();
        expect(escrow.cancelIfUnfulfilled).not.toHaveBeenCalled();
    });

    it('quá 14 ngày: nút bật, có lời giải thích, hết đồng hồ giao hàng', async () => {
        const { fetchStatus } = serverState({ o1: locked(15) });
        await show([order('o1', lockedWeb3(15))], { fetchStatus });
        await waitFor(() => expect(inPanel('o1').getByTestId('cancel-btn').disabled).toBe(false));
        expect(inPanel('o1').queryByTestId('delivery-countdown')).toBeNull();
        expect(inPanel('o1').getByTestId('phase-text').textContent).toMatch(/quá 14 ngày/);
    });

    it('đường vui: bấm -> xác nhận NGAY TRONG trang (không window.confirm) -> cancelIfUnfulfilled đúng id -> chỉ REFUNDED khi API báo', async () => {
        const srv = serverState({ o1: locked(15) });
        const escrow = { cancelIfUnfulfilled: vi.fn(async () => tx()), earlyRelease: vi.fn(), raiseDispute: vi.fn() };
        await show([order('o1', lockedWeb3(15))], { fetchStatus: srv.fetchStatus, escrow });
        await waitFor(() => expect(inPanel('o1').getByTestId('cancel-btn').disabled).toBe(false));
        fireEvent.click(inPanel('o1').getByTestId('cancel-btn'));
        expect(inPanel('o1').getByTestId('cancel-confirm-box').textContent).toMatch(/hoàn lại cho ví của bạn/);
        expect(escrow.cancelIfUnfulfilled).not.toHaveBeenCalled();          // mới chỉ hỏi, chưa mở ví
        fireEvent.click(inPanel('o1').getByTestId('cancel-confirm'));

        await waitFor(() => expect(escrow.cancelIfUnfulfilled).toHaveBeenCalledWith(100001n));
        expect(window.confirm).not.toHaveBeenCalled();                      // quy tắc Web3: không dùng confirm của trình duyệt
        await waitFor(() => expect(inPanel('o1').getByTestId('action-progress').dataset.step).toBe('WAITING_INDEXER'));
        // biên nhận đã có nhưng API vẫn LOCKED: KHÔNG tự coi là đã hoàn tiền (DD-04, BR-09)
        expect(inPanel('o1').getByTestId('status-badge').dataset.status).toBe('LOCKED');
        expect(inPanel('o1').getByTestId('cancel-btn').disabled).toBe(true);   // khóa trong lúc chờ: không bấm dồn
        expect(inPanel('o1').queryByTestId('cancel-confirm-box')).toBeNull();
        expect(escrow.earlyRelease).not.toHaveBeenCalled();
        expect(escrow.raiseDispute).not.toHaveBeenCalled();

        srv.st.o1 = { status: 'REFUNDED', delivered_at: null, chain_created_at: NOW - 15 * DAY };   // Indexer ghi OrderRefunded
        await waitFor(() => expect(inPanel('o1').getByTestId('status-badge').dataset.status).toBe('REFUNDED'));
        await waitFor(() => expect(inPanel('o1').getByTestId('action-progress').dataset.step).toBe('DONE'));
        expect(inPanel('o1').getByTestId('action-progress').textContent).toMatch(/Hủy đơn/);
        expect(inPanel('o1').queryByTestId('cancel-btn')).toBeNull();
        expect(inPanel('o1').getByTestId('phase-text').textContent).toMatch(/hoàn lại cho bạn/);
        const calls = srv.fetchStatus.mock.calls.length;
        await wait(120);
        expect(srv.fetchStatus.mock.calls.length).toBe(calls);               // trạng thái cuối: polling dừng hẳn
    });

    it('"Không hủy": đóng khung xác nhận, không gọi ví', async () => {
        const escrow = { cancelIfUnfulfilled: vi.fn(async () => tx()) };
        await show([order('o1', lockedWeb3(15))], { fetchStatus: serverState({ o1: locked(15) }).fetchStatus, escrow });
        await waitFor(() => expect(inPanel('o1').getByTestId('cancel-btn').disabled).toBe(false));
        fireEvent.click(inPanel('o1').getByTestId('cancel-btn'));
        fireEvent.click(inPanel('o1').getByTestId('cancel-abort'));
        await wait(60);
        expect(inPanel('o1').queryByTestId('cancel-confirm-box')).toBeNull();
        expect(escrow.cancelIfUnfulfilled).not.toHaveBeenCalled();
        expect(inPanel('o1').queryByTestId('action-progress')).toBeNull();
    });

    it('ví khác ví đã ký quỹ: cảnh báo, nút Hủy đơn khóa', async () => {
        const escrow = { cancelIfUnfulfilled: vi.fn(async () => tx()) };
        await show([order('o1', lockedWeb3(15))], { fetchStatus: serverState({ o1: locked(15) }).fetchStatus, escrow, account: OTHER });
        expect(await inPanel('o1').findByTestId('gate-wrong-account')).toBeTruthy();
        expect(inPanel('o1').getByTestId('cancel-btn').disabled).toBe(true);
        fireEvent.click(inPanel('o1').getByTestId('cancel-btn'));
        expect(escrow.cancelIfUnfulfilled).not.toHaveBeenCalled();
    });

    it('sai mạng: có nút chuyển mạng, Hủy đơn khóa', async () => {
        await show([order('o1', lockedWeb3(15))], { fetchStatus: serverState({ o1: locked(15) }).fetchStatus, chainId: '0x1' });
        expect(await inPanel('o1').findByTestId('gate-switch')).toBeTruthy();
        expect(inPanel('o1').getByTestId('cancel-btn').disabled).toBe(true);
    });

    it('người dùng hủy trong MetaMask: thông báo nhẹ, đóng được, bấm lại để thử tiếp', async () => {
        const escrow = { cancelIfUnfulfilled: vi.fn(async () => { throw Object.assign(new Error('rejected'), { code: 4001 }); }) };
        await show([order('o1', lockedWeb3(15))], { fetchStatus: serverState({ o1: locked(15) }).fetchStatus, escrow });
        await waitFor(() => expect(inPanel('o1').getByTestId('cancel-btn').disabled).toBe(false));
        fireEvent.click(inPanel('o1').getByTestId('cancel-btn'));
        fireEvent.click(inPanel('o1').getByTestId('cancel-confirm'));
        await waitFor(() => expect(inPanel('o1').getByTestId('action-progress').dataset.step).toBe('FAILED'));
        expect(inPanel('o1').getByTestId('action-progress').textContent).toMatch(/Bạn đã hủy thao tác/);
        expect(inPanel('o1').getByTestId('cancel-btn').disabled).toBe(false);
    });

    it('contract từ chối "Timeout not reached" (đồng hồ chuỗi chậm hơn dự đoán): báo rõ bằng tiếng Việt, tiền không đổi', async () => {
        const escrow = { cancelIfUnfulfilled: vi.fn(async () => ({ hash: '0x1', wait: async () => { throw Object.assign(new Error('x'), { reason: 'Timeout not reached' }); } })) };
        await show([order('o1', lockedWeb3(15))], { fetchStatus: serverState({ o1: locked(15) }).fetchStatus, escrow });
        await waitFor(() => expect(inPanel('o1').getByTestId('cancel-btn').disabled).toBe(false));
        fireEvent.click(inPanel('o1').getByTestId('cancel-btn'));
        fireEvent.click(inPanel('o1').getByTestId('cancel-confirm'));
        await waitFor(() => expect(inPanel('o1').getByTestId('action-progress').textContent).toMatch(/Chưa quá 14 ngày/));
        expect(inPanel('o1').getByTestId('status-badge').dataset.status).toBe('LOCKED');
    });

    it('bấm dồn nhanh chỉ gửi MỘT giao dịch', async () => {
        let release;
        const escrow = { cancelIfUnfulfilled: vi.fn(() => new Promise((r) => { release = () => r(tx()); })) };
        await show([order('o1', lockedWeb3(15))], { fetchStatus: serverState({ o1: locked(15) }).fetchStatus, escrow });
        await waitFor(() => expect(inPanel('o1').getByTestId('cancel-btn').disabled).toBe(false));
        fireEvent.click(inPanel('o1').getByTestId('cancel-btn'));
        const confirm = inPanel('o1').getByTestId('cancel-confirm');
        fireEvent.click(confirm); fireEvent.click(confirm); fireEvent.click(confirm);
        await waitFor(() => expect(escrow.cancelIfUnfulfilled).toHaveBeenCalledTimes(1));
        release();
    });

    it('đơn thiếu chain_created_at (dữ liệu cũ): không hiện phần Hủy đơn, không đoán theo created_at của đơn', async () => {
        const { fetchStatus } = serverState({ o1: { status: 'LOCKED', delivered_at: null } });
        await show([order('o1', web3({ status: 'LOCKED', delivered_at: null }))], { fetchStatus, connect: false });
        await waitFor(() => expect(fetchStatus).toHaveBeenCalled());
        await wait(80);
        expect(inPanel('o1').queryByTestId('cancel-section')).toBeNull();
        expect(inPanel('o1').queryByTestId('cancel-btn')).toBeNull();
    });

    it('đơn đã giao hoặc đã xong không có nút Hủy đơn, dù đã quá 14 ngày kể từ lúc ký quỹ', async () => {
        const delivered = { status: 'DELIVERED', chain_created_at: NOW - 20 * DAY };
        await show([order('o1', web3({ chain_created_at: NOW - 20 * DAY })), order('o2', web3({ status: 'COMPLETED', chain_created_at: NOW - 20 * DAY }))],
            { fetchStatus: serverState({ o1: delivered }).fetchStatus, connect: false });
        await waitFor(() => expect(inPanel('o1').getByTestId('receive-btn')).toBeTruthy());
        expect(inPanel('o1').queryByTestId('cancel-btn')).toBeNull();
        expect(inPanel('o2').queryByTestId('cancel-btn')).toBeNull();
    });

    it('hai đơn trong một lô: hủy đơn shop A không đổi đơn shop B (BR-11)', async () => {
        const srv = serverState({ a: locked(15), b: locked(10) });
        const escrow = { cancelIfUnfulfilled: vi.fn(async () => tx()) };
        const orders = [order('a', lockedWeb3(15, { onchain_order_id: 111 })), order('b', lockedWeb3(10, { onchain_order_id: 222 }), { items: [{ productName: 'Quần', quantity: 1, unitPrice: 1, shopName: 'Shop B' }] })];
        await show(orders, { fetchStatus: srv.fetchStatus, escrow });
        await waitFor(() => expect(inPanel('a').getByTestId('cancel-btn').disabled).toBe(false));
        expect(inPanel('b').getByTestId('cancel-btn').disabled).toBe(true);         // shop B mới 10 ngày
        fireEvent.click(inPanel('a').getByTestId('cancel-btn'));
        fireEvent.click(inPanel('a').getByTestId('cancel-confirm'));
        await waitFor(() => expect(escrow.cancelIfUnfulfilled).toHaveBeenCalledTimes(1));
        expect(escrow.cancelIfUnfulfilled).toHaveBeenCalledWith(111n);
        expect(inPanel('b').getByTestId('status-badge').dataset.status).toBe('LOCKED');
        expect(inPanel('b').queryByTestId('action-progress')).toBeNull();
    });
});
