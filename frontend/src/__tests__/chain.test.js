import { describe, it, expect, vi } from 'vitest';
import { DeploymentError, addChainParams, loadDeployment, parseDeployment, sameAddress, toChainIdHex } from '../lib/chain';

const ESCROW = '0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512';
const USD = '0x5FbDB2315678afecb367f032d93F642f64180aa3';
const valid = () => ({
    chainId: 31337,
    escrow: ESCROW,
    mockUSD: USD,
    deployBlock: 1,
    token: { address: USD, symbol: 'MUSD', decimals: 6 },
    roles: { shipper: '0x70997970C51812dc3A010C7d01b50e0d17dc79C8' },
    testAccounts: { buyer: '0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc' },
});

describe('parseDeployment', () => {
    it('chấp nhận tệp triển khai hợp lệ và đóng băng kết quả', () => {
        const d = parseDeployment(valid());
        expect(d.chainId).toBe(31337);
        expect(d.escrow).toBe(ESCROW);
        expect(d.token).toEqual({ symbol: 'MUSD', decimals: 6 });
        expect(Object.isFrozen(d)).toBe(true);
    });

    it('từ chối chainId khác 31337 (chỉ chạy trên Anvil)', () => {
        expect(() => parseDeployment({ ...valid(), chainId: 1 })).toThrow(DeploymentError);
    });

    it.each([
        ['escrow thiếu', { escrow: undefined }],
        ['escrow sai định dạng', { escrow: '0x123' }],
        ['mockUSD sai định dạng', { mockUSD: 'not-an-address' }],
        ['deployBlock âm', { deployBlock: -1 }],
        ['deployBlock không phải số nguyên', { deployBlock: '5' }],
        ['decimals sai', { token: { symbol: 'MUSD', decimals: 'six' } }],
    ])('từ chối: %s', (_name, patch) => {
        expect(() => parseDeployment({ ...valid(), ...patch })).toThrow(DeploymentError);
    });

    it('từ chối đầu vào rỗng', () => {
        expect(() => parseDeployment(null)).toThrow(DeploymentError);
        expect(() => parseDeployment({})).toThrow(DeploymentError);
    });
});

describe('loadDeployment', () => {
    it('tải và kiểm tra tệp', async () => {
        const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => valid() });
        const d = await loadDeployment(fetchImpl, '/deployments/local.json');
        expect(d.escrow).toBe(ESCROW);
        expect(fetchImpl).toHaveBeenCalledWith('/deployments/local.json', { cache: 'no-store' });
    });

    it('404 → báo cần chạy bootstrap.sh', async () => {
        const fetchImpl = vi.fn().mockResolvedValue({ ok: false });
        await expect(loadDeployment(fetchImpl)).rejects.toThrow(/bootstrap\.sh/);
    });

    it('lỗi mạng → DeploymentError', async () => {
        const fetchImpl = vi.fn().mockRejectedValue(new Error('offline'));
        await expect(loadDeployment(fetchImpl)).rejects.toBeInstanceOf(DeploymentError);
    });

    it('JSON hỏng → DeploymentError', async () => {
        const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => { throw new Error('bad'); } });
        await expect(loadDeployment(fetchImpl)).rejects.toBeInstanceOf(DeploymentError);
    });
});

describe('tiện ích chuỗi', () => {
    it('toChainIdHex(31337) = 0x7a69', () => expect(toChainIdHex(31337)).toBe('0x7a69'));

    it('addChainParams dùng chainId từ tệp triển khai', () => {
        const p = addChainParams(parseDeployment(valid()), 'http://127.0.0.1:8545');
        expect(p.chainId).toBe('0x7a69');
        expect(p.rpcUrls).toEqual(['http://127.0.0.1:8545']);
        expect(p.nativeCurrency.decimals).toBe(18);
    });

    it('sameAddress so sánh không phân biệt hoa thường và an toàn với giá trị rỗng', () => {
        expect(sameAddress(ESCROW, ESCROW.toLowerCase())).toBe(true);
        expect(sameAddress(ESCROW, USD)).toBe(false);
        expect(sameAddress(undefined, ESCROW)).toBe(false);
    });
});
