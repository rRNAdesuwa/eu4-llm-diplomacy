# V21 R3: faithful spy setter and typed cancellation graph

This is a new private file/fake-only component revision. R2, its independent
review, the native adapter candidate and all formal/runtime/native sources remain
unchanged. `pair_component.h` is byte-identical to R2; no public interface, send,
DLL, loader, authorization, OS sampler or game operation is introduced.

The integration blocker was concrete: native `586330(false)` writes the matching
entry's signed int32 ID into action `+30` at `586424`. Sealed R2 instead required
`-1` after that void setter and then wrote an ID through a synthetic binder. The
adapter's preserved `test_r2_spy_setter` reproduced `envoy_binding_changed` with
native-shaped output 17, only factory/setter entered, zero preview/cleanup.

R3 keeps the real setter and immediately expects the already-private graph's
exact `spy.envoy`. It never clears, masks or replaces the native field. The legacy
ABI method named `bind_envoy_owned` remains for compatibility with the sealed
adapter's private state: it is **read-only equality confirmation**, not a writer.
The modified synthetic Engine also only compares. Full fields and the current
typed graph are re-read, then two current stamps and a final fresh clock are
required before full `+88`. Wrong IDs, `-1`, changed state, stale graph, expiry,
rollback or changed session freeze without preview, guessed cleanup or retries.
Other families and all 38 R2 timing/cleanup regression conditions are retained.

## Typed graph addition

Offsets and sizes come from the pinned `curry-favors-observer-1375` observer and
report, `native-pair-cancel-1375`, and the entry-constructor portion of the fixed
`core-five-full88-and-spy-entry-1375` report. No new bytes are decoded or read from
the EXE. Reads are private injected bytes, not OS-attested memory.

* Country `+1480/+1488/+1490` holder begin/end/capacity must be aligned, ordered,
  contain at least four and at most sixteen manager pointers. Read holder `+18`
  only after those bounds pass.
* Manager must first have vtable `1cac380`, marker DWORD `165`, token DWORD `2746`,
  kind BYTE `3`, and unaligned full owner QWORD at `+16` equal to current actor.
  Only then read vector `+20/+28/+30`. Begin/end/capacity are ordered aligned
  pointers with capacity at most 256 entries.
* Every candidate entry must first have vtable `1cac2f0`, marker DWORD `165` and
  kind BYTE `3`. Unknown type/kind refuses before status or mission reads.
  Duplicate entry pointers refuse. Non-state-2 entries have no mission read.
* A state-2 entry's mission must first have vtable `1c4b2b8` and marker DWORD
  `182`, before its task pointer. The task vtable must equal `1ce3ba0` before any
  task-derived fields. Existing full actor/target generation, ID, ownership and
  task/mission/entry backlinks remain mandatory, as does the target task list.
* Bounds and added fields enter the exact typed read transcript. Both complete
  passes and the immediate later rebind compare it. Limits remain 256 envoys,
  1,024 target tasks, 8,192 reads/pass, at most eight bytes/read. Equal samples
  still do not exclude ABA or confer object lifetime synchronization.

The earlier full88 static supplement has a known descriptive stack offset error
(`-81` should be `-89`); R3 does not consume that stack metadata or promote its
normal-caller status. The six-profile registry and `FullCallerEvidence` values are
byte/semantic unchanged: the five core flags remain `StaticSlotOnly`. Normal AI
stack-object evidence is not a heap-allocation/deleting-dtor authorization.

## Offline integration and limits

The candidate includes exact copies of the sealed adapter engine/header/Fake.
Only these private fake-memory pieces are linked with the new R3 component. The
real Win32Platform is not copied, compiled or linked in this candidate. The new
suite checks all twelve component modes with a faithful void setter, exact envoy
0/17/INT32_MAX, mismatching native values, state mutation, type-before-derived
read traps, vector bounds, owner generation, mission marker, double-pass mutation,
duplicate idle entry and post-setter clock/identity changes. The original 24 groups
receive only the truthful setter/readonly-confirmation and complete typed fixture
updates; the original 38-countercheck source is byte-identical. All original
fixtures and source files are retained in `preimages/` and checked against R2.

The adapter's separate independent review is still in progress. Its reviewer has
reported a potential marriage heap-string alias gap outside this spy revision;
passing well-formed marriage fake scenarios here does not approve that adapter or
repair that unrelated issue. This revision establishes private integration and
type-order behavior only. Real Authority/Guard, new source-bound Host composition,
durable claims, fresh owner callbacks, loaded-image attestation and effect evidence
remain separate work. Runtime/native-ready, strict SP, epoch, causality and
production are always false.

```powershell
python -B work/candidates/v21-core-pair-nosend-r3-1375/prepare.py --check
python -B work/candidates/v21-core-pair-nosend-r3-1375/validate.py validation-independent-1
```

The second command creates a fresh directory, compiles MSVC `/W4 /WX` objects and
three puremock executables, and executes only those mocks. A suspended exact child
is placed in a kill-on-close job before spawning any compiler children: 768 MiB
per-process and aggregate job cap, 55 seconds. All child outputs and exact source
preimages are saved. Check totals include repeated bounded fake read assertions;
they are not independent scenario counts. No old artifact is overwritten.

Development attempt 1 passed (24 groups, 38 checks, 37 new groups). An initial
build-script patch had an unmatched text context and made no change; its corrected
patch was then applied. There was no native/game/OS memory access, DLL or EXE-byte
analysis. Only this spawned compiler/test job uses OS process control.
