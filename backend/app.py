import logging
import os

import click
from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

load_dotenv()  # đọc backend/.env (SECRET_KEY, DB_*, ...) trước khi nạp config
# Web3 (RPC_URL, ESCROW_ADDRESS, khóa vai trò...) do scripts/bootstrap.sh sinh; không ghi đè biến đã đặt sẵn
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env.web3'))

import config

# Initialize flask app
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
from slopee_web3.adapters.logging_filter import install as install_log_redaction
install_log_redaction()  # SDD 5.6: che signature/private/key/mnemonic trong log

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

# Web3 Escrow (Tuần 3): /api/wallet, /api/orders, /api/checkout-groups
from slopee_web3.adapters.flask_api import register_web3
register_web3(app, eager=not os.environ.get('SLOPEE_SKIP_WEB3_BOOT'))

# CORS cho frontend Vite. Truy cập từ LAN/VPN đi qua proxy /api của Vite (cùng origin) nên KHÔNG cần mở rộng CORS.
# Chỉ khi gọi API trực tiếp từ origin khác mới đặt CORS_ORIGINS="https://host:5173,http://100.x.x.x:5173" (phân tách bằng dấu phẩy).
_DEFAULT_CORS = ['http://localhost:5173', 'http://127.0.0.1:5173', 'https://localhost:5173', 'https://127.0.0.1:5173']
_cors_origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip()] or _DEFAULT_CORS
CORS(app, resources={r"/api/*": {"origins": _cors_origins}})

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


@app.cli.command('seed-shipper')
@click.option('--username', prompt=True, help='Tên đăng nhập Shipper (> 3 ký tự).')
@click.option('--name', default='Shipper', show_default=True)
@click.password_option(envvar='SHIPPER_PASSWORD', help='Mật khẩu (>= 12 ký tự). Có thể truyền qua SHIPPER_PASSWORD.')
def seed_shipper_command(username, name, password):
    """Tạo tài khoản Shipper: flask --app app seed-shipper (gán đơn: PUT /api/admin/orders/<code>/shipper)."""
    from shipper_seed import seed_shipper
    from routes.auth import get_db_connection
    conn = get_db_connection()
    try:
        user_id = seed_shipper(conn, username, password, name=name)
    except ValueError as e:
        raise click.ClickException(str(e))
    finally:
        conn.close()
    click.echo(f"Shipper '{username}' created (id {user_id}).")


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
    # FLASK_HOST=0.0.0.0 để thiết bị khác trong LAN/VPN truy cập được. Mặc định chỉ loopback.
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    debug = app.config['DEBUG']
    if debug and host not in ('127.0.0.1', 'localhost'):
        # Trình debug Werkzeug cho phép chạy code từ xa -> không để lộ ra mạng ngoài loopback.
        logging.getLogger(__name__).warning('FLASK_HOST=%s: tắt debug để tránh lộ Werkzeug debugger ra mạng.', host)
        debug = False
    app.run(debug=debug, host=host, port=5000)
