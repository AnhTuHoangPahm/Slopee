// Thông tin chuỗi: đọc `deployments/local.json` do scripts/bootstrap.sh sinh (SDD 4.7, 8.1, 9.1).
// Frontend CHỈ lấy chainId và địa chỉ contract từ tệp này, không nhập tay (SDD 8.1).
// ABI sẽ được thêm vào đây sau khi đóng băng giao diện hàm (M1, cuối tuần 2).
export const ANVIL_CHAIN_ID = 31337; // chỉ chạy trên Anvil (BRD): không mainnet, không tiền thật
export const DEPLOYMENT_URL = `${import.meta.env?.BASE_URL ?? '/'}deployments/local.json`;
export const DEFAULT_RPC_URL = import.meta.env?.VITE_RPC_URL || 'http://127.0.0.1:8545';

const ADDRESS_RE = /^0x[0-9a-fA-F]{40}$/;

export class DeploymentError extends Error {
    constructor(message) {
        super(message);
        this.name = 'DeploymentError';
    }
}

const requireAddress = (value, field) => {
    if (typeof value !== 'string' || !ADDRESS_RE.test(value)) {
        throw new DeploymentError(`deployments/local.json: "${field}" không phải địa chỉ hợp lệ`);
    }
    return value;
};

/** Kiểm tra và chuẩn hóa nội dung `deployments/local.json`. Ném DeploymentError nếu sai. */
export function parseDeployment(raw) {
    if (!raw || typeof raw !== 'object') throw new DeploymentError('deployments/local.json rỗng hoặc sai định dạng');
    if (raw.chainId !== ANVIL_CHAIN_ID) {
        throw new DeploymentError(`chainId phải là ${ANVIL_CHAIN_ID} (Anvil), nhận được ${String(raw.chainId)}`);
    }
    if (!Number.isInteger(raw.deployBlock) || raw.deployBlock < 0) {
        throw new DeploymentError('deployments/local.json: "deployBlock" phải là số nguyên không âm');
    }
    const decimals = raw.token?.decimals;
    if (!Number.isInteger(decimals) || decimals < 0 || decimals > 36) {
        throw new DeploymentError('deployments/local.json: "token.decimals" không hợp lệ');
    }
    return Object.freeze({
        chainId: raw.chainId,
        escrow: requireAddress(raw.escrow, 'escrow'),
        mockUSD: requireAddress(raw.mockUSD, 'mockUSD'),
        deployBlock: raw.deployBlock,
        token: Object.freeze({ symbol: String(raw.token?.symbol ?? 'MUSD'), decimals }),
        roles: Object.freeze({ ...(raw.roles ?? {}) }),
        testAccounts: Object.freeze({ ...(raw.testAccounts ?? {}) }),
    });
}

/** Tải và kiểm tra tệp triển khai. `fetchImpl` cho phép thay trong test. */
export async function loadDeployment(fetchImpl = (...a) => fetch(...a), url = DEPLOYMENT_URL) {
    let res;
    try {
        res = await fetchImpl(url, { cache: 'no-store' });
    } catch {
        throw new DeploymentError('Không tải được deployments/local.json — đã chạy ./scripts/bootstrap.sh chưa?');
    }
    if (!res.ok) throw new DeploymentError('Chưa có deployments/local.json — hãy chạy ./scripts/bootstrap.sh');
    let raw;
    try {
        raw = await res.json();
    } catch {
        throw new DeploymentError('deployments/local.json không phải JSON hợp lệ');
    }
    return parseDeployment(raw);
}

export const toChainIdHex = (chainId) => `0x${Number(chainId).toString(16)}`;

/** Tham số cho `wallet_addEthereumChain` (MetaMask) khi ví chưa có mạng Anvil. */
export const addChainParams = (deployment, rpcUrl = DEFAULT_RPC_URL) => ({
    chainId: toChainIdHex(deployment.chainId),
    chainName: 'Slopee Anvil (local)',
    nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 },
    rpcUrls: [rpcUrl],
});

/** Địa chỉ lưu và so sánh bằng chữ thường (AI_CONTEXT mục 4). */
export const sameAddress = (a, b) =>
    typeof a === 'string' && typeof b === 'string' && a.toLowerCase() === b.toLowerCase();
