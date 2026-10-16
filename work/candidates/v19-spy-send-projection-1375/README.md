# v19 fixed spy send: isolated mock projection

This candidate projects the complete typed `eu4_spy19::Event` and the separate
post-invoke `Result` into the sealed R2 send model. It supports only
`origin=isolated_mock_cpp`. It has no game reader, sender, DLL, HTTP route, wire
consumer, loader or actual-session parser. All execution, production, effect,
SP and world-epoch authorization remains false.

`capture_mock.cpp` includes the exact sealed `mock_support.inc` and links the
exact sealed `spy_send_core.cpp`; neither input is edited. Its resolver uses
the original isolated mock functions through additional observation wrappers.
The wrappers record the entry into **mock** functions, not into game code.
All native structs are serialized member by member, including default zeros,
false flags, original/clone fields, logical object IDs, complete outcomes and
the complete private world stamp. Padding is not serialized or interpreted.

The outer capture has one header, explicit operation begin/result pairs,
independent durable-claim callback assertions, complete core events, mock-call
entry observations, and a terminal initial/final-census hash assertion. Three
preflight booleans are explicitly synthetic assertions; they are not a replay
of a real preflight journal. One batch claim and five unique ordered item
claims are required. Every later-health operation must use a strictly later
frame. A result arrives after the core callback returns; an item-return event
alone does not complete its operation or its later-health requirement.

The semantic validator checks every normal item's exact fields, object IDs,
ownership transitions, field initialization, call order, callback outcome,
cleanup flags, logical frame, full identities and complete world stamp. Full
preview false and command gate false require their distinct known cleanup
paths. A normal true return plus a consumed command slot yields `dispatched`,
never `effect_verified`. Once submit is entered, the model relinquishes caller
ownership. A missing return, false return, unconsumed slot, logger failure,
fault, inconsistent field, missing line or truncated capture permanently
freezes the projection. The current item and `dispatch_unknown` are retained;
its recorded ownership list never grants cleanup or retry permission.

## Time evidence and the actual-host boundary

A durable step/dispatch intent occurs **before** the last native guard. It
does not prove actual entry. This mock harness supplies an independent
`mock_call_enter` observation so the abstract model can receive a point-valued
work time. Normal returned work is projected only after its return is known;
both the mock entry time and return-observation time remain in the result.
Known cleanup and observed submit return may cross expiry; new work may not.

This is not a requirement to add a game function-entry hook. In a future actual
Host, a normal source-bound Core `step_return` with entered/returned flags can
prove both control-flow facts, while its earlier intent and later observation
bound an interval. Neither endpoint is an exact actual-entry timestamp. A
future adapter must explicitly represent that interval and the sealed final
guard contract. Unknown/SEH ownership must come from the actual complete Core
`Result` and known step boundary; unsupported or missing data must retain the
current item. This candidate does not implement or authorize that actual-origin
adapter, and rejects actual Host schema/origin inputs.

The future Host author has been asked to preserve the original preflight
`EU4SPYHOST/1` records and add a separate `EU4SPYSENDHOST/1` envelope with full
Core Event and post-invoke Result, identity, sequence, owner frame, ordinal,
observed time and locked frame. No field is removed to satisfy the old model.

## Bounds and validation

The reader allows at most 4 MiB / 4,096 rows per mock capture file, 512 rows per
scenario, 8,192 bytes per line and 256 core events per batch. The sealed core's
per-operation read budgets remain 8,192 calls / 1 MiB; every declared result
is type/range checked. These are mock accounting assertions, not authenticated
remote-memory reads. Unknown fields, bool/int/float aliases, duplicate JSON
keys, nonfinite numbers and incomplete final lines are rejected.

Run only these offline entry points from the repository root:

```text
python -B work/candidates/v19-spy-send-projection-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v19-spy-send-projection-1375 -p test_projection.py -v
```

The already recorded `compile-final` artifacts are an isolated object and mock
executable, never a DLL. `capture.cmd <new-output-directory>` can reproduce
them with `/std:c++17 /W4 /WX`; it refuses an existing output directory. The
sealed mock itself releases its private heap blocks at test teardown. That is
mock-harness disposal, not a native cleanup permission after an unknown call.

Development captures and failures are retained separately. Initial capture
instrumentation recorded only submit entry; the initial projector correctly
froze a false-preview cleanup case whose return crossed TTL. All mock call
entries were then recorded to preserve entry/return intervals without using
an intent as an entry timestamp. The old capture and source preimages remain
under `compile-attempt1`. No old core, model, Host, report or formal API source
was modified, and no new native disassembly was performed.

The first broad type-mutation suite timed out after 55 seconds because the same
shape was replayed for every repeated family event. Its source and timeout are
retained under `test-attempt1`. The narrowed four representative complete
payloads keep every scalar member under test. The next run exposed a missing
final `batch_complete` requirement (one removed-line counterexample); its
source/output remain under `test-attempt2`. That terminal requirement was fixed
only in this new candidate before the final validation.
