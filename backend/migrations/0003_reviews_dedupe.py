"""P0-04 (S-13): đưa DB cũ về khai báo reviews/reviewImages đã gộp.

schema.sql từng khai báo hai lần, bản ĐẦU thắng nhờ IF NOT EXISTS nên DB cũ thiếu UNIQUE(userId, productId),
comment cho phép NULL và FK userId là RESTRICT (admin xóa người dùng đã có đánh giá thì lỗi).
reviewImages giữ id VARCHAR(36): backend sinh UUID (reviews.py), không cần đổi cấu trúc bảng.
Idempotent.
"""
from dbschema import ensure_foreign_key, index_exists


def upgrade(cursor):
    cursor.execute("UPDATE reviews SET comment = '' WHERE comment IS NULL")
    cursor.execute("ALTER TABLE reviews MODIFY comment text NOT NULL")

    # Mỗi (userId, productId) chỉ giữ đánh giá mới nhất trước khi thêm ràng buộc UNIQUE
    cursor.execute("""
        DELETE r1 FROM reviews r1
        JOIN reviews r2
          ON r1.userId = r2.userId AND r1.productId = r2.productId
         AND (r1.createdAt < r2.createdAt OR (r1.createdAt = r2.createdAt AND r1.id < r2.id))
    """)
    if not index_exists(cursor, 'reviews', 'uniqueReview'):
        cursor.execute("ALTER TABLE reviews ADD CONSTRAINT uniqueReview UNIQUE (userId, productId)")

    ensure_foreign_key(cursor, 'reviews', 'userId', 'users', 'id', 'fk_reviews_user', 'CASCADE')
