import { configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AdminDisputes from '../components/AdminDisputes';
import { Web3ApiError } from '../lib/errors';
import * as api from '../api/disputes';

configure({ asyncUtilTimeout: 4000 });
vi.mock('../api/disputes');

const base = {
    order_id: 'ord-12345678-aaaa', onchain_order_id: '1001', shop_name: 'Shop A', buyer_name: 'An', amount_raw: '16500000', symbol: 'mUSD',
    price_vnd: 412500, disputed_at: 1_800_000_000, dispute_timeout: 30 * 86400, force_resolve_at: 1_800_000_000 + 30 * 86400,
    note: { reason: 'Hàng bị vỡ', evidence_url: 'https://example.com/a.jpg' }, resolution: null,
};
const SERVER_TIME = 1_800_003_600;
const resolution = (over = {}) => ({ id: 1, status: 'PROPOSED', payout_to: '0xabc', payout_side: 'BUYER', amount_raw: '16500000', nonce: '0',
    deadline: SERVER_TIME + 7 * 86400, signed_by: ['ARBITRATOR'], reason_note: null, submitted_tx_hash: null, expired: false, ...over });
const list = (...disputes) => api.fetchAdminDisputesAPI.mockResolvedValue({ disputes, serverTime: SERVER_TIME });
const code = base.order_id;
afterEach(() => vi.resetAllMocks());

describe('AdminDisputes (UC-06)', () => {
    it('rỗng -> báo không có tranh chấp', async () => {
        list();
        render(<AdminDisputes />);
        expect(await screen.findByTestId('disputes-empty')).toBeTruthy();
    });

    it('hiện lý do của Buyer, liên kết bằng chứng an toàn, số tiền token và mốc thoát hiểm', async () => {
        list(base);
        render(<AdminDisputes />);
        const row = await screen.findByTestId(`dispute-${code}`);
        expect(within(row).getByTestId(`note-${code}`).textContent).toBe('Hàng bị vỡ');
        const link = within(row).getByRole('link', { name: 'Xem bằng chứng' });
        expect(link.getAttribute('href')).toBe('https://example.com/a.jpg');
        expect(link.getAttribute('rel')).toMatch(/noopener/);
        expect(row.textContent).toMatch(/16,50 mUSD/);
        expect(row.textContent).toMatch(/thoát hiểm/);
        expect(screen.getByTestId(`stage-${code}`).textContent).toBe('Chưa có đề xuất');
    });

    it('ẩn đường dẫn bằng chứng không an toàn (javascript:)', async () => {
        list({ ...base, note: { reason: 'x', evidence_url: 'javascript:alert(1)' } });
        render(<AdminDisputes />);
        const row = await screen.findByTestId(`dispute-${code}`);
        expect(within(row).queryByRole('link')).toBeNull();
        expect(row.textContent).toMatch(/không hợp lệ/);
    });

    it('lý do chứa HTML được hiển thị như chữ, không thành thẻ', async () => {
        list({ ...base, note: { reason: '<img src=x onerror=alert(1)>', evidence_url: null } });
        render(<AdminDisputes />);
        const el = await screen.findByTestId(`note-${code}`);
        expect(el.textContent).toBe('<img src=x onerror=alert(1)>');
        expect(el.querySelector('img')).toBeNull();
    });

    it('tạo đề xuất: phải chọn bên nhận tiền; có cảnh báo "bất kỳ ai cũng có thể thi hành"; gửi payout_side và ghi chú', async () => {
        list(base);
        api.createDisputeProposalAPI.mockResolvedValue({});
        render(<AdminDisputes />);
        fireEvent.click(await screen.findByRole('button', { name: 'Tạo đề xuất phán quyết' }));
        const dlg = screen.getByTestId('admin-dialog');
        expect(dlg.textContent).toMatch(/bất kỳ ai cũng có thể thi hành/);
        fireEvent.click(screen.getByTestId('dialog-confirm'));
        expect(api.createDisputeProposalAPI).not.toHaveBeenCalled();                  // chưa chọn bên
        expect(screen.getByRole('alert').textContent).toMatch(/chọn hoàn tiền/);
        fireEvent.click(screen.getByLabelText(/Hoàn tiền cho Buyer/));
        fireEvent.change(screen.getByTestId('proposal-note'), { target: { value: '  Ảnh rõ hàng vỡ  ' } });
        fireEvent.click(screen.getByTestId('dialog-confirm'));
        await waitFor(() => expect(api.createDisputeProposalAPI).toHaveBeenCalledWith(code, { payoutSide: 'BUYER', reasonNote: 'Ảnh rõ hàng vỡ' }));
        expect((await screen.findByTestId(`notice-${code}`)).textContent).toMatch(/Chờ Buyer hoặc Merchant ký/);
        expect(screen.queryByTestId('admin-dialog')).toBeNull();
    });

    it('hủy hộp thoại không gọi API', async () => {
        list(base);
        render(<AdminDisputes />);
        fireEvent.click(await screen.findByRole('button', { name: 'Tạo đề xuất phán quyết' }));
        fireEvent.click(screen.getByRole('button', { name: 'Hủy' }));
        expect(screen.queryByTestId('admin-dialog')).toBeNull();
        expect(api.createDisputeProposalAPI).not.toHaveBeenCalled();
    });

    it('chờ chữ ký: chưa có nút thi hành, hiện bên đã ký và thời gian còn lại', async () => {
        list({ ...base, resolution: resolution() });
        render(<AdminDisputes />);
        const res = await screen.findByTestId(`resolution-${code}`);
        expect(res.textContent).toMatch(/Hoàn tiền cho Buyer/);
        expect(res.textContent).toMatch(/Đã ký: Trọng tài/);
        await waitFor(() => expect(screen.getByTestId(`resolution-${code}`).textContent).toMatch(/còn 7 ngày/));      // đồng hồ máy chủ gán sau lần poll đầu
        expect(screen.queryByRole('button', { name: 'Thi hành phán quyết' })).toBeNull();
        expect(screen.getByTestId(`stage-${code}`).textContent).toBe('Chờ Buyer/Merchant ký');
    });

    it('đủ chữ ký: thi hành qua hộp thoại xác nhận (không dùng window.confirm), chỉ gọi API MỘT lần dù bấm đúp', async () => {
        const nativeConfirm = vi.spyOn(window, 'confirm');
        list({ ...base, resolution: resolution({ signed_by: ['ARBITRATOR', 'BUYER'] }) });
        let release;
        api.submitDisputeAPI.mockImplementation(() => new Promise((r) => { release = () => r({ outcome: 'SENT', tx_hash: '0x' + 'ab'.repeat(32) }); }));
        render(<AdminDisputes />);
        fireEvent.click(await screen.findByRole('button', { name: 'Thi hành phán quyết' }));
        const ok = screen.getByTestId('dialog-confirm');
        fireEvent.click(ok);
        fireEvent.click(ok);
        await waitFor(() => expect(api.submitDisputeAPI).toHaveBeenCalledTimes(1));
        expect(api.submitDisputeAPI).toHaveBeenCalledWith(code);
        release();
        expect((await screen.findByTestId(`notice-${code}`)).textContent).toMatch(/Đã gửi phán quyết/);
        expect(api.submitDisputeAPI).toHaveBeenCalledTimes(1);
        expect(nativeConfirm).not.toHaveBeenCalled();
    });

    it('lỗi chưa đủ chữ ký từ máy chủ nêu rõ ai đã ký', async () => {
        list({ ...base, resolution: resolution({ signed_by: ['ARBITRATOR', 'BUYER'] }) });
        api.submitDisputeAPI.mockRejectedValue(new Web3ApiError({ code: 'DISPUTE_NOT_READY', status: 409, extra: { signed_by: ['ARBITRATOR'] } }));
        render(<AdminDisputes />);
        fireEvent.click(await screen.findByRole('button', { name: 'Thi hành phán quyết' }));
        fireEvent.click(screen.getByTestId('dialog-confirm'));
        const n = await screen.findByTestId(`notice-${code}`);
        expect(n.getAttribute('role')).toBe('alert');
        expect(n.textContent).toMatch(/Đã có chữ ký của: Trọng tài/);
    });

    it('đề xuất hết hạn: không thi hành được, chỉ được tạo đề xuất mới', async () => {
        list({ ...base, resolution: resolution({ signed_by: ['ARBITRATOR', 'BUYER'], expired: true }) });
        render(<AdminDisputes />);
        await screen.findByTestId(`dispute-${code}`);
        expect(screen.getByTestId(`stage-${code}`).textContent).toMatch(/Hết hạn chữ ký/);
        expect(screen.queryByRole('button', { name: 'Thi hành phán quyết' })).toBeNull();
        expect(screen.getByRole('button', { name: 'Tạo đề xuất mới' })).toBeTruthy();
    });

    it('đã nộp: hiện mã giao dịch và cho nộp lại (idempotent)', async () => {
        list({ ...base, resolution: resolution({ status: 'SUBMITTED', signed_by: ['ARBITRATOR', 'BUYER'], submitted_tx_hash: '0x' + 'cd'.repeat(32) }) });
        render(<AdminDisputes />);
        const res = await screen.findByTestId(`resolution-${code}`);
        expect(res.textContent).toMatch(/0xcdcdcd…cdcd/);
        expect(screen.getByRole('button', { name: 'Nộp lại' })).toBeTruthy();
        expect(screen.queryByRole('button', { name: 'Thi hành phán quyết' })).toBeNull();
    });

    it('lỗi tải danh sách hiện cảnh báo, không sập', async () => {
        api.fetchAdminDisputesAPI.mockRejectedValue(new Web3ApiError({ code: 'CHAIN_UNAVAILABLE', status: 503 }));
        render(<AdminDisputes />);
        expect((await screen.findByRole('alert')).textContent).toMatch(/blockchain/);
    });

    describe('UC-07 thoát hiểm timeout: nút Xử đơn phương', () => {
        const past = { ...base, disputed_at: SERVER_TIME - 31 * 86400, force_resolve_at: SERVER_TIME - 3600 };       // đã quá hạn 1 giờ
        const EARLY = { ...base, force_resolve_at: SERVER_TIME + 2 * 86400 + 3 * 3600 };

        it('chưa tới mốc: hiện đếm ngược và nút bị tắt, bấm không mở hộp thoại', async () => {
            list(EARLY);
            render(<AdminDisputes />);
            await screen.findByTestId(`dispute-${code}`);
            await waitFor(() => expect(screen.getByTestId(`force-countdown-${code}`).textContent).toMatch(/sau 2 ngày 3 giờ/));
            const btn = screen.getByTestId(`force-btn-${code}`);
            expect(btn.disabled).toBe(true);
            fireEvent.click(btn);
            expect(screen.queryByTestId('admin-dialog')).toBeNull();
            expect(api.forceResolveDisputeAPI).not.toHaveBeenCalled();
        });

        it('đã quá hạn: nút bật; phải chọn bên và nhập lý do; gọi API MỘT lần dù bấm đúp', async () => {
            list(past);
            let release;
            api.forceResolveDisputeAPI.mockImplementation(() => new Promise((r) => { release = () => r({ outcome: 'SENT', tx_hash: '0x' + 'ab'.repeat(32) }); }));
            render(<AdminDisputes />);
            await screen.findByTestId(`dispute-${code}`);
            await waitFor(() => expect(screen.getByTestId(`force-btn-${code}`).disabled).toBe(false));
            expect(screen.getByTestId(`force-countdown-${code}`).textContent).toMatch(/Đã quá thời hạn/);
            fireEvent.click(screen.getByTestId(`force-btn-${code}`));
            expect(screen.getByTestId('admin-dialog').textContent).toMatch(/không thể hoàn tác/);
            const ok = screen.getByTestId('dialog-confirm');
            fireEvent.click(ok);                                                           // chưa chọn gì
            expect(api.forceResolveDisputeAPI).not.toHaveBeenCalled();
            expect(screen.getAllByRole('alert').length).toBe(2);
            fireEvent.click(screen.getByLabelText(/Giải ngân cho Merchant/));
            fireEvent.click(ok);                                                           // có bên nhưng thiếu lý do
            expect(api.forceResolveDisputeAPI).not.toHaveBeenCalled();
            fireEvent.change(screen.getByTestId('force-note'), { target: { value: '  Hai bên không phản hồi  ' } });
            fireEvent.click(ok);
            fireEvent.click(ok);
            await waitFor(() => expect(api.forceResolveDisputeAPI).toHaveBeenCalledTimes(1));
            expect(api.forceResolveDisputeAPI).toHaveBeenCalledWith(code, { payoutSide: 'MERCHANT', reasonNote: 'Hai bên không phản hồi' });
            release();
            expect((await screen.findByTestId(`notice-${code}`)).textContent).toMatch(/phán quyết đơn phương/);
            expect(screen.queryByTestId('admin-dialog')).toBeNull();
        });

        it('vẫn dùng được khi đang có đề xuất 2/3 dang dở (hai đường không cùng hợp lệ nên không cần hủy đề xuất)', async () => {
            list({ ...past, resolution: resolution({ status: 'EXPIRED' }) });
            render(<AdminDisputes />);
            await screen.findByTestId(`dispute-${code}`);
            await waitFor(() => expect(screen.getByTestId(`force-btn-${code}`).disabled).toBe(false));
        });

        it('máy chủ từ chối vì chưa tới mốc (đồng hồ lệch): báo còn bao lâu, không gửi giao dịch', async () => {
            list(past);
            api.forceResolveDisputeAPI.mockRejectedValue(new Web3ApiError({ code: 'FORCE_RESOLVE_TOO_EARLY', status: 409, extra: { force_resolve_at: 1, seconds_remaining: 5400 } }));
            render(<AdminDisputes />);
            await screen.findByTestId(`dispute-${code}`);
            await waitFor(() => expect(screen.getByTestId(`force-btn-${code}`).disabled).toBe(false));
            fireEvent.click(screen.getByTestId(`force-btn-${code}`));
            fireEvent.click(screen.getByLabelText(/Hoàn tiền cho Buyer/));
            fireEvent.change(screen.getByTestId('force-note'), { target: { value: 'quá hạn' } });
            fireEvent.click(screen.getByTestId('dialog-confirm'));
            const n = await screen.findByTestId(`notice-${code}`);
            expect(n.getAttribute('role')).toBe('alert');
            expect(n.textContent).toMatch(/còn 1 giờ 30 phút/);
        });

        it('ALREADY_RESOLVED: báo đã xử lý trước đó', async () => {
            list(past);
            api.forceResolveDisputeAPI.mockResolvedValue({ outcome: 'ALREADY_RESOLVED', tx_hash: null });
            render(<AdminDisputes />);
            await screen.findByTestId(`dispute-${code}`);
            await waitFor(() => expect(screen.getByTestId(`force-btn-${code}`).disabled).toBe(false));
            fireEvent.click(screen.getByTestId(`force-btn-${code}`));
            fireEvent.click(screen.getByLabelText(/Hoàn tiền cho Buyer/));
            fireEvent.change(screen.getByTestId('force-note'), { target: { value: 'x' } });
            fireEvent.click(screen.getByTestId('dialog-confirm'));
            expect((await screen.findByTestId(`notice-${code}`)).textContent).toMatch(/đã được xử lý trên blockchain/);
        });
    });
});
