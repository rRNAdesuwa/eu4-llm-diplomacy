# V19 private client R2: verified launcher and final publication time gate

This is a separately sealed research candidate. R1, the pure reader, native
sources, DLL and manifest are unchanged. It implements no backend and makes no
runtime, effect, SP, world-generation or whole loaded-image hash assertion.
The earlier R1 source-gate and post-identity timing counterexamples are retained
and pinned. A normal host/core still independently checks TTL before native work;
a late file publication alone is not evidence of a late native call.

## Trust chain and entrypoint

The root operator first verifies the exact `launcher.py` SHA from the independent
review/sealed report, and invokes it with a trusted Python `-I -B` interpreter.
The launcher contains a literal SHA256 for `inventory.json`. It verifies and
captures every listed local/dependency byte, including `client.py`, `frozen.py`,
`provenance.py`, `readonly.py`, `graph.py`, `pins.json` and `source-index.json`,
before executing any candidate code. Count <=256, each <=2 MiB, total <=20 MiB;
paths must be ordinary, single-link files without symlinks/reparse points.

`source-index.json` lists the payload/dependencies but not itself, the launcher or
inventory. The inventory adds the index's SHA. The launcher binds the inventory.
The report/root expected SHA binds the launcher. This is deliberately acyclic;
there is no self-hash and no claim to resist replacement of the launcher,
interpreter, whole tree or compromised standard library in the Python process.

A private graph executes captured bytes, not pyc, sys.path or an existing
candidate `sys.modules` entry. Original sealed modules retain their `__file__`
and original bytes. Nested source-loading uses verified snapshots as well. A
private temporary module registration is used only for Python dataclass
annotation processing and is removed after evaluation. Legacy injector/probe/
local_config modules are privately loaded; their main/loader/native entrypoints
are never invoked. Only the already-reviewed read-only helper methods are used.
The dependency's old 1.37.4 hash constant is not used as a game-identity check;
readonly.py explicitly hashes the 1.37.5 EXE as before.

The only public actual CLI is **launcher.py**. Importing library code or invoking
its private fake seam is not a trusted entrypoint. `client.py` rejects direct
script execution. `prepare.py` and tests are file-only developer checks.

## Publication timing repair

All R1 durable intent/pending/no-overwrite and three complete-source/held gates
remain. After the final `held.identity_check()` returns, R2 reads uptime again,
requires it to be monotonic and typed, rechecks the exact stage and <=2500 ms
logged-health freshness, and requires `now < original expires`. Only then does
it issue the no-replace `MoveFileExW` call. No original deadline is extended.
Any failure retains the permanent intent/pending/request state; never resend or
clean up an ambiguous publication. Native work retains its independent guard.

## Checks (no process or native call)

```powershell
python -B work/candidates/v19-spy-real-client-r2-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v19-spy-real-client-r2-1375 -p test_*.py -v
```

Tests replay the inherited 19 temp/fake methods plus byte tampering of every
execution local/pins/index/inventory; forged valid-origin cache entries; captured
bytes vs later local reads; typed inventory/path/schema failures; final guard
latency expiry, stale health, rollback and type aliases; exact freshness/TTL
boundaries. They never open an actual process, read a runtime session, or publish
a request outside a temporary test directory. Temporary no-replace renames use
the real Windows filesystem. Original R1 development failure history remains in
its sealed report; this revision records its own actual validation attempts.

## Future explicit invocation, after independent review

From the repo root, verify launcher SHA externally first; substitute only the
explicitly approved BUILD/PID/creation/session. No defaults choose a process.

```text
python -I -B work/candidates/v19-spy-real-client-r2-1375/launcher.py --build BUILD --pid PID --creation HEX16 --session HEX32 status
python -I -B work/candidates/v19-spy-real-client-r2-1375/launcher.py --build BUILD --pid PID --creation HEX16 --session HEX32 stage lifecycle --ack-disposable-research-send
```

The other explicit fixed stage names are `family_preview`, `owned_command`, and
`send_batch`. Each is one invocation after validated readiness; seq4 is the
fixed five-family batch automatically serviced by the sealed native Host, not
an arbitrary sender. There is no automatic stage chaining, retries or per-action
effect observation. Do not use R1 client.py as a source-authenticated CLI.
