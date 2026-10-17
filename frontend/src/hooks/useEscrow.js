// Hai bước ví của Buyer (SDD 9.3): approve tổng rồi depositEscrowBatch. Địa chỉ lấy từ deployments/local.json (qua useWallet),
// ABI lấy từ lib/abi (đóng băng ở M1). Mọi số tiền là BigInt.
import { useCallback, useEffect, useReducer, useRef } from 'react';
import { Contract } from 'ethers';
import escrowAbi from '../lib/abi/SlopeeEscrowMaster.json';
import tokenAbi from '../lib/abi/MockUSD.json';
import { depositReducer, initialDepositState, isBusy, mapDepositError, runDeposit } from '../lib/depositFlow';
import { useWallet } from './useWallet';

/** Dựng hai hợp đồng ethers gắn signer của ví đang kết nối. Tách riêng để test thay thế được. */
export async function makeContracts({ getSigner, deployment }) {
    const signer = await getSigner();
    return {
        token: new Contract(deployment.mockUSD, tokenAbi, signer),
        escrow: new Contract(deployment.escrow, escrowAbi, signer),
    };
}

/**
 * @param {object}   [opts]
 * @param {Function} [opts.contractsFactory]  thay cho makeContracts (chỉ dùng khi test)
 * @returns {{ state, deposit(group, remaining), reset(), busy }}
 */
export function useEscrow({ contractsFactory = makeContracts } = {}) {
    const w = useWallet();
    const [state, dispatch] = useReducer(depositReducer, undefined, initialDepositState);
    const running = useRef(false); // chặn bấm dồn: mỗi lần chỉ MỘT luồng ví

    const busy = isBusy(state);
    // Cảnh báo khi đóng/tải lại tab giữa chừng (tiền có thể đã được approve/nạp mà giao diện chưa kịp ghi nhận)
    useEffect(() => {
        if (!busy) return undefined;
        const onBeforeUnload = (e) => { e.preventDefault(); e.returnValue = ''; };
        window.addEventListener('beforeunload', onBeforeUnload);
        return () => window.removeEventListener('beforeunload', onBeforeUnload);
    }, [busy]);

    const deposit = useCallback(async (group, remaining) => {
        if (running.current) return null;
        running.current = true;
        try {
            let contracts;
            try {
                contracts = await contractsFactory({ getSigner: w.getSigner, deployment: w.deployment });
            } catch (e) { // không lấy được signer/hợp đồng: phải hiện lỗi, không được im lặng
                dispatch({ type: 'START' });
                const mapped = mapDepositError(e);
                const walletMsg = { code: 'WALLET_UNAVAILABLE', message: 'Không kết nối được ví. Hãy kết nối lại MetaMask rồi thử lại.', userRejected: false, extra: {} };
                dispatch({ type: 'FAIL', error: mapped.userRejected ? mapped : walletMsg });
                return null;
            }
            return await runDeposit({ group, account: w.account, deployment: w.deployment, ...contracts, remaining, dispatch });
        } catch {
            return null; // runDeposit đã phát FAIL cho mọi lỗi của luồng
        } finally {
            running.current = false;
        }
    }, [w.getSigner, w.deployment, w.account, contractsFactory]);

    const reset = useCallback(() => dispatch({ type: 'RESET' }), []);
    return { state, dispatch, deposit, reset, busy };
}
