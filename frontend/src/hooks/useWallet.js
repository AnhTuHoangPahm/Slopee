// Khung kết nối ví (EIP-1193 / MetaMask) — tuần 1 (SDD 9.1: trạng thái ví nằm trong MỘT React context).
// Phạm vi tuần 1: kết nối, theo dõi tài khoản/chuỗi, chuyển sang Anvil, lấy signer ethers, đọc deployments/local.json.
// Liên kết ví với tài khoản Slopee (UC-00, personal_sign + nonce) làm ở tuần 3 (pages/Wallet.jsx).
// Không lưu gì vào localStorage/sessionStorage; mọi trạng thái ví chỉ nằm trong bộ nhớ.
import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useReducer, useState } from 'react';
import { BrowserProvider } from 'ethers';
import { addChainParams, loadDeployment, toChainIdHex } from '../lib/chain';

export const WALLET_STATUS = Object.freeze({
    NO_PROVIDER: 'no_provider', // không có ví cài sẵn (chưa có MetaMask)
    DISCONNECTED: 'disconnected',
    CONNECTING: 'connecting',
    CONNECTED: 'connected',
});

export const WALLET_ERROR = Object.freeze({
    USER_REJECTED: 'USER_REJECTED', // mã 4001: người dùng hủy — không phải lỗi hệ thống
    REQUEST_PENDING: 'REQUEST_PENDING', // -32002: ví đang chờ người dùng xử lý yêu cầu trước
    NO_PROVIDER: 'NO_PROVIDER',
    NO_DEPLOYMENT: 'NO_DEPLOYMENT',
    UNKNOWN: 'UNKNOWN',
});

const MESSAGES = {
    [WALLET_ERROR.USER_REJECTED]: 'Bạn đã hủy thao tác.',
    [WALLET_ERROR.REQUEST_PENDING]: 'Ví đang chờ bạn xác nhận một yêu cầu khác. Hãy mở ví để xử lý.',
    [WALLET_ERROR.NO_PROVIDER]: 'Không tìm thấy ví. Hãy cài MetaMask rồi tải lại trang.',
    [WALLET_ERROR.NO_DEPLOYMENT]: 'Chưa có thông tin hợp đồng. Hãy chạy ./scripts/bootstrap.sh rồi tải lại trang.',
    [WALLET_ERROR.UNKNOWN]: 'Không kết nối được ví. Vui lòng thử lại.',
};

export const makeWalletError = (code) => ({ code, message: MESSAGES[code] });

/** Chuẩn hóa lỗi từ ví thành {code, message} tiếng Việt (SDD 9.5: mã 4001 là "Bạn đã hủy thao tác", không báo lỗi hệ thống). */
export function normalizeWalletError(err) {
    if (err?.code === 4001 || err?.code === 'ACTION_REJECTED') return makeWalletError(WALLET_ERROR.USER_REJECTED);
    if (err?.code === -32002) return makeWalletError(WALLET_ERROR.REQUEST_PENDING);
    return makeWalletError(WALLET_ERROR.UNKNOWN);
}

/** Tìm ví EIP-1193 được tiêm vào trang; nếu nhiều ví cùng tiêm thì ưu tiên MetaMask. */
export function getInjectedProvider(win = typeof window === 'undefined' ? undefined : window) {
    const eth = win?.ethereum;
    if (!eth) return null;
    if (Array.isArray(eth.providers) && eth.providers.length) {
        return eth.providers.find((p) => p.isMetaMask) ?? eth.providers[0];
    }
    return eth;
}

// chainId từ ví là chuỗi hex ("0x7a69") — đổi sang số; null nếu không hợp lệ
export const parseChainId = (hex) => {
    const n = typeof hex === 'string' && /^0x[0-9a-fA-F]+$/.test(hex) ? parseInt(hex, 16) : Number(hex);
    return Number.isSafeInteger(n) ? n : null;
};

export const initialWalletState = (hasProvider) => ({
    status: hasProvider ? WALLET_STATUS.DISCONNECTED : WALLET_STATUS.NO_PROVIDER,
    account: null,
    chainId: null,
    error: null,
});

/** Reducer thuần (dễ kiểm thử) cho trạng thái ví. */
export function walletReducer(state, action) {
    switch (action.type) {
        case 'CONNECTING':
            return { ...state, status: WALLET_STATUS.CONNECTING, error: null };
        case 'CONNECTED':
            return { status: WALLET_STATUS.CONNECTED, account: action.account, chainId: action.chainId, error: null };
        case 'ACCOUNTS_CHANGED':
            // Ví trả mảng rỗng khi người dùng ngắt kết nối/khóa ví
            return action.accounts.length
                ? { ...state, status: WALLET_STATUS.CONNECTED, account: action.accounts[0], error: null }
                : { ...state, status: WALLET_STATUS.DISCONNECTED, account: null };
        case 'CHAIN_CHANGED':
            return { ...state, chainId: action.chainId };
        case 'DISCONNECTED':
            return { ...state, status: WALLET_STATUS.DISCONNECTED, account: null };
        case 'ERROR':
            return {
                ...state,
                status: state.account ? WALLET_STATUS.CONNECTED : state.status === WALLET_STATUS.NO_PROVIDER ? state.status : WALLET_STATUS.DISCONNECTED,
                error: action.error,
            };
        case 'CLEAR_ERROR':
            return { ...state, error: null };
        default:
            return state;
    }
}

const WalletContext = createContext(null);

/**
 * Bọc ứng dụng một lần. Props (đều tùy chọn, chủ yếu để test): `provider` (ví EIP-1193 giả),
 * `deployment` (đối tượng đã qua parseDeployment), `loadDeploymentFn`.
 */
export function WalletProvider({ children, provider: providerProp, deployment: deploymentProp, loadDeploymentFn = loadDeployment }) {
    const provider = useMemo(() => providerProp ?? getInjectedProvider(), [providerProp]);
    const [state, dispatch] = useReducer(walletReducer, Boolean(provider), initialWalletState);
    const [deploymentState, setDeploymentState] = useState(
        deploymentProp ? { status: 'ready', deployment: deploymentProp, error: null } : { status: 'loading', deployment: null, error: null },
    );

    // Đọc deployments/local.json (nếu chưa được truyền vào)
    useEffect(() => {
        if (deploymentProp) return undefined;
        let cancelled = false;
        loadDeploymentFn()
            .then((deployment) => !cancelled && setDeploymentState({ status: 'ready', deployment, error: null }))
            .catch((error) => !cancelled && setDeploymentState({ status: 'error', deployment: null, error }));
        return () => {
            cancelled = true;
        };
    }, [deploymentProp, loadDeploymentFn]);

    // Theo dõi sự kiện của ví + khôi phục phiên đã cấp quyền (eth_accounts không bật cửa sổ xác nhận)
    useEffect(() => {
        if (!provider) return undefined;
        let cancelled = false;
        const onAccounts = (accounts) => dispatch({ type: 'ACCOUNTS_CHANGED', accounts });
        const onChain = (hex) => {
            const chainId = parseChainId(hex);
            if (chainId !== null) dispatch({ type: 'CHAIN_CHANGED', chainId });
        };
        const onDisconnect = () => dispatch({ type: 'DISCONNECTED' });
        provider.on?.('accountsChanged', onAccounts);
        provider.on?.('chainChanged', onChain);
        provider.on?.('disconnect', onDisconnect);

        (async () => {
            try {
                const accounts = await provider.request({ method: 'eth_accounts' });
                if (cancelled || !accounts?.length) return;
                const chainId = parseChainId(await provider.request({ method: 'eth_chainId' }));
                if (!cancelled) dispatch({ type: 'CONNECTED', account: accounts[0], chainId });
            } catch {
                /* im lặng: chưa kết nối thì người dùng bấm "Kết nối ví" */
            }
        })();

        return () => {
            cancelled = true;
            provider.removeListener?.('accountsChanged', onAccounts);
            provider.removeListener?.('chainChanged', onChain);
            provider.removeListener?.('disconnect', onDisconnect);
        };
    }, [provider]);

    const connect = useCallback(async () => {
        if (!provider) {
            dispatch({ type: 'ERROR', error: makeWalletError(WALLET_ERROR.NO_PROVIDER) });
            return false;
        }
        dispatch({ type: 'CONNECTING' });
        try {
            const accounts = await provider.request({ method: 'eth_requestAccounts' });
            const chainId = parseChainId(await provider.request({ method: 'eth_chainId' }));
            if (!accounts?.length) throw new Error('no accounts');
            dispatch({ type: 'CONNECTED', account: accounts[0], chainId });
            return true;
        } catch (err) {
            dispatch({ type: 'ERROR', error: normalizeWalletError(err) });
            return false;
        }
    }, [provider]);

    // Ví không có API "ngắt kết nối" chuẩn: chỉ quên trạng thái phía trang; quyền ở ví vẫn còn cho tới khi người dùng thu hồi trong ví
    const disconnect = useCallback(() => dispatch({ type: 'DISCONNECTED' }), []);
    const clearError = useCallback(() => dispatch({ type: 'CLEAR_ERROR' }), []);

    const deployment = deploymentState.deployment;

    // Yêu cầu ví chuyển sang mạng Anvil trong deployments/local.json (CHECK_NETWORK ở SDD 9.3); thêm mạng nếu ví chưa có (mã 4902)
    const switchToDeployedChain = useCallback(async () => {
        if (!provider) {
            dispatch({ type: 'ERROR', error: makeWalletError(WALLET_ERROR.NO_PROVIDER) });
            return false;
        }
        if (!deployment) {
            dispatch({ type: 'ERROR', error: makeWalletError(WALLET_ERROR.NO_DEPLOYMENT) });
            return false;
        }
        const chainIdHex = toChainIdHex(deployment.chainId);
        try {
            try {
                await provider.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: chainIdHex }] });
            } catch (err) {
                if (err?.code !== 4902) throw err;
                await provider.request({ method: 'wallet_addEthereumChain', params: [addChainParams(deployment)] });
            }
            dispatch({ type: 'CHAIN_CHANGED', chainId: deployment.chainId });
            return true;
        } catch (err) {
            dispatch({ type: 'ERROR', error: normalizeWalletError(err) });
            return false;
        }
    }, [provider, deployment]);

    // Signer ethers v6 của tài khoản đang kết nối (dùng cho approve/nạp tiền ở tuần 4 và ký EIP-712 ở tuần 6)
    const getSigner = useCallback(async () => {
        if (!provider) throw new Error(MESSAGES[WALLET_ERROR.NO_PROVIDER]);
        return new BrowserProvider(provider).getSigner();
    }, [provider]);

    const value = useMemo(
        () => ({
            ...state,
            isConnected: state.status === WALLET_STATUS.CONNECTED,
            hasProvider: Boolean(provider),
            deployment,
            deploymentStatus: deploymentState.status,
            deploymentError: deploymentState.error,
            isCorrectChain: Boolean(deployment) && state.chainId === deployment.chainId,
            connect,
            disconnect,
            clearError,
            switchToDeployedChain,
            getSigner,
        }),
        [state, provider, deployment, deploymentState, connect, disconnect, clearError, switchToDeployedChain, getSigner],
    );

    return createElement(WalletContext.Provider, { value }, children);
}

export function useWallet() {
    const ctx = useContext(WalletContext);
    if (!ctx) throw new Error('useWallet phải được dùng bên trong <WalletProvider>');
    return ctx;
}
