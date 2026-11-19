// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title AgentopiaCore
 * @notice Non-custodial community proof contract for the AGENTOPIA game.
 *         Agent ID owners join directly; a trusted game oracle signs achievement
 *         vouchers for validated in-game activities. This is NOT trustless game
 *         state verification. No tokens, NFTs, deposits, or asset approvals.
 * @dev Source is standalone (no npm or OpenZeppelin import required).
 */
interface IAgentIDRegistry {
    function balanceOf(address owner) external view returns (uint256);
}

contract AgentopiaCore {
    IAgentIDRegistry public immutable agentID;
    address public owner;
    address public oracle;

    bytes32 private constant EIP712_DOMAIN_TYPEHASH = keccak256(
        "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
    );
    bytes32 public constant CONTRIBUTION_TYPEHASH = keccak256(
        "Contribution(address player,uint256 buildingId,uint256 amount,bytes32 actionId,uint256 deadline)"
    );
    bytes32 private constant NAME_HASH = keccak256("Agentopia");
    bytes32 private constant VERSION_HASH = keccak256("1");
    uint256 private constant SECP256K1N_HALF =
        0x7fffffffffffffffffffffffffffffff5d576e7357a4501ddfe92f46681b20a0;

    mapping(address => bool) public citizens;
    mapping(address => uint256) public contributionOf;
    mapping(bytes32 => bool) public usedActions;
    mapping(uint256 => uint256) public progress;
    mapping(uint256 => uint256) public targets;

    event CitizenJoined(address indexed player);
    event Contributed(address indexed player, uint256 indexed buildingId, uint256 amount, bytes32 actionId);
    event OwnerTransferred(address indexed previousOwner,address indexed newOwner);
    event OracleChanged(address indexed previousOracle,address indexed newOracle);
    event BuildingConfigured(uint256 indexed buildingId,uint256 target);

    error NotOwner();
    error NotAgentIDHolder();
    error BadAddress();
    error AlreadyJoined();
    error NotCitizen();
    error InvalidAmount();
    error InvalidBuilding();
    error ExpiredVoucher();
    error VoucherAlreadyUsed();
    error InvalidVoucher();

    constructor(address registry,address initialOracle) {
        if (registry == address(0) || initialOracle == address(0) || registry.code.length == 0)
            revert BadAddress();
        agentID = IAgentIDRegistry(registry);
        owner = msg.sender;
        oracle = initialOracle;
        targets[1] = 10_000; // Season-wide proof cap; distinct from off-chain bridge progress.
        emit OwnerTransferred(address(0),msg.sender);
        emit OracleChanged(address(0),initialOracle);
        emit BuildingConfigured(1,10_000);
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyHolder() {
        if (agentID.balanceOf(msg.sender) == 0) revert NotAgentIDHolder();
        _;
    }

    function isAgentHolder(address account) external view returns (bool) {
        return agentID.balanceOf(account) > 0;
    }

    function joinCity() external onlyHolder {
        if (citizens[msg.sender]) revert AlreadyJoined();
        citizens[msg.sender] = true;
        emit CitizenJoined(msg.sender);
    }

    function domainSeparator() public view returns (bytes32) {
        return keccak256(abi.encode(
            EIP712_DOMAIN_TYPEHASH, NAME_HASH, VERSION_HASH, block.chainid, address(this)
        ));
    }

    function hashContribution(
        address player, uint256 buildingId, uint256 amount,bytes32 actionId,uint256 deadline
    ) public view returns(bytes32) {
        bytes32 structHash = keccak256(abi.encode(
            CONTRIBUTION_TYPEHASH,player,buildingId,amount,actionId,deadline
        ));
        return keccak256(abi.encodePacked("\x19\x01",domainSeparator(),structHash));
    }

    function contribute(
        uint256 buildingId,uint256 amount,bytes32 actionId,uint256 deadline,bytes calldata signature
    ) external onlyHolder {
        if (!citizens[msg.sender]) revert NotCitizen();
        if (amount == 0 || amount > 20) revert InvalidAmount();
        if (targets[buildingId] == 0 || progress[buildingId] + amount > targets[buildingId])
            revert InvalidBuilding();
        if (block.timestamp > deadline) revert ExpiredVoucher();
        if (usedActions[actionId]) revert VoucherAlreadyUsed();
        bytes32 digest = hashContribution(msg.sender,buildingId,amount,actionId,deadline);
        if (_recover(digest,signature) != oracle) revert InvalidVoucher();

        usedActions[actionId] = true;
        progress[buildingId] += amount;
        contributionOf[msg.sender] += amount;
        emit Contributed(msg.sender,buildingId,amount,actionId);
    }

    function _recover(bytes32 digest,bytes calldata signature) private pure returns(address signer) {
        if(signature.length != 65) return address(0);
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset,32))
            v := byte(0,calldataload(add(signature.offset,64)))
        }
        if (uint256(s) == 0 || uint256(s) > SECP256K1N_HALF) return address(0);
        if (v != 27 && v != 28) return address(0);
        return ecrecover(digest,v,r,s);
    }

    function configureBuilding(uint256 buildingId,uint256 target) external onlyOwner {
        if (buildingId == 0 || target <= progress[buildingId]) revert InvalidBuilding();
        targets[buildingId] = target;
        emit BuildingConfigured(buildingId,target);
    }

    function setOracle(address newOracle) external onlyOwner {
        if (newOracle == address(0)) revert BadAddress();
        emit OracleChanged(oracle,newOracle);
        oracle = newOracle;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert BadAddress();
        emit OwnerTransferred(owner,newOwner);
        owner = newOwner;
    }
}
