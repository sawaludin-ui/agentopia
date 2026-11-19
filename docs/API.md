# API & WebSocket Contract (v0.1)

Auth uses `agentopia_sid` HTTP-only SameSite cookie. No bearer tokens in query parameters. POST JSON only. Most routes except guest/leaderboard/world require login.

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/guest` | `{"nickname":"Alice"}` | Player + Set-Cookie |
| GET | `/api/me` | — | Player, world, current mode |
| POST | `/api/profile` | `{"nickname":"Alice","avatar":0}` | Updated player |
| GET | `/api/world` | — | Bridge progress and node positions |
| GET | `/api/leaderboard` | — | 25 highest-contributing players |
| POST | `/api/gather` | `{"node_id":"oak"}` | Updated inventory; requires proximity |
| POST | `/api/build` | `{"material":"wood","amount":1}` | Updated progress; bridge proximity |
| GET | `/api/pix` | — | Game-state guidance, not autonomous AI |
| POST | `/api/identity/challenge` | `{"address":"0x..."}` | One-time EIP-712 typed data |
| POST | `/api/identity/verify` | `{"address":"0x...","signature":"0x..."}` | Verified player; may restore old account session |
| GET | `/api/chain/join` | — | `joinCity()` calldata; verified only |
| POST | `/api/chain/contribution` | `{"material":"wood","amount":1}` | Signed voucher + calldata; reserves inventory |
| POST | `/api/chain/submit` | `{"action_id":"0x...","tx_hash":"0x..."}` | Submitted status |
| GET | `/api/chain/action/{id}` | — | Prepared, pending, confirming, confirmed or failed |
| POST | `/api/chain/cancel/{id}` | — | Expired/refunded after on-chain replay state check |
| GET | `/health` | — | Service health |

WebSocket endpoint `/ws` uses same cookie. Frames:

- Browser → server: `{"type":"input","dx":1,"dy":0}` (server normalizes, computes position)
- Browser → server: `{"type":"chat","text":"Hi!"}`
- Browser → server: `{"type":"emote","value":"wave"}`
- Server → browser: `welcome`, `snapshot`, `chat`, `notice`, `construction`, `onchain`, `emote`.

HTTP `409` means conflict (cooldown, invalid state, reused/expired challenge, insufficient material). `503` means external signing/registry/RPC unavailable. Repeated mutating requests to `build` will spend additional materials; a production payments-related flow should have explicit request IDs and exactly-once semantics across network retries. The current wallet proof action has a unique action ID for replay prevention on chain.
