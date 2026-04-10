from flask import Blueprint, request, jsonify
import pymysql
import os
import time

products_bp = Blueprint('products', __name__)

def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'slopee_db'),
        cursorclass=pymysql.cursors.DictCursor
    )

@products_bp.route('/', methods=['GET'])
def get_products():
    search_query = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # We track elapsed time to prove we meet the < 0.5s SLA
            start_time = time.time()
            if search_query:
                # Parameterized LIKE query. Usually DB indexes handles this rapidly.
                query = "SELECT p.*, s.name as shopName FROM products p JOIN shops s ON p.shopId = s.id WHERE p.isActive = TRUE AND p.name LIKE %s ORDER BY p.name ASC"
                cursor.execute(query, ('%' + search_query + '%',))
            else:
                cursor.execute("SELECT p.*, s.name as shopName FROM products p JOIN shops s ON p.shopId = s.id WHERE p.isActive = TRUE ORDER BY p.name ASC")
            
            items = cursor.fetchall()
            elapsed_time = time.time() - start_time
            
            return jsonify({
                "time_taken_sec": round(elapsed_time, 4),
                "items": items
            }), 200
    finally:
        conn.close()
