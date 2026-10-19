# v17 batch ledger validator — pure mock candidate

This is a new offline candidate. It has no `run`, `sample`, publication,
process reader, actual-case preparation or runtime-directory discovery entry
point. The author did not read the ongoing batch or growing native log.

`ledger.audit()` replays an explicitly supplied, hash-bound journal with the
unchanged reviewed driver R3 and adapter R2. It requires exactly the fixed 36
action/target rows, sequence 1 as the prior fixture boundary, sequential
publications from 2, adjacent successful legality before submission, the
driver's same-target date rule, permanent no-retry intent order, exact fixed
CLI argv/capture bytes, typed ownership/SEH normalization, known legal
rejections without an invented submit, and only initial/final census receipts.
A terminal batch, missing final census, missing completion, active helper,
unexpected event or extra record after the final summary cannot pass.

The pure result is **ledger consistency only**. It always retains
`native_source_replay_required=true`, `native_execution_verified=false`,
`individual_effect_verified=false`, `request_causality_verified=false`, and
all production/SP/world-epoch claims false. No cancellation is treated as
proof that its earlier positive action took effect. Cross-date selected state
censuses are not passed to a same-date effect comparison.

The final adapter supplied a completion when its own bounded checks passed,
but its journal does not record every coordinator tick or completion tick.
The offline replay checks a feasible ordering of the recorded issue/status
times; it cannot independently prove the actual 40-second completion duration.
`actual_completion_elapsed_verified` remains false. Native claim TTL and
supervisor timestamps remain available for a separate fixed-source audit.

## Required next gate, before any actual success review

Root must first freeze an explicit finalized case containing the stopped
session and its complete log, exit identity, batch scope/journal/summary,
all named status/capture/supervisor artifacts, two real census reports, and the
initial 20/1/72/72 preflight summary. No `latest` lookup is permitted.

An additional independently reviewed entry point must then:

1. Verify every explicit file descriptor before reading/importing it; copy
   only bounded fixed inputs to a private offline location if needed.
2. Preload the canonical formal v17 modules and verify origin/default-root
   bindings, avoiding the previously diagnosed candidate-MIRROR import error.
3. Run frozen `lab.read_evidence` on the complete fixed session. Its phase
   claims, request claims, fixture profile and lease-pause claims are required.
4. Match each `status_prefix_requirements` item to a complete-line byte boundary
   and SHA in that full log. Match the status frame and each complete request
   record to its actual prefix, rather than trusting cached `evidence` JSON.
5. Recompute both real census receipts from every strict typed raw pass using
   the pinned observers; bind the full held creation/world/player/date and
   selected report roles. The injected `census_checker` seam here is purely an
   internal testing interface and must not be an actual-case user option.
6. Check the explicit final stopped identity and selected batch boundary;
   do not infer missing final files or borrow evidence from a different run.

This candidate intentionally cannot complete that next gate. Synthetic prefix
hashes and census marker files in the tests are not actual native evidence.
No actual-case success CLI is exposed while those gates are absent.

## Bounds and tests

Artifacts: at most 1,400 explicitly named files, 8 MiB each, 160 MiB aggregate.
Journal: at most 32 MiB / 10,000 lines; at most 1,024 distinct status captures.
Source hashes are checked before module import. JSON duplicate keys, nonfinite
values, bool/int/float aliases at typed contract boundaries and noncanonical
relative paths are rejected. No source or existing artifact is overwritten.

Tests drive the real sealed adapter/driver with fake Popen and a fake census
callback. They cover all 36 rows, 34 synthetic dispatches, a separate native
legality rejection, missing final evidence, repeated/gapped identities,
publisher hash/argv binding, unknown ownership, altered summary and strict
JSON boundaries. This is not a native or game test.

The first real offline run had 14 tests / 2 errors: frozen Windows adapter
journal paths use backslashes, whereas the private byte inventory uses `/`.
That initial source and failure record remain under
`history/initial-winpath-failure`. The repair normalizes references only after
rejecting absolute paths, drive syntax, empty segments and traversal; inventory
keys remain canonical and duplicate status aliases share one identity. The
second run passed all 14 tests. No native proof condition was changed.

```powershell
python -B work/candidates/v17-batch-summary-review/prepare.py --check
python -B -m unittest discover -s work/candidates/v17-batch-summary-review -p test_ledger.py -v
```
