// Tuần 8 [C] — ví thử EIP-1193 cho Playwright (SRS 12.3, SDD 13.5): tiêm `window.ethereum` bằng addInitScript, CHỈ trong môi trường kiểm thử.
// Bản demo thủ công vẫn dùng MetaMask thật. Khóa của ví thử nằm ở tiến trình Node này; trang chỉ thấy các lời gọi request() và kết quả,
// nên mã giao diện không bao giờ chạm vào khóa (cùng điều kiện với MetaMask). Ký thật bằng ethers (không giả chữ ký): contract thật chấp nhận.
//
//   const wallet = await installMockWallet(page, testWallet());
//   wallet.rejectNext('eth_sendTransaction');   // lần gửi giao dịch kế tiếp bị "người dùng hủy" (mã 4001)
//   wallet.count('eth_sendTransaction');        // đếm số lần ví phải xác nhận (E-07: đúng 2 lần cho cả giỏ)
import { getBytes } from 'ethers';
import { CHAIN_ID, provider, rpcRaw } from './anvil.js';

const USER_REJECTED = { code: 4001, message: 'User rejected the request.' };
// Các phương thức mà MetaMask bật cửa sổ xác nhận (người dùng có thể bấm Hủy)
export const PROMPTING_METHODS = new Set(['eth_requestAccounts', 'wallet_switchEthereumChain', 'wallet_addEthereumChain', 'personal_sign', 'eth_signTypedData_v4', 'eth_sendTransaction']);

const hexChain = (n) => `0x${Number(n).toString(16)}`;

// Chạy TRONG TRÌNH DUYỆT (được addInitScript tuần tự hóa nên không được tham chiếu biến ngoài)
function injectProvider({ chainIdHex }) {
    const listeners = {};
    const provider = {
        isMetaMask: true,
        isE2EMock: true,
        chainId: chainIdHex,
        request: async ({ method, params }) => {
            const out = await window.__e2eWalletRequest({ method, params: params === undefined ? [] : params });
            if (out && out.error) {
                const err = new Error(out.error.message);
                err.code = out.error.code;
                if (out.error.data !== undefined) err.data = out.error.data;
                throw err;
            }
            return out ? out.result : null;
        },
        on(event, fn) { (listeners[event] = listeners[event] || []).push(fn); return provider; },
        addListener(event, fn) { return provider.on(event, fn); },
        removeListener(event, fn) { listeners[event] = (listeners[event] || []).filter((f) => f !== fn); return provider; },
        off(event, fn) { return provider.removeListener(event, fn); },
    };
    window.__e2eEmit = (event, payload) => { (listeners[event] || []).slice().forEach((fn) => { try { fn(payload); } catch (e) { console.error(e); } }); };
    Object.defineProperty(window, 'ethereum', { value: provider, writable: false, configurable: true });
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {import('ethers').Wallet} wallet   ví đã `.connect(provider)` (xem anvil.js::testWallet)
 * @param {{ preconnected?: boolean, chainId?: number }} [opts]
 */
export async function installMockWallet(page, wallet, { preconnected = false, chainId = CHAIN_ID } = {}) {
    const state = { wallet, connected: preconnected, chainIdHex: hexChain(chainId), rejects: new Map(), calls: [] };

    const emit = async (event, payload) => {
        try { await page.evaluate(([e, p]) => window.__e2eEmit && window.__e2eEmit(e, p), [event, payload]); } catch { /* trang đã đóng hoặc đang điều hướng */ }
    };
    const consumeReject = (method) => {
        const left = state.rejects.get(method) ?? 0;
        if (left <= 0) return false;
        state.rejects.set(method, left - 1);
        return true;
    };

    async function handle({ method, params }) {
        state.calls.push({ method, params });
        const w = state.wallet;
        const me = w.address.toLowerCase();
        if (PROMPTING_METHODS.has(method) && consumeReject(method)) return { error: USER_REJECTED };

        try {
            switch (method) {
                case 'eth_accounts': return { result: state.connected ? [me] : [] };
                case 'eth_requestAccounts': state.connected = true; return { result: [me] };
                case 'eth_chainId': return { result: state.chainIdHex };
                case 'net_version': return { result: String(parseInt(state.chainIdHex, 16)) };
                case 'wallet_switchEthereumChain': {
                    const wanted = String(params?.[0]?.chainId ?? '').toLowerCase();
                    if (wanted !== hexChain(CHAIN_ID)) return { error: { code: 4902, message: 'Unrecognized chain ID. Try adding the chain using wallet_addEthereumChain first.' } };
                    state.chainIdHex = wanted;
                    await emit('chainChanged', wanted);
                    return { result: null };
                }
                case 'wallet_addEthereumChain': {
                    state.chainIdHex = String(params?.[0]?.chainId ?? state.chainIdHex).toLowerCase();
                    await emit('chainChanged', state.chainIdHex);
                    return { result: null };
                }
                case 'personal_sign': {
                    const [message, from] = params;
                    if (String(from).toLowerCase() !== me) return { error: { code: -32602, message: 'The requested account has not been authorized by the user.' } };
                    return { result: await w.signMessage(getBytes(message)) };
                }
                case 'eth_signTypedData_v4': {
                    const [from, json] = params;
                    if (String(from).toLowerCase() !== me) return { error: { code: -32602, message: 'The requested account has not been authorized by the user.' } };
                    const typed = typeof json === 'string' ? JSON.parse(json) : json;
                    const types = { ...typed.types };
                    delete types.EIP712Domain; // ethers tự dựng domain từ `domain`
                    return { result: await w.signTypedData(typed.domain, types, typed.message) };
                }
                case 'eth_sendTransaction': {
                    const tx = params[0];
                    if (tx.from && String(tx.from).toLowerCase() !== me) return { error: { code: -32602, message: 'The requested account has not been authorized by the user.' } };
                    if (parseInt(state.chainIdHex, 16) !== CHAIN_ID) return { error: { code: -32603, message: 'Wallet is on the wrong network.' } };
                    const sent = await w.connect(provider).sendTransaction({
                        to: tx.to,
                        data: tx.data,
                        value: tx.value ? BigInt(tx.value) : 0n,
                        gasLimit: tx.gas ? BigInt(tx.gas) : undefined,
                    });
                    return { result: sent.hash };
                }
                default: {
                    // Mọi lời gọi chỉ đọc/ước lượng (eth_call, eth_estimateGas, eth_getTransactionReceipt...) chuyển thẳng tới Anvil, giữ nguyên lỗi revert
                    const out = await rpcRaw(method, params ?? []);
                    return out.error ? { error: { code: out.error.code, message: out.error.message, data: out.error.data } } : { result: out.result };
                }
            }
        } catch (e) {
            return { error: { code: -32603, message: e?.shortMessage ?? e?.message ?? 'Internal error' } };
        }
    }

    await page.exposeFunction('__e2eWalletRequest', handle);
    await page.addInitScript(injectProvider, { chainIdHex: state.chainIdHex });

    return {
        wallet,
        get address() { return state.wallet.address; },
        get calls() { return state.calls; },
        /** Các lời gọi ví theo phương thức (để khẳng định số lần xác nhận). */
        callsOf: (method) => state.calls.filter((c) => c.method === method),
        count: (method) => state.calls.filter((c) => c.method === method).length,
        /** Lần `times` yêu cầu kế tiếp của `method` bị người dùng hủy (mã 4001). */
        rejectNext: (method, times = 1) => state.rejects.set(method, (state.rejects.get(method) ?? 0) + times),
        /** Ví đổi sang mạng khác (vd. 1) để kiểm cổng "sai mạng"; phát chainChanged cho trang. */
        setChain: async (id) => { state.chainIdHex = hexChain(id); await emit('chainChanged', state.chainIdHex); },
        /** Người dùng đổi tài khoản trong ví (kiểm cổng "sai ví"). */
        switchAccount: async (next) => { state.wallet = next; await emit('accountsChanged', [next.address.toLowerCase()]); },
        /** Ví khóa/ngắt kết nối. */
        lock: async () => { state.connected = false; await emit('accountsChanged', []); },
        isConnected: () => state.connected,
    };
}
