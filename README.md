# AGENTOPIA — First Settlement 🌻

An original, multiplayer, browser-based social village game for the **BNB Chain Agent ID Hackathon 2026**. A small world where people gather resources, meet friends, and rebuild a community bridge. Verified Agent ID holders can independently authorize on-chain citizen registration and contribution proofs.

**Status as of 20 Nov 2026:** `AgentopiaCore` **deployed on BNB Chain mainnet (chainId 56)** at [`0x76b2fd65304a780bb46922a1e05c14848f6d7582`](https://bscscan.com/address/0x76b2fd65304a780bb46922a1e05c14848f6d7582) via CreateX `deployCreate2AndInit` (tx [`0x9cb9ff76b970ae128bfe6670616922bb624678a11c856760f9e86fcad68d173a`](https://bscscan.com/tx/0x9cb9ff76b970ae128bfe6670616922bb624678a11c856760f9e86fcad68d173a), block 134544244). Owner and initial oracle: `0x607cF25614065179a9238705E03E6590C082F56d`; registry: official Agent ID `0x60b9262456de011f7d15a54cdd8c48baaa8b022f`. BscScan source verification and public hosting are in progress. Local playable MVP runs via the instructions below; the demo's mock Agent ID registry is **not valid for hackathon eligibility**. See [Test report](docs/TEST_REPORT.md).

## What works today

- Browser multiplayer canvas game with original drawn assets and touch-friendly camera
- Guest onboarding, six character appearances, editable nickname
- Server-authoritative WASD/touch movement, chat, live online presence
- Three resource nodes with 6-second per-player harvest cooldown
- Inventory, community bridge building, worldwide progress, leaderboard
- Guide NPC PIX (rule-based; explicitly **not** an autonomous crypto trading agent)
- SQLite persistence, hashed HTTP-only session cookies, WebSocket authentication
- EIP-712 challenge identity binding and on-chain `balanceOf` Agent ID eligibility check
- Solidity `AgentopiaCore` registration and oracle-signed contribution proof contract
- Browser-wallet-compatible data prepared for `joinCity()`/`contribute()` calls; calldata export for manual Agentic Wallet execution
- On-chain receipt reconciler, 2-block wait, contract event validation, action replay protection, recover-expired flow
- Automated Python unit/integration tests and live multiplayer smoke/load scripts

## Start in 2 minutes (local)

### Windows
1. Install **Python 3.11 or later** (check “Add Python to PATH”).
2. Extract the ZIP to a folder that you control.
3. Double-click `RUN-WINDOWS.bat` (it installs dependencies in local `.venv`).
4. Open **http://127.0.0.1:8000**.
5. Open a second browser/private window, create another guest, and walk with WASD to see multiplayer.

### macOS / Linux

```bash
./RUN-LINUX-MAC.sh
# or manually:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The local server is for development. In default **mock** identity mode no wallet address is considered an Agent ID holder unless added to `AGENTOPIA_MOCK_HOLDERS`. Never use this mode in public production; the code refuses to start in non-development environments with the mock option.

## How to play

| Action | Control |
|---|---|
| Move | `WASD` or arrow keys, touch direction pad |
| Harvest near a node | `E` |
| Open bridge building near construction marker | `B` |
| Talk with PIX | `P` |
| Send chat | `Enter`, type, press Enter |
| Change appearance | Passport pencil button |
| Verify Agent ID | Top-right `Verify Agent ID` |

The actual resource nodes are the large tree west of the town square, the quarry east of it, and the energy reactor below the plaza. Gather several materials, then walk east to the construction marker near the river to contribute.

## Architecture

```text
Browser (HTML/CSS/Canvas JS)
    | HTTP + authenticated WebSocket
FastAPI server (single process; authoritative movement & gameplay)
    | SQLite WAL
    | EIP-712 challenge verification
    | RPC read → Agent ID registry
    | oracle-signed contribution proof
    | RPC event/receipt verification
BNB Chain (separate user-approved transactions)
    ├─ official Agent ID ERC-721 registry (mainnet)
    └─ AgentopiaCore smart contract
```

**Why no Phaser/React in this build?** The build environment had no access to npm. A dependency-free Canvas client made it possible to produce a genuinely runnable game and validate the server immediately. It is not a commitment against adding a game engine later. The MVP is a **single-server game** capped at 60 simultaneous sockets; for thousands of players, replace the in-memory room with horizontal multiplayer infrastructure.

**Two different progress numbers:** the bridge is a game-server community target of 160; the smart contract has a separate season-wide ceiling of 10,000 verified contribution points. Confirmed on-chain contributions count toward local bridge progress, capped at 160. Unverified guest contributions work off-chain. There is no NFT or saleable token economy.

## Agent ID model (no third-party QR login)

Guest mode allows everyone to play. To become verified:
1. Player supplies an address.
2. Backend creates one-time, expiring EIP-712 typed-data login challenge bound to address/chain/nonce.
3. Player signs it with **their own** compatible wallet or trusted Agentic Wallet workflow, **not** by giving the website any pairing code.
4. Backend recovers the signing address, validates nonce, then reads `balanceOf(address)` from the configured registry.
5. Verified account stores address. Owners can re-authenticate from another device by signing a new challenge; this recovers their existing player account.
6. For on-chain game actions, the **holder** directly reviews/authorizes the transaction. The server never signs as the holder.

In production, EIP-712 signing/recovery uses `eth-account`; the standalone pure-Python implementation is **development/test fallback only**. That custom cryptography is not suitable for production security assurances.

On BNB mainnet set:

```text
AGENTOPIA_ENV=production
AGENTOPIA_REGISTRY_MODE=mainnet
AGENTOPIA_CHAIN_ID=56
AGENTOPIA_AGENT_ID_CONTRACT=0x60b9262456de011f7d15a54cdd8c48baaa8b022f
AGENTOPIA_GAME_CONTRACT=<VERIFIED_MAINNET_AGENTOPIA_CORE_ADDRESS>
AGENTOPIA_RPC_URL=<TRUSTED_BNB_RPC_ENDPOINT>
AGENTOPIA_SECURE_COOKIES=1
```

Other required production controls: HTTPS reverse proxy, server hardening, firewall, stable database, backup/restore testing, independent contract audit, operational monitoring, moderation, and compatibility testing with real Agentic Wallet users.

## Solidity deployment

See [Testnet → Mainnet deployment runbook](docs/TESTNET_RUNBOOK.md). On testnet, deploy `MockAgentID` and configure BSC chain ID 97; these **do not qualify as real Agent ID holders** for the hackathon. After Foundry tests and manual wallet integration pass, deploy `AgentopiaCore` on BNB mainnet against the official Agent ID registry, verify the code on BscScan, and have real holders interact. **No private keys are included in this repository**.

## Testnet deploy automation (not yet executed on-chain)

The new `scripts/testnet_deploy.py` performs a guarded chain-97 preflight and can deploy a test-only MockAgentID + AgentopiaCore using an encrypted Foundry test keystore (no seed/private key input). **It has not successfully broadcast anything from this environment.** See [attempt evidence](docs/TESTNET_ATTEMPT_2026-11-19.md) and the [Foundry/testnet runbook](docs/TESTNET_RUNBOOK.md).

```bash
# Diagnose compiler, chain ID, test wallet and gas; no transactions
python scripts/testnet_deploy.py
# Only on a real funded BSC Testnet environment, after forge-std install:
python scripts/testnet_deploy.py --account agentopia-test-deployer --oracle 0xTEST_ORACLE_ADDRESS --broadcast
```

**Mainnet deployment is explicitly out of scope of this script.** A successful testnet mock is not a genuine Binance Agent ID.

## Development & testing

```bash
pip install -r requirements-dev.txt
pytest -q
node --check web/game.js  # optional but recommended
# Start live server in another shell:
uvicorn app.main:app --host 127.0.0.1 --port 8765
python tests/smoke_live.py
python tests/gameplay_live.py
python tests/load_live.py
# Solidity: install Foundry and forge-std, then:
cd contracts
forge test -vvv
```

For Windows, if `node` isn't installed, you can still run the game; Node is only used for static JavaScript syntax checks.

## Security and privacy

- Never enter seed phrases, pairing codes, or private keys in this game. The only browser prompts are normal user-approved wallet signatures/transactions.
- The oracle key (if enabled) is **project-only**, separated from user wallets and stored in server secrets; it can authorize game achievement vouchers, **not asset transfers**.
- All gameplay materials are off-chain points. **Nothing is a tradeable token or guaranteed reward.**
- Backend-authoritative harvest and movement, cooldown, atomic DB writes, action IDs, and EIP-712 binding reduce simple cheats. More anti-bot protection is needed before a high-traffic launch.
- Current account recovery uses wallet signatures and a 7-day session. Users without a linked wallet should consider their guest sessions temporary.
- Chat is unencrypted public in-room broadcast, not persisted in DB; do not share sensitive information. A real public launch requires report/mute workflows and a published privacy policy.
- See [Threat model](docs/SECURITY.md).

## Hackathon

Official announcement: https://www.binance.com/en/support/announcement/detail/95f5dbe0ea674a48a739b59e046648bf

Submission closes **2026-12-09 08:00 UTC (15:00 WIB)**. The project must be live and use real Agent ID, and its contract must be deployed and verified on BNB Chain. Innovation Award eligibility requires **at least 30 actual Agent ID holder addresses interacting with project contracts** during the submission period. **This ZIP has not satisfied those conditions by itself**.

## License & disclaimer

MIT licensed, independent community project. Not affiliated with or endorsed by Binance. Prototype is provided as-is; before handling real transactions, run independent security review and test with a dedicated, minimally funded wallet.
