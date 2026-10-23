import { describe, expect, it, vi } from 'vitest';
import {
    ACTION_STEP, ORDER_ACTION, TARGET_STATUS, clearDisputeDraft, initialActionState, isActionBusy, loadDisputeDraft, mapOrderActionError,
    orderActionReducer, runOrderAction, saveDisputeDraft, validateDisputeForm,
} from '../lib/orderActions';

const run = (events) => events.reduce(orderActionReducer, initialActionState());
const tx = (hash = '0xabc', wait = async () => ({ status: 1 })) => ({ hash, wait: vi.fn(wait) });

describe('orderActionReducer', () => {
    it('đường vui: IDLE -> SIGNING -> CONFIRMING -> WAITING_INDEXER -> DONE', () => {
        let s = orderActionReducer(initialActionState(), { type: 'START', kind: ORDER_ACTION.EARLY_RELEASE });
        expect(s.step).toBe(ACTION_STEP.SIGNING);
        s = orderActionReducer(s, { type: 'SENT', hash: '0x1' });
        expect(s).toMatchObject({ step: ACTION_STEP.CONFIRMING, txHash: '0x1' });
        s = orderActionReducer(s, { type: 'MINED' });
        expect(s.step).toBe(ACTION_STEP.WAITING_INDEXER);
        s = orderActionReducer(s, { type: 'INDEXED' });
        expect(s.step).toBe(ACTION_STEP.DONE);
    });
    it('biên nhận KHÔNG phải trạng thái mới: MINED chưa phải DONE', () => {
        expect(isActionBusy(run([{ type: 'START', kind: 'X' }, { type: 'SENT', hash: 'h' }, { type: 'MINED' }]))).toBe(true);
    });
    it('Indexer nhanh hơn biên nhận: INDEXED chấp nhận từ CONFIRMING', () => {
        expect(run([{ type: 'START', kind: 'X' }, { type: 'SENT', hash: 'h' }, { type: 'INDEXED' }]).step).toBe(ACTION_STEP.DONE);
    });
    it('sự kiện sai thứ tự/trùng bị bỏ qua, không lùi bước', () => {
        expect(run([{ type: 'MINED' }]).step).toBe(ACTION_STEP.IDLE);
        expect(run([{ type: 'INDEXED' }]).step).toBe(ACTION_STEP.IDLE);
        const s = run([{ type: 'START', kind: 'X' }, { type: 'SENT', hash: 'h' }, { type: 'MINED' }, { type: 'START', kind: 'Y' }]);
        expect(s.step).toBe(ACTION_STEP.WAITING_INDEXER);
        expect(s.kind).toBe('X');
    });
    it('FAIL rồi cho thử lại (START từ FAILED); FAIL không đè DONE', () => {
        let s = run([{ type: 'START', kind: 'X' }, { type: 'FAIL', error: { message: 'm' } }]);
        expect(s.step).toBe(ACTION_STEP.FAILED);
        s = orderActionReducer(s, { type: 'START', kind: 'X' });
        expect(s).toMatchObject({ step: ACTION_STEP.SIGNING, error: null, txHash: null });
        const done = run([{ type: 'START', kind: 'X' }, { type: 'SENT', hash: 'h' }, { type: 'INDEXED' }, { type: 'FAIL', error: {} }]);
        expect(done.step).toBe(ACTION_STEP.DONE);
    });
});

describe('runOrderAction', () => {
    const collect = () => { const events = []; return { events, dispatch: (e) => events.push(e) }; };

    it('earlyRelease: gọi hợp đồng với BigInt, phát START/SENT/MINED, dừng trước DONE', async () => {
        const escrow = { earlyRelease: vi.fn(async () => tx('0xe1')), raiseDispute: vi.fn() };
        const { events, dispatch } = collect();
        const r = await runOrderAction({ kind: ORDER_ACTION.EARLY_RELEASE, onchainOrderId: '100001', escrow, dispatch });
        expect(escrow.earlyRelease).toHaveBeenCalledWith(100001n);
        expect(escrow.raiseDispute).not.toHaveBeenCalled();
        expect(r).toEqual({ hash: '0xe1' });
        expect(events.map((e) => e.type)).toEqual(['START', 'SENT', 'MINED']);
    });
    it('raiseDispute gọi đúng hàm', async () => {
        const escrow = { earlyRelease: vi.fn(), raiseDispute: vi.fn(async () => tx()) };
        await runOrderAction({ kind: ORDER_ACTION.RAISE_DISPUTE, onchainOrderId: 7, escrow, dispatch: () => {} });
        expect(escrow.raiseDispute).toHaveBeenCalledWith(7n);
    });
    it('người dùng hủy trong ví: phát FAIL userRejected và ném lại', async () => {
        const escrow = { earlyRelease: vi.fn(async () => { throw Object.assign(new Error('rejected'), { code: 4001 }); }) };
        const { events, dispatch } = collect();
        await expect(runOrderAction({ kind: ORDER_ACTION.EARLY_RELEASE, onchainOrderId: 1, escrow, dispatch })).rejects.toBeTruthy();
        expect(events.at(-1)).toMatchObject({ type: 'FAIL', error: { code: 'USER_REJECTED', userRejected: true } });
    });
    it('giao dịch revert khi chờ biên nhận: phát FAIL, không phát MINED', async () => {
        const escrow = { earlyRelease: vi.fn(async () => tx('0x1', async () => { throw Object.assign(new Error('x'), { reason: 'Not delivered' }); })) };
        const { events, dispatch } = collect();
        await expect(runOrderAction({ kind: ORDER_ACTION.EARLY_RELEASE, onchainOrderId: 1, escrow, dispatch })).rejects.toBeTruthy();
        expect(events.map((e) => e.type)).toEqual(['START', 'SENT', 'FAIL']);
        expect(events.at(-1).error.message).toMatch(/không còn ở trạng thái chờ kiểm tra/);
    });
    it('hành động lạ/id sai: FAIL, không gọi hợp đồng', async () => {
        const escrow = { earlyRelease: vi.fn(), raiseDispute: vi.fn() };
        const { events, dispatch } = collect();
        await expect(runOrderAction({ kind: 'NOPE', onchainOrderId: 1, escrow, dispatch })).rejects.toBeTruthy();
        await expect(runOrderAction({ kind: ORDER_ACTION.EARLY_RELEASE, onchainOrderId: 'abc', escrow, dispatch })).rejects.toBeTruthy();
        expect(escrow.earlyRelease).not.toHaveBeenCalled();
        expect(events.filter((e) => e.type === 'FAIL')).toHaveLength(2);
    });
});

describe('mapOrderActionError', () => {
    it.each([
        [{ reason: 'Not delivered' }, /không còn ở trạng thái chờ kiểm tra/],
        [{ reason: 'Only buyer' }, /Chỉ ví đã ký quỹ/],
        [{ reason: 'Expired' }, /quá thời hạn kiểm tra/],
        [{ reason: 'Under inspection' }, /Chưa hết thời hạn kiểm tra/],
        [{ shortMessage: 'execution reverted: "Only buyer"' }, /Chỉ ví đã ký quỹ/],
    ])('revert %j', (err, re) => {
        const m = mapOrderActionError(err);
        expect(m.code).toBe('TX_REVERTED');
        expect(m.message).toMatch(re);
    });
    it('hủy ví (4001) và ACTION_REJECTED', () => {
        expect(mapOrderActionError({ code: 4001 }).userRejected).toBe(true);
        expect(mapOrderActionError({ code: 'ACTION_REJECTED' }).userRejected).toBe(true);
    });
    it('yêu cầu ví đang chờ (-32002)', () => expect(mapOrderActionError({ code: -32002 }).code).toBe('REQUEST_PENDING'));
    it('lỗi lạ: thông điệp chung, không lộ chi tiết kỹ thuật', () => {
        const m = mapOrderActionError(new Error('secret rpc url http://x'));
        expect(m.code).toBe('TX_FAILED');
        expect(m.message).not.toMatch(/rpc|http/i);
    });
});

describe('validateDisputeForm', () => {
    it('hợp lệ, có cắt khoảng trắng; bằng chứng có thể bỏ trống', () => {
        const r = validateDisputeForm({ reason: '  Hàng bị vỡ khi nhận  ', evidenceUrl: '' });
        expect(r.ok).toBe(true);
        expect(r.value).toEqual({ reason: 'Hàng bị vỡ khi nhận', evidenceUrl: '' });
    });
    it('lý do quá ngắn/quá dài', () => {
        expect(validateDisputeForm({ reason: 'ngắn' }).errors.reason).toMatch(/tối thiểu/);
        expect(validateDisputeForm({ reason: 'x'.repeat(1001) }).errors.reason).toMatch(/tối đa/);
    });
    it.each(['javascript:alert(1)', 'data:text/html,x', 'file:///etc/passwd', 'abc', 'ftp://x.com/a'])('chặn URL bằng chứng %s', (u) =>
        expect(validateDisputeForm({ reason: 'lý do đủ dài rồi', evidenceUrl: u }).errors.evidenceUrl).toBeTruthy());
    it('nhận http/https', () => {
        expect(validateDisputeForm({ reason: 'lý do đủ dài rồi', evidenceUrl: 'https://img.example.com/a.jpg' }).ok).toBe(true);
        expect(validateDisputeForm({ reason: 'lý do đủ dài rồi', evidenceUrl: 'http://x.com/v' }).ok).toBe(true);
    });
    it('URL quá dài', () => expect(validateDisputeForm({ reason: 'lý do đủ dài rồi', evidenceUrl: `https://x.com/${'a'.repeat(500)}` }).errors.evidenceUrl).toMatch(/tối đa/));
});

describe('bản nháp khiếu nại (sessionStorage)', () => {
    it('lưu / đọc / xóa theo mã đơn', () => {
        saveDisputeDraft('o1', { reason: 'abc def ghi jkl', evidenceUrl: 'https://x.com' });
        expect(loadDisputeDraft('o1')).toEqual({ reason: 'abc def ghi jkl', evidenceUrl: 'https://x.com' });
        expect(loadDisputeDraft('o2')).toBeNull();
        clearDisputeDraft('o1');
        expect(loadDisputeDraft('o1')).toBeNull();
    });
    it('dữ liệu hỏng trong storage thì coi như không có', () => {
        sessionStorage.setItem('slopee.disputeNote.bad', '{not json');
        expect(loadDisputeDraft('bad')).toBeNull();
        sessionStorage.setItem('slopee.disputeNote.bad2', JSON.stringify({ reason: 5 }));
        expect(loadDisputeDraft('bad2')).toBeNull();
    });
    it('storage ném lỗi (bị chặn) không làm vỡ luồng', () => {
        const broken = { setItem() { throw new Error('quota'); }, getItem() { throw new Error('x'); }, removeItem() { throw new Error('x'); } };
        expect(() => saveDisputeDraft('o', { reason: 'r' }, broken)).not.toThrow();
        expect(loadDisputeDraft('o', broken)).toBeNull();
        expect(() => clearDisputeDraft('o', broken)).not.toThrow();
    });
});

// ---- Tuần 7 [C] (UC-07): "Hủy đơn" quá 14 ngày chưa giao = cancelIfUnfulfilled ----------------------------------------------------------
describe('cancelIfUnfulfilled (CANCEL_UNFULFILLED)', () => {
    it('đích là REFUNDED: chỉ khi API (Indexer) báo REFUNDED mới coi là xong', () => {
        expect(TARGET_STATUS[ORDER_ACTION.CANCEL_UNFULFILLED]).toBe('REFUNDED');
    });
    it('runOrderAction gọi đúng hàm với BigInt, không đụng hàm khác, dừng ở MINED', async () => {
        const events = [];
        const escrow = { cancelIfUnfulfilled: vi.fn(async () => tx('0xca')), earlyRelease: vi.fn(), raiseDispute: vi.fn() };
        const r = await runOrderAction({ kind: ORDER_ACTION.CANCEL_UNFULFILLED, onchainOrderId: '100002', escrow, dispatch: (e) => events.push(e) });
        expect(escrow.cancelIfUnfulfilled).toHaveBeenCalledWith(100002n);
        expect(escrow.earlyRelease).not.toHaveBeenCalled();
        expect(escrow.raiseDispute).not.toHaveBeenCalled();
        expect(r).toEqual({ hash: '0xca' });
        expect(events.map((e) => e.type)).toEqual(['START', 'SENT', 'MINED']);
        expect(events[0]).toMatchObject({ type: 'START', kind: ORDER_ACTION.CANCEL_UNFULFILLED });
    });
    it('luồng reducer: SIGNING -> CONFIRMING -> WAITING_INDEXER -> DONE', () => {
        const s = [{ type: 'START', kind: ORDER_ACTION.CANCEL_UNFULFILLED }, { type: 'SENT', hash: '0x1' }, { type: 'MINED' }, { type: 'INDEXED' }].reduce(orderActionReducer, initialActionState());
        expect(s).toMatchObject({ step: ACTION_STEP.DONE, kind: ORDER_ACTION.CANCEL_UNFULFILLED });
    });
    it('người dùng hủy trong ví: FAIL userRejected, không phải lỗi hệ thống', async () => {
        const events = [];
        const escrow = { cancelIfUnfulfilled: vi.fn(async () => { throw Object.assign(new Error('rejected'), { code: 4001 }); }) };
        await expect(runOrderAction({ kind: ORDER_ACTION.CANCEL_UNFULFILLED, onchainOrderId: 1, escrow, dispatch: (e) => events.push(e) })).rejects.toBeTruthy();
        expect(events.at(-1)).toMatchObject({ type: 'FAIL', error: { code: 'USER_REJECTED', userRejected: true } });
    });
    it.each([
        [{ reason: 'Timeout not reached' }, /Chưa quá 14 ngày/],
        [{ shortMessage: 'execution reverted: "Timeout not reached"' }, /Chưa quá 14 ngày/],
        [{ reason: 'Not locked' }, /không còn ở trạng thái chờ giao/],
        [{ reason: 'Unauthorized' }, /Chỉ ví đã ký quỹ/],
    ])('revert của contract %j được dịch sang tiếng Việt', (err, re) => {
        const m = mapOrderActionError(err);
        expect(m).toMatchObject({ code: 'TX_REVERTED', userRejected: false });
        expect(m.message).toMatch(re);
    });
    it('lý do revert cũ không bị đổi nghĩa bởi ba cụm mới', () => {
        expect(mapOrderActionError({ reason: 'Not delivered' }).message).toMatch(/không còn ở trạng thái chờ kiểm tra/);
        expect(mapOrderActionError({ reason: 'Under inspection' }).message).toMatch(/Chưa hết thời hạn kiểm tra/);
    });
});
