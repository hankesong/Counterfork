// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {InvestigationRegistry} from "../src/InvestigationRegistry.sol";

interface VmInvestigationRegistry {
    struct Log {
        bytes32[] topics;
        bytes data;
        address emitter;
    }
    function prank(address sender) external;
    function expectRevert(bytes4 selector) external;
    function expectRevert(bytes calldata data) external;
    function expectEmit(bool, bool, bool, bool, address) external;
    function recordLogs() external;
    function getRecordedLogs() external returns (Log[] memory);
    function warp(uint256 timestamp) external;
    function roll(uint256 blockNumber) external;
}

contract InvestigationRegistryTest {
    VmInvestigationRegistry constant vm =
        VmInvestigationRegistry(address(uint160(uint256(keccak256("hevm cheat code")))));
    InvestigationRegistry registry;
    bytes32 constant CASE = keccak256("compound-2020-11-26-dai");
    bytes32 constant MANIFEST = keccak256("TEST manifest");
    bytes32 constant RESULT = keccak256("TEST reproduction");
    address constant ALICE = address(0xA11CE);
    address constant BOB = address(0xB0B);

    event InvestigationSubmitted(bytes32 indexed caseId, uint256 version, address author, bytes32 manifestHash);
    event ReproductionAttested(bytes32 indexed caseId, uint256 version, address reproducer, bool matched);

    function setUp() public {
        registry = new InvestigationRegistry();
        vm.warp(1700000000);
        vm.roll(123);
    }

    function submit(bytes32 caseId) internal returns (uint256) {
        return registry.submitInvestigation(caseId, 1, 100, 200, MANIFEST, "ipfs://TEST-only");
    }

    function testVersionsAppendWithoutOverwrite() public {
        vm.prank(ALICE);
        require(submit(CASE) == 1, "first version");
        bytes32 beforeHash = keccak256(abi.encode(registry.getInvestigation(CASE, 1)));
        vm.warp(1700000010);
        vm.roll(124);
        vm.prank(BOB);
        require(registry.submitInvestigation(CASE, 968, 300, 400, RESULT, "TEST://v2") == 2, "second version");
        require(registry.latestVersion(CASE) == 2, "latest");
        require(keccak256(abi.encode(registry.getInvestigation(CASE, 1))) == beforeHash, "old version changed");
        InvestigationRegistry.Investigation memory second = registry.getInvestigation(CASE, 2);
        require(second.author == BOB && second.targetChainId == 968, "second author/chain");
        require(second.fromBlock == 300 && second.toBlock == 400 && second.manifestHash == RESULT, "second payload");
        require(second.timestamp == 1700000010 && second.blockNumber == 124, "second metadata");
        require(keccak256(bytes(second.manifestURI)) == keccak256("TEST://v2"), "second URI");
    }

    function testIndependentCasesAndZeroCaseId() public {
        require(submit(CASE) == 1 && submit(CASE) == 2, "case sequence");
        require(submit(bytes32(0)) == 1, "zero case allowed");
        require(registry.latestVersion(CASE) == 2 && registry.latestVersion(bytes32(0)) == 1, "independence");
        require(registry.latestVersion(RESULT) == 0, "unknown case latest");
    }

    function testInvalidBlockRange() public {
        vm.expectRevert(InvestigationRegistry.InvalidBlockRange.selector);
        registry.submitInvestigation(CASE, 1, 201, 200, MANIFEST, "TEST");
        require(registry.latestVersion(CASE) == 0, "failed submit advanced version");
    }

    function testEmptyManifestHash() public {
        vm.expectRevert(InvestigationRegistry.EmptyManifestHash.selector);
        registry.submitInvestigation(CASE, 1, 100, 200, bytes32(0), "TEST");
    }

    function testEmptyManifestURI() public {
        vm.expectRevert(InvestigationRegistry.EmptyManifestURI.selector);
        registry.submitInvestigation(CASE, 1, 100, 200, MANIFEST, "");
    }

    function testEqualBlockBoundsAndFullReadback() public {
        vm.prank(ALICE);
        registry.submitInvestigation(CASE, 1, 0, 0, MANIFEST, "TEST");
        InvestigationRegistry.Investigation memory item = registry.getInvestigation(CASE, 1);
        require(item.author == ALICE && item.targetChainId == 1, "identity");
        require(item.fromBlock == 0 && item.toBlock == 0, "range");
        require(item.manifestHash == MANIFEST && keccak256(bytes(item.manifestURI)) == keccak256("TEST"), "manifest");
        require(item.timestamp == 1700000000 && item.blockNumber == 123, "metadata");
        require(registry.attestationCount(CASE, 1) == 0 && !registry.hasAttested(CASE, 1, ALICE), "empty attestations");
    }

    function testSubmissionEventExactLayout() public {
        vm.expectEmit(true, false, false, true, address(registry));
        emit InvestigationSubmitted(CASE, 1, ALICE, MANIFEST);
        vm.recordLogs();
        vm.prank(ALICE);
        submit(CASE);
        VmInvestigationRegistry.Log[] memory logs = vm.getRecordedLogs();
        require(logs.length == 1 && logs[0].topics.length == 2, "only case indexed");
        require(logs[0].topics[0] == keccak256("InvestigationSubmitted(bytes32,uint256,address,bytes32)"), "signature");
        require(logs[0].topics[1] == CASE && logs[0].emitter == address(registry), "topic/emitter");
        require(keccak256(logs[0].data) == keccak256(abi.encode(uint256(1), ALICE, MANIFEST)), "event data");
    }

    function testAttestMissingVersion() public {
        vm.expectRevert(abi.encodeWithSelector(InvestigationRegistry.InvestigationNotFound.selector, CASE, 1));
        registry.attestReproduction(CASE, 1, true, RESULT);
        submit(CASE);
        vm.expectRevert(abi.encodeWithSelector(InvestigationRegistry.InvestigationNotFound.selector, CASE, 0));
        registry.attestReproduction(CASE, 0, true, RESULT);
        vm.expectRevert(abi.encodeWithSelector(InvestigationRegistry.InvestigationNotFound.selector, CASE, 2));
        registry.attestReproduction(CASE, 2, false, RESULT);
    }

    function testEmptyResultHashDoesNotConsumeSlot() public {
        submit(CASE);
        vm.expectRevert(InvestigationRegistry.EmptyResultHash.selector);
        vm.prank(ALICE);
        registry.attestReproduction(CASE, 1, true, bytes32(0));
        require(!registry.hasAttested(CASE, 1, ALICE) && registry.attestationCount(CASE, 1) == 0, "slot consumed");
        vm.prank(ALICE);
        registry.attestReproduction(CASE, 1, true, RESULT);
    }

    function testDuplicateReproductionReverts() public {
        submit(CASE);
        vm.prank(ALICE);
        registry.attestReproduction(CASE, 1, true, RESULT);
        vm.expectRevert(abi.encodeWithSelector(InvestigationRegistry.AlreadyAttested.selector, CASE, 1, ALICE));
        vm.prank(ALICE);
        registry.attestReproduction(CASE, 1, false, MANIFEST);
        require(registry.attestationCount(CASE, 1) == 1, "duplicate stored");
        require(registry.getAttestation(CASE, 1, 0).matched, "old attestation overwritten");
    }

    function testTwoReproducersAndBothOutcomes() public {
        submit(CASE);
        vm.prank(ALICE);
        registry.attestReproduction(CASE, 1, true, RESULT);
        vm.warp(1700000020);
        vm.roll(130);
        vm.prank(BOB);
        registry.attestReproduction(CASE, 1, false, MANIFEST);
        InvestigationRegistry.Attestation memory first = registry.getAttestation(CASE, 1, 0);
        InvestigationRegistry.Attestation memory second = registry.getAttestation(CASE, 1, 1);
        require(first.reproducer == ALICE && first.matched && first.resultHash == RESULT, "first content");
        require(first.timestamp == 1700000000 && first.blockNumber == 123, "first metadata");
        require(second.reproducer == BOB && !second.matched && second.resultHash == MANIFEST, "second content");
        require(second.timestamp == 1700000020 && second.blockNumber == 130, "second metadata");
        require(registry.attestationCount(CASE, 1) == 2, "count");
        require(registry.hasAttested(CASE, 1, ALICE) && registry.hasAttested(CASE, 1, BOB), "membership");
        require(!registry.hasAttested(CASE, 1, address(this)), "unknown reproducer");
    }

    function testAttestationScopeIsCaseAndVersion() public {
        submit(CASE);
        submit(CASE);
        submit(RESULT);
        vm.prank(ALICE);
        registry.attestReproduction(CASE, 1, true, RESULT);
        require(!registry.hasAttested(CASE, 2, ALICE) && !registry.hasAttested(RESULT, 1, ALICE), "scope leaked");
        vm.prank(ALICE);
        registry.attestReproduction(CASE, 2, false, RESULT);
        vm.prank(ALICE);
        registry.attestReproduction(RESULT, 1, false, RESULT);
        require(registry.attestationCount(CASE, 1) == 1 && registry.attestationCount(CASE, 2) == 1, "version counts");
        require(registry.attestationCount(RESULT, 1) == 1, "case count");
    }

    function testAttestationEventsBothOutcomes() public {
        submit(CASE);
        vm.expectEmit(true, false, false, true, address(registry));
        emit ReproductionAttested(CASE, 1, ALICE, true);
        vm.prank(ALICE);
        registry.attestReproduction(CASE, 1, true, RESULT);
        vm.expectEmit(true, false, false, true, address(registry));
        emit ReproductionAttested(CASE, 1, BOB, false);
        vm.recordLogs();
        vm.prank(BOB);
        registry.attestReproduction(CASE, 1, false, RESULT);
        VmInvestigationRegistry.Log[] memory logs = vm.getRecordedLogs();
        require(logs.length == 1 && logs[0].topics.length == 2, "only case indexed");
        require(logs[0].topics[0] == keccak256("ReproductionAttested(bytes32,uint256,address,bool)"), "signature");
        require(logs[0].topics[1] == CASE && logs[0].emitter == address(registry), "topic/emitter");
        require(keccak256(logs[0].data) == keccak256(abi.encode(uint256(1), BOB, false)), "event data");
    }

    function testMissingReadAndOutOfBounds() public {
        bytes memory missing = abi.encodeWithSelector(InvestigationRegistry.InvestigationNotFound.selector, CASE, 0);
        vm.expectRevert(missing);
        registry.getInvestigation(CASE, 0);
        vm.expectRevert(missing);
        registry.attestationCount(CASE, 0);
        vm.expectRevert(missing);
        registry.hasAttested(CASE, 0, ALICE);
        vm.expectRevert(missing);
        registry.getAttestation(CASE, 0, 0);
        submit(CASE);
        vm.expectRevert(abi.encodeWithSelector(InvestigationRegistry.AttestationIndexOutOfBounds.selector, 0));
        registry.getAttestation(CASE, 1, 0);
    }

    function testFuzzVersionsStrictlyIncrease(bytes32 caseId, uint256 a, uint256 b, uint8 countSeed) public {
        (uint256 fromBlock, uint256 toBlock) = a <= b ? (a, b) : (b, a);
        uint256 count = uint256(countSeed % 16) + 2;
        for (uint256 i = 1; i <= count; ++i) {
            uint256 version = registry.submitInvestigation(caseId, 1, fromBlock, toBlock, MANIFEST, "TEST fuzz");
            require(version == i && registry.latestVersion(caseId) == i, "non-increasing version");
        }
        InvestigationRegistry.Investigation memory first = registry.getInvestigation(caseId, 1);
        require(first.fromBlock == fromBlock && first.toBlock == toBlock, "first range changed");
    }
}
