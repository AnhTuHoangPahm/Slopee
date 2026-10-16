import { configure, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Web3CheckoutPanel from '../components/Web3CheckoutPanel';
import { WalletProvider } from '../hooks/useWallet';
import { parseDeployment } from '../lib/chain';
import { installWeb3Mock } from '../mocks/web3Mock';
import { linkWalletAPI, requestWalletNonceAPI } from '../api/web3';

// Luồng Tuần 4 (UC-02, M2): Ký quỹ 2 bước ví -> chờ Indexer (polling) -> LOCKED -> tự chuyển màn hình.
// Hợp đồng được giả bằng đối tượng cùng giao diện ethers (không cần Anvil); chuỗi thật được kiểm ở kịch bản M2 chạy tay/E2E.
configure({ asyncUtilTimeout: 8000 });
vi.setConfig({ testTimeout: 20000 });

const ACCOUNT = '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc';
const deployment = parseDeployment({
    chainId: 31337, escrow: '0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512', mockUSD: '0x5FbDB2315678afecb367f032d93F642f64180aa3',
    deployBlock: 1, token: { symbol: 'MUSD', decimals: 6 },
});
const provider = () => ({
    request: vi.fn(async ({ method }) => {
        if (method === 'eth_requestAccounts') return [ACCOUNT];
        if (method === 'eth_accounts') return [];
        if (method === 'eth_chainId') return '0x7a69';
        throw Object.assign(new Error(`unhandled ${method}`), { code: -32601 });
    }),
    on: vi.fn(), removeListener: vi.fn(),
});

const tx = (hash) => ({ hash, wait: vi.fn(async () => ({ status: 1 })) });
function fakeContracts(over = {}) {
    const token = { balanceOf: vi.fn(async () => 1_000_000_000n), allowance: vi.fn(async () => 0n), approve: vi.fn(async () => tx(`0x${'a1'.repeat(32)}`)), ...over.token };
    const escrow = { depositEscrowBatch: vi.fn(async () => tx(`0x${'b2'.repeat(32)}`)), ...over.escrow };
    return { token, escrow, factory: async () => ({ token, escrow }) };
}

let mock;
beforeEach(() => {
    sessionStorage.setItem('token', 't');
    sessionStorage.setItem('user', JSON.stringify({ id: 'u1', name: 'An', role: 'user' }));
    mock = installWeb3Mock({ latencyMs: 0 });
});
afterEach(() => { mock.uninstall(); sessionStorage.clear(); });

async function openQuote(ui) {
    const n = await requestWalletNonceAPI(ACCOUNT);
    await linkWalletAPI({ address: ACCOUNT, signature: 's', nonce: n.nonce });
    render(<MemoryRouter initialEntries={['/checkout']}><WalletProvider provider={provider()} deployment={deployment}>
        <Routes>
            <Route path="/checkout" element={ui} />
            <Route path="/orders" element={<div data-testid="orders-page">Đơn hàng</div>} />
        </Routes>
    </WalletProvider></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: /Kết nối MetaMask/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Tạo báo giá' }));
    await screen.findByTestId('quote-result');
}

describe('Web3CheckoutPanel — ký quỹ 2 bước (Tuần 4)', () => {
    it('đường vui: approve tổng -> nạp gom -> CHỜ API -> LOCKED -> tự chuyển sang /orders', async () => {
        const c = fakeContracts();
        await openQuote(<Web3CheckoutPanel cartItemIds={['c1', 'c2']} contractsFactory={c.factory} />);
        fireEvent.click(screen.getByTestId('deposit-button'));

        await waitFor(() => expect(c.escrow.depositEscrowBatch).toHaveBeenCalledTimes(1));
        expect(c.token.approve).toHaveBeenCalledWith(deployment.escrow, 20_760_000n); // tổng cả giỏ, đúng một lần approve
        const [quotes, sigs] = c.escrow.depositEscrowBatch.mock.calls[0];
        expect(quotes).toHaveLength(2);
        expect(sigs).toHaveLength(2);

        // Biên nhận của ví KHÔNG phải LOCKED: giao diện vẫn chờ API
        await waitFor(() => expect(screen.getByTestId('tx-step-wait').dataset.mark).toBe('⏳'));
        expect(screen.queryByTestId('deposit-locked')).toBeNull();
        expect(screen.queryByTestId('orders-page')).toBeNull();

        // Indexer ghi LOCKED (mô phỏng) -> polling thấy -> thành công -> tự chuyển màn hình
        mock.state.lock([...mock.state.groups.keys()][0]);
        expect((await screen.findByTestId('deposit-locked')).textContent).toMatch(/2 đơn/);
        expect(await screen.findByTestId('orders-page')).toBeTruthy();
    });

    it('prop onLocked thay cho điều hướng mặc định', async () => {
        const onLocked = vi.fn();
        const c = fakeContracts();
        await openQuote(<Web3CheckoutPanel cartItemIds={['c1']} contractsFactory={c.factory} onLocked={onLocked} />);
        fireEvent.click(screen.getByTestId('deposit-button'));
        await screen.findByTestId('tx-stepper');
        await waitFor(() => expect(screen.getByTestId('tx-step-wait').dataset.mark).toBe('⏳'));
        mock.state.lock([...mock.state.groups.keys()][0]);
        await waitFor(() => expect(onLocked).toHaveBeenCalledTimes(1));
        expect(onLocked.mock.calls[0][0].orders.every((o) => o.status === 'LOCKED')).toBe(true);
    });

    it('đủ hạn mức thì bỏ approve', async () => {
        const c = fakeContracts({ token: { allowance: vi.fn(async () => 999_000_000n) } });
        await openQuote(<Web3CheckoutPanel cartItemIds={['c1', 'c2']} contractsFactory={c.factory} />);
        fireEvent.click(screen.getByTestId('deposit-button'));
        await waitFor(() => expect(c.escrow.depositEscrowBatch).toHaveBeenCalled());
        expect(c.token.approve).not.toHaveBeenCalled();
        expect(screen.getByTestId('tx-step-approve').textContent).toMatch(/bỏ qua/);
    });

    it('hủy trong ví (4001): thông báo trung tính, không phải lỗi; bấm lại được', async () => {
        const c = fakeContracts({ token: { approve: vi.fn().mockRejectedValueOnce(Object.assign(new Error('denied'), { code: 4001 })).mockResolvedValue(tx(`0x${'a1'.repeat(32)}`)) } });
        await openQuote(<Web3CheckoutPanel cartItemIds={['c1']} contractsFactory={c.factory} />);
        fireEvent.click(screen.getByTestId('deposit-button'));
        expect((await screen.findByTestId('deposit-cancelled')).textContent).toMatch(/Bạn đã hủy thao tác/);
        expect(screen.queryByTestId('deposit-error')).toBeNull();
        expect(c.escrow.depositEscrowBatch).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole('button', { name: 'Thử lại ký quỹ' }));
        await waitFor(() => expect(c.escrow.depositEscrowBatch).toHaveBeenCalledTimes(1));
    });

    it('thiếu số dư: nêu số thiếu, không gọi ví', async () => {
        const c = fakeContracts({ token: { balanceOf: vi.fn(async () => 10_000_000n) } });
        await openQuote(<Web3CheckoutPanel cartItemIds={['c1', 'c2']} contractsFactory={c.factory} />);
        fireEvent.click(screen.getByTestId('deposit-button'));
        const err = await screen.findByTestId('deposit-error');
        expect(err.textContent).toMatch(/Số dư mUSD không đủ/);
        expect(err.textContent).toContain('10,76 mUSD'); // 20,76 - 10,00
        expect(c.token.approve).not.toHaveBeenCalled();
        expect(c.escrow.depositEscrowBatch).not.toHaveBeenCalled();
    });

    it('nạp gom revert "Quote expired": cả lô thất bại, KHÔNG LOCKED, gợi ý lấy báo giá mới', async () => {
        const c = fakeContracts({ escrow: { depositEscrowBatch: vi.fn(async () => { throw Object.assign(new Error('x'), { reason: 'Quote expired' }); }) } });
        await openQuote(<Web3CheckoutPanel cartItemIds={['c1', 'c2']} contractsFactory={c.factory} />);
        fireEvent.click(screen.getByTestId('deposit-button'));
        expect((await screen.findByTestId('deposit-error')).textContent).toMatch(/hết hạn/);
        expect(screen.queryByTestId('deposit-locked')).toBeNull();
        expect(screen.getByTestId('tx-step-deposit').dataset.mark).toBe('❌');
        expect(screen.getByTestId('tx-step-approve').dataset.mark).toBe('✅'); // approve đã xong, chỉ bước nạp thất bại
    });

    it('"Order exists" (lần nạp trước đã vào chuỗi): không báo lỗi, chuyển sang chờ API rồi LOCKED', async () => {
        const c = fakeContracts({ escrow: { depositEscrowBatch: vi.fn(async () => { throw Object.assign(new Error('x'), { reason: 'Order exists' }); }) } });
        const onLocked = vi.fn();
        await openQuote(<Web3CheckoutPanel cartItemIds={['c1']} contractsFactory={c.factory} onLocked={onLocked} />);
        fireEvent.click(screen.getByTestId('deposit-button'));
        await waitFor(() => expect(screen.getByTestId('tx-step-wait').dataset.mark).toBe('⏳'));
        mock.state.lock([...mock.state.groups.keys()][0]);
        await waitFor(() => expect(onLocked).toHaveBeenCalled());
    });

    it('bấm dồn chỉ chạy MỘT luồng ví', async () => {
        const c = fakeContracts();
        await openQuote(<Web3CheckoutPanel cartItemIds={['c1']} contractsFactory={c.factory} />);
        const btn = screen.getByTestId('deposit-button');
        fireEvent.click(btn); fireEvent.click(btn); fireEvent.click(btn);
        await waitFor(() => expect(c.escrow.depositEscrowBatch).toHaveBeenCalledTimes(1));
        expect(c.token.approve).toHaveBeenCalledTimes(1);
    });

    it('lỗi dựng ví/signer hiện lỗi chứ không im lặng', async () => {
        await openQuote(<Web3CheckoutPanel cartItemIds={['c1']} contractsFactory={async () => { throw new Error('no signer'); }} />);
        fireEvent.click(screen.getByTestId('deposit-button'));
        expect((await screen.findByTestId('deposit-error')).textContent).toMatch(/Không kết nối được ví/);
    });
});
