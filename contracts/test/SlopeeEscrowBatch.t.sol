// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./EscrowBase.t.sol";
import "./TestActors.sol";
import {console2} from "forge-std/console2.sol";

/// @notice Test nạp gom `depositEscrowBatch` (BR-11): T-25 … T-32 và T-34. T-33 (fuzz/invariant) ở `SlopeeEscrowInvariant.t.sol`.
contract SlopeeEscrowBatchTest is EscrowBase {
    function setUp() public override {
        super.setUp();
        vm.deal(address(this), 100 ether);
    }

    // ------------------------------------------------------------------ Helpers cục bộ

    function _states(SlopeeEscrowMaster.Quote[] memory qs) internal view returns (uint8[] memory st) {
        st = new uint8[](qs.length);
        for (uint256 i = 0; i < qs.length; i++) st[i] = uint8(_state(qs[i].orderId));
    }

    function _total(SlopeeEscrowMaster.Quote[] memory qs) internal pure returns (uint256 t) {
        for (uint256 i = 0; i < qs.length; i++) t += qs[i].amount;
    }

    function _assertNoneCreated(SlopeeEscrowMaster.Quote[] memory qs) internal view {
        for (uint256 i = 0; i < qs.length; i++) {
            assertEq(uint8(_state(qs[i].orderId)), uint8(SlopeeEscrowMaster.OrderState.NONE), unicode"không đơn nào được tạo");
        }
    }

    function _resign(SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs, uint256 i) internal view {
        sigs[i] = _signQuote(qs[i]);
    }

    function _depositBatchAsBuyer(SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) internal {
        vm.prank(buyer);
        escrow.depositEscrowBatch(qs, sigs);
    }

    // ================================================================== T-25

    function test_T25_batchOf3_singleTransferFrom_threeEvents_independentTerms() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 3, AMOUNT);
        // mỗi đơn có phí, thời hạn kiểm tra và tranh chấp riêng
        uint16[3] memory fees = [uint16(0), 100, 300];
        uint256[3] memory insp = [uint256(1 hours), 3 days, 30 days];
        uint256[3] memory tmo = [uint256(7 days), 30 days, 90 days];
        for (uint256 i = 0; i < 3; i++) {
            qs[i].feeBps = fees[i];
            qs[i].inspectionDuration = insp[i];
            qs[i].disputeTimeout = tmo[i];
            sigs[i] = _signQuote(qs[i]);
        }
        uint256 total = _total(qs);
        uint256 buyerBefore = usd.balanceOf(buyer);

        // đúng MỘT lần transferFrom (bất kỳ tham số nào) và đúng tổng tiền
        vm.expectCall(address(usd), abi.encodeWithSelector(usd.transferFrom.selector), 1);
        vm.expectCall(address(usd), abi.encodeWithSelector(usd.transferFrom.selector, buyer, address(escrow), total), 1);
        for (uint256 i = 0; i < 3; i++) {
            vm.expectEmit(true, true, true, true, address(escrow));
            emit OrderCreated(qs[i].orderId, buyer, qs[i].merchant, address(usd), qs[i].amount, insp[i], tmo[i], DOC_HASH, fees[i]);
        }
        _depositBatchAsBuyer(qs, sigs);

        assertEq(usd.balanceOf(address(escrow)), total);
        assertEq(buyerBefore - usd.balanceOf(buyer), total);
        for (uint256 i = 0; i < 3; i++) {
            assertEq(uint8(_state(qs[i].orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
            (address b, address m,, uint256 amt,,,, uint256 t, uint256 ins, uint256 fee,,) = escrow.orders(qs[i].orderId);
            assertEq(b, buyer);
            assertEq(m, qs[i].merchant);
            assertEq(amt, qs[i].amount);
            assertEq(t, tmo[i]);
            assertEq(ins, insp[i]);
            assertEq(fee, fees[i]);
        }
    }

    function test_T25_batchOfEth_collectsExactMsgValue() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(0), 3, 1 ether);
        uint256 total = _total(qs);
        vm.prank(buyer);
        escrow.depositEscrowBatch{value: total}(qs, sigs);
        assertEq(address(escrow).balance, total);
        for (uint256 i = 0; i < 3; i++) {
            assertEq(uint8(_state(qs[i].orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
        }
    }

    // ================================================================== T-26

    function test_T26_emptyBatch_reverts() public {
        SlopeeEscrowMaster.Quote[] memory qs = new SlopeeEscrowMaster.Quote[](0);
        bytes[] memory sigs = new bytes[](0);
        vm.prank(buyer);
        vm.expectRevert("Invalid batch size");
        escrow.depositEscrowBatch(qs, sigs);
    }

    function test_T26_moreThanFive_reverts_exactlyFiveOk() public {
        (SlopeeEscrowMaster.Quote[] memory six, bytes[] memory sixSigs) = _batch(address(usd), 6, AMOUNT);
        vm.prank(buyer);
        vm.expectRevert("Invalid batch size");
        escrow.depositEscrowBatch(six, sixSigs);
        _assertNoneCreated(six);

        (SlopeeEscrowMaster.Quote[] memory five, bytes[] memory fiveSigs) = _batch(address(usd), 5, AMOUNT);
        _depositBatchAsBuyer(five, fiveSigs);
        assertEq(uint8(_state(five[4].orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
    }

    function test_T26_lengthMismatch_reverts() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 3, AMOUNT);
        bytes[] memory fewer = new bytes[](2);
        fewer[0] = sigs[0];
        fewer[1] = sigs[1];
        vm.prank(buyer);
        vm.expectRevert("Length mismatch");
        escrow.depositEscrowBatch(qs, fewer);

        bytes[] memory more = new bytes[](4);
        more[0] = sigs[0];
        more[1] = sigs[1];
        more[2] = sigs[2];
        more[3] = sigs[2];
        vm.prank(buyer);
        vm.expectRevert("Length mismatch");
        escrow.depositEscrowBatch(qs, more);
        _assertNoneCreated(qs);
    }

    // ================================================================== T-27

    function test_T27_duplicateOrderIdInsideBatch_reverts_balancesUnchanged() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 3, AMOUNT);
        qs[2].orderId = qs[0].orderId; // hai báo giá cùng mã đơn
        qs[2].merchant = makeAddr("anotherShop");
        sigs[2] = _signQuote(qs[2]);
        uint256 buyerBefore = usd.balanceOf(buyer);

        vm.prank(buyer);
        vm.expectRevert("Order exists");
        escrow.depositEscrowBatch(qs, sigs);

        assertEq(usd.balanceOf(buyer), buyerBefore);
        assertEq(usd.balanceOf(address(escrow)), 0);
        _assertNoneCreated(qs);
    }

    function test_T27_batchContainingAlreadyUsedOrderId_reverts() public {
        SlopeeEscrowMaster.Quote memory used = _depositToken(AMOUNT, FEE_BPS);
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 2, AMOUNT);
        qs[1].orderId = used.orderId;
        sigs[1] = _signQuote(qs[1]);
        vm.prank(buyer);
        vm.expectRevert("Order exists");
        escrow.depositEscrowBatch(qs, sigs);
        assertEq(usd.balanceOf(address(escrow)), AMOUNT); // chỉ còn tiền của đơn nạp trước đó
        assertEq(uint8(_state(qs[0].orderId)), uint8(SlopeeEscrowMaster.OrderState.NONE));
    }

    // ================================================================== T-28 (một báo giá xấu làm cả lô revert)

    function _badQuoteAt(uint256 badIndex, uint256 kind) internal returns (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs, string memory reason) {
        (qs, sigs) = _batch(address(usd), 3, AMOUNT);
        if (kind == 0) {
            qs[badIndex].deadline = block.timestamp - 1; // hết hạn
            sigs[badIndex] = _signQuote(qs[badIndex]);
            reason = "Quote expired";
        } else if (kind == 1) {
            sigs[badIndex] = _sign(MERCHANT_KEY, _quoteDigest(qs[badIndex])); // sai người ký
            reason = "Bad quote signature";
        } else if (kind == 2) {
            qs[badIndex].feeBps = 301; // vượt trần 300
            sigs[badIndex] = _signQuote(qs[badIndex]);
            reason = "Fee exceeds on-chain cap";
        } else {
            qs[badIndex].buyer = makeAddr("someoneElse"); // buyer khác người gửi
            sigs[badIndex] = _signQuote(qs[badIndex]);
            reason = "Caller must be quote buyer";
        }
    }

    function test_T28_oneBadQuote_revertsWholeBatch() public {
        for (uint256 kind = 0; kind < 4; kind++) {
            for (uint256 idx = 0; idx < 3; idx++) {
                (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs, string memory reason) = _badQuoteAt(idx, kind);
                uint256 buyerBefore = usd.balanceOf(buyer);
                vm.prank(buyer);
                vm.expectRevert(bytes(reason));
                escrow.depositEscrowBatch(qs, sigs);
                assertEq(usd.balanceOf(buyer), buyerBefore);
                assertEq(usd.balanceOf(address(escrow)), 0);
                _assertNoneCreated(qs);
            }
        }
    }

    function test_T28_adminLowersCeilingBetweenSigningAndDeposit_wholeBatchRejected() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 3, AMOUNT);
        vm.prank(admin);
        escrow.setDefaultFeeBps(100);
        vm.prank(buyer);
        vm.expectRevert("Fee exceeds on-chain cap");
        escrow.depositEscrowBatch(qs, sigs); // cả lô cần được cấp lại báo giá (SDD 4.9)
        _assertNoneCreated(qs);
    }

    function test_T28_missingAllowance_revertsAndLeavesNoOrders() public {
        vm.prank(buyer);
        usd.approve(address(escrow), 0);
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 2, AMOUNT);
        vm.prank(buyer);
        vm.expectRevert(); // ERC20InsufficientAllowance
        escrow.depositEscrowBatch(qs, sigs);
        _assertNoneCreated(qs);
    }

    // ================================================================== T-29

    function test_T29_mixedTokens_reverts() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 3, AMOUNT);
        qs[1].token = address(0);
        sigs[1] = _signQuote(qs[1]);
        vm.prank(buyer);
        vm.expectRevert("Mixed tokens unsupported");
        escrow.depositEscrowBatch{value: 1 ether}(qs, sigs);
        _assertNoneCreated(qs);

        // thứ tự ngược lại (phần tử đầu là ETH)
        (qs, sigs) = _batch(address(0), 2, 1 ether);
        qs[1].token = address(usd);
        sigs[1] = _signQuote(qs[1]);
        vm.prank(buyer);
        vm.expectRevert("Mixed tokens unsupported");
        escrow.depositEscrowBatch{value: 2 ether}(qs, sigs);
    }

    function test_T29_ethBatch_wrongMsgValue_reverts() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(0), 3, 1 ether);
        uint256 total = _total(qs);
        uint256[3] memory bad = [total - 1, total + 1, uint256(0)];
        for (uint256 i = 0; i < bad.length; i++) {
            vm.prank(buyer);
            vm.expectRevert("Wrong ETH value");
            escrow.depositEscrowBatch{value: bad[i]}(qs, sigs);
        }
        _assertNoneCreated(qs);
        assertEq(address(escrow).balance, 0);
    }

    function test_T29_tokenBatch_withEth_reverts() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 2, AMOUNT);
        vm.prank(buyer);
        vm.expectRevert("Do not send ETH for token");
        escrow.depositEscrowBatch{value: 1 wei}(qs, sigs);
        _assertNoneCreated(qs);
    }

    function test_T29_feeOnTransferToken_batchRejected() public {
        FeeOnTransferToken fot = new FeeOnTransferToken();
        fot.mint(buyer, 10 * AMOUNT);
        vm.prank(buyer);
        fot.approve(address(escrow), type(uint256).max);
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(fot), 2, AMOUNT);
        vm.prank(buyer);
        vm.expectRevert("Fee-on-transfer unsupported");
        escrow.depositEscrowBatch(qs, sigs);
        _assertNoneCreated(qs);
    }

    // ================================================================== T-30 (mọi kiểm tra của depositEscrow áp dụng cho từng phần tử)

    function _mutateMiddle(uint256 kind) internal returns (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs, string memory reason) {
        (qs, sigs) = _batch(address(usd), 3, AMOUNT);
        SlopeeEscrowMaster.Quote memory m = qs[1];
        if (kind == 0) { m.amount = 0; reason = "Zero amount"; }
        else if (kind == 1) { m.merchant = buyer; reason = "Invalid merchant"; }
        else if (kind == 2) { m.merchant = address(0); reason = "Invalid merchant"; }
        else if (kind == 3) { m.merchant = arbitrator; reason = "Arbitrator cannot trade"; }
        else if (kind == 4) { m.inspectionDuration = 1 hours - 1; reason = "Invalid duration"; }
        else if (kind == 5) { m.inspectionDuration = 30 days + 1; reason = "Invalid duration"; }
        else if (kind == 6) { m.disputeTimeout = 7 days - 1; reason = "Invalid dispute timeout"; }
        else { m.disputeTimeout = 90 days + 1; reason = "Invalid dispute timeout"; }
        qs[1] = m;
        sigs[1] = _signQuote(m);
    }

    function test_T30_everySingleDepositCheck_appliesToBatchElements() public {
        for (uint256 kind = 0; kind < 8; kind++) {
            (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs, string memory reason) = _mutateMiddle(kind);
            vm.prank(buyer);
            vm.expectRevert(bytes(reason));
            escrow.depositEscrowBatch(qs, sigs);
            _assertNoneCreated(qs);
        }
    }

    function test_T30_arbitratorAsBuyer_inBatch_reverts() public {
        usd.mint(arbitrator, 10 * AMOUNT);
        vm.prank(arbitrator);
        usd.approve(address(escrow), type(uint256).max);
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 2, AMOUNT);
        for (uint256 i = 0; i < 2; i++) {
            qs[i].buyer = arbitrator;
            sigs[i] = _signQuote(qs[i]);
        }
        vm.prank(arbitrator);
        vm.expectRevert("Arbitrator cannot trade");
        escrow.depositEscrowBatch(qs, sigs);
    }

    function test_T30_durationBoundsAreInclusive_inBatch() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 4, AMOUNT);
        qs[0].inspectionDuration = 1 hours;
        qs[1].inspectionDuration = 30 days;
        qs[2].disputeTimeout = 7 days;
        qs[3].disputeTimeout = 90 days;
        for (uint256 i = 0; i < 4; i++) sigs[i] = _signQuote(qs[i]);
        _depositBatchAsBuyer(qs, sigs);
        for (uint256 i = 0; i < 4; i++) {
            assertEq(uint8(_state(qs[i].orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
        }
    }

    // ================================================================== T-31 (độc lập sau khi nạp)

    function test_T31_ordersInBatch_settleIndependently() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 3, AMOUNT);
        qs[0].feeBps = 0;
        qs[1].feeBps = 100;
        qs[2].feeBps = 300;
        qs[2].inspectionDuration = 1 days;
        for (uint256 i = 0; i < 3; i++) sigs[i] = _signQuote(qs[i]);
        _depositBatchAsBuyer(qs, sigs);
        uint256 idA = qs[0].orderId;
        uint256 idB = qs[1].orderId;
        uint256 idC = qs[2].orderId;
        uint256 amtA = qs[0].amount;
        uint256 amtB = qs[1].amount;
        uint256 amtC = qs[2].amount;
        uint256 buyerBefore = usd.balanceOf(buyer);

        // A: mở khóa sớm (phí 0)
        _deliver(idA);
        vm.prank(buyer);
        escrow.earlyRelease(idA);
        assertEq(usd.balanceOf(qs[0].merchant), amtA);
        assertEq(uint8(_state(idB)), uint8(SlopeeEscrowMaster.OrderState.LOCKED), unicode"B không bị ảnh hưởng");
        assertEq(uint8(_state(idC)), uint8(SlopeeEscrowMaster.OrderState.LOCKED), unicode"C không bị ảnh hưởng");

        // B: giao, khiếu nại, Trọng tài + Buyer ký hoàn tiền (không trừ phí)
        _deliver(idB);
        vm.prank(buyer);
        escrow.raiseDispute(idB);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, idB, buyer, amtB, deadline);
        escrow.resolveDispute(idB, buyer, deadline, s1, s2);
        assertEq(usd.balanceOf(buyer) - buyerBefore, amtB);
        assertEq(usd.balanceOf(qs[1].merchant), 0);

        // C: giao, hết hạn kiểm tra thì ai cũng giải ngân được (phí 3%)
        _deliver(idC);
        vm.warp(block.timestamp + 1 days);
        escrow.releaseAfterInspection(idC);
        uint256 feeC = (amtC * 300) / 10000;
        assertEq(usd.balanceOf(qs[2].merchant), amtC - feeC);
        assertEq(usd.balanceOf(feeRecipient), feeC); // A phí 0, B hoàn tiền không phí

        assertEq(uint8(_state(idA)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
        assertEq(uint8(_state(idB)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));
        assertEq(uint8(_state(idC)), uint8(SlopeeEscrowMaster.OrderState.COMPLETED));
        assertEq(usd.balanceOf(address(escrow)), 0);
    }

    function test_T31_oneOrderTimingOut_doesNotAffectSiblings() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 2, AMOUNT);
        _depositBatchAsBuyer(qs, sigs);
        vm.warp(block.timestamp + 14 days);
        vm.prank(buyer);
        escrow.cancelIfUnfulfilled(qs[0].orderId); // chỉ hủy đơn 0
        assertEq(uint8(_state(qs[0].orderId)), uint8(SlopeeEscrowMaster.OrderState.REFUNDED));
        assertEq(uint8(_state(qs[1].orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
        assertEq(usd.balanceOf(address(escrow)), qs[1].amount);
    }

    // ================================================================== T-32 (gas)

    function test_T32_batchOfFive_succeeds_andGasUnderTarget() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(usd), 5, AMOUNT);
        uint256 g = gasleft();
        _depositBatchAsBuyer(qs, sigs);
        g -= gasleft();
        console2.log("gas depositEscrowBatch (5 don, token):", g);
        assertLt(g, 3_000_000, "muc tieu < 3.000.000 gas");
        for (uint256 i = 0; i < 5; i++) {
            assertEq(uint8(_state(qs[i].orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
        }
    }

    function test_T32_batchOfFiveEth_gasUnderTarget() public {
        (SlopeeEscrowMaster.Quote[] memory qs, bytes[] memory sigs) = _batch(address(0), 5, 1 ether);
        uint256 total = _total(qs);
        uint256 g = gasleft();
        vm.prank(buyer);
        escrow.depositEscrowBatch{value: total}(qs, sigs);
        g -= gasleft();
        console2.log("gas depositEscrowBatch (5 don, ETH):", g);
        assertLt(g, 3_000_000);
    }

    // ================================================================== T-34 (đơn lẻ == lô một phần tử)

    function _orderDigest(uint256 id) internal view returns (bytes32) {
        (address b, address m, address t, uint256 amt, uint256 cAt, uint256 dAt, uint256 xAt, uint256 tmo, uint256 ins, uint256 fee, SlopeeEscrowMaster.OrderState st, bytes32 doc) = escrow.orders(id);
        return keccak256(abi.encode(b, m, t, amt, cAt, dAt, xAt, tmo, ins, fee, uint8(st), doc));
    }

    function _runSingle(SlopeeEscrowMaster.Quote memory q, bytes memory sig, bool viaBatch) internal returns (bytes32 digest, Vm.Log[] memory logs, uint256 escrowBal) {
        vm.recordLogs();
        vm.prank(buyer);
        if (viaBatch) {
            SlopeeEscrowMaster.Quote[] memory qs = new SlopeeEscrowMaster.Quote[](1);
            bytes[] memory sigs = new bytes[](1);
            qs[0] = q;
            sigs[0] = sig;
            escrow.depositEscrowBatch(qs, sigs);
        } else {
            escrow.depositEscrow(q, sig);
        }
        logs = vm.getRecordedLogs();
        digest = _orderDigest(q.orderId);
        escrowBal = usd.balanceOf(address(escrow));
    }

    function test_T34_singleDeposit_equalsBatchOfOne() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _signQuote(q);

        uint256 snap = vm.snapshotState();
        (bytes32 d1, Vm.Log[] memory l1, uint256 b1) = _runSingle(q, sig, false);
        vm.revertToState(snap);
        (bytes32 d2, Vm.Log[] memory l2, uint256 b2) = _runSingle(q, sig, true);

        assertEq(d1, d2, "trang thai don giong het nhau");
        assertEq(b1, b2, "so du contract giong het nhau");
        assertEq(l1.length, l2.length, "so su kien bang nhau");
        for (uint256 i = 0; i < l1.length; i++) {
            assertEq(l1[i].emitter, l2[i].emitter);
            assertEq(l1[i].data, l2[i].data);
            assertEq(l1[i].topics.length, l2[i].topics.length);
            for (uint256 j = 0; j < l1[i].topics.length; j++) assertEq(l1[i].topics[j], l2[i].topics[j]);
        }
    }

    function test_T34_singleDeposit_equalsBatchOfOne_eth() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(0), 2 ether);
        bytes memory sig = _signQuote(q);
        uint256 snap = vm.snapshotState();

        vm.recordLogs();
        vm.prank(buyer);
        escrow.depositEscrow{value: 2 ether}(q, sig);
        Vm.Log[] memory l1 = vm.getRecordedLogs();
        bytes32 d1 = _orderDigest(q.orderId);
        vm.revertToState(snap);

        SlopeeEscrowMaster.Quote[] memory qs = new SlopeeEscrowMaster.Quote[](1);
        bytes[] memory sigs = new bytes[](1);
        qs[0] = q;
        sigs[0] = sig;
        vm.recordLogs();
        vm.prank(buyer);
        escrow.depositEscrowBatch{value: 2 ether}(qs, sigs);
        Vm.Log[] memory l2 = vm.getRecordedLogs();

        assertEq(d1, _orderDigest(q.orderId));
        assertEq(l1.length, l2.length);
        assertEq(keccak256(abi.encode(l1[0].topics, l1[0].data)), keccak256(abi.encode(l2[0].topics, l2[0].data)));
        assertEq(address(escrow).balance, 2 ether);
    }

    // ================================================================== Báo giá đơn lẻ/lô dùng chung kiểm tra (không có đường yếu hơn)

    function test_batch_sameQuoteCannotBeDepositedTwice_acrossSingleAndBatch() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        escrow.depositEscrow(q, sig);

        SlopeeEscrowMaster.Quote[] memory qs = new SlopeeEscrowMaster.Quote[](1);
        bytes[] memory sigs = new bytes[](1);
        qs[0] = q;
        sigs[0] = sig;
        vm.prank(buyer);
        vm.expectRevert("Order exists");
        escrow.depositEscrowBatch(qs, sigs);
        assertEq(usd.balanceOf(address(escrow)), AMOUNT);
    }
}
