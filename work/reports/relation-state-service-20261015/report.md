# Current relation host and retained live-byte audit

This additive host exposes the frozen relation reader for `offer_alliance`,
`royal_marriage` and `guarantee`. It performs current-state observations only.
It never evaluates a new request, invokes EU4 functions, publishes commands,
writes game memory, saves or reloads the world.

## Independent retained-file audit

`audit_live_file.py` independently decodes each complete 24-byte generic index
header, all used 16-byte entries and the full selected 0x40/0x48-byte object in
the fixed live receipt. It checks signed bounds, duplicate slots, selected
pointer aliases, complete country handles, country-root container arithmetic,
bilateral identity, object vtable/357 marker, complete endpoints, start date and
both lifecycle bytes. All six retained cases and 28 input pins pass:

| Action | Actor | Target | Retained current state |
| --- | --- | --- | --- |
| offer_alliance | FRA | POR | current_relation_observed |
| offer_alliance | POR | FRA | current_relation_observed |
| royal_marriage | ORL | BRI | current_relation_observed |
| guarantee | FRA | SAV | current_relation_observed |
| guarantee | SAV | FRA | reverse_relation_observed |
| offer_alliance | FRA | ENG | pair_absent_observed |

The source live file SHA256 is
`4fcfddb5e8551a132a188a601aa74d9d45a4e663e7591d27c711d76594edbbe9`.
It reports PID 80340 / creation `01dd5c075fcf8c26`, date 56461512,
2325 shared RPM calls, 52162 bytes and a largest read of 11040 bytes.
This audit does not access that process. Raw country headers, the full TAG
table and raw bilateral relationship records are not included in this live
receipt; their original checks can only be attributed to the pinned producer
and reader. The raw generic indexes and selected objects are fully retained.

## New host boundary

`RelationStateObserver(pid, creation, store=None, allow_tag_host=False)` uses
the existing R1 `RuntimeCapture`, `HeldRPMPort` and shared `BudgetReader`.
The existing capture authenticates the held PID/creation, exact main module,
disk executable identity and loaded main PE header. This host does not create
another memory API. Only the default build-7 TAG metadata is permitted.
No research DLL is accepted by default. The explicit `allow_tag_host` option
accepts exactly one research module at the canonical default DLL path, with
the expected machine/timestamp/SizeOfImage; it does not install a TAG session.

Before decoding a pair the host verifies its full source graph and frozen
reader/R1 evidence. It requires the current manual pause byte to be exactly
one, scans every slot in the 1380-entry country table, rejects duplicate
selected TAGs and resolves complete selected handles through the country
database. The frozen reader then obtains both complete current relation passes
and verifies the loaded getter bytes, typed roots, native indexes and object.
Before returning, this host also requires initial roots to match every retained
pass and final roots, re-reads the entire country table, authenticates the held
process again, and verifies modules, frozen R1 pins, default backend and complete
host source graph again. Every held capture closes on success and exception.

The compact result keeps these distinct statuses:

- `current_relation_observed`: both indexes select the same complete typed
  object and the requested direction matches. Alliance and marriage are
  symmetric, so their stored initiator order is not asserted.
- `reverse_relation_observed`: a valid guarantee exists in the opposite
  direction. `requested_direction_matches` and `current_relation_observed`
  are both false.
- `pair_absent_observed`: neither current typed index selects the counterpart.
  `requested_direction_matches` is null.
- `unknown`: no successful complete current projection. Read or guard failures
  do not become absence or action rejection.

`runtime_effect_verified`, `global_membership_verified`, AI acceptance,
request causality, atomic snapshot, world epoch and lifetime lease remain false
for every current-state response. Both indexes are physical root indexes;
country aliases are not counted as independent evidence. Optional local journal
files retain the complete two-pass capture and pins with exclusive creation.

## HTTP and CLI integration

`make_relation_server(observer, base_server)` wraps the caller's already
authenticated handler and returns the same server object. It adds only
`GET /observer/v1/relations/<action>/<actor>/<target>`. Authentication,
capabilities, other GET routes and write refusal remain inherited. The factory
does not bind a listener, invent a combined effect count or modify capabilities.
Malformed requests fail before observation; runtime faults return 409/unknown
with no command retry. The root composition layer supplies its own catalog.

Offline checks and a current query use:

```powershell
python tools/observe_relation_runtime.py check
python tools/observe_relation_runtime.py catalog
python tools/observe_relation_runtime.py --pid <pid> --creation <creation> status --action guarantee --actor SAV --target FRA
```

`watch` uses the same action/pair arguments, duration 1..300 seconds and interval
1000..10000 ms. `serve --port 8775` uses `EU4_OBSERVER_TOKEN`, the existing
loopback/Host/Origin/Bearer checks and a standalone catalog with no configured
request-effect profiles. The standalone service also does not claim that these
three current-state readers increase the request-effect profile count.

## Verification scope

New tests use actual-layout synthetic memory graphs and real local HTTP
connections. They exercise all three layouts, symmetric and directional
queries, retained absence, complete-handle corruption, duplicate TAG at the
last country slot, missing country, pause/load/cache guards, full table
mutation and faults, short object reads, source/module/process changes,
default-host restrictions, the existing held RPM port and PE parser, complete
local journal, inherited routes/authentication/catalog and write refusals.
All loopback listener threads are shut down, joined and sockets closed.
This subtask does not access EU4 and performs no new disassembly. Runtime HTTP
acceptance is delegated to the parent after these sources are sealed.
