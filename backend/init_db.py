import pymysql
import os

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
            
            # Run schema.sql from the identical directory
            schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
            with open(schema_path, 'r') as f:
                sql_script = f.read()
            
            # Split schema statements
            statements = [stmt.strip() for stmt in sql_script.split(';') if stmt.strip()]
            for stmt in statements:
                if stmt:
                    cursor.execute(stmt)
            print("Schema loaded successfully.")
            
            # P0-02: không còn tạo sẵn tài khoản admin/admin.
            # Tạo admin bằng CLI:  flask --app app seed-admin
            print("Tip: create the admin account with: flask --app app seed-admin")
                
        conn.commit()
        print("Database Initialization completely successful!")
    finally:
        conn.close()

if __name__ == "__main__":
    init_database()
