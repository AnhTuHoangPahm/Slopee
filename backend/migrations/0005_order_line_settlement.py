"""Quyết định nhóm (Phase 0, S-05): hủy đơn `paid` phải hoàn tiền + hoàn kho mà KHÔNG tạo ra tiền.

Hoàn tiền cho người mua chỉ an toàn khi thu lại đúng khoản đã cộng cho người bán. Checkout cũ không ghi lại
người bán nào được cộng bao nhiêu, nên thêm hai cột vào orderLines:
- sellerPaymentMethodId: phương thức thanh toán của người bán đã được cộng (NULL nếu không có / tài khoản đã bị xóa)
- sellerCredit:          số VND đã cộng cho người bán từ dòng này (0 nếu người mua không bị trừ tiền: COD, 'cash')

Backfill đơn cũ (đã thanh toán bằng phương thức không phải 'cash'): suy ra người bán từ products -> shops -> người
bán và phương thức đầu tiên theo id (đúng cách checkout cũ đã chọn). Dòng có productId = NULL (sản phẩm đã bị xóa)
không suy ra được nên giữ sellerCredit = 0 (giới hạn đã biết của dữ liệu cũ; DB demo nên tạo lại bằng init_db.py).
Idempotent: chạy lại trên DB đã đúng không đổi gì.
"""
from dbschema import add_column_if_missing, ensure_foreign_key


def upgrade(cursor):
    add_column_if_missing(cursor, 'orderLines', 'sellerPaymentMethodId', 'varchar(36) NULL')
    added = add_column_if_missing(cursor, 'orderLines', 'sellerCredit',
                                  "decimal(15,0) NOT NULL DEFAULT 0 COMMENT 'VND đã cộng cho người bán từ dòng này'")
    ensure_foreign_key(cursor, 'orderLines', 'sellerPaymentMethodId', 'paymentMethods', 'id',
                       'fk_orderlines_seller_pm', 'SET NULL')

    if added:  # chỉ backfill đúng lần đầu cột được tạo (không ghi đè dữ liệu mới)
        cursor.execute("""
            UPDATE orderLines ol
            JOIN orders o ON o.id = ol.orderId
            JOIN paymentMethods bpm ON bpm.id = o.paymentMethodId AND bpm.methodType <> 'cash'
            JOIN products p ON p.id = ol.productId
            JOIN shops s ON s.id = p.shopId
            SET ol.sellerCredit = ol.unitPrice * ol.quantity,
                ol.sellerPaymentMethodId = (SELECT MIN(spm.id) FROM paymentMethods spm WHERE spm.userId = s.sellerId)
            WHERE o.status IN ('paid', 'shipped', 'received')
        """)
