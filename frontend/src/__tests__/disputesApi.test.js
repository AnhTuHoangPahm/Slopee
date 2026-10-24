import { afterEach, describe, expect, it, vi } from 'vitest';
import * as web3 from '../api/web3';
import { createDisputeProposalAPI, fetchAdminDisputesAPI, forceResolveDisputeAPI, submitDisputeAPI } from '../api/disputes';

vi.mock('../api/web3', () => ({ request: vi.fn() }));
afterEach(() => vi.resetAllMocks());

describe('api/disputes', () => {
    it('proposal gửi payout_to (tên trường của SKELETON), KHÔNG gửi địa chỉ ví, bỏ reason_note rỗng, mã đơn được mã hóa', async () => {
        web3.request.mockResolvedValue({});
        await createDisputeProposalAPI('a/b c', { payoutSide: 'BUYER', reasonNote: '' });
        expect(web3.request).toHaveBeenCalledWith('/api/admin/disputes/a%2Fb%20c/proposal', { method: 'POST', body: { payout_to: 'BUYER' } });
        await createDisputeProposalAPI('x', { payoutSide: 'MERCHANT', reasonNote: 'Ảnh rõ' });
        expect(web3.request).toHaveBeenLastCalledWith('/api/admin/disputes/x/proposal', { method: 'POST', body: { payout_to: 'MERCHANT', reason_note: 'Ảnh rõ' } });
    });
    it('submit gọi đúng đường dẫn, danh tính chỉ từ token (thân rỗng)', async () => {
        web3.request.mockResolvedValue({ outcome: 'SENT' });
        await submitDisputeAPI('ord-1');
        expect(web3.request).toHaveBeenCalledWith('/api/disputes/ord-1/submit', { method: 'POST', body: {} });
    });
    it('danh sách: chuẩn hóa khi thiếu trường', async () => {
        web3.request.mockResolvedValue({ disputes: [{ order_id: 'a' }], server_time: 5 });
        expect(await fetchAdminDisputesAPI()).toEqual({ disputes: [{ order_id: 'a' }], serverTime: 5 });
        web3.request.mockResolvedValue({});
        expect(await fetchAdminDisputesAPI()).toEqual({ disputes: [], serverTime: null });
    });

    it('force-resolve gửi payout_to + reason_note tới đúng đường dẫn, mã đơn được mã hóa, bỏ reason_note rỗng', async () => {
        web3.request.mockResolvedValue({ outcome: 'SENT' });
        await forceResolveDisputeAPI('a/b c', { payoutSide: 'MERCHANT', reasonNote: 'Hai bên im lặng' });
        expect(web3.request).toHaveBeenCalledWith('/api/admin/disputes/a%2Fb%20c/force-resolve', { method: 'POST', body: { payout_to: 'MERCHANT', reason_note: 'Hai bên im lặng' } });
        await forceResolveDisputeAPI('x', { payoutSide: 'BUYER', reasonNote: '' });
        expect(web3.request).toHaveBeenLastCalledWith('/api/admin/disputes/x/force-resolve', { method: 'POST', body: { payout_to: 'BUYER' } });
    });
});
