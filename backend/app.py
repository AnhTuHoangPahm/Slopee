import logging
import os

import click
from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

load_dotenv()  # đọc backend/.env (SECRET_KEY, DB_*, ...) trước khi nạp config

import config

# Initialize flask app
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

app = Flask(__name__)
app.config.from_object(config.Config)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024  # P0-06: body tối đa 1 MB

# P0-06: 404/405/500... luôn trả JSON chung; chi tiết lỗi chỉ ghi vào log máy chủ
from errors import register_app_errors
register_app_errors(app)

from json_provider import SlopeeJSONProvider
app.json = SlopeeJSONProvider(app)

# Register Blueprints
from routes.auth import auth_bp
from routes.shops import shops_bp
from routes.admin import admin_bp
from routes.products import products_bp
from routes.carts import carts_bp
from routes.payments import payments_bp
from routes.reviews import reviews_bp

app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(shops_bp, url_prefix='/api/shops')
app.register_blueprint(admin_bp, url_prefix='/api/admin')
app.register_blueprint(products_bp, url_prefix='/api/products')
app.register_blueprint(carts_bp, url_prefix='/api/carts')
app.register_blueprint(payments_bp, url_prefix='/api/payments')
app.register_blueprint(reviews_bp, url_prefix='/api/reviews')

# Enable CORS for the React frontend port (Vite running on localhost:5173)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:5173"}})

@app.cli.command('seed-admin')
@click.option('--username', prompt=True, help='Tên đăng nhập admin (> 3 ký tự).')
@click.option('--name', default='System Admin', show_default=True)
@click.option('--email', default=None, help='Mặc định: <username>@slopee.local')
@click.password_option(envvar='ADMIN_PASSWORD', help='Mật khẩu admin (>= 12 ký tự). Có thể truyền qua ADMIN_PASSWORD.')
def seed_admin_command(username, name, email, password):
    """Tạo tài khoản admin: flask --app app seed-admin"""
    from admin_seed import seed_admin
    from routes.auth import get_db_connection
    conn = get_db_connection()
    try:
        seed_admin(conn, username, password, name=name, email=email)
    except ValueError as e:
        raise click.ClickException(str(e))
    finally:
        conn.close()
    click.echo(f"Admin '{username}' created.")


@app.cli.command('migrate')
@click.argument('action', default='up', type=click.Choice(['up', 'status']))
def migrate_command(action):
    """Chạy migration CSDL: flask --app app migrate [up|status]  (P0-04, không có route HTTP)."""
    import migrate
    migrate.main([action])


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "Slopee Backend is running!"})

if __name__ == '__main__':
    # P0-06: debug chỉ bật khi SLOPEE_ENV=development (xem config.is_development); mặc định tắt
    app.run(debug=app.config['DEBUG'], port=5000)
