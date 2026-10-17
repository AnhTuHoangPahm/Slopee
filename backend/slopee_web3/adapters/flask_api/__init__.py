"""Adapter Flask của mô-đun Web3. `register_web3(app)` gắn các blueprint Web3; không làm hỏng app khi chưa cấu hình Web3."""
import logging

from ...ports.chain_port import ChainUnavailable
from . import container
from .routes import admin_w3_bp, disputes_bp, groups_bp, notifications_bp, orders_bp, shipper_bp, wallet_bp

log = logging.getLogger('slopee.web3')


def register_web3(app, *, eager=False):
    app.register_blueprint(wallet_bp, url_prefix='/api/wallet')
    app.register_blueprint(orders_bp, url_prefix='/api/orders')
    app.register_blueprint(groups_bp, url_prefix='/api/checkout-groups')
    app.register_blueprint(shipper_bp, url_prefix='/api/shipper')
    app.register_blueprint(admin_w3_bp, url_prefix='/api/admin')
    app.register_blueprint(notifications_bp, url_prefix='/api/notifications')
    app.register_blueprint(disputes_bp, url_prefix='/api/disputes')
    if not eager:
        return
    # Dựng sớm để khóa vai trò sai/ABI lệch làm DỪNG khởi động (SDD 5.6); Anvil chưa chạy chỉ cảnh báo, dựng lười sau.
    from routes.auth import get_db_connection
    try:
        container.get_container(lambda: get_db_connection())
        log.info('Web3 đã sẵn sàng (khóa vai trò khớp contract).')
    except ChainUnavailable as e:
        log.warning('Chưa kết nối được Anvil (%s); API Web3 sẽ thử lại khi có yêu cầu.', e)
    except Exception as e:
        from ...domain.errors import DomainError
        if isinstance(e, DomainError) and e.code == 'WEB3_NOT_CONFIGURED':
            log.info('Chưa cấu hình Web3 (thiếu backend/.env.web3): chỉ chạy Slopee cũ. Chạy scripts/bootstrap.sh.')
        else:
            raise
