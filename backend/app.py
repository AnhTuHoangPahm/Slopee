from flask import Flask, jsonify
from flask_cors import CORS
import config

# Initialize flask app
app = Flask(__name__)
app.config.from_object(config.Config)

# Register Blueprints
from routes.auth import auth_bp
from routes.shops import shops_bp
from routes.admin import admin_bp
from routes.products import products_bp
from routes.carts import carts_bp
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(shops_bp, url_prefix='/api/shops')
app.register_blueprint(admin_bp, url_prefix='/api/admin')
app.register_blueprint(products_bp, url_prefix='/api/products')
app.register_blueprint(carts_bp, url_prefix='/api/carts')

# Enable CORS for the React frontend port (Vite running on localhost:5173)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:5173"}})

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "Slopee Backend is running!"})

if __name__ == '__main__':
    # Run the server in debug mode at port 5000
    app.run(debug=True, port=5000)
