"""Ghi chú khiếu nại của Buyer (UC-05, SEQ-02): lý do + đường dẫn bằng chứng, lưu ở sàn.

Thứ tự đúng của SEQ-02: Buyer tự gửi `raiseDispute` lên chuỗi, Indexer ghi `DISPUTED`, SAU ĐÓ giao diện mới gửi ghi chú này.
Vì vậy chỉ nhận khi MySQL đã `DISPUTED` (trạng thái do Indexer ghi, BR-09), và chỉ từ đúng Buyer của đơn. Gửi lại (lỗi mạng) là
idempotent: ghi đè bản cũ. Sau khi Admin đã có đề xuất phán quyết thì khóa lại để bằng chứng Admin đang xét không bị đổi.
"""
from ..domain.dispute_note import clean_evidence_url, clean_reason
from ..domain.errors import DomainError


class DisputeNoteService:
    def __init__(self, uow_factory):
        self._uow = uow_factory

    def save_note(self, user_id, order_code, reason, evidence_url=None):
        reason, evidence_url = clean_reason(reason), clean_evidence_url(evidence_url)      # kiểm đầu vào trước khi chạm CSDL
        with self._uow() as uow:
            order = uow.dispute_notes.order_for_note(order_code, lock=True)
            if order is None or order['buyer_user_id'] != user_id:         # người khác/không tồn tại: không lộ sự tồn tại của đơn
                raise DomainError('ORDER_NOT_FOUND', 'Không tìm thấy đơn hàng.')
            if order['status'] != 'DISPUTED':
                raise DomainError('INVALID_STATE', 'Chỉ gửi lý do khiếu nại khi đơn đã được ghi nhận là đang khiếu nại.',
                                  {'status': order['status']})
            if uow.dispute_notes.has_resolution(order['order_id']):
                raise DomainError('INVALID_STATE', 'Đơn đã có đề xuất phán quyết, không thể sửa lý do khiếu nại.',
                                  {'status': order['status']})
            created = uow.dispute_notes.upsert(order['order_id'], user_id, reason, evidence_url)
            uow.commit()
        return {'order_id': order['order_id'], 'reason': reason, 'evidence_url': evidence_url, 'created': created}
