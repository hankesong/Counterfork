// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice Permissionless, append-only investigation and reproduction registry.
/// @dev This contract only registers claims; it does not validate manifest contents.
/// Credibility comes from independent reproduction by multiple parties.
/// No administrator, upgrade mechanism, or payable entry point is provided.
contract InvestigationRegistry {
    struct Investigation {
        address author;
        uint256 targetChainId;
        uint256 fromBlock;
        uint256 toBlock;
        bytes32 manifestHash;
        string manifestURI;
        uint256 timestamp;
        uint256 blockNumber;
    }

    struct Attestation {
        address reproducer;
        bool matched;
        bytes32 resultHash;
        uint256 timestamp;
        uint256 blockNumber;
    }

    error InvalidBlockRange();
    error EmptyManifestHash();
    error EmptyManifestURI();
    error InvestigationNotFound(bytes32 caseId, uint256 version);
    error AlreadyAttested(bytes32 caseId, uint256 version, address reproducer);
    error EmptyResultHash();
    error AttestationIndexOutOfBounds(uint256 index);

    event InvestigationSubmitted(bytes32 indexed caseId, uint256 version, address author, bytes32 manifestHash);
    event ReproductionAttested(bytes32 indexed caseId, uint256 version, address reproducer, bool matched);

    mapping(bytes32 => uint256) public latestVersion;
    mapping(bytes32 => mapping(uint256 => Investigation)) private investigations;
    mapping(bytes32 => mapping(uint256 => Attestation[])) private attestations;
    mapping(bytes32 => mapping(uint256 => mapping(address => bool))) private attested;

    function submitInvestigation(
        bytes32 caseId,
        uint256 targetChainId,
        uint256 fromBlock,
        uint256 toBlock,
        bytes32 manifestHash,
        string calldata manifestURI
    ) external returns (uint256 version) {
        if (fromBlock > toBlock) revert InvalidBlockRange();
        if (manifestHash == bytes32(0)) revert EmptyManifestHash();
        if (bytes(manifestURI).length == 0) revert EmptyManifestURI();

        version = ++latestVersion[caseId];
        investigations[caseId][version] = Investigation({
            author: msg.sender,
            targetChainId: targetChainId,
            fromBlock: fromBlock,
            toBlock: toBlock,
            manifestHash: manifestHash,
            manifestURI: manifestURI,
            timestamp: block.timestamp,
            blockNumber: block.number
        });
        emit InvestigationSubmitted(caseId, version, msg.sender, manifestHash);
    }

    function attestReproduction(bytes32 caseId, uint256 version, bool matched, bytes32 resultHash) external {
        requireInvestigation(caseId, version);
        if (attested[caseId][version][msg.sender]) revert AlreadyAttested(caseId, version, msg.sender);
        if (resultHash == bytes32(0)) revert EmptyResultHash();

        attested[caseId][version][msg.sender] = true;
        attestations[caseId][version].push(Attestation(msg.sender, matched, resultHash, block.timestamp, block.number));
        emit ReproductionAttested(caseId, version, msg.sender, matched);
    }

    function getInvestigation(bytes32 caseId, uint256 version) external view returns (Investigation memory) {
        requireInvestigation(caseId, version);
        return investigations[caseId][version];
    }

    function attestationCount(bytes32 caseId, uint256 version) external view returns (uint256) {
        requireInvestigation(caseId, version);
        return attestations[caseId][version].length;
    }

    function getAttestation(bytes32 caseId, uint256 version, uint256 index) external view returns (Attestation memory) {
        requireInvestigation(caseId, version);
        if (index >= attestations[caseId][version].length) revert AttestationIndexOutOfBounds(index);
        return attestations[caseId][version][index];
    }

    function hasAttested(bytes32 caseId, uint256 version, address reproducer) external view returns (bool) {
        requireInvestigation(caseId, version);
        return attested[caseId][version][reproducer];
    }

    function requireInvestigation(bytes32 caseId, uint256 version) private view {
        if (version == 0 || version > latestVersion[caseId]) revert InvestigationNotFound(caseId, version);
    }
}
