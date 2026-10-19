# v17 stopped batch review R3 candidate

This is an offline candidate for an explicitly stopped, complete 36-row batch
run by the frozen driver R3 and adapter R3. It does not run an adapter, read a
process, publish a request, load a DLL, or discover an active/latest session.
No actual batch artifacts were read while this candidate was authored.
The previous pure-mock ledger remains unchanged.

`reviewer.py review` requires an explicit finalized case. It verifies pinned
sources before import, preloads the canonical formal v17 protocol and all five
validators, and rejects candidate-MIRROR module origins or default roots. It
replays the fixed preflight case/summary (including both original independent
diagnostics), then replays the entire stopped native log from a private byte
mirror using `lab.read_evidence`. All 20/1/72/72 phase proofs, perpetual owned
empty guards, phase intents/claims, request intents/claims, lease-pause claims,
and exact full process identity are retained. A pending request, unknown result,
unclaimed extra file, altered source, or abnormal/missing held exit cannot pass.

Every journal status snapshot is compared with **the complete evidence object**
recomputed at its exact byte length and SHA in that log. The prefix must end on
a complete line. Its raw lease arms and pause-core records are independently
re-extracted from the same prefix; future completion records cannot fill gaps.
The later full-log record must equal each selected prefix request. Native
sequences must cover the fixture at 1 and every batch publication from 2 without
a hole or an extra request. The normalized ledger still runs the actual sealed
driver and R3 adapter. It requires known ownership/cleanup, typed results,
explicit legal rejections, fresh preceding legality, exact publisher argv and
claim hashes, permanent no-retry order, and matching supervisor artifacts.

The strict stream is a scoped copy of the frozen v17 experiment stream. Its
only semantic changes are the batch's pristine acceptance-window requirement
and R3 date-triggered lease subset. Within each running/pause callback dates
remain equal; pause must be at least initial +48, while the following paused
heartbeat may describe completion of the current engine day. Adapter R3 still
binds that pause to the same supervisor's final date, and the next ready driver
health must equal that final date. Native timer-only pauses below +48 are
unsupported by this reviewer; they are not labeled native failures.

The two census receipts are recomputed internally from all 22 fixed raw
reports, their strict typed two passes, stored selected states, two full held
outer identities, exact health frames present in the native log, and both full
diagnostic passes. Legacy observers are called for **each** pass and followed
by canonical typed comparison; the old Python `False == 0`/`int == float`
equality cannot substitute for the second pass. The ordinary-insult observer's
own strict typed contract is retained. Diplomat pool and idle-state counts are
recomputed, not copied from the receipt. The command date/sequence, process
creation, player and selected target roles must match. There is no user-supplied
checker, imported callback path or skip-verification flag.

This verifies recorded native call/claim history and selected boundary state,
not individual diplomatic effects or AI acceptance. Positive then cancel may
erase intermediate state. `individual_effect_verified`, natural AI acceptance,
request causality, strict SP, world epoch, whole-world and production claims
remain false. `native_execution_verified` remains false; the separate field
`native_log_claim_replay_verified` describes exactly the reviewed evidence.
The original journal lacks coordinator completion tick timestamps, so
`actual_completion_elapsed_verified` stays false even if every recorded order
is compatible with the 40-second job limit. No save/reload proof is added.

## Explicit case

`reviewer.py template` writes a NEW unfinalized JSON template. Root supplies:

- `inputs`: canonical repository-relative paths mapped to `{bytes,sha256}`.
- Paths in that inventory for `batch_scope`, `journal`, `summary`, `exit`, and
  `stopped_audit`.
- `session_files`: exact basename-to-inventory-path mapping for the stopped
  `session-<pid>-<creation>` directory, including permanent phase/request files.
- `preflight_scope`: the unchanged explicit v17 experiment scope (identity,
  world/thread/date, DLL/manifest/export pins, prefix bytes/hash, and paths to
  the independently reviewed preflight case and summary). Its entire original
  input inventory must also appear in `inputs`.

The stopped-audit JSON has exactly `pid`, `creation`, `process_exit_filetime`,
`complete_log`, `session_files`, and `stopped:true`. `complete_log` is the same
`{bytes,sha256}` descriptor as the full log; `session_files` maps each basename
to its matching descriptor. Exit evidence is the recorded exact held-handle
Wait/GetProcessTimes normal exit, with the same creation, exit code zero,
read-only observer and executable SHA. A recorded descriptor is not a process
access request. The reviewer may enumerate only this explicit stopped directory
to reject hidden/pending files; it performs no runtime-directory discovery.

Bounds remain 1,400 input files, 8 MiB per artifact, 160 MiB aggregate, 1,024
status snapshots, and 10,000 journal records. Source reads have a separate
32 MiB aggregate bound. Distinct status-prefix replays have a 512 MiB cumulative
byte budget; exceeding it fails closed and requires a separately reviewed
budget change. Read limits apply to actual `read(MAX+1)` results. Existing
outputs are never overwritten. `check` recomputes and compares an existing
summary; `review` writes only CREATE_NEW output.

```powershell
python -B work/candidates/v17-batch-summary-review-r3/prepare.py --check
python -B -m unittest discover -s work/candidates/v17-batch-summary-review-r3 -p test_*.py -v
python -B work/candidates/v17-batch-summary-review-r3/reviewer.py template --output <NEW-case-template.json>
python -B work/candidates/v17-batch-summary-review-r3/reviewer.py review --case <fixed-case.json> --output <NEW-review.json>
python -B work/candidates/v17-batch-summary-review-r3/reviewer.py check --case <fixed-case.json> --output <existing-review.json>
```

Only the first two commands were used in authoring. Tests separate: complete
36-row fake adapter/ledger replay; real frozen native validator replay on a
synthetic 20/1/72/72 + fixture/pair/speed log; all 22 synthetic sparse-memory
census reports; strict entry/file boundaries; and an entry glue test joining
real preflight/exit/inventory/native replay to an explicitly mocked four-request
ledger result. The glue test is not labeled a full combined 36-request native
fixture. No actual case has passed this new entry until root supplies and reviews
its fixed inputs.

Initial author test errors are recorded in `lineage.json`: a test label omitted
its literal `:None` suffix; a synthetic mocked `verify_build` lacked the formal
signature; and copying that synthetic preflight to another temp root broke the
intended absolute loader-DLL-path binding. Fixtures were corrected without
relaxing those implementation checks or changing any frozen predecessor.
