# v18 capture verifier R2

This is a file-only Python verifier revision for the original v18 bootstrap
candidate. It does not create or relabel a DLL, change a manifest, load a process,
publish a stage, or replace the original loader/client. Root must explicitly
select this verifier for evidence review.

The independent review `55d953382e43b67ce4ecaeaf84054babe9ea1848e0ff5fb5ef0252643f920a39`
found three impossible successful-install receipts accepted by the first
verifier: nonzero error, zero collected threads, and nonzero failure thread/RIP.
The native `ThreadSet` source already rejects a completed enumeration with zero
threads; success has no failure diagnostic. No native change is needed.

The sole semantic change is the result-zero branch: `collected >= 1` and
`error == failure_thread == rip == 0`, in addition to all prior strict integer,
failure-stage, resume, retry and patch checks. `0 <= suspended <= collected <=
512` remains valid: collected terminated thread objects can be skipped. The
verifier deliberately does not require collected and suspended counts to match.
No previously unsupported failure or retry branch is enabled.

Original DLL SHA256:
`6aff9a9fc4d46692c9be0ac39b0c741bf8eeb840abaf8731d0144510a938f00b`.
Original build.json SHA256:
`d1f65cae88cfb7ed2535c590206b9844882f0870f02773da23c747a6346aa5e5`.
Both still live under the original candidate's `build-final` directory. The old
manifest continues to describe the old source set. The new capture-reader
revision is bound separately by its own source/index hashes; it is never
presented as an original DLL manifest field. All original native sources,
objects, DLL and metadata remain byte-identical.

`_frozen.py` loads only three fixed helper files by pinned bytes, preserving their
original `__file__` values. Consequently their build verification still reads
the original directory and source pins. `real_capture.py` retains the complete
old validation body with only that dependency import and the successful receipt
check changed. `prepare.py --check` verifies the exact delta and all lineage.

Offline reproduction from the repository root:

```
python -B work/candidates/v18-spy-bootstrap-capture-r2-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v18-spy-bootstrap-capture-r2-1375 -p test_*.py -v
```

`inspect_capture.py --pid PID --creation HEX --session HEX [--complete]` only
reads the explicitly identified original private session. Optional `--output`
is CreateNew. It is not a publisher and never chooses the latest process or
session. No actual session was inspected while authoring this revision.

All runtime, strict-SP, epoch, production, and individual-effect limitations of
the original candidate remain. This revision addresses only the identified
capture-verifier gap, not a game-execution approval.
