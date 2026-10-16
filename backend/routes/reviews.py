from flask import Blueprint, jsonify, g
import uuid
from routes.auth import get_db_connection
from auth_utils import require_auth
from errors import register_blueprint_errors
from validation import json_body, get_int, get_str, get_url_list

reviews_bp = Blueprint('reviews', __name__)
register_blueprint_errors(reviews_bp)

MAX_COMMENT_LEN = 5000
MAX_REVIEW_IMAGES = 5


@reviews_bp.route('/<product_id>', methods=['POST'])
@require_auth
def add_review(product_id):
    data = json_body()
    user_id = g.user_id
    try:
        rating = get_int(data, 'rating', default=0, label='rating')
    except Exception:
        rating = 0
    comment = data.get('comment', '')
    if not isinstance(comment, str):
        comment = ''
    images = get_url_list(data, 'images', max_items=MAX_REVIEW_IMAGES, label='images')

    if not (1 <= rating <= 5) or not comment.strip():
        return jsonify({"error": "A 1-5 rating, and a written comment are required."}), 400
    comment = comment.strip()[:MAX_COMMENT_LEN]

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # High-Security Validation: Has this user actually bought and received this exact product?
            cursor.execute("""
                SELECT o.status 
                FROM orders o
                JOIN orderLines ol ON o.id = ol.orderId
                WHERE o.userId = %s AND ol.productId = %s
                LIMIT 1
            """, (user_id, product_id))
            validation = cursor.fetchone()
            
            # The architecture requires receipt of goods (received) or at least paid/shipped to validate integrity
            if not validation or validation['status'] not in ['paid', 'shipped', 'received']:
                return jsonify({"error": "Unauthorized. You must have successfully purchased this product to review it."}), 403
            
            # Check for duplicate reviews by the same user
            cursor.execute("SELECT id FROM reviews WHERE userId=%s AND productId=%s", (user_id, product_id))
            if cursor.fetchone():
                return jsonify({"error": "You have already left a review for this product."}), 409
                
            # Synthesize Review Block
            review_id = str(uuid.uuid4())[:15]
            cursor.execute("""
                INSERT INTO reviews (id, userId, productId, rating, comment)
                VALUES (%s, %s, %s, %s, %s)
            """, (review_id, user_id, product_id, rating, comment))
            
            # P0-04 (S-13): reviewImages.id là VARCHAR(36) không tự sinh -> backend phải cấp UUID
            # (trước đây INSERT thiếu id gây lỗi 1364 ở strict mode)
            for img_url in images:
                cursor.execute("INSERT INTO reviewImages (id, reviewId, imageUrl) VALUES (%s, %s, %s)",
                               (str(uuid.uuid4()), review_id, img_url))
                    
            conn.commit()
            return jsonify({"message": "Review perfectly published!", "reviewId": review_id}), 201
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
