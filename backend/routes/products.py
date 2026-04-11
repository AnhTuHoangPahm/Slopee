from flask import Blueprint, request, jsonify
from routes.auth import get_db_connection
import time
import json

products_bp = Blueprint('products', __name__)

@products_bp.route('/categories', methods=['GET'])
def get_categories():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM categories ORDER BY name ASC")
            categories = cursor.fetchall()
            return jsonify({"categories": categories}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@products_bp.route('/', methods=['GET'])
def search_products():
    search_query = request.args.get('search', '')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            start_time = time.time()
            if search_query:
                query = "SELECT p.*, s.name as shopName FROM products p JOIN shops s ON p.shopId = s.id WHERE p.isActive = TRUE AND (p.name LIKE %s OR s.name LIKE %s) ORDER BY p.name ASC"
                cursor.execute(query, ('%' + search_query + '%', '%' + search_query + '%'))
            else:
                cursor.execute("SELECT p.*, s.name as shopName FROM products p JOIN shops s ON p.shopId = s.id WHERE p.isActive = TRUE ORDER BY p.name ASC")
            
            items = cursor.fetchall()
            
            for item in items:
                cursor.execute("SELECT imageUrl FROM productImages WHERE productId=%s AND isPrimary=TRUE LIMIT 1", (item['id'],))
                img = cursor.fetchone()
                item['primaryImage'] = img['imageUrl'] if img else None
                
                cursor.execute("SELECT id, variantName, variantValue FROM productVariants WHERE productId=%s", (item['id'],))
                item['variants'] = cursor.fetchall()
                
                cursor.execute("SELECT AVG(rating) as avg_rating FROM reviews WHERE productId=%s", (item['id'],))
                avg_res = cursor.fetchone()
                item['averageRating'] = round(float(avg_res['avg_rating']), 1) if avg_res and avg_res['avg_rating'] else 0.0
                
            elapsed_time = time.time() - start_time
            
            return jsonify({
                "time_taken_sec": round(elapsed_time, 4),
                "items": items
            }), 200
    finally:
        conn.close()

# --- FEATURE G: PRODUCT VIEWS & REVIEWS AGGREGATORS ---

@products_bp.route('/<product_id>', methods=['GET'])
def get_product_details(product_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT 
                    p.*,
                    c.name as categoryName,
                    s.name as shopName, s.avatarUrl as shopAvatarUrl,
                    (SELECT JSON_ARRAYAGG(JSON_OBJECT('id', img.id, 'imageUrl', img.imageUrl, 'isPrimary', img.isPrimary)) 
                     FROM productImages img WHERE img.productId = p.id) AS images,
                    (SELECT JSON_ARRAYAGG(JSON_OBJECT('id', var.id, 'variantName', var.variantName, 'variantValue', var.variantValue)) 
                     FROM productVariants var WHERE var.productId = p.id) AS variants
                FROM products p
                JOIN shops s ON p.shopId = s.id
                JOIN categories c ON p.categoryId = c.id
                WHERE p.id = %s AND p.isActive = TRUE
            """
            cursor.execute(query, (product_id,))
            prod = cursor.fetchone()
            
            if not prod:
                return jsonify({"error": "Product not found or unavailable."}), 404
                
            # Safely parse PyMySQL JSON_ARRAYAGG text output logically back into Lists
            if prod.get('images'):
                prod['images'] = json.loads(prod['images'])
            else:
                prod['images'] = []
                
            if prod.get('variants'):
                prod['variants'] = json.loads(prod['variants'])
            else:
                prod['variants'] = []
            
            return jsonify({"product": prod}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@products_bp.route('/<product_id>/reviews', methods=['GET'])
def get_product_reviews(product_id):
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 5))
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.id, r.rating, r.comment, r.createdAt, u.name as userName,
                    (SELECT JSON_ARRAYAGG(JSON_OBJECT('url', ri.imageUrl)) FROM reviewImages ri WHERE ri.reviewId = r.id) as reviewImages
                FROM reviews r
                JOIN users u ON r.userId = u.id
                WHERE r.productId = %s
                ORDER BY r.createdAt DESC
                LIMIT %s OFFSET %s
            """, (product_id, limit, offset))
            reviews = cursor.fetchall()
            
            for r in reviews:
                if r.get('reviewImages'):
                    r['reviewImages'] = json.loads(r['reviewImages'])
                else:
                    r['reviewImages'] = []
            
            cursor.execute("SELECT AVG(rating) as avgRating, COUNT(id) as totalReviews FROM reviews WHERE productId=%s", (product_id,))
            stats = cursor.fetchone()
            
            return jsonify({
                "reviews": reviews,
                "stats": {
                    "average": float(stats['avgRating']) if stats['avgRating'] else 0,
                    "total": stats['totalReviews']
                }
            }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
