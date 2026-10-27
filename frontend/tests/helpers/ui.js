// Tuần 8 [C] — các bước giao diện dùng chung cho E2E (chọn bằng role/chữ/data-testid, KHÔNG bằng CSS mong manh).
import { expect } from '@playwright/test';
import { installMockWallet } from './walletMock.js';

/** Phiên đăng nhập giả lập cho trang (sessionStorage, đúng cách ứng dụng lưu: lib/client.js). Chạy trước mọi script của trang. */
export async function injectSession(page, session) {
    await page.addInitScript(([token, user]) => {
        window.sessionStorage.setItem('token', token);
        window.sessionStorage.setItem('user', JSON.stringify(user));
    }, [session.token, session.user]);
}

/** Một "người dùng trình duyệt": trang riêng (context riêng) + phiên + (tùy chọn) ví thử. */
export async function openActor(browser, { session, wallet, preconnected = false, acceptDialogs = true }) {
    const context = await browser.newContext({ baseURL: 'http://localhost:5173' });
    const page = await context.newPage();
    if (acceptDialogs) page.on('dialog', (d) => d.accept()); // window.confirm của nút "Đã nhận hàng" (chưa đổi sang hộp thoại React: xem PROGRESS Tuần 8)
    const mock = wallet ? await installMockWallet(page, wallet, { preconnected }) : null;
    if (session) await injectSession(page, session);
    return { context, page, wallet: mock, close: () => context.close() };
}

/** UC-00 qua giao diện: kết nối ví thử → ký personal_sign (không tốn gas) → liên kết. */
export async function linkWalletInUi(page) {
    await page.goto('/wallet');
    await page.getByRole('button', { name: 'Kết nối MetaMask' }).click();
    await expect(page.getByTestId('connected-address')).toBeVisible();
    await page.getByRole('button', { name: 'Liên kết ví này' }).click();
    await expect(page.getByTestId('link-ok')).toBeVisible({ timeout: 30_000 });
}

/** Giỏ → Thanh toán → chọn "Thanh toán Web3" → Tạo báo giá. Dừng ở bước đã có báo giá (chưa ký quỹ). */
export async function startWeb3Checkout(page, { expectedShops }) {
    await page.goto('/cart');
    await page.getByLabel(/Select All/).first().check();
    await page.getByRole('button', { name: 'Proceed to checkout' }).click();
    await expect(page).toHaveURL(/\/checkout/);
    await page.getByTestId('web3-method').locator('input[type="radio"]').check();
    await expect(page.getByTestId('web3-panel')).toBeVisible();
    // Ví đã kết nối từ bước liên kết (eth_accounts khôi phục phiên) nên không còn nút "Kết nối MetaMask"; chưa kết nối thì bấm
    const connect = page.getByTestId('web3-panel').getByRole('button', { name: 'Kết nối MetaMask' });
    if (await connect.isVisible().catch(() => false)) await connect.click();
    await page.getByRole('button', { name: 'Tạo báo giá' }).click();
    await expect(page.getByTestId('quote-result')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('quote-row')).toHaveCount(expectedShops);
}

/** Bấm "Ký quỹ" (approve + depositEscrowBatch) và đợi API báo MỌI đơn con LOCKED (DD-04: không tin biên nhận ví). */
export async function depositAndWaitLocked(page) {
    await page.getByTestId('deposit-button').click();
    await expect(page.getByTestId('deposit-locked')).toBeVisible({ timeout: 120_000 });
}

export const orderPanel = (page, code) => page.locator(`[data-testid="web3-panel"][data-order="${code}"]`);
export const badge = (panel) => panel.getByTestId('status-badge');
export async function expectStatus(panel, status, timeout = 90_000) {
    await expect(badge(panel)).toHaveAttribute('data-status', status, { timeout });
}
