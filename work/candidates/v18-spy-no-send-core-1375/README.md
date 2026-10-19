# Five-family no-send C++ core candidate

This isolated candidate implements only temporary-object research. It does not
implement a DLL, game hook, request consumer, stage publisher, transport, sender,
fixture, speed control or acceptance override. No game process was opened.
Object-only compilation and a separately linked mock executable are the entire
native validation scope. Production readiness and runtime verification remain
false even when every mock stage completes.

The fixed profile contains `corrupt_officials`, `sabotage_reputation`,
`sow_discontent`, `slander_merchants`, and `sabotage_recruitment`, in that order.
Every initialized temporary action uses full FRA and ENG identities, value true,
state zero and envoy -1. There is no caller-selected action, target, cost, flag,
pointer, RVA, string or false/cancellation variant. Each explicit stage visits
all five families once:

1. Factory defaults, independent clone, clone deletion, original deletion.
2. Factory and fixed initialization, **family virtual +0x88** full preview,
   original deletion. A false return is a successfully observed research result.
3. Factory and fixed initialization, `4e9930` owned wrapper, original deletion,
   **command virtual +0x40 (`4e8630`)** gate, command deletion with owned clone.
   A false gate is likewise a research result. It does not authorize execution.

The command gate invokes action +0x80 internally. It must never stand in for
the family +0x88 capability check. Full preview can touch lazy caches, TLS and
script machinery; neither preview nor gate is described as a read-only game
operation. A future host must invoke them only on the verified game owner thread
in an explicitly claimed stage.

## ABI and ownership

Windows x64 ABI is used. The following are the only resolver call sites:

| Call | Fixed arguments and return | Ownership after a known normal return |
| --- | --- | --- |
| Factory `35d210` | `void*(uint32 token, const void* null)` | One original 0x40 action; null/sentinel is unknown and freezes |
| Family clone +0xb0 | `void*(const void* original)` | New distinct action; the original remains owned |
| Family full preview +0x88 | `bool(void* original, void* null, bool false)` | Retains original; exact bool outcome is recorded |
| Owned wrapper `4e9930` | `void**(void* original, void** slot)`; slot initially null and return exactly `&slot` | Separate 0x58 command owns a distinct clone at +0x50; original remains independently owned |
| Command gate +0x40 | `bool(void* command)` | Retains command and clone |
| Action deleting dtor `129450` | `(object, unsigned 1)`; return ignored | Object gone; never dereferenced again |
| Command deleting dtor `4e7470` | `(command, unsigned 1)`; return ignored | Command and clone gone; no separate clone deletion |

The five action +0xa8 slots are pinned to false. This is the evidence that the
command destructor owns and deletes its clone. Command structure checks cover
its vtable, marker, token, String32 empty fields and selected flags/sentinels,
including its exact clone pointer. These checks are repeated after the original
destructor and before the gate, so a consumed command cannot be used or deleted.

Action fields are individually read as uint8, uint32/int32 or uint64. Padding is
not compared. Defaults include sentinel handles `0x2d2d2d`, dates 43808760, state
zero, value one, flag39 zero, identifier zero and envoy -1. A direct clone copies
source primary date into secondary date and clears flag39. The real wrapper
separately writes the **current game date** to clone secondary at `4e995c`.
The profile locks both source and game to one positive raw date, then validates
the clone and re-reads the same date; this limited equivalence is not a general
claim that wrapper secondary date always comes from the source object.

Only the corrupt-officials normal-AI initialization was independently closed
in the source report. Reusing the same fixed initialization for the other four
families is a no-send candidate hypothesis checked against their constructors,
clones and selected layout. It is not runtime evidence or a sending ABI grant.

## Failure and integration boundaries

`Core` has no reset method. Stage order, strictly later health frame, durable
claim, exact game hash, thread, root and manual pause are required. A repeated
stage, any unknown result, failed read/write/audit, pin mismatch, alias, root/date
change or callback reentrancy freezes it. SEH covers resolver, callbacks and
engine-call boundaries. After SEH, no engine destructor, retry or repair is
attempted. In particular, a factory or wrapper could have allocated internally
before failing; absence of a returned pointer does not prove no allocation.
Normal deleting-dtor return is the only release transition. A successful audit
is not a substitute for that return. The final fault event is best effort and
cannot authorize cleanup or advancement.

Expiry is checked before new work. After a known normal call, required cleanup
can finish beyond expiry while exact roots, date, thread and audit remain valid;
the next work call is then blocked. Clock regression is terminal. Read limits
are 64 bytes per read, 8,192 reads and 1 MiB per stage; selected object/root reads
use fixed offsets, not heap scans. Each stage validates 21 code prefixes (643
bytes) and 52 virtual slots, plus PE identity; called prefixes are checked again.

`Host` is a **private trusted integration ABI**, not a public request schema.
Its resolver/read/write/logger/guard functions are supplied only by the isolated
test here. Non-mock resolution must equal image base plus a fixed approved RVA;
there is no implementation that obtains this base from a game process. The
full-hash and durable-claim booleans require independent host proof; the core's
bounded prefixes do not replace full executable hashing. The mock path is
explicitly recorded and can never certify a real run. Future integration still
needs a process-singleton core, exact session/process identity, unique durable
claims, paused owner-thread scheduling, later healthy-frame proof, bounded
durable logging, and a reviewed root reader. No strict single-player origin or
world-epoch proof is claimed by the selected pointer/date checks.

`Event` is an internal typed audit record, **not an implemented serializer** for
the sealed Python `EU4SPYLAB/1` model. The host envelope, ordered wire ordinals,
session binding and translation of object IDs/steps are deliberately absent.
The `initialize` audit describes fixed writes to the newly owned action, not an
engine callback. `Result.completed` means this invocation's operations and
audits completed; it does not mean effect, AI acceptance or execution support.
All runtime/effect/strict-SP/epoch/production permissions stay false. False
preview and false command gate remain separate observations across stages.

## Reproducible offline checks

From the repository root:

```powershell
python -B work/candidates/v18-spy-no-send-core-1375/prepare.py --check
cmd /c work\candidates\v18-spy-no-send-core-1375\test_core.cmd C:\unique-new-output-directory
```

The second command refuses an existing output directory. It compiles `core.obj`
and a mock executable, never a DLL. The executable has no process-open or native
game resolver. It constructs sparse synthetic PE/root memory and private heap
objects, checks exact null arguments, independent cleanup, field widths/padding,
false gates, allocation/clone aliases, premature consume, audit/guard failures,
SEH, TTL cleanup, reentrancy, all prefix/slot mutations and stage/identity gates.
The first compiler attempt failed only on a test forward declaration; its output
is retained. The corrected and subsequently strengthened attempts are retained
separately. Full success and all failure evidence are pinned by `review.json`.

The 22 frozen v17 native files, host/support sources, DLL/manifest and the sealed
Python proposal are unchanged. This candidate neither installs nor authorizes
anything in the running game.
