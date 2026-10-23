// Ký phán quyết bằng ví (`eth_signTypedData_v4`, không tốn gas) rồi gửi chữ ký lên sàn. Một instance cho một màn hình.
import { useCallback, useReducer, useRef } from 'react';
import { sendDisputeSignatureAPI } from '../api/disputes';
import { initialSignState, isSignBusy, sendSignature, signAndSendDispute, signReducer } from '../lib/disputeFlow';
import { expectedWallet } from '../lib/disputeSign';
import { useWallet } from './useWallet';

/**
 * @param {{ send?: Function, onSent?: Function }} [opts]  `send` chỉ để test; `onSent` gọi sau khi sàn nhận chữ ký (để làm mới dữ liệu)
 * @returns {{ state, sign(view), resend(view), reset(), busy }}
 */
export function useSignDispute({ send = sendDisputeSignatureAPI, onSent } = {}) {
    const w = useWallet();
    const [state, dispatch] = useReducer(signReducer, undefined, initialSignState);
    const running = useRef(false); // chặn bấm dồn: một luồng ví tại một thời điểm
    const busy = isSignBusy(state);

    const guard = useCallback(async (fn) => {
        if (running.current) return null;
        running.current = true;
        try {
            const res = await fn();
            onSent?.();
            return res;
        } catch {
            return null; // lỗi đã được phát qua dispatch(FAIL)
        } finally {
            running.current = false;
        }
    }, [onSent]);

    const sign = useCallback((view) => guard(async () => {
        const signer = await w.getSigner();
        return signAndSendDispute({ view, signer, deployment: w.deployment, send, dispatch, expectedWallet: expectedWallet(view) });
    }), [guard, w, send]);

    const resend = useCallback((view) => guard(async () => {
        dispatch({ type: 'RESEND' });
        return sendSignature({ view, signature: state.signature, send, dispatch });
    }), [guard, state.signature, send]);

    const reset = useCallback(() => dispatch({ type: 'RESET' }), []);
    return { state, sign, resend, reset, busy };
}
