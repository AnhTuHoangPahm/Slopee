// Lỗi API Web3 + thông báo cho người dùng (SDD 9.5). Backend trả { code, message } tiếng Việt (SDD 10.2);
// bảng dưới là dự phòng khi thiếu `message` và để Frontend rẽ nhánh theo `code`, không theo nội dung chữ.
import { normalizeWalletError } from '../hooks/useWallet';

export const ERROR_MESSAGES = Object.freeze({
    WALLET_NOT_LINKED: 'Bạn cần liên kết ví trước khi thanh toán Web3.',
    WALLET_TAKEN: 'Ví này đã được liên kết với một tài khoản khác.',
    NONCE_INVALID: 'Mã xác thực đã hết hạn hoặc đã được dùng, hãy thử lại.',
    BAD_SIGNATURE: 'Chữ ký không hợp lệ hoặc không khớp với ví đã chọn.',
    INVALID_ADDRESS: 'Địa chỉ ví không hợp lệ.',
    RATE_LIMITED: 'Bạn thao tác quá nhanh, hãy thử lại sau ít phút.',
    QUOTE_EXPIRED: 'Báo giá đã hết hạn, hãy lấy báo giá mới.',
    INVALID_STATE: 'Đơn không còn ở trạng thái cho phép thao tác này.',
    BATCH_TOO_LARGE: 'Mỗi lần thanh toán tối đa 5 shop, hãy bỏ bớt sản phẩm.',
    EMPTY_CART: 'Chưa chọn sản phẩm nào để thanh toán.',
    CART_ITEM_NOT_FOUND: 'Có sản phẩm không còn trong giỏ hàng của bạn.',
    GROUP_NOT_FOUND: 'Không tìm thấy lô thanh toán.',
    PRODUCT_UNAVAILABLE: 'Có sản phẩm đã ngừng bán.',
    OUT_OF_STOCK: 'Có sản phẩm không đủ hàng.',
    SELF_PURCHASE: 'Bạn không thể mua sản phẩm của chính shop mình.',
    INVALID_AMOUNT: 'Số tiền quy đổi không hợp lệ.',
    PENDING_GROUP_EXISTS: 'Bạn đang có lô thanh toán chưa hoàn tất cho sản phẩm này.',
    POLICY_OUT_OF_RANGE: 'Chính sách thời hạn của nhóm hàng không hợp lệ, hãy báo quản trị viên.',
    POLICY_NOT_CONFIGURED: 'Chưa cấu hình chính sách nhóm hàng, hãy báo quản trị viên.',
    SETTING_INVALID: 'Cấu hình sàn chưa hợp lệ, hãy báo quản trị viên.',
    CHAIN_UNAVAILABLE: 'Không kết nối được blockchain, hãy thử lại sau ít phút.',
    WEB3_NOT_CONFIGURED: 'Tính năng thanh toán Web3 chưa được cấu hình trên máy chủ.',
    ACCOUNT_CHANGED: 'Bạn vừa đổi tài khoản trong ví, hãy thử lại.',
    NETWORK_ERROR: 'Không kết nối được máy chủ, hãy kiểm tra mạng và thử lại.',
    forbidden: 'Tài khoản của bạn không dùng được tính năng này.',
    internal_error: 'Đã có lỗi phía máy chủ, hãy thử lại sau.',
});

export class Web3ApiError extends Error {
    constructor({ code, message, status = 0, extra = {} }) {
        super(message || ERROR_MESSAGES[code] || 'Đã có lỗi, vui lòng thử lại.');
        this.name = 'Web3ApiError';
        this.code = code;
        this.status = status;
        this.extra = extra;
    }
}

/** Thông báo hiển thị cho người dùng từ MỌI loại lỗi: API, ví (4001 = hủy, không phải lỗi hệ thống), mạng. */
export function toUserMessage(err) {
    if (err instanceof Web3ApiError) return err.message;
    if (err?.code === 4001 || err?.code === 'ACTION_REJECTED' || err?.code === -32002) return normalizeWalletError(err).message;
    if (typeof err?.code === 'string' && ERROR_MESSAGES[err.code]) return ERROR_MESSAGES[err.code];
    return 'Đã có lỗi, vui lòng thử lại.';
}

/** Hủy trong ví là lựa chọn của người dùng: không hiện như lỗi (màu đỏ). */
export const isUserRejection = (err) => err?.code === 4001 || err?.code === 'ACTION_REJECTED';
