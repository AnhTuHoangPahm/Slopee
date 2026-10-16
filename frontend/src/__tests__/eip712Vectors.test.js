// Kiểm tra chéo ngôn ngữ phía JavaScript: dùng đúng shared/eip712/vectors.json mà Python (test_eip712_vectors.py)
// và Solidity (Eip712Vectors.t.sol) cũng kiểm tra. Cùng domainSeparator/digest/người ký ⇒ ba nơi băm giống hệt nhau.
import { describe, it, expect } from 'vitest';
import { TypedDataEncoder, keccak256, toUtf8Bytes, verifyMessage } from 'ethers';
import vectors from '../../../shared/eip712/vectors.json';
import typesFile from '../../../shared/eip712/types.json';
import {
    EIP712_TYPES, buildDomain, disputeDigest, quoteDigest, recoverDisputeSigner, recoverQuoteSigner,
} from '../lib/eip712';

const deployment = { chainId: vectors.domain.chainId, escrow: vectors.domain.verifyingContract };
const domain = buildDomain(deployment);

describe('shared/eip712 — JavaScript (ethers v6)', () => {
    it('domain dựng từ tệp triển khai khớp domain trong vector', () => {
        expect(domain).toEqual(vectors.domain);
    });

    it('typeStrings trong types.json khớp danh sách trường (đúng thứ tự)', () => {
        for (const [name, fields] of Object.entries(EIP712_TYPES)) {
            const expected = `${name}(${fields.map((f) => `${f.type} ${f.name}`).join(',')})`;
            expect(typesFile.typeStrings[name]).toBe(expected);
        }
    });

    it.each(vectors.orderQuote.map((v) => [v.name, v]))('OrderQuote %s: domainSeparator, structHash, digest, người ký', (_n, v) => {
        expect(TypedDataEncoder.hashDomain(domain)).toBe(v.domainSeparator);
        expect(TypedDataEncoder.hashStruct('OrderQuote', { OrderQuote: EIP712_TYPES.OrderQuote }, v.message)).toBe(v.structHash);
        expect(quoteDigest(domain, v.message)).toBe(v.digest);
        expect(recoverQuoteSigner(domain, v.message, v.signature)).toBe(v.signer);
        expect(v.signer).toBe(vectors.accounts.quoteSigner);
    });

    it.each(vectors.disputeResolution.map((v) => [v.name, v]))('DisputeResolution %s: structHash, digest, hai người ký', (_n, v) => {
        expect(TypedDataEncoder.hashStruct('DisputeResolution', { DisputeResolution: EIP712_TYPES.DisputeResolution }, v.message)).toBe(v.structHash);
        expect(disputeDigest(domain, v.message)).toBe(v.digest);
        expect(recoverDisputeSigner(domain, v.message, v.signature)).toBe(v.signer);
        expect(recoverDisputeSigner(domain, v.message, v.arbitratorSignature)).toBe(v.arbitrator);
    });

    it.each(vectors.docHash.map((v) => [v.name, v]))('docHash %s: keccak256(canonical_json)', (_n, v) => {
        expect(keccak256(toUtf8Bytes(v.canonicalJson))).toBe(v.docHash);
    });

    it('đổi một trường (số tiền) thì chữ ký khôi phục ra địa chỉ khác', () => {
        const v = vectors.orderQuote[0];
        const tampered = { ...v.message, amount: String(BigInt(v.message.amount) + 1n) };
        expect(recoverQuoteSigner(domain, tampered, v.signature)).not.toBe(v.signer);
    });

    it('đổi verifyingContract thì digest đổi (chống phát lại chéo hợp đồng)', () => {
        const v = vectors.orderQuote[0];
        const other = { ...domain, verifyingContract: '0x5FbDB2315678afecb367f032d93F642f64180aa3' };
        expect(quoteDigest(other, v.message)).not.toBe(v.digest);
    });
});

describe('walletLink (UC-00): chữ ký personal_sign do Python sinh, ethers phải khôi phục đúng người ký', () => {
    it.each(vectors.walletLink.map((v) => [v.name, v]))('%s', (_n, v) => {
        expect(verifyMessage(v.message, v.signature)).toBe(v.signer);
        expect(verifyMessage(`${v.message} `, v.signature)).not.toBe(v.signer); // đổi một ký tự là ra người khác
        // thông điệp ràng buộc đủ ngữ cảnh: tên miền, địa chỉ (chữ thường), tài khoản, nonce, chainId, thời hạn
        [v.domain, v.address.toLowerCase(), v.userId, v.nonce, `Chain ID: ${v.chainId}`, 'Expiration Time:'].forEach((x) => expect(v.message).toContain(x));
    });
});
