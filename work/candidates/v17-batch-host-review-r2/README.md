# Offline v17 fixed 36 batch coordinator

This candidate is a pure finite state machine and fixed argv compiler. It does
not spawn processes, publish requests, inspect a game, or register a production
backend. `test_batch.py` supplies a fake adapter. A separate reviewed adapter is
required before any real run. Frozen v17 native, CLI, DLL, fixture and shared
support files are unchanged.

The exact order and targets are projected from the independently reviewed
`../v17-batch-action-matrix-1375/plan.json`, pinned in `source-pins.json`.
Every row gets one fresh legality request. Only an allowed row can progress to
one submit; `support_independence` and `cancel_independence_support` are always
guard surveys and never submit. Every cancellation gets its own legality check;
a positive dispatch does not establish that a cancellable relationship exists.
Fixed native gift/subsidy/trade/insult scalars cannot be supplied by callers.

Only **initial + final** cross-date selected-state censuses are supported. There
is no per-action effect observation, acceptance window, fixture operation,
midpoint snapshot, or automatic yesman control. Positive then cancellation can
erase intermediate state. All individual effects, natural AI acceptance,
request causality, strict single-player provenance, world epoch and production
readiness remain unverified. A known legality rejection is an attempted row,
not a completed feature or successful diplomacy.

Initial census must independently attest the exact world/process/date/last
sequence, paused two-pass consistency, a bounded pool of 100..256 diplomats and
at least 100 entries with state zero. Pool size alone is insufficient: zero
state is an available-candidate resource check, not proof of mission eligibility
or currently installed fixture modifiers. Final census is similarly bound to
its resolved decision date, sequence and sample time, without comparing
cross-date snapshots through a same-day effect matcher.

The sequential order is a valid topological ordering of the matrix. After a
finished row, another row for that target uses a strictly later date even when
the prior row was rejected. A fixed speed-5 request goes exclusively through
the frozen external watchdog. At most 36 date leases and 128 native
publications are allowed. Positive speed's watchdog uses its own frozen 5 s
request TTL; pair requests use 60 s. These are different contracts.

`next(health, now)` and `receive(command_id, receipt, now)` do bounded work and
never block. One resolved intent is durably recorded before returning
`start_once`. A caller may poll progress but cannot obtain another outstanding
publication. Every next sequence is explicit and is incremented only after a
known native completion; rejection creates no reserved submit hole. Each job
has a 40 s outer deadline, including receipt-time validation when no intervening
poll occurred. Clock regression, lost audit, stale/frozen/world-changed health,
unexpected writer, exception or uncertain ownership terminates without retry
or restart/resume. The outstanding intent is retained when uncertain.

`journal(record)` is an internal durable-append contract; a later adapter must
use exclusive reservation, flush and fsync. `validated_frozen_evidence` is an
internal normalization tag, **not authentication or a public ACK**. The future
adapter must independently check complete frozen CLI captures, native event
chains, exact PID/creation/world/thread, request and claim bytes, completion
ownership, fresh latest health and the fixed build before supplying receipts.
This pure model is not a substitute for those validators. A completed speed
receipt still cannot authorize the next request while the latest frame has an
active/pending lease. Its before-date and the following paused frame's exact
after-date must agree. Submit receipts require all preview/gate booleans and
known normal return with consumed ownership.

Offline validation (no game or CLI invocation):

```powershell
python -B work/candidates/v17-batch-host-review-r2/prepare.py --check
python -B -m unittest discover -s work/candidates/v17-batch-host-review -p test_*.py -v
```

The fake runs cover all 36 legality rows and at most 34 submits, every known
rejection, strict-next allocation, mandatory survey skips, uncertain ownership,
late ACK without a poll, stale observation, date/clock aliases, contradictory
dispatch, completed-speed/lease health, and attempted extension of action,
target, scalar or observation scope. Their results are synthetic only.

R2 preserves the sealed predecessor. It permanently latches fatal process/world/thread/flag health while a job is outstanding, while allowing that job's own consumed sequence and running speed lease. A non-returned submit must retain null context-return and container-ownership fields. The predecessor's independent findings are pinned, not overwritten.
