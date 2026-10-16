// Luồng liên kết ví UC-00 (SRS UC-00): lấy nonce -> ký personal_sign -> gửi chữ ký. Tách khỏi giao diện để test được.
import { sameAddress } from './chain';

export const LINK_STEP = Object.freeze({
    IDLE: 'idle',
    REQUESTING_NONCE: 'requesting_nonce',
    AWAITING_SIGNATURE: 'awaiting_signature', // đang chờ người dùng bấm "Ký" trong ví
    LINKING: 'linking',
    DONE: 'done',
});

/**
 * Chạy trọn luồng. `api` = { requestWalletNonceAPI, linkWalletAPI }; `signer` = ethers Signer (signMessage).
 * `onStep(step)` để giao diện hiển thị tiến trình. Thông điệp ký là NGUYÊN VĂN do Backend trả (không tự dựng lại).
 * Ném lại lỗi gốc (Web3ApiError hoặc lỗi ví) để giao diện dịch ra thông báo.
 */
export async function runLinkFlow({ address, signer, api, onStep = () => {} }) {
    onStep(LINK_STEP.REQUESTING_NONCE);
    const { nonce, message } = await api.requestWalletNonceAPI(address);

    onStep(LINK_STEP.AWAITING_SIGNATURE);
    const signature = await signer.signMessage(message);
    const signerAddress = await signer.getAddress?.();
    if (signerAddress && !sameAddress(signerAddress, address)) {
        // Người dùng đổi tài khoản trong ví giữa chừng: chữ ký sẽ không khớp địa chỉ đã gửi, báo sớm thay vì gọi API
        const err = new Error('account changed');
        err.code = 'ACCOUNT_CHANGED';
        throw err;
    }

    onStep(LINK_STEP.LINKING);
    const result = await api.linkWalletAPI({ address, signature, nonce });
    onStep(LINK_STEP.DONE);
    return result;
}

/** Trạng thái liên kết để giao diện rẽ nhánh. linked = dữ liệu từ GET /api/wallet; account = địa chỉ ví đang kết nối. */
export function linkState({ linked, account }) {
    if (!account) return 'NO_ACCOUNT';
    if (!linked?.linked) return 'NOT_LINKED';
    return sameAddress(linked.address, account) ? 'LINKED_THIS' : 'LINKED_OTHER';
}
