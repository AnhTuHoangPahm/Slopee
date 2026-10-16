import { act, render, screen, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { describe, it, expect, vi } from 'vitest';
import {
    WALLET_ERROR, WALLET_STATUS, WalletProvider, getInjectedProvider, initialWalletState, normalizeWalletError,
    parseChainId, useWallet, walletReducer,
} from '../hooks/useWallet';
import { parseDeployment } from '../lib/chain';

const deployment = parseDeployment({
    chainId: 31337,
    escrow: '0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512',
    mockUSD: '0x5FbDB2315678afecb367f032d93F642f64180aa3',
    deployBlock: 1,
    token: { symbol: 'MUSD', decimals: 6 },
});
const ACCOUNT = '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc';

/** Ví EIP-1193 giả: `handlers` ghi đè phản hồi theo method; `emit` giả lập sự kiện từ ví. */
function fakeProvider(handlers = {}) {
    const listeners = {};
    const provider = {
        request: vi.fn(async ({ method, params }) => {
            if (handlers[method]) return handlers[method](params);
            const defaults = {
                eth_accounts: [],
                eth_requestAccounts: [ACCOUNT],
                eth_chainId: '0x1',
            };
            if (method in defaults) return defaults[method];
            throw Object.assign(new Error(`unhandled ${method}`), { code: -32601 });
        }),
        on: vi.fn((ev, fn) => { (listeners[ev] ||= new Set()).add(fn); }),
        removeListener: vi.fn((ev, fn) => listeners[ev]?.delete(fn)),
        emit: (ev, payload) => (listeners[ev] ? [...listeners[ev]].forEach((fn) => fn(payload)) : undefined),
        listenerCount: (ev) => listeners[ev]?.size ?? 0,
    };
    return provider;
}

const holder = { current: null };
function Probe() {
    const wallet = useWallet();
    useEffect(() => { holder.current = wallet; });
    return <div data-testid="status">{wallet.status}</div>;
}
const mount = (provider, props = {}) =>
    render(<WalletProvider provider={provider} deployment={deployment} {...props}><Probe /></WalletProvider>);

describe('walletReducer (hàm thuần)', () => {
    it('trạng thái đầu', () => {
        expect(initialWalletState(true).status).toBe(WALLET_STATUS.DISCONNECTED);
        expect(initialWalletState(false).status).toBe(WALLET_STATUS.NO_PROVIDER);
    });

    it('CONNECTING → CONNECTED → ACCOUNTS_CHANGED rỗng = ngắt kết nối', () => {
        let s = walletReducer(initialWalletState(true), { type: 'CONNECTING' });
        expect(s.status).toBe(WALLET_STATUS.CONNECTING);
        s = walletReducer(s, { type: 'CONNECTED', account: ACCOUNT, chainId: 31337 });
        expect(s).toMatchObject({ status: WALLET_STATUS.CONNECTED, account: ACCOUNT, chainId: 31337, error: null });
        s = walletReducer(s, { type: 'ACCOUNTS_CHANGED', accounts: [] });
        expect(s).toMatchObject({ status: WALLET_STATUS.DISCONNECTED, account: null });
    });

    it('ERROR giữ trạng thái đã kết nối nếu đang có tài khoản (ví dụ hủy chuyển mạng)', () => {
        const connected = { status: WALLET_STATUS.CONNECTED, account: ACCOUNT, chainId: 1, error: null };
        const s = walletReducer(connected, { type: 'ERROR', error: { code: 'X', message: 'm' } });
        expect(s.status).toBe(WALLET_STATUS.CONNECTED);
        expect(s.error.code).toBe('X');
    });

    it('ERROR không đổi NO_PROVIDER thành DISCONNECTED', () => {
        const s = walletReducer(initialWalletState(false), { type: 'ERROR', error: { code: 'X', message: 'm' } });
        expect(s.status).toBe(WALLET_STATUS.NO_PROVIDER);
    });
});

describe('tiện ích ví', () => {
    it('parseChainId', () => {
        expect(parseChainId('0x7a69')).toBe(31337);
        expect(parseChainId(31337)).toBe(31337);
        expect(parseChainId('xyz')).toBeNull();
    });

    it('mã 4001 → "Bạn đã hủy thao tác." (không phải lỗi hệ thống)', () => {
        const e = normalizeWalletError({ code: 4001 });
        expect(e.code).toBe(WALLET_ERROR.USER_REJECTED);
        expect(e.message).toBe('Bạn đã hủy thao tác.');
        expect(normalizeWalletError({ code: 'ACTION_REJECTED' }).code).toBe(WALLET_ERROR.USER_REJECTED);
        expect(normalizeWalletError({ code: -32002 }).code).toBe(WALLET_ERROR.REQUEST_PENDING);
        expect(normalizeWalletError(new Error('boom')).code).toBe(WALLET_ERROR.UNKNOWN);
    });

    it('getInjectedProvider ưu tiên MetaMask khi có nhiều ví', () => {
        const other = { name: 'other' };
        const mm = { name: 'mm', isMetaMask: true };
        expect(getInjectedProvider({ ethereum: { providers: [other, mm] } })).toBe(mm);
        expect(getInjectedProvider({ ethereum: other })).toBe(other);
        expect(getInjectedProvider({})).toBeNull();
    });
});

describe('WalletProvider / useWallet', () => {
    it('useWallet ngoài provider thì báo lỗi rõ ràng', () => {
        const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
        expect(() => render(<Probe />)).toThrow(/WalletProvider/);
        spy.mockRestore();
    });

    it('không có ví → NO_PROVIDER; connect() báo lỗi tiếng Việt', async () => {
        mount(null);
        expect(screen.getByTestId('status').textContent).toBe('no_provider');
        await act(async () => { expect(await holder.current.connect()).toBe(false); });
        expect(holder.current.error.code).toBe(WALLET_ERROR.NO_PROVIDER);
        expect(holder.current.status).toBe('no_provider');
    });

    it('connect() thành công, lấy tài khoản và chainId, so với chain đã triển khai', async () => {
        const provider = fakeProvider();
        mount(provider);
        await act(async () => { expect(await holder.current.connect()).toBe(true); });
        expect(holder.current.isConnected).toBe(true);
        expect(holder.current.account).toBe(ACCOUNT);
        expect(holder.current.chainId).toBe(1);
        expect(holder.current.isCorrectChain).toBe(false); // ví đang ở mạng 1, cần 31337
    });

    it('người dùng hủy kết nối (4001): không báo lỗi hệ thống, về DISCONNECTED', async () => {
        const provider = fakeProvider({ eth_requestAccounts: () => { throw Object.assign(new Error('x'), { code: 4001 }); } });
        mount(provider);
        await act(async () => { expect(await holder.current.connect()).toBe(false); });
        expect(holder.current.status).toBe(WALLET_STATUS.DISCONNECTED);
        expect(holder.current.error.code).toBe(WALLET_ERROR.USER_REJECTED);
    });

    it('khôi phục phiên đã cấp quyền bằng eth_accounts (không bật cửa sổ xác nhận)', async () => {
        const provider = fakeProvider({ eth_accounts: () => [ACCOUNT], eth_chainId: () => '0x7a69' });
        mount(provider);
        await waitFor(() => expect(holder.current.isConnected).toBe(true));
        expect(holder.current.isCorrectChain).toBe(true);
        expect(provider.request).not.toHaveBeenCalledWith(expect.objectContaining({ method: 'eth_requestAccounts' }));
    });

    it('theo dõi accountsChanged / chainChanged và gỡ listener khi unmount', async () => {
        const provider = fakeProvider({ eth_accounts: () => [ACCOUNT], eth_chainId: () => '0x7a69' });
        const { unmount } = mount(provider);
        await waitFor(() => expect(holder.current.isConnected).toBe(true));

        act(() => provider.emit('chainChanged', '0x1'));
        expect(holder.current.chainId).toBe(1);
        expect(holder.current.isCorrectChain).toBe(false);

        act(() => provider.emit('accountsChanged', ['0x70997970C51812dc3A010C7d01b50e0d17dc79C8']));
        expect(holder.current.account).toBe('0x70997970C51812dc3A010C7d01b50e0d17dc79C8');

        act(() => provider.emit('accountsChanged', []));
        expect(holder.current.status).toBe(WALLET_STATUS.DISCONNECTED);

        unmount();
        expect(provider.listenerCount('accountsChanged')).toBe(0);
        expect(provider.listenerCount('chainChanged')).toBe(0);
    });

    it('switchToDeployedChain gọi wallet_switchEthereumChain với chainId trong tệp triển khai', async () => {
        const provider = fakeProvider({ wallet_switchEthereumChain: () => null });
        mount(provider);
        await act(async () => { await holder.current.connect(); });
        await act(async () => { expect(await holder.current.switchToDeployedChain()).toBe(true); });
        expect(provider.request).toHaveBeenCalledWith({ method: 'wallet_switchEthereumChain', params: [{ chainId: '0x7a69' }] });
        expect(holder.current.isCorrectChain).toBe(true);
    });

    it('ví chưa có mạng (4902) → thêm mạng Anvil rồi chuyển', async () => {
        const provider = fakeProvider({
            wallet_switchEthereumChain: () => { throw Object.assign(new Error('unknown chain'), { code: 4902 }); },
            wallet_addEthereumChain: () => null,
        });
        mount(provider);
        await act(async () => { await holder.current.connect(); });
        await act(async () => { expect(await holder.current.switchToDeployedChain()).toBe(true); });
        const add = provider.request.mock.calls.find(([a]) => a.method === 'wallet_addEthereumChain')[0];
        expect(add.params[0].chainId).toBe('0x7a69');
        expect(add.params[0].chainName).toContain('Anvil');
    });

    it('người dùng từ chối chuyển mạng (4001): ở lại đã kết nối, báo "Bạn đã hủy thao tác."', async () => {
        const provider = fakeProvider({ wallet_switchEthereumChain: () => { throw Object.assign(new Error('rej'), { code: 4001 }); } });
        mount(provider);
        await act(async () => { await holder.current.connect(); });
        await act(async () => { expect(await holder.current.switchToDeployedChain()).toBe(false); });
        expect(holder.current.isConnected).toBe(true);
        expect(holder.current.error.message).toBe('Bạn đã hủy thao tác.');
    });

    it('chưa có deployments/local.json: deploymentStatus = error, switchToDeployedChain báo NO_DEPLOYMENT', async () => {
        const provider = fakeProvider();
        const failing = vi.fn().mockRejectedValue(new Error('404'));
        render(<WalletProvider provider={provider} loadDeploymentFn={failing}><Probe /></WalletProvider>);
        await waitFor(() => expect(holder.current.deploymentStatus).toBe('error'));
        await act(async () => { expect(await holder.current.switchToDeployedChain()).toBe(false); });
        expect(holder.current.error.code).toBe(WALLET_ERROR.NO_DEPLOYMENT);
        expect(holder.current.isCorrectChain).toBe(false);
    });

    it('không ghi gì vào localStorage/sessionStorage', async () => {
        localStorage.clear(); sessionStorage.clear();
        const provider = fakeProvider();
        mount(provider);
        await act(async () => { await holder.current.connect(); });
        expect(localStorage.length).toBe(0);
        expect(sessionStorage.length).toBe(0);
    });
});
