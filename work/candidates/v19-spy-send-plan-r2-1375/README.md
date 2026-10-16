# v19 fixed spy-send plan, pure-model repair R2

This new candidate repairs two findings in the sealed v19 plan. It is still a
synthetic state machine, with no native sender, resolver, file publisher,
process access, DLL or real journal validator. The original static report and
plan remain unchanged and pinned; there is no new disassembly or permission.

F1: `event()` requires an exact string kind before any guard or event counter
mutation. Invalid kinds, including lists and dictionaries, enter the same
permanent frozen state as other invalid events. Valid-looking later events
cannot resume the model.

F2: a `current_item` begins only after the fixed family order and durable item
claim assertions pass. It remains separate from completed `rows`. Entering
submit immediately records `dispatch_unknown` and nullable return fields,
and relinquishes the model's local command ownership. A fault without a
return, an invalid return field, or a known non-acknowledged return leaves that
current record visible. Exact valid return fields are retained without being
interpreted as an effect. Only a later clean health event moves the item into
completed rows. The remaining family list excludes the current attempted item.

`last_recorded_owned_objects` reports only the model's last established local
set. In particular, wrapper/factory failure can leave unknown allocations;
the list does not authorize cleanup. Every current-item summary therefore
sets `cleanup_authorized=false` and `retry_allowed=false`. The current record
can also describe a known return awaiting later health; it is never inserted
into completed rows prematurely. All returned containers are independent
copies.

The request codec, five-family order, exact FRA-to-ENG binding, all native ABI
claims, three required preliminary stage assertions, expiry rules and cleanup
rules are unchanged. `contract.json` and the original 20-test suite are copied
byte-for-byte from the prior candidate. Read the pinned original README/report
for the finite static evidence and unresolved real host/reader/implementation
requirements. A successful model run is not a native result and grants no
production, strict-SP, epoch, causal or effect authority.

Offline commands:

```powershell
python -B work/candidates/v19-spy-send-plan-r2-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v19-spy-send-plan-r2-1375 -p test_*.py -v
```

The seven added regression methods cover non-string kinds, each reviewed
unknown transfer variant in multiple item positions, an enter followed by a
fault, invalid return scalar aliases, later-health separation, pre-enter
ownership uncertainty, completed/untouched summaries, and copy isolation.
`validate.py` only captures those offline commands into a new output directory.
