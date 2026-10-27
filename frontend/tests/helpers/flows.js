// Tuần 8 [C] — các kịch bản con dùng lại giữa E-01…E-07: dựng dữ liệu, ký quỹ qua giao diện, khiếu nại, ký phán quyết.
// Nguyên tắc (DD-04, BR-09): trạng thái đơn CHỈ tin khi API/Indexer báo, không tin biên nhận của ví.
import { expect } from '@playwright/test';
import { addToCart, assignAndDeliver, buyerOrders, createMerchant, login, loginAdmin, loginShipper, newApi, orderStatus, signupAndLogin, waitForStatus } from './api.js';
import { fundWallet, testWallet } from './anvil.js';
import { depositAndWaitLocked, expectStatus, linkWalletInUi, openActor, orderPanel, startWeb3Checkout } from './ui.js';

export const USD = 10n ** 6n; // MockUSD có 6 decimals
export const feeOf = (amount, feeBps) => (amount * BigInt(feeBps)) / 10_000n; // làm tròn xuống, đúng contract (SlopeeEscrowMaster._payout)

/**
 * Dựng một kịch bản: `shops` Merchant (ví đã liên kết qua API), một Buyer (có mUSD + ETH thử), giỏ chứa 1 sản phẩm của mỗi shop,
 * và trình duyệt của Buyer với ví thử. `registerViaUi` đăng ký + đăng nhập bằng giao diện (E-01).
 */
export async function buildScenario(browser, { shops = 1, price = 400_000, registerViaUi = false } = {}) {
    const api = await newApi();
    const admin = await loginAdmin(api);
    const shipper = await loginShipper(api);
    const merchants = [];
    for (let i = 0; i < shops; i += 1) {
        merchants.push(await createMerchant(api, { wallet: testWallet(), products: [{ name: `Hàng E2E ${i + 1}`, price }] }));
    }

    const buyerWallet = testWallet();
    await fundWallet(buyerWallet.address, { usd: 1_000n * USD });

    let buyer;
    let actor;
    if (registerViaUi) {
        actor = await openActor(browser, { wallet: buyerWallet });
        buyer = await registerAndLoginInUi(actor.page, api);
    } else {
        buyer = await signupAndLogin(api, { label: 'buyer' });
        actor = await openActor(browser, { session: buyer, wallet: buyerWallet });
    }
    for (const m of merchants) await addToCart(api, buyer.token, m.products[0].id, 1);

    return { api, admin, shipper, merchants, buyer, buyerWallet, actor, orders: [], dispose: async () => { await actor.close(); await api.dispose(); } };
}

/** Đăng ký rồi đăng nhập bằng form thật; trả về token (đăng nhập API cùng tài khoản) để thêm giỏ hàng. */
async function registerAndLoginInUi(page, api) {
    const stamp = `${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`;
    const username = `e2e_ui_${stamp}`;
    const password = 'SecurePass123!';
    await page.goto('/signup'); // hộp thoại "Account created…" do openActor tự chấp nhận
    await page.getByPlaceholder('Full Name').fill('E2E Người Mua');
    await page.getByPlaceholder('Email').fill(`${username}@example.com`);
    await page.getByPlaceholder('Phone Number').fill(`0${String(Math.floor(Math.random() * 1e9)).padStart(9, '0')}`);
    await page.getByPlaceholder('Username (min 4 characters)').fill(username);
    await page.getByPlaceholder('Password', { exact: true }).fill(password);
    await page.getByPlaceholder('6-Digit Payment Passphrase').fill('123456');
    await page.getByRole('button', { name: 'SIGN UP' }).click();
    await expect(page).toHaveURL(/\/login/);

    await page.getByPlaceholder('Username').fill(username);
    await page.getByPlaceholder('Password').fill(password);
    await page.getByRole('button', { name: 'LOG IN' }).click();
    await expect(page).not.toHaveURL(/\/login/);
    const session = await login(api, username, password);
    return { ...session, username, password };
}

/** UC-00 + UC-01 + UC-02 qua giao diện: liên kết ví → báo giá → ký quỹ gom (approve + depositEscrowBatch) → đợi LOCKED. Trả các đơn theo thứ tự shop. */
export async function checkoutViaUi(sc) {
    const { page } = sc.actor;
    await linkWalletInUi(page);
    await startWeb3Checkout(page, { expectedShops: sc.merchants.length });
    await depositAndWaitLocked(page);
    await expect(page).toHaveURL(/\/orders/, { timeout: 30_000 });

    const list = await buyerOrders(sc.api, sc.buyer.token);
    sc.orders = sc.merchants.map((m) => {
        const o = list.find((x) => x.shopName === m.shopName);
        if (!o?.web3) throw new Error(`Không thấy đơn Web3 của shop ${m.shopName}`);
        return { code: o.orderId, onchainId: o.web3.onchain_order_id, merchant: m };
    });
    for (const o of sc.orders) expect(await waitForStatus(sc.api, sc.buyer.token, o.code, 'LOCKED')).toBe('LOCKED');
    return sc.orders;
}

/** Admin gán Shipper, Shipper xác nhận giao (relayer gửi confirmDelivery); đợi Indexer ghi DELIVERED. Trả trạng thái (có hạn kiểm tra/timeout). */
export async function deliver(sc, order) {
    await assignAndDeliver(sc.api, { adminToken: sc.admin.token, shipper: sc.shipper, code: order.code });
    await waitForStatus(sc.api, sc.buyer.token, order.code, 'DELIVERED');
    return orderStatus(sc.api, sc.buyer.token, order.code);
}

/** Buyer khiếu nại qua hộp thoại: giao dịch raiseDispute gửi trước, lý do chỉ lưu SAU khi Indexer ghi DISPUTED (SEQ-02). */
export async function raiseDisputeViaUi(sc, order, reason = 'Hàng nhận được không đúng mô tả (E2E).') {
    const { page } = sc.actor;
    await page.goto('/orders');
    const panel = orderPanel(page, order.code);
    await expectStatus(panel, 'DELIVERED'); // đơn LOCKED poll 15 giây nên đợi tới 90 giây
    await panel.getByTestId('dispute-btn').click();
    await page.getByTestId('dispute-reason').fill(reason);
    await page.getByTestId('dispute-evidence').fill('https://example.com/e2e-evidence.jpg');
    await page.getByTestId('dispute-submit').click();
    await expectStatus(panel, 'DISPUTED');
    await expect(panel.getByTestId('dispute-note-status')).toHaveAttribute('data-state', 'saved', { timeout: 60_000 });
}

/** Bên (Buyer hoặc Merchant) ký EIP-712 trên trang tranh chấp rồi nhờ sàn nộp; đợi Indexer ghi EXECUTED. */
export async function signDisputeAndExecute(page, code) {
    await page.goto(`/disputes/${code}`);
    await expect(page.getByTestId('proposal')).toBeVisible({ timeout: 90_000 }); // trang tự poll tới khi Admin đề xuất
    await expect(page.getByTestId('sign-warning')).toBeVisible();                // khung vàng đứng ngay trước nút ký (SDD 9.7)
    await page.getByTestId('ack').check();
    await page.getByTestId('sign-btn').click();
    await expect(page.getByTestId('phase-ready')).toBeVisible({ timeout: 60_000 });
    await page.getByTestId('execute-btn').click();
    await expect(page.getByTestId('phase-executed')).toBeVisible({ timeout: 120_000 });
}

/** Admin mở /admin bằng giao diện (không ví). */
export async function openAdmin(browser, sc) {
    const admin = await openActor(browser, { session: sc.admin });
    await admin.page.goto('/admin');
    await expect(admin.page.getByTestId('admin-disputes')).toBeVisible({ timeout: 30_000 });
    return admin;
}
