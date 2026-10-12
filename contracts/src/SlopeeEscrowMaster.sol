// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title SlopeeEscrowMaster — nạp đơn (đơn lẻ và nạp gom), giao hàng, giải ngân, tranh chấp 2/3 chữ ký, thoát hiểm timeout.
/// @notice Bám theo mã tham chiếu SRS mục 10 (đã áp dụng thay đổi SDD 4.8 và 4.9). Tuần 1 làm phần nạp đơn lẻ/giao/giải ngân/hủy;
///         tuần 2 bổ sung `depositEscrowBatch`, `raiseDispute`, `resolveDispute`, `arbitratorForceResolve`, `claimPending`,
///         `setDefaultFeeBps`, `setFeeRecipient`. Struct, enum, sự kiện, hằng số và storage KHÔNG đổi so với tuần 1 (ABI/storage ổn định).
/// @dev Mã cho đồ án, chưa qua kiểm toán độc lập. ABI đóng băng ở cột mốc M1.
contract SlopeeEscrowMaster is AccessControl, ReentrancyGuard, EIP712 {
    using SafeERC20 for IERC20;

    bytes32 public constant SHIPPER_ROLE      = keccak256("SHIPPER_ROLE");
    bytes32 public constant ARBITRATOR_ROLE   = keccak256("ARBITRATOR_ROLE");
    bytes32 public constant QUOTE_SIGNER_ROLE = keccak256("QUOTE_SIGNER_ROLE");

    bytes32 public constant QUOTE_TYPEHASH = keccak256(
        "OrderQuote(uint256 orderId,address buyer,address merchant,address token,uint256 amount,uint256 inspectionDuration,uint256 disputeTimeout,uint256 feeBps,bytes32 docHash,uint256 deadline)"
    );
    bytes32 public constant DISPUTE_TYPEHASH = keccak256(
        "DisputeResolution(uint256 orderId,address payoutTo,uint256 amount,uint256 nonce,uint256 deadline)"
    );

    enum OrderState { NONE, LOCKED, DELIVERED, DISPUTED, COMPLETED, REFUNDED }

    struct Order {
        address buyer;
        address merchant;
        address token;              // address(0) = ETH, khác = ERC20
        uint256 amount;
        uint256 createdAt;
        uint256 deliveredAt;
        uint256 disputedAt;
        uint256 disputeTimeout;     // chốt từ báo giá, 7-90 ngày
        uint256 inspectionDuration;
        uint256 feeBps;             // chốt từ báo giá, không vượt trần defaultFeeBps
        OrderState state;
        bytes32 docHash;
    }

    // Trùng 1-1 với kiểu EIP-712 OrderQuote (cùng trường, cùng thứ tự)
    struct Quote {
        uint256 orderId;
        address buyer;
        address merchant;
        address token;
        uint256 amount;
        uint256 inspectionDuration;
        uint256 disputeTimeout;
        uint256 feeBps;             // phí chốt trong báo giá
        bytes32 docHash;
        uint256 deadline;
    }

    uint256 public constant MIN_INSPECTION_DURATION = 1 hours;
    uint256 public constant MAX_INSPECTION_DURATION = 30 days;
    uint256 public constant DELIVERY_TIMEOUT = 14 days;
    uint256 public constant MIN_DISPUTE_TIMEOUT = 7 days;   // ≥ hạn chữ ký phán quyết mặc định
    uint256 public constant MAX_DISPUTE_TIMEOUT = 90 days;
    uint256 public constant MAX_FEE_BPS = 1000;             // tối đa 10%
    uint256 public constant MAX_BATCH_SIZE = 5;             // dùng ở tuần 2 (depositEscrowBatch)

    address public feeRecipient;
    uint256 public defaultFeeBps = 300;                     // 3%

    mapping(uint256 => Order) public orders;
    mapping(uint256 => uint256) public disputeNonces;
    // token => người nhận => số tiền chờ rút (pull-payment)
    mapping(address => mapping(address => uint256)) public pendingWithdrawals;

    event OrderCreated(
        uint256 indexed orderId, address indexed buyer, address indexed merchant,
        address token, uint256 amount, uint256 inspectionDuration, uint256 disputeTimeout, bytes32 docHash, uint256 feeBps
    );
    event OrderDelivered(uint256 indexed orderId, uint256 deliveredAt);
    event OrderDisputed(uint256 indexed orderId, address indexed raisedBy, uint256 disputedAt);
    event OrderCompleted(uint256 indexed orderId, uint256 netPayout, uint256 feeAmount);
    event OrderRefunded(uint256 indexed orderId, address indexed to, uint256 amount);
    event DisputeResolved(uint256 indexed orderId, address indexed payoutTo, uint256 amount);
    event ArbitratorForceResolved(uint256 indexed orderId, address indexed payoutTo);
    event PayoutDeferred(address indexed token, address indexed to, uint256 amount);
    event PendingClaimed(address indexed token, address indexed to, uint256 amount);
    event FeeUpdated(uint256 newFeeBps);
    event FeeRecipientUpdated(address newRecipient);

    constructor(
        address _admin,
        address _shipper,
        address _arbitrator,
        address _quoteSigner,
        address _feeRecipient
    ) EIP712("SlopeeEscrow", "1") {
        require(_admin != address(0) && _feeRecipient != address(0), "Invalid address");
        feeRecipient = _feeRecipient;
        _grantRole(DEFAULT_ADMIN_ROLE, _admin);
        _grantRole(SHIPPER_ROLE, _shipper);
        _grantRole(ARBITRATOR_ROLE, _arbitrator);
        _grantRole(QUOTE_SIGNER_ROLE, _quoteSigner);
    }

    // ---------------------------------------------------------------- Nạp tiền

    /// @notice Nạp tiền cho một đơn (tương đương lô một phần tử, xem T-34).
    function depositEscrow(Quote calldata q, bytes calldata quoteSig)
        external
        payable
        nonReentrant
    {
        _acceptQuote(q, quoteSig);
        _collect(q.token, q.amount);
    }

    /// @notice Nạp gom nhiều đơn (nhiều shop) trong đúng một giao dịch, thu tiền đúng một lần (BR-11).
    /// @dev Nguyên tử: một báo giá lỗi thì cả giao dịch revert, không đơn nào được tạo. Tối đa `MAX_BATCH_SIZE` đơn, một token.
    ///      Đơn được ghi LOCKED ngay trong vòng lặp nên `orderId` trùng trong cùng lô bị từ chối bằng "Order exists"
    ///      (nếu kiểm trước, ghi sau thì tiền bị thu hai lần mà chỉ có một đơn — sai INV-01).
    function depositEscrowBatch(Quote[] calldata quotes, bytes[] calldata quoteSigs)
        external
        payable
        nonReentrant
    {
        uint256 n = quotes.length;
        require(n > 0 && n <= MAX_BATCH_SIZE, "Invalid batch size");
        require(n == quoteSigs.length, "Length mismatch");

        address token = quotes[0].token;
        uint256 total = 0;
        for (uint256 i = 0; i < n; i++) {
            require(quotes[i].token == token, "Mixed tokens unsupported");
            _acceptQuote(quotes[i], quoteSigs[i]);
            total += quotes[i].amount;
        }
        _collect(token, total);
    }

    /// @dev Kiểm tra mọi điều kiện của một báo giá và ghi đơn. Không chuyển tiền.
    ///      `depositEscrow` và `depositEscrowBatch` dùng chung hàm này nên không có đường nạp nào yếu hơn.
    function _acceptQuote(Quote calldata q, bytes calldata sig) internal {
        // slither-disable-next-line incorrect-equality -- so sánh enum (NONE = mã đơn chưa dùng), không phải so sánh số dư
        require(orders[q.orderId].state == OrderState.NONE, "Order exists");
        require(block.timestamp <= q.deadline, "Quote expired");
        require(q.amount > 0, "Zero amount");
        require(q.buyer == msg.sender, "Caller must be quote buyer");
        require(q.feeBps <= defaultFeeBps, "Fee exceeds on-chain cap");
        require(q.merchant != address(0) && q.merchant != msg.sender, "Invalid merchant");
        require(
            q.inspectionDuration >= MIN_INSPECTION_DURATION &&
            q.inspectionDuration <= MAX_INSPECTION_DURATION,
            "Invalid duration"
        );
        require(
            q.disputeTimeout >= MIN_DISPUTE_TIMEOUT && q.disputeTimeout <= MAX_DISPUTE_TIMEOUT,
            "Invalid dispute timeout"
        );
        require(
            !hasRole(ARBITRATOR_ROLE, msg.sender) && !hasRole(ARBITRATOR_ROLE, q.merchant),
            "Arbitrator cannot trade"
        );
        _verifyQuote(q, sig);

        Order storage o = orders[q.orderId];
        o.buyer = msg.sender;
        o.merchant = q.merchant;
        o.token = q.token;
        o.amount = q.amount;
        o.createdAt = block.timestamp;
        o.inspectionDuration = q.inspectionDuration;
        o.disputeTimeout = q.disputeTimeout;
        o.feeBps = q.feeBps;           // phí theo báo giá (đã kiểm không vượt trần)
        o.state = OrderState.LOCKED;
        o.docHash = q.docHash;

        emit OrderCreated(
            q.orderId, msg.sender, q.merchant, q.token, q.amount,
            q.inspectionDuration, q.disputeTimeout, q.docHash, q.feeBps
        );
    }

    /// @dev Thu tiền đúng một lần (trạng thái đã ghi trước; hàm gọi được bảo vệ bởi nonReentrant).
    function _collect(address token, uint256 total) internal {
        if (token == address(0)) {
            require(msg.value == total, "Wrong ETH value");
        } else {
            require(msg.value == 0, "Do not send ETH for token");
            // slither-disable-start reentrancy-balance,incorrect-equality
            // Chủ đích: đọc chênh lệch số dư để loại token phí-khi-chuyển (SDD 4.4). Không khai thác được tái nhập vì
            // mọi đường gọi `_collect` đều có `nonReentrant` (test T-17: token độc hại gọi lại khi nạp bị chặn).
            uint256 before = IERC20(token).balanceOf(address(this));
            IERC20(token).safeTransferFrom(msg.sender, address(this), total);
            require(
                IERC20(token).balanceOf(address(this)) - before == total,
                "Fee-on-transfer unsupported"
            );
            // slither-disable-end reentrancy-balance,incorrect-equality
        }
    }

    function _verifyQuote(Quote calldata q, bytes calldata sig) internal view {
        bytes32 digest = _hashTypedDataV4(keccak256(abi.encode(
            QUOTE_TYPEHASH, q.orderId, q.buyer, q.merchant, q.token,
            q.amount, q.inspectionDuration, q.disputeTimeout, q.feeBps, q.docHash, q.deadline
        )));
        require(hasRole(QUOTE_SIGNER_ROLE, ECDSA.recover(digest, sig)), "Bad quote signature");
    }

    // ------------------------------------------------------------ Giao hàng, giải ngân

    function confirmDelivery(uint256 _orderId) external onlyRole(SHIPPER_ROLE) {
        Order storage order = orders[_orderId];
        require(order.state == OrderState.LOCKED, "Not locked");
        order.deliveredAt = block.timestamp;
        order.state = OrderState.DELIVERED;
        emit OrderDelivered(_orderId, block.timestamp);
    }

    function earlyRelease(uint256 _orderId) external nonReentrant {
        Order storage order = orders[_orderId];
        require(order.state == OrderState.DELIVERED, "Not delivered");
        require(msg.sender == order.buyer, "Only buyer");
        _executePayout(order, _orderId);
    }

    function releaseAfterInspection(uint256 _orderId) external nonReentrant {
        Order storage order = orders[_orderId];
        require(order.state == OrderState.DELIVERED, "Not delivered");
        require(block.timestamp >= order.deliveredAt + order.inspectionDuration, "Under inspection");
        _executePayout(order, _orderId);
    }

    function cancelIfUnfulfilled(uint256 _orderId) external nonReentrant {
        Order storage order = orders[_orderId];
        require(order.state == OrderState.LOCKED, "Not locked");
        require(block.timestamp >= order.createdAt + DELIVERY_TIMEOUT, "Timeout not reached");
        require(msg.sender == order.buyer || hasRole(DEFAULT_ADMIN_ROLE, msg.sender), "Unauthorized");
        _refund(order, _orderId);
    }

    // ----------------------------------------------------------------- Tranh chấp

    /// @notice Buyer khiếu nại trong hạn kiểm tra; đóng băng tiền cho tới khi phân xử hoặc hết `disputeTimeout`.
    function raiseDispute(uint256 _orderId) external {
        Order storage order = orders[_orderId];
        require(order.state == OrderState.DELIVERED, "Not delivered");
        require(msg.sender == order.buyer, "Only buyer");
        require(block.timestamp < order.deliveredAt + order.inspectionDuration, "Expired");
        order.state = OrderState.DISPUTED;
        order.disputedAt = block.timestamp;
        emit OrderDisputed(_orderId, msg.sender, block.timestamp);
    }

    /// @notice Phân xử bằng 2 chữ ký EIP-712 của 2 bên khác nhau (Buyer / Merchant / Trọng tài). Ai cũng có thể nộp.
    /// @dev `_deadline < disputedAt + disputeTimeout` để hai đường xử lý (chữ ký và thoát hiểm) không bao giờ cùng hợp lệ (R-02).
    ///      Nonce tăng trước khi kiểm tra bên; nếu revert thì mức tăng bị hoàn tác (INV-04 chỉ xét trạng thái đã commit).
    function resolveDispute(
        uint256 _orderId,
        address _payoutTo,
        uint256 _deadline,
        bytes calldata _sig1,
        bytes calldata _sig2
    ) external nonReentrant {
        Order storage order = orders[_orderId];
        require(order.state == OrderState.DISPUTED, "Not disputed");
        require(_payoutTo == order.buyer || _payoutTo == order.merchant, "Invalid payout recipient");
        require(block.timestamp <= _deadline, "Signature expired");
        require(_deadline < order.disputedAt + order.disputeTimeout, "Deadline must be before dispute timeout");

        bytes32 digest = _hashTypedDataV4(keccak256(abi.encode(
            DISPUTE_TYPEHASH, _orderId, _payoutTo, order.amount, disputeNonces[_orderId], _deadline
        )));
        disputeNonces[_orderId]++;

        uint8 p1 = _partyOf(order, ECDSA.recover(digest, _sig1));
        uint8 p2 = _partyOf(order, ECDSA.recover(digest, _sig2));
        require(p1 != 0 && p2 != 0 && p1 != p2, "Need two distinct parties");

        _settle(order, _orderId, _payoutTo);
        emit DisputeResolved(_orderId, _payoutTo, order.amount);
    }

    /// @notice Thoát hiểm: Trọng tài xử đơn phương khi quá `disputeTimeout` của chính đơn đó (BR-05, BR-10).
    function arbitratorForceResolve(uint256 _orderId, address _payoutTo)
        external
        nonReentrant
        onlyRole(ARBITRATOR_ROLE)
    {
        Order storage order = orders[_orderId];
        require(order.state == OrderState.DISPUTED, "Not disputed");
        require(block.timestamp >= order.disputedAt + order.disputeTimeout, "Dispute timeout not reached");
        require(_payoutTo == order.buyer || _payoutTo == order.merchant, "Invalid payout recipient");

        _settle(order, _orderId, _payoutTo);
        emit ArbitratorForceResolved(_orderId, _payoutTo);
    }

    // ------------------------------------------------------------------- Nội bộ

    /// @dev Chọn đường thanh toán theo người được nhận: Buyer ⇒ hoàn tiền nguyên vẹn, Merchant ⇒ giải ngân có trừ phí.
    function _settle(Order storage order, uint256 _orderId, address _payoutTo) internal {
        if (_payoutTo == order.buyer) {
            _refund(order, _orderId);
        } else {
            _executePayout(order, _orderId);
        }
    }

    function _refund(Order storage order, uint256 _orderId) internal {
        order.state = OrderState.REFUNDED;                 // cập nhật trạng thái trước khi chuyển tiền
        _payout(order.token, order.buyer, order.amount);
        emit OrderRefunded(_orderId, order.buyer, order.amount);
    }

    function _executePayout(Order storage order, uint256 _orderId) internal {
        order.state = OrderState.COMPLETED;
        uint256 feeAmount = (order.amount * order.feeBps) / 10000;
        uint256 netPayout = order.amount - feeAmount;

        _payout(order.token, order.merchant, netPayout);
        if (feeAmount > 0) {
            _payout(order.token, feeRecipient, feeAmount);
        }
        emit OrderCompleted(_orderId, netPayout, feeAmount);
    }

    /// @dev ETH: nếu người nhận từ chối, ghi vào sổ chờ rút thay vì revert làm kẹt đơn (rút bằng `claimPending`).
    function _payout(address _token, address _to, uint256 _amount) internal {
        if (_token == address(0)) {
            (bool ok, ) = payable(_to).call{value: _amount, gas: 30000}("");
            if (!ok) {
                pendingWithdrawals[_token][_to] += _amount;
                emit PayoutDeferred(_token, _to, _amount);
            }
        } else {
            IERC20(_token).safeTransfer(_to, _amount);
        }
    }

    /// @notice Rút khoản đã bị hoãn (pull-payment). Xóa số dư trước khi chuyển (Checks-Effects-Interactions) + `nonReentrant`.
    function claimPending(address _token) external nonReentrant {
        uint256 amount = pendingWithdrawals[_token][msg.sender];
        require(amount > 0, "Nothing to claim");
        pendingWithdrawals[_token][msg.sender] = 0;
        if (_token == address(0)) {
            (bool ok, ) = payable(msg.sender).call{value: amount}("");
            require(ok, "ETH transfer failed");
        } else {
            IERC20(_token).safeTransfer(msg.sender, amount);
        }
        emit PendingClaimed(_token, msg.sender, amount);
    }

    /// @dev 1 = Buyer, 2 = Merchant, 3 = Trọng tài, 0 = không thuộc đơn. Buyer/Merchant được ưu tiên nếu một địa chỉ mang nhiều vai.
    function _partyOf(Order storage order, address _signer) internal view returns (uint8) {
        if (_signer == order.buyer) return 1;
        if (_signer == order.merchant) return 2;
        if (hasRole(ARBITRATOR_ROLE, _signer)) return 3;
        return 0;
    }

    // ------------------------------------------------------------------ Quản trị

    /// @notice Đặt TRẦN phí on-chain (tối đa `MAX_FEE_BPS`). Phí từng đơn lấy từ báo giá và đã chốt khi nạp nên không bị ảnh hưởng (INV-06).
    function setDefaultFeeBps(uint256 _newFeeBps) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(_newFeeBps <= MAX_FEE_BPS, "Exceeds cap");
        defaultFeeBps = _newFeeBps;
        emit FeeUpdated(_newFeeBps);
    }

    function setFeeRecipient(address _newRecipient) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(_newRecipient != address(0), "Invalid fee recipient");
        feeRecipient = _newRecipient;
        emit FeeRecipientUpdated(_newRecipient);
    }
}
