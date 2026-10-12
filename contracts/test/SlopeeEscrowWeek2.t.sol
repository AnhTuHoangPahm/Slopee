// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./EscrowBase.t.sol";
import "./TestActors.sol";
import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";

/// @notice Test tuần 2 (phần tranh chấp, thoát hiểm, sổ chờ rút, quản trị, an toàn).
///         Mã T-xx theo SRS mục 12.1 / PROGRESS.md mục 5.1. Phần nạp gom (T-25…T-34) ở `SlopeeEscrowBatch.t.sol`.
contract SlopeeEscrowWeek2Test is EscrowBase {
    uint256 internal constant SECP_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;

    address internal outsider;

    function setUp() public override {
        super.setUp();
        outsider = makeAddr("outsider");
        vm.deal(address(this), 100 ether);
    }

    // ------------------------------------------------------------------ Helpers cục bộ

    function _depositEthTo(address merchant_, uint256 amount) internal returns (SlopeeEscrowMaster.Quote memory q) {
        q = _quote(address(0), amount);
        q.merchant = merchant_;
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        escrow.depositEscrow{value: amount}(q, sig);
    }

    /// @dev Đơn token DISPUTED với `disputeTimeout` tùy chọn (T-15, T-20, T-21).
    function _disputedOrder(uint256 timeout) internal returns (SlopeeEscrowMaster.Quote memory q) {
        q = _quote(address(usd), AMOUNT);
        q.disputeTimeout = timeout;
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        escrow.depositEscrow(q, sig);
        _deliver(q.orderId);
        vm.prank(buyer);
        escrow.raiseDispute(q.orderId);
    }

    /// @dev Phân xử bằng hai khóa bất kỳ; người nộp là `submitter` (ai cũng nộp được).
    function _resolve(uint256 id, address payoutTo, uint256 keyA, uint256 keyB, uint256 deadline) internal {
        (bytes memory s1, bytes memory s2) = _twoSigs(keyA, keyB, id, payoutTo, AMOUNT, deadline);
        vm.prank(outsider);
        escrow.resolveDispute(id, payoutTo, deadline, s1, s2);
    }

    function _unauthorized(address who, bytes32 role) internal pure returns (bytes memory) {
        return abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, who, role);
    }

    // ================================================================== T-08 (phần còn lại, cần setDefaultFeeBps)

    function test_T08_feeSplit_at1000Bps_afterRaisingCeiling() public {
        vm.prank(admin);
        escrow.setDefaultFeeBps(1000);
        uint256 amount = 100_000_001;
        SlopeeEscrowMaster.Quote memory q = _depositToken(amount, 1000);
        _deliver(q.orderId);
        vm.prank(buyer);
        escrow.earlyRelease(q.orderId);

        uint256 fee = (amount * 1000) / 10000;
        assertEq(usd.balanceOf(feeRecipient), fee);
        assertEq(usd.balanceOf(merchant), amount - fee);
        assertEq(usd.balanceOf(address(escrow)), 0);
    }

    function test_T08_smallAmounts_roundFeeDown() public {
        uint256[4] memory amounts = [uint256(1), 33, 34, 3333];
        for (uint256 i = 0; i < amounts.length; i++) {
            uint256 mBefore = usd.balanceOf(merchant);
            uint256 fBefore = usd.balanceOf(feeRecipient);
            SlopeeEscrowMaster.Quote memory q = _depositToken(amounts[i], 300);
            _deliver(q.orderId);
            vm.prank(buyer);
            escrow.earlyRelease(q.orderId);
            uint256 fee = (amounts[i] * 300) / 10000; // floor: 1→0, 33→0, 34→1, 3333→99
            assertEq(usd.balanceOf(feeRecipient) - fBefore, fee);
            assertEq(usd.balanceOf(merchant) - mBefore, amounts[i] - fee);
        }
    }

    function test_T08_changingCeilingAfterDeposit_doesNotAffectOldOrder() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, 300); // phí 3% đã chốt
        vm.prank(admin);
        escrow.setDefaultFeeBps(0); // trần hạ về 0 sau khi nạp
        _deliver(q.orderId);
        vm.prank(buyer);
        escrow.earlyRelease(q.orderId);

        assertEq(usd.balanceOf(feeRecipient), (AMOUNT * 300) / 10000);
        assertEq(usd.balanceOf(merchant), AMOUNT - (AMOUNT * 300) / 10000);
    }

    function test_T08_orderCreatedCarriesQuoteFee() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        q.feeBps = 123;
        bytes memory sig = _signQuote(q);
        vm.expectEmit(true, true, true, true, address(escrow));
        emit OrderCreated(q.orderId, buyer, merchant, address(usd), AMOUNT, INSPECTION, DISPUTE_TIMEOUT, DOC_HASH, 123);
        vm.prank(buyer);
        escrow.depositEscrow(q, sig);
    }

    // ================================================================== T-09

    function test_T09_setDefaultFeeBps_aboveMax_reverts() public {
        vm.prank(admin);
        vm.expectRevert("Exceeds cap");
        escrow.setDefaultFeeBps(1001);
    }

    function test_T09_setDefaultFeeBps_exactMax_emitsAndSets() public {
        vm.expectEmit(false, false, false, true, address(escrow));
        emit FeeUpdated(1000);
        vm.prank(admin);
        escrow.setDefaultFeeBps(1000);
        assertEq(escrow.defaultFeeBps(), 1000);
    }

    function test_T09_setDefaultFeeBps_nonAdmin_reverts() public {
        bytes32 role = escrow.DEFAULT_ADMIN_ROLE();
        address[5] memory callers = [buyer, merchant, shipper, arbitrator, outsider];
        for (uint256 i = 0; i < callers.length; i++) {
            vm.prank(callers[i]);
            vm.expectRevert(_unauthorized(callers[i], role));
            escrow.setDefaultFeeBps(100);
        }
        assertEq(escrow.defaultFeeBps(), 300);
    }

    function test_T09_setFeeRecipient_rules() public {
        bytes32 role = escrow.DEFAULT_ADMIN_ROLE();
        address newRecipient = makeAddr("newRecipient");

        vm.prank(outsider);
        vm.expectRevert(_unauthorized(outsider, role));
        escrow.setFeeRecipient(newRecipient);

        vm.prank(admin);
        vm.expectRevert("Invalid fee recipient");
        escrow.setFeeRecipient(address(0));

        vm.expectEmit(false, false, false, true, address(escrow));
        emit FeeRecipientUpdated(newRecipient);
        vm.prank(admin);
        escrow.setFeeRecipient(newRecipient);
        assertEq(escrow.feeRecipient(), newRecipient);

        // phí của đơn sau đó về đúng người nhận mới
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, 300);
        _deliver(q.orderId);
        vm.prank(buyer);
        escrow.earlyRelease(q.orderId);
        assertEq(usd.balanceOf(newRecipient), (AMOUNT * 300) / 10000);
        assertEq(usd.balanceOf(feeRecipient), 0);
    }

    // ================================================================== T-22 (phần còn lại)

    function test_T22_feeEqualToCeiling_accepted() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, 300);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
    }

    function test_T22_adminLowersCeiling_oldQuoteRejected_newQuoteAccepted() public {
        SlopeeEscrowMaster.Quote memory oldQ = _quote(address(usd), AMOUNT); // feeBps = 300, đã ký
        bytes memory oldSig = _signQuote(oldQ);

        vm.prank(admin);
        escrow.setDefaultFeeBps(100);

        vm.prank(buyer);
        vm.expectRevert("Fee exceeds on-chain cap");
        escrow.depositEscrow(oldQ, oldSig);

        SlopeeEscrowMaster.Quote memory newQ = _quote(address(usd), AMOUNT);
        newQ.feeBps = 100;
        bytes memory newSig = _signQuote(newQ);
        vm.expectEmit(true, true, true, true, address(escrow));
        emit OrderCreated(newQ.orderId, buyer, merchant, address(usd), AMOUNT, INSPECTION, DISPUTE_TIMEOUT, DOC_HASH, 100);
        vm.prank(buyer);
        escrow.depositEscrow(newQ, newSig);
    }

    // ================================================================== T-21 (chữ ký gắn với từng trường báo giá)

    function test_T21_tamperAfterSigning_isRejected() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _signQuote(q);

        SlopeeEscrowMaster.Quote memory t1 = q;
        t1.disputeTimeout = 30 days;
        vm.prank(buyer);
        vm.expectRevert("Bad quote signature");
        escrow.depositEscrow(t1, sig);

        SlopeeEscrowMaster.Quote memory t2 = q;
        t2.feeBps = 100;
        vm.prank(buyer);
        vm.expectRevert("Bad quote signature");
        escrow.depositEscrow(t2, sig);

        // đổi buyer sang ví khác và để chính ví đó gọi: qua kiểm tra người nạp nhưng chữ ký không còn khớp
        address other = makeAddr("otherBuyer");
        usd.mint(other, AMOUNT);
        vm.prank(other);
        usd.approve(address(escrow), AMOUNT);
        SlopeeEscrowMaster.Quote memory t3 = q;
        t3.buyer = other;
        vm.prank(other);
        vm.expectRevert("Bad quote signature");
        escrow.depositEscrow(t3, sig);
    }

    function test_T21_parallelOrders_independentTimeouts() public {
        SlopeeEscrowMaster.Quote memory q7 = _disputedOrder(7 days);
        SlopeeEscrowMaster.Quote memory q45 = _disputedOrder(45 days);
        uint256 at7 = _disputedAt(q7.orderId);

        vm.warp(at7 + 8 days); // ngày thứ 8: đơn 7 ngày xử được, đơn 45 ngày thì chưa
        vm.prank(arbitrator);
        escrow.arbitratorForceResolve(q7.orderId, buyer);
        assertEq(uint8(_state(q7.orderId)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));

        vm.prank(arbitrator);
        vm.expectRevert("Dispute timeout not reached");
        escrow.arbitratorForceResolve(q45.orderId, buyer);
        assertEq(uint8(_state(q45.orderId)), uint8(SlopeeEscrowMaster.OrderState.DISPUTED));
    }

    // ================================================================== T-10 (raiseDispute)

    function test_T10_raiseDispute_inWindow_freezesFunds() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        _deliver(q.orderId);
        vm.warp(block.timestamp + INSPECTION - 1);

        uint256 nowTs = vm.getBlockTimestamp(); // đọc trực tiếp từ cheatcode: không phụ thuộc cách biên dịch (kể cả coverage --ir-minimum)
        vm.expectEmit(true, true, false, true, address(escrow));
        emit OrderDisputed(q.orderId, buyer, nowTs);
        vm.prank(buyer);
        escrow.raiseDispute(q.orderId);

        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.DISPUTED));
        assertEq(_disputedAt(q.orderId), nowTs);
        assertEq(usd.balanceOf(address(escrow)), AMOUNT); // tiền vẫn nằm trong contract
    }

    function test_T10_raiseDispute_atExactExpiry_reverts_andReleaseBecomesValid() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        _deliver(q.orderId);
        vm.warp(block.timestamp + INSPECTION); // đúng mốc hết hạn kiểm tra

        vm.prank(buyer);
        vm.expectRevert("Expired");
        escrow.raiseDispute(q.orderId);

        escrow.releaseAfterInspection(q.orderId); // tại mốc này chỉ có đường giải ngân hợp lệ
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
    }

    function test_T10_oneSecondBeforeExpiry_disputeOk_releaseReverts() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        _deliver(q.orderId);
        vm.warp(block.timestamp + INSPECTION - 1);

        vm.expectRevert("Under inspection");
        escrow.releaseAfterInspection(q.orderId);

        vm.prank(buyer);
        escrow.raiseDispute(q.orderId);
    }

    function test_T10_raiseDispute_byNonBuyer_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        _deliver(q.orderId);
        address[4] memory callers = [merchant, shipper, arbitrator, outsider];
        for (uint256 i = 0; i < callers.length; i++) {
            vm.prank(callers[i]);
            vm.expectRevert("Only buyer");
            escrow.raiseDispute(q.orderId);
        }
    }

    function test_T10_raiseDispute_notDelivered_orTwice_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.prank(buyer);
        vm.expectRevert("Not delivered"); // đơn còn LOCKED
        escrow.raiseDispute(q.orderId);

        _deliver(q.orderId);
        vm.prank(buyer);
        escrow.raiseDispute(q.orderId);
        vm.prank(buyer);
        vm.expectRevert("Not delivered"); // đã DISPUTED
        escrow.raiseDispute(q.orderId);
    }

    // ================================================================== T-11 (resolveDispute thành công)

    function test_T11_arbitratorPlusBuyer_refundsBuyer() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, deadline);

        vm.expectEmit(true, true, false, true, address(escrow));
        emit OrderRefunded(q.orderId, buyer, AMOUNT);
        vm.expectEmit(true, true, false, true, address(escrow));
        emit DisputeResolved(q.orderId, buyer, AMOUNT);
        vm.prank(outsider); // ai cũng nộp được
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);

        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));
        assertEq(usd.balanceOf(buyer), 1_000_000_000); // hoàn đủ, không trừ phí
        assertEq(usd.balanceOf(merchant), 0);
        assertEq(usd.balanceOf(feeRecipient), 0);
        assertEq(usd.balanceOf(address(escrow)), 0);
        assertEq(escrow.disputeNonces(q.orderId), 1);
    }

    function test_T11_arbitratorPlusMerchant_paysMerchantWithFee() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, MERCHANT_KEY, q.orderId, merchant, AMOUNT, deadline);
        uint256 fee = (AMOUNT * FEE_BPS) / 10000;

        vm.expectEmit(true, false, false, true, address(escrow));
        emit OrderCompleted(q.orderId, AMOUNT - fee, fee);
        vm.expectEmit(true, true, false, true, address(escrow));
        emit DisputeResolved(q.orderId, merchant, AMOUNT);
        vm.prank(outsider);
        escrow.resolveDispute(q.orderId, merchant, deadline, s1, s2);

        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
        assertEq(usd.balanceOf(merchant), AMOUNT - fee);
        assertEq(usd.balanceOf(feeRecipient), fee);
        assertEq(usd.balanceOf(address(escrow)), 0);
    }

    function test_T11_buyerPlusMerchant_agreementWithoutArbitrator() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        // hai bên thương lượng được với nhau: hai vai khác nhau (1 và 2) là đủ
        (bytes memory s1, bytes memory s2) = _twoSigs(MERCHANT_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, deadline);
        vm.prank(outsider);
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));
    }

    function test_T11_signatureOrderDoesNotMatter() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(MERCHANT_KEY, ARBITRATOR_KEY, q.orderId, merchant, AMOUNT, deadline);
        escrow.resolveDispute(q.orderId, merchant, deadline, s1, s2);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
    }

    function test_T11_deadlineEqualNow_isAccepted() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp; // `now <= deadline` ⇒ đúng mốc vẫn hợp lệ
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, deadline);
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));
    }

    // ================================================================== T-12 (resolveDispute bị từ chối)

    function test_T12_twoSignaturesFromSameParty_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(BUYER_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, deadline);
        vm.expectRevert("Need two distinct parties");
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);

        (s1, s2) = _twoSigs(MERCHANT_KEY, MERCHANT_KEY, q.orderId, merchant, AMOUNT, deadline);
        vm.expectRevert("Need two distinct parties");
        escrow.resolveDispute(q.orderId, merchant, deadline, s1, s2);
        assertEq(escrow.disputeNonces(q.orderId), 0); // revert thì nonce không tăng
    }

    function test_T12_twoDifferentArbitratorAddresses_countAsOneParty() public {
        uint256 arb2Key = uint256(keccak256("arbitrator-2"));
        bytes32 role = escrow.ARBITRATOR_ROLE();
        vm.prank(admin);
        escrow.grantRole(role, vm.addr(arb2Key));

        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, arb2Key, q.orderId, buyer, AMOUNT, deadline);
        vm.expectRevert("Need two distinct parties");
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
    }

    function test_T12_strangerSignature_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        uint256 strangerKey = uint256(keccak256("stranger"));

        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, strangerKey, q.orderId, buyer, AMOUNT, deadline);
        vm.expectRevert("Need two distinct parties");
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);

        (s1, s2) = _twoSigs(strangerKey, strangerKey, q.orderId, buyer, AMOUNT, deadline);
        vm.expectRevert("Need two distinct parties");
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
    }

    function test_T12_shipperAndSignerRolesAreNotParties() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(SHIPPER_KEY, SIGNER_KEY, q.orderId, buyer, AMOUNT, deadline);
        vm.expectRevert("Need two distinct parties");
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
    }

    function test_T12_expiredSignature_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, deadline);
        vm.warp(deadline + 1);
        vm.expectRevert("Signature expired");
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
    }

    function test_T12_wrongNonce_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        bytes memory s1 = _signDispute(ARBITRATOR_KEY, q.orderId, buyer, AMOUNT, 1, deadline); // nonce thật là 0
        bytes memory s2 = _signDispute(BUYER_KEY, q.orderId, buyer, AMOUNT, 1, deadline);
        vm.expectRevert("Need two distinct parties");
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
    }

    function test_T12_wrongAmount_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        bytes memory s1 = _signDispute(ARBITRATOR_KEY, q.orderId, buyer, AMOUNT + 1, 0, deadline);
        bytes memory s2 = _signDispute(BUYER_KEY, q.orderId, buyer, AMOUNT + 1, 0, deadline);
        vm.expectRevert("Need two distinct parties");
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
    }

    function test_T12_signedForOtherPayee_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        // hai bên ký cho Merchant nhận, nhưng người nộp đổi sang Buyer nhận
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, MERCHANT_KEY, q.orderId, merchant, AMOUNT, deadline);
        vm.expectRevert("Need two distinct parties");
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
    }

    function test_T12_signedForOtherDeadline_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, deadline);
        vm.expectRevert("Need two distinct parties");
        escrow.resolveDispute(q.orderId, buyer, deadline + 1, s1, s2); // đổi deadline sau khi ký
    }

    function test_T12_payoutToStranger_orArbitrator_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, outsider, AMOUNT, deadline);
        vm.expectRevert("Invalid payout recipient");
        escrow.resolveDispute(q.orderId, outsider, deadline, s1, s2);

        (s1, s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, arbitrator, AMOUNT, deadline);
        vm.expectRevert("Invalid payout recipient");
        escrow.resolveDispute(q.orderId, arbitrator, deadline, s1, s2);
    }

    function test_T12_notDisputed_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS); // LOCKED
        vm.expectRevert("Not disputed");
        escrow.resolveDispute(q.orderId, buyer, block.timestamp + 1 days, "", "");
    }

    function test_T12_malformedSignatures_revert() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, ) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, deadline);
        vm.expectRevert(); // chữ ký rỗng ⇒ ECDSAInvalidSignatureLength
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, "");
        vm.expectRevert(); // chữ ký quá ngắn
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, hex"1234");
    }

    /// @dev Chữ ký malleable (s cao, v đảo): OpenZeppelin phải từ chối nên không dùng được để "nhân đôi" một chữ ký thành hai bên.
    function test_T12_malleableSignature_rejected() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(BUYER_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, deadline);
        bytes memory twin = _malleate(s2);
        bytes32 highS;
        assembly {
            highS := mload(add(twin, 64))
        }
        // OpenZeppelin 5.0.2: error ECDSAInvalidSignatureS(bytes32 s)
        vm.expectRevert(abi.encodeWithSelector(bytes4(keccak256("ECDSAInvalidSignatureS(bytes32)")), highS));
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, twin);
    }

    function _malleate(bytes memory sig) internal pure returns (bytes memory) {
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := mload(add(sig, 32))
            s := mload(add(sig, 64))
            v := byte(0, mload(add(sig, 96)))
        }
        return abi.encodePacked(r, bytes32(SECP_N - uint256(s)), v == 27 ? uint8(28) : uint8(27));
    }

    // ================================================================== T-13

    function test_T13_replayAfterSettled_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, deadline);
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);

        vm.expectRevert("Not disputed");
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
        assertEq(usd.balanceOf(buyer), 1_000_000_000); // không hoàn thêm lần hai
        assertEq(usd.balanceOf(address(escrow)), 0);
    }

    function test_T13_signatureOfOneOrder_isUselessForAnother() public {
        SlopeeEscrowMaster.Quote memory a = _toDisputed(AMOUNT, FEE_BPS);
        SlopeeEscrowMaster.Quote memory b = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, a.orderId, buyer, AMOUNT, deadline);
        escrow.resolveDispute(a.orderId, buyer, deadline, s1, s2);

        vm.expectRevert("Need two distinct parties"); // chữ ký đã dùng cho đơn A không áp dụng cho đơn B
        escrow.resolveDispute(b.orderId, buyer, deadline, s1, s2);
        assertEq(uint8(_state(b.orderId)), uint8(SlopeeEscrowMaster.OrderState.DISPUTED));
    }

    function test_T13_resolveAfterForceResolve_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _disputedOrder(DISPUTE_TIMEOUT);
        uint256 at = _disputedAt(q.orderId);
        uint256 deadline = at + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, deadline);
        vm.warp(at + DISPUTE_TIMEOUT);
        vm.prank(arbitrator);
        escrow.arbitratorForceResolve(q.orderId, merchant);

        vm.expectRevert("Not disputed");
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
    }

    // ================================================================== T-24

    function test_T24_deadlineAtOrAfterTimeoutBoundary_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _disputedOrder(DISPUTE_TIMEOUT);
        uint256 limit = _disputedAt(q.orderId) + DISPUTE_TIMEOUT;

        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, limit);
        vm.expectRevert("Deadline must be before dispute timeout");
        escrow.resolveDispute(q.orderId, buyer, limit, s1, s2);

        (s1, s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, limit + 1);
        vm.expectRevert("Deadline must be before dispute timeout");
        escrow.resolveDispute(q.orderId, buyer, limit + 1, s1, s2);

        (s1, s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, type(uint256).max);
        vm.expectRevert("Deadline must be before dispute timeout"); // "chữ ký vĩnh viễn" bị chặn
        escrow.resolveDispute(q.orderId, buyer, type(uint256).max, s1, s2);
    }

    function test_T24_deadlineOneSecondBeforeBoundary_succeeds() public {
        SlopeeEscrowMaster.Quote memory q = _disputedOrder(DISPUTE_TIMEOUT);
        uint256 limit = _disputedAt(q.orderId) + DISPUTE_TIMEOUT;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, limit - 1);
        escrow.resolveDispute(q.orderId, buyer, limit - 1, s1, s2);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));
    }

    // ================================================================== T-15 / T-20 (arbitratorForceResolve)

    function test_T15_forceResolve_beforeAndAfterTimeout_for7_30_90Days() public {
        uint256[3] memory timeouts = [uint256(7 days), 30 days, 90 days];
        for (uint256 i = 0; i < timeouts.length; i++) {
            SlopeeEscrowMaster.Quote memory q = _disputedOrder(timeouts[i]);
            uint256 at = _disputedAt(q.orderId);

            vm.warp(at + timeouts[i] - 1);
            vm.prank(arbitrator);
            vm.expectRevert("Dispute timeout not reached");
            escrow.arbitratorForceResolve(q.orderId, buyer);

            vm.warp(at + timeouts[i]);
            vm.expectEmit(true, true, false, true, address(escrow));
            emit OrderRefunded(q.orderId, buyer, AMOUNT);
            vm.expectEmit(true, true, false, false, address(escrow));
            emit ArbitratorForceResolved(q.orderId, buyer);
            vm.prank(arbitrator);
            escrow.arbitratorForceResolve(q.orderId, buyer);
            assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));
        }
    }

    function test_T15_forceResolve_toMerchant_paysWithFee() public {
        SlopeeEscrowMaster.Quote memory q = _disputedOrder(DISPUTE_TIMEOUT);
        vm.warp(_disputedAt(q.orderId) + DISPUTE_TIMEOUT);
        vm.prank(arbitrator);
        escrow.arbitratorForceResolve(q.orderId, merchant);

        uint256 fee = (AMOUNT * FEE_BPS) / 10000;
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
        assertEq(usd.balanceOf(merchant), AMOUNT - fee);
        assertEq(usd.balanceOf(feeRecipient), fee);
    }

    function test_T15_forceResolve_byNonArbitrator_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _disputedOrder(DISPUTE_TIMEOUT);
        vm.warp(_disputedAt(q.orderId) + DISPUTE_TIMEOUT);
        bytes32 role = escrow.ARBITRATOR_ROLE();
        address[5] memory callers = [admin, buyer, merchant, shipper, outsider];
        for (uint256 i = 0; i < callers.length; i++) {
            vm.prank(callers[i]);
            vm.expectRevert(_unauthorized(callers[i], role));
            escrow.arbitratorForceResolve(q.orderId, buyer);
        }
    }

    function test_T15_forceResolve_strangerPayee_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _disputedOrder(DISPUTE_TIMEOUT);
        vm.warp(_disputedAt(q.orderId) + DISPUTE_TIMEOUT);
        address[3] memory payees = [outsider, arbitrator, address(0)];
        for (uint256 i = 0; i < payees.length; i++) {
            vm.prank(arbitrator);
            vm.expectRevert("Invalid payout recipient");
            escrow.arbitratorForceResolve(q.orderId, payees[i]);
        }
    }

    function test_T15_forceResolve_notDisputed_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        _deliver(q.orderId);
        vm.warp(block.timestamp + 365 days);
        vm.prank(arbitrator);
        vm.expectRevert("Not disputed");
        escrow.arbitratorForceResolve(q.orderId, buyer);
    }

    /// @dev Ca biên R-02: tại mốc trừ 1 giây chỉ `resolveDispute` hợp lệ; tại đúng mốc chỉ `arbitratorForceResolve` hợp lệ.
    function test_T15_boundary_oneSecondBefore_onlySignaturesWork() public {
        SlopeeEscrowMaster.Quote memory q = _disputedOrder(DISPUTE_TIMEOUT);
        uint256 limit = _disputedAt(q.orderId) + DISPUTE_TIMEOUT;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, limit - 1);

        vm.warp(limit - 1);
        vm.prank(arbitrator);
        vm.expectRevert("Dispute timeout not reached");
        escrow.arbitratorForceResolve(q.orderId, buyer);

        escrow.resolveDispute(q.orderId, buyer, limit - 1, s1, s2);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));
    }

    function test_T15_boundary_atExactLimit_onlyForceResolveWorks() public {
        SlopeeEscrowMaster.Quote memory q = _disputedOrder(DISPUTE_TIMEOUT);
        uint256 limit = _disputedAt(q.orderId) + DISPUTE_TIMEOUT;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, limit - 1);

        vm.warp(limit);
        vm.expectRevert("Signature expired"); // chữ ký hợp lệ nhất có thể (deadline = limit - 1) đã hết hạn
        escrow.resolveDispute(q.orderId, buyer, limit - 1, s1, s2);

        (s1, s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, limit);
        vm.expectRevert("Deadline must be before dispute timeout"); // và không thể ký deadline = limit
        escrow.resolveDispute(q.orderId, buyer, limit, s1, s2);

        vm.prank(arbitrator);
        escrow.arbitratorForceResolve(q.orderId, buyer);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));
    }

    // ================================================================== T-20 (phần resolve/force)

    function test_T20_disputeTimeoutBounds_stillEnforced_onDeposit() public {
        uint256[4] memory bad = [uint256(7 days - 1), 90 days + 1, 0, 1 days];
        for (uint256 i = 0; i < bad.length; i++) {
            SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
            q.disputeTimeout = bad[i];
            bytes memory sig = _signQuote(q);
            vm.prank(buyer);
            vm.expectRevert("Invalid dispute timeout");
            escrow.depositEscrow(q, sig);
        }
    }

    // ================================================================== T-16 (sổ chờ rút / claimPending)

    function test_T16_rejectingMerchant_deferred_thenClaimedByOwnerOnly() public {
        SmartWallet wallet = new SmartWallet(false);
        uint256 fee = (1 ether * FEE_BPS) / 10000;
        SlopeeEscrowMaster.Quote memory q = _depositEthTo(address(wallet), 1 ether);
        _deliver(q.orderId);

        vm.expectEmit(true, true, false, true, address(escrow));
        emit PayoutDeferred(address(0), address(wallet), 1 ether - fee);
        vm.prank(buyer);
        escrow.earlyRelease(q.orderId); // không revert dù ví từ chối ETH

        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
        assertEq(feeRecipient.balance, fee); // phần phí vẫn tới nơi ngay
        assertEq(escrow.pendingWithdrawals(address(0), address(wallet)), 1 ether - fee);
        assertEq(address(escrow).balance, 1 ether - fee);

        // người lạ không có gì để rút
        vm.prank(outsider);
        vm.expectRevert("Nothing to claim");
        escrow.claimPending(address(0));

        // ví vẫn từ chối: rút thất bại và sổ chờ rút được giữ nguyên (không mất tiền)
        vm.expectRevert("ETH transfer failed");
        wallet.exec(address(escrow), abi.encodeWithSelector(escrow.claimPending.selector, address(0)));
        assertEq(escrow.pendingWithdrawals(address(0), address(wallet)), 1 ether - fee);

        // ví nhận ETH trở lại: rút thành công
        wallet.setAccept(true);
        vm.expectEmit(true, true, false, true, address(escrow));
        emit PendingClaimed(address(0), address(wallet), 1 ether - fee);
        wallet.exec(address(escrow), abi.encodeWithSelector(escrow.claimPending.selector, address(0)));

        assertEq(address(wallet).balance, 1 ether - fee);
        assertEq(escrow.pendingWithdrawals(address(0), address(wallet)), 0);
        assertEq(address(escrow).balance, 0);

        // rút lần hai
        vm.expectRevert("Nothing to claim");
        wallet.exec(address(escrow), abi.encodeWithSelector(escrow.claimPending.selector, address(0)));
    }

    function test_T16_rejectingFeeRecipient_doesNotBlockMerchant() public {
        SmartWallet feeWallet = new SmartWallet(false);
        vm.prank(admin);
        escrow.setFeeRecipient(address(feeWallet));

        uint256 fee = (1 ether * FEE_BPS) / 10000;
        SlopeeEscrowMaster.Quote memory q = _depositEth(1 ether);
        _deliver(q.orderId);
        uint256 mBefore = merchant.balance;
        vm.prank(buyer);
        escrow.earlyRelease(q.orderId);

        assertEq(merchant.balance - mBefore, 1 ether - fee); // Merchant được trả đủ
        assertEq(escrow.pendingWithdrawals(address(0), address(feeWallet)), fee);

        feeWallet.setAccept(true);
        feeWallet.exec(address(escrow), abi.encodeWithSelector(escrow.claimPending.selector, address(0)));
        assertEq(address(feeWallet).balance, fee);
        assertEq(address(escrow).balance, 0);
    }

    function test_T16_rejectingBuyer_refundDeferred_notStuck() public {
        // Buyer là ví hợp đồng (không ký được EIP-712): hoàn tiền đi đường thoát hiểm của Trọng tài
        SmartWallet buyerWallet = new SmartWallet(false);
        SlopeeEscrowMaster.Quote memory q = _quote(address(0), 1 ether);
        q.buyer = address(buyerWallet);
        bytes memory sig = _signQuote(q);
        buyerWallet.exec{value: 1 ether}(address(escrow), abi.encodeWithSelector(escrow.depositEscrow.selector, q, sig));
        _deliver(q.orderId);
        buyerWallet.exec(address(escrow), abi.encodeWithSelector(escrow.raiseDispute.selector, q.orderId));

        vm.warp(_disputedAt(q.orderId) + DISPUTE_TIMEOUT);
        vm.prank(arbitrator);
        escrow.arbitratorForceResolve(q.orderId, address(buyerWallet)); // không revert

        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));
        assertEq(escrow.pendingWithdrawals(address(0), address(buyerWallet)), 1 ether);

        buyerWallet.setAccept(true);
        buyerWallet.exec(address(escrow), abi.encodeWithSelector(escrow.claimPending.selector, address(0)));
        assertEq(address(buyerWallet).balance, 1 ether);
        assertEq(address(escrow).balance, 0);
    }

    function test_T16_claimPending_erc20_nothingToClaim_reverts() public {
        vm.prank(merchant);
        vm.expectRevert("Nothing to claim");
        escrow.claimPending(address(usd));
    }

    function test_T16_claimPending_erc20Path_paysOutRecordedBalance() public {
        // ERC-20 không bao giờ bị hoãn bởi `_payout`; dựng số dư chờ rút bằng cách ghi trực tiếp vào storage
        // để chứng minh nhánh rút ERC-20 hoạt động và dùng đúng số dư đã ghi.
        uint256 pending = 5_000_000;
        usd.mint(address(escrow), pending); // INV-01 giữ đúng: số dư contract = sổ chờ rút
        bytes32 slot = keccak256(abi.encode(merchant, keccak256(abi.encode(address(usd), uint256(_pendingSlot())))));
        vm.store(address(escrow), slot, bytes32(pending));
        assertEq(escrow.pendingWithdrawals(address(usd), merchant), pending);

        vm.expectEmit(true, true, false, true, address(escrow));
        emit PendingClaimed(address(usd), merchant, pending);
        vm.prank(merchant);
        escrow.claimPending(address(usd));

        assertEq(usd.balanceOf(merchant), pending);
        assertEq(escrow.pendingWithdrawals(address(usd), merchant), 0);
        assertEq(usd.balanceOf(address(escrow)), 0);
    }

    /// @dev Chỉ số slot của `pendingWithdrawals` suy từ layout (sau AccessControl/ReentrancyGuard/EIP712/state biến của contract).
    ///      Tìm bằng cách ghi thử: tránh phụ thuộc số cứng khi layout thay đổi.
    function _pendingSlot() internal returns (uint256 found) {
        for (uint256 s = 0; s < 20; s++) {
            bytes32 slot = keccak256(abi.encode(merchant, keccak256(abi.encode(address(usd), s))));
            bytes32 before = vm.load(address(escrow), slot);
            vm.store(address(escrow), slot, bytes32(uint256(777)));
            if (escrow.pendingWithdrawals(address(usd), merchant) == 777) {
                vm.store(address(escrow), slot, before);
                return s;
            }
            vm.store(address(escrow), slot, before);
        }
        revert("pendingWithdrawals slot not found");
    }

    // ================================================================== T-17 (reentrancy)

    function test_T17_reentrantWallet_claimPending_attacksAreBlocked_swallowed() public {
        ReentrantWallet atk = new ReentrantWallet(escrow);
        // đơn phụ để kẻ tấn công thử rút/hủy khi đang bị gọi lại
        SlopeeEscrowMaster.Quote memory other = _depositToken(AMOUNT, FEE_BPS);
        _deliver(other.orderId);

        SlopeeEscrowMaster.Quote memory q = _depositEthTo(address(atk), 1 ether);
        _deliver(q.orderId);
        vm.prank(buyer);
        escrow.earlyRelease(q.orderId); // ví từ chối ⇒ ghi sổ chờ rút
        uint256 pending = escrow.pendingWithdrawals(address(0), address(atk));
        assertGt(pending, 0);

        atk.arm(other.orderId, false); // nuốt lỗi: lần rút vẫn thành công, nhưng chỉ một lần
        atk.exec(address(escrow), abi.encodeWithSelector(escrow.claimPending.selector, address(0)));

        assertEq(atk.attempts(), 4);
        assertEq(atk.blocked(), 4, unicode"mọi đòn gọi lại phải bị ReentrancyGuard chặn");
        assertEq(atk.succeeded(), 0);
        assertEq(address(atk).balance, pending, unicode"chỉ được rút đúng một lần");
        assertEq(escrow.pendingWithdrawals(address(0), address(atk)), 0);
        assertEq(address(escrow).balance, 0);
        assertEq(uint8(_state(other.orderId)), uint8(SlopeeEscrowMaster.OrderState.DELIVERED)); // đơn phụ không bị đụng tới
    }

    function test_T17_reentrantWallet_bubbledRevert_keepsPendingBalance() public {
        ReentrantWallet atk = new ReentrantWallet(escrow);
        SlopeeEscrowMaster.Quote memory q = _depositEthTo(address(atk), 1 ether);
        _deliver(q.orderId);
        vm.prank(buyer);
        escrow.earlyRelease(q.orderId);
        uint256 pending = escrow.pendingWithdrawals(address(0), address(atk));

        atk.arm(q.orderId, true); // đòn bị chặn ⇒ ví tự revert ⇒ cả lần rút thất bại
        vm.expectRevert("ETH transfer failed");
        atk.exec(address(escrow), abi.encodeWithSelector(escrow.claimPending.selector, address(0)));

        assertEq(escrow.pendingWithdrawals(address(0), address(atk)), pending, unicode"số dư chờ rút không được mất");
        assertEq(address(escrow).balance, pending);
    }

    function test_T17_evilToken_reentersDuringDeposit_isBlocked() public {
        EvilToken evil = new EvilToken();
        evil.mint(buyer, AMOUNT);
        vm.prank(buyer);
        evil.approve(address(escrow), AMOUNT);

        // Trong lúc nạp, token cố nạp thêm một đơn khác và rút/hủy
        SlopeeEscrowMaster.Quote memory q2 = _quote(address(evil), AMOUNT);
        bytes memory sig2 = _signQuote(q2);
        bytes[] memory calls = new bytes[](3);
        calls[0] = abi.encodeWithSelector(escrow.depositEscrow.selector, q2, sig2);
        calls[1] = abi.encodeWithSelector(escrow.claimPending.selector, address(evil));
        calls[2] = abi.encodeWithSelector(escrow.cancelIfUnfulfilled.selector, q2.orderId);
        evil.arm(address(escrow), calls);

        SlopeeEscrowMaster.Quote memory q = _quote(address(evil), AMOUNT);
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        escrow.depositEscrow(q, sig);

        assertEq(evil.attempts(), 3);
        assertEq(evil.blocked(), 3);
        assertEq(evil.succeeded(), 0);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
        assertEq(uint8(_state(q2.orderId)), uint8(SlopeeEscrowMaster.OrderState.NONE));
        assertEq(evil.balanceOf(address(escrow)), AMOUNT);
    }

    function test_T17_evilToken_reentersDuringPayout_isBlocked() public {
        EvilToken evil = new EvilToken();
        evil.mint(buyer, 2 * AMOUNT);
        vm.prank(buyer);
        evil.approve(address(escrow), type(uint256).max);

        SlopeeEscrowMaster.Quote memory a = _quote(address(evil), AMOUNT);
        bytes memory sigA = _signQuote(a);
        SlopeeEscrowMaster.Quote memory b = _quote(address(evil), AMOUNT);
        bytes memory sigB = _signQuote(b);
        vm.startPrank(buyer);
        escrow.depositEscrow(a, sigA);
        escrow.depositEscrow(b, sigB);
        vm.stopPrank();
        _deliver(a.orderId);
        _deliver(b.orderId);
        vm.warp(block.timestamp + INSPECTION); // đơn B đã hết hạn kiểm tra: ai cũng giải ngân được

        // Khi đơn A giải ngân, token cố giải ngân đơn B (hợp lệ nếu không có khóa) và rút khoản chờ
        bytes[] memory calls = new bytes[](2);
        calls[0] = abi.encodeWithSelector(escrow.releaseAfterInspection.selector, b.orderId);
        calls[1] = abi.encodeWithSelector(escrow.claimPending.selector, address(evil));
        evil.arm(address(escrow), calls);

        vm.prank(buyer);
        escrow.earlyRelease(a.orderId);

        assertEq(evil.blocked(), 2);
        assertEq(evil.succeeded(), 0);
        assertEq(uint8(_state(a.orderId)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
        assertEq(uint8(_state(b.orderId)), uint8(SlopeeEscrowMaster.OrderState.DELIVERED), unicode"đơn B không bị giải ngân chen ngang");

        escrow.releaseAfterInspection(b.orderId); // sau đó vẫn giải ngân bình thường
        assertEq(uint8(_state(b.orderId)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
        assertEq(evil.balanceOf(address(escrow)), 0);
    }

    function test_T17_evilToken_reentersDuringDisputeSettlement_isBlocked() public {
        EvilToken evil = new EvilToken();
        evil.mint(buyer, 2 * AMOUNT);
        vm.prank(buyer);
        evil.approve(address(escrow), type(uint256).max);

        SlopeeEscrowMaster.Quote memory a = _quote(address(evil), AMOUNT);
        bytes memory sigA = _signQuote(a);
        SlopeeEscrowMaster.Quote memory b = _quote(address(evil), AMOUNT);
        bytes memory sigB = _signQuote(b);
        vm.startPrank(buyer);
        escrow.depositEscrow(a, sigA);
        escrow.depositEscrow(b, sigB);
        vm.stopPrank();
        _deliver(a.orderId);
        _deliver(b.orderId);
        vm.prank(buyer);
        escrow.raiseDispute(a.orderId); // đơn A tranh chấp
        vm.prank(buyer);
        escrow.raiseDispute(b.orderId); // đơn B cũng tranh chấp

        uint256 at = _disputedAt(a.orderId);
        vm.warp(at + DISPUTE_TIMEOUT);

        // Khi đơn A được Trọng tài xử, token cố xử luôn đơn B trước khi A chuyển xong
        bytes[] memory calls = new bytes[](2);
        calls[0] = abi.encodeWithSelector(escrow.arbitratorForceResolve.selector, b.orderId, buyer);
        calls[1] = abi.encodeWithSelector(escrow.resolveDispute.selector, b.orderId, buyer, at + 1 days, "", "");
        evil.arm(address(escrow), calls);

        vm.prank(arbitrator);
        escrow.arbitratorForceResolve(a.orderId, merchant);

        assertEq(evil.attempts(), 2);
        // Lời gọi đầu mang msg.sender = token (không có ARBITRATOR_ROLE) nên có thể bị chặn bởi quyền thay vì khóa tái nhập;
        // điều cần chứng minh là KHÔNG lời gọi nào thành công và đơn B không bị đụng tới.
        assertEq(evil.succeeded(), 0);
        assertEq(uint8(_state(a.orderId)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
        assertEq(uint8(_state(b.orderId)), uint8(SlopeeEscrowMaster.OrderState.DISPUTED));
        assertEq(evil.balanceOf(address(escrow)), AMOUNT); // còn đúng khoản của đơn B
    }

    // ================================================================== Nạp token đặc biệt (T-03 mở rộng)

    function test_T03_feeOnTransferToken_rejected() public {
        FeeOnTransferToken fot = new FeeOnTransferToken();
        fot.mint(buyer, AMOUNT);
        vm.prank(buyer);
        fot.approve(address(escrow), AMOUNT);
        SlopeeEscrowMaster.Quote memory q = _quote(address(fot), AMOUNT);
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Fee-on-transfer unsupported");
        escrow.depositEscrow(q, sig);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.NONE));
    }
}
