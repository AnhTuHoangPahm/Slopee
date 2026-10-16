// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import {SlopeeEscrowMaster} from "../src/SlopeeEscrowMaster.sol";
import {MockUSD} from "../src/MockUSD.sol";

/// @notice Triển khai MockUSD + SlopeeEscrowMaster lên Anvil và ghi `deployments/local.json` (SDD 4.7).
///         Mặc định dùng 7 tài khoản thử của Anvil; mọi địa chỉ/khóa đều ghi đè được bằng biến môi trường.
///         Tài khoản mặc định: #0 admin/deployer, #1 shipper, #2 arbitrator, #3 quoteSigner, #4 feeRecipient,
///         #5 buyer thử (được mint MockUSD), #6 merchant thử.
contract Deploy is Script {
    // Khóa #0 của Anvil (công khai, chỉ dùng cục bộ) — dùng làm deployer mặc định
    uint256 internal constant ANVIL_KEY_0 = 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80;

    function run() external {
        require(block.chainid == 31337, "Chi trien khai tren Anvil (chainId 31337)");

        uint256 deployerKey = vm.envOr("DEPLOYER_KEY", ANVIL_KEY_0);
        address admin = vm.envOr("ADMIN_ADDRESS", vm.addr(deployerKey));
        address shipper = vm.envOr("SHIPPER_ADDRESS", address(0x70997970C51812dc3A010C7d01b50e0d17dc79C8));
        address arbitrator = vm.envOr("ARBITRATOR_ADDRESS", address(0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC));
        address quoteSigner = vm.envOr("QUOTE_SIGNER_ADDRESS", address(0x90F79bf6EB2c4f870365E785982E1f101E93b906));
        address feeRecipient = vm.envOr("FEE_RECIPIENT_ADDRESS", address(0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65));
        address testBuyer = vm.envOr("TEST_BUYER_ADDRESS", address(0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc));
        address testMerchant = vm.envOr("TEST_MERCHANT_ADDRESS", address(0x976EA74026E726554dB657fA54763abd0C3a0aa9));
        uint256 buyerMint = vm.envOr("TEST_BUYER_MINT_RAW", uint256(1_000_000 * 10 ** 6)); // 1.000.000 MUSD

        uint256 startBlock = block.number;

        vm.startBroadcast(deployerKey);
        MockUSD usd = new MockUSD();
        SlopeeEscrowMaster escrow = new SlopeeEscrowMaster(admin, shipper, arbitrator, quoteSigner, feeRecipient);
        usd.mint(testBuyer, buyerMint);
        vm.stopBroadcast();

        // Ghi deployments/local.json cho backend, indexer và frontend cùng đọc (SDD 4.7, 8.1)
        string memory roles = "roles";
        vm.serializeAddress(roles, "admin", admin);
        vm.serializeAddress(roles, "shipper", shipper);
        vm.serializeAddress(roles, "arbitrator", arbitrator);
        vm.serializeAddress(roles, "quoteSigner", quoteSigner);
        string memory rolesJson = vm.serializeAddress(roles, "feeRecipient", feeRecipient);

        string memory testAccts = "testAccounts";
        vm.serializeAddress(testAccts, "buyer", testBuyer);
        string memory testJson = vm.serializeAddress(testAccts, "merchant", testMerchant);

        string memory token = "mockUSD";
        vm.serializeAddress(token, "address", address(usd));
        vm.serializeString(token, "symbol", "MUSD");
        string memory tokenJson = vm.serializeUint(token, "decimals", uint256(usd.decimals()));

        string memory root = "deployment";
        vm.serializeUint(root, "chainId", block.chainid);
        vm.serializeAddress(root, "escrow", address(escrow));
        vm.serializeAddress(root, "mockUSD", address(usd));
        // Chặn dưới của block triển khai: các giao dịch trên nằm ở block >= startBlock + 1.
        // Indexer đặt indexer_cursor.last_block = deployBlock - 1.
        vm.serializeUint(root, "deployBlock", startBlock + 1);
        vm.serializeString(root, "domainName", "SlopeeEscrow");
        vm.serializeString(root, "domainVersion", "1");
        vm.serializeString(root, "rolesNote", "Dia chi cac vai tro tren chuoi; khoa rieng nam trong backend/.env.web3 (chi cuc bo).");
        vm.serializeString(root, "token", tokenJson);
        vm.serializeString(root, "roles", rolesJson);
        string memory finalJson = vm.serializeString(root, "testAccounts", testJson);

        vm.writeJson(finalJson, "../deployments/local.json");

        console2.log("MockUSD :", address(usd));
        console2.log("Escrow  :", address(escrow));
    }
}
