from flask import Blueprint, request, jsonify, g
import uuid
from routes.auth import get_db_connection
from auth_utils import require_auth

reviews_bp = Blueprint('reviews', __name__)

@reviews_bp.route('/<product_id>', methods=['POST'])
@require_auth
def add_review(product_id):
    data = request.get_json(silent=True) or {}
    user_id = g.user_id
    try:
        rating = int(data.get('rating', 0))
    except (TypeError, ValueError):
        rating = 0
    comment = data.get('comment', '')
    images = data.get('images', [])
    
    if not (1 <= rating <= 5) or not comment.strip():
        return jsonify({"error": "A 1-5 rating, and a written comment are required."}), 400
        
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
            
            # Synthesize Associated Imagery
            for imgUrl in images:
                if imgUrl:
                    cursor.execute("INSERT INTO reviewImages (reviewId, imageUrl) VALUES (%s, %s)", (review_id, imgUrl))
                    
            conn.commit()
            return jsonify({"message": "Review perfectly published!", "reviewId": review_id}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
