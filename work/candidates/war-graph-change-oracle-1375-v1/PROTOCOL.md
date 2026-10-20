# Pure copied war-graph change oracle

`evaluate_graph_change(before, after, actor_handle, target_handle)` and `catalog()` are pure data functions. No file, process, native, clock, CLI, source loader, HTTP or publisher is used. The module imports no dependencies. These are extra copied-data consistency guards, not newly attributed native checks.

Each input is an exact built-in dict with these keys:

```text
schema = EU4-WAR-GRAPH-COPIED-VIEW/1
identity = {pid: positive DWORD, creation: 16 lowercase hex digits, nonzero}
world = {game_address, database_address, country_table_address,
         now_raw: positive signed32, country_count: 1380}
actor, target = {address, handle, tag, slot}
complete_current_global_scan = true       # supplied claim, never authenticated
global_war_count: integer 0..64
wars: list[war], length == global_war_count
```

A war dict has exactly `current_war_address`, `vtable_rva="0x1d1f768"`, `marker=357`, `started_raw_date`, `primary_attacker_handle`, `primary_defender_handle`, `goal_pointer_raw`, `attackers`, `defenders`, `raw_outcome`. Side lists contain the same four-key country views, 1..64 entries. Raw outcome is uint32; raw start is positive signed32 no later than the view's raw date. No enum or expiry meaning is inferred. Goal is only an aligned canonical pointer value, not a typed goal/definition.

Address and handle strings use canonical lowercase `0x` hex with no leading zeroes. Address values are aligned8 in user range; the selected structural span must fit. Handles preserve the frozen ordinary country encoding: nonzero generation byte7, kind byte6=0, byte3=0, positive 16-bit slot below1380, uppercase/digit three-byte TAG. Exact built-in types are required; bool/float cannot stand in for integers, subclasses cannot supply hooks. Unknown or extra keys are rejected rather than allowing caller authority flags to override the output.

Within each view, country identities must agree for repeated full handles; one slot/address cannot name different handles, and a country cannot alias a war address. Global war addresses are unique. Side handles/slots are unique, sides disjoint, and primary leaders belong to their respective sides. There may be up to8192 member occurrences and1379 unique ordinary countries per view. Lists/counts are checked before traversal. Validation follows only this finite fixed schema; cyclic or arbitrarily nested data does not invoke generic recursion. Malformed input returns `unknown` with a fixed reason code and all authority false.

Across views, PID/creation and the three world address metadata fields must agree, selected full identities must agree, and shared country handles/slots cannot silently rebind. Reverse raw dates are an unsupported comparison and return unknown. These equalities establish only copied-data consistency. Equal PID/creation, root addresses and dates do **not** prove no reload, same world epoch, atomicity, or continuous object identity. Same-address ABA replacement can be invisible even if every copied field is unchanged.

Valid output is `observed_data_pattern`, with global address additions/removals, global ordering changes, same-address field/member/order changes, and the selected full pair's opposing-address sets. Address additions are not named war creation; removals are not retirement, destruction, peace or completion. Same-address comparison is explicitly an address-keyed pattern, not continuity of one object. Multiple opposing addresses are permitted only by this independent pure-data schema. Frozen war_r2 line176 strictly rejects more than one opposing war; its failed capture cannot supply this scene to the oracle. No runtime adapter is implemented, no `unknown` runtime receipt is transformed into a valid input, and caller metadata cannot authorize such promotion. Raw capture receipts, including a `status` field, fail the exact input schema.

The output owns new dict/list containers; inputs are never mutated or returned as mutable aliases. `catalog()` describes the finite schema and limits only. Every result, including unknown, fixes input authentication, current-runtime verification, original-request causality, dispatch, effect, AI acceptance, terms, war creation/retirement, peace completion, native readiness, sender permission, epoch/atomic/lease, persistence, same-address continuity and retry authority to false. It does not increase15/48/44/42 historical effect counts.

Source preparation is limited to the four frozen files in `source-plan.json`, totaling57334B per guard pass. First new offline tests exercise malformed inputs, identity changes, complete/multiple/empty graphs, duplicate/overlapping sides, NULLs, bounds, reordering and explicit ABA ambiguity. No old tests, readers, runtime queries, game, native calls, constructors or source executors run. This candidate remains separate from stable modules and runtime services until independent source review; even source-ready would grant no runtime authority.
