# Restricted v17 batch CLI adapter candidate

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
python -B work/candidates/v17-batch-cli-adapter/validate.py --check
python -B -m unittest discover -s work/candidates/v17-batch-cli-adapter -p test_*.py -v
```

After independent review, the root can explicitly supply a complete driver
plan (exact identities, first sequence, run ID and fixed matrix):

```powershell
python -B work/candidates/v17-batch-cli-adapter/adapter.py run --plan <reviewed-plan.json> --ack-disposable
```

This command was not executed during authoring. The first synthetic test run
found parent stdout/stderr handles left open for a hanging read-only helper;
the candidate now closes them and limits helper termination to the read-only
worker. No game process or real CLI was involved.
