// E-02 (AC-04): giao hàng → tua giờ Anvil quá hạn kiểm tra → AutoRelease + Indexer tự giải ngân → Buyer thấy COMPLETED.
import { test, expect } from '@playwright/test';
import { buildScenario, checkoutViaUi, deliver, feeOf } from './helpers/flows.js';
import { onchainOrder, STATE, timeTravel, usdBalance } from './helpers/anvil.js';
import { requireStack } from './helpers/stack.js';
import { expectReconciled } from './helpers/scripts.js';
import { expectStatus, orderPanel } from './helpers/ui.js';
import { waitForStatus } from './helpers/api.js';

test.describe('E-02 Hết hạn kiểm tra', () => {
    test.beforeEach(async () => { await requireStack(test); });

    test('quá hạn kiểm tra mà không khiếu nại thì tự giải ngân cho Merchant', async ({ browser }) => {
        test.setTimeout(300_000);
        const sc = await buildScenario(browser, { shops: 1 });
        try {
            const [o] = await checkoutViaUi(sc);
            const st = await deliver(sc, o);
            expect(st.inspection_duration).toBeGreaterThan(0);

            // Còn trong hạn kiểm tra: chưa ai giải ngân
            expect((await onchainOrder(o.onchainId)).state).toBe(STATE.DELIVERED);
            expect(await usdBalance(o.merchant.wallet.address)).toBe(0n);

            await timeTravel(Number(st.inspection_duration) + 30); // tua Anvil quá hạn (tiến vĩnh viễn trên node này)
            await waitForStatus(sc.api, sc.buyer.token, o.code, 'COMPLETED', { timeoutMs: 120_000 }); // AutoRelease (scheduler) → releaseAfterInspection → Indexer

            const chain = await onchainOrder(o.onchainId);
            expect(chain.state).toBe(STATE.COMPLETED);
            expect(await usdBalance(o.merchant.wallet.address)).toBe(chain.amount - feeOf(chain.amount, chain.feeBps));

            // Giao diện của Buyer phản ánh đúng, và không còn nút khiếu nại/nhận hàng
            const { page } = sc.actor;
            await page.goto('/orders');
            const panel = orderPanel(page, o.code);
            await expectStatus(panel, 'COMPLETED');
            await expect(panel.getByTestId('dispute-btn')).toHaveCount(0);
            await expect(panel.getByTestId('receive-btn')).toHaveCount(0);

            await expectReconciled(expect);
        } finally {
            await sc.dispose();
        }
    });
});
