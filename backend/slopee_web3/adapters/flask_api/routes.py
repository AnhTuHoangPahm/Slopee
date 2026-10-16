"""API Web3 (SRS 7, SDD 10): ví, tạo đơn + báo giá, lô thanh toán. Lỗi luôn dạng {code, message} tiếng Việt.

Danh tính chỉ lấy từ token (g.user_id), không nhận userId từ body/URL. Chỉ role user/seller dùng được ví và đặt hàng:
admin và shipper không phải bên mua/bán (shipper có khóa relayer riêng ở phía máy chủ).
"""
import logging

from flask import Blueprint, g, jsonify
from werkzeug.exceptions import HTTPException

from auth_utils import require_auth
from errors import ApiError
from routes.auth import get_db_connection
from validation import json_body, get_str

from ...domain.errors import DomainError, http_status
from ...ports.chain_port import ChainUnavailable
from . import container as c

log = logging.getLogger('slopee.web3')

wallet_bp = Blueprint('w3_wallet', __name__)
orders_bp = Blueprint('w3_orders', __name__)
groups_bp = Blueprint('w3_groups', __name__)

BUYER_ROLES = ('user', 'seller')
MAX_CART_ITEMS = 100


def _err(code, message, status, extra=None):
    body = {'code': code, 'message': message}
    if extra:
        body.update(extra)
    resp = jsonify(body)
    resp.status_code = status
    return resp


def _on_domain_error(e):
    return _err(e.code, e.message, http_status(e.code), e.extra)


def _on_api_error(e):       # lỗi kiểm đầu vào của validation.py (P0-06) -> cùng dạng {code, message}
    return _err(e.code, e.message, e.status, e.extra)


def _on_chain_unavailable(e):
    log.warning('Chain unavailable: %s', e)
    return _err('CHAIN_UNAVAILABLE', 'Không kết nối được blockchain, hãy thử lại sau ít phút.', 503)


def _on_unexpected(e):
    if isinstance(e, HTTPException):
        return _err((e.name or 'error').lower().replace(' ', '_'), e.description or e.name, e.code or 500)
    log.error('Unhandled error in web3 API: %r', e, exc_info=True)      # chi tiết chỉ ở log (đã lọc dữ liệu nhạy cảm)
    return _err('internal_error', 'Đã có lỗi phía máy chủ, hãy thử lại sau.', 500)


for _bp in (wallet_bp, orders_bp, groups_bp):
    _bp.register_error_handler(DomainError, _on_domain_error)
    _bp.register_error_handler(ApiError, _on_api_error)
    _bp.register_error_handler(ChainUnavailable, _on_chain_unavailable)
    _bp.register_error_handler(Exception, _on_unexpected)


def _container():
    return c.get_container(lambda: get_db_connection())


# ------------------------------------------------------------------ UC-00
@wallet_bp.route('/nonce', methods=['POST'])
@require_auth(*BUYER_ROLES)
def wallet_nonce():
    data = json_body()
    # SDD 10.2 ghi "không có đầu vào", nhưng thông điệp SIWE phải chứa địa chỉ nên Frontend gửi địa chỉ MetaMask đang chọn.
    address = get_str(data, 'address', max_len=64, label='address')
    return jsonify(_container().wallet_service().issue_nonce(g.user_id, address)), 200


@wallet_bp.route('/link', methods=['POST'])
@require_auth(*BUYER_ROLES)
def wallet_link():
    data = json_body()
    address = get_str(data, 'address', max_len=64, label='address')
    signature = get_str(data, 'signature', max_len=200, label='signature')
    nonce = get_str(data, 'nonce', required=False, max_len=64, label='nonce')   # tùy chọn: bỏ qua thì dùng nonce mới nhất
    return jsonify(_container().wallet_service().link_wallet(g.user_id, address, signature, nonce)), 200


@wallet_bp.route('', methods=['GET'])
@require_auth(*BUYER_ROLES)
def wallet_get():
    return jsonify(_container().wallet_service().get_wallet(g.user_id)), 200


# ------------------------------------------------------------------ UC-01
def _cart_item_ids(data):
    raw = data.get('cart_item_ids')
    if not isinstance(raw, list) or not raw:
        raise DomainError('EMPTY_CART', 'Chưa chọn sản phẩm nào để thanh toán.')
    if len(raw) > MAX_CART_ITEMS:
        raise DomainError('INVALID_AMOUNT', f'Tối đa {MAX_CART_ITEMS} dòng sản phẩm mỗi lần thanh toán.')
    for v in raw:
        if not isinstance(v, str) or not v.strip() or len(v) > 36:
            raise DomainError('CART_ITEM_NOT_FOUND', 'Mã dòng giỏ hàng không hợp lệ.')
    return [v.strip() for v in raw]


@orders_bp.route('', methods=['POST'])
@require_auth(*BUYER_ROLES)
def create_order():
    ids = _cart_item_ids(json_body())
    return jsonify(_container().quote_service().create_checkout(g.user_id, ids)), 201


@orders_bp.route('/eligibility', methods=['POST'])
@require_auth(*BUYER_ROLES)
def web3_eligibility():
    """Chỉ đọc: các shop trong giỏ đã liên kết ví nhận tiền chưa (để Checkout ẩn/khóa lựa chọn Web3 thay vì để lỗi ở bước cuối)."""
    ids = _cart_item_ids(json_body())
    return jsonify(_container().quote_service().check_web3_eligibility(g.user_id, ids)), 200


@orders_bp.route('/<order_code>/status', methods=['GET'])
@require_auth(*BUYER_ROLES, 'admin')
def order_status(order_code):
    """Polling 2-3 giây (DD-04): trạng thái lấy từ MySQL do Indexer ghi, kèm server_time."""
    return jsonify(_container().order_status_service().get_status(g.user_id, g.role, order_code)), 200


@groups_bp.route('/<group_id>/quote', methods=['POST'])
@require_auth(*BUYER_ROLES)
def requote_group(group_id):
    return jsonify(_container().quote_service().reissue_group_quotes(g.user_id, group_id)), 200


@groups_bp.route('/<group_id>', methods=['GET'])
@require_auth(*BUYER_ROLES)
def get_group(group_id):
    return jsonify(_container().quote_service().get_group(g.user_id, group_id)), 200
