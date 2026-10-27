/* global process */
// Tuần 8 [C] — kiểm tra "đủ stack" trước khi chạy E2E Web3 (Anvil + backend + tài khoản admin/shipper đã gieo).
// Cùng quy ước với REQUIRE_ANVIL của pytest: máy dev thiếu stack thì test bị bỏ qua có thông báo; CI đặt E2E_REQUIRE_STACK=1 nên thiếu là ĐỎ.
import { anvilUp, API_URL, loadDeployment } from './anvil.js';
import { loginAdmin, loginShipper, newApi } from './api.js';

let cached;

export function stackStatus() {
    cached ??= (async () => {
        const problems = [];
        if (!(await anvilUp())) problems.push('Anvil không chạy ở RPC_URL (chạy ./scripts/bootstrap.sh)');
        try { loadDeployment(); } catch (e) { problems.push(e.message); }
        const api = await newApi();
        try {
            const res = await api.get('/api/products/categories').catch(() => null);
            if (!res || !res.ok()) problems.push(`Backend không trả lời ở ${API_URL}`);
            else {
                await loginAdmin(api).catch(() => problems.push('Thiếu tài khoản admin E2E (./scripts/e2e_stack.sh seed)'));
                await loginShipper(api).catch(() => problems.push('Thiếu tài khoản shipper E2E (./scripts/e2e_stack.sh seed)'));
            }
        } finally {
            await api.dispose();
        }
        return { ok: problems.length === 0, problems };
    })();
    return cached;
}

/** Gọi trong `test.beforeEach(...)` của mỗi spec Web3. */
export async function requireStack(test) {
    const s = await stackStatus();
    if (s.ok) return;
    const msg = `Thiếu stack E2E: ${s.problems.join('; ')}`;
    if (process.env.E2E_REQUIRE_STACK === '1') throw new Error(msg);
    test.skip(true, msg);
}
