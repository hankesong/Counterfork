// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
import "./Phase1.t.sol";

/// One fork and one test per borrower; all formal and diagnostic groups share state.
contract Phase3Test is Phase1Test {
    bool protocolError;
    function atPrice(uint256 price) internal returns (string memory result, int256 balance) {
        vm.clearMockedCalls();
        setPrice(cdai, price);
        result = group();
        (uint256 err, uint256 liquid, uint256 shortfall) = comptroller.getAccountLiquidity(borrower);
        if (err != 0) protocolError = true;
        balance = int256(liquid) - int256(shortfall);
    }

    function threshold(uint256[5] memory prices, int256[5] memory balances) internal returns (string memory) {
        if (protocolError) return '{"price_raw":null,"reason":"protocol error in sensitivity group"}';
        int256 delta = balances[4] - balances[0];
        if (delta >= 0) return '{"price_raw":null,"reason":"no decreasing DAI exposure"}';
        for (uint256 i = 1; i < 4; i++) {
            int256 expected = balances[0] + delta * int256(prices[i] - prices[0]) / int256(prices[4] - prices[0]);
            int256 residual = balances[i] - expected;
            if (residual > 1e10 || residual < -1e10)
                return '{"price_raw":null,"reason":"nonlinear beyond 1e-8 USD rounding tolerance"}';
        }
        int256 candidate = int256(prices[0]) - balances[0] * int256(prices[4] - prices[0]) / delta;
        if (candidate <= 1e14) return '{"price_raw":null,"reason":"nonpositive or untestable critical price"}';
        (string memory below, int256 low) = atPrice(uint256(candidate) - 1e14);
        (string memory above, int256 high) = atPrice(uint256(candidate) + 1e14);
        bool flipped = !protocolError && low > 0 && high < 0;
        return string.concat('{"price_raw":', flipped ? string.concat('"', vm.toString(uint256(candidate)), '"') : 'null',
            ',"candidate_raw":"', vm.toString(uint256(candidate)), '","derived":true,"epsilon_raw":"100000000000000",',
            '"linear_tolerance_usd":"0.00000001","sign_flip":', flipped ? 'true' : 'false',
            ',"reason":"', flipped ? 'verified sign flip' : 'validation did not flip', '","below":', below, ',"above":', above, '}');
    }

    function testBatchAccount() public {
        uint256 n = vm.envUint("PHASE1_BLOCK");
        vm.createSelectFork(vm.envString("ETH_RPC_URL"), n);
        require(block.chainid == 1 && block.number == n, "wrong fork");
        require(block.timestamp == vm.envUint("PHASE1_TIMESTAMP"), "wrong timestamp");
        comptroller = ComptrollerPhase1(vm.envAddress("PHASE1_COMPTROLLER"));
        cdai = vm.envAddress("PHASE1_CDAI");
        borrower = vm.envAddress("PHASE1_BORROWER");
        oracle = comptroller.oracle();
        require(oracle == vm.envAddress("PHASE1_ORACLE"), "wrong oracle");
        address underlying = CTokenPhase1(cdai).underlying();
        require(underlying == vm.envAddress("PHASE1_DAI") && TokenPhase1(underlying).decimals() == 18, "wrong DAI");
        vm.clearMockedCalls();
        require(OraclePhase1(oracle).getUnderlyingPrice(cdai) == vm.envUint("PHASE1_REFERENCE_PRICE"), "wrong original price");
        string memory referenceGroup = group();
        vm.clearMockedCalls();
        setPrice(cdai, vm.envUint("PHASE1_ACTUAL_PRICE"));
        string memory realGroup = group();
        uint256[5] memory prices = [uint256(1e18), 1.05e18, 1.10e18, 1.20e18, 1.30e18];
        int256[5] memory balances;
        string memory sensitivity = '[';
        for (uint256 i; i < 5; i++) {
            (string memory result, int256 balance) = atPrice(prices[i]);
            balances[i] = balance;
            sensitivity = string.concat(sensitivity, i == 0 ? '' : ',', result);
        }
        sensitivity = string.concat(sensitivity, ']');
        string memory critical = threshold(prices, balances);
        vm.clearMockedCalls();
        string memory diagnostic = 'null';
        uint256 count = vm.envUint("PHASE1_DIAGNOSTIC_COUNT");
        if (count > 0) {
            setPrice(cdai, vm.envUint("PHASE1_ACTUAL_PRICE"));
            for (uint256 i; i < count; i++) {
                string memory suffix = vm.toString(i);
                setPrice(vm.envAddress(string.concat("PHASE1_MARKET_", suffix)), vm.envUint(string.concat("PHASE1_PRICE_", suffix)));
            }
            diagnostic = string.concat('{"diagnostic_only":true,"result":', group(), '}');
        }
        vm.clearMockedCalls();
        vm.writeJson(string.concat('{"block":"', vm.toString(block.number), '","oracle":"', vm.toString(oracle),
            '","underlying":"', vm.toString(underlying), '","underlying_decimals":"18","reference":', referenceGroup,
            ',"real":', realGroup, ',"sensitivity":', sensitivity, ',"critical_price":', critical, ',"diagnostic":', diagnostic, '}'),
            vm.envString("PHASE3_OUTPUT"));
    }
}
