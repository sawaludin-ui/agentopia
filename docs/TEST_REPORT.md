# AGENTOPIA — Verified Testing Evidence

**Build date:** 2026-11-19. **Do not mistake unit-test success for a production security guarantee.**

## Automated tests actually run

| Test | Status | Evidence |
|---|---|---|
| Python backend unit/integration tests | **PASS — 36** | `pytest -q`: `36 passed` (tests under `tests/`) |
| Keccak-256 known vectors and secp256k1 key address | **PASS** | `tests/test_crypto.py` |
| EIP-712 login/verifier, nonce binding, signature replay and wallet re-authentication | **PASS (development implementation)** | `tests/test_api.py`, `tests/test_crypto.py` |
| Harvest proximity, cooldown, inventory changes, bridge progress | **PASS** | `tests/test_api.py` |
| SQL session isolation, authenticated WebSocket chat and movement | **PASS** | `tests/test_api.py` |
| EIP-712 contribution voucher hash + calldata, material reservation | **PASS (development implementation)** | `tests/test_api.py` |
| Javascript parser check | **PASS** | `node --check web/game.js` |
| Live two-client WebSocket chat, state sync, authoritative movement | **PASS** | `python tests/smoke_live.py` |
| Live full gameplay transport: move → harvest → move → donate → leaderboard | **PASS** | `python tests/gameplay_live.py` |
| 30 simultaneous real WebSocket connections | **PASS** | `python tests/load_live.py` (all 30 received 11 snapshots during ~1 second) |

## BSC Testnet attempted again — 19 Nov 2026

A new guarded testnet deploy runner was created and its preflight executed. It returned `BLOCKED` (no forge/cast, no RPC DNS, no funded test signer). Compiler download was attempted and failed. **No on-chain deploy occurred.** See [testnet attempt record](TESTNET_ATTEMPT_2026-11-19.md). Seven additional offline tests for the deployment guardrails passed.

## Not tested / blocked

| Test | Status | Why |
|---|---|---|
| Visual Chromium desktop/mobile UI test | **BLOCKED** | Container's managed Chromium has enterprise URLBlocklist `*`; navigation to local server is blocked by administrator policy |
| Solidity `forge build` + `forge test` | **NOT RUN** | `forge`/`solc` absent, package-download network unavailable |
| Deployed BSC Testnet contract and mock registry | **NOT DEPLOYED** | No deployer wallet/funding or live outbound RPC available |
| Official Agentic Wallet external-sign compatibility | **NOT RUN** | Requires actual user's wallet/Developer Mode approval |
| Mainnet official Agent ID verification | **NOT RUN** | No BSC RPC access in the build container and no user-held Agent ID wallet |
| Live blockchain event reconciliation | **NOT RUN ON-CHAIN** | Requires contract deployment and real transaction receipts |
| Independent smart contract audit | **NOT DONE** | Must precede mainnet use |
| Real mobile touch interaction | **NOT RUN** | Browser interaction blocked by container policy |

## Important discovered/fixed defects

- Fixed two wrong Keccak round constants before accepting the crypto implementation; cross-checked Keccak empty-input and `abc` test vectors and known Ethereum private-key-to-address result.
- Added `pytest.ini` so Python tests import project modules correctly.
- Added wallet re-authentication from a second device rather than trapping the wallet in the first guest account.
- Added bridge-proximity validation so players cannot contribute from anywhere on the map.
- Added production guard against mock Agent ID configuration, native `eth-account` production signing, security headers, signup throttling, concurrent room cap.
- Added on-chain material reconciliation flow with event validation, expiration handling, and oracle-signed voucher checks.

## Reproduction

```bash
pip install -r requirements-dev.txt
pytest -q
node --check web/game.js
uvicorn app.main:app --host 127.0.0.1 --port 8765
# In another terminal:
python tests/smoke_live.py
python tests/gameplay_live.py
python tests/load_live.py
```

**Release decision:** Local playable prototype only. **DO NOT deploy to BNB mainnet or solicit users' real transaction signatures** until Solidity tests, testnet integration, security review, and real wallet compatibility are completed.
