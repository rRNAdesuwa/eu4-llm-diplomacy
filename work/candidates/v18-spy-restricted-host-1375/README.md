# Restricted spy Host source candidate

This candidate supplies a private C++ controller, the exact `EU4SPYLAB/1`
codec, a durable Windows journal and a bounded current-process environment.
It has been compiled as objects and exercised with isolated mocks. It has
**no DLL, export, owner-hook installer, loader, mailbox consumer, publisher,
HTTP route or send operation**. Nothing here has run in EU4.

The only permitted profile is the five sealed spy families, in their fixed
order, `FRA -> ENG`, positive value, state zero and envoy -1. Each explicit
packet selects one complete stage: lifecycle, family full preview, then owned
command. Packets cannot select an individual family, pointer, RVA, console
string, amount, fixture, speed, acceptance override or target. A normal `false`
family preview or command gate is a research result and confers no authority.

## Private boundary

`Controller::start` is one-shot. `frame` is a proposed private owner callback,
not a hook installer or public ABI. The native environment also has a
process-wide one-shot initialization guard. Reentry/foreign-thread failure
sets atomic terminal flags before any continuation; only the owner may inspect
the non-atomic status snapshot. There is no reset or rearm.

`NativeEnvironment::initialize` is compiled but is **not invoked by the tests**.
Its future trusted bootstrap must supply exact PID/creation, a session nonce,
expected own-module and manifest SHA256 and the disposable-test premise.
The self-module anchor is an internal fixed function, not a request pointer.
Initialization verifies current PID/creation, `eu4.exe` disk SHA, loaded PE
timestamp/image size, sealed Core prefixes/vtable slots and root getter slots.
The executable, containing module and exact manifest bytes are streamed with
hard size limits and held with read sharing only, denying later write/delete.
It does not parse a future build manifest or authenticate a loader; those
bootstrap duties and their public entry are unimplemented. The unique visible
unowned window thread is a candidate owner, not proof that a hook was installed
or that every world transition is synchronized.

Every frame and Core barrier reads the selected world twice. Required values
include the exact database+118 country array, signed database+124 count
123..4096, FRA slot122/ENG slot46 full handles and country+18f0 overlords,
game/player/effective-player roots, raw date, server and pause-manager backlink,
manual pause, reset/load/ironman state and the reviewed multiplayer classifier.
Both countries must have no active overlord. All selected roots, fields and
the date remain fixed for the entire three-stage session. The classifier
reproduces the reviewed bounded chain (maximum256, cycle rejection), but its
false result is **not strict offline single-player provenance**. Selected root
equality is **not a world generation token or an engine lifetime lock**.

Read access is at most64bytes per transfer, committed readable regions only,
with guard/noaccess rejection and SEH. Core-origin reads have a32768call/2MiB
Host cap in addition to the Core's smaller per-run cap. The environment has
a262144call/16MiB frame cap including profile samples and image pins. The
selected list traversal is the only bounded list walk; no heap scanning occurs.
The environment object is tested on mock-owned VirtualAlloc pages only.

`WriteOwned` is private to the pinned Core callback. It requires the factory
normal-return event, then exactly ten fixed initialization offsets, widths,
values and addresses in order. Writes are limited to committed private
read-write pages and never alter protection. **Allocation identity comes from
the pinned Core's trusted control flow** (`original = factory return`), not
from matching an object layout or from independently authenticated Event IDs.
No arbitrary address/data interface is exposed. Resolver addresses are the
fifteen fixed factories/clones/preview/gate/destructors already in the sealed
Core, with no command execute or transport target.

## Claims, timing and log meaning

Codec input is at most1024bytes of printable ASCII and LF, with exactly the
sealed sixteen ordered fields. Re-rendered bytes must match exactly. Sequence
equals stage ordinal1..3. Failed parsing leaves the caller's output untouched.
Before Core entry, `now < expires <= now+60000`, a fresh paused health record
and exact session identity are required. A stage gets a permanent exclusive
claim containing its original bytes before any Core work; after claim flush
the clock, world and expiry are checked again. Partial claim/write/flush/close
failure freezes. Each new stage needs an independently sampled later callback
frame after the previous successful returned Result. Health is written before
that frame can accept a packet. This code does not invent an owner frame source.

The journal creates an exclusive session directory under a trusted private
bootstrap parent. It resolves and holds the parent and child directory handles,
rejects reparse directory handles, sets a protected current-user/SYSTEM ACL,
never reuses an existing session, and never removes a partial claim. Log writes
are one-shot append+flush with8192byte lines,512records and1MiB total bounds.
Close failures are checked by explicit `close`; destructor cleanup is best
effort after the object can no longer perform actions. It is not a security
boundary against malicious code already running as the same user/process.

`EU4SPYHOST/1` is a **private raw journal schema**, distinct from the sealed
logical model schema. Each record has actual Host identity, frame/time, image
base, observed selected roots/profile and an ordinal. Each Core Event contains
all original typed fields and its own Stamp. `step_begin` is a durable intent
before the second barrier/resolver; it is **not proof that native entry happened**.
Normal-return events carry the Core's entered/returned flags. The final callback
is not stage completion without the returned successful audited `Result`.

Fault Events and returned failed Results are retained where the journal remains
healthy. They use the last known envelope with
`current_observation_verified=false`, make no new engine reads and do not
authorize cleanup or retry. An audit failure is not retried merely to produce
another diagnostic. Every serialization overflow is terminal. Known-return
cleanup may cross expiry; new work cannot. Unknown native/ownership/cleanup
results freeze without guessing a destructor or compensating call.

## Replay and remaining integration

`audit_mock.py` validates the captured C++ mock envelope and its selected raw
fields, then projects only `mock_environment=true` through the independently
reviewed sealed R2 projection and unchanged protocol/model. Its synthesized
logical `durable` field describes mock journal assertions, not authenticated
game evidence. A real origin, fault trace, missing returned Result or missing
later health cannot pass. `availability()` explicitly says the real Host
projection is unsupported until owner-hook/bootstrap/capture authentication
exists. No runtime, selected effect, AI acceptance, strict SP, epoch or
production claim can be raised by this replay.

Minimum subsequent work: independent source/mock review; a new immutable build
manifest plus trusted bootstrap; reviewed owner-entry/return/exception hook
installation and revocation; a private exclusive file-input consumer; and an
authenticated real journal exporter/replayer. Those must remain separate from
this candidate. A future owner callback must not claim arbitrary calls of
`frame()` constitute engine frames. No DLL compilation, loading or publication
is authorized by an object build.

The four additional normal-AI initialization paths are referenced only through
their new sealed static report, separately from the original Core's historical
restriction. This candidate does not rewrite that predecessor or claim live
initialization/preview results. Full action+88 family preview is preserved;
command+40 gate is a distinct call and never replaces it. Preview may touch
lazy caches, so it is an owner-thread no-send experiment, not a read-only probe.

## Offline checks

```text
python -B work/candidates/v18-spy-restricted-host-1375/prepare.py --check
python -B -m unittest discover -s work/candidates/v18-spy-restricted-host-1375 -p test_*.py -v
work\candidates\v18-spy-restricted-host-1375\test_host.cmd <new-unique-output-directory>
```

The command compiles four objects and two mock executables with `/W4 /WX`.
It does not link a DLL. The native environment object is linked only into the
isolated-memory test; its real initializer is never called. Mock files are
created under a new temporary directory and retained. Validation-attempt1
failed for a missing initializer-list dependency; attempt2 failed for a mock
DWORD/uint32 callback type. Both failed before any mock execution and remain
preserved. Later attempts passed. Final validation records exact source and
artifact hashes rather than treating these earlier compilations as final proof.
