# Exact text configuration source profile R2

This is a new source-only profile. R1, its one failed status, original v2 CLI and
all old tests remain frozen. No new live grant or config pin is created here.

Future authorization must be EU4-PEACE-V2-CURRENT-STATUS-ONCE/2 and bind this
source manifest, controller, child, adapter, a sealed/passed independent review
with those four subject triples, and local_configuration_pin exactly
{path: local.env, bytes: integer 0..65536, sha256: lowercase64}. Build authorization
alone and the old /1 grant fail closed. Runtime config path is ROOT/local.env,
not a command-line parameter. Selection and original budgets remain fixed.

The adapter accepts only r/rt, utf-8-sig, strict/default errors and universal
newlines. It rejects aliases, writes, other text and custom opening options.
Each snapshot opens binary, verifies regular size <=64KiB and expected size,
reserves and accounts the full size+1 request through the unchanged ordinary
Meter, reads once, charges returned raw bytes, compares the raw SHA and size,
closes binary, then privately decodes and validates the frozen KEY grammar.
Generic errors suppress exception context; no raw line/value/text is logged.
Valid text enters a read-only in-memory stream; virtual reads add no physical
bytes. Up to16 snapshots are allowed. Every accepted current result additionally
requires accepted exact-pin snapshots and closed binary/virtual streams.

This validates syntax and byte identity, not configured-path semantics, all
Mods, world compatibility or downstream arbitrary value usage. No global stdout
scrubber is installed and the frozen parser/CLI is not modified. Malformed
syntax/encoding is blocked before that parser can format raw_line. Existing
whole-IO limitations remain: intercepted explicit Python reads, not OS/import
cache internals or full delegated API coverage. Generic donor __getattr__ routes
remain unchanged. Required unmetered routes must block a future live decision.

Only eight new fictional adapter cases may run once, after source freeze.
Fixtures and injected opener paths remain inside this namespace; the real
local.env is never statted, opened, hashed, read, imported or used as a fixture.
The runner compiles only the frozen donor Meter/ReadPort class definitions;
no donor main, old fake/tests, CLI, status, PE, game or native calls run.
First failure stops; no automatic repair/retry. Job45s/768MiB/output2MiB bounds
apply to the new tests, and software source guards remain768MiB/1GiB stop.

Current presence is never original-request effect, acceptance, settlement or
peace completion. All existing false authority and unknown closure remain.
