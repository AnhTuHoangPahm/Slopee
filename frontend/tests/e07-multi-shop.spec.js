// E-07 (AC-14, BR-11): giỏ 3 shop, đúng 2 lần xác nhận ví; shop A mở khóa sớm, shop B khiếu nại và hoàn tiền, shop C hết hạn tự giải ngân; đối soát khớp.
import { test, expect } from '@playwright/test';
import { buildScenario, checkoutViaUi, deliver, feeOf, raiseDisputeViaUi, signDisputeAndExecute } from './helpers/flows.js';
import { onchainOrder, STATE, timeTravel, usdBalance } from './helpers/anvil.js';
import { adminPropose, orderStatus, waitForStatus } from './helpers/api.js';
import { requireStack } from './helpers/stack.js';
import { expectReconciled } from './helpers/scripts.js';
import { expectStatus, orderPanel } from './helpers/ui.js';

test.describe('E-07 Giỏ 3 shop', () => {
    test.beforeEach(async () => { await requireStack(test); });

    test('3 shop kết thúc độc lập: A mở khóa sớm, B hoàn tiền, C tự giải ngân', async ({ browser }) => {
        test.setTimeout(600_000);
        const sc = await buildScenario(browser, { shops: 3 });
        try {
            const [a, b, c] = await checkoutViaUi(sc);
            expect(sc.actor.wallet.count('eth_sendTransaction')).toBe(2); // approve tổng + depositEscrowBatch, bất kể số shop
            for (const o of [a, b, c]) expect((await onchainOrder(o.onchainId)).state).toBe(STATE.LOCKED);

            const stC = await deliver(sc, c);
            await deliver(sc, a);
            await deliver(sc, b);
            const { page } = sc.actor;

            // A: Buyer "Đã nhận hàng" (earlyRelease)
            await page.goto('/orders');
            await expectStatus(orderPanel(page, a.code), 'DELIVERED');
            await orderPanel(page, a.code).getByTestId('receive-btn').click();
            await expectStatus(orderPanel(page, a.code), 'COMPLETED');

            // B: khiếu nại, Admin đề xuất hoàn tiền, Buyer ký và thi hành
            const buyerBeforeB = await usdBalance(sc.buyerWallet.address);
            await raiseDisputeViaUi(sc, b);
            await adminPropose(sc.api, sc.admin.token, b.code, 'BUYER');
            await signDisputeAndExecute(page, b.code);

            // C: không làm gì, tua giờ quá hạn kiểm tra (A và B đã xong nên không bị ảnh hưởng) → tự giải ngân
            await timeTravel(Number(stC.inspection_duration) + 60);
            await waitForStatus(sc.api, sc.buyer.token, c.code, 'COMPLETED', { timeoutMs: 150_000 });

            const [ca, cb, cc] = await Promise.all([a, b, c].map((o) => onchainOrder(o.onchainId)));
            expect([ca.state, cb.state, cc.state]).toEqual([STATE.COMPLETED, STATE.REFUNDED, STATE.COMPLETED]);
            expect(await usdBalance(a.merchant.wallet.address)).toBe(ca.amount - feeOf(ca.amount, ca.feeBps));
            expect(await usdBalance(b.merchant.wallet.address)).toBe(0n);
            expect(await usdBalance(c.merchant.wallet.address)).toBe(cc.amount - feeOf(cc.amount, cc.feeBps));
            expect(await usdBalance(sc.buyerWallet.address)).toBe(buyerBeforeB + cb.amount); // chỉ đơn B hoàn tiền cho Buyer
            for (const [o, s] of [[a, 'COMPLETED'], [b, 'REFUNDED'], [c, 'COMPLETED']]) expect((await orderStatus(sc.api, sc.buyer.token, o.code)).status).toBe(s);

            await expectReconciled(expect);
        } finally {
            await sc.dispose();
        }
    });
});
