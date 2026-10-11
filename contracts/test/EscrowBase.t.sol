// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import {SlopeeEscrowMaster} from "../src/SlopeeEscrowMaster.sol";
import {MockUSD} from "../src/MockUSD.sol";

/// @dev Nền chung cho test contract: dùng 7 tài khoản mặc định của Anvil để khớp với bootstrap.sh.
abstract contract EscrowBase is Test {
    // Khóa thử mặc định của Anvil (chỉ dùng cục bộ, KHÔNG phải khóa thật)
    uint256 internal constant ADMIN_KEY      = 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80;
    uint256 internal constant SHIPPER_KEY    = 0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d;
    uint256 internal constant ARBITRATOR_KEY = 0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a;
    uint256 internal constant SIGNER_KEY     = 0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6;
    uint256 internal constant FEE_KEY        = 0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a;
    uint256 internal constant BUYER_KEY      = 0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba;
    uint256 internal constant MERCHANT_KEY   = 0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e;

    // Khai báo lại sự kiện để dùng với vm.expectEmit (solc 0.8.20 chưa cho `emit Contract.Event`)
    event OrderCreated(
        uint256 indexed orderId, address indexed buyer, address indexed merchant,
        address token, uint256 amount, uint256 inspectionDuration, uint256 disputeTimeout, bytes32 docHash, uint256 feeBps
    );
    event OrderDelivered(uint256 indexed orderId, uint256 deliveredAt);
    event OrderCompleted(uint256 indexed orderId, uint256 netPayout, uint256 feeAmount);
    event OrderRefunded(uint256 indexed orderId, address indexed to, uint256 amount);

    SlopeeEscrowMaster internal escrow;
    MockUSD internal usd;

    address internal admin;
    address internal shipper;
    address internal arbitrator;
    address internal signer;
    address internal feeRecipient;
    address internal buyer;
    address internal merchant;

    uint256 internal constant AMOUNT = 100_000_000; // 100 MUSD (6 decimals)
    uint256 internal constant INSPECTION = 3 days;
    uint256 internal constant DISPUTE_TIMEOUT = 14 days;
    uint256 internal constant FEE_BPS = 300;
    bytes32 internal constant DOC_HASH = keccak256("slopee-doc");

    uint256 internal nextId = 1;

    function setUp() public virtual {
        admin = vm.addr(ADMIN_KEY);
        shipper = vm.addr(SHIPPER_KEY);
        arbitrator = vm.addr(ARBITRATOR_KEY);
        signer = vm.addr(SIGNER_KEY);
        feeRecipient = vm.addr(FEE_KEY);
        buyer = vm.addr(BUYER_KEY);
        merchant = vm.addr(MERCHANT_KEY);

        escrow = new SlopeeEscrowMaster(admin, shipper, arbitrator, signer, feeRecipient);
        usd = new MockUSD();

        usd.mint(buyer, 1_000_000_000);
        vm.deal(buyer, 100 ether);
        vm.prank(buyer);
        usd.approve(address(escrow), type(uint256).max);
    }

    // ------------------------------------------------------------------ Helpers

    function _quote(address token, uint256 amount) internal returns (SlopeeEscrowMaster.Quote memory q) {
        q = SlopeeEscrowMaster.Quote({
            orderId: nextId++,
            buyer: buyer,
            merchant: merchant,
            token: token,
            amount: amount,
            inspectionDuration: INSPECTION,
            disputeTimeout: DISPUTE_TIMEOUT,
            feeBps: FEE_BPS,
            docHash: DOC_HASH,
            deadline: block.timestamp + 1 hours
        });
    }

    function _domainSeparator() internal view returns (bytes32) {
        return keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256(bytes("SlopeeEscrow")),
            keccak256(bytes("1")),
            block.chainid,
            address(escrow)
        ));
    }

    function _quoteDigest(SlopeeEscrowMaster.Quote memory q) internal view returns (bytes32) {
        bytes32 structHash = keccak256(abi.encode(
            escrow.QUOTE_TYPEHASH(), q.orderId, q.buyer, q.merchant, q.token,
            q.amount, q.inspectionDuration, q.disputeTimeout, q.feeBps, q.docHash, q.deadline
        ));
        return keccak256(abi.encodePacked("\x19\x01", _domainSeparator(), structHash));
    }

    function _sign(uint256 key, bytes32 digest) internal pure returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    function _signQuote(SlopeeEscrowMaster.Quote memory q) internal view returns (bytes memory) {
        return _sign(SIGNER_KEY, _quoteDigest(q));
    }

    /// @dev Buyer nạp một đơn token MockUSD, trả về báo giá đã dùng.
    function _depositToken(uint256 amount, uint256 feeBps) internal returns (SlopeeEscrowMaster.Quote memory q) {
        q = _quote(address(usd), amount);
        q.feeBps = feeBps;
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        escrow.depositEscrow(q, sig);
    }

    function _depositEth(uint256 amount) internal returns (SlopeeEscrowMaster.Quote memory q) {
        q = _quote(address(0), amount);
        bytes memory sig = _signQuote(q);
        vm.prank(buyer);
        escrow.depositEscrow{value: amount}(q, sig);
    }

    function _state(uint256 id) internal view returns (SlopeeEscrowMaster.OrderState st) {
        (, , , , , , , , , , st, ) = escrow.orders(id);
    }
}
