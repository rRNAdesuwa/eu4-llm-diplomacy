# V19 private fixed client — separate candidate

This is a research client candidate, not a production diplomacy backend. It
imports and checks files only; actual process reads and publication occur only
through an explicit CLI `status` or `stage` invocation. The author validation
did not open a game process, read an actual session, inject, load a DLL, call a
native game function, or publish a real request.

The only accepted build is the sealed bootstrap `build-attempt2` directory:

- DLL SHA256 `d907f38e5bc108489b315a37b564d565b9fc4ff333012b62af586058691ab31f`.
- Manifest SHA256 `b8e85393c96122949a60173ecec83f657a1d6dec24c5af0483aa7abb32d8e49a`.
- BridgeStart RVA is parsed from the pinned PE/manifest (`19264`).

The original build helper's `__file__`/`ROOT` remain unchanged. Private imports
map the pure reader's module graph to its exact pinned files; no `sys.path`
substitution selects a candidate mirror or a formal API module. The manifest is
recomputed from every exact source, DLL bytes and PE export. The permanent
bootstrap wire must equal the canonical identity. Loader schema, identity,
bootstrap hash/length, DLL path/base/export address, normal return, and clean
installation fields are checked. This is source-bound local evidence, not a
cryptographic attestation against replacement of all local files.

Bootstrap independent review `30d872d4…896753` and pure reader independent
review `1cb2947e…64248a` are pinned as development provenance. Their booleans are
not treated as runtime authorization. This new client requires its own
independent review before actual use. No prior seal was modified.

An empty raw journal is accepted only with the exact completed startup sequence
(bootstrap, at most three bounded install attempts, hook installed), no claims,
and no owner/core events. It has no claimed world snapshot. Once a normal raw
health row exists, the complete sealed reader handles it; no health/core row is
fabricated. Three-stage receipts plus later health permit only sequence 4.
All original raw and outer files are read; no tail is truncated. Only the sealed
reader's bounded health-only coherent reread behavior is inherited.

The live guard, when explicitly invoked, opens one held process handle with
query, synchronization and VM_READ rights only. It checks full creation time,
alive state and executable path before and after work, exact game/DLL module
paths and bases, a unique visible unowned window thread, disk EXE SHA256, and
remote game/DLL PE headers. Modules are capped at 512, enumerated windows at
2048, each remote read at 8192 bytes, and the per-check total at 32768 bytes.
Disk EXE hashing streams up to 256 MiB. Only selected pinned injector query
helpers are used; its old 1.37.4 constant, `probe_native_state.main`, remote-thread
and loader functions are never called. PE headers are **not** a hash of the
whole loaded image, and roots/window/classifier do not prove SP or world epoch.

Each explicit publication performs three full file/held guards. It requires a
successful owner/startup boundary no more than 2500 ms old and a monotonic local
uptime. Its only TTL is 60000 ms. Publication writes a permanent exclusive
`N.publisher-intent.json`, flushes/fsyncs it, revalidates, writes an exclusive
`N.publisher-pending`, flushes/fsyncs it, revalidates, then uses Windows
`MoveFileExW(WRITE_THROUGH)` **without REPLACE_EXISTING** to publish `N.request`.
The intent remains permanently. Any existing intent/pending/request/claim blocks
republication. An unknown result or any post-intent error preserves files and
does not retry, delete, reclaim, unload or repair the session. Exactly one
selected stage is published; the Host itself executes the fixed five items
after explicit `send_batch` sequence 4. No arbitrary family, target, pointer,
RVA, amount, or control is accepted.

`source_bound_origin_verified` describes the pinned file/loader chain only.
`live_identity_verified` is set only by the explicit live status guard.
`runtime_authorized`, effects, strict SP, epoch and production remain false.
Publication reports `native_result_unknown`; it does not claim dispatch or
effect. A parser `next_sequence` is receipt readiness, not permission to ignore
an existing permanent publisher intent. Completed/stopped offline reports can
use the file-only `provenance.inspect`; the CLI live status is intentionally
strict about freshness and a still-alive held identity.

Offline validation, without game/process access:

```powershell
python -B work/candidates/v19-spy-real-client-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v19-spy-real-client-1375 -p test_*.py -v
```

Future explicit CLI shape (requires reviewed current PID/creation/session,
approved build installation and a disposable research game):

```text
client.py --build BUILD --pid PID --creation HEX16 --session HEX32 status
client.py --build BUILD --pid PID --creation HEX16 --session HEX32 stage lifecycle --ack-disposable-research-send
client.py --build BUILD --pid PID --creation HEX16 --session HEX32 stage family_preview --ack-disposable-research-send
client.py --build BUILD --pid PID --creation HEX16 --session HEX32 stage owned_command --ack-disposable-research-send
client.py --build BUILD --pid PID --creation HEX16 --session HEX32 stage send_batch --ack-disposable-research-send
```

Each stage command is a separate explicit invocation after a validated later
health boundary. There is no loop, automatic retry or automatic stage chaining.
The fixture tests use temp files and fake held/clock/observer objects through a
private testing seam. The public CLI cannot supply those replacements. The
first expanded RO test run failed because its fake canonical-path function did
not normalize Windows slashes; only that fake normalization was corrected.
Neither a test success nor mock provenance authorizes a live call.
