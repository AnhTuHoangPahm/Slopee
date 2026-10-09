import pymysql
import os
import uuid
import hashlib
from dotenv import load_dotenv

# load .env file inside /backend
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)

def create_connection():
    # Attempt to use standard local development credentials, or read from env.
    host = os.environ.get('DB_HOST', 'localhost')
    port = int(os.environ.get('DB_PORT', 3306))
    user = os.environ.get('DB_USER', 'root')
    password = os.environ.get('DB_PASSWORD', '') # Default no password
    
    # Connect without a db initially to create it if it doesn't exist.
    conn = pymysql.connect(
        host=host,
        port=port,
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
            with open(schema_path, 'r', encoding='utf8') as f:
                sql_script = f.read()
            
            # Split schema statements
            statements = [stmt.strip() for stmt in sql_script.split(';') if stmt.strip()]
            for stmt in statements:
                if stmt:
                    cursor.execute(stmt)
            print("Schema loaded successfully.")
            
            # 1. Provide Admin Credentials: (Shadowed,admin,admin,0,0)
            admin_username = "admin"
            admin_password = "admin"
            
            cursor.execute("SELECT id FROM users WHERE email='0'")
            admin_exists = cursor.fetchone()
            
            if not admin_exists:
                admin_id = str(uuid.uuid4())
                
                cursor.execute(
                    "INSERT INTO users (id, role, name, email, phone, bio) VALUES (%s, %s, %s, %s, %s, %s)",
                    (admin_id, 'admin', 'Shadowed', '0', '0', '')
                )
                
                salt = os.urandom(16).hex()
                try:
                    from werkzeug.security import generate_password_hash
                    # Werkzeug includes the salt within the hash string natively
                    password_hash = generate_password_hash(admin_password)
                    salt = 'werkzeug-managed' 
                except ImportError:
                    password_hash = hashlib.sha256((admin_password + salt).encode()).hexdigest()
                    
                cursor.execute(
                    "INSERT INTO credentials (userId, username, passwordHash, passwordSalt, passPhraseHash) VALUES (%s, %s, %s, %s, %s)",
                    (admin_id, admin_username, password_hash, salt, None)
                )
                print("Admin user (admin:admin) created successfully.")
            else:
                print("Admin user already exists in DB. (admin:admin)")
                
        conn.commit()
        print("Database Initialization completely successful!")
    finally:
        conn.close()

if __name__ == "__main__":
    init_database()
