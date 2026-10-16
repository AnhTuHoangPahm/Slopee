// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {SlopeeEscrowMaster} from "../src/SlopeeEscrowMaster.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @dev Selector của lỗi OpenZeppelin ReentrancyGuard (v5): `ReentrancyGuardReentrantCall()`.
bytes4 constant REENTRANCY_SELECTOR = bytes4(keccak256("ReentrancyGuardReentrantCall()"));

/// @notice Ví hợp đồng dùng làm Buyer/Merchant/nơi nhận phí trong test.
///         `accept = false` ⇒ từ chối ETH (mô phỏng ví không nhận được tiền → khoản bị hoãn vào sổ chờ rút).
///         `exec` cho phép ví gọi bất kỳ hàm nào với tư cách `msg.sender` (ví hợp đồng không ký được EIP-712 bằng ECDSA).
contract SmartWallet {
    bool public accept;

    constructor(bool _accept) {
        accept = _accept;
    }

    function setAccept(bool a) external {
        accept = a;
    }

    /// @dev Chuyển tiếp lỗi nguyên văn để test kiểm được lý do revert của contract đích.
    function exec(address target, bytes calldata data) external payable returns (bytes memory ret) {
        bool ok;
        (ok, ret) = target.call{value: msg.value}(data);
        if (!ok) {
            assembly {
                revert(add(ret, 32), mload(ret))
            }
        }
    }

    receive() external payable virtual {
        require(accept, "no ETH");
    }
}

/// @notice Ví tấn công reentrancy. Khi nhận ETH qua `claimPending` (đủ gas) nó cố gọi lại escrow bằng nhiều hàm di chuyển tiền.
///         Lần nhận đầu bằng `_payout` (giới hạn 30.000 gas) bị từ chối (`accept = false`) để tiền vào sổ chờ rút.
contract ReentrantWallet is SmartWallet {
    SlopeeEscrowMaster public immutable escrow;
    bool public attack;          // true: lần nhận kế tiếp sẽ tấn công (một lần)
    bool public bubbleRevert;    // true: nếu có đòn bị chặn thì revert luôn lần nhận ETH
    uint256 public otherOrder;   // một đơn khác để thử rút/hủy khi đang bị gọi lại
    uint256 public attempts;
    uint256 public blocked;      // số đòn bị ReentrancyGuard chặn
    uint256 public succeeded;    // số đòn KHÔNG bị chặn (phải luôn = 0)

    constructor(SlopeeEscrowMaster _escrow) SmartWallet(false) {
        escrow = _escrow;
    }

    function arm(uint256 _otherOrder, bool _bubble) external {
        otherOrder = _otherOrder;
        bubbleRevert = _bubble;
        attack = true;
        accept = true;
    }

    function _try(bytes memory data) internal {
        attempts++;
        (bool ok, bytes memory ret) = address(escrow).call(data);
        if (ok) {
            succeeded++;
        } else if (ret.length >= 4 && bytes4(ret) == REENTRANCY_SELECTOR) {
            blocked++;
        }
    }

    receive() external payable override {
        require(accept, "no ETH");
        if (attack) {
            attack = false; // chỉ tấn công một lần để tránh vòng lặp vô hạn
            _try(abi.encodeWithSelector(escrow.claimPending.selector, address(0)));
            _try(abi.encodeWithSelector(escrow.earlyRelease.selector, otherOrder));
            _try(abi.encodeWithSelector(escrow.releaseAfterInspection.selector, otherOrder));
            _try(abi.encodeWithSelector(escrow.cancelIfUnfulfilled.selector, otherOrder));
            if (bubbleRevert && blocked > 0) revert("reentry blocked");
        }
    }
}

/// @notice ERC-20 độc hại: ngay trước khi chuyển (cả `transferFrom` lúc nạp lẫn `transfer` lúc giải ngân)
///         nó gọi lại escrow bằng danh sách lời gọi đã nạp sẵn. Mọi lời gọi phải bị `nonReentrant` chặn.
contract EvilToken is ERC20 {
    address public target;
    bytes[] internal attacks;
    bool public armed;
    uint256 public attempts;
    uint256 public blocked;
    uint256 public succeeded;

    constructor() ERC20("Evil", "EVL") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function arm(address _target, bytes[] calldata calls) external {
        target = _target;
        delete attacks;
        for (uint256 i = 0; i < calls.length; i++) {
            attacks.push(calls[i]);
        }
        armed = true;
    }

    function _update(address from, address to, uint256 value) internal override {
        if (armed) {
            armed = false; // một lần cho mỗi lần `arm`
            for (uint256 i = 0; i < attacks.length; i++) {
                attempts++;
                (bool ok, bytes memory ret) = target.call(attacks[i]);
                if (ok) {
                    succeeded++;
                } else if (ret.length >= 4 && bytes4(ret) == REENTRANCY_SELECTOR) {
                    blocked++;
                }
            }
        }
        super._update(from, to, value);
    }
}

/// @notice Token thu phí 1% khi chuyển: contract phải từ chối (kiểm tra chênh lệch số dư khi nạp).
contract FeeOnTransferToken is ERC20 {
    constructor() ERC20("FeeToken", "FEE") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0) && to != address(0)) {
            uint256 fee = value / 100;
            super._update(from, address(0), fee); // đốt 1%
            super._update(from, to, value - fee);
        } else {
            super._update(from, to, value);
        }
    }
}
