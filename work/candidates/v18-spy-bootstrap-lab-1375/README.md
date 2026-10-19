# Isolated v18 spy no-send bootstrap candidate

This candidate connects the sealed five-family Core and restricted Host to a
private DLL bootstrap and source-bound capture reader. No game process has been
opened by the candidate author, no DLL has been loaded, and no request has been
published. Object/DLL compilation and synthetic tests are not runtime approval.

Only `lifecycle`, `family_preview`, and `owned_command`, in that order, exist.
Every stage covers the fixed five families, FRA to ENG, true/state 0/envoy -1.
The family check is the full action +88 call. The independently owned command
uses wrapper 0x4e9930 and command gate +40. Returning false from either gate is
a normal recorded result, never a grant to send. No sender, transport, command
execute, reply, fixture, speed or acceptance-control endpoint is linked here.

## Source and runtime boundaries

The sealed Core, Host, native environment and journal are linked without edits.
The only game patch in this candidate is the independently installed 20-byte
owner-frame hook at RVA 0x10a6ec0. Its static unwind trampoline/volatile register
preservation and bounded thread-freeze implementation are exact copies from the
frozen v17 sources, with the separate installer logging adapted here. They do
not establish full XSTATE equivalence, strict single-player origin, or an engine
world-lifetime lock. The existing owner-thread and selected-root guards remain
research constraints, not production provenance.

`BridgeStart` is one-shot even on failure. It derives all paths beside this exact
DLL, reads a <=1024-byte `EU4SPYBOOT/1` packet, and checks PID/creation plus actual
EXE/DLL/manifest hashes and loaded code/vtable pins. The NativeEnvironment,
Controller and FileJournal are explicitly constructed in aligned storage before
the hook. The directory ACL is inherited from the sealed private journal. The
unique session is `spy18-PID-CREATION-SESSION`; previous directories are never
rearmed. Held source files and the installed hook live until process exit.

Installation retries at most three times, and only after a prepatch thread
freeze rejection with unchanged prefix and all owned suspensions restored.
Patch/protection/cache-flush/restoration uncertainty is terminal. Duplicate
installation and hot unloading are unsupported. Foreign owner entry, reentry,
SEH, missing source proof or durable logging failure stops further Core calls;
there is no cleanup guess, replay or compensating call.

The outer scheduler counts actual owner-hook entries. Controller frame numbers
count only sampled callbacks: at most one input poll per 100 ms, and an idle
health callback per 1000 ms. These are separate counters, never game frame
counts. The third successful stage still needs a later independent Controller
health callback before `completed_no_send`; after that the scheduler stops
sampling and cannot accept another stage. The installed inert hook remains.

## Durable source-bound evidence

`raw-events.jsonl` preserves the Host's exact original fields, including
`owner_hook_installed:false`, `loader_implemented:false` and
`runtime_verified:false`. Those fields describe that sealed component. They are
not rewritten to pretend it installed the new hook. Separate
`bootstrap-events.jsonl` records actual bootstrap, install, owner-call entry and
return, and complete/terminal results. Each return binds the exact raw byte
range, record range, SHA256, Controller frame and actual owner-entry count.

The file-only `real_capture.inspect` requires the fixed manifest/source/DLL,
canonical bootstrap bytes, actual loader return, derived session directory,
permanent exact request/claim files, every raw row and every outer row. A partial
read, unmatched begin, fault, unknown tail, missing later health, wrong type,
ownership ambiguity or prefix mismatch is rejected. It then runs the sealed
semantic model through a native-origin projection; only the origin marker is
adapted, not ownership or allowed-result rules. All raw health records are
validated before redundant healthy samples are compacted. Core and result rows
are never dropped. Budgets remain 512 raw rows/1 MiB, 1024 outer rows/2 MiB,
8192 bytes per line, and 192 projected input records/256 model events.

A Core `step_begin` is durable intent before its second guard/resolver, not proof
that the native call was entered. Actual normal-return evidence remains paired
with the Core return. Cleanup can safely run after TTL in the Core following a
known return; if the unchanged proposed Python model cannot accept a late
cleanup trace, this reader rejects it. It never changes timestamps to pass.

Local source provenance is not cryptographic attestation against a malicious
user able to replace all files. This reader does not claim current liveness:
`live_readiness:null`. It does not infer strict SP, world generation, diplomacy
effects, AI acceptance, production readiness or permission to submit anything.

## Future explicit research use

These commands are documentation, not author-executed process operations. Root
must independently review the sealed candidate before any runtime use. Select
the exact candidate build directory and explicit PID/creation; there is no
latest-process search.

```
python loader.py --build BUILD --pid PID --creation CREATION --ack-disposable-test --plan-only
python loader.py --build BUILD --pid PID --creation CREATION --ack-disposable-test
python client.py --build BUILD --pid PID --creation CREATION --session SESSION status
python client.py --build BUILD --pid PID --creation CREATION --session SESSION stage lifecycle
python client.py --build BUILD --pid PID --creation CREATION --session SESSION stage family_preview
python client.py --build BUILD --pid PID --creation CREATION --session SESSION stage owned_command
```

The loader writes only its permanent bootstrap packet, never a stage. The client
has a held query-only PID/creation identity, requires source-bound completed
health <=2500 ms old, writes/fsyncs a permanent stage intent and exclusive temp
file, revalidates, then atomically renames without replacing a destination. Each
TTL is 60 seconds; the native owner checks it afresh. Only exact 1/2/3 stage
requests are representable. A publication result is unknown until the original
claim and returned owner health verify. Do not retry an existing intent, request
or claim. A status read concurrent with a callback can refuse because its logs
are incomplete; another read does not authorize republishing.

## Offline validation

```
python -B prepare.py --check
python -B -m unittest discover -s work/candidates/v18-spy-bootstrap-lab-1375 -p test_*.py -v
```

The C++ bootstrap test only exercises canonical codecs and the pure scheduler.
The linked DLL is never mapped or invoked in validation. Python full-stream
fixtures are explicitly synthetic adaptations of a sealed mock capture;
they test the strict parser and source-binding rules and are not real native
evidence. The supplied disk-chain test replaces only its build-verification
result inside the test, not through any public reader callback.

Earlier build attempts remain recorded: missing cstddef in attempt 1, a /WX
test-loop conversion diagnostic in attempt 2, then a successful attempt 3.
Attempt 3 predates the explicit outer actual-thread field; only the final build
listed in review.json is eligible for later review. The first Python run had an
incorrect test expectation of true/list while the mock correctly returned a
five-family false dictionary; the expectation was corrected without changing
gate interpretation. All runtime access remains unperformed.
