# Local v9 research HTTP interface

`tools/serve_diplomacy_lab_v9.py` is an explicitly bound **EU4LAB/2 research service**. It wraps the existing v9 pair CLI protocol. It does not register the EU4PAIR/1 production backend, enable production `/v1/requests`, install a DLL, run a preflight phase, or change the fixture. The initial implementation has offline synthetic tests only; this HTTP transport has not been exercised against a live game.

The HTTP surface contains ten pair actions, in `legality_only` or `submit` mode:

| Family | Positive action | Reverse action |
|---|---|---|
| Marriage | `royal_marriage` | `break_marriage` |
| Vassalization | `offer_vassalization` | `cancel_vassalization` |
| Relations | `improve_relations` | `stop_improving_relations` |
| Guarantee | `guarantee` | `revoke_guarantee` |
| Spy network | `build_spy_network` | `stop_building_spy_network` |

The fixed research tags are `FRA`, `ENG`, `POR`, `NAV`, and `FOI`; actor and target must differ. `submit` requires actor `FRA`. A valid tag pair does not imply native legality or AI acceptance. Capabilities retain separate static mappings, reviewed historical effects, and production-unsupported fields. The shared evidence index now accepts the fixed v9 cancellation and save/reload experiment; new runtime activity still requires independent review and never becomes an effect merely through a native return.

`fixture`, `speed`, `stage`, DLL loading, console/event execution, arbitrary pointers/RVAs, custom paths, and reset/unfreeze operations have **no HTTP route**. Existing CLI setup remains explicit; positive speed remains behind its exact-process external watchdog. No code in this service bypasses those requirements.

## Explicit startup

Run from the repository, only after the exact v9 research DLL and session have been independently prepared. Supply the exact PID and 16-character lowercase creation FILETIME. No default PID, process discovery, or automatic rebinding exists.

```powershell
# Generate once and pass this environment value to your trusted local client.
$env:EU4_LAB_HTTP_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
python tools/serve_diplomacy_lab_v9.py --pid <PID> --creation <CREATION_HEX>
```

The only allowed host is `127.0.0.1`; the default port is `8766`. The token is read from `EU4_LAB_HTTP_TOKEN`, never from an argument or printed by the service. It must contain 32–128 ASCII letters, digits, underscores, or hyphens. Startup checks the build, exact loaded module identity, process creation time, native installation claim, session log, and installed fixture files before binding the socket. It can start before the three phases pass, but publication then remains unavailable.

Every live status/publication observation repeats the existing `verify_build`, `LiveLabProcess`, session metadata and evidence checks. It also verifies fixed fixture source/installed hashes, enabled-mod configuration, and modification times before process creation. This is disk/startup evidence, **not proof that every definition is loaded or that the current world has a strict single-player origin**. The research host still lacks a production-grade world-generation witness. Responses keep `strict_live_single_player_verified=false`, `world_generation_verified=false`, `research_only=true`, and `production=false`.

## Routes and body

All routes require `Authorization: Bearer <token>` and an exact `Host` of `127.0.0.1:<port>` or `localhost:<port>`. Browser `Origin` requests are rejected. There is no CORS support. JSON bodies are limited to 4 KiB, reject duplicate keys and non-finite JSON numbers, and require one canonical `Content-Length`. Chunked transfer and `Expect` handshakes are rejected. The server uses HTTP/1.0 close semantics, at most eight connection handlers, and a bounded body read deadline.

| Method / route | Result |
|---|---|
| `GET /research/v9/capabilities` | Offline, hash-checked capability/history index plus the exact HTTP contract. `live_readiness=null`; no process access for this route. |
| `GET /research/v9/status` | Fresh, read-only process/session/frame evidence, phase state, `pair_publication_ready`, and durable `mailbox_holds`. |
| `GET /research/v9/requests/{sequence}` | Read-only intent/claim/native-result comparison for this explicit sequence. |
| `POST /research/v9/pair` | One explicit pair publication, or a read-only replay of the exact existing HTTP request. |

Example JSON **with synthetic identities**; replace identity and sequence explicitly after reviewing the current session. The service does not allocate or increment a sequence for the caller.

```json
{
  "protocol": "EU4LAB/2",
  "pid": 1234,
  "creation": "01da123456789abc",
  "sequence": 1,
  "mode": "legality_only",
  "action": "royal_marriage",
  "actor": "FRA",
  "target": "NAV",
  "ttl_ms": 5000
}
```

All nine fields are required; extra fields are rejected. Sequence is an integer in `1..2^63-1`, and TTL is an integer in `1..60000` milliseconds. Booleans do not count as integers. A new publication must use exactly the next observed native sequence. `legality_only` is a real, claimed native main-thread research operation using temporary native objects; it consumes a sequence and is distinct from the production API's pure parameter preview. To request sending, explicitly set `mode=submit`.

`202` means the exact request file was durably published. It does not mean consumed, accepted by AI, or applied. A repeated exact HTTP request returns `200` with `replayed=true` and `request_written=false`. Changing any field, including TTL, under the same sequence is a `409` conflict. Identity/version/body errors fail before publication; a publication exception after reservation returns `502 publication_unknown`. Query status after any response loss. Do not automatically POST again, choose a replacement sequence, or delete intents.

## Durable identity and uncertain outcomes

The key is the bound v9 process/session plus sequence. Before invoking the existing native publisher, the service exclusively publishes a permanent `<sequence:020>.http-intent` containing the exact HTTP body, its SHA-256, and the pinned manifest SHA-256. The existing publisher then creates its permanent `.host-intent`, rechecks current process/world/frame/profile evidence, and exclusively publishes `.request`. Native code makes its own permanent `.claim`. Files are not overwritten or deleted by HTTP. A service restart does not reset this ledger. Independent service instances also contend on the same exclusive intent file.

An HTTP intent left before publication is **not** a native acknowledgement. It blocks further publication. The HTTP service does not fabricate an ACK or retry the publisher. It compares exact host-intent bytes, hashes, PID, creation, purpose, manifest, decoded request, and verified native records before reporting status. Publications made by the CLI and pending phase/request files also block a new HTTP publication; a healthy frame may precede file pickup.

| State | Meaning |
|---|---|
| `queued` | An unexpired matching request file exists; native dispatch is unverified. |
| `native_completed` | The existing v9 validator accepted the matching native completion and its core audit. Examine the native result for legality/return status. Applied effects and AI acceptance remain unverified by this transport. |
| `native_dispatch_unknown` | A native claim exists without complete validated evidence. No retry. This can concern either mode. |
| `publication_unknown` | An intent exists but current files/evidence do not establish a live queue or completed result. No retry. |

If native logs report a frozen session, missing ownership proof, malformed evidence, or a changed process/world, the service returns a guard error rather than a cached success. There is no recovery route that asserts rejection from missing evidence. An independently verified native completion may later resolve an incomplete observation; the transport itself cannot do so.

Completion of the previous request does **not** authorize immediate concurrent publication. Every next request checks the latest heartbeat, paused flag, exact selected world/player identity and date, all three detailed phases, `mailbox_ready`, `pending`, `lease_pending`, and `lease_active`. A speed command's completion can precede the frame confirming automatic pause and lease release. Use a fresh status observation; publication repeats all guards and may still reject a race.

## Offline validation

```powershell
python -m unittest bridge.tests.test_diplomacy_lab_http -v
```

Tests use synthetic mailboxes, fake process observations and in-memory HTTP streams. They do not create listening sockets or call a game process. They exercise ten actions in both modes, strict route/schema/version/session rejection, publication faults, durable exact replay across service restart, conflicting TTL, exclusive sequence races, stale/paused/lease guards, native-record mismatch, disk-profile/build changes, authentication, bounded framing and slow-body rejection. They do not constitute live HTTP or production verification.
