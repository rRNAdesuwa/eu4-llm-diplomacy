# R3 coherent health-tail file reader

This separate Python-only wrapper keeps the original DLL, manifest, wire,
loader, client source bytes and R2 semantic reader unchanged. It does not retry
a publication or a stage. One original client invocation still performs the
same status read or two publication gates. Only the file inspector may read
whole captures up to three times inside one gate.

The sole retryable failure is R2's exact final paired-tail error, further
restricted to a non-request health callback. Every raw row is checked by the
unchanged strict semantic reducer, including any unpaired row. There must be
a prior complete owner call and at most one extra complete health row. A
pending begin must have request_sequence=0. Claim/core/run-result tails,
malformed or partial JSON/lines, invalid installation receipts, ownership,
roots, identity, clocks, complete contradictions and native faults are terminal.
No old prefix is returned, no tail is removed and no return row is synthesized.

Each later log read must extend the entire earlier byte string. Non-log inputs
must keep their hash/size. A rewrite/truncation cannot erase a previously read
record. Success requires an entire new unchanged-R2 inspect to pass. Persisting
incompleteness fails after the third read. The 10 ms between at most two rereads
is a bounded file-read delay, not waiting for a stage or scheduling progression.

Budgets: each original file bound and line/count bound remains; at most 384
bounded file reads and 64 MiB total per inspect, three raw 1 MiB and outer 2 MiB
captures maximum. Only current/previous log bytes are retained. Success adds
`coherent_read` metadata; a failure raises `CoherentReadError` with all attempt
hashes/sizes/counts/errors and the CLI prints them to stderr. These hashes record
the observed attempts, not an atomic filesystem transaction or trusted signing.

The client preserves CREATE_NEW/fsync intent and temporary publication. An
existing permanent intent blocks another invocation even when all read attempts
fail. There is no automatic re-publish, stage progression, sender or production
backend. The stopped PID 24072 is not reused; its final strict partial replay
had 280 health rows, zero stages/core calls and one intent without request/claim.
The BridgeStart RVA in the original manifest is decimal 15680 = hex 0x3d40.

Offline check/test only:

```powershell
python -B work/candidates/v18-spy-coherent-client-r3-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v18-spy-coherent-client-r3-1375 -p test_*.py -v
```

Future root-authorized entry is `client_r3.py` with the original explicit
`--build --pid --creation --session status` or `stage` arguments. Tests use
synthetic files and fake process/clock; candidate authoring accesses no process,
game, native function or actual stage. Source checks remain local research
provenance, not protection against an adversarial Python interpreter.

The 16 test methods include complete prior stages 1/2/3 and their unchanged
claims, the original three invalid install receipts, stale healthy evidence,
new request/core/fault tails, rewritten files, typed clock faults, bounded
exhaustion, and the second publication gate leaving a permanent intent on
failure. A fake process guard is used only by tests. No actual session was
inspected while validating this candidate. The separate stopped-session
triage is a pinned historical note, not live readiness or stage authority.
