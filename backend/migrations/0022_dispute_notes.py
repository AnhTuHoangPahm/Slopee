"""Web3 tuần 5-6 (UC-05, SEQ-02): lý do và đường dẫn bằng chứng khiếu nại do Buyer gửi sau khi đơn `DISPUTED`.

SRS 7 / UC-05 yêu cầu "lưu ở sàn" nhưng lược đồ chưa có chỗ lưu (`dispute_resolutions.reason_note` là ghi chú thẩm định của ADMIN
cho đề xuất phán quyết, không phải lời của Buyer). Một đơn có đúng MỘT ghi chú (PK = order_id): Buyer gửi lại khi lỗi mạng thì ghi đè,
không tạo bản trùng; service chặn sửa sau khi Admin đã có đề xuất phán quyết. Khóa ngoại tới order_web3 lấy kiểu/charset từ
`order_web3.order_id` để không lỗi errno 150 (Q-06); xóa đơn thì ghi chú đi theo. Idempotent.
"""
from dbschema import column_like, require_innodb


def upgrade(cursor):
    require_innodb(cursor, 'order_web3')
    order_id = column_like(cursor, 'order_web3', 'order_id')
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS dispute_notes (
            order_id {order_id} NOT NULL PRIMARY KEY,
            buyer_user_id VARCHAR(36) NOT NULL COMMENT 'Buyer đã gửi (kiểm lúc ghi, lưu để truy vết)',
            reason TEXT NOT NULL,
            evidence_url VARCHAR(500) DEFAULT NULL COMMENT 'chỉ http/https',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT fk_dispute_note_order FOREIGN KEY (order_id) REFERENCES order_web3(order_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
