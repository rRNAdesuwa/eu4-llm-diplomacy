# Current peace pending queue candidate — 1.37.5

This is a draft read-only candidate. Its only commands are `check`, `catalog`,
and `status --pid … --creation … --actor … --target …`. Current source and
production gates reject status before library/observer/process construction.
The first offline run invokes only new fake tests, check and catalog. There is
no HTTP, watch, dispatcher, hook, native function, save or retry operation.

Status describes the selected actor→target direction in the target's current
queue. Exit0 means file verification or a supported current presence/absence
observation; it never means a request succeeded. Exit2 means unknown/invalid.
An absent queue item is not rejection, acceptance or peace completion. Native
ID0, duplicate IDs and all raw32 states are retained as raw facts; multiple
objects remain a list. No original request/session correlation is available.

The exact design owner graph, independent design review, CLI/tests/source
tools and read-only library roots are pinned in source-manifest.json. It also
pins the CLI itself. Frozen direct-v1 Libraries verifies its existing source
closure and old host manifest. The old host's fixed PID, main, capture, REA,
Frida and registered-argv operations are never used. Reused helpers provide
source validation, host_sample, typed country and structural read checks.

Runtime requires sealed=true/runtime_capture_authorized=true plus independent
source and root production receipts. Each is a top-level path/bytes/sha256
object; receipt JSON must have sealed=true/passed=true/blocking_findings=[],
subject_cli_pin and subject_source_graph_sha256 matching the candidate. The
production receipt additionally has approved_for_current_readonly_status=true.
The source graph hash is SHA256 of ASCII canonical sorted source_pins JSON with
separators(',',':'). These metadata changes need no code change and avoid a
draft-manifest hash cycle. They are not supplied by this implementation task.

Only QUERY/VM_READ/SYNCHRONIZE is inherited. A small RuntimeCapture subclass
preserves the frozen initialization and exit contracts and its entry identity
checks; it routes the existing8192B PE comparison through the same attempt
budget/journal as all later reads. Frozen sources are unchanged. It does not
claim the OS CloseHandle return was checked: close_os_return_checked staysfalse.
All success is committed after normal context exit, held.handle=None, disk and
source postguards. Caller PID is nonzero DWORD, creation nonzero16hex; its fresh
readonly nonce is not an installed TAG session. Disk exact path/38462504B/SHA,
loaded PE, identity/modules, paused roots and unsupported research modules are
checked on the status path only. File commands do not open/stat the PE/game.

Two complete fresh1380-QWORD table/selected-country/queue passes must agree.
Tables are read again after each queue. Country identity uses complete handles,
positive table slots, typed vt/357/header and fresh array binding. Only target
queue head/tail/count/branch are read. Iteration byte must be0; count<=128;
physical chain, previous/next links, tail and no-tombstone active count must
agree. Node flag is checked before any action dereference. A tombstone yields
unknown, even if its action pointer is invalid. Foreign vtables get two8B reads
only. Matching peace objects get64B twice, marker357, target-owner equality and
actor/original-actor coherence. One actor field matching without the other is
unknown. No offer, +40 derived flags, +208 field, full outer210 allocation,
slot98 or missing59ba30 getter bytes are read.

Shared budget:4096 attempted admitted reads,512KiB requested bytes,64KiB per
read, canonical span with lower bound0x10000. Invalid arguments and exhausted
budget do not reach RPM. Short reads keep attempt and returned-byte accounting
separate. Frozen AlignedPort adds8-byte alignment for structural reads>=8B as
an extra conservative reader guard, not a derived native class invariant. The
four exact pinned code ranges bypass only that extra alignment rule (one starts
at4e8205), while still sharing canonical/span/attempt limits and raw journal.
Loaded735B is checked before and after:1470B total, without invoking any code.
The93330B design subtotal excludes root/host/country lookup overhead. A valid
large queue may exhaust the shared cap and return unknown; no silent increase.

Double external reads do not prove an atomic snapshot, ABA exclusion, object
lifetime or world epoch. All native/effect/request/acceptance/completion/lease/
atomic/persistence flags remainfalse. This does not change stable15 profiles,
98pins, native DLLs, or historical48/44/42 counts. It requires non-author source
review and root production approval before any separately authorized real read.
