import { describe, expect, it } from 'vitest';
import { STAGE, canPropose, canResubmit, canSubmit, disputeStage, hasEnoughSignatures, notReadyMessage, safeEvidenceUrl, signatureRemaining,
    submitMessage, validateProposalForm } from '../lib/adminDisputes';

const clock = { serverTime: 1000, receivedAtMs: 0 };   // mọi lời gọi truyền nowMs=0: không phụ thuộc đồng hồ thật của máy chạy test
const dispute = (res) => ({ order_id: 'o1', resolution: res });
const R = (over = {}) => ({ status: 'PROPOSED', deadline: 5000, signed_by: ['ARBITRATOR'], expired: false, ...over });

describe('hasEnoughSignatures (khớp contract: hai bên KHÁC NHAU)', () => {
    it.each([
        [['ARBITRATOR', 'BUYER'], true], [['ARBITRATOR', 'MERCHANT'], true], [['BUYER', 'MERCHANT'], true],
        [['ARBITRATOR'], false], [['BUYER'], false], [[], false], [['BUYER', 'BUYER'], false],
    ])('%j -> %s', (signed, ok) => expect(hasEnoughSignatures(signed)).toBe(ok));
});

describe('disputeStage', () => {
    it('không có đề xuất -> NO_PROPOSAL', () => expect(disputeStage(dispute(null), clock, 0)).toBe(STAGE.NO_PROPOSAL));
    it('chỉ có chữ ký Trọng tài -> WAITING_SIGNATURE', () => expect(disputeStage(dispute(R()), clock, 0)).toBe(STAGE.WAITING_SIGNATURE));
    it('Trọng tài + Buyer -> READY', () => expect(disputeStage(dispute(R({ signed_by: ['ARBITRATOR', 'BUYER'] })), clock, 0)).toBe(STAGE.READY));
    it('đã nộp hoặc đã thi hành -> SUBMITTED', () => {
        expect(disputeStage(dispute(R({ status: 'SUBMITTED' })), clock, 0)).toBe(STAGE.SUBMITTED);
        expect(disputeStage(dispute(R({ status: 'EXECUTED' })), clock, 0)).toBe(STAGE.SUBMITTED);
    });
    it('EXPIRED/CANCELLED hoặc máy chủ báo expired -> EXPIRED', () => {
        expect(disputeStage(dispute(R({ status: 'EXPIRED' })), clock, 0)).toBe(STAGE.EXPIRED);
        expect(disputeStage(dispute(R({ status: 'CANCELLED' })), clock, 0)).toBe(STAGE.EXPIRED);
        expect(disputeStage(dispute(R({ expired: true, signed_by: ['ARBITRATOR', 'BUYER'] })), clock, 0)).toBe(STAGE.EXPIRED);
    });
    it('hết hạn theo ĐỒNG HỒ MÁY CHỦ dù danh sách chưa kịp làm mới (không đủ chữ ký cũng không thi hành được)', () => {
        const late = disputeStage(dispute(R({ signed_by: ['ARBITRATOR', 'BUYER'] })), clock, 4001 * 1000);     // 1000 + 4001 > 5000
        expect(late).toBe(STAGE.EXPIRED);
        expect(signatureRemaining(dispute(R()), clock, 0)).toBe(4000);
    });
    it('chưa có đồng hồ máy chủ thì không tự coi là hết hạn', () => {
        expect(signatureRemaining(dispute(R()), null)).toBeNull();
        expect(disputeStage(dispute(R()), null)).toBe(STAGE.WAITING_SIGNATURE);
    });
});

describe('quyền thao tác theo giai đoạn', () => {
    it('chỉ tạo đề xuất khi chưa có hoặc đã hết hạn; chỉ thi hành khi READY; nộp lại khi SUBMITTED', () => {
        expect(Object.values(STAGE).filter(canPropose).sort()).toEqual([STAGE.EXPIRED, STAGE.NO_PROPOSAL].sort());
        expect(Object.values(STAGE).filter(canSubmit)).toEqual([STAGE.READY]);
        expect(Object.values(STAGE).filter(canResubmit)).toEqual([STAGE.SUBMITTED]);
    });
});

describe('safeEvidenceUrl', () => {
    it.each(['javascript:alert(1)', 'data:text/html,<script>', 'file:///etc/passwd', 'ftp://a.com/x', '', null, undefined, 'khong-phai-url', 123])
        ('chặn %s', (u) => expect(safeEvidenceUrl(u)).toBeNull());
    it('chấp nhận http/https và cắt khoảng trắng', () => {
        expect(safeEvidenceUrl(' https://example.com/a.jpg ')).toBe('https://example.com/a.jpg');
        expect(safeEvidenceUrl('http://example.com')).toBe('http://example.com/');
    });
});

describe('validateProposalForm', () => {
    it('bắt buộc chọn bên nhận tiền', () => expect(validateProposalForm({ payoutSide: '', reasonNote: '' }).errors.payoutSide).toBeTruthy());
    it('chỉ nhận BUYER hoặc MERCHANT (không nhận địa chỉ ví tùy ý)', () => {
        expect(validateProposalForm({ payoutSide: '0xabc', reasonNote: '' }).ok).toBe(false);
        expect(validateProposalForm({ payoutSide: 'BUYER', reasonNote: '  ok  ' })).toMatchObject({ ok: true, value: { payoutSide: 'BUYER', reasonNote: 'ok' } });
    });
    it('ghi chú tối đa 2000 ký tự', () => expect(validateProposalForm({ payoutSide: 'MERCHANT', reasonNote: 'x'.repeat(2001) }).errors.reasonNote).toBeTruthy());
});

describe('thông báo', () => {
    it('submitMessage phân biệt đã thi hành trước đó', () => {
        expect(submitMessage({ outcome: 'ALREADY_RESOLVED' })).toMatch(/đã được thi hành/);
        expect(submitMessage({ outcome: 'SENT' })).toMatch(/Đã gửi phán quyết/);
    });
    it('notReadyMessage nêu bên đã ký', () => {
        expect(notReadyMessage({ extra: { signed_by: ['ARBITRATOR'] } })).toMatch(/Trọng tài/);
        expect(notReadyMessage({})).toMatch(/chưa ai/);
    });
});
