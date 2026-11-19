# BNB Chain Testnet → Mainnet Runbook

**Not executed in this build environment.** A deployed contract, a funded deployer, and a functioning RPC require external action. Do not mark these steps complete until you have actual transaction hashes and verified source links.

## 0. Requirements

Install Foundry (`forge`, `cast`), Python 3.11+, an EVM wallet/key store that **you control**, and tBNB from the official testnet faucet. Do not email or paste secret keys to anyone. Test with a disposable test-only wallet; keep project-oracle signing material separate from the deployer account and any personal funds.

Official testnet: chain ID **97**, RPC `https://data-seed-prebsc-1-s1.bnbchain.org:8545` (availability varies; check the official BNB docs).

Official guides:
- https://docs.bnbchain.org/bnb-smart-chain/developers/wallet-configuration/
- https://docs.bnbchain.org/bnb-smart-chain/developers/json_rpc/json-rpc-endpoint/
- https://www.binance.com/en/support/announcement/detail/95f5dbe0ea674a48a739b59e046648bf

## 1. Compile and test FIRST

```bash
cd contracts
mkdir -p lib
git clone --depth 1 https://github.com/foundry-rs/forge-std lib/forge-std
forge fmt --check
forge build
forge test -vvv
```

Use current Foundry installation instructions if an option has changed. Stop deployment on any compiler/test failure. Tests use `forge-std/Test.sol` and require installing `forge-std`.

## 2. Prepare your testnet wallet

```bash
# Use an encrypted local keystore; no plaintext private key on the command line.
cast wallet import agentopia-test-deployer --interactive
cast wallet import agentopia-test-oracle --interactive
cast wallet address --account agentopia-test-deployer
cast wallet address --account agentopia-test-oracle
```

Fund the test **deployer** with a small amount of tBNB using a trusted faucet. `oracle` should use its own key; testnet oracle key can be used in server secrets if necessary, but **never** a key that holds user funds.

## 3. Deploy registry mock on testnet

```bash
export BSC_TEST_RPC=https://data-seed-prebsc-1-s1.bnbchain.org:8545
forge create src/MockAgentID.sol:MockAgentID --rpc-url "$BSC_TEST_RPC" \
  --account agentopia-test-deployer --broadcast
```

Save the deployed mock address from the transaction receipt. `MockAgentID` is not an official `.ai` Agent ID and does not count toward competition requirements.

```bash
cast send <MOCK_REGISTRY_ADDRESS> 'grant(address)' <TEST_HOLDER_ADDRESS> \
  --rpc-url "$BSC_TEST_RPC" --account agentopia-test-deployer
cast call <MOCK_REGISTRY_ADDRESS> 'balanceOf(address)(uint256)' <TEST_HOLDER_ADDRESS> --rpc-url "$BSC_TEST_RPC"
```

Expected result: `1` after grant.

## 4. Deploy the game proof contract

```bash
forge create src/AgentopiaCore.sol:AgentopiaCore --rpc-url "$BSC_TEST_RPC" \
  --account agentopia-test-deployer --broadcast \
  --constructor-args <MOCK_REGISTRY_ADDRESS> <PROJECT_ORACLE_ADDRESS>
```

Record the new contract address. Ensure `core.agentID()` returns the mock testnet registry, `core.oracle()` returns the intended project oracle, and `targets(1)` is 10,000.

## 5. Configure server for testnet

Provide these secrets via host environment or an untracked `.env` file loaded by your process manager; the FastAPI app does **not** automatically read `.env`.

```text
AGENTOPIA_ENV=production
AGENTOPIA_REGISTRY_MODE=testnet
AGENTOPIA_CHAIN_ID=97
AGENTOPIA_AGENT_ID_CONTRACT=<MOCK_REGISTRY_ADDRESS>
AGENTOPIA_GAME_CONTRACT=<GAME_CONTRACT_ADDRESS>
AGENTOPIA_RPC_URL=https://data-seed-prebsc-1-s1.bnbchain.org:8545
AGENTOPIA_ORACLE_PRIVATE_KEY=<PROJECT_ORACLE_KEY_FROM_SECURE_SECRET_STORE>
AGENTOPIA_SECURE_COOKIES=1
```

The app requires `eth-account` for production/testnet real signature verification. Host it behind HTTPS so Secure session cookies work.

## 6. Run a real end-to-end wallet test

1. Sign the site login challenge with the test holder wallet using EIP-712.
2. Confirm RPC `balanceOf` reports holder = true.
3. Call the `joinCity()` transaction **from that holder address**; confirm `CitizenJoined` on-chain.
4. Enter the game, harvest materials and reach the bridge build area.
5. Prepare a voucher through `/api/chain/contribution`.
6. Preview the exact custom contract-call `to`, `inputData`, `value=0`, and chain ID in the wallet. Make sure no unrelated transfer/approval is requested.
7. Approve and send the `contribute()` transaction from the **same** holder address.
8. Submit tx hash and poll `/api/chain/action/<actionId>` until confirmed.
9. Confirm action ID is marked used on-chain, and leaderboard/bridge progress is updated exactly once.
10. Attempt replay of the same proof, expired proof, altered amount, non-holder account, and wrong-chain signature; each must revert.

**Agentic Wallet note:** Binance Agentic Wallet custom contract calls require Developer Mode and preview/confirmation under the official wallet workflow. A third-party website must not request QR/pairing codes or control that wallet session. Manual calldata export is provided for experimentation and review; a streamlined official-skill user experience needs a separate compatibility test. See `docs/AGENTIC_WALLET.md`.

## 7. Mainnet (only after testnet passes)

Use BNB mainnet RPC, **chain 56**, and official Agent ID registry:

```text
0x60b9262456de011f7d15a54cdd8c48baaa8b022f
```

Deploy **only AgentopiaCore** (not the testnet mock) with that registry and the correct project oracle address. Verify source code on `https://bscscan.com/` using the BscScan/Foundry verification process. Publish owner/oracle powers clearly. Test with a separate funded wallet and real Agent ID, then invite genuine users; no fabricated interactions or mass-wallet farming. Submit project details by **2026-12-09 08:00 UTC**.

## 8. Contract administration / maintenance

- Owner: can transfer ownership, configure building caps, rotate oracle. **No** ability to transfer user assets from this contract.
- Oracle: can sign game vouchers, which can inflate proof points if compromised. Rotate immediately on compromise; monitor anomalies.
- Use an address reserved for operations, with private key stored off-repository. Consider multisig owner for production.
- Deploy new version if serious flaws are found: this contract is not upgradeable. Inform users and update the published contract references.
