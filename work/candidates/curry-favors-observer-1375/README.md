# Fixed FRA → POR curry-favors raw observer candidate

This is an isolated **read-only candidate**. Import and the injectable-reader
functions never open a process. There is no CLI, engine getter, native function
call, DLL, sender, hook or memory-write capability. Only the explicitly invoked
future `sample_process(pid=..., creation=..., executable=...)` wrapper opens a
`PROCESS_QUERY_INFORMATION | PROCESS_VM_READ` handle. Its OS paths have only
been exercised through mocks in this candidate, never against a game process.

The static source is the exact local 1.37.5 EXE SHA
`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`.
The already independently reviewed curry-favors contract is inherited without
modifying it. `trace.py --check` revalidates all selected instruction bytes and
data pins against that disk executable.

## Entry type closure

The existing fixture report contains the missing diplomat-entry constructor:

- `6fec80` allocates `0x48` bytes, passes manager kind `+0x14` in `R8B` and
  vector ordinal in `R9D`, calls `6ff4e0`, and appends the returned object.
- `6ff4ef` names concrete entry vtable **`1cac2f0`**. The constructor writes
  marker `+8 = 0x165`, mission pointer `+0x10`, status byte `+0x18`, kind byte
  `+0x40`, and ID DWORD `+0x44`. Kind comes from the manager; diplomats use 3.
- Country construction creates token `0x2746`, kind 3, full owner handle from
  country `+0x20`, and appends this manager fourth in `country+0x1480`.
- Manager type is **`1cac380 / 0x165`**, token `+0x10`, kind `+0x14`, unaligned
  full owner QWORD `+0x16`, and entry-pointer vector `+0x20/+0x28/+0x30`.
- Mission is a different class: **`1c4b2b8 / 0x182`**, never entry marker165.
  It contains entry `+0x48`, ID `+0x50`, actor `+0x80`, target `+0x88`, and
  action token `+0xa8`. Curry token is `0x3acc`.

One additional bounded CFG, `c9f10`, was needed to validate the country manager
holder before indexing its fourth pointer. Its **30 decoded bytes** establish
the vector end/capacity at `+8/+0x10` and stride8. The producer checks country
`+0x1480/+0x1488/+0x1490`, with 4–16 valid manager slots, before reading slot3.
Every new exploratory decode is retained in `decode-01.json`. There are no
unrecorded exploratory decodes: total30B, per-function window8KiB, task cap24KiB.
`report-entry-only-draft.json` preserves the initial zero-new-decode draft
before adding this holder bound; it is not the final contract.

Unknown manager, entry or mission vtables stop derived reads for that object.
A known entry with kind other than3 also stops before mission/status/ID reads.
These states become `unknown_selected_graph`; they cannot establish absence.
Wrong markers, inconsistent handles, invalid bounds or broken backreferences
raise a read error. The producer never calls a type predicate to fill a gap.

## Selected graph and interpretation

The fixed full handles are FRA `0x0100007a00415246` and POR
`0x010000bd00524f50`. It validates the bounded country lookup, both full handles,
current FRA player, raw date, selected root addresses and known reset/load flags.
The flags are exclusions, not a complete world-epoch or paused/SP proof.

The outgoing index is actor's selected bilateral record root, pointer `+0x158`,
capacity DWORD `+0x160`, count DWORD `+0x164`, at most4096 stride16 rows. All slots
must be unique and inside the live country lookup count; object pointers must
be unique. Only the POR-selected relation object is dereferenced. No reciprocal
incoming curry index is invented. The selected record's full owner/counterpart
handles must be FRA/POR in that direction.

An active relation requires vtable `1c7b178`, marker165, removed byte `+0x28=0`,
full actor/target at `+0x10/+0x18`, positive start date no later than the sample,
and mission `+0x30`. A removed object is not followed to its former mission.
The corresponding mission must uniquely match the actor's diplomat vector,
entry status2, entry ID, reciprocal entry pointer, both full handles and token.
All known entries have distinct pointers and IDs; known missions cannot alias.

The state output distinguishes:

| State | What was read |
| --- | --- |
| `active_relation_mission_graph` | A unique complete selected association |
| `selected_index_and_mission_absent` | No selected index row or matching known mission, with no unknown objects |
| `index_absent_mission_present` | No index row, but matching mission remains; possibly travel/return, not verified recall |
| `unknown_selected_graph` | Unknown types, removed/unlinked relation, unsupported status or incomplete association |

Missing is not rejected. Index disappearance does not prove task return,
resource release, request causality, original AI acceptance or successful
native cancellation. A positive graph canceled before a batch-end sample may
leave no positive evidence; this observer must not reconstruct it.

## API and validation

`capture(reader, base)` takes only an injectable `read(address, size)` provider.
It returns **both complete passes**, exact typed equality, separately computed
selected state, read trace and budgets. Both passes reread roots at their end;
code/vtable pins are checked before and after the pair. `atomic` is always false.
Bounds are64KiB/read, 16MiB total, 8192 calls, country/index/envoy counts≤4096.
The aggregate call/byte budget can reject a count below the structural limit;
it never silently truncates. A synthetic103-free-diplomat case is covered.

`inspect_capture(report)` revalidates every complete pass, exact scalar types,
state recomputation, budget trace and optional held-process envelope. Imported
JSON remains unauthenticated evidence. `compare_snapshots(before, after)` is a
pure typed census-difference helper; it allows monotonically advancing dates
with identical selected roots/full identities. It is explicitly not the old
same-day effect matcher. `compare_captures` additionally requires two complete
held-process envelopes with identical PID, full creation FILETIME, module and
disk path/hash. Cross-process addresses are never compared as an identity proof.

The future wrapper verifies the exact disk EXE path/full SHA and PE signature,
holds one read-only handle, checks its PID/full creation/zero exit time before
and after capture, rechecks loaded PE headers and disk SHA, and closes on every
exit. Creation is a canonical16-digit lowercase hex string; PID is a strict int.
It does not hash all loaded-image bytes or authenticate arbitrary saved reports.

Run only these offline author checks:

```powershell
python -B work/candidates/curry-favors-observer-1375/trace.py --check
python -B work/candidates/curry-favors-observer-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/curry-favors-observer-1375 -p test_observer.py -v
```

All runtime/execution/effect/causality/authority/visibility/strict-SP/world-epoch/
pause/object-lifetime/persistence claims remain false. Favors amount, growth,
decay, save layout, DLL integration and actual samples are not implemented or
verified. Unknown native unwind/TLS/side effects grant no call authorization.
