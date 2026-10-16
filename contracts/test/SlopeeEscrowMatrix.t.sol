// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./EscrowBase.t.sol";

/// @notice T-19: ma trận âm của máy trạng thái (SRS mục 5). Dựng một đơn ở mỗi trạng thái rồi gọi MỌI hàm thay đổi trạng thái;
///         cặp (trạng thái, hàm) nào không có trong bảng SRS mục 5 đều phải revert đúng lý do và không đổi trạng thái.
contract SlopeeEscrowMatrixTest is EscrowBase {
    enum M { ConfirmDelivery, EarlyRelease, ReleaseAfterInspection, CancelIfUnfulfilled, RaiseDispute, ResolveDispute, ForceResolve, Deposit, DepositBatch }

    uint256 internal constant METHODS = 9;
    uint256 internal constant STATES = 6; // NONE, LOCKED, DELIVERED, DISPUTED, COMPLETED, REFUNDED

    uint256[STATES] internal idOf;

    function setUp() public override {
        super.setUp();

        idOf[0] = 9_999_999; // NONE: mã chưa từng dùng
        idOf[1] = _depositToken(AMOUNT, FEE_BPS).orderId; // LOCKED

        idOf[2] = _depositToken(AMOUNT, FEE_BPS).orderId; // DELIVERED
        _deliver(idOf[2]);

        idOf[3] = _toDisputed(AMOUNT, FEE_BPS).orderId; // DISPUTED

        idOf[4] = _depositToken(AMOUNT, FEE_BPS).orderId; // COMPLETED
        _deliver(idOf[4]);
        vm.prank(buyer);
        escrow.earlyRelease(idOf[4]);

        idOf[5] = _toDisputed(AMOUNT, FEE_BPS).orderId; // REFUNDED (Trọng tài + Buyer ký hoàn tiền)
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, idOf[5], buyer, AMOUNT, deadline);
        escrow.resolveDispute(idOf[5], buyer, deadline, s1, s2);

        // Quá mọi mốc thời gian (14 ngày hủy, hạn kiểm tra, disputeTimeout) để lỗi chỉ có thể đến từ TRẠNG THÁI.
        vm.warp(block.timestamp + 200 days);
    }

    /// @dev Cặp hợp lệ theo SRS mục 5 (chỉ các cặp này không bị kỳ vọng revert vì lý do trạng thái).
    function _isValid(M m, OrderStateIdx st) internal pure returns (bool) {
        if (m == M.ConfirmDelivery) return st == OrderStateIdx.LOCKED;
        if (m == M.EarlyRelease) return st == OrderStateIdx.DELIVERED;
        if (m == M.ReleaseAfterInspection) return st == OrderStateIdx.DELIVERED;
        if (m == M.CancelIfUnfulfilled) return st == OrderStateIdx.LOCKED;
        if (m == M.RaiseDispute) return st == OrderStateIdx.DELIVERED;
        if (m == M.ResolveDispute) return st == OrderStateIdx.DISPUTED;
        if (m == M.ForceResolve) return st == OrderStateIdx.DISPUTED;
        return st == OrderStateIdx.NONE; // Deposit, DepositBatch
    }

    enum OrderStateIdx { NONE, LOCKED, DELIVERED, DISPUTED, COMPLETED, REFUNDED }

    function _expectedReason(M m) internal pure returns (string memory) {
        if (m == M.ConfirmDelivery) return "Not locked";
        if (m == M.EarlyRelease) return "Not delivered";
        if (m == M.ReleaseAfterInspection) return "Not delivered";
        if (m == M.CancelIfUnfulfilled) return "Not locked";
        if (m == M.RaiseDispute) return "Not delivered";
        if (m == M.ResolveDispute) return "Not disputed";
        if (m == M.ForceResolve) return "Not disputed";
        return "Order exists";
    }

    /// @dev Gọi hàm `m` lên đơn `id` bằng người gọi đúng vai (để lỗi không đến từ quyền).
    function _invoke(M m, uint256 id) internal returns (bool ok, bytes memory ret) {
        if (m == M.ConfirmDelivery) {
            vm.prank(shipper);
            (ok, ret) = address(escrow).call(abi.encodeWithSelector(escrow.confirmDelivery.selector, id));
        } else if (m == M.EarlyRelease) {
            vm.prank(buyer);
            (ok, ret) = address(escrow).call(abi.encodeWithSelector(escrow.earlyRelease.selector, id));
        } else if (m == M.ReleaseAfterInspection) {
            (ok, ret) = address(escrow).call(abi.encodeWithSelector(escrow.releaseAfterInspection.selector, id));
        } else if (m == M.CancelIfUnfulfilled) {
            vm.prank(buyer);
            (ok, ret) = address(escrow).call(abi.encodeWithSelector(escrow.cancelIfUnfulfilled.selector, id));
        } else if (m == M.RaiseDispute) {
            vm.prank(buyer);
            (ok, ret) = address(escrow).call(abi.encodeWithSelector(escrow.raiseDispute.selector, id));
        } else if (m == M.ResolveDispute) {
            (ok, ret) = address(escrow).call(
                abi.encodeWithSelector(escrow.resolveDispute.selector, id, buyer, block.timestamp + 1, bytes(""), bytes(""))
            );
        } else if (m == M.ForceResolve) {
            vm.prank(arbitrator);
            (ok, ret) = address(escrow).call(abi.encodeWithSelector(escrow.arbitratorForceResolve.selector, id, buyer));
        } else {
            SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
            q.orderId = id; // dùng lại mã đơn đã tồn tại
            bytes memory sig = _signQuote(q);
            if (m == M.Deposit) {
                vm.prank(buyer);
                (ok, ret) = address(escrow).call(abi.encodeWithSelector(escrow.depositEscrow.selector, q, sig));
            } else {
                SlopeeEscrowMaster.Quote[] memory qs = new SlopeeEscrowMaster.Quote[](1);
                bytes[] memory sigs = new bytes[](1);
                qs[0] = q;
                sigs[0] = sig;
                vm.prank(buyer);
                (ok, ret) = address(escrow).call(abi.encodeWithSelector(escrow.depositEscrowBatch.selector, qs, sigs));
            }
        }
    }

    function test_T19_everyInvalidStateMethodPair_reverts_withoutSideEffects() public {
        uint256 checked;
        uint256 escrowBalance = usd.balanceOf(address(escrow));
        for (uint256 s = 0; s < STATES; s++) {
            for (uint256 mi = 0; mi < METHODS; mi++) {
                M m = M(mi);
                if (_isValid(m, OrderStateIdx(s))) continue;

                uint8 stateBefore = uint8(_state(idOf[s]));
                (bool ok, bytes memory ret) = _invoke(m, idOf[s]);

                assertFalse(ok, "cap (trang thai, ham) khong hop le phai revert");
                assertEq(
                    keccak256(ret),
                    keccak256(abi.encodeWithSignature("Error(string)", _expectedReason(m))),
                    "sai ly do revert"
                );
                assertEq(uint8(_state(idOf[s])), stateBefore, "trang thai khong duoc doi");
                checked++;
            }
        }
        assertEq(usd.balanceOf(address(escrow)), escrowBalance, "khong co tien di chuyen");
        assertEq(checked, STATES * METHODS - METHODS, "9 cap hop le, con lai 45 cap am");
    }

    /// @dev Đối chiếu ngược: các cặp hợp lệ trong bảng thật sự thành công (không để ma trận "âm" vô nghĩa vì hàm luôn revert).
    function test_T19_validPairs_actuallySucceed() public {
        // Quay lại thời điểm trước warp: dựng đơn mới ở LOCKED rồi đi qua từng cặp hợp lệ
        vm.warp(block.timestamp - 200 days);
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        (bool ok,) = _invoke(M.ConfirmDelivery, q.orderId);
        assertTrue(ok, "ConfirmDelivery @ LOCKED");
        (ok,) = _invoke(M.RaiseDispute, q.orderId);
        assertTrue(ok, "RaiseDispute @ DELIVERED");

        SlopeeEscrowMaster.Quote memory r = _depositToken(AMOUNT, FEE_BPS);
        (ok,) = _invoke(M.ConfirmDelivery, r.orderId);
        assertTrue(ok);
        (ok,) = _invoke(M.EarlyRelease, r.orderId);
        assertTrue(ok, "EarlyRelease @ DELIVERED");

        SlopeeEscrowMaster.Quote memory c = _depositToken(AMOUNT, FEE_BPS);
        vm.warp(block.timestamp + 14 days);
        (ok,) = _invoke(M.CancelIfUnfulfilled, c.orderId);
        assertTrue(ok, "CancelIfUnfulfilled @ LOCKED");

        vm.warp(_disputedAt(q.orderId) + DISPUTE_TIMEOUT);
        (ok,) = _invoke(M.ForceResolve, q.orderId);
        assertTrue(ok, "ForceResolve @ DISPUTED");
    }
}
