// Mock fetch cho API tranh chấp (UC-06, SDD 9.6): dựng và thử màn hình ký phán quyết khi backend Tuần 6 chưa có.
// Hình dạng phản hồi BÁM hợp đồng đề xuất ở api/disputes.js. Khác web3Mock (chữ ký giả), mock này KIỂM CHỮ KÝ THẬT: khôi phục địa chỉ
// từ typed data `DisputeResolution` rồi so với ví của bên ký, đúng như backend (BAD_SIGNATURE) sẽ làm. Trang ký sai dữ liệu hay sai
// ví thì bị từ chối ở đây giống như bị hợp đồng từ chối. Bọc `fetch` hiện có: chỉ đón `/api/disputes/...`, phần còn lại chuyển tiếp.
//
// Dùng khi demo: VITE_WEB3_MOCK=true, đăng nhập (seller = Merchant, còn lại = Buyer), mở /disputes/mock-dispute-1. Ví MetaMask phải là
// ví Buyer (Anvil #5) hoặc Merchant (Anvil #6) mặc định bên dưới, hoặc truyền `buyerWallet`/`merchantWallet` của bạn.
import { buildDomain, recoverDisputeSigner } from '../lib/eip712';

const ANVIL = {
    buyer: '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc', // #5
    merchant: '0x976EA74026E726554dB657fA54763abd0C3a0aa9', // #6
    arbitrator: '0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC', // #2
    escrow: '0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512',
};
const SEVEN_DAYS = 7 * 86400;
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const err = (status, code, message, extra = {}) => json(status, { code, message, ...extra });
const hex = (n) => Array.from({ length: n }, () => Math.floor(Math.random() * 16).toString(16)).join('');

/**
 * @param {object} [opts]
 * @param {() => number} [opts.now]  giờ máy chủ (giây); mặc định đồng hồ máy
 * @param {number} [opts.latencyMs]
 * @param {number|null} [opts.autoExecuteMs]  sau khi `submit` thì tự chuyển EXECUTED sau chừng này ms (null = chỉ khi gọi state.execute())
 * @returns {{ uninstall: Function, state: object }}
 */
export function installDisputeMock({
    now = () => Math.floor(Date.now() / 1000), latencyMs = 80, autoExecuteMs = 1500,
    buyerWallet = ANVIL.buyer, merchantWallet = ANVIL.merchant, arbitratorWallet = ANVIL.arbitrator, escrow = ANVIL.escrow, chainId = 31337,
} = {}) {
    const realFetch = globalThis.fetch;
    const state = {
        forceRole: null, // 'BUYER' | 'MERCHANT' | null (null = theo vai trò đăng nhập: seller -> MERCHANT)
        calls: [], // [{ method, path, body }] để test xem đã gọi gì
        order: {
            order_id: 'mock-dispute-1', onchain_order_id: '100501', order_status: 'DISPUTED', amount_raw: '25000000', decimals: 6, symbol: 'mUSD',
            fee_bps: 300, disputed_at: now() - 3600, dispute_timeout: 2592000,
        },
        note: { reason: 'Hàng nhận được bị vỡ góc, khác với mô tả sản phẩm.', evidence_url: 'https://example.com/evidence/photo-1.jpg', updated_at: now() - 3000 },
        resolution: null,
        nextResolutionId: 1,
        serverSkewSec: 0, // lệch giờ giả giữa máy chủ và máy khách
    };

    const party = () => {
        if (state.forceRole) return state.forceRole;
        try { return JSON.parse(sessionStorage.getItem('user') || '{}').role === 'seller' ? 'MERCHANT' : 'BUYER'; } catch { return 'BUYER'; }
    };
    const serverNow = () => now() + state.serverSkewSec;
    const walletOf = (p) => (p === 'BUYER' ? buyerWallet : merchantWallet);

    const view = () => ({
        ...state.order, your_party: party(), buyer_wallet: buyerWallet, merchant_wallet: merchantWallet, server_time: serverNow(),
        note: state.note, resolution: state.resolution,
    });

    /** Việc của Admin (UC-06 bước 1-2): tạo đề xuất + chữ ký Trọng tài. `payoutTo`: 'buyer' | 'merchant' | địa chỉ. */
    state.propose = ({ payoutTo = 'buyer', ttlSec = SEVEN_DAYS, nonce = 0 } = {}) => {
        const to = payoutTo === 'buyer' ? buyerWallet : payoutTo === 'merchant' ? merchantWallet : payoutTo;
        const limit = state.order.disputed_at + state.order.dispute_timeout - 1;
        state.resolution = {
            resolution_id: state.nextResolutionId++, payout_to: to, amount_raw: state.order.amount_raw, nonce, deadline: Math.min(serverNow() + ttlSec, limit),
            status: 'PROPOSED', reason_note: 'Bằng chứng của Buyer khớp mô tả lỗi; đề xuất hoàn tiền.', submitted_tx_hash: null, created_at: serverNow(),
            signatures: [{ party: 'ARBITRATOR', signer: arbitratorWallet, signed_at: serverNow() }],
        };
        return state.resolution;
    };
    state.expire = () => { if (state.resolution) state.resolution.status = 'EXPIRED'; };
    state.execute = () => {
        const r = state.resolution;
        if (!r) return;
        r.status = 'EXECUTED';
        state.order.order_status = r.payout_to.toLowerCase() === buyerWallet.toLowerCase() ? 'REFUNDED' : 'COMPLETED';
    };

    const handle = async (method, path, rawBody) => {
        const body = rawBody ? JSON.parse(rawBody) : null;
        state.calls.push({ method, path, body });
        const m = path.match(/^\/api\/disputes\/([^/]+)(?:\/(signatures|submit))?$/);
        const [, code, action] = m;
        if (code !== state.order.order_id) return err(404, 'ORDER_NOT_FOUND', 'Không tìm thấy đơn hàng.');
        if (!action && method === 'GET') return json(200, view());

        const r = state.resolution;
        if (action === 'signatures' && method === 'POST') {
            if (!r || Number(body?.resolution_id) !== r.resolution_id) return err(404, 'ORDER_NOT_FOUND', 'Không tìm thấy đề xuất phán quyết.');
            if (r.status !== 'PROPOSED') return err(409, 'INVALID_STATE', 'Đề xuất không còn nhận chữ ký.', { status: r.status });
            if (serverNow() > r.deadline) return err(409, 'SIGNATURE_EXPIRED', 'Đề xuất đã hết hạn ký.');
            const p = party();
            if (r.signatures.some((s) => s.party === p)) return err(409, 'ALREADY_SIGNED', 'Bạn đã ký đề xuất này.');
            let signer;
            try {
                signer = recoverDisputeSigner(buildDomain({ chainId, escrow }), {
                    orderId: BigInt(state.order.onchain_order_id), payoutTo: r.payout_to, amount: BigInt(r.amount_raw), nonce: BigInt(r.nonce), deadline: BigInt(r.deadline),
                }, String(body?.signature ?? ''));
            } catch {
                return err(422, 'BAD_SIGNATURE', 'Chữ ký không hợp lệ.');
            }
            if (signer.toLowerCase() !== walletOf(p).toLowerCase()) return err(422, 'BAD_SIGNATURE', 'Chữ ký không khớp với ví đã liên kết.');
            r.signatures.push({ party: p, signer, signed_at: serverNow() });
            r.status = 'READY';
            return json(200, { status: 'READY' });
        }
        if (action === 'submit' && method === 'POST') {
            if (!r || r.status !== 'READY') return err(409, 'INVALID_STATE', 'Chưa đủ chữ ký để thi hành.', { status: r?.status ?? null });
            if (serverNow() > r.deadline) return err(409, 'SIGNATURE_EXPIRED', 'Đề xuất đã hết hạn ký.');
            r.status = 'SUBMITTED';
            r.submitted_tx_hash = `0x${hex(64)}`;
            if (autoExecuteMs !== null) setTimeout(state.execute, autoExecuteMs);
            return json(200, { tx_hash: r.submitted_tx_hash });
        }
        return err(405, 'METHOD_NOT_ALLOWED', 'Không hỗ trợ.');
    };

    globalThis.fetch = async (input, init = {}) => {
        const url = new URL(typeof input === 'string' ? input : input.url, 'http://localhost');
        if (!url.pathname.startsWith('/api/disputes/')) return realFetch(input, init);
        if (latencyMs) await new Promise((r) => setTimeout(r, latencyMs));
        return handle((init.method ?? 'GET').toUpperCase(), url.pathname, init.body);
    };
    return { uninstall: () => { globalThis.fetch = realFetch; }, state };
}
