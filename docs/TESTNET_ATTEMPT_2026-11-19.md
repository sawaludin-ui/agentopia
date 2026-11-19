# BSC Testnet Deployment Attempt — 19 Nov 2026

**Result: BLOCKED (no contract deployed).** No tx hashes, chain receipts, or testnet explorer addresses were produced. These are observations from this environment, not evidence that BNB Chain Testnet is down.

## Operations actually attempted

1. Verified `/mnt/data/agentopia/contracts/src/AgentopiaCore.sol`, `MockAgentID.sol`, and Foundry test source exist.
2. Probed `forge` and `solc` / `cast` installations: unavailable.
3. Probed official testnet RPC `https://data-seed-prebsc-1-s1.bnbchain.org:8545`: DNS resolution failed in the session.
4. Tried to download the Solidity compiler catalog: download failed.
5. Ran guarded `python scripts/testnet_deploy.py` with no `--broadcast`. This checked the toolchain and attempted RPC chain-ID read. Result `BLOCKED`, with the exact machine-readable diagnostic in `artifacts/testnet-attempt-2026-11-19.json`.
6. Re-ran local `pytest`: **36 passed**, including 7 tests of the new testnet deployment runner. Verified JS syntax with `node --check web/game.js`.

## Blockers

- **Compiler/toolchain:** no `forge`, `cast`, or `solc` installed, and outbound package download unavailable. Thus Solidity was not compiled or executed against an EVM in this session.
- **Network:** the environment cannot resolve external testnet RPC DNS; `eth_chainId`/`eth_getBalance` cannot complete.
- **Signer and gas:** there is no funded, disposable BSC Testnet deployer keystore available in this environment. A broadcast requires an authorized signer and tBNB; neither is provided here. Do NOT supply an existing wallet seed or private key to an assistant.

## Guarded deployment runner (new)

`python scripts/testnet_deploy.py --account agentopia-test-deployer --oracle 0xTEST_ORACLE_ADDRESS --broadcast`

Only run this in a separate environment where Foundry, `forge-std`, encrypted test-only keystore, BSC Testnet RPC, and tBNB are genuinely available. The runner validates the remote chain is **97** before broadcasting; runs `forge build` and `forge test` before deployment; deploys MockAgentID then AgentopiaCore; grants mock Agent ID to the funded test deployer; sends `joinCity` and reads the on-chain result. It writes the deployment addresses/tx hashes to `artifacts/testnet-deployment-attempt.json` only if returned by real on-chain commands. `--broadcast` is an explicit opt-in.

**Limitation:** The runner itself has only been unit-tested with mocks; its Foundry command compatibility and live on-chain behavior are **not verified** here. Its scope is contract deployment plus `joinCity`, not the complete oracle-signed `contribute` flow.

Official docs: https://docs.bnbchain.org/bnb-smart-chain/developers/wallet-configuration/ and https://www.bnbchain.org/en/testnet-faucet

## Release decision

**NOT testnet tested, NOT hackathon-submission ready.** A BSC Testnet deployment is demonstrated only by real `0x...` transaction hashes that can be opened on `https://testnet.bscscan.com`, followed by observed events and successful `joinCity`/`contribute` receipts.
