// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface VmPhase1 {
    function envString(string calldata) external returns (string memory);
    function envUint(string calldata) external returns (uint256);
    function envAddress(string calldata) external returns (address);
    function createSelectFork(string calldata, uint256) external returns (uint256);
    function mockCall(address, bytes calldata, bytes calldata) external;
    function clearMockedCalls() external;
    function toString(address) external pure returns (string memory);
    function toString(uint256) external pure returns (string memory);
    function writeJson(string calldata, string calldata) external;
}
interface ComptrollerPhase1 {
    function oracle() external view returns (address);
    function getAccountLiquidity(address) external view returns (uint256, uint256, uint256);
}
interface OraclePhase1 {
    function getUnderlyingPrice(address) external view returns (uint256);
}
interface CTokenPhase1 { function underlying() external view returns (address); }
interface TokenPhase1 { function decimals() external view returns (uint8); }

/// All groups share N-1 state. Only oracle return values are overridden.
contract Phase1Test {
    VmPhase1 constant vm = VmPhase1(address(uint160(uint256(keccak256("hevm cheat code")))));
    address oracle;
    address cdai;
    address borrower;
    ComptrollerPhase1 comptroller;

    function setPrice(address market, uint256 price) internal {
        vm.mockCall(oracle, abi.encodeWithSelector(OraclePhase1.getUnderlyingPrice.selector, market), abi.encode(price));
        require(OraclePhase1(oracle).getUnderlyingPrice(market) == price, "mock readback failed");
    }

    function group() internal view returns (string memory) {
        (uint256 err, uint256 liquidity, uint256 shortfall) = comptroller.getAccountLiquidity(borrower);
        return string.concat('{"dai_price_raw":"', vm.toString(OraclePhase1(oracle).getUnderlyingPrice(cdai)),
            '","err":"', vm.toString(err), '","liquidity":"', vm.toString(liquidity),
            '","shortfall":"', vm.toString(shortfall), '"}');
    }

    function testSingleAccount() public {
        uint256 n = vm.envUint("PHASE1_BLOCK");
        vm.createSelectFork(vm.envString("ETH_RPC_URL"), n);
        require(block.chainid == 1 && block.number == n, "wrong fork");
        require(block.timestamp == vm.envUint("PHASE1_TIMESTAMP"), "wrong timestamp");
        comptroller = ComptrollerPhase1(vm.envAddress("PHASE1_COMPTROLLER"));
        cdai = vm.envAddress("PHASE1_CDAI");
        borrower = vm.envAddress("PHASE1_BORROWER");
        oracle = comptroller.oracle();
        require(oracle == vm.envAddress("PHASE1_ORACLE") && oracle.code.length > 0, "wrong oracle");
        address underlying = CTokenPhase1(cdai).underlying();
        require(underlying == vm.envAddress("PHASE1_DAI"), "wrong underlying");
        require(TokenPhase1(underlying).decimals() == 18, "wrong decimals");
        require(OraclePhase1(oracle).getUnderlyingPrice(cdai) == vm.envUint("PHASE1_REFERENCE_PRICE"), "wrong original price");
        string memory referenceGroup = group();
        uint256 actual = vm.envUint("PHASE1_ACTUAL_PRICE");
        setPrice(cdai, actual);
        string memory realGroup = group();
        vm.clearMockedCalls();
        setPrice(cdai, 1e18);
        string memory counterfactual = group();
        vm.clearMockedCalls();
        string memory diagnostic = "null";
        uint256 count = vm.envUint("PHASE1_DIAGNOSTIC_COUNT");
        if (count > 0) {
            setPrice(cdai, actual);
            for (uint256 i; i < count; i++) {
                string memory suffix = vm.toString(i);
                setPrice(vm.envAddress(string.concat("PHASE1_MARKET_", suffix)),
                    vm.envUint(string.concat("PHASE1_PRICE_", suffix)));
            }
            require(OraclePhase1(oracle).getUnderlyingPrice(cdai) == actual, "diagnostic DAI mismatch");
            diagnostic = string.concat('{"diagnostic_only":true,"result":', group(), '}');
        }
        vm.clearMockedCalls();
        vm.writeJson(string.concat('{"block":"', vm.toString(block.number), '","timestamp":"',
            vm.toString(block.timestamp), '","oracle":"', vm.toString(oracle), '","underlying":"',
            vm.toString(underlying), '","underlying_decimals":"18","reference":', referenceGroup,
            ',"real":', realGroup, ',"counterfactual":', counterfactual, ',"diagnostic":', diagnostic, '}'),
            "data/phase1/fork_result.json");
        // Acceptance is evaluated by Python after preserving all diagnostic groups.
    }
}
