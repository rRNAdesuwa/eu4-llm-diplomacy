# Isolated v13 Python host review

This directory generates review files only. It never materializes into the
repository's live tool paths, builds a DLL, installs a fixture, opens a process,
starts an HTTP server, publishes a real request, or invokes game code.

Inputs pin native review `ceaa1802a0230761ebaf27476c368377d59485cd275f7d8466da5052223a1ef7`,
its original 42 inputs and all generated native files, the frozen v12 host and
three phase verifiers, shared read-only helpers and offline test fixtures.
`python -B work/candidates/v13-host-review/prepare.py --check` checks all 91
inputs and reproduces `new-files.json`, `candidate.diff` and `review.json`.
Without `--check`, writes remain under this isolated directory only.

The 11 prospective Python files include protocol, loader, build recorder,
speed watchdog, explicit request CLI, four phase verifiers, HTTP adapter and
server CLI. Five unchanged fixture definitions are copied under a distinct
prospective v13 fixture source directory. No shared API or capability registry
is modified. The HTTP route becomes `/research/v13` (localhost port 8770);
HTTP still exposes only the 36 restricted pair actions, not phase/fixture/speed
or arbitrary parameters. Default CLI use plans; explicit publication remains
required. No production backend is registered.

The phase order is lifecycle20 → owned-peace1 → preview72 → command72.
`stage owned_peace` writes exact PID/creation-bound marker bytes from the native
contract. The consumed native claim is permanent. Any previous claim, host
intent or phase begin blocks a repeat. Partial logs can describe an incomplete
attempt but cannot open later work. Missing frame diagnostics, failure records,
duplicate or reordered core steps, mismatched scalar types or claims fail closed.

Owned-peace evidence consists of nine ordered core records (begin/complete for
four calls, then return), a successful returned wrapper and a later healthy
paused frame in the same world/date. Integer core flags and boolean wrapper
flags are checked separately; a final core return is not a wrapper result.
The verifier does not treat destructor return as independent heap-release proof.
All 36 pair IDs, positive-only families and five fixed scalar log fields stay
unchanged; no real peace operation is added to the mailbox.

Prospective build manifest schema 2 contains 20 native sources, 11 Python host
sources, eight exact shared support sources, fixed native review SHA and the
four-stage contract. Recording is exclusive and refuses an existing manifest
or session. Verification hashes DLL, native, host, support and fixture files.
Root must materialize these files and review the complete build before the
native script's single formal build. Its call to `record_lab_v13_build.py`
already matches; this task does not change the native candidate.

`python -B work/candidates/v13-host-review/verify_tests.py` creates a new evidence
directory, runs synthetic filesystem/log/protocol/HTTP-service tests, and stores
exit codes, failure details and input/output hashes. Tests import the generated
files themselves, use temporary synthetic sessions, mock live-process entry,
and do not bind a socket. Existing v12 experiment audits are not rerun or edited.

The loader still requires a disposable-test premise and verifies its file, not
the provenance of the current live world. Root/player/date checks are not an
authoritative world epoch or full multiplayer-origin proof. This remains an
isolated research host; runtime and execution readiness are not claimed.
