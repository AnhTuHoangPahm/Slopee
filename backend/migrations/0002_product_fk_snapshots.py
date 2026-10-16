"""P0-04 (S-07): chuyển nội dung route GET /api/shops/migrate cũ thành migration có số thứ tự.

Route cũ chạy ALTER TABLE không cần đăng nhập và hardcode tên schema. Ở đây:
- thêm cột snapshot tên sản phẩm/shop cho orderLines nếu thiếu, rồi backfill cho dòng cũ
- cartItems.productId -> ON DELETE CASCADE (xóa sản phẩm thì dọn khỏi giỏ)
- orderLines.productId cho phép NULL + ON DELETE SET NULL (xóa sản phẩm vẫn giữ lịch sử đơn nhờ snapshot)
Idempotent: chạy lại trên DB đã đúng không làm gì.
"""
from dbschema import add_column_if_missing, ensure_foreign_key, real_table_name


def upgrade(cursor):
    add_column_if_missing(cursor, 'orderLines', 'snapshotProductName', 'varchar(255)')
    add_column_if_missing(cursor, 'orderLines', 'snapshotShopName', 'varchar(255)')

    cursor.execute("""
        UPDATE orderLines ol
        JOIN products p ON ol.productId = p.id
        JOIN shops s ON p.shopId = s.id
        SET ol.snapshotProductName = p.name, ol.snapshotShopName = s.name
        WHERE ol.snapshotProductName IS NULL
    """)

    ensure_foreign_key(cursor, 'cartItems', 'productId', 'products', 'id', 'fk_cart_products', 'CASCADE')

    # productId phải NULL được trước khi đặt SET NULL (nếu đã NULL được thì MODIFY không đổi gì)
    cursor.execute(f"ALTER TABLE `{real_table_name(cursor, 'orderLines')}` MODIFY productId varchar(15) NULL")
    ensure_foreign_key(cursor, 'orderLines', 'productId', 'products', 'id', 'fk_orders_products', 'SET NULL')
