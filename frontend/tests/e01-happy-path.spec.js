// E-01 (AC-01, AC-03, AC-04): đăng ký → liên kết ví → giỏ 2 shop → ký quỹ gom → Shipper giao → Buyer "Đã nhận hàng".
// Chạy trên stack THẬT (Anvil + MySQL + backend + Indexer); ví là ví thử EIP-1193 ký thật. Cần ./scripts/e2e_stack.sh up.
import { test, expect } from '@playwright/test';
import { buildScenario, checkoutViaUi, deliver, feeOf } from './helpers/flows.js';
import { onchainOrder, STATE, usdBalance } from './helpers/anvil.js';
import { expectReconciled } from './helpers/scripts.js';
import { expectStatus, orderPanel } from './helpers/ui.js';
import { orderStatus } from './helpers/api.js';
import { requireStack } from './helpers/stack.js';

test.describe('E-01 Happy path', () => {
    test.beforeEach(async () => { await requireStack(test); });

    test('đăng ký → liên kết ví → ký quỹ gom 2 shop → giao → mở khóa sớm; shop còn lại vẫn LOCKED', async ({ browser }) => {
        test.setTimeout(300_000);
        const sc = await buildScenario(browser, { shops: 2, registerViaUi: true });
        try {
            const [a, b] = await checkoutViaUi(sc);
            // Ký quỹ gom đúng 2 lần xác nhận ví (approve tổng + depositEscrowBatch), không phải 2 lần cho mỗi shop (BR-11, AC-14)
            expect(sc.actor.wallet.count('eth_sendTransaction')).toBe(2);
            expect(sc.actor.wallet.count('personal_sign')).toBe(1); // liên kết ví (không tốn gas)

            // Hai đơn cùng một lô, đều đã khóa tiền thật trên chuỗi
            for (const o of [a, b]) expect((await onchainOrder(o.onchainId)).state).toBe(STATE.LOCKED);

            // Shipper giao đơn của shop A (đơn B không bị ảnh hưởng)
            await deliver(sc, a);

            const { page } = sc.actor;
            await page.goto('/orders');
            const panelA = orderPanel(page, a.code);
            await expectStatus(panelA, 'DELIVERED');      // LOCKED poll 15 giây nên có thể mất tới ~15 giây
            const before = await usdBalance(a.merchant.wallet.address);
            expect(before).toBe(0n);

            await panelA.getByTestId('receive-btn').click(); // window.confirm được openActor tự chấp nhận
            await expectStatus(panelA, 'COMPLETED');

            // Tiền chia đúng theo feeBps đã khóa trong báo giá (AC-04): Merchant nhận amount - fee
            const chainA = await onchainOrder(a.onchainId);
            expect(chainA.state).toBe(STATE.COMPLETED);
            const fee = feeOf(chainA.amount, chainA.feeBps);
            expect(await usdBalance(a.merchant.wallet.address)).toBe(chainA.amount - fee);

            // BR-11: đơn của shop B vẫn LOCKED, cả trên API lẫn chuỗi
            expect((await orderStatus(sc.api, sc.buyer.token, b.code)).status).toBe('LOCKED');
            expect((await onchainOrder(b.onchainId)).state).toBe(STATE.LOCKED);
            expect(await usdBalance(b.merchant.wallet.address)).toBe(0n);

            await expectReconciled(expect); // E-06 sau kịch bản
        } finally {
            await sc.dispose();
        }
    });
});
