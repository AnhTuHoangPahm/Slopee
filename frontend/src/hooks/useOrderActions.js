// Hai thao tác ví của Buyer trên MỘT đơn: "Đã nhận hàng" (earlyRelease) và "Khiếu nại" (raiseDispute). Mỗi đơn dùng một instance
// riêng nên thao tác trên đơn của shop này không đổi trạng thái đơn của shop khác (BR-11, SDD 9.3).
import { useCallback, useEffect, useReducer, useRef } from 'react';
import { Contract } from 'ethers';
import escrowAbi from '../lib/abi/SlopeeEscrowMaster.json';
import { ACTION_STEP, initialActionState, isActionBusy, mapOrderActionError, orderActionReducer, runOrderAction } from '../lib/orderActions';
import { useWallet } from './useWallet';

/** Dựng hợp đồng escrow gắn signer của ví đang kết nối. Tách riêng để test thay thế được. */
export async function makeEscrow({ getSigner, deployment }) {
    const signer = await getSigner();
    return new Contract(deployment.escrow, escrowAbi, signer);
}

/**
 * @param {object} [opts]
 * @param {Function} [opts.escrowFactory]  thay cho makeEscrow (chỉ dùng khi test)
 * @returns {{ state, run(kind, onchainOrderId), markIndexed(), reset(), busy }}
 */
export function useOrderActions({ escrowFactory = makeEscrow } = {}) {
    const w = useWallet();
    const [state, dispatch] = useReducer(orderActionReducer, undefined, initialActionState);
    const running = useRef(false); // chặn bấm dồn: mỗi lần chỉ MỘT luồng ví cho đơn này
    const busy = isActionBusy(state);

    // Cảnh báo khi đóng/tải lại tab giữa chừng (giao dịch có thể đã gửi mà giao diện chưa kịp ghi nhận)
    useEffect(() => {
        if (!busy) return undefined;
        const onBeforeUnload = (e) => { e.preventDefault(); e.returnValue = ''; };
        window.addEventListener('beforeunload', onBeforeUnload);
        return () => window.removeEventListener('beforeunload', onBeforeUnload);
    }, [busy]);

    const run = useCallback(async (kind, onchainOrderId) => {
        if (running.current) return null;
        running.current = true;
        try {
            let escrow;
            try {
                escrow = await escrowFactory({ getSigner: w.getSigner, deployment: w.deployment });
            } catch (e) { // không lấy được signer/hợp đồng: phải hiện lỗi, không được im lặng
                dispatch({ type: 'START', kind });
                const mapped = mapOrderActionError(e);
                dispatch({ type: 'FAIL', error: mapped.userRejected ? mapped : { code: 'WALLET_UNAVAILABLE', message: 'Không kết nối được ví. Hãy kết nối lại MetaMask rồi thử lại.', userRejected: false } });
                return null;
            }
            return await runOrderAction({ kind, onchainOrderId, escrow, dispatch });
        } catch {
            return null; // runOrderAction đã phát FAIL cho mọi lỗi của luồng
        } finally {
            running.current = false;
        }
    }, [w.getSigner, w.deployment, escrowFactory]);

    const markIndexed = useCallback(() => dispatch({ type: 'INDEXED' }), []);
    const reset = useCallback(() => dispatch({ type: 'RESET' }), []);
    return { state, run, markIndexed, reset, busy, failed: state.step === ACTION_STEP.FAILED };
}
