"""Guard dùng chung cho kiểm quyền / trạng thái (P0-03)."""
import pymysql

ER_NO_SUCH_TABLE = 1146


def is_web3_order(cursor, order_id):
    """True nếu đơn đã có dòng trong order_web3 (SRS 5.1: Web3 là nguồn sự thật trạng thái của đơn đó).

    Trước khi migration Web3 (bảng order_web3) được áp dụng thì chưa có đơn Web3 nào, nên bảng
    chưa tồn tại (lỗi 1146) được hiểu là False thay vì làm hỏng toàn bộ route đơn hàng cũ.
    """
    try:
        cursor.execute("SELECT 1 FROM order_web3 WHERE order_id=%s LIMIT 1", (order_id,))
    except pymysql.err.ProgrammingError as e:
        if e.args and e.args[0] == ER_NO_SUCH_TABLE:
            return False
        raise
    return cursor.fetchone() is not None
