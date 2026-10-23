// @vitest-environment node
/* global process */
// Tuần 6 [Q] (Thành viên C), E-03 phía giao diện: giải quyết tranh chấp bằng 2/3 chữ ký EIP-712 trên CHUỖI THẬT.
// Buyer/Merchant ký bằng CHÍNH code ký của giao diện (lib/disputeSign.buildDisputeMessage + lib/eip712.signDispute + buildDomain);
// chữ ký Trọng tài do khóa Anvil ký (thay cho backend Tuần 6, chưa có `DisputeService`). Hợp đồng thật chấp nhận/từ chối, nên đây là bằng
// chứng nhất quán nhất rằng chữ ký của trình duyệt khớp contract (nonce, amount, deadline, thứ tự trường).
// Tự skip nếu không có Anvil; REQUIRE_ANVIL=1 thì thiếu là ĐỎ. Một test TUA GIỜ Anvil tiến lên vĩnh viễn (về giờ thật: bootstrap.sh --fresh).
import { describe, expect, it } from 'vitest';
import { signDispute } from '../lib/eip712';
import { buildDisputeMessage } from '../lib/disputeSign';
import { KEYS, STATE, anvilUp, bal, chainNow, deliver, domain, escrowAs, lockOrder, orderOf, raiseDispute, timeTravel, wallet } from './helpers/anvilChain';

const up = await anvilUp();
if (!up && process.env.REQUIRE_ANVIL) throw new Error('Không có Anvil/contract (REQUIRE_ANVIL đang bật)');

const SEVEN_DAYS = 7 * 86400;
const arbitrator = () => wallet(KEYS.arbitrator);
const relayer = () => wallet(KEYS.shipper); // "bất kỳ ai" nộp chữ ký lên chuỗi

/** Đơn đã DISPUTED + đề xuất do "Admin" tạo đúng quy tắc backend: deadline = min(now_chain + 7 ngày, disputedAt + timeout - 1). */
async function disputedOrder({ payoutTo, ttl = SEVEN_DAYS, amount, deadline } = {}) {
    const id = await lockOrder(amount ? { amount } : {});
    await deliver(id);
    await raiseDispute(id);
    const o = await orderOf(id);
    const limit = o.disputedAt + o.disputeTimeout - 1n;
    const nonce = await escrowAs(relayer()).disputeNonces(id);
    const payout = payoutTo === 'merchant' ? wallet(KEYS.merchant).address : wallet(KEYS.buyer).address;
    const dl = deadline ?? (BigInt(await chainNow()) + BigInt(ttl) < limit ? BigInt(await chainNow()) + BigInt(ttl) : limit);
    // `view` có đúng hình dạng mà giao diện nhận từ API; buildDisputeMessage là code THẬT của trang
    const view = { onchain_order_id: id.toString(), resolution: { payout_to: payout, amount_raw: o.amount.toString(), nonce: nonce.toString(), deadline: dl.toString() } };
    return { id, o, view, payout, deadline: dl, message: buildDisputeMessage(view) };
}
const sign = (w, message) => signDispute(w, domain(), message);
const resolve = (d, sigs, { payoutTo = d.payout, deadline = d.deadline, by = relayer() } = {}) => escrowAs(by).resolveDispute(d.id, payoutTo, deadline, sigs[0], sigs[1]);
async function expectRevert(promise, reason) {
    const e = await promise.then(() => null, (err) => err);
    expect(e, `phải revert "${reason}"`).not.toBeNull();
    expect(`${e.reason ?? ''} ${e.shortMessage ?? ''} ${e.message ?? ''}`).toContain(reason);
}

describe.skipIf(!up)('E-03: giải quyết tranh chấp bằng 2/3 chữ ký EIP-712 (chữ ký của giao diện, hợp đồng thật)', () => {
    it('HOÀN TIỀN BUYER: Trọng tài + Buyer ký (giao diện) -> relayer nộp -> Buyer nhận 100%, không trừ phí', async () => {
        const d = await disputedOrder({ payoutTo: 'buyer' });
        const buyer = wallet(KEYS.buyer);
        const sigs = [await sign(arbitrator(), d.message), await sign(buyer, d.message)];
        const [buyerBefore, merchantBefore, escrowBefore] = await Promise.all([bal(buyer.address), bal(wallet(KEYS.merchant).address), bal(await escrowAs(buyer).getAddress())]);

        const rc = await (await resolve(d, sigs)).wait();
        expect((await orderOf(d.id)).state).toBe(STATE.REFUNDED);
        expect(await bal(buyer.address) - buyerBefore).toBe(d.o.amount);            // hoàn đủ 100%
        expect(await bal(wallet(KEYS.merchant).address)).toBe(merchantBefore);
        expect(escrowBefore - await bal(await escrowAs(buyer).getAddress())).toBe(d.o.amount);
        const names = rc.logs.map((l) => { try { return escrowAs(buyer).interface.parseLog(l)?.name; } catch { return null; } });
        expect(names).toContain('OrderRefunded');
        expect(names).toContain('DisputeResolved');
        expect(await escrowAs(buyer).disputeNonces(d.id)).toBe(1n); // nonce tăng đúng một lần
    }, 90_000);

    it('GIẢI NGÂN MERCHANT: Trọng tài + Merchant ký (giao diện) -> Merchant nhận amount trừ phí, người nhận phí nhận phí', async () => {
        const d = await disputedOrder({ payoutTo: 'merchant' });
        const merchant = wallet(KEYS.merchant);
        const feeTo = await escrowAs(merchant).feeRecipient();
        const sigs = [await sign(arbitrator(), d.message), await sign(merchant, d.message)];
        const [mBefore, fBefore] = await Promise.all([bal(merchant.address), bal(feeTo)]);

        await (await resolve(d, sigs)).wait();
        expect((await orderOf(d.id)).state).toBe(STATE.COMPLETED);
        const fee = d.o.amount * d.o.feeBps / 10000n;
        expect(await bal(merchant.address) - mBefore).toBe(d.o.amount - fee);
        expect(await bal(feeTo) - fBefore).toBe(fee);
        expect(fee).toBeGreaterThan(0n);
    }, 90_000);

    it('Buyer và Merchant đồng thuận (không cần Trọng tài) cũng đủ 2 bên khác nhau', async () => {
        const d = await disputedOrder({ payoutTo: 'buyer' });
        const sigs = [await sign(wallet(KEYS.buyer), d.message), await sign(wallet(KEYS.merchant), d.message)];
        await (await resolve(d, sigs)).wait();
        expect((await orderOf(d.id)).state).toBe(STATE.REFUNDED);
    }, 90_000);

    describe('hợp đồng TỪ CHỐI (UC-06 luồng lỗi): trạng thái và nonce không đổi', () => {
        const stillDisputed = async (d) => {
            expect((await orderOf(d.id)).state).toBe(STATE.DISPUTED);
            expect(await escrowAs(relayer()).disputeNonces(d.id)).toBe(0n); // revert hoàn tác mức tăng nonce
        };

        it('hai chữ ký cùng một bên (Buyer + Buyer)', async () => {
            const d = await disputedOrder({ payoutTo: 'buyer' });
            const s = await sign(wallet(KEYS.buyer), d.message);
            await expectRevert(resolve(d, [s, s]), 'Need two distinct parties');
            await stillDisputed(d);
        }, 90_000);

        it('hai chữ ký cùng Trọng tài', async () => {
            const d = await disputedOrder({ payoutTo: 'buyer' });
            const s = await sign(arbitrator(), d.message);
            await expectRevert(resolve(d, [s, s]), 'Need two distinct parties');
        }, 90_000);

        it('chữ ký của người ngoài bộ ba (Trọng tài + người lạ)', async () => {
            const d = await disputedOrder({ payoutTo: 'buyer' });
            await expectRevert(resolve(d, [await sign(arbitrator(), d.message), await sign(wallet(KEYS.outsider), d.message)]), 'Need two distinct parties');
            await stillDisputed(d);
        }, 90_000);

        it('payoutTo không phải Buyer hoặc Merchant', async () => {
            const d = await disputedOrder({ payoutTo: 'buyer' });
            const stranger = wallet(KEYS.outsider).address;
            const m = { ...d.message, payoutTo: stranger };
            await expectRevert(resolve(d, [await sign(arbitrator(), m), await sign(wallet(KEYS.buyer), m)], { payoutTo: stranger }), 'Invalid payout recipient');
        }, 90_000);

        it('sai số tiền hoặc sai nonce trong chữ ký (chữ ký khôi phục ra địa chỉ lạ)', async () => {
            const d = await disputedOrder({ payoutTo: 'buyer' });
            for (const bad of [{ ...d.message, amount: d.message.amount - 1n }, { ...d.message, nonce: d.message.nonce + 1n }]) {
                await expectRevert(resolve(d, [await sign(arbitrator(), bad), await sign(wallet(KEYS.buyer), bad)]), 'Need two distinct parties');
            }
            await stillDisputed(d);
        }, 90_000);

        it('chữ ký cho hoàn tiền KHÔNG dùng được để giải ngân cho Merchant (đổi payoutTo)', async () => {
            const d = await disputedOrder({ payoutTo: 'buyer' });
            const sigs = [await sign(arbitrator(), d.message), await sign(wallet(KEYS.buyer), d.message)];
            await expectRevert(resolve(d, sigs, { payoutTo: wallet(KEYS.merchant).address }), 'Need two distinct parties');
            await stillDisputed(d);
        }, 90_000);

        it('deadline không nhỏ hơn disputedAt + disputeTimeout (đường thoát hiểm của Trọng tài, R-02)', async () => {
            const d0 = await disputedOrder({ payoutTo: 'buyer' });
            const limit = d0.o.disputedAt + d0.o.disputeTimeout;
            const dd = { ...d0, deadline: limit, message: { ...d0.message, deadline: limit } };
            await expectRevert(resolve(dd, [await sign(arbitrator(), dd.message), await sign(wallet(KEYS.buyer), dd.message)]), 'Deadline must be before dispute timeout');
        }, 90_000);

        it('chữ ký đã hết hạn (tua giờ qua deadline)', async () => {
            const d = await disputedOrder({ payoutTo: 'buyer', ttl: 30 });
            const sigs = [await sign(arbitrator(), d.message), await sign(wallet(KEYS.buyer), d.message)];
            await timeTravel(120);
            await expectRevert(resolve(d, sigs), 'Signature expired');
            await stillDisputed(d);
        }, 90_000);

        it('dùng lại chữ ký sau khi đã giải quyết, hoặc đơn chưa tranh chấp', async () => {
            const d = await disputedOrder({ payoutTo: 'buyer' });
            const sigs = [await sign(arbitrator(), d.message), await sign(wallet(KEYS.buyer), d.message)];
            await (await resolve(d, sigs)).wait();
            await expectRevert(resolve(d, sigs), 'Not disputed'); // phát lại chữ ký không chuyển tiền lần hai

            const id2 = await lockOrder();
            await deliver(id2);
            const fake = { id: id2, payout: wallet(KEYS.buyer).address, deadline: BigInt(await chainNow()) + 1000n };
            await expectRevert(resolve(fake, ['0x', '0x']), 'Not disputed');
        }, 120_000);
    });
});
