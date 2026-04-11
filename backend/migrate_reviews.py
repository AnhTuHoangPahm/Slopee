import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from routes.auth import get_db_connection

conn = get_db_connection()
try:
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id varchar(36) PRIMARY KEY,
                userId varchar(36) NOT NULL,
                productId varchar(15) NOT NULL,
                rating int NOT NULL check (rating >= 1 AND rating <= 5),
                comment text NOT NULL,
                createdAt timestamp NOT NULL DEFAULT current_timestamp,
                FOREIGN KEY (userId) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (productId) REFERENCES products(id) ON DELETE CASCADE,
                CONSTRAINT uniqueReview UNIQUE(userId, productId)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviewImages (
                id int auto_increment PRIMARY KEY,
                reviewId varchar(36) NOT NULL,
                imageUrl varchar(500) NOT NULL,
                FOREIGN KEY (reviewId) REFERENCES reviews(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        print("Review tables successfully synthesized.")
finally:
    conn.close()
