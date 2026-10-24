/* global process */
// Tuần 8 [C] — chạy các script chỉ-đọc của dự án từ test: đối soát số dư (E-06, AC-10) và quét khóa (E-05, AC-09).
// Kết quả nằm ở MÃ THOÁT (0 = đạt), giống cách CI/cron dùng.
import { execFile } from 'node:child_process';
import path from 'node:path';
import { REPO_ROOT } from './anvil.js';

const PYTHON = process.env.PYTHON ?? 'python3';

function run(args, { timeoutMs = 120_000 } = {}) {
    return new Promise((resolve) => {
        execFile(PYTHON, args, { cwd: REPO_ROOT, env: process.env, timeout: timeoutMs, maxBuffer: 8 * 1024 * 1024 }, (err, stdout, stderr) => {
            resolve({ code: err ? (typeof err.code === 'number' ? err.code : 2) : 0, stdout: String(stdout), stderr: String(stderr) });
        });
    });
}

/** scripts/reconcile.py --deep --events --wait 30: số dư contract == tổng đơn mở + sổ chờ rút, và trạng thái từng đơn khớp chuỗi. */
export const reconcile = ({ waitSeconds = 30 } = {}) => run([path.join('scripts', 'reconcile.py'), '--deep', '--events', '--wait', String(waitSeconds)]);

/** Khẳng định đối soát khớp; thông báo lỗi kèm đầu ra của script để gỡ lỗi ngay trong báo cáo Playwright. */
export async function expectReconciled(expect) {
    const r = await reconcile();
    expect(r.code, `reconcile.py thoát ${r.code}\n${r.stdout}\n${r.stderr}`).toBe(0);
}

/** scripts/scan_no_user_keys.py [--db] [--logs ...]: 0 = không có khóa/seed người dùng. */
export const scanNoUserKeys = ({ db = false, logs = [] } = {}) =>
    run([path.join('scripts', 'scan_no_user_keys.py'), ...(db ? ['--db'] : []), ...(logs.length ? ['--logs', ...logs] : [])]);
