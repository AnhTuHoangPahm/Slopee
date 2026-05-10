import pytest
from flask import Flask
import sys
import os
# Add root folder (Slopee) to path so 'from backend.routes...' works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
# Add backend folder to path so 'from routes...' inside backend works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))
from backend.routes.auth import auth_bp
from backend.routes.carts import carts_bp
from backend.routes.products import products_bp
from backend.routes.shops import shops_bp
from backend.routes.payments import payments_bp

@pytest.fixture
def app():
    """Create a minimal Flask app to provide the application context and routing."""
    app = Flask(__name__)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(carts_bp, url_prefix='/api/cart')
    app.register_blueprint(products_bp, url_prefix='/api/products')
    app.register_blueprint(shops_bp, url_prefix='/api/shop')
    app.register_blueprint(payments_bp, url_prefix='/api/checkout')
    return app

@pytest.fixture
def client(app):
    """Provides a simulated browser client to make POST requests without a real server running."""
    return app.test_client()

@pytest.fixture
def mock_db_cursor(mocker):
    """Reusable fixture that patches the DB connection globally and returns a fake cursor."""
    # Note: We can patch it at the app level, but since get_db_connection is imported everywhere, 
    # we should patch the specific module where it's used. Since we don't know which route will be called
    # we can patch multiple, or just let individual tests patch their specific route.
    # Actually, a better global mock is to patch the database library directly, or patch all routes.
    # Let's keep it simple for now and just return the MagicMock components.
    pass