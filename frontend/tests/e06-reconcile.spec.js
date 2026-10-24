// E-06 (AC-10, G-01): đối soát số dư contract. Mỗi kịch bản E-01…E-07 đã tự gọi expectReconciled ở cuối; file này kiểm cả hai đường độc lập
// sau toàn bộ các kịch bản trước (chạy sau E-05 theo thứ tự tên tệp, một worker): script CLI và API Admin.
import { test, expect } from '@playwright/test';
import { loginAdmin, newApi } from './helpers/api.js';
import { requireStack } from './helpers/stack.js';
import { reconcile } from './helpers/scripts.js';

test.describe('E-06 Đối soát số dư', () => {
    test.beforeEach(async () => { await requireStack(test); });

    test('scripts/reconcile.py --deep --events thoát 0 và API Admin đối soát thành công', async () => {
        const r = await reconcile({ waitSeconds: 60 });
        expect(r.code, `reconcile.py thoát ${r.code}\n${r.stdout}\n${r.stderr}`).toBe(0);

        const api = await newApi();
        try {
            const admin = await loginAdmin(api);
            const res = await api.get('/api/admin/reconcile?deep=1', { headers: { Authorization: `Bearer ${admin.token}` } });
            expect(res.status()).toBe(200);
        } finally {
            await api.dispose();
        }
    });
});
