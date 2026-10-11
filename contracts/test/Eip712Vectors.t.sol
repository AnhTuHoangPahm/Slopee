// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./EscrowBase.t.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

/// @notice Kiểm tra chéo ngôn ngữ phía Solidity: dùng đúng `shared/eip712/vectors.json` mà Python (eth_account)
///         và JavaScript (ethers v6) cũng kiểm tra. Phải cho cùng domainSeparator, structHash, digest, người ký.
///         Báo giá trong vector còn được NẠP THẬT vào contract để chứng minh chữ ký Python được contract chấp nhận (I-02).
contract Eip712VectorsTest is EscrowBase {
    string internal json;
    address internal vecEscrow;
    address internal vecToken;

    function setUp() public override {
        super.setUp();
        json = vm.readFile("../shared/eip712/vectors.json");

        vecEscrow = vm.parseJsonAddress(json, ".domain.verifyingContract");
        vecToken = vm.parseJsonAddress(json, ".orderQuote[0].message.token");
        assertEq(vm.parseJsonUint(json, ".domain.chainId"), block.chainid, "vector chainId != anvil/forge chainId");

        // Đặt contract và token đúng địa chỉ mà vector dùng làm verifyingContract / token
        deployCodeTo(
            "SlopeeEscrowMaster.sol:SlopeeEscrowMaster",
            abi.encode(admin, shipper, arbitrator, signer, feeRecipient),
            vecEscrow
        );
        escrow = SlopeeEscrowMaster(vecEscrow);
        deployCodeTo("MockUSD.sol:MockUSD", "", vecToken);
        usd = MockUSD(vecToken);
        usd.mint(buyer, 1_000_000_000);
        vm.prank(buyer);
        usd.approve(address(escrow), type(uint256).max);

        // Tài khoản trong vector phải là tài khoản Anvil mà test dùng
        assertEq(vm.parseJsonAddress(json, ".accounts.buyer"), buyer);
        assertEq(vm.parseJsonAddress(json, ".accounts.merchant"), merchant);
        assertEq(vm.parseJsonAddress(json, ".accounts.quoteSigner"), signer);
        assertEq(vm.parseJsonAddress(json, ".accounts.arbitrator"), arbitrator);
    }

    function _p(string memory prefix, string memory field) internal pure returns (string memory) {
        return string.concat(prefix, field);
    }

    function _quoteFromVector(uint256 i) internal view returns (SlopeeEscrowMaster.Quote memory q) {
        string memory pre = string.concat(".orderQuote[", vm.toString(i), "].message.");
        q.orderId = vm.parseJsonUint(json, _p(pre, "orderId"));
        q.buyer = vm.parseJsonAddress(json, _p(pre, "buyer"));
        q.merchant = vm.parseJsonAddress(json, _p(pre, "merchant"));
        q.token = vm.parseJsonAddress(json, _p(pre, "token"));
        q.amount = vm.parseJsonUint(json, _p(pre, "amount"));
        q.inspectionDuration = vm.parseJsonUint(json, _p(pre, "inspectionDuration"));
        q.disputeTimeout = vm.parseJsonUint(json, _p(pre, "disputeTimeout"));
        q.feeBps = vm.parseJsonUint(json, _p(pre, "feeBps"));
        q.docHash = vm.parseJsonBytes32(json, _p(pre, "docHash"));
        q.deadline = vm.parseJsonUint(json, _p(pre, "deadline"));
    }

    function test_vectors_typeStringsMatchContractTypehashes() public view {
        string memory typesJson = vm.readFile("../shared/eip712/types.json");
        string memory quoteStr = vm.parseJsonString(typesJson, ".typeStrings.OrderQuote");
        string memory disputeStr = vm.parseJsonString(typesJson, ".typeStrings.DisputeResolution");
        assertEq(keccak256(bytes(quoteStr)), escrow.QUOTE_TYPEHASH());
        assertEq(keccak256(bytes(disputeStr)), escrow.DISPUTE_TYPEHASH());
    }

    function test_vectors_orderQuote_digestAndSigner() public view {
        for (uint256 i = 0; i < 3; i++) {
            string memory pre = string.concat(".orderQuote[", vm.toString(i), "].");
            SlopeeEscrowMaster.Quote memory q = _quoteFromVector(i);

            assertEq(_domainSeparator(), vm.parseJsonBytes32(json, _p(pre, "domainSeparator")), "domainSeparator");
            bytes32 digest = _quoteDigest(q);
            assertEq(digest, vm.parseJsonBytes32(json, _p(pre, "digest")), "digest");

            address recovered = ECDSA.recover(digest, vm.parseJsonBytes(json, _p(pre, "signature")));
            assertEq(recovered, vm.parseJsonAddress(json, _p(pre, "signer")), "signer");
            assertEq(recovered, signer, "signer != QUOTE_SIGNER");
        }
    }

    /// @dev Chữ ký do Python tạo được contract chấp nhận: nạp ERC-20 (vector 0) và ETH (vector 1).
    function test_vectors_orderQuote_pythonSignatureAcceptedByContract() public {
        SlopeeEscrowMaster.Quote memory q0 = _quoteFromVector(0);
        bytes memory sig0 = vm.parseJsonBytes(json, ".orderQuote[0].signature");
        vm.prank(buyer);
        escrow.depositEscrow(q0, sig0);
        assertEq(uint8(_state(q0.orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
        assertEq(usd.balanceOf(address(escrow)), q0.amount);

        SlopeeEscrowMaster.Quote memory q1 = _quoteFromVector(1);
        bytes memory sig1 = vm.parseJsonBytes(json, ".orderQuote[1].signature");
        vm.prank(buyer);
        escrow.depositEscrow{value: q1.amount}(q1, sig1);
        assertEq(uint8(_state(q1.orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
        assertEq(address(escrow).balance, q1.amount);
    }

    function test_vectors_disputeResolution_digestAndSigners() public view {
        for (uint256 i = 0; i < 2; i++) {
            string memory pre = string.concat(".disputeResolution[", vm.toString(i), "].");
            string memory m = string.concat(pre, "message.");
            bytes32 structHash = keccak256(abi.encode(
                escrow.DISPUTE_TYPEHASH(),
                vm.parseJsonUint(json, _p(m, "orderId")),
                vm.parseJsonAddress(json, _p(m, "payoutTo")),
                vm.parseJsonUint(json, _p(m, "amount")),
                vm.parseJsonUint(json, _p(m, "nonce")),
                vm.parseJsonUint(json, _p(m, "deadline"))
            ));
            assertEq(structHash, vm.parseJsonBytes32(json, _p(pre, "structHash")), "structHash");
            bytes32 digest = keccak256(abi.encodePacked("\x19\x01", _domainSeparator(), structHash));
            assertEq(digest, vm.parseJsonBytes32(json, _p(pre, "digest")), "digest");

            assertEq(
                ECDSA.recover(digest, vm.parseJsonBytes(json, _p(pre, "signature"))),
                vm.parseJsonAddress(json, _p(pre, "signer")),
                "party signer"
            );
            assertEq(
                ECDSA.recover(digest, vm.parseJsonBytes(json, _p(pre, "arbitratorSignature"))),
                arbitrator,
                "arbitrator signer"
            );
        }
    }

    function test_vectors_docHash() public view {
        for (uint256 i = 0; i < 2; i++) {
            string memory pre = string.concat(".docHash[", vm.toString(i), "].");
            string memory canonical = vm.parseJsonString(json, _p(pre, "canonicalJson"));
            assertEq(keccak256(bytes(canonical)), vm.parseJsonBytes32(json, _p(pre, "docHash")));
        }
    }
}
