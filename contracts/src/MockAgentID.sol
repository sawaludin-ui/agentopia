// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Testnet/local-only stand-in. NEVER present this as Binance Agent ID.
contract MockAgentID {
    address public immutable owner;
    mapping(address => uint256) public balanceOf;
    constructor(){owner=msg.sender;}
    function grant(address account) external {
        require(msg.sender==owner,"owner only");
        require(account!=address(0),"invalid address");
        balanceOf[account]=1;
    }
    function revoke(address account) external {
        require(msg.sender==owner,"owner only");
        balanceOf[account]=0;
    }
}
