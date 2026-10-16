import pymysql
import os

import migrate

def create_connection():
    # Attempt to use standard local development credentials, or read from env.
    host = os.environ.get('DB_HOST', 'localhost')
    user = os.environ.get('DB_USER', 'root')
    password = os.environ.get('DB_PASSWORD', '') # Default no password
    
    # Connect without a db initially to create it if it doesn't exist.
    conn = pymysql.connect(
        host=host,
        user=user,
        password=password,
        cursorclass=pymysql.cursors.DictCursor
    )
    return conn

def init_database():
    db_name = os.environ.get('DB_NAME', 'slopee_db')
    print(f"Connecting to MySQL to initialize database: {db_name}")
    try:
        conn = create_connection()
    except pymysql.err.OperationalError as e:
        print(f"Could not connect to MySQL: {e}")
        print("Please ensure your MySQL server is running on localhost with user 'root' and no password (or configure DB_PASSWORD via env).")
        return

    try:
        with conn.cursor() as cursor:
            # Create DB
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
            cursor.execute(f"USE {db_name}")
            print(f"Database '{db_name}' created/selected.")

            # DB đã có bảng users từ trước = DB cũ: schema.sql (IF NOT EXISTS) không nâng cấp được nó
            cursor.execute("SELECT COUNT(*) AS c FROM information_schema.TABLES "
                           "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users'", (db_name,))
            is_fresh = cursor.fetchone()['c'] == 0
            
            # Run schema.sql from the identical directory
            schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
            with open(schema_path, 'r', encoding='utf-8') as f:
                sql_script = f.read()
            
            # P0-04: bộ tách an toàn (bỏ chú thích, không cắt nhầm dấu ; trong chuỗi)
            for stmt in migrate.split_sql(sql_script):
                cursor.execute(stmt)
            print("Schema loaded successfully.")
            
            # P0-02: không còn tạo sẵn tài khoản admin/admin.
            # Tạo admin bằng CLI:  flask --app app seed-admin
            print("Tip: create the admin account with: flask --app app seed-admin")
                
        conn.commit()

        # schema.sql đã là schema mới nhất nên các migration hiện có được đánh dấu là đã áp dụng (không chạy lại).
        # DB cũ tạo trước đây thì chạy:  python migrate.py
        if is_fresh:
            conn.select_db(db_name)
            marked = migrate.mark_applied(conn)
            print(f"Marked {len(marked)} migration(s) as applied (schema.sql is up to date).")
        else:
            print("Existing database detected: run `python migrate.py` to apply pending migrations.")
        print("Database Initialization completely successful!")
    finally:
        conn.close()

if __name__ == "__main__":
    init_database()
