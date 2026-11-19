// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/AgentopiaCore.sol";
import "../src/MockAgentID.sol";

contract AgentopiaCoreTest is Test {
    AgentopiaCore core;
    MockAgentID registry;
    uint256 oracleKey = 0xBEEF;
    uint256 aliceKey = 0xA11CE;
    address oracle;
    address alice;
    address bob = address(0xB0B);

    function setUp() public {
        registry = new MockAgentID();
        oracle = vm.addr(oracleKey);
        alice = vm.addr(aliceKey);
        core = new AgentopiaCore(address(registry),oracle);
        registry.grant(alice);
    }

    function testOnlyAgentHolderCanJoin() public {
        vm.prank(bob);
        vm.expectRevert(AgentopiaCore.NotAgentIDHolder.selector);
        core.joinCity();
        vm.prank(alice);
        core.joinCity();
        assertTrue(core.citizens(alice));
        vm.prank(alice);
        vm.expectRevert(AgentopiaCore.AlreadyJoined.selector);
        core.joinCity();
    }

    function _voucher(uint256 amount,bytes32 aid,uint256 deadline) internal returns(bytes memory) {
        bytes32 hash=core.hashContribution(alice,1,amount,aid,deadline);
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(oracleKey,hash);
        return abi.encodePacked(r,s,v);
    }

    function testSignedContributionAndReplayRejected() public {
        vm.prank(alice);core.joinCity();
        bytes32 aid=keccak256("once");
        uint256 deadline=block.timestamp+3600;
        bytes memory sig=_voucher(5,aid,deadline);
        vm.prank(alice);core.contribute(1,5,aid,deadline,sig);
        assertEq(core.progress(1),5);
        assertEq(core.contributionOf(alice),5);
        vm.prank(alice);
        vm.expectRevert(AgentopiaCore.VoucherAlreadyUsed.selector);
        core.contribute(1,5,aid,deadline,sig);
    }

    function testTamperedContributionFails() public {
        vm.prank(alice);core.joinCity();
        bytes32 aid=keccak256("tamper");uint256 deadline=block.timestamp+100;
        bytes memory sig=_voucher(5,aid,deadline);
        vm.prank(alice);
        vm.expectRevert(AgentopiaCore.InvalidVoucher.selector);
        core.contribute(1,6,aid,deadline,sig);
    }

    function testExpiredContributionFails() public {
        vm.prank(alice);core.joinCity();
        bytes32 aid=keccak256("late");uint256 deadline=block.timestamp+5;
        bytes memory sig=_voucher(5,aid,deadline);
        vm.warp(block.timestamp+6);
        vm.prank(alice);vm.expectRevert(AgentopiaCore.ExpiredVoucher.selector);
        core.contribute(1,5,aid,deadline,sig);
    }

    function testNoUnauthorizedOracleChange() public {
        vm.prank(bob);vm.expectRevert(AgentopiaCore.NotOwner.selector);
        core.setOracle(bob);
    }

    function testHolderRequiredOnEveryContribution() public {
        vm.prank(alice);core.joinCity();
        registry.revoke(alice);
        bytes32 aid=keccak256("revoked");uint256 deadline=block.timestamp+100;
        bytes memory sig=_voucher(5,aid,deadline);
        vm.prank(alice);vm.expectRevert(AgentopiaCore.NotAgentIDHolder.selector);
        core.contribute(1,5,aid,deadline,sig);
    }

    function testFuzzContributionBound(uint256 amount) public {
        vm.assume(amount == 0 || amount > 20);
        vm.prank(alice);core.joinCity();
        bytes32 aid=keccak256(abi.encode(amount));uint256 deadline=block.timestamp+100;
        vm.prank(alice);vm.expectRevert(AgentopiaCore.InvalidAmount.selector);
        core.contribute(1,amount,aid,deadline,hex"");
    }
}
