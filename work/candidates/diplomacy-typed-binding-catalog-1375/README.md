# Isolated typed diplomacy binding catalog

This candidate reuses the existing public catalog and strict schema validator. It does not replace or register the production API, research HTTP service, v17 protocol, v18 private Host, or any native backend. The original 274 action IDs and 270 static mappings remain discoverable; **production executable actions remain zero**. Historical effect evidence is unchanged and is not imported as current readiness.

The useful delta is an importable `ContractCatalog.describe(action)`, `validate(request)` and `request(request)` interface that separates structural parameters from a future live native binding. There are 15 enriched action descriptions. Two explicitly versioned candidate schemas change; the other 272 schemas are byte-equivalent as parsed JSON to the existing catalog. `describe` retains the old schema and its `specified`/`partial` label, which never meant the native binder was complete. The base catalog contains 194 specified and 80 partial schemas.

## Contract and readiness

The exact envelope has four fields:

```json
{"protocol":"EU4DIPLOMACY-CONTRACT/2","request_id":"example-1","action":"steal_maps","parameters":{"actor":"FRA","target":"ENG","region_index":0}}
```

This namespace is deliberately separate from EU4LAB/2, EU4LAB/3, EU4SPYLAB/1 and the production request envelope. No implicit legacy conversion occurs. Request IDs use the existing ASCII 1–64 character contract. Unknown properties, raw pointers/RVAs, arbitrary DLLs, scripts, events, fees, native state/value, or envoy selectors are rejected.

`validate` confirms only structural validity and returns a canonical request digest. It reports `native_binding_resolved=false` and `native_legality=null`. `request` returns that immutable canonical snapshot and a symbolic binding, always with `status="unsupported"`, `queued=false`, `request_written=false`, and `native_called=false`. It creates no database, queue, request file, idempotence reservation or callback. Repeated IDs are not reserved here (`not_reserved_contract_only`); a future real adapter must use the existing production durable ledger/holds and reconciliation semantics. A draft digest is neither a dispatch acknowledgment nor global idempotence proof.

Descriptions distinguish static mappings, prior source/mock-only no-send profiles, missing current native binding, and production unavailability. `native_ready=false`, `live_readiness=null`, current legality, AI acceptance and effect are never inferred. The listed game hash is the **static catalog build**, not a live image inspection. No process is opened or inspected.

## Incremental bindings

| Actions | Candidate parameters and finite native meaning | Remaining binding boundary |
| --- | --- | --- |
| Five spies: corrupt officials, sabotage reputation, sow discontent, slander merchants, sabotage recruitment | Existing actor/target schema; internal value true, state 0, envoy −1. Sealed normal-AI callers and source/mock no-send lifecycle exist. | Current capability/cost/identity; full family `+88` preview may initialize caches; action `+80` and owned command `+40` are separate gates. No production sender. |
| Curry / stop currying favors | Existing actor/target; shared token, true/false; both keep envoy −1. | Complete current relation/mission/envoy graph, permissions and ownership; relation activity does not prove favor amount/rate. |
| Subject military focus | Existing exact six names compile symbolically to 0–5. | Already a 0x60 command; native gate is not overlord authorization. Both definition flags, entitlement and complete subject graph required. Clone consumes its temporary String32. |
| Subject embargo rivals / scutage / divert trade | Existing `enabled` strict bool is **desired state**. Symbolic cancel stays null. | Future binder must read current flag and full subject graph, compare desired/current, then use constructor snapshot and stale-state guard. This module cannot return `already_desired`. |
| Steal maps | **V2 migration:** `region_id` string replaced by `region_index`, exact int 0…2³¹−1. | Native selected signed index is known; bounded live registry membership, type/name and lifetime are not. −1 is generic search, not a selected region. No false/undo mode. |
| Support rebels | **V2 migration:** `rebel_faction_id` string replaced by `faction_identity:{low:uint32,high:uint32}` for serialized +10/+14. | Two words are only a lookup key. Full selected target, bounded faction vector, unique match, type, supporter, borrowed lifetime, selected owning caller and treasury fee remain unresolved. Even all-zero keys are only structurally valid, never resolved. |
| Stop supporting rebels | Name remains discoverable, no fixed false binding. | Full family preview rejects false; false effect searches first matching supporter rather than selected faction. Cancellation is unsupported. |
| Steal modern ideas | Only fixed stock definition `steal_modern_ideas`; caller cannot select arbitrary script names. | Loaded borrowed definition, condition and registry lifecycle unresolved. Stock script changes Russian modernization government power and charges 24/30 network; it is not generic technology-level theft. |

Three toggle observations must not be generalized: divert-trade cancellation may restore default 50% trade power; embargo uses independently checked rivals; scutage cancellation's modifier vector differs from timed spy modifiers. A flag change alone would not verify all of those effects.

## Importing without executing

```python
import importlib.util
from pathlib import Path

path = Path("work/candidates/diplomacy-typed-binding-catalog-1375/catalog.py")
spec = importlib.util.spec_from_file_location("typed_diplomacy", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
catalog = module.ContractCatalog()
descriptor = catalog.describe("subject.set_military_focus")
draft = catalog.request({
    "protocol": module.PROTOCOL,
    "request_id": "focus-example",
    "action": "subject.set_military_focus",
    "parameters": {"actor": "FRA", "target": "NAV", "focus": "siege"},
})
assert draft["status"] == "unsupported"
```

The pinned public API module is executed only to reuse its function definitions. `DiplomacyAPI` is never instantiated. Its hash is checked before compiling the same bytes, avoiding a second unchecked source read. The typed candidate does not have a backend argument or an injection seam for caller-provided runtime evidence.

## Budgets and evidence

`input-pins.json` binds 23 fixed sources (7,508,644 bytes): the original catalog/validator, six static contract/report groups, the no-send source/mock review records, and the extracted stock diplomatic script. Ordinary files are actually read with `read(limit+1)` and length checked, not merely stat-checked. Limits: 64 input artifacts, 2 MiB each, 16 MiB aggregate. Reports are hashed one at a time and discarded. No PE decoding, disassembly sweep or whole save read occurs.

Requests are at most 16 KiB, depth 8, 128 nodes, 32 keys/object, 64 items/array and 4096 characters/string. In-memory Python callers get the same strict JSON-tree checks; bool is not an integer. Duplicate keys, non-finite numbers and non-JSON objects are rejected. Schema validation and symbolic binding both use the same canonical snapshot; mutating the caller's dictionary cannot change its digest-bound result.

Evidence annotations are facts from pinned sources, not independently authenticated live object receipts. Every native binding remains unresolved. Source/mock tests and normal AI/UI paths do not establish strict single-player origin, synchronized world generation, current process/pause, ownership at queued consumption, or production permissions.

## Next implementation, after independent review

1. Integrate the existing five-spy no-send source core with an authenticated owner-thread bootstrap/claim/health source; the already reviewed restricted Host is still source/obj/mock, with hook/loader/runtime unavailable. Preserve full `+88` versus command gate and unknown-ownership terminal behavior. Do not add sends by treating this catalog as a whitelist.
2. Implement bounded **read-side binders** for region registry and target faction vector that return complete typed identity/lifetime evidence. The two schema migrations are intentionally not native calls. Faction lookup must prove full target and supporter membership, not merely equality of two DWORDs.
3. Implement subject graph/definition/permission producers for the six military modes and three desired-state toggles, then explicit owned lifecycle tests. Keep already-command constructors separate from ordinary action wrappers. A current-state query is required before any desired-state decision.

None of these steps registers a backend automatically. The existing production ledger's unknown-dispatch holds remain the eventual submission boundary. All other 259 actions retain their catalog schemas without pretending that a new typed native binding was added.

## Offline verification

From the repository root:

```powershell
python -B work/candidates/diplomacy-typed-binding-catalog-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/diplomacy-typed-binding-catalog-1375 -p test_*.py -v
```

Tests cover every catalog ID, migration bounds, six enum mappings, toggle semantics, unsupported cancellation, wire ambiguity, mutable snapshots, source tampering and real bounded reads. SQLite connection and subprocess launch are replaced with failures in the side-effect test. No native/mock C++ build, game, UI, HTTP listener, production registration, frozen-source change or request publication is part of this candidate.
