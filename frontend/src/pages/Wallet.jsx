import { useCallback, useEffect, useState } from 'react';
import Navbar from '../components/Navbar';
import { useWallet } from '../hooks/useWallet';
import { fetchLinkedWalletAPI, linkWalletAPI, requestWalletNonceAPI } from '../api/web3';
import { isUserRejection, toUserMessage } from '../lib/errors';
import { LINK_STEP, linkState, runLinkFlow } from '../lib/walletLink';
import { shortAddress } from '../lib/format';

const STEP_TEXT = {
    [LINK_STEP.REQUESTING_NONCE]: 'Đang lấy mã xác thực…',
    [LINK_STEP.AWAITING_SIGNATURE]: 'Hãy mở ví và bấm "Ký" để xác nhận (không tốn phí gas).',
    [LINK_STEP.LINKING]: 'Đang xác minh chữ ký…',
};

const card = { background: '#fff', border: '1px solid #e5e5e5', borderRadius: 8, padding: 20, marginBottom: 16 };
const btn = { padding: '10px 18px', borderRadius: 6, border: 'none', background: '#ee4d2d', color: '#fff', cursor: 'pointer', fontWeight: 600 };

/** UC-00: kết nối MetaMask rồi liên kết ví với tài khoản bằng chữ ký personal_sign. */
export default function Wallet() {
    const w = useWallet();
    const [linked, setLinked] = useState(null); // null = đang tải
    const [loadError, setLoadError] = useState('');
    const [step, setStep] = useState(LINK_STEP.IDLE);
    const [message, setMessage] = useState({ kind: '', text: '' });

    const refresh = useCallback(async () => {
        try {
            setLinked(await fetchLinkedWalletAPI());
            setLoadError('');
        } catch (e) {
            setLoadError(toUserMessage(e));
            setLinked({ linked: false });
        }
    }, []);
    useEffect(() => { refresh(); }, [refresh]);

    const busy = step !== LINK_STEP.IDLE && step !== LINK_STEP.DONE;
    const state = linkState({ linked, account: w.account });

    const handleLink = async () => {
        setMessage({ kind: '', text: '' });
        try {
            const signer = await w.getSigner();
            await runLinkFlow({ address: w.account, signer, api: { requestWalletNonceAPI, linkWalletAPI }, onStep: setStep });
            await refresh();
            setMessage({ kind: 'ok', text: 'Đã liên kết ví với tài khoản của bạn.' });
        } catch (e) {
            // Hủy trong ví là lựa chọn của người dùng, không phải lỗi
            setMessage({ kind: isUserRejection(e) ? 'info' : 'error', text: toUserMessage(e) });
        } finally {
            setStep(LINK_STEP.IDLE);
        }
    };

    return (
        <div>
            <Navbar />
            <main style={{ maxWidth: 640, margin: '24px auto', padding: '0 16px' }}>
                <h2>Ví của bạn</h2>
                <p style={{ color: '#666' }}>Liên kết ví MetaMask để thanh toán bằng ký quỹ (mUSD trên mạng thử Anvil). Không dùng tiền thật.</p>

                <section style={card} aria-label="Kết nối ví">
                    <h3>1. Kết nối ví</h3>
                    {!w.hasProvider && <p role="alert">Không tìm thấy ví. Hãy cài MetaMask rồi tải lại trang.</p>}
                    {w.hasProvider && !w.isConnected && (
                        <button type="button" style={btn} onClick={w.connect} disabled={w.status === 'connecting'}>
                            {w.status === 'connecting' ? 'Đang kết nối…' : 'Kết nối MetaMask'}
                        </button>
                    )}
                    {w.isConnected && (
                        <>
                            <p>Đang kết nối: <strong data-testid="connected-address" title={w.account}>{shortAddress(w.account)}</strong></p>
                            {w.deploymentStatus === 'error' && <p role="alert">{w.deploymentError?.message}</p>}
                            {!w.isCorrectChain && w.deploymentStatus !== 'error' && (
                                <p role="alert">
                                    Ví đang ở sai mạng.{' '}
                                    <button type="button" style={btn} onClick={w.switchToDeployedChain}>Chuyển sang mạng Anvil</button>
                                </p>
                            )}
                        </>
                    )}
                    {w.error && <p role="alert" style={{ color: '#c0392b' }}>{w.error.message}</p>}
                </section>

                <section style={card} aria-label="Liên kết tài khoản">
                    <h3>2. Liên kết với tài khoản Slopee</h3>
                    {linked === null && <p>Đang tải…</p>}
                    {loadError && <p role="alert" style={{ color: '#c0392b' }}>{loadError}</p>}

                    {linked?.linked && (
                        <p>Ví đã liên kết: <strong data-testid="linked-address" title={linked.address}>{shortAddress(linked.address)}</strong></p>
                    )}
                    {state === 'LINKED_THIS' && <p data-testid="link-ok" style={{ color: '#2e7d32' }}>✓ Ví đang kết nối chính là ví đã liên kết.</p>}
                    {state === 'LINKED_OTHER' && (
                        <p role="alert" style={{ color: '#b26a00' }}>
                            Ví đang kết nối khác ví đã liên kết. Bạn có thể đổi sang ví này — ví cũ sẽ ngừng được dùng để thanh toán.
                        </p>
                    )}
                    {state === 'NOT_LINKED' && <p>Tài khoản chưa liên kết ví nào.</p>}
                    {state === 'NO_ACCOUNT' && <p>Hãy kết nối ví ở bước 1 trước.</p>}

                    {(state === 'NOT_LINKED' || state === 'LINKED_OTHER') && (
                        <button type="button" style={btn} onClick={handleLink} disabled={busy || !w.isCorrectChain}>
                            {state === 'LINKED_OTHER' ? 'Đổi sang ví này' : 'Liên kết ví này'}
                        </button>
                    )}
                    {(state === 'NOT_LINKED' || state === 'LINKED_OTHER') && !w.isCorrectChain && (
                        <p style={{ color: '#666', fontSize: 13 }}>Cần chuyển đúng mạng trước khi ký.</p>
                    )}
                    {busy && <p data-testid="link-progress" role="status">{STEP_TEXT[step]}</p>}
                    {message.text && (
                        <p role={message.kind === 'error' ? 'alert' : 'status'}
                            style={{ color: message.kind === 'error' ? '#c0392b' : message.kind === 'ok' ? '#2e7d32' : '#555' }}>
                            {message.text}
                        </p>
                    )}
                    <p style={{ color: '#888', fontSize: 12 }}>Bạn chỉ ký một thông điệp xác thực, không gửi giao dịch và không mất phí gas.</p>
                </section>
            </main>
        </div>
    );
}
