// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./EscrowBase.t.sol";

/// @notice Tuần 8 [A]: rà checklist an ninh (Reentrancy, Signature Malleability, Role Separation, Front-running).
///         Chỉ BỔ SUNG các góc chưa có test riêng ở Tuần 1-2; mỗi test ghi rõ nó khóa mục nào của docs/SECURITY_CHECKLIST_W8.md.
///         KHÔNG đổi contract (ABI/storage đóng băng ở M1, Feature Freeze ở Tuần 8).
contract SlopeeEscrowSecurityW8Test is EscrowBase {
    uint256 internal constant SECP_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;

    address internal stranger;

    function setUp() public override {
        super.setUp();
        stranger = makeAddr("w8-stranger");
    }

    function _unauth(address who, bytes32 role) internal pure returns (bytes memory) {
        return abi.encodeWithSignature("AccessControlUnauthorizedAccount(address,bytes32)", who, role);
    }

    // ===================================================================== Role Separation (RS)

    /// @dev RS-1: chỉ DEFAULT_ADMIN_ROLE cấp/thu hồi vai trò. Không vai vận hành nào tự nâng quyền hoặc tước quyền vai khác.
    function test_W8_RS1_roleAdministration_onlyDefaultAdmin() public {
        bytes32 adminRole = escrow.DEFAULT_ADMIN_ROLE();
        bytes32 shipperRole = escrow.SHIPPER_ROLE();
        bytes32 arbRole = escrow.ARBITRATOR_ROLE();
        address[6] memory callers = [buyer, merchant, shipper, arbitrator, signer, stranger];
        for (uint256 i = 0; i < callers.length; i++) {
            vm.prank(callers[i]);
            vm.expectRevert(_unauth(callers[i], adminRole));
            escrow.grantRole(arbRole, callers[i]);

            vm.prank(callers[i]);
            vm.expectRevert(_unauth(callers[i], adminRole));
            escrow.revokeRole(shipperRole, shipper);
        }
        assertTrue(escrow.hasRole(shipperRole, shipper));
        assertFalse(escrow.hasRole(arbRole, buyer));
        assertFalse(escrow.hasRole(arbRole, stranger));
    }

    /// @dev RS-2: Admin không có đường nào rút tiền đang ký quỹ: không phải Buyer thì không giải ngân/khiếu nại,
    ///      không có ARBITRATOR_ROLE thì không xử đơn phương. Tiền nằm nguyên trong contract.
    function test_W8_RS2_admin_cannotMoveEscrowedFunds() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        _deliver(q.orderId);
        bytes32 arbRole = escrow.ARBITRATOR_ROLE();

        vm.startPrank(admin);
        vm.expectRevert("Only buyer");
        escrow.earlyRelease(q.orderId);
        vm.expectRevert("Only buyer");
        escrow.raiseDispute(q.orderId);
        vm.expectRevert(_unauth(admin, arbRole));
        escrow.arbitratorForceResolve(q.orderId, merchant);
        vm.stopPrank();

        assertEq(usd.balanceOf(address(escrow)), AMOUNT);
        assertEq(usd.balanceOf(admin), 0);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.DELIVERED));
    }

    /// @dev RS-3: ba khóa vận hành tách vai. Signer báo giá và Trọng tài không xác nhận giao hàng; Shipper không tự giải ngân,
    ///      không khiếu nại, không xử đơn; Signer báo giá không xử đơn.
    function test_W8_RS3_operatorKeys_cannotCrossDuties() public {
        SlopeeEscrowMaster.Quote memory q = _depositToken(AMOUNT, FEE_BPS);
        bytes32 shipperRole = escrow.SHIPPER_ROLE();
        bytes32 arbRole = escrow.ARBITRATOR_ROLE();

        vm.prank(signer);
        vm.expectRevert(_unauth(signer, shipperRole));
        escrow.confirmDelivery(q.orderId);
        vm.prank(arbitrator);
        vm.expectRevert(_unauth(arbitrator, shipperRole));
        escrow.confirmDelivery(q.orderId);

        _deliver(q.orderId);
        vm.prank(shipper);
        vm.expectRevert("Only buyer");
        escrow.earlyRelease(q.orderId);
        vm.prank(shipper);
        vm.expectRevert("Only buyer");
        escrow.raiseDispute(q.orderId);

        vm.prank(buyer);
        escrow.raiseDispute(q.orderId);
        vm.warp(_disputedAt(q.orderId) + DISPUTE_TIMEOUT);          // tới mốc thoát hiểm: chỉ Trọng tài mới được xử
        vm.prank(shipper);
        vm.expectRevert(_unauth(shipper, arbRole));
        escrow.arbitratorForceResolve(q.orderId, merchant);
        vm.prank(signer);
        vm.expectRevert(_unauth(signer, arbRole));
        escrow.arbitratorForceResolve(q.orderId, merchant);

        assertEq(usd.balanceOf(address(escrow)), AMOUNT);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.DISPUTED));
    }

    // ===================================================================== Front-running (FR)

    /// @dev FR-1: kẻ chạy trước với báo giá + chữ ký chép từ mempool không đốt được `orderId` của Buyer
    ///      (báo giá gắn `buyer == msg.sender`), nên Buyer thật vẫn nạp được sau đó.
    function test_W8_FR1_attackerCannotBurnBuyersOrderId() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        bytes memory sig = _signQuote(q);
        usd.mint(stranger, AMOUNT);

        vm.startPrank(stranger);
        usd.approve(address(escrow), type(uint256).max);
        vm.expectRevert("Caller must be quote buyer");
        escrow.depositEscrow(q, sig);
        vm.stopPrank();
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.NONE));

        vm.prank(buyer);
        escrow.depositEscrow(q, sig);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
    }

    /// @dev FR-2: ai cũng nộp được 2 chữ ký phán quyết (kể cả kẻ chạy trước), nhưng kết quả bị CHÍNH chữ ký khóa:
    ///      đổi người nhận thì chữ ký không còn khớp; nộp trước thì tiền vẫn về đúng người đã ký, kẻ nộp không được gì.
    function test_W8_FR2_anySubmitter_getsOnlyTheSignedOutcome() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, q.orderId, buyer, AMOUNT, deadline);

        // chạy trước và đổi người nhận sang Merchant: chữ ký không khớp
        vm.prank(stranger);
        vm.expectRevert("Need two distinct parties");
        escrow.resolveDispute(q.orderId, merchant, deadline, s1, s2);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.DISPUTED));

        // chạy trước nguyên văn: hoàn tiền đúng cho Buyer, kẻ nộp không nhận gì
        uint256 buyerBefore = usd.balanceOf(buyer);
        vm.prank(stranger);
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
        assertEq(usd.balanceOf(buyer), buyerBefore + AMOUNT);
        assertEq(usd.balanceOf(stranger), 0);
        assertEq(usd.balanceOf(merchant), 0);
        assertEq(usd.balanceOf(feeRecipient), 0);

        // lần nộp thứ hai (người gốc nộp chậm) không làm gì thêm
        vm.expectRevert("Not disputed");
        escrow.resolveDispute(q.orderId, buyer, deadline, s1, s2);
    }

    // ===================================================================== Signature Malleability (SM)

    /// @dev SM-1: một bên không thể tự "nhân đôi" chữ ký thành hai bên bằng cách đổi cách mã hóa của CHÍNH chữ ký đó:
    ///      (a) bản chuẩn + bản EIP-2098 compact 64 byte, (b) bản chuẩn + bản sinh đôi s cao / v đảo.
    ///      Tùy phiên bản OpenZeppelin, mã hóa lạ bị từ chối ngay (độ dài/`s` cao) hoặc quy về cùng một bên ("Need two distinct parties");
    ///      cả hai đều là revert, đơn vẫn DISPUTED và tiền nằm nguyên.
    function test_W8_SM1_sameSigner_cannotBeCountedTwice_viaAlternateEncodings() public {
        SlopeeEscrowMaster.Quote memory q = _toDisputed(AMOUNT, FEE_BPS);
        uint256 deadline = block.timestamp + 1 days;
        bytes32 digest = _disputeDigest(q.orderId, buyer, AMOUNT, 0, deadline);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(BUYER_KEY, digest);

        bytes memory canonical = abi.encodePacked(r, s, v);
        bytes memory compact = abi.encodePacked(r, bytes32((uint256(v - 27) << 255) | uint256(s)));
        bytes memory twin = abi.encodePacked(r, bytes32(SECP_N - uint256(s)), v == 27 ? uint8(28) : uint8(27));

        vm.expectRevert();
        escrow.resolveDispute(q.orderId, buyer, deadline, canonical, compact);
        vm.expectRevert();
        escrow.resolveDispute(q.orderId, buyer, deadline, canonical, twin);
        vm.expectRevert();
        escrow.resolveDispute(q.orderId, buyer, deadline, twin, canonical);

        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.DISPUTED));
        assertEq(usd.balanceOf(address(escrow)), AMOUNT);
        assertEq(escrow.disputeNonces(q.orderId), 0);               // nonce hoàn tác khi revert
    }

    /// @dev SM-2: chữ ký báo giá dạng s cao (twin) bị từ chối, nên không thể dựng "chữ ký thứ hai hợp lệ" cho cùng một báo giá.
    function test_W8_SM2_quoteSignature_highSTwin_rejected() public {
        SlopeeEscrowMaster.Quote memory q = _quote(address(usd), AMOUNT);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(SIGNER_KEY, _quoteDigest(q));
        bytes memory twin = abi.encodePacked(r, bytes32(SECP_N - uint256(s)), v == 27 ? uint8(28) : uint8(27));

        vm.prank(buyer);
        vm.expectRevert();
        escrow.depositEscrow(q, twin);
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.NONE));

        vm.prank(buyer);                                              // chữ ký chuẩn vẫn dùng được
        escrow.depositEscrow(q, abi.encodePacked(r, s, v));
        assertEq(uint8(_state(q.orderId)), uint8(SlopeeEscrowMaster.OrderState.LOCKED));
    }
}
