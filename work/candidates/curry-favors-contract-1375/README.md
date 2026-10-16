# Curry favors / stop currying favors — 1.37.5 static candidate

Exact EXE SHA256 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`.
This candidate does not open a process, compile native code, call any game function,
publish a request, or change the production API. All runtime, execution, effect,
causality and production assertions remain false.

## Findings

Both public IDs use token `0x3acc`, action vtable `0x1c7aef8`, allocation `0x40`.
`curry_favors` has value=true, `stop_currying_favors` false. Factory
`35d210` dispatches at `35f559/35f565` to `35fceb`: invalid full handles
`0x2d2d2d`, envoy=-1, state=0, dates=`0x29c77f8`, value=true, flag39=false,
request ID=0. Padding bytes are not part of the contract.

Normal AI caller `12b860` dispatches proposal token3acc at `12cc8e`.
`12cd39..12cdc1` copies proposal actor+0 into action+10/+18 and proposal
target+8 into action+20, with current date+28/+2c, envoy=-1, state=0, id=0.
The caller's third bool switches value to false. Both modes reach `129b60`,
whose full+88(null,false), +80 and +40 wrapper path transfers the owned
command into the AI queue at +a68, nulling the temporary. This closes a normal
AI caller; a specific human GUI sender has not been newly located.

`5ae2b0` independently allocates/copies 0x40. Clone+2c is source+28,
not source+2c; flag39 resets. Destructor `129450` frees only this object when
flags&1. Wrapper `4e9930` clones, stamps current date into clone+2c, allocates
command0x58/vtable1c814b0, puts clone at+50 and returns the caller's slot address.
`4e7470` owns/destructs that nonborrowed clone, destroys its own String32+18,
then optionally frees0x58. No separate clone destruction after command cleanup.
Allocation failures, unknown aliases, exceptions and native unwind paths are
not a license to guess cleanup or retry. This is static ownership evidence,
not a successful live lifecycle.

Full preview `5ae110` and local validity `5ade60` both examine globals
233ff48/233fed6. If first==0 OR second!=0 they read GS:58 TLS, potentially call
initialization1a334c0 and require TLS+10. Full preview then calls4e9d00;
command gate4e8630 invokes family+80. Positive local validity rejects existing
war index(root+50/count5c) and curry index(+158/count164), then runs scripted
prerequisite4ebdb0. Negative validity requires that curry index entry.
These functions are **not read-only observer functions**. No entitlement,
TLS instance, full player authority, thread safety, SP or world epoch is proved.

## Effect and cancellation direction

Positive `5ace50` calls script hook4ec160, creates relation0x40 with vtable
`1c7b178`, actor+10, target+18 and current start+20, then registers it with
game+1bb8 and the actor's outgoing index. `a69af0` uses root+150 map,
pointer+158, DWORD capacity+160/count+164, 16-byte `{slot32,padding,pointer64}`
entries. It also updates the generic all-relations list and dirty/cache flags.
There is no evidence here for a mirrored incoming curry index that must point
to the same object. A target→actor relation is a distinct direction.

The false branch `5ad74d..5ad7fd` is direct cancellation effect evidence:
lookup `a69bf0(actor→target)`, remove from manager and outgoing index,
set removed+28=1, call base relation destructor `a5bb00`, free0x40.
The claim therefore does not depend on UI cancellation text alone.

Positive action+100/+f8 return value; +d0 and +108 are false. The common command
creates an actor diplomat mission via4e7550, with mission vtable1c4b2b8,
fullactor+80/target+88, token+a8=3acc, entry+48 and ID+50. Settlement's
explicit3acc branch `4eaee4..4eaf12` writes relation+30=entry+10mission and
sets entry status2. There is no spy-like nested task+a0 requirement for this
relation association.

Cancellation uses the base setter `4e99d0(action,bool)`, which returns void
and only writes value. Its initialized action envoy remains **-1**. The
relation destructor obtains its linked mission from+30 and calls
`25a3c0(mission,-1)` under the observed server/game-reset/entry predicates.
Do not populate the action with a guessed existing ID, scan a reverse owner's
diplomats, or separately recall that mission. Re-read the index after removal;
the old relation pointer can already be freed. Registry tombstones may retain
freed pointers: a marked registry node must be skipped without dereferencing it.

## Minimal future read-only contract and batch

`contract.json` records known roots, widths, outgoing index, relation, mission
and actor envoy fields. A future sampler must use held process identity,
full EXE SHA/PE pins, bounded arrays and duplicate detection, known type/vtable
before derived fields, full generation-bearing handles, root/date consistency
and two complete typed-equal passes. A single lower native check searches slot
numbers only and is insufficient for an external object's ownership proof.

`contract_model.py` is a pure synthetic model of those selected fields. It has
no process reader or callable authorization. A missing selected relation is
reported as absent, never as proof of rejection. Entry status2 is merely the
observed associated status; this report does not infer a completed journey.
Before building a live sampler, reuse/close the diplomat entry's own exact type
guard and held-read implementation. Pause/window-thread/TLS are not supplied
by this static model.

A future fixed disposable FRA→POR batch can do initial census, fresh curry
legality and conditional submission, known completion/ownership/paused health,
bounded supervised time if native cooldown requires, fresh stop legality and
conditional submission, then final census. It must not assume the preceding
dispatch created an effect. No intermediate effect sampling is required;
starting and stopping can erase the positive end-state evidence, so both
per-action effect assertions remain false. No batch is implemented here.

Favors amount/rate/decay, complete script side effects, serialization/persistence
matching, runtime lifetime and actual task recall remain unsupported. Generic
relation serialization alone is not a selected save/reload proof.

## Reproduction and limits

```powershell
python -B work/candidates/curry-favors-contract-1375/trace.py --check
python -B work/candidates/curry-favors-contract-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/curry-favors-contract-1375 -p test_contract.py -v
```

35 new CFG entries, 19,581 decoded bytes total, all exploration retained;
each CFG window8192 bytes/max2500 instructions, total ceiling65536 bytes.
Calls are not recursively followed. 12,464 bytes are imported from frozen
reports and individually rechecked against the exact PE. Four irrelevant
exploratory entries remain retained/accounted and are explicitly unused for
curry semantics. No whole executable disassembly or omitted exploratory scan.
The first exploration serialization failed only because a module-valued decoder
version was not JSON serializable. Its incomplete file is preserved as
`decode-01.failed.txt`; the already-written function data was recovered without
redisassembly, and subsequent serialization now finishes before CREATE_NEW.

Trace checks every saved instruction against a fresh bounded disassembly and
all imported rows/data against PE bytes. `prepare.py --check` verifies sealed
source inputs; it does not reproduce runtime evidence. Validation creates new
outputs exclusively. Author tests cover layout differences, strict numeric and
bool types, opposite direction, stale generation, wrong task, broken links,
removed/unknown objects, duplicates, bounds and no effect promotion.
