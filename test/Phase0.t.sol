// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface Vm {
    function envString(string calldata) external returns (string memory);
    function envUint(string calldata) external returns (uint256);
    function envAddress(string calldata) external returns (address);
    function createSelectFork(string calldata, uint256) external returns (uint256);
    function toString(address) external pure returns (string memory);
    function toString(uint256) external pure returns (string memory);
    function writeJson(string calldata, string calldata) external;
}

interface Comptroller {
    function oracle() external view returns (address);
}

interface Oracle {
    function getUnderlyingPrice(address) external view returns (uint256);
}

interface CToken {
    function underlying() external view returns (address);
}

interface Token {
    function decimals() external view returns (uint8);
}

/// Historical environment check only. No price override or account experiment.
contract Phase0Test {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    function testHistoricalOracle() public {
        uint256 n = vm.envUint("PHASE0_BLOCK");
        vm.createSelectFork(vm.envString("ETH_RPC_URL"), n);
        require(block.chainid == 1 && block.number == n, "wrong fork");
        require(block.timestamp == vm.envUint("PHASE0_TIMESTAMP"), "wrong timestamp");
        address cdai = vm.envAddress("PHASE0_CDAI");
        address oracle = Comptroller(vm.envAddress("PHASE0_COMPTROLLER")).oracle();
        require(oracle != address(0) && oracle.code.length > 0, "missing oracle");
        address underlying = CToken(cdai).underlying();
        uint8 decimals = Token(underlying).decimals();
        require(decimals == 18, "unexpected DAI decimals");
        uint256 price = Oracle(oracle).getUnderlyingPrice(cdai);
        require(price > 0, "zero price");
        vm.writeJson(
            string.concat(
                '{"oracle":"',
                vm.toString(oracle),
                '","dai_price_raw":"',
                vm.toString(price),
                '","underlying":"',
                vm.toString(underlying),
                '","underlying_decimals":18,"block":',
                vm.toString(block.number),
                ',"timestamp":',
                vm.toString(block.timestamp),
                "}"
            ),
            "data/phase0/fork_read.json"
        );
    }
}
