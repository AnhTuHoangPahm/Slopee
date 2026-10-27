// E-03 (AC-05, AC-06): khiếu nại → Admin đề xuất → hai bên ký EIP-712 → nộp → hoàn tiền (và biến thể giải ngân Merchant).
import { test, expect } from '@playwright/test';
import { buildScenario, checkoutViaUi, deliver, feeOf, openAdmin, raiseDisputeViaUi, signDisputeAndExecute } from './helpers/flows.js';
import { onchainOrder, STATE, usdBalance } from './helpers/anvil.js';
import { requireStack } from './helpers/stack.js';
import { expectReconciled } from './helpers/scripts.js';
import { adminPropose, getDispute, orderStatus } from './helpers/api.js';
import { openActor } from './helpers/ui.js';

test.describe('E-03 Tranh chấp', () => {
    test.beforeEach(async () => { await requireStack(test); });

    test('hoàn tiền Buyer: Admin đề xuất bằng giao diện, Buyer ký, tiền về đủ 100%', async ({ browser }) => {
        test.setTimeout(420_000);
        const sc = await buildScenario(browser, { shops: 1 });
        let admin;
        try {
            const [o] = await checkoutViaUi(sc);
            await deliver(sc, o);
            const buyerBefore = await usdBalance(sc.buyerWallet.address); // sau khi đã ký quỹ
            await raiseDisputeViaUi(sc, o);
            expect((await onchainOrder(o.onchainId)).state).toBe(STATE.DISPUTED);
            expect(sc.actor.wallet.count('eth_sendTransaction')).toBe(3); // approve + depositEscrowBatch + raiseDispute

            // Admin thẩm định và đề xuất "Hoàn tiền cho Buyer" ngay trên màn hình Admin (trọng tài ký phiếu của mình)
            admin = await openAdmin(browser, sc);
            const section = admin.page.getByTestId(`dispute-${o.code}`);
            await expect(section).toBeVisible({ timeout: 60_000 });
            await expect(admin.page.getByTestId(`note-${o.code}`)).toContainText('Hàng nhận được không đúng mô tả'); // lý do của Buyer, hiển thị như chữ
            await section.getByRole('button', { name: 'Tạo đề xuất phán quyết' }).click();
            await admin.page.getByLabel(/Hoàn tiền cho Buyer/).check();
            await admin.page.getByTestId('proposal-note').fill('Bằng chứng khớp khiếu nại (E2E).');
            await admin.page.getByTestId('dialog-confirm').click();
            await expect(admin.page.getByTestId(`resolution-${o.code}`)).toBeVisible({ timeout: 60_000 });

            // Buyer ký (không tốn gas) rồi nhờ sàn nộp: hợp đồng thật chấp nhận chữ ký do giao diện tạo
            await signDisputeAndExecute(sc.actor.page, o.code);
            expect(sc.actor.wallet.count('eth_signTypedData_v4')).toBe(1);

            const chain = await onchainOrder(o.onchainId);
            expect(chain.state).toBe(STATE.REFUNDED);
            expect(await usdBalance(sc.buyerWallet.address)).toBe(buyerBefore + chain.amount); // hoàn 100%, không trừ phí
            expect(await usdBalance(o.merchant.wallet.address)).toBe(0n);
            expect((await orderStatus(sc.api, sc.buyer.token, o.code)).status).toBe('REFUNDED');

            await expectReconciled(expect);
        } finally {
            await admin?.close();
            await sc.dispose();
        }
    });

    test('giải ngân Merchant: Admin đề xuất, Merchant ký bằng giao diện của mình, tiền chia theo feeBps', async ({ browser }) => {
        test.setTimeout(420_000);
        const sc = await buildScenario(browser, { shops: 1 });
        let merchantUi;
        try {
            const [o] = await checkoutViaUi(sc);
            await deliver(sc, o);
            await raiseDisputeViaUi(sc, o, 'Người mua khiếu nại không có cơ sở (E2E).');
            await adminPropose(sc.api, sc.admin.token, o.code, 'MERCHANT', 'Hàng đúng mô tả (E2E).');

            // Merchant vào trang tranh chấp bằng chính ví đã liên kết (phiên đã đăng nhập, ví đã kết nối sẵn)
            merchantUi = await openActor(browser, { session: o.merchant, wallet: o.merchant.wallet, preconnected: true });
            await signDisputeAndExecute(merchantUi.page, o.code);

            const chain = await onchainOrder(o.onchainId);
            expect(chain.state).toBe(STATE.COMPLETED);
            expect(await usdBalance(o.merchant.wallet.address)).toBe(chain.amount - feeOf(chain.amount, chain.feeBps));
            const view = (await getDispute(sc.api, sc.buyer.token, o.code)).body;
            expect(view.resolution.status).toBe('EXECUTED');
            expect(JSON.stringify(view)).not.toMatch(/0x[0-9a-fA-F]{130}/); // API không bao giờ trả chữ ký thô

            await expectReconciled(expect);
        } finally {
            await merchantUi?.close();
            await sc.dispose();
        }
    });
});
