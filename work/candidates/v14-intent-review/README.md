# Isolated v14 phase publication repair

This candidate is not materialized or built. Root exclusively owns those later steps.
The v13 session 45844 / 01dd56a52618bc90 is abandoned with its permanent intent intact.
Its first publication failed because a fresh read correctly saw the newly written
host intent, while the publisher treated that same invocation as a retry.

The 20 native sources differ only by `v13`/`V13` to `v14`/`V14` replacement.
Five fixture files are byte-identical. Eleven host entrypoints use the new version;
only the protocol helper has a behavioral change. Public `check_ready` and
`prepare_request` remain unchanged. No API backend is registered.

For a stage only, `CREATE_NEW` opens an intent with read-only sharing. Full write
and `FlushFileBuffers` precede a real evidence reread. The held file identity,
single link, exact bytes, and path are checked. Fresh attempt diagnostics must
show only a host intent, without a native claim or stage begin. A local copy of
that one phase's readiness evidence can then pass the unchanged public guard.
The intent remains held through no-replace marker publication. There is no
external ignore/override argument. Every error retains the intent, so a later
invocation cannot retry, even if the old file has identical content.

The native phase matrix remains 20 ordinary lifecycle / 1 default-owned-peace /
72 preview / 72 command. The default peace object proves no war identity,
negotiated offer, send, AI acceptance, or settlement. The whole DLL has a sender;
the phase tests remain no-send. World epoch and live single-player provenance
limitations remain unchanged.

Run `python -B work/candidates/v14-intent-review/prepare.py --check` and
`python -B work/candidates/v14-intent-review/verify_tests.py` from the repository.
The tests use real Windows temporary files and actual `read_evidence` callbacks;
they never access a game process, inject, compile, publish a live marker, or start
a server. The validation runner records source hashes before/after and preserves
each run in a new directory, including failures.

The original `input-pins.json` and `initial-pin-rejection.json` preserve a real
generation refusal when the shared HTTP discovery file changed concurrently.
Root explicitly approved that two-line discovery change as a new v14 support
dependency. `input-pins-v14-support.json` binds it; `support-delta.json` proves
that reversing exactly the two discovery changes reconstructs the v13 hash.
The old v13 manifest is unchanged and its current shared-support check fails.

The first 12-test run failed one test because its supposed stale heartbeat was
only 1100 ms old, inside the permitted 2500 ms window. Only the test was fixed
to use an out-of-bound future timestamp; the held-intent implementation did not
change. The failed candidate is preserved under `history/b19bdb687488b91236a14daad88487e847e81bf3175dd27041c1c6e0b914c108`.
Each phase fixture now also checks that its actual temporary volume is NTFS.
