// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice ERC-20 giả lập cho môi trường thử (Anvil). 6 chữ số thập phân (Q-01).
/// @dev Chỉ dùng để demo đồ án: `mint` không có kiểm soát truy cập vì token không có giá trị thật.
contract MockUSD is ERC20 {
    constructor() ERC20("Mock USD", "MUSD") {}

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
