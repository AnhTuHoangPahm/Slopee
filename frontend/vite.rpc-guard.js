// Proxy JSON-RPC có lọc: /rpc -> Anvil (mặc định http://127.0.0.1:8545).
// Anvil mở khóa sẵn 10 tài khoản công khai (kể cả khóa vận hành của sàn) nên KHÔNG được để lộ nguyên trạng ra LAN/VPN.
// Chỉ cho các phương thức đọc + eth_sendRawTransaction (giao dịch đã ký bởi ví người dùng). Chặn eth_sendTransaction,
// eth_accounts, eth_sign*, personal_*, anvil_*, evm_*, hardhat_*, debug_*... Anvil vẫn chỉ nghe ở 127.0.0.1.
import http from 'node:http';

export const RPC_ALLOWED_METHODS = new Set([
    'web3_clientVersion', 'net_version', 'net_listening', 'eth_chainId', 'eth_syncing', 'eth_protocolVersion',
    'eth_blockNumber', 'eth_getBlockByNumber', 'eth_getBlockByHash', 'eth_getBlockTransactionCountByNumber',
    'eth_getBalance', 'eth_getCode', 'eth_getStorageAt', 'eth_getTransactionCount',
    'eth_getTransactionByHash', 'eth_getTransactionReceipt', 'eth_getLogs',
    'eth_call', 'eth_estimateGas', 'eth_gasPrice', 'eth_maxPriorityFeePerGas', 'eth_feeHistory',
    'eth_sendRawTransaction',
]);

const MAX_BODY = 1024 * 1024;
const MAX_BATCH = 50;

const rpcError = (id, message) => ({ jsonrpc: '2.0', id: id ?? null, error: { code: -32601, message } });

/** Trả về null nếu hợp lệ, hoặc đối tượng lỗi JSON-RPC nếu có phương thức bị chặn. */
export function checkRpcPayload(payload) {
    const calls = Array.isArray(payload) ? payload : [payload];
    if (calls.length === 0 || calls.length > MAX_BATCH) return rpcError(null, 'Batch không hợp lệ');
    for (const c of calls) {
        if (!c || typeof c !== 'object' || typeof c.method !== 'string' || !RPC_ALLOWED_METHODS.has(c.method)) {
            return rpcError(c?.id, `Phương thức RPC không được phép qua proxy: ${c?.method ?? '?'}`);
        }
    }
    return null;
}

export function rpcGuardPlugin(target = process.env.RPC_TARGET || 'http://127.0.0.1:8545') {
    const url = new URL(target);
    const handler = (req, res) => {
        const send = (code, obj) => {
            res.statusCode = code;
            res.setHeader('Content-Type', 'application/json');
            res.end(JSON.stringify(obj));
        };
        if (req.method !== 'POST') return send(405, rpcError(null, 'Chỉ chấp nhận POST'));
        const chunks = [];
        let size = 0;
        let aborted = false;
        req.on('data', (c) => {
            size += c.length;
            if (size > MAX_BODY) { aborted = true; send(413, rpcError(null, 'Body quá lớn')); req.destroy(); return; }
            chunks.push(c);
        });
        req.on('end', () => {
            if (aborted) return;
            const raw = Buffer.concat(chunks);
            let payload;
            try { payload = JSON.parse(raw.toString('utf8')); } catch { return send(400, rpcError(null, 'JSON không hợp lệ')); }
            const bad = checkRpcPayload(payload);
            if (bad) return send(403, bad);
            const up = http.request({
                hostname: url.hostname, port: url.port || 80, path: url.pathname === '/' ? '/' : url.pathname, method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Content-Length': raw.length },
            }, (r) => {
                res.statusCode = r.statusCode || 502;
                res.setHeader('Content-Type', 'application/json');
                r.pipe(res);
            });
            up.on('error', () => send(502, rpcError(null, 'Không kết nối được Anvil (chạy ./scripts/e2e_stack.sh up?)')));
            up.end(raw);
        });
    };
    return {
        name: 'slopee-rpc-guard',
        configureServer(server) { server.middlewares.use('/rpc', handler); },
        configurePreviewServer(server) { server.middlewares.use('/rpc', handler); },
    };
}
