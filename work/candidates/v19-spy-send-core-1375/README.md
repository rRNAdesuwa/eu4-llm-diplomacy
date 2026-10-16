# Isolated v19 fixed spy-send core candidate

Only source, an object file and a mock executable are in scope. There is no
DLL, owner-hook installer, process reader, loader, filesystem publisher,
real Host implementation, public API or actual journal verifier. Tests resolve
fixed RVAs to mock functions operating on private allocations. No EU4 process
or native game function is accessed. `production_ready`, runtime, effects,
strict SP, epoch and retry fields always remain false.

The lineage is the independently reviewed v19 R2 plan, plus exact copied v18
core/header/pins under `v18-preimage`. The new implementation reuses the
reviewed field-by-field 0x40 action and 0x58 command checks, not object-padding
memcmp. Source preimages remain byte identical. This version does not depend
on mutable formal `bridge/diplomacy_api.py`. New fixed sender pins are supplied
by the separate bounded sender/context static review and copied unchanged.

## Private Host contract

`Core::invoke(begin|next_item|later_health, Host)` is the only core entry. Host
identity is exact PID/creation/session/DLL/manifest plus sequence 4. The v18 DLL
is explicitly rejected. A real future Host must authenticate the full on-disk
EXE SHA and loaded PE, current process identity, new DLL and manifest, and all
three same-session preflight stages with independently later owner health.
The booleans in this core are private assertions, not file proof or capability
tokens. No implementation presently manufactures those assertions from logs.

The core independently reads exact loaded PE identity, all fixed code/vtable
pins, two matching snapshots, database count (123..4096), fixed FRA slot 122
and ENG slot 46 with complete country handles, current/effective FRA player,
independent actor/target overlord high-byte check, manual pause, no reset/load
source and non-ironman. It locks the same date and selected root pointers.
The restricted server+19f1 byte must equal 0; this does **not** establish strict
single-player origin. Context ready bytes are read individually and require
nonzero +55 OR +80d; holder/context/transport roots and bytes stay fixed. It
does not invent a context vtable, engine lifetime lock, epoch or MP guarantee.

Read/WriteOwned/Resolve/Clock/Guard/Logger/Claim callbacks are trusted private
Host functions, fixed across the batch. Reads are capped at 64 bytes each,
8192 calls/1 MiB per invoke and 65536 calls/8 MiB for the entire Core. The only
writes are the ten exact 1/4/8-byte initialized action fields, after a verified
fresh factory return; there is no externally supplied write address or value.
Allocation identity comes from this control flow, not a standalone event.
Non-mock resolution must equal image_base + the fixed reviewed RVA.

`Claim(user, 4, item_ordinal, identity, stamp)` uses ordinal 0 for the batch and
1..5 for items. True must mean a private unique permanent claim was durably
flushed. `Logger` true must mean the entire typed event was durably appended.
File naming, atomicity, hash binding and actual transport of these records
remain future Host responsibilities. An intent is not a native-enter record.
Normal return events and fault records carry entered/returned state, including
nullable submit observations represented by explicit `*_observed` booleans.

## Fixed order and ownership

Families are corrupt_officials, sabotage_reputation, sow_discontent,
slander_merchants, sabotage_recruitment. There are no caller action, target,
amount, pointer or mode parameters. Initialization is fixed FRA→ENG,
true/state0/envoy−1, same paused date. Each item has a durable claim before its
factory and runs at most once in a new actual owner frame. The next item is
not allowed until a still later clean health invocation commits the prior
item. A future host must bind supplied frame numbers to actual owner entries;
the core cannot independently authenticate a caller's frame counter.

Calls are Factory(token,NULL), family action virtual +88(action,NULL,false),
Wrapper(action,&fresh_null_slot), command virtual +40(command), and scalar
deleting destructors(object,1). Full +88 is necessary; action generic +80 is
not a substitute. False preview cleans only the original. False command gate
cleans the command (which owns its clone) then the independent original.
True gate first normally destroys the original and retains only the command.
Clone secondary date is checked against current locked game date, not a
general assumption that every wrapper simply copies the source field.

The unique transfer is `bool 14ca210(context, void** owned_slot)`. Its target
and command are rechecked after a durable dispatch intent, with a final fresh
work barrier after the last owned-field read. Only fixed local assignments
then separate that barrier from the call. Immediately before
entry, the core relinquishes command and clone ownership and marks the current
item `dispatch_unknown`. After entry it never reads or destroys either object.
Only normal AL true plus caller slot NULL is `dispatched`. False, non-NULL slot,
exception, guard/log failure or uncertain return freezes permanently with the
current item and its known observation flags retained. There is no manual
consumer/execute/drain, reconstitution, resend or cleanup guess. Dispatch is
not an AI acceptance, queue-settlement or selected-effect result.

Before new work, `now < expires` is required; begin requires remaining TTL
1..60000 ms. Clock and owner frame cannot regress. Normal returned-call known
cleanup and later health may cross TTL, but all thread/world guards remain.
Expired new work, reentry, wrong identity, invalid object, claim/audit failure
or SEH is terminal. All mock fault allocations are released by the mock
fixture's teardown only; that is not a core native cleanup or retry.

The new source deliberately contains no wire codec or parser. No stage
progression, phase authentication, disk journaling, real context lifetime lock
or full unwind guarantee is claimed. These must be reviewed in a later Host
integration rather than inferred from mock success.

## Reproducible isolated checks

From the repository root:

```powershell
python -B work/candidates/v19-spy-send-core-1375/prepare.py --check
python -B work/candidates/v19-spy-send-core-1375/validate.py --output work/candidates/v19-spy-send-core-1375/validation-new
```

The output directory must not exist. MSVC builds only the core object and a
private mock executable with `/O2 /W4 /WX`; the core uses explicit SEH and the
mock maps every callable RVA to a mock function. The runner collects the exact
owned command tree, records before/after source hashes and bounded build output.
It does not compile a DLL, map the game EXE, or open a game process.

`derive_mock.py` preserves the one-time initial scaffold derivation. It is not
a final-source regeneration command: the final mock includes reviewed
additional transfer, claim, TTL and final-guard cases. Both development build
attempts and their original input descriptors are retained; the first also
archives its complete local source preimages. The final validation binds the
exact final test and core bytes. Private typed Event traces are not a public
wire format and have no claim to be replayable by the older Python model.
