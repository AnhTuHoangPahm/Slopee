// Thao tác ví "Rút về ví" (claimPending) của Merchant. Mỗi lần chỉ MỘT luồng ví (nút khóa khi đang chạy).
import { useCallback, useEffect, useReducer, useRef } from 'react';
import { CLAIM_STEP, ETH_ADDRESS, claimReducer, initialClaimState, isClaimBusy, mapClaimError, runClaimPending } from '../lib/claimPending';
import { makeEscrow } from './useOrderActions';
import { useWallet } from './useWallet';

export { ETH_ADDRESS };

/**
 * @param {object} [opts]
 * @param {Function} [opts.escrowFactory]  thay cho makeEscrow (chỉ dùng khi test)
 * @returns {{ state, run(token, address), markIndexed(), reset(), busy }}
 */
export function useClaimPending({ escrowFactory = makeEscrow } = {}) {
    const w = useWallet();
    const [state, dispatch] = useReducer(claimReducer, undefined, initialClaimState);
    const running = useRef(false);        // cờ đồng bộ: bấm đúp không mở hai luồng ví
    const busy = isClaimBusy(state);

    // Cảnh báo khi đóng/tải lại tab giữa chừng (giao dịch có thể đã gửi mà giao diện chưa kịp ghi nhận)
    useEffect(() => {
        if (!busy) return undefined;
        const onBeforeUnload = (e) => { e.preventDefault(); e.returnValue = ''; };
        window.addEventListener('beforeunload', onBeforeUnload);
        return () => window.removeEventListener('beforeunload', onBeforeUnload);
    }, [busy]);

    const run = useCallback(async (token, address) => {
        if (running.current) return null;
        running.current = true;
        try {
            let escrow;
            try {
                escrow = await escrowFactory({ getSigner: w.getSigner, deployment: w.deployment });
            } catch (e) { // không lấy được signer/hợp đồng: phải hiện lỗi, không được im lặng
                dispatch({ type: 'START', token, address });
                const mapped = mapClaimError(e);
                dispatch({ type: 'FAIL', error: mapped.userRejected ? mapped : { code: 'WALLET_UNAVAILABLE', message: 'Không kết nối được ví. Hãy kết nối lại MetaMask rồi thử lại.', userRejected: false } });
                return null;
            }
            return await runClaimPending({ token, address, escrow, dispatch });
        } catch {
            return null; // runClaimPending đã phát FAIL cho mọi lỗi của luồng
        } finally {
            running.current = false;
        }
    }, [w.getSigner, w.deployment, escrowFactory]);

    const markIndexed = useCallback(() => dispatch({ type: 'INDEXED' }), []);
    const reset = useCallback(() => dispatch({ type: 'RESET' }), []);
    return { state, run, markIndexed, reset, busy, failed: state.step === CLAIM_STEP.FAILED };
}
