import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from routes.auth import get_db_connection

conn = get_db_connection()
try:
    with conn.cursor() as cursor:
        try:
            cursor.execute("""
                ALTER TABLE users ADD COLUMN deletionRequestedAt timestamp NULL DEFAULT NULL;
            """)
            conn.commit()
            print("Successfully added deletionRequestedAt column.")
        except Exception as alt_err:
            print("Column might already exist or error:", alt_err)
        print("Feature H Schema Extrapolation Subroutine Executed.")
except Exception as e:
    print("Schema Exception:", e)
finally:
    conn.close()
