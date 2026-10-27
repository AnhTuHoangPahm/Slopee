// E-04 (AC-07): hai lối thoát timeout, kiểm bằng cách tua giờ Anvil.
//   (1) Delivery timeout: quá 14 ngày kể từ lúc ký quỹ mà chưa giao → Buyer tự hủy và nhận lại 100%.
//   (2) Dispute timeout: quá disputedAt + disputeTimeout → Admin (Trọng tài) xử đơn phương; trước mốc nút bị khóa.
import { test, expect } from '@playwright/test';
import { buildScenario, checkoutViaUi, deliver, feeOf, openAdmin, raiseDisputeViaUi } from './helpers/flows.js';
import { onchainOrder, STATE, timeTravel, usdBalance } from './helpers/anvil.js';
import { requireStack } from './helpers/stack.js';
import { expectReconciled } from './helpers/scripts.js';
import { orderStatus, waitForStatus } from './helpers/api.js';
import { expectStatus, orderPanel } from './helpers/ui.js';

const DAY = 86_400;

test.describe('E-04 Timeouts', () => {
    test.beforeEach(async () => { await requireStack(test); });

    test('Delivery timeout: chưa giao quá 14 ngày thì Buyer hủy đơn và nhận lại đủ tiền', async ({ browser }) => {
        test.setTimeout(300_000);
        const sc = await buildScenario(browser, { shops: 1 });
        try {
            const [o] = await checkoutViaUi(sc);
            const buyerAfterDeposit = await usdBalance(sc.buyerWallet.address);
            const { page } = sc.actor;

            // Trước hạn: có đồng hồ giao hàng, nút hủy bị khóa
            await page.goto('/orders');
            const panel = orderPanel(page, o.code);
            await expect(panel.getByTestId('delivery-countdown')).toBeVisible({ timeout: 60_000 });
            await expect(panel.getByTestId('cancel-btn')).toBeDisabled();

            await timeTravel(14 * DAY + 120);
            await page.reload(); // lấy server_time mới (= giờ block sau khi tua)
            await expect(panel.getByTestId('cancel-btn')).toBeEnabled({ timeout: 60_000 });

            // Xác nhận NGAY TRONG trang (không window.confirm), rồi ví gửi cancelIfUnfulfilled
            await panel.getByTestId('cancel-btn').click();
            await panel.getByTestId('cancel-confirm').click();
            await expectStatus(panel, 'REFUNDED');

            const chain = await onchainOrder(o.onchainId);
            expect(chain.state).toBe(STATE.REFUNDED);
            expect(await usdBalance(sc.buyerWallet.address)).toBe(buyerAfterDeposit + chain.amount); // hoàn 100%
            expect(await usdBalance(o.merchant.wallet.address)).toBe(0n);
            await expectReconciled(expect);
        } finally {
            await sc.dispose();
        }
    });

    test('Dispute timeout: trước mốc nút "Xử đơn phương" bị khóa, sau mốc Admin xử và Merchant nhận tiền trừ phí', async ({ browser }) => {
        test.setTimeout(420_000);
        const sc = await buildScenario(browser, { shops: 1 });
        let admin;
        try {
            const [o] = await checkoutViaUi(sc);
            await deliver(sc, o);
            await raiseDisputeViaUi(sc, o);
            const st = await orderStatus(sc.api, sc.buyer.token, o.code);
            expect(st.dispute_timeout).toBeGreaterThanOrEqual(7 * DAY); // BR-10: biên 7–90 ngày do contract ép

            admin = await openAdmin(browser, sc);
            const force = admin.page.getByTestId(`force-btn-${o.code}`);
            await expect(force).toBeVisible({ timeout: 60_000 });
            await expect(force).toBeDisabled(); // chưa tới mốc: giao diện không cho gửi giao dịch sẽ revert (R-02)

            await timeTravel(Number(st.dispute_timeout) + 120);
            await admin.page.reload();
            await expect(force).toBeEnabled({ timeout: 60_000 });

            await force.click();
            await admin.page.getByLabel(/Giải ngân cho Merchant/).check();
            await admin.page.getByTestId('force-note').fill('Quá hạn tranh chấp, hai bên không ký (E2E).'); // lý do bắt buộc, được ghi nhật ký kèm Admin
            await admin.page.getByTestId('dialog-confirm').click();

            await waitForStatus(sc.api, sc.buyer.token, o.code, 'COMPLETED', { timeoutMs: 120_000 }); // Indexer ghi sau khi chuỗi xử
            const chain = await onchainOrder(o.onchainId);
            expect(chain.state).toBe(STATE.COMPLETED);
            expect(await usdBalance(o.merchant.wallet.address)).toBe(chain.amount - feeOf(chain.amount, chain.feeBps));
            await expectReconciled(expect);
        } finally {
            await admin?.close();
            await sc.dispose();
        }
    });
});
