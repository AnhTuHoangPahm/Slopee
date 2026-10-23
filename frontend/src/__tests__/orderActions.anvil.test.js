/* global process */
// @vitest-environment node
// Tuần 5 [Q] (Thành viên C): luồng ví của Buyer trên CHUỖI THẬT. Chạy CHÍNH `runOrderAction` + ABI của frontend + ethers v6
// (không giả hợp đồng) để chứng minh: earlyRelease thật chạy được qua hàm của giao diện, và lỗi revert THẬT của contract được
// dịch đúng sang tiếng Việt (test giả không chứng minh được hình dạng lỗi thật của ethers).
// Tự skip nếu không có Anvil/contract. Chạy: ./scripts/bootstrap.sh --fresh --force-env && npx vitest run src/__tests__/orderActions.anvil.test.js
// Đặt REQUIRE_ANVIL=1 (như CI) để thiếu Anvil thì ĐỎ thay vì skip. Test này TUA GIỜ Anvil (evm_increaseTime) như I-05 phía backend.
import { Contract, JsonRpcProvider, Wallet, hexlify, randomBytes } from 'ethers';
import { describe, expect, it } from 'vitest';
import escrowAbi from '../lib/abi/SlopeeEscrowMaster.json';
import { buildDomain, EIP712_TYPES } from '../lib/eip712';
import { ORDER_ACTION, runOrderAction } from '../lib/orderActions';
import vectors from '../../../shared/eip712/vectors.json';

const RPC = process.env.RPC_URL ?? 'http://127.0.0.1:8545';
const ESCROW = vectors.domain.verifyingContract;
const TOKEN = '0x5FbDB2315678afecb367f032d93F642f64180aa3';   // MockUSD của bootstrap (deployer #0, nonce 0)
// Khóa mặc định CÔNG KHAI của Anvil, giống test/w3_support.py (không phải bí mật).
const KEYS = {
    shipper: '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d',
    quoteSigner: '0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6',
    buyer: '0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba',
    merchant: '0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e',
};
const ERC20 = [
    'function mint(address to, uint256 amount)', 'function approve(address spender, uint256 amount) returns (bool)',
    'function balanceOf(address) view returns (uint256)',
];
const STATE = { NONE: 0n, LOCKED: 1n, DELIVERED: 2n, DISPUTED: 3n, COMPLETED: 4n, REFUNDED: 5n };

const provider = new JsonRpcProvider(RPC, undefined, { staticNetwork: true, pollingInterval: 300 });
async function anvilUp() {
    try {
        const code = await Promise.race([provider.getCode(ESCROW), new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 2500))]);
        return code !== '0x';
    } catch { return false; }
}
const up = await anvilUp();
if (!up && process.env.REQUIRE_ANVIL) throw new Error(`Không có Anvil/contract tại ${RPC} (REQUIRE_ANVIL đang bật)`);

const wallet = (k) => new Wallet(k, provider);
const escrowAs = (w) => new Contract(ESCROW, escrowAbi, w);
const collect = () => { const events = []; return { events, dispatch: (e) => events.push(e) }; };

/** Báo giá hợp lệ ký bằng QUOTE_SIGNER (đúng như backend), rồi nạp bằng ví Buyer: đơn LOCKED thật. */
async function lockOrder({ inspection = 259200, amount = 1_000_000n } = {}) {
    const buyer = wallet(KEYS.buyer);
    const token = new Contract(TOKEN, ERC20, buyer);
    await (await token.mint(buyer.address, amount)).wait();
    await (await token.approve(ESCROW, amount)).wait();
    const now = (await provider.getBlock('latest')).timestamp;
    const quote = {
        orderId: BigInt(Date.now()) * 1000n + BigInt(Math.floor(Math.random() * 1000)),
        buyer: buyer.address, merchant: wallet(KEYS.merchant).address, token: TOKEN, amount,
        inspectionDuration: BigInt(inspection), disputeTimeout: 2592000n, feeBps: 300n,
        docHash: hexlify(randomBytes(32)), deadline: BigInt(now + 600),
    };
    const sig = await wallet(KEYS.quoteSigner).signTypedData(buildDomain({ chainId: 31337, escrow: ESCROW }), { OrderQuote: EIP712_TYPES.OrderQuote }, quote);
    await (await escrowAs(buyer).depositEscrow(quote, sig)).wait();
    return quote.orderId;
}
const deliver = async (id) => (await escrowAs(wallet(KEYS.shipper)).confirmDelivery(id)).wait();
const stateOf = async (id) => (await escrowAs(wallet(KEYS.buyer)).orders(id)).state;

describe.skipIf(!up)('Buyer trên chuỗi thật (ethers + ABI + runOrderAction của giao diện)', () => {
    it('đường vui: đơn đã giao -> runOrderAction(EARLY_RELEASE) thật -> COMPLETED on-chain', async () => {
        const id = await lockOrder();
        expect(await stateOf(id)).toBe(STATE.LOCKED);
        await deliver(id);
        expect(await stateOf(id)).toBe(STATE.DELIVERED);

        const { events, dispatch } = collect();
        const r = await runOrderAction({ kind: ORDER_ACTION.EARLY_RELEASE, onchainOrderId: id.toString(), escrow: escrowAs(wallet(KEYS.buyer)), dispatch });
        expect(r.hash).toMatch(/^0x[0-9a-f]{64}$/);
        expect(events.map((e) => e.type)).toEqual(['START', 'SENT', 'MINED']);
        expect(await stateOf(id)).toBe(STATE.COMPLETED);
    }, 60_000);

    it('khiếu nại thật: runOrderAction(RAISE_DISPUTE) trong hạn -> DISPUTED on-chain', async () => {
        const id = await lockOrder();
        await deliver(id);
        const { events, dispatch } = collect();
        await runOrderAction({ kind: ORDER_ACTION.RAISE_DISPUTE, onchainOrderId: id.toString(), escrow: escrowAs(wallet(KEYS.buyer)), dispatch });
        expect(events.map((e) => e.type)).toEqual(['START', 'SENT', 'MINED']);
        expect(await stateOf(id)).toBe(STATE.DISPUTED);
    }, 60_000);

    it('revert THẬT "Not delivered" (đơn chưa giao) được dịch đúng, không rơi vào lỗi chung', async () => {
        const id = await lockOrder();
        const { events, dispatch } = collect();
        await expect(runOrderAction({ kind: ORDER_ACTION.EARLY_RELEASE, onchainOrderId: id.toString(), escrow: escrowAs(wallet(KEYS.buyer)), dispatch })).rejects.toBeTruthy();
        const fail = events.at(-1);
        expect(fail.type).toBe('FAIL');
        expect(fail.error).toMatchObject({ code: 'TX_REVERTED', userRejected: false });
        expect(fail.error.message).toMatch(/không còn ở trạng thái chờ kiểm tra/);
        expect(await stateOf(id)).toBe(STATE.LOCKED);                         // revert: tiền không đổi
    }, 60_000);

    it('revert THẬT "Only buyer" (ví khác ví ký quỹ) được dịch đúng', async () => {
        const id = await lockOrder();
        await deliver(id);
        const { events, dispatch } = collect();
        await expect(runOrderAction({ kind: ORDER_ACTION.EARLY_RELEASE, onchainOrderId: id.toString(), escrow: escrowAs(wallet(KEYS.merchant)), dispatch })).rejects.toBeTruthy();
        expect(events.at(-1).error).toMatchObject({ code: 'TX_REVERTED' });
        expect(events.at(-1).error.message).toMatch(/Chỉ ví đã ký quỹ/);
        expect(await stateOf(id)).toBe(STATE.DELIVERED);
    }, 60_000);

    it('I-05: quá hạn kiểm tra -> revert THẬT "Expired" khi Khiếu nại, còn "Đã nhận hàng" vẫn chạy được', async () => {
        const id = await lockOrder({ inspection: 3600 });
        await deliver(id);
        await provider.send('evm_increaseTime', [3600 + 60]);
        await provider.send('evm_mine', []);

        const { events, dispatch } = collect();
        await expect(runOrderAction({ kind: ORDER_ACTION.RAISE_DISPUTE, onchainOrderId: id.toString(), escrow: escrowAs(wallet(KEYS.buyer)), dispatch })).rejects.toBeTruthy();
        expect(events.at(-1).error.message).toMatch(/quá thời hạn kiểm tra/);
        expect(await stateOf(id)).toBe(STATE.DELIVERED);

        const ok = collect();
        await runOrderAction({ kind: ORDER_ACTION.EARLY_RELEASE, onchainOrderId: id.toString(), escrow: escrowAs(wallet(KEYS.buyer)), dispatch: ok.dispatch });
        expect(ok.events.map((e) => e.type)).toEqual(['START', 'SENT', 'MINED']);
        expect(await stateOf(id)).toBe(STATE.COMPLETED);
    }, 90_000);

    // ---- Tuần 7 [C] (UC-07, T-14, E-04 phần giao diện): hủy đơn chưa giao quá 14 ngày bằng CHÍNH runOrderAction của giao diện ----------------
    const DAY = 86400;
    const balanceOf = (addr) => new Contract(TOKEN, ERC20, provider).balanceOf(addr);

    it('UC-07: chưa tới 14 ngày -> revert THẬT "Timeout not reached" được dịch đúng, đơn vẫn LOCKED', async () => {
        const id = await lockOrder();
        const { events, dispatch } = collect();
        await expect(runOrderAction({ kind: ORDER_ACTION.CANCEL_UNFULFILLED, onchainOrderId: id.toString(), escrow: escrowAs(wallet(KEYS.buyer)), dispatch })).rejects.toBeTruthy();
        expect(events.at(-1)).toMatchObject({ type: 'FAIL', error: { code: 'TX_REVERTED', userRejected: false } });
        expect(events.at(-1).error.message).toMatch(/Chưa quá 14 ngày/);
        expect(await stateOf(id)).toBe(STATE.LOCKED);
    }, 60_000);

    it('UC-07: quá 14 ngày -> người ngoài bị "Unauthorized", Buyer hủy được và nhận lại ĐỦ tiền ký quỹ (REFUNDED on-chain)', async () => {
        const amount = 1_234_567n;
        const id = await lockOrder({ amount });
        const buyer = wallet(KEYS.buyer);
        const before = await balanceOf(buyer.address);                    // sau khi ký quỹ (tiền đã nằm trong contract)
        await provider.send('evm_increaseTime', [14 * DAY + 60]);
        await provider.send('evm_mine', []);

        const bad = collect();
        await expect(runOrderAction({ kind: ORDER_ACTION.CANCEL_UNFULFILLED, onchainOrderId: id.toString(), escrow: escrowAs(wallet(KEYS.merchant)), dispatch: bad.dispatch })).rejects.toBeTruthy();
        expect(bad.events.at(-1).error.message).toMatch(/Chỉ ví đã ký quỹ/);
        expect(await stateOf(id)).toBe(STATE.LOCKED);                    // revert: tiền không đổi

        const { events, dispatch } = collect();
        const r = await runOrderAction({ kind: ORDER_ACTION.CANCEL_UNFULFILLED, onchainOrderId: id.toString(), escrow: escrowAs(buyer), dispatch });
        expect(r.hash).toMatch(/^0x[0-9a-f]{64}$/);
        expect(events.map((e) => e.type)).toEqual(['START', 'SENT', 'MINED']);
        expect(await stateOf(id)).toBe(STATE.REFUNDED);
        expect((await balanceOf(buyer.address)) - before).toBe(amount);   // hoàn đủ, không trừ phí sàn
    }, 120_000);

    it('UC-07: đơn đã giao thì quá 14 ngày cũng KHÔNG hủy được -> revert THẬT "Not locked" được dịch đúng', async () => {
        const id = await lockOrder();
        await deliver(id);
        await provider.send('evm_increaseTime', [14 * DAY + 60]);
        await provider.send('evm_mine', []);
        const { events, dispatch } = collect();
        await expect(runOrderAction({ kind: ORDER_ACTION.CANCEL_UNFULFILLED, onchainOrderId: id.toString(), escrow: escrowAs(wallet(KEYS.buyer)), dispatch })).rejects.toBeTruthy();
        expect(events.at(-1).error.message).toMatch(/không còn ở trạng thái chờ giao/);
        expect(await stateOf(id)).toBe(STATE.DELIVERED);
    }, 120_000);
});
