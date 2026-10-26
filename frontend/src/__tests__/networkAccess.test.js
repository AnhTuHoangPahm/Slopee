import { describe, it, expect } from 'vitest';
import { guessRpcUrl } from '../lib/chain';
import { checkRpcPayload } from '../../vite.rpc-guard.js';

describe('guessRpcUrl (truy cập từ LAN/VPN)', () => {
    it('loopback → Anvil trực tiếp', () => {
        expect(guessRpcUrl({ hostname: 'localhost', origin: 'http://localhost:5173' })).toBe('http://127.0.0.1:8545');
        expect(guessRpcUrl({ hostname: '127.0.0.1', origin: 'https://127.0.0.1:5173' })).toBe('http://127.0.0.1:8545');
    });
    it('IP VPN/LAN → proxy /rpc cùng origin (HTTPS cho MetaMask)', () => {
        expect(guessRpcUrl({ hostname: '100.64.1.2', origin: 'https://100.64.1.2:5173' })).toBe('https://100.64.1.2:5173/rpc');
        expect(guessRpcUrl({ hostname: 'pc.tail1234.ts.net', origin: 'https://pc.tail1234.ts.net:5173' })).toBe('https://pc.tail1234.ts.net:5173/rpc');
    });
});

describe('proxy /rpc chỉ cho phương thức an toàn', () => {
    const call = (method, id = 1) => ({ jsonrpc: '2.0', id, method, params: [] });
    it('cho phép đọc + eth_sendRawTransaction', () => {
        for (const m of ['eth_chainId', 'eth_call', 'eth_getLogs', 'eth_sendRawTransaction', 'eth_estimateGas']) {
            expect(checkRpcPayload(call(m))).toBeNull();
        }
    });
    it('chặn tài khoản mở khóa sẵn của Anvil và các lệnh quản trị', () => {
        for (const m of ['eth_sendTransaction', 'eth_accounts', 'eth_sign', 'personal_sign', 'anvil_setBalance', 'evm_increaseTime', 'hardhat_impersonateAccount', 'debug_traceCall']) {
            expect(checkRpcPayload(call(m, 7))?.error?.message).toContain(m);
        }
    });
    it('batch: một phương thức xấu làm hỏng cả batch; batch rỗng/quá lớn bị chặn; rác bị chặn', () => {
        expect(checkRpcPayload([call('eth_chainId'), call('anvil_mine', 2)])).not.toBeNull();
        expect(checkRpcPayload([])).not.toBeNull();
        expect(checkRpcPayload(Array.from({ length: 51 }, () => call('eth_chainId')))).not.toBeNull();
        expect(checkRpcPayload(null)).not.toBeNull();
        expect(checkRpcPayload({ id: 1 })).not.toBeNull();
    });
});
