/* global process */
// Tuần 8 [C] — tiện ích chuỗi cho E2E (Node, KHÔNG chạy trong trình duyệt). Chỉ nói chuyện với Anvil cục bộ (chainId 31337).
// Ví thử được SUY RA lúc chạy từ mnemonic CÔNG KHAI của Anvil (không ghi cứng khóa hex trong mã): mỗi lần chạy dùng một dải chỉ số
// mới nên ví không trùng giữa các lần chạy (một ví chỉ liên kết được với một tài khoản). Khóa nằm ở tiến trình Playwright, KHÔNG BAO GIỜ vào trang.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Contract, HDNodeWallet, JsonRpcProvider } from 'ethers';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, '..', '..');
const REPO = path.resolve(FRONTEND, '..');

export const RPC_URL = process.env.RPC_URL ?? 'http://127.0.0.1:8545';
export const API_URL = (process.env.VITE_API_BASE ?? 'http://localhost:5000').replace(/\/+$/, '');
export const CHAIN_ID = 31337;
export const REPO_ROOT = REPO;

const PUBLIC_ANVIL_MNEMONIC = 'test test test test test test test test test test test junk'; // mnemonic công khai của Anvil, chỉ dùng thử
const ERC20_ABI = [
    'function mint(address to, uint256 amount)',
    'function balanceOf(address) view returns (uint256)',
];

const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
export const escrowAbi = readJson(path.join(FRONTEND, 'src', 'lib', 'abi', 'SlopeeEscrowMaster.json'));

/** Địa chỉ contract do bootstrap.sh sinh: ưu tiên bản frontend đang phục vụ, rồi tới bản gốc ở gốc repo. */
export function loadDeployment() {
    for (const p of [path.join(FRONTEND, 'public', 'deployments', 'local.json'), path.join(REPO, 'deployments', 'local.json')]) {
        if (fs.existsSync(p)) return readJson(p);
    }
    throw new Error('Không thấy deployments/local.json: hãy chạy ./scripts/bootstrap.sh trước.');
}

// ---- JSON-RPC thô tới Anvil (giữ nguyên lỗi của node để ví giả chuyển tiếp đúng mã/thông điệp)
let rpcId = 1;
export async function rpcRaw(method, params = [], url = RPC_URL) {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', id: rpcId++, method, params }) });
    return res.json();
}
export async function rpc(method, params = []) {
    const out = await rpcRaw(method, params);
    if (out.error) throw new Error(`${method}: ${out.error.message}`);
    return out.result;
}

export const provider = new JsonRpcProvider(RPC_URL, CHAIN_ID, { staticNetwork: true, cacheTimeout: -1, pollingInterval: 500 });

export async function anvilUp() {
    try {
        const out = await Promise.race([rpcRaw('eth_chainId'), new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 2500))]);
        return parseInt(out.result, 16) === CHAIN_ID;
    } catch {
        return false;
    }
}

// ---- Ví thử
let walletCounter = 0;
const RUN_BASE = 1000 + (Date.now() % 1_000_000) * 8; // mỗi lần chạy một dải chỉ số riêng; còn xa dưới 2^31
/** Ví thử mới, duy nhất trong lần chạy. `index` cố định (0..19) nếu cần đúng tài khoản Anvil có sẵn tiền (vd. 0 = người triển khai). */
export function testWallet(index) {
    const i = index ?? RUN_BASE + walletCounter++;
    return HDNodeWallet.fromPhrase(PUBLIC_ANVIL_MNEMONIC, undefined, `m/44'/60'/0'/0/${i}`).connect(provider);
}

/** Cấp ETH thử cho ví (anvil_setBalance) và mUSD (MockUSD.mint là hàm mở cho môi trường thử). */
export async function fundWallet(address, { eth = '0x56BC75E2D63100000' /* 100 ETH */, usd = 0n } = {}) {
    await rpc('anvil_setBalance', [address, eth]);
    if (usd > 0n) await mintUsd(address, usd);
}
export async function mintUsd(address, amount) {
    const dep = loadDeployment();
    const deployer = testWallet(0);
    const tk = new Contract(dep.mockUSD, ERC20_ABI, deployer);
    await (await tk.mint(address, amount)).wait();
}
export const usdBalance = async (address) => new Contract(loadDeployment().mockUSD, ERC20_ABI, provider).balanceOf(address);
export const escrowBalance = async () => usdBalance(loadDeployment().escrow);

// ---- Đọc contract
export const STATE = { NONE: 0, LOCKED: 1, DELIVERED: 2, DISPUTED: 3, COMPLETED: 4, REFUNDED: 5 };
export const escrowRead = () => new Contract(loadDeployment().escrow, escrowAbi, provider);
export async function onchainOrder(onchainId) {
    const o = await escrowRead().orders(BigInt(onchainId));
    return { state: Number(o.state), amount: o.amount, buyer: o.buyer, merchant: o.merchant, feeBps: o.feeBps, createdAt: o.createdAt, deliveredAt: o.deliveredAt, disputedAt: o.disputedAt, disputeTimeout: o.disputeTimeout, inspectionDuration: o.inspectionDuration };
}

// ---- Thời gian (E-02, E-04): tua Anvil tiến, đào một block để block mới mang giờ mới. Tiến VĨNH VIỄN trên node đang chạy.
export async function timeTravel(seconds) {
    await rpc('evm_increaseTime', [Number(seconds)]);
    await rpc('evm_mine', []);
}
export const chainNow = async () => Number((await provider.getBlock('latest')).timestamp);
