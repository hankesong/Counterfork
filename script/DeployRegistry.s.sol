// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {InvestigationRegistry} from "../src/InvestigationRegistry.sol";

interface VmDeployRegistry {
    function envUint(string calldata name) external returns (uint256);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

contract DeployRegistry {
    VmDeployRegistry constant vm = VmDeployRegistry(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run() external returns (InvestigationRegistry registry) {
        uint256 privateKey = vm.envUint("BOT_PRIVATE_KEY");
        vm.startBroadcast(privateKey);
        registry = new InvestigationRegistry();
        vm.stopBroadcast();
    }
}
