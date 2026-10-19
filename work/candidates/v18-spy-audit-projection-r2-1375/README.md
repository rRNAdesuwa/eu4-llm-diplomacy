# R2 terminal-boundary correction

The sealed predecessor remains unchanged. R2 moves the incremental input-count
check inside the terminal exception boundary and makes every explicit EOF final,
including premature finish and serialization-budget failure. A rejected 193rd
record or premature EOF can no longer be followed by a successful finish/resume.
The unchanged 18 baseline tests plus four new incremental boundary tests pass.
This does not change the sealed core, model, wire grammar, metadata limits or any
runtime permission. The six captured C++ mock streams are byte-identical copies;
no additional compilation or game call is needed for this Python-only revision.

# V18 private audit projection — isolated mock only

This new candidate leaves both the sealed core and sealed `EU4SPYLAB/1`
protocol/model unchanged. It provides a strict **offline mock** projection from
the C++ core's private `Event` and `Result` structures to the proposed model's
canonical JSONL. It does not supply a game host, native log producer, execution
authority, publisher, process reader, DLL or network service. No game was read.

`projection.py` imports the exact pinned protocol/model **from verified bytes**.
It never weakens their field, type, ordering, TTL or ownership checks. It accepts
only `origin=isolated_mock`; actual game/native origin is explicitly unsupported.
Every output retains `native_log_authenticated=false`, `runtime_verified=false`,
`effects_verified=false`, `production_ready=false`, and the SP/epoch limitations.

## What is measured and what is missing

`capture_mock.cpp` includes the sealed core/test source without editing it and
uses the original isolated fake memory/function resolver. A replacement mock
logger serializes the **actual C++ private structure values** received during
three `Core::run` calls. It also serializes each complete returned `Result`.
The capture is stdout, not a durable game log. The callback returns according to
the original mock logger; a line existing does not prove that callback returned
true. The independent final Result/fault checks close that distinction.

Private `Event` contains selected roots/date/handles and object ordinals, but it
has no PID creation identity, session nonce, build-manifest identity, frame,
clock, owner-thread capture, durable claim, or independent healthy frame. Its
root Stamp also lacks country-array count and target-overlord guard evidence.
The core delegates additional constraints to a trusted Host guard. This layer
cannot recover or prove them from adjacent callbacks. `availability()` reports
the missing host contract; raw Event-only projection fails closed.

The Python tests attach **explicitly synthetic** host envelopes, claims and
health records to the mock captures. They do not assert that PID 777 or the
synthetic creation/session/build values identify a running game. The recorded
thread belongs to the mock executable. `durable=true` in those model fixtures is
a mocked Host assertion, not a claim about the stdout capture. Therefore a
complete projected model means only that this finite proposed host contract can
represent the isolated core trace; it is not an authenticated runtime replay.

An eventual native host needs independently captured process/session/build and
owner-thread facts, atomic durable claim consumption, bounded durable callbacks,
monotonic actual callback times, and independently sampled later health. It must
also enforce the required array-count/overlord/profile guards. Adding those facts
would require a new reviewed producer, not a reinterpretation of these mocks.

## Exact mapping and event limits

| Core input | Proposed-model output | Meaning and source |
| --- | --- | --- |
| Explicit mock Host health/claim | `health` / `claim` | Required separate records; never inferred from Core |
| `stage_begin` | No emitted event | Validates initial defaults and an already existing claim |
| First factory `step_begin` in a family | Derived `case_begin`, then `step_begin` | Logical case boundary from the ordered factory intent; not an extra engine observation |
| Other `step_begin` | `step_begin` | Intent persisted before the second guard/resolver; both entered and returned must still be false |
| `step_return` | `step_complete` | Known normal native return, except fixed owned-field initialization |
| `initialize` return | `step_complete` | Private owned writes; raw entered/returned must remain false, never advertised as a native callback |
| `case_complete` | `case_complete` | Exact retained snapshot plus released object graph |
| `stage_complete` callback **and** successful returned `Result` | `stage_complete` | Deferred until completed/audit/ownership/case/legality vectors agree |
| Fault, nonzero reason, exception, failed audit Result | Terminal rejection | No successful completion or guessed cleanup is emitted |

Result clock may be later than the final callback while remaining in the same
frame. That later observation advances the input clock high-water mark; a later
input cannot borrow an older health record. Frames advance only through explicit
health. All callback stamps remain exactly equal to the fixed selected world,
date and full FRA/ENG handles. Three complete calls produce 161 private callbacks
and three returned Results. Seven explicit mock health/claim records make 171
inputs; the unchanged model receives 180 events, including 15 derived case starts.

Original, clone and command IDs must follow the actual core's monotonic 1-based
allocation, not merely be distinct. Retained fields and destruction flags are
checked before and after every step. Fields use exact integer widths; the raw
BYTE value/flag39 are converted to model booleans only after checking canonical
0/1. Padding is not invented or compared. Model vtable RVAs come from the checked
actual pointer minus the explicit mock image base.

The wrapper's size 0x58/vtable 0x1c814b0, full-preview null string/false mode, and
fixed function routes are **static projections from the pinned core contract**.
The private Event does not independently carry a command-memory snapshot or ABI
argument record. The core verifies those constraints before a known return audit,
and this candidate pins that source. The provenance table labels all derived
boundaries and static projections; it does not relabel them as raw observations.

The sealed model deliberately permits `destroy_*` step entry after expiry while
continuing to require exact ownership, date, pause, thread and paired return.
The actual `late_cleanup` mock reaches expiry during full preview: the destructor
begins and returns at the expiry tick, but the next factory is rejected by the
core. Projection preserves that cleanup and then stops on the real fault. It does
not change the timestamp or retry the next family. A single completed stage plus
later health is a consistent partial log, not a successful three-stage finish.

Input bounds: 192 records, 8 KiB per line and 512 KiB total file read via
`read(MAX+1)`; exact duplicate-key and non-finite JSON rejection. Output uses the
sealed limits of 256 events, 8 KiB per line and 256 KiB total. Invalid input locks
the projection object against further feed/resume.

## Offline validation

```powershell
python -B work/candidates/v18-spy-audit-projection-r2-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v18-spy-audit-projection-1375 -p test_projection.py -v
cmd /c work\candidates\v18-spy-audit-projection-r2-1375\capture_mock.cmd C:\unique-new-capture-directory
```

The last command compiles a core object and mock executable only, refuses an
existing output directory, and emits six finite scenarios: all false, mixed,
all true, expired cleanup, factory SEH, and final audit failure. Tests consume
the pinned `mock-attempt-1` captures, never a current game/session path. There is
no API allowing callers to inject a validation callback or enable actual origin.

The three normal projections all pass the original model, with false outcomes
preserved independently for +0x88 and command +0x40. Adversarial tests cover absent
host proof, partial stages, failed final logger, incomplete Result, ABI intent vs
return, scalar aliases, retained snapshots, ownership/clone IDs, frame/time
regression, foreign identity, explicit claim TTL and serialization bounds.
All results are stored as mock evidence and never added to research capabilities.
