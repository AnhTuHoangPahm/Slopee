// EIP-712 phía JavaScript (ethers v6). Kiểu dữ liệu đọc từ `shared/eip712/types.json` — nguồn DUY NHẤT dùng chung
// với Python (eth_account) và Solidity (typehash); không tự gõ lại danh sách trường ở đây (SDD 8.1).
import { TypedDataEncoder, verifyTypedData } from 'ethers';
import typesFile from '../../../shared/eip712/types.json';

export const EIP712_TYPES = Object.freeze(typesFile.types);
export const EIP712_DOMAIN_NAME = typesFile.domain.name;
export const EIP712_DOMAIN_VERSION = typesFile.domain.version;

/** Domain ký: chainId và verifyingContract CHỈ lấy từ đối tượng triển khai đã qua `parseDeployment`. */
export const buildDomain = (deployment) => ({
    name: EIP712_DOMAIN_NAME,
    version: EIP712_DOMAIN_VERSION,
    chainId: deployment.chainId,
    verifyingContract: deployment.escrow,
});

const only = (primary) => ({ [primary]: EIP712_TYPES[primary] });

export const quoteDigest = (domain, message) => TypedDataEncoder.hash(domain, only('OrderQuote'), message);
export const disputeDigest = (domain, message) => TypedDataEncoder.hash(domain, only('DisputeResolution'), message);

export const recoverQuoteSigner = (domain, message, signature) =>
    verifyTypedData(domain, only('OrderQuote'), message, signature);
export const recoverDisputeSigner = (domain, message, signature) =>
    verifyTypedData(domain, only('DisputeResolution'), message, signature);

/** Ký phán quyết bằng ví người dùng (`eth_signTypedData_v4`, không tốn gas). Dùng ở tuần 6 (pages/Dispute.jsx). */
export const signDispute = (signer, domain, message) =>
    signer.signTypedData(domain, only('DisputeResolution'), message);
