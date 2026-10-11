// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./EscrowBase.t.sol";

/// @dev Ví Merchant từ chối nhận ETH — dùng cho kiểm thử sổ chờ rút (T-16, phần ghi sổ).
contract RejectingWallet {
    receive() external payable { revert("no ETH"); }
}

/// @notice Test tuần 1: nạp đơn có báo giá, giao hàng, giải ngân, hủy quá hạn.
///         Mã T-xx theo SRS mục 12.1 / PROGRESS.md mục 5.1.
contract SlopeeEscrowWeek1Test is EscrowBase {
    // ------------------------------------------------------------------ T-01
    function test_T01_depositToken_validQuote_locksOrder() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _signQuote(q);

        vm.expectEmit(true, true, true, true, address(escrow));
        emit OrderCreated(
            q.orderId, buyer, merchant, address(usd), AMOUNT, INSPECTION, DISPUTE_TIMEOUT, DOC_HASH, FEE_BPS
        );
        vm.prank(buyer);
        escrow.depositEscrow(q, sig);

        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
        assertEq(usd.balanceOf(address(escrow)), AMOUNT);
        assertEq(usd.balanceOf(buyer), 1_000_000_000 - AMOUNT);
        (address b, address m, address t, uint256 amt, uint256 createdAt,,,,,uint256 fee,, bytes32 doc) = escrow.orders(q.orderId);
        assertEq(b, buyer);
        assertEq(m, merchant);
        assertEq(t, address(usd));
        assertEq(amt, AMOUNT);
        assertEq(createdAt, block.timestamp);
        assertEq(fee, FEE_BPS);
        assertEq(doc, DOC_HASH);
    }

    function test_T01_depositEth_validQuote_locksOrder() public {
        SlopeeEscrowMaster.Quote memory q = _depositEth(1 ether);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
        assertEq(address(escrow).balance, 1 ether);
    }

    // ------------------------------------------------------------------ T-02
    function test_T02_expiredQuote_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _signQuote(q);
        vm.warp(q.deadline + 1);
        vm.prank(buyer);
        vm.expectRevert("Quote expired");
        escrow.depositEscrow(q, sig);
    }

    function test_T02_quoteAtExactDeadline_isAccepted() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _signQuote(q);
        vm.warp(q.deadline);
        vm.prank(buyer);
        escrow.depositEscrow(q, sig);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
    }

    function test_T02_wrongCaller_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _signQuote(q);
        address stranger = makeAddr("stranger");
        usd.mint(stranger, AMOUNT);
        vm.prank(stranger);
        usd.approve(address(escrow), AMOUNT);
        vm.prank(stranger);
        vm.expectRevert("Caller must be quote buyer");
        escrow.depositEscrow(q, sig);
    }

    function test_T02_signatureFromNonSigner_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _sign(MERCHANT_KEY, _quoteDigest(q)); // người ký không có QUOTE_SIGNER_ROLE
        vm.prank(buyer);
        vm.expectRevert("Bad quote signature");
        escrow.depositEscrow(q, sig);
    }

    function test_T02_tamperedQuote_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _signQuote(q);
        q.amount = AMOUNT - 1; // sửa số tiền sau khi ký → khôi phục ra địa chỉ lạ
        vm.prank(buyer);
        vm.expectRevert("Bad quote signature");
        escrow.depositEscrow(q, sig);
    }

    function test_T02_signerRoleRevoked_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _signQuote(q);
        bytes32 role = escrow.QUOTE_SIGNER_ROLE();
        vm.prank(admin);
        escrow.revokeRole(role, signer);
        vm.prank(buyer);
        vm.expectRevert("Bad quote signature");
        escrow.depositEscrow(q, sig);
    }

    // ------------------------------------------------------------------ T-03
    function test_T03_duplicateOrderId_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Order exists");
        escrow.depositEscrow(q, sig);
        assertEq(usd.balanceOf(address(escrow)), AMOUNT); // không thu tiền lần hai
    }

    function test_T03_ethValueMismatch_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(0), 1 ether);
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Wrong ETH value");
        escrow.depositEscrow{value: 1 ether - 1}(q, sig);
    }

    function test_T03_tokenDepositWithEth_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Do not send ETH for token");
        escrow.depositEscrow{value: 1 wei}(q, sig);
    }

    function test_T03_insufficientAllowance_reverts() public {
        vm.prank(buyer);
        usd.approve(address(escrow), AMOUNT - 1);
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert(); // ERC20InsufficientAllowance (custom error của OZ v5)
        escrow.depositEscrow(q, sig);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.NONE)); // giao dịch revert, không ghi đơn
    }

    function test_T03_zeroAmount_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), 0);
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Zero amount");
        escrow.depositEscrow(q, sig);
    }

    // ------------------------------------------------------------------ T-04
    function test_T04_merchantEqualsBuyer_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        q.merchant = buyer;
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Invalid merchant");
        escrow.depositEscrow(q, sig);
    }

    function test_T04_merchantZeroAddress_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        q.merchant = address(0);
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Invalid merchant");
        escrow.depositEscrow(q, sig);
    }

    function test_T04_arbitratorAsMerchant_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        q.merchant = arbitrator;
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Arbitrator cannot trade");
        escrow.depositEscrow(q, sig);
    }

    function test_T04_arbitratorAsBuyer_reverts() public {
        usd.mint(arbitrator, AMOUNT);
        vm.prank(arbitrator);
        usd.approve(address(escrow), AMOUNT);
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        q.buyer = arbitrator;
        bytes memory sig = _signQuote(q);
        vm.prank(arbitrator);
        vm.expectRevert("Arbitrator cannot trade");
        escrow.depositEscrow(q, sig);
    }

    function test_T04_inspectionDurationOutOfRange_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        q.inspectionDuration = 1 hours - 1;
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Invalid duration");
        escrow.depositEscrow(q, sig);

        q = _quote(address(usd), AMOUNT);
        q.inspectionDuration = 30 days + 1;
        sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Invalid duration");
        escrow.depositEscrow(q, sig);
    }

    function test_T04_inspectionDurationBoundaries_accepted() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        q.inspectionDuration = 1 hours;
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        escrow.depositEscrow(q, sig);

        q = _quote(address(usd), AMOUNT);
        q.inspectionDuration = 30 days;
        sig = _signQuote(q);
        vm.prank(buyer);
        escrow.depositEscrow(q, sig);
    }

    // ------------------------------------------------------------------ T-20 (phần nạp tiền)
    function test_T20_disputeTimeoutBounds() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        q.disputeTimeout = 7 days - 1;
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Invalid dispute timeout");
        escrow.depositEscrow(q, sig);

        q = _quote(address(usd), AMOUNT);
        q.disputeTimeout = 90 days + 1;
        sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Invalid dispute timeout");
        escrow.depositEscrow(q, sig);

        q = _quote(address(usd), AMOUNT);
        q.disputeTimeout = 7 days;
        sig = _signQuote(q);
        vm.prank(buyer);
        escrow.depositEscrow(q, sig);

        q = _quote(address(usd), AMOUNT);
        q.disputeTimeout = 90 days;
        sig = _signQuote(q);
        vm.prank(buyer);
        escrow.depositEscrow(q, sig);
    }

    // ------------------------------------------------------------------ T-22 (phần trần phí), T-23
    function test_T22_feeAboveCap_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        q.feeBps = escrow.defaultFeeBps() + 1;
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Fee exceeds on-chain cap");
        escrow.depositEscrow(q, sig);
    }

    function test_T23_quoteBuyerDifferentFromCaller_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        q.buyer = makeAddr("someoneElse");
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        vm.expectRevert("Caller must be quote buyer");
        escrow.depositEscrow(q, sig);
    }

    // ------------------------------------------------------------------ T-05
    function test_T05_confirmDelivery_onlyShipperRole() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        bytes32 role = escrow.SHIPPER_ROLE();
        for (uint256 i = 0; i < 3; i++) {
            address caller = i == 0 ? buyer : (i == 1 ? merchant : admin);
            vm.prank(caller);
            vm.expectRevert(abi.encodeWithSignature("AccessControlUnauthorizedAccount(address,bytes32)", caller, role));
            escrow.confirmDelivery(q.orderId);
        }
    }

    function test_T05_confirmDelivery_notLocked_reverts() public {
        vm.prank(shipper);
        vm.expectRevert("Not locked"); // đơn chưa tồn tại (NONE)
        escrow.confirmDelivery(999);

        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.prank(shipper);
        escrow.confirmDelivery(q.orderId);
        vm.prank(shipper);
        vm.expectRevert("Not locked"); // đã DELIVERED
        escrow.confirmDelivery(q.orderId);
    }

    function test_T05_confirmDelivery_setsDeliveredAndEmits() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.warp(block.timestamp + 1 days);
        vm.expectEmit(true, false, false, true, address(escrow));
        emit OrderDelivered(q.orderId, block.timestamp);
        vm.prank(shipper);
        escrow.confirmDelivery(q.orderId);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.DELIVERED));
        (,,,,, uint256 deliveredAt,,,,,,) = escrow.orders(q.orderId);
        assertEq(deliveredAt, block.timestamp);
    }

    // ------------------------------------------------------------------ T-06
    function test_T06_earlyRelease_buyerPaysMerchantAndFee() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.prank(shipper);
        escrow.confirmDelivery(q.orderId);

        uint256 fee = (AMOUNT * FEE_BPS) / 10000;
        vm.expectEmit(true, false, false, true, address(escrow));
        emit OrderCompleted(q.orderId, AMOUNT - fee, fee);
        vm.prank(buyer);
        escrow.earlyRelease(q.orderId);

        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
        assertEq(usd.balanceOf(merchant), AMOUNT - fee);
        assertEq(usd.balanceOf(feeRecipient), fee);
        assertEq(usd.balanceOf(address(escrow)), 0);
    }

    function test_T06_earlyRelease_byNonBuyer_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.prank(shipper);
        escrow.confirmDelivery(q.orderId);
        address[3] memory callers = [merchant, shipper, admin];
        for (uint256 i = 0; i < callers.length; i++) {
            vm.prank(callers[i]);
            vm.expectRevert("Only buyer");
            escrow.earlyRelease(q.orderId);
        }
    }

    function test_T06_earlyRelease_beforeDelivery_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.prank(buyer);
        vm.expectRevert("Not delivered");
        escrow.earlyRelease(q.orderId);
    }

    function test_T06_earlyRelease_twice_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.prank(shipper);
        escrow.confirmDelivery(q.orderId);
        vm.prank(buyer);
        escrow.earlyRelease(q.orderId);
        vm.prank(buyer);
        vm.expectRevert("Not delivered"); // COMPLETED là trạng thái cuối
        escrow.earlyRelease(q.orderId);
    }

    // ------------------------------------------------------------------ T-07
    function test_T07_releaseAfterInspection_boundary() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.prank(shipper);
        escrow.confirmDelivery(q.orderId);
        uint256 deliveredAt = block.timestamp;

        vm.warp(deliveredAt + INSPECTION - 1);
        vm.expectRevert("Under inspection");
        escrow.releaseAfterInspection(q.orderId); // trước 1 giây

        vm.warp(deliveredAt + INSPECTION);
        address anyone = makeAddr("anyone");
        vm.prank(anyone); // ai cũng gọi được
        escrow.releaseAfterInspection(q.orderId);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
        assertEq(usd.balanceOf(merchant), AMOUNT - (AMOUNT * FEE_BPS) / 10000);
    }

    function test_T07_releaseAfterInspection_notDelivered_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.warp(block.timestamp + 365 days);
        vm.expectRevert("Not delivered");
        escrow.releaseAfterInspection(q.orderId);
    }

    // ------------------------------------------------------------------ T-08 (chia phí với trần mặc định 300)
    function test_T08_feeSplit_zeroAndCap() public {
        uint16[2] memory fees = [0, 300];
        for (uint256 i = 0; i < fees.length; i++) {
            uint256 amount = 100_000_001; // lẻ để thấy làm tròn xuống
            SlopeeEscrowMaster.Quote memory q = _depositToken(amount, fees[i]);
            vm.prank(shipper);
            escrow.confirmDelivery(q.orderId);

            uint256 mBefore = usd.balanceOf(merchant);
            uint256 fBefore = usd.balanceOf(feeRecipient);
            vm.prank(buyer);
            escrow.earlyRelease(q.orderId);

            uint256 fee = (amount * fees[i]) / 10000;
            assertEq(usd.balanceOf(feeRecipient) - fBefore, fee);
            assertEq(usd.balanceOf(merchant) - mBefore, amount - fee);
        }
    }

    /// @dev INV-03 (phần nạp–giải ngân): net + fee = amount và fee = floor(amount*feeBps/10000).
    function testFuzz_INV03_feeSplitConserved(uint96 amount, uint16 feeBps) public {
        amount = uint96(bound(amount, 1, 500_000_000));
        feeBps = uint16(bound(feeBps, 0, 300));
        usd.mint(buyer, amount); // đủ số dư cho mọi giá trị fuzz
        SlopeeEscrowMaster.Quote memory q = _depositToken(amount, feeBps);
        vm.prank(shipper);
        escrow.confirmDelivery(q.orderId);
        vm.prank(buyer);
        escrow.earlyRelease(q.orderId);

        uint256 fee = (uint256(amount) * feeBps) / 10000;
        assertEq(usd.balanceOf(feeRecipient), fee);
        assertEq(usd.balanceOf(merchant), amount - fee);
        assertEq(usd.balanceOf(address(escrow)), 0);
    }

    // ------------------------------------------------------------------ T-14 (cancelIfUnfulfilled)
    function test_T14_cancelIfUnfulfilled_beforeTimeout_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.warp(block.timestamp + 14 days - 1);
        vm.prank(buyer);
        vm.expectRevert("Timeout not reached");
        escrow.cancelIfUnfulfilled(q.orderId);
    }

    function test_T14_cancelIfUnfulfilled_afterTimeout_buyerRefunded() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.warp(block.timestamp + 14 days);
        vm.expectEmit(true, true, false, true, address(escrow));
        emit OrderRefunded(q.orderId, buyer, AMOUNT);
        vm.prank(buyer);
        escrow.cancelIfUnfulfilled(q.orderId);

        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));
        assertEq(usd.balanceOf(buyer), 1_000_000_000); // hoàn đủ, không trừ phí
        assertEq(usd.balanceOf(address(escrow)), 0);
    }

    function test_T14_cancelIfUnfulfilled_adminAllowed_outsiderRejected() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.warp(block.timestamp + 14 days);

        vm.prank(makeAddr("outsider"));
        vm.expectRevert("Unauthorized");
        escrow.cancelIfUnfulfilled(q.orderId);

        vm.prank(merchant);
        vm.expectRevert("Unauthorized");
        escrow.cancelIfUnfulfilled(q.orderId);

        vm.prank(admin);
        escrow.cancelIfUnfulfilled(q.orderId);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));
        assertEq(usd.balanceOf(buyer), 1_000_000_000); // tiền về Buyer, không về Admin
    }

    function test_T14_cancelIfUnfulfilled_afterDelivery_reverts() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        vm.prank(shipper);
        escrow.confirmDelivery(q.orderId);
        vm.warp(block.timestamp + 30 days);
        vm.prank(buyer);
        vm.expectRevert("Not locked");
        escrow.cancelIfUnfulfilled(q.orderId);
    }

    // ------------------------------------------------------------------ ETH: đường giải ngân
    function test_ETH_fullFlow_paysMerchantAndFee() public {
        SlopeeEscrowMaster.Quote memory q = _depositEth(10 ether);
        vm.prank(shipper);
        escrow.confirmDelivery(q.orderId);

        uint256 mBefore = merchant.balance;
        uint256 fBefore = feeRecipient.balance;
        vm.prank(buyer);
        escrow.earlyRelease(q.orderId);

        uint256 fee = (10 ether * FEE_BPS) / 10000;
        assertEq(merchant.balance - mBefore, 10 ether - fee);
        assertEq(feeRecipient.balance - fBefore, fee);
        assertEq(address(escrow).balance, 0);
    }

    /// @dev Phần ghi sổ của T-16: ví Merchant từ chối ETH không làm kẹt đơn; tiền vào `pendingWithdrawals`.
    ///      (Hàm `claimPending` và phần rút tiền được kiểm thử ở tuần 2.)
    function test_ETH_rejectingMerchant_deferredToPendingWithdrawals() public {
        RejectingWallet bad = new RejectingWallet();
        SlopeeEscrowMaster.Quote memory q = _quote(address(0), 1 ether);
        q.merchant = address(bad);
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        escrow.depositEscrow{value: 1 ether}(q, sig);

        vm.prank(shipper);
        escrow.confirmDelivery(q.orderId);
        vm.prank(buyer);
        escrow.earlyRelease(q.orderId); // không revert

        uint256 fee = (1 ether * FEE_BPS) / 10000;
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
        assertEq(escrow.pendingWithdrawals(address(0), address(bad)), 1 ether - fee);
        // INV-01 (phần ETH): số dư contract = tổng sổ chờ rút
        assertEq(address(escrow).balance, 1 ether - fee);
    }

    // ------------------------------------------------------------------ Hằng số / domain
    function test_constants_matchSpec() public view {
        assertEq(escrow.DELIVERY_TIMEOUT(), 14 days);
        assertEq(escrow.MIN_DISPUTE_TIMEOUT(), 7 days);
        assertEq(escrow.MAX_DISPUTE_TIMEOUT(), 90 days);
        assertEq(escrow.MAX_FEE_BPS(), 1000);
        assertEq(escrow.MAX_BATCH_SIZE(), 5);
        assertEq(escrow.defaultFeeBps(), 300);
        assertEq(escrow.feeRecipient(), feeRecipient);
        assertTrue(escrow.hasRole(escrow.DEFAULT_ADMIN_ROLE(), admin));
        assertTrue(escrow.hasRole(escrow.SHIPPER_ROLE(), shipper));
        assertTrue(escrow.hasRole(escrow.ARBITRATOR_ROLE(), arbitrator));
        assertTrue(escrow.hasRole(escrow.QUOTE_SIGNER_ROLE(), signer));
    }

    function test_mockUSD_has6Decimals() public view {
        assertEq(usd.decimals(), 6);
    }
}
