# Proposed v18 spy no-send contract

This is a pure Python grammar and offline model. It has no native producer,
publisher, loader, HTTP server, process reader, DLL, or execution adapter. It
does not parse or certify an actual v18 session. Synthetic event acceptance
always reports native authentication, runtime verification, effects, strict
single-player provenance, world epoch, and production readiness as false.
Existing v17 sources, artifacts and capabilities remain unchanged.

`EU4SPYLAB/1` is a new proposed protocol, not compatible with deployed
`EU4LAB/3` or production `EU4PAIR/1`. It exposes three explicit stages only:

1. `lifecycle`: each of the five factory objects, clone, clone destruction,
   then original destruction.
2. `family_preview`: factory, fixed initialization, the complete family
   action virtual `+0x88` with null string output and false mode, destruction.
3. `owned_command`: factory, fixed initialization, action wrapper `0x4e9930`,
   original destruction, command virtual `+0x40` gate `0x4e8630`, then command
   virtual destruction including its owned clone. The command is `0x58` bytes
   with vtable `0x1c814b0` and clone at `+0x50`.

Every stage processes exactly this fixed order: `corrupt_officials`,
`sabotage_reputation`, `sow_discontent`, `slander_merchants`,
`sabotage_recruitment`. There is no per-request action selector. All initialized
objects are FRA to ENG, value true, state 0, envoy -1. No false modes, arbitrary
tags, pointers, RVAs, amounts, scripts, console strings, overrides or send
operation are accepted. Proposed session hashes are required syntax/binding,
not a claim that any v18 binary already exists.

The generic preview `0x4e9d00` eventually invokes the action's virtual `+0x80`
condition; it is not the family's full `+0x88` capability check. Likewise the
owned command gate is a distinct operation. The two allowed results are recorded
separately by family. Either can be false, and they need not agree. False is a
completed legal research observation when the callback and cleanup are known;
it does not prevent the later independent no-send command experiment. True
does not authorize dispatch. No transport, game queue or action execute callback
appears in the step grammar.

The static report independently closes normal AI initialization for
`corrupt_officials`. The other four have matching factory/base/clone layout but
do not acquire an independent normal-caller proof from this proposal. Their
fixed initialization is a proposed no-send experiment profile requiring native
author/reviewer confirmation before implementation. It is not a newly verified
send ABI. All five preserve the special clone rules: secondary date copies the
source primary date and byte `+0x39` clears. Whole-object memcmp is not the
contract. Factory dates/handles are sentinels; initialized dates are the fixed
session date and actor/controller are the full FRA handle, target full ENG.

The full preview can initialize TLS, allocate/cache definitions and evaluate
scripted conditions. It is not read-only or side-effect-free. Future calls must
run only on the game owner thread, explicitly staged in a disposable paused
test session. `family_preview` is not a background/query endpoint. A non-MP
classifier or fixed server vtable does not establish strict single-player
origin; selected root/date/thread equality is not a lifetime epoch.

## Wire and event model

`protocol.py` encodes a canonical LF-only ASCII record of at most 1024 bytes,
with exact field order and decimal/hex spelling. It binds purpose, game hash,
PID/creation, nonce, DLL/manifest hashes, sequence 1..3 and the corresponding
stage, expiry, profile, and the fixed actor/target/value/state/envoy. Claim-time
validation requires `now < expires <= now + 60000`. No function writes a file
or invokes the game. The nonce and hashes are untrusted supplied data until a
future independent native handshake is implemented.

`log-contract.json` enumerates the proposed JSONL events and step grammar.
`model.py` checks exact keys/types and full session/world/thread/country/date
identity on every event, strict ordinal order, monotonic clocks, and same-frame
entry/return pairing. Five cases must complete with no remaining ownership.
Each stage needs a subsequent paused health frame before the next explicit
claim. Missing, duplicate, reordered, foreign, exceptional, unknown-ownership
or unaudited events terminate the model; it cannot retry or resume. Initial
and between-stage health has a 2500-ms model freshness bound. TTL applies before
new work, while known cleanup may continue after expiry.

Objects use nonreused local ordinals 1..128, never addresses. Factory/clone/
wrapper returns establish a finite ownership graph. The wrapper owns its clone;
the original is destroyed before the command gate; destroying the command must
close that exact clone. Logs include raw selected field snapshots and bound
object ordinals, but these are still producer assertions. The model does not
authenticate bytes, prove pointer safety, inspect real allocations, or authorize
an engine call. A future native implementation must pin exact code/vtables,
recheck guards immediately before work, maintain durable CREATE_NEW claims,
stop on audit/SEH/ownership uncertainty, and never guess cleanup or retries.
Those native mechanisms are explicitly absent here.

Input limits are 256 KiB total JSONL, 8192 bytes per line, and 256 records.
The mock complete run has 180 events. File verification uses actual bounded
`read(limit+1)` and hashes, with separate 4-MiB single-file / 16-MiB total source
budgets and 128 external pins. No latest-session discovery or external checker
callback exists. Only synthetic bytes are passed to `replay` in these tests.

## Later batch design, not implemented

The five effects are different country modifiers, not inverse boolean modes.
The existing bounded modifier observer identifies known definition names,
sentinel/unknown definitions, full country identity, linked-list flags and
expiry. It does not make an unknown layout into absence or attribute a modifier
to a request. Its cost path can remain unknown. Stock costs total 315 points
(25/60/80/70/80), beyond a single 100-point network; actual costs may differ.
100 available diplomats do not establish the required spy network or capability.

Any later five-action send study needs a separately reviewed cost fixture or
target/network schedule and explicit send authorization. It should retain the
user's initial/final-only batch observations, using the five distinct modifiers
as selected final-state evidence. No intermediate-effect snapshots, automatic
false/undo, acceptance override, cost replenishment or production capability
are added by this candidate.

```powershell
python -B work/candidates/v18-spy-no-send-contract-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v18-spy-no-send-contract-1375 -p test_*.py -v
```

The first paused `DRAFT.md` is retained as history. These files supersede its
unfinished status only for this offline contract; they do not establish native
readiness. C++ implementation and all runtime steps remain separate work.
