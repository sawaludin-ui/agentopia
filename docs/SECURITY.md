# Threat Model — AGENTOPIA MVP

**Trust boundaries:** browser (untrusted) → FastAPI (trusted gameplay) → SQLite (state) → BNB RPC (untrusted responses need verification) → AgentopiaCore (on-chain logic) → user wallet (user-exclusive signing).

## Threats and existing controls

| Threat | MVP control | Residual risk |
|---|---|---|
| Forged client coordinates | Browser sends directional input, server updates position + collision at a capped speed | Movement speed/teleport should be load-tested against network abuse |
| Material duplication | SQLite immediate transactions, unique cooldowns, inventory mutation server-only | Single-process SQLite won't scale to multi-region writes |
| CSRF/session theft | HTTP-only SameSite cookie; JSON-only state mutations; WS Origin check; secure cookie production | Deploy behind HTTPS, HSTS, anti-XSS and robust session management |
| Chat XSS | Escaped via DOM `textContent`, printable filter, length cap | Spam/content moderation is basic |
| Wallet spoofing | EIP-712 challenge recovered address, nonce, 5 min expiry, Agent ID `balanceOf` check | Some Agentic Wallets may not support streamlined signing |
| Replay voucher | EIP-712 typed data binds chain and contract, unique actionId on chain | Trusted oracle can issue multiple distinct vouchers |
| Manipulated activity | Server-authoritative gathering + inventory | Determined bot may still farm legitimately repeated actions |
| Stolen oracle secret | Server secret env, rotateable oracle | Compromise allows fraudulent scoring, not direct asset theft |
| User wallet theft | No user keys/pairing codes, no token approvals/transfers | Custom transaction must still be reviewed by user |
| RPC outage | Fails closed on holder verification and confirmation | Temporarily blocks blockchain actions |
| Transaction failing | Reserved materials and receipt checks; safe expiry cancel after checking on-chain replay state | If RPC unavailable, materials cannot be automatically released; support needed |
| Distributed DoS | Server per-room cap, simple signup and chat rate limits | Public launch needs edge DDoS protection and monitoring |
| Sybil scoring | Real holder requirement on contract | Agent ID alone does not prove one human; avoid manufactured traffic |

## Administrative permissions

**GameCore owner** can rotate the oracle address, change proof targets, and transfer ownership. **Oracle** can issue signed contribution vouchers. Both are centralized powers and should be disclosed clearly. The contract has *no methods to withdraw tokens or call ERC-20 approve*. On-chain reputation proofs are not equivalent to trustless gameplay validation.

## Production release blockers

1. Run Foundry Solidity tests and external Solidity audit before mainnet.
2. Test actual wallet EIP-712 compatibility and `contract-call` with a separate user-controlled wallet.
3. Test identity revocation and recovery, on-chain reorgs, pending transactions, safe voucher expiry and refund.
4. Add systematic chat moderation, block/report features, privacy policy, deletion procedure for off-chain data, data retention schedule.
5. Apply HTTPS/HSTS, reverse proxy limits, monitoring, rate limits across distributed workers, secret manager, backups, restore drill, and operations runbook.
6. Run actual browser E2E tests on desktop and mobile, including accessibility and touch inputs.
7. Run third-party contract security analysis and static tests in an environment with a Solidity compiler.

Do not classify this prototype as audited or production-safe until these blockers are resolved.
