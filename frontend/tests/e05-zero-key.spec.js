/* global process */
// E-05 (AC-09, BR-01): không có khóa riêng/seed của người dùng ở trình duyệt, đường truyền, CSDL và log.
// Khóa của ví thử chỉ nằm ở tiến trình Playwright. Sau một luồng đủ ký (liên kết ví, ký quỹ, ký EIP-712 không), test tìm CHÍNH khóa đó ở mọi nơi.
import { test, expect } from '@playwright/test';
import { buildScenario, checkoutViaUi, deliver, raiseDisputeViaUi, signDisputeAndExecute } from './helpers/flows.js';
import { adminPropose } from './helpers/api.js';
import { requireStack } from './helpers/stack.js';
import { scanNoUserKeys } from './helpers/scripts.js';

/** Thu mọi thứ trang gửi đi (URL, header, thân) và mọi dòng console. */
function trackPage(page) {
    const seen = [];
    page.on('request', (r) => seen.push(`${r.method()} ${r.url()}\n${JSON.stringify(r.headers())}\n${r.postData() ?? ''}`));
    page.on('console', (m) => seen.push(`console:${m.text()}`));
    return seen;
}

test.describe('E-05 Zero-key', () => {
    test.beforeEach(async () => { await requireStack(test); });

    test('khóa ví thử không xuất hiện ở storage, DOM, request, console; quét CSDL và repo sạch', async ({ browser }) => {
        test.setTimeout(420_000);
        const sc = await buildScenario(browser, { shops: 1 });
        try {
            const seen = trackPage(sc.actor.page);
            const [o] = await checkoutViaUi(sc);       // personal_sign + approve + deposit
            await deliver(sc, o);
            await raiseDisputeViaUi(sc, o);
            await adminPropose(sc.api, sc.admin.token, o.code, 'BUYER');
            await signDisputeAndExecute(sc.actor.page, o.code); // eth_signTypedData_v4

            expect(sc.actor.wallet.count('personal_sign')).toBe(1);
            expect(sc.actor.wallet.count('eth_signTypedData_v4')).toBe(1);

            // Mọi chuỗi có thể là khóa: khóa thật của ví, với và không có tiền tố 0x
            const secret = sc.buyerWallet.privateKey.toLowerCase();
            const bare = secret.replace(/^0x/, '');
            const page = sc.actor.page;
            const dom = (await page.content()).toLowerCase();
            const storage = JSON.stringify(await page.evaluate(() => ({ s: { ...sessionStorage }, l: { ...localStorage } }))).toLowerCase();
            for (const [where, text] of [['DOM', dom], ['storage', storage], ['request/console', seen.join('\n').toLowerCase()]]) {
                expect(text.includes(bare), `khóa ví xuất hiện ở ${where}`).toBe(false);
            }
            // Không có tên trường nhạy cảm trong storage của ứng dụng
            expect(storage).not.toMatch(/private|mnemonic|seed|keystore/);
            // Ví chỉ lưu địa chỉ công khai ở phía máy chủ
            const linked = await (await sc.api.get('/api/wallet', { headers: { Authorization: `Bearer ${sc.buyer.token}` } })).json();
            expect(linked.address.toLowerCase()).toBe(sc.buyerWallet.address.toLowerCase());
            expect(JSON.stringify(linked).toLowerCase()).not.toContain(bare);

            // Quét CSDL đang chạy (đã chứa nonce, chữ ký, đơn, ví của chính luồng trên) và kèm log backend nếu có
            const logs = process.env.E2E_BACKEND_LOG ? [process.env.E2E_BACKEND_LOG] : [];
            const scan = await scanNoUserKeys({ db: true, logs });
            expect(scan.code, `scan_no_user_keys.py thoát ${scan.code}\n${scan.stdout}\n${scan.stderr}`).toBe(0);
        } finally {
            await sc.dispose();
        }
    });
});
