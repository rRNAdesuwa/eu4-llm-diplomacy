# v14 directional-session preflight review candidate

This isolated candidate inherits the frozen review `499cde0e62012fb2dd97a5d3295e3a1db94d7221602c8bc002a500024dc3878c`.
Only `EXPECTED_SESSION` changes in `reviewer.py`: PID 18356, creation
01dd56aa6f724ea8, world 0x221c8dac040, raw date 56456976, window thread 47264.
The thread comes from the already saved and hash-pinned directional health report;
the running process and its complete mutable native log are never read here.

All original strict schemas, whole-prefix frame validation, exact BridgeStart
0x59c0, DLL/build/source pins, durable stage claims, held-RO identity checks,
status/prefix binding and the 20 / 1 / 72 / 72 phase requirements are unchanged.
Only the explicitly preserved no-request prefix is eligible. Later fixture,
legality, request or send events must never be silently trimmed by this reviewer.
The default owned-peace case proves object lifecycle only, not white peace, war
identity, a send, settlement, causality or production readiness.

`prepare.py --check` proves the reviewer's exact byte delta and pins the old
review, its six sources, inherited inputs and the saved identity provenance.
The inherited 17 rule tests now synthesize this fixed identity; an additional
test locks the five constants and runs the complete synthetic four-stage pipeline.
Build locations alone are mocked, as in the frozen baseline. Test artifacts use
CreateNew and retain every attempt. No actual case is prepared or run by tests.

```
python -B work/candidates/v14-directional-preflight-review/prepare.py --check
python -B work/candidates/v14-directional-preflight-review/verify_tests.py
```

Root may later explicitly supply the seven-file immutable prefix and before,
after, loader, status reports to `reviewer.py prepare`, then separately `review`.
The candidate does not discover a process/session, access a game, change runtime
files, publish requests, build/load a DLL, or modify its frozen predecessor.
