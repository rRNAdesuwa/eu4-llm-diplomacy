# Fixed 63500 offline preflight case builder

This independent constructor fixes PID 63500, creation `01dd56c21f9b7c9d`, world `0x23fc93a11e0`, thread 21668 and raw date 56456976. DLL SHA D8B962B19D489FD366F346416BB72A8958F3DC53B504A29EC835D3B99CAFA1EE, manifest b7cf7bb7b31cddf621729e0d541404d80bdb155c6f804082e2a25f651c97067d and BridgeStart RVA 28832 are fixed. Prefix is exactly 181222 bytes / 69af3b8f2edb3691bc7b4a53a048fa7435724bbe56618a2711ede03133c83105.

It reads only explicit offline files. It never opens a process, publishes a request/marker, executes native code or invokes the final formal reviewer. Prior PID 22784 cannot pass this scope and a missing second held read-only report is never filled from status or a copy.

## Inputs and verification

The explicit plan contains thirteen exact path/length/SHA-256 descriptors: seven immutable prefix files, two full held read-only diagnostics, loader, final stage status, build manifest and prefix snapshot metadata. There is no latest-file search, live session path, wildcard selection or capture inference. The selected prefix directory must contain exactly its seven expected files. Path components may not be symbolic links or junctions.

Input files are at most 2 MiB each and 8 MiB in aggregate. Plan JSON is at most 64 KiB, exact JSON keys are required and duplicate/nonfinite JSON values are rejected. Pinned validator sources are individually bounded at 8 MiB, 256 entries and 32 MiB aggregate; zero-byte historical diff artifacts are permitted only in this source inventory, never as runtime evidence. The frozen build verifier additionally reads the exact DLL with its bounded 32 MiB PE export parser and streams fixed source hashes; no unrelated binary/save is read.

Every input is length/hash checked before parsing. All seven phase files are copied from these hashed bytes into a temporary directory before the frozen validator reads them. Original inputs, sources and build are rechecked after construction. This detects changed selected inputs, without claiming a filesystem-atomic or process-atomic snapshot.

The fixed, independently reviewed v17 preflight helpers verify complete held PID/creation/EXE identity, before/after timestamps, full player/world/date, loader/export, all 20 / 1 / 72 / 72 phase claims/proofs, strict every-frame schema, pristine acceptance state, sequence zero and the exact status prefix. The selected RO projection is module base, actor, target, player, date, relation cooldown and actor diplomats. Capture timestamps and read-budget counters may differ; full game state equality is not asserted. Both captures must have distinct paths and bytes, and the first end timestamp must precede the second start.

The one owned-peace stage covers default empty offer lifecycle only. It proves neither war identity, white peace, diplomacy submission, nor a production backend. Current root-provided prefix metadata explicitly describes an active-log prefix, not a stopped/unchanged whole session.

## Separate root execution after review

From the repository root, create a NEW placeholder template, then explicitly fill all thirteen descriptors and NEW output paths. No actual template with filled input descriptors or actual case has been prepared by this author.

```powershell
python -B work/candidates/v17-preflight-case-builder-action-catalog/build_case.py --template <new-plan.json>
python -B work/candidates/v17-preflight-case-builder-action-catalog/build_case.py --config <explicit-plan.json>
python -B work/candidates/v17-preflight-case-builder-action-catalog/build_case.py --config <explicit-plan.json> --create
```

`--create` first completes validation, then creates a previously absent output directory and exactly three exclusive files: scope.json, preflight-case.json and construction.json. It never produces preflight-summary.json. Interrupted partial output is retained; an existing output directory is never retried/overwritten. The root separately invokes the frozen formal reviewer:

```powershell
python -B work/candidates/v17-acceptance-experiment-review/reviewer.py --preflight --case <new-directory/preflight-case.json> --scope <new-directory/scope.json> --output <new-directory/preflight-summary.json>
```

The construction record is explicitly nonfinal and no execution/runtime promotion follows from it.

## Offline checks and lineage

```powershell
python -B work/candidates/v17-preflight-case-builder-action-catalog/prepare.py --check
python -B -m unittest discover -s work/candidates/v17-preflight-case-builder-action-catalog -p test_builder.py -v
python -B work/candidates/v17-preflight-case-builder-action-catalog/validate.py
```

The tests reuse the actual frozen validators with entirely synthetic complete prefix/claim/RO data. Only process/build fixtures and the expected identity constants are replaced in test scope; no process or publication method may run. They cover two-capture failures, strict identity types, timing overlap, selected-state changes, budget-only differences, export mismatch, stage claims, unsafe paths, limits, build rejection, private replay bytes, concurrent input change and CreateNew output.

The initial sixteen-test run had two actual errors: source inventory validation rejected a legitimate zero-byte frozen diff. `history/initial-nonempty-source-failure` retains its three exact author inputs and failure record. The minimum was changed only for pinned source artifacts; the sixteen-test rerun passed. The final nineteen-test suite also exercises hashed-private-copy replay, disk-build rejection and mutation during replay. Earlier negative-test successes are not used as evidence until rerun after that repair. The draft by external_api at v17-preflight-case-builder remains unchanged; this candidate is separately owned and pins the sealed v17 reviewer and its independent review.

The first recorded nineteen-test run had one assertion-message failure: the deliberately invalid diplomat vector was correctly rejected earlier as malformed, rather than at the later equality check. The exact seven sources/index are retained in `history/nineteen-test-assertion-failure`; its original validation remains unchanged. The test now checks that precise rejection and separately supplies a valid but changed diplomat state to reach the equality guard. Production builder logic was not changed by this test correction.
