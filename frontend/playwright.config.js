/* global process */
import { defineConfig, devices } from '@playwright/test';

// Hai nhóm test:
//   firefox   : bộ cũ (đăng ký, Tetris), cần MySQL để dọn dữ liệu.
//   web3-e2e  : Tuần 8, E-01…E-07 trên stack thật (Anvil + backend + Indexer + Scheduler) với ví thử EIP-1193 (tests/helpers/walletMock.js).
//               Chạy TUẦN TỰ một worker: các kịch bản tua giờ Anvil tiến vĩnh viễn và dùng chung một chuỗi/CSDL.
//               Dựng stack: ./scripts/e2e_stack.sh up  ·  chạy: npx playwright test --project=web3-e2e
const WEB3 = /e0[1-7]-.*\.spec\.js$/;

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0, // thử lại trên chuỗi dùng chung có thể gây trùng ví/đơn; lỗi phải thấy ngay
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'html',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    ignoreHTTPSErrors: true, // dev server có thể chạy HTTPS tự ký (frontend/certs) khi dùng E2E_BASE_URL=https://localhost:5173
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: process.env.E2E_NO_WEBSERVER ? undefined : {
    command: 'npm run dev -- --port 5173 --strictPort',
    url: process.env.E2E_BASE_URL || 'http://localhost:5173',
    env: { ...process.env, VITE_HTTPS: process.env.E2E_BASE_URL?.startsWith('https') ? '1' : '0' }, // test mặc định chạy http thuần dù có frontend/certs
    ignoreHTTPSErrors: true,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    { name: 'firefox', testIgnore: WEB3, use: { ...devices['Desktop Firefox'] } },
    { name: 'web3-e2e', testMatch: WEB3, use: { ...devices['Desktop Firefox'] } },
  ],
});
