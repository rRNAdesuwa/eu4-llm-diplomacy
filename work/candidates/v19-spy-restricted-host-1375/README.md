# Private v19 three-stage preflight and fixed spy batch Host

This is a source/object/mock candidate. It includes no DLL, hook, loader,
publisher, process attachment, public API, actual session or game call. The
object-only `preflight/native_env.cpp` is not linked into or initialized by the
mock. The mock resolver points only to private fake allocations and functions.

The exact v18 Host/codec/native-environment/journal sources are retained in
`v18-preimage`. The independently reviewed v19 send core and the exact v18 core
it references are copied under `core`. Their bytes are unchanged. No mutable
formal API source is a dependency. `preflight-delta.diff` records the narrow
versioned Controller additions and include/purpose changes.

## Stable private interface

`eu4_spy_send_host19::Controller::start(Environment, Journal)` may run once.
`frame(packet,size)` is called by the future actual owner-entry hook; this
candidate does not install one. `status()` is owner-thread-only and returns a
copy. Non-mock Controllers additionally acquire one never-reset process static
instance. Any reentry, exception, changed identity/world/date, budget or audit
failure is terminal. Root pointers are finite selected identity checks, not an
engine lifetime lock, world epoch or strict SP provenance proof.

Environment is the versioned `eu4_spy_host18::Environment`; Bootstrap and
NativeEnvironment are in `preflight/native_env.h`. The environment preserves
the full-disk SHA/loaded-PE/current-process creation and actual owner-thread
checks of the reviewed source. Its existing initialization cannot run in the
mock executable because the mock does not link that object.

The new Journal has synchronous `append(user,bytes,length)` and
`claim(user,sequence,item,bytes,length)`. True is permitted only after complete
durable append or unique claim flush. The supplied FileJournal uses a new
`spy19-PID-CREATION-SESSION` directory, private ACL, no-reparse held directory,
CREATE_NEW log/claims, bounded ASCII writes, checked flush and close. An old or
partial directory cannot be reused. Claims are 1.claim, 2.claim, 3.claim,
4.claim, then 4.item-1.claim through 4.item-5.claim. A partial claim remains
permanent even if its callback consumes the TTL or the next audit fails.

Only two wire forms exist, each at most 1024 bytes and exactly canonical ASCII
with final LF. Sequences 1..3 use EU4SPYLAB/1 with new purpose
`restricted_spy_lab_1375_v19`, the three fixed no-send stages and the existing
fixed fields. Sequence 4 uses EU4SPYSEND/1, `stage=send_batch`, the same purpose,
FRA→ENG, fixed profile, true/state0/envoy−1. No caller family, amount, pointer,
RVA, console text or arbitrary target is accepted. `render_item` is a private
permanent claim format, not an external request endpoint.

## Actual preflight provenance

The versioned preflight Controller owns the same nested no-send Core instance
for all three stages. Its private `StageReceipt[3]` is populated only from that
Core's returned Result after the complete `run_result` append succeeded. A
subsequent independent owner call must append a health record successfully
before the receipt receives `later_health=true`. The typed proof checks all
three results, five cases each, stage identity, audit/cleanup/exception flags,
the original observed/allowed arrays and strictly later health frames. No
external receipt setter or JSON-to-proof converter exists. `completed_preflight`
returns an isolated copy; mutating it cannot alter the Controller's history.

False family or command gates remain false in the old raw records and typed
proof. They are valid completed preflight tests, not a send grant. Sequence 4
is accepted only in a later owner call than the third later-health frame and
rechecks the exact identity/selected world. It then claims the batch without
sending a family in that same callback. Each subsequent work callback invokes
one fixed family, and the following callback only authenticates its later
health. Every family freshly runs its full +88 preview and command +40 gate.

The first two stages' just-completed counters may match while health is still
pending. A bootstrap must therefore use `preflight_ready` as well as counters:
for stages 1..3 require state=preflight, preflight_ready, claimed_sequence<3;
for sequence 4 require state=preflight, preflight_ready,
authenticated_stages=3, claimed_sequence=3 and batch_claimed=false.
`batch_ready` means an already explicitly claimed batch can run its next fixed
item automatically; it is never an input-poll permission. While the batch is
active, any further packet permanently rejects. No automatic seq4 request is
generated.

## Raw event contract and limits

Preflight records retain the old EU4SPYHOST/1 schema and all false send/runtime
fields; a new outer bootstrap must describe its own hook separately. Sequence
4 records use EU4SPYSENDHOST/1, a global append ordinal, actual Controller entry
counter `owner_frame`, exact identity, owner thread, observed clock, image and
world, operation and expiry. `send_core` contains the complete typed Event
payload (base stamp nested, extra stamp fields alongside it). `operation_result`
and `terminal_result` preserve the complete Result, all completed outcomes and
current item. `final_health` is a selected health record, not an effect receipt.

Intent records precede the last guard and cannot be renamed actual-entry
records. Normal returns or faults preserve actual entered/returned and transfer
flags; the result is copied after the real private `invoke` returns. This
candidate does not turn those bounded intervals into fictitious exact entry
timestamps or claim compatibility with a pure-model point-time projection.

Sender entry relinquishes command and clone ownership permanently. Only normal
true plus NULL caller slot records dispatched. Exceptions, false/nonconsumed
returns, audit or guard failures preserve the current item and stop; no cleanup
guess, resend, queue drain or effect assertion exists. Known false-gate cleanup
can advance only after normal cleanup and independently later health.

Host limits are 64 bytes/read, 32768 reads/2 MiB per owner call; inherited native
environment and Core limits also remain in force. The journal is at most
512 lines, 8192 bytes/line and 1 MiB total. Controller owner entries are capped
at 4096. New work requires strictly unexpired TTL no more than 60000 ms; a
flushed claim is rechecked before returning to the Core. Known post-return
cleanup and later health may cross expiry. Actual bootstrap/client/reader,
full exception-unwind/lifetime proof and meaningful initial/final effects are
separate future work. All runtime, production, effect, strict-SP and epoch
claims remain false.

## Offline validation

```powershell
python -B work/candidates/v19-spy-restricted-host-1375/prepare.py --check
python -B work/candidates/v19-spy-restricted-host-1375/validate.py --output work/candidates/v19-spy-restricted-host-1375/validation-new
```

The output directory must be new. MSVC /W4 /WX builds six objects and one mock
executable. Tests include nested actual Core calls via isolated resolvers,
typed proof copy isolation, all-false preflight, fresh gates, strict later
health, once-only claims, every new per-item audit boundary, unknown ownership,
TTL/identity/reentry rejection and real temporary CREATE_NEW journal files.
Those temporary files are deliberately retained. No NativeEnvironment
initializer, native game function, EU4 process or original runtime is used.

Development attempt 1 failed only because a test function reused the mock
counter name; all objects had compiled. Attempt 2 exposed a missing immediate
post-claim TTL recheck: later work would reject, but batch begin had accepted.
The corrected Host now checks that boundary immediately. Both failed outputs
and relevant source preimages are retained. Subsequent mock validation passed.
