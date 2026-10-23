/* global process */
// Tiện ích dùng chung cho test chạy trên Anvil THẬT (ethers v6). Khóa là khóa CÔNG KHAI mặc định của Anvil (giống test/w3_support.py).
import { Contract, JsonRpcProvider, Wallet, hexlify, randomBytes } from 'ethers';
import escrowAbi from '../../lib/abi/SlopeeEscrowMaster.json';
import { buildDomain, EIP712_TYPES } from '../../lib/eip712';
import vectors from '../../../../shared/eip712/vectors.json';

export const RPC = process.env.RPC_URL ?? 'http://127.0.0.1:8545';
export const ESCROW = vectors.domain.verifyingContract;
export const TOKEN = '0x5FbDB2315678afecb367f032d93F642f64180aa3'; // MockUSD của bootstrap
export const KEYS = {
    shipper: '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d', // #1
    arbitrator: '0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a', // #2
    quoteSigner: '0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6', // #3
    buyer: '0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba', // #5
    merchant: '0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e', // #6
    outsider: '0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356', // #8: không thuộc đơn nào
};
export const STATE = { NONE: 0n, LOCKED: 1n, DELIVERED: 2n, DISPUTED: 3n, COMPLETED: 4n, REFUNDED: 5n };
const ERC20 = ['function mint(address to, uint256 amount)', 'function approve(address spender, uint256 amount) returns (bool)', 'function balanceOf(address) view returns (uint256)'];

export const provider = new JsonRpcProvider(RPC, undefined, { staticNetwork: true, pollingInterval: 300 });
export const wallet = (k) => new Wallet(k, provider);
export const escrowAs = (w) => new Contract(ESCROW, escrowAbi, w);
export const token = () => new Contract(TOKEN, ERC20, provider);
export const domain = () => buildDomain({ chainId: 31337, escrow: ESCROW });

export async function anvilUp() {
    try {
        const code = await Promise.race([provider.getCode(ESCROW), new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 2500))]);
        return code !== '0x';
    } catch { return false; }
}

/** Báo giá hợp lệ ký bằng QUOTE_SIGNER, nạp bằng ví Buyer: đơn LOCKED thật. */
export async function lockOrder({ inspection = 259200, amount = 1_000_000n, disputeTimeout = 2592000n } = {}) {
    const buyer = wallet(KEYS.buyer);
    const tk = new Contract(TOKEN, ERC20, buyer);
    await (await tk.mint(buyer.address, amount)).wait();
    await (await tk.approve(ESCROW, amount)).wait();
    const now = (await provider.getBlock('latest')).timestamp;
    const quote = {
        orderId: BigInt(Date.now()) * 1000n + BigInt(Math.floor(Math.random() * 1000)),
        buyer: buyer.address, merchant: wallet(KEYS.merchant).address, token: TOKEN, amount,
        inspectionDuration: BigInt(inspection), disputeTimeout, feeBps: 300n,
        docHash: hexlify(randomBytes(32)), deadline: BigInt(now + 600),
    };
    const sig = await wallet(KEYS.quoteSigner).signTypedData(domain(), { OrderQuote: EIP712_TYPES.OrderQuote }, quote);
    await (await escrowAs(buyer).depositEscrow(quote, sig)).wait();
    return quote.orderId;
}
export const deliver = async (id) => (await escrowAs(wallet(KEYS.shipper)).confirmDelivery(id)).wait();
export const raiseDispute = async (id) => (await escrowAs(wallet(KEYS.buyer)).raiseDispute(id)).wait();
export const orderOf = (id) => escrowAs(wallet(KEYS.buyer)).orders(id);
export const bal = (addr) => token().balanceOf(addr);
export async function timeTravel(seconds) {
    await provider.send('evm_increaseTime', [Number(seconds)]);
    await provider.send('evm_mine', []);
}
export const chainNow = async () => (await provider.getBlock('latest')).timestamp;
