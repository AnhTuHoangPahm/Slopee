"""Hàm tiện ích introspection information_schema cho migration dạng Python (P0-04).

Không hardcode tên schema: luôn dùng DATABASE() của kết nối hiện tại (S-07 từng hardcode tên schema).
Mọi hàm nhận `cursor` (DictCursor) và đều idempotent để migration chạy lại an toàn.
"""


def real_table_name(cursor, table):
    """Tên bảng đúng chữ hoa/thường như đã lưu (MySQL trên Linux phân biệt, Windows thì không). None nếu chưa có."""
    cursor.execute("SELECT TABLE_NAME AS name FROM information_schema.TABLES "
                   "WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = LOWER(%s)", (table,))
    row = cursor.fetchone()
    return row['name'] if row else None


def column_exists(cursor, table, column):
    cursor.execute("SELECT 1 AS x FROM information_schema.COLUMNS "
                   "WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = LOWER(%s) AND COLUMN_NAME = %s",
                   (table, column))
    return cursor.fetchone() is not None


def add_column_if_missing(cursor, table, column, definition):
    if not column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE `{real_table_name(cursor, table)}` ADD COLUMN `{column}` {definition}")
        return True
    return False


def index_exists(cursor, table, index_name):
    cursor.execute("SELECT 1 AS x FROM information_schema.STATISTICS "
                   "WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = LOWER(%s) AND INDEX_NAME = %s LIMIT 1",
                   (table, index_name))
    return cursor.fetchone() is not None


def foreign_keys(cursor, table, column, referenced_table):
    """Danh sách khóa ngoại của table.column trỏ tới referenced_table: [{'name', 'delete_rule'}]."""
    cursor.execute("""
        SELECT k.CONSTRAINT_NAME AS name, r.DELETE_RULE AS delete_rule
        FROM information_schema.KEY_COLUMN_USAGE k
        JOIN information_schema.REFERENTIAL_CONSTRAINTS r
          ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
         AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
         AND r.TABLE_NAME = k.TABLE_NAME
        WHERE k.TABLE_SCHEMA = DATABASE()
          AND LOWER(k.TABLE_NAME) = LOWER(%s)
          AND k.COLUMN_NAME = %s
          AND LOWER(k.REFERENCED_TABLE_NAME) = LOWER(%s)
    """, (table, column, referenced_table))
    return list(cursor.fetchall())


def ensure_foreign_key(cursor, table, column, referenced_table, referenced_column, new_name, on_delete):
    """Đảm bảo table.column có đúng MỘT khóa ngoại với ON DELETE = on_delete.
    Đã đúng thì không làm gì; sai thì xóa khóa cũ (tên bất kỳ) rồi tạo lại."""
    on_delete = on_delete.upper()
    fks = foreign_keys(cursor, table, column, referenced_table)
    if len(fks) == 1 and (fks[0]['delete_rule'] or '').upper() == on_delete:
        return False
    real = real_table_name(cursor, table)
    for fk in fks:
        cursor.execute(f"ALTER TABLE `{real}` DROP FOREIGN KEY `{fk['name']}`")
    cursor.execute(f"ALTER TABLE `{real}` ADD CONSTRAINT `{new_name}` FOREIGN KEY (`{column}`) "
                   f"REFERENCES `{referenced_table}` (`{referenced_column}`) ON DELETE {on_delete}")
    return True
