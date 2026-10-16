# v14 offline four-stage preflight review candidate

This new candidate preserves the untested v13 draft unchanged. It inherits its
bounded content-addressed inventory, loader record checks, selected diagnostic
fields, exact process creation string, and held read-only process envelope.
It adds an explicit case binding for PID, creation, world, raw date, window
thread, build/DLL hashes, and exact prefix length/hash. The status report must
name that exact prefix and final frame, with no requests or outstanding activity.
All real native stage claims are required. Host intents are not replacements.

The actual frozen v14 validators run again for the 20 / 1 / 72 / 72 matrix.
Owned peace requires all nine core records, the durable wrapper result, and a
following healthy frame. An additional whole-prefix event-order check rejects
duplicate phase records appended after a cached phase proof. All five fixed
native parameter scalars retain their existing validation. Native allowed=false
is valid legality evidence, never an AI rejection claim.

The single owned-peace case covers a **default owned object lifecycle only**.
It proves no war identity, parameterized offer, white peace, diplomatic submit,
acceptance, settlement, independent heap deallocation, world epoch, or production
readiness. The loader report records installation, not an independent memory
hash of the loaded DLL. Selected RO snapshots are non-atomic and do not timestamp
individual native calls. The whole frozen DLL contains a sender; only the exact
preserved prefix is reviewed as no-send.

Independent review found that the first candidate accepted an arbitrary,
self-consistent loader base+RVA. The revised candidate pins BridgeStart to
0x59c0 and the independent post-build PE review hash. It also compares the status
frame using canonical JSON, so float/int/bool equivalence in Python cannot pass
the exact-frame check. Every raw frame, including frames after all four cached
proofs, must also match the native complete schema, strict scalar types, fixed
identity, zero request/lease state, and the observed stage completion flags.
The previous ee323031 candidate and all its validation
records are preserved together under `history/ee3230312b52f812ae60d9f572eb8c516f32ceb3e8a5b2d65b2ef4e1221c79fd`.

Root supplied the final v14 build pins in `runtime-pins.json`. This candidate has
collected no actual game evidence. Tests synthesize process observations/logs and
claims, invoke the actual frozen validators, and mock only the disk build location.
The real entrypoint is restricted to root's explicit session: PID 29492, creation
01dd56a7d38f2649, world 0x2f48cc3f030, raw date 56456976, thread 57620.
Synthetic tests substitute that identity constant only inside their test process.
The first test run caught a hash normalization error inherited from the untested
v13 draft (lowercase expected hash versus the validator's uppercase canonical
hash). The v14 reviewer now uses the validator's canonical hash helper. Its failed
source/test snapshot and output are preserved in `validation-results/initial-*`.

From the repository, validate the candidate with:

```
python -B work/candidates/v14-preflight-review/prepare.py --check
python -B work/candidates/v14-preflight-review/verify_tests.py
```

For a later explicitly collected prefix, root can run:

```
python -B work/candidates/v14-preflight-review/reviewer.py prepare --pid PID --creation HEX16 --world 0xWORLD --raw-date DATE --window-thread THREAD --session PREFIX_DIR --before BEFORE.json --after AFTER.json --loader LOADER.json --status STATUS.json --output NEW_CASE.json
python -B work/candidates/v14-preflight-review/reviewer.py review --case NEW_CASE.json --output NEW_SUMMARY.json
```

`PREFIX_DIR` holds exactly the explicitly inventoried session.json, install.claim,
four native phase claims, and research-1375.jsonl. The log bytes must hash exactly
to the supplied status digest. If the stopped full log contains later frames,
root must preserve the exact previously declared prefix separately; the reviewer
never discovers a latest PID or silently trims/extends evidence. Inputs must be
repository-relative regular files. Publication uses CreateNew and fsync; no
result is written on validation failure, and existing results are never replaced.

The case generator validates before writing. The reviewer copies only the
inventoried bytes to a disposable offline directory for all four validator runs,
then rehashes original inputs and the frozen build. No process, network, DLL load,
mailbox publication, native call, or formal build is performed.
