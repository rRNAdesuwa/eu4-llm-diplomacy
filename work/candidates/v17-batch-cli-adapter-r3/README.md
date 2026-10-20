# Restricted v17 batch CLI adapter R3 candidate

R3 preserves the sealed R2 adapter and all driver/native/host/fixture inputs.
The parent reported that the second stopped batch had a successful pause
callback at raw date 56457168, followed by supervisor paused observation at
56457192. R2 incorrectly required those dates to be equal. This candidate has
not read the actual run artifacts or accessed any game process; those reported
values are reproduced only as a finite synthetic contract. Neither stopped
batch may be resumed.

The frozen native `service_lease` triggers at the wall-clock deadline **or**
when the raw-date delta reaches 48. Therefore 48 is a native date trigger, not
a minimum advance guaranteed for every valid pause. This adapter deliberately
supports only the date-triggered subset: timer-only pauses below 48 terminate
as unsupported evidence, not as an asserted native failure. It never republishes
or tries to complete the date advance after that terminal result.

The read-only worker retains the untouched `lab_lease_armed` record from the
exact prefix length/hash already accepted by the frozen reader. It does not
read new tail records to fill a missing proof. Sequence, PID, creation,
initial date, trigger 48, automatic-pause flag and generation limitation are
strictly typed and bound to the original speed request. The armed deadline
must lie in `[command issued uptime + 5000, request expires + 4999]`, matching
creation before the original request's strict expiry gate. Missing or duplicate
arms, a changed prefix hash, or an unbound completion cannot be repaired by
inference.

Both the running and pause native callbacks must retain equal before/after
dates internally, all six cleanup/readback booleans true, no exception, exact
thread/index/speed and no freeze. The running date equals the arm's initial
date. The pause date must be at least initial + 48 and no later than the
supervisor's independently recorded final paused date. The original exact
supervisor identity, roots, claimed request, lease completion, elapsed bound
and final paused-state checks remain. This is not permission to borrow an
arbitrary future date: the final date belongs to this exact supervisor record,
and the driver's following paused health must equal it before the next request.

R2 transition-readiness handling is unchanged: a still-fresh older heartbeat
is not ready, latest live date remains the high-water mark, and pending or
active leases independently prevent publication. The 10-second readiness,
40-second job and 30-minute run bounds remain. Terminal state is irreversible.

Thirteen new tests cover full 36-row callback +48/final +72 replay, known
completion waiting for a final-date heartbeat, callback internal-date change,
reverse intervals, under-48 unsupported evidence, wrong/missing/aliased arm,
request-deadline lower/upper bounds, and exact-prefix/duplicate/tail behavior.
The original 28 tests also run; their synthetic speed fixture now uses the
supported +48 subset. The initial new-test run had six assertion KeyErrors
because the test used summary `reason` instead of `failure`; the implementation
had already rejected those cases. Only that test-field typo was corrected.
No real CLI, status worker, game or native method was invoked.

This is an explicit disposable research runner for the sealed 36-row driver R3.
It changes no native file, DLL, protocol, fixture, HTTP service or production
backend. Only synthetic files and fake Popen were exercised during authoring.
Review and a deliberate `run --ack-disposable` invocation are separate from
import, offline tests and dependency checking.

The driver dictates every pair action, target, mode and sequence. Its two
independence rows remain legality-only surveys. The adapter starts each fixed
`work/run_lab_step_v17_1375.py` argv **once** using Popen, with hidden Windows
console flags and separately reserved stdout/stderr files. All pair parameters
are native constants. Speed can only use the existing exact-process external
watchdog, including its own short TTL, automatic pause and disposable-process
termination behavior. There is no fixture or acceptance-control endpoint.

A separate asynchronous read-only worker validates the frozen build, the
installed fixture's disk/startup evidence, exact PID/creation and loaded DLL,
all four native preflight chains, request/claim bytes, acceptance state,
continuous owned-peace guards and native mailbox records. It also takes held
world/flag and pause observations. Complete evidence and live read-only samples
are saved to exclusive status files. A status worker failure, malformed record
or stale heartbeat is not retried as a publication.

The complete publication capture must have the exact argv, identity, build and
SHA of the native claimed 13-field EU4LAB/3 request. Pair core attribution,
cleanup, no exception and consumed ownership are checked before a trusted
internal receipt is returned to the driver. There is no public ACK interface.
A speed completion additionally needs its permanent supervisor transcript and
native lease completion to agree. Later status must still be paused, current
and free of pending work/leases before a new command is emitted.

The run directory is CREATE_NEW. The journal is flushed and fsynced for every
intent, spawn, completion and terminal state. Existing directories and capture
names cannot be resumed or replaced. Job timeout remains 40 s, status-worker
timeout 10 s, total run bound 30 minutes. Each status JSON is at most 8 MiB,
status count at most 1024, retained status bytes at most 128 MiB, and journal at
most 32 MiB. Polling ticks do not block on a CLI or observer future. Progress is
printed after each known receipt.

Only initial/final observations use the explicitly pinned root-authored
`../v17-batch-census-r3/census.py` census
callback. They remain cross-date selected-state censuses, with no per-action
effect, natural AI acceptance, request causality, strict single-player, world
epoch or production claims. A large diplomat pool alone is insufficient; the
driver separately checks at least 100 idle-state candidates at the initial
boundary. Positive-then-cancel can erase intermediate evidence.

On terminal state, no next action is allowed. `finish()` retains unresolved
driver intent and reports still-running publisher/watchdog process IDs. It
closes its own file handles, but does **not** cancel a published game operation
or kill the game's speed watchdog. It may stop only its own read-only status
worker. An observer future exceeding the deadline may finish its read-only
work later; timeout is not cancellation and never authorizes resume. A frozen
or unknown native result remains terminal regardless of a later good ACK.

Offline commands:

```powershell
python -B work/candidates/v17-batch-cli-adapter-r3/validate.py --check
python -B -m unittest discover -s work/candidates/v17-batch-cli-adapter-r2 -p test_*.py -v
```

After independent review, the root can explicitly supply a complete driver
plan (exact identities, first sequence, run ID and fixed matrix):

```powershell
python -B work/candidates/v17-batch-cli-adapter-r3/adapter.py run --plan <reviewed-plan.json> --ack-disposable
```

This command was not executed during authoring. The first synthetic test run
found parent stdout/stderr handles left open for a hanging read-only helper;
the candidate now closes them and limits helper termination to the read-only
worker. No game process or real CLI was involved.
