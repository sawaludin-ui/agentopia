# Binance Agentic Wallet Compatibility Notes

## Important limitations

Agent ID is a non-transferable identity ERC-721. Agentic Wallet is a separate user-owned wallet interface; websites must **not** use external QR/pairing code login. Agentic Wallet external custom calls require Developer Mode, preview, and user review. Standard `personal_sign` should not be assumed supported. The website has no access to the private keys or signing session.

Official docs:
- https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/external-sign.md
- https://web3.binance.com/en/dev-docs/products/agentic-wallet/introduction

## Identity verification

The site creates EIP-712 typed data (`AgentopiaLogin`) with wallet, random nonce, chain ID, and expiration. A user may sign it through a compatible wallet or **their own** Agentic Wallet signing mechanism. The resulting 65-byte ECDSA signature can be pasted into the website. The backend checks recovered signer + Agent ID `balanceOf`. A mere submitted wallet address grants **no verified privileges**.

The exact Agentic Wallet `sign-message` input uses a JSON-RPC-shaped object with `method=eth_signTypedData_v4` and two params: signer address and a JSON-serialized typedData string. The user must review the official wallet preview before confirming. Never send this data to a service requesting QR/pairing codes.

## Custom contract-call

The game exports a transaction object:

```json
{
  "chainId": 97,
  "from": "0xTHE_TEST_HOLDER",
  "to": "0xDEPLOYED_GAME_CONTRACT",
  "value": "0x0",
  "inputData": "0xENCODED_CALLDATA"
}
```

For the testnet `joinCity()` or `contribute()` action, preview in the user-controlled Agentic Wallet CLI/skill, for example:

```bash
baw wallet settings --json
baw contract-call preview \
 --binanceChainId 97 \
 --from 0xTEST_HOLDER \
 --to 0xDEPLOYED_GAME_CONTRACT \
 --value 0 \
 --inputData 0xENCODED_CALLDATA \
 --json
```

Only if Developer Mode is enabled and the user verifies preview contents/risks:

```bash
baw contract-call execute --requestId REQUEST_ID_FROM_PREVIEW --json
```

A request may require further confirmation in Binance. **This flow has NOT been executed in this build environment.** CLI features and supported chains may vary; consult current official docs before testing. No guarantee that every holder will have compatible tooling enabled.

## Security invariant

**No website QR login, no pairing code harvesting, no seed phrases, no token approvals, no automatic asset transfers.** Even a valid signature must be checked against the official registry. Guest users may play the off-chain game without a wallet.
