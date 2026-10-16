# Early origin capture: isolated native source review

This is a source candidate for the exact 1.37.5 executable, SHA256
`9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`.
It does not hook, read or call the game, create a DLL, load a library, open a
mailbox, export an API, or authorize diplomacy. No C++ compilation or execution
has occurred in this review. Frozen v12/v11 sources and artifacts are untouched.

`capture-core.h/.cpp` implements only the fixed-storage record transport and
invocation bookkeeping. `test_capture_core.cpp` contains synthetic tests to be
compiled separately if later authorized. `sites.json` and `pins.h` are generated
from the final offline observer map and exact disk bytes. Every hook/return/
inline-store site explicitly remains unsupported. A byte prefix is not a patch
length and is not a proof that those instructions can be relocated.

## Record and bounded execution contract

Each record is 392 bytes: a 64-byte header and a 328-byte payload. The payload
has a 64-bit presence mask and 40 unsigned 64-bit scalar slots. Unused slots
must remain zero. Presence distinguishes an observed zero from an absent value.
`Field` supplies stable names; `config0/config1` and the type/flag/transport
fields flatten the arrays in the existing Python reducer. This is a native
in-memory layout, not a portable network protocol. No untrusted payload should
ever reach it. The internal interface cannot write through recorded addresses.

The header binds ticket, epoch word, monotonic clock sample, thread, span,
parent span, preserved entry RSP and original return VA. The real adapter must
obtain thread/clock/register values directly; accepting caller-supplied scalars
in synthetic tests does not authenticate them. Neither PID/creation identity
nor the logging envelope has been implemented. Field completeness and native
origin state transitions remain the separate final reducer's responsibility;
an empty structurally valid payload cannot form a source witness.

The capture object has 256 ring slots and a 32-entry owner-thread invocation
stack. A compile-time assertion caps its storage at 128 KiB. Atomic 64/32-bit
operations must be lock free on the target. There are no loops waiting for
another thread, retrying CAS, allocating, writing a file, or calling the engine.
Bounded loops only initialize/copy fixed storage or inspect the 40 scalar slots.

`test_capture_core.cpp` has ten synthetic groups: FIFO reuse through three ring
wraps, an unpublished earlier ticket, publication timeout, capacity exhaustion,
reservation abandonment, invalidation despite logging failure, nested tokens,
each return-identity mismatch, wrong thread/clock/depth/unwind, and malformed
payload/active-scope/foreign-revocation cases. These are **test source**, not a
passing test claim. Real concurrent scheduling, exception delivery and code
generation have not been tested.

## Publication and loss

The ring is MPSC with exactly one consumer. A producer checks capacity then
attempts one strong head CAS. Contention is conservatively terminal; there is
no spin or second attempt. A reservation is move-only and consumed once by
publish/abandon. Its owning producer writes only its slot, then release-publishes
the exact monotonic ticket. The consumer acquire-loads only its expected ticket.
It never skips a hole to accept a later ready event. After copying, it clears
ready and release-advances tail; a producer acquire-loads tail before reuse.
Tickets never wrap. The caller must not share one reservation between threads,
concurrently call the single consumer, or destroy storage while any call exists.

If a reserved producer has not published, `pop` returns `pending` without
reading the payload. A later poll after 50 ms of observed missing publication
sets terminal loss. This deadline is measured when polled; it is not a timer
that independently runs after the consumer dies. No request authorization may
continue while pending. An adapter catching an exception after reservation must
call `abandon`/`abnormal_return`; otherwise the consumer's missing-ticket path
is a backstop. An already acquired reservation may still finish after a
concurrent loss, but a terminal consumer never interprets it as evidence.

Loss publication does not depend on a free ring slot: a packed atomic epoch has
bit 0 = revoked, bit 63 = terminal, bits 1..62 = generation; another atomic
holds first-fault thread/reason. Revocation occurs before attempting to log an
invalidation. A failed revocation CAS, overflow, full queue, wrong thread,
recorder reentry, bad token or exceptional return sets the terminal bit.
The first-fault field can briefly remain zero after terminal becomes visible;
terminal is sufficient to reject, and diagnostic readers may wait for metadata
without letting engine work continue. There is no API to clear terminal or
revoked state, reset tickets, reuse storage, or rearm a session.

The revoked bit deliberately stays set even for a synthetically complete trace.
This module neither creates an origin witness nor authorizes a native call.
Its atomic state protects only its own diagnostics. It does not synchronize
engine object lifetime. A foreign invalidator touches only atomics/ring storage,
never the owner span stack. Any future reducer must compare the live atomic
generation before and after consuming evidence; event adjacency or an older
record's epoch is insufficient when another producer invalidates concurrently.

## Invocation, reentry and initial origin filtering

Only the selected owner thread may enter/leave ordinary observed scopes. Each
entry creates a monotonic span and captures the current stack top as parent.
Each normal return must match site, span, parent, original RSP and return VA.
This catches reuse or reordered return tokens. It does not prove that a return
trampoline actually ran. An unfinished scope prohibits frame snapshots.
Recorder-internal reentry is terminal; ordinary nested engine scopes are
supported after the preceding recorder call has finished. `stop` always retires
the candidate, including a clean stop. No exception cleanup calls the engine.

`invalidate` conservatively revokes even when binding is unclassified. The
entry RCX is recorded as an integer, never dereferenced to identify freed
objects. `binding_verified=false` cannot be exported as the final reducer's
confirmed `bound_identity_match=true`. The adapter that distinguishes the
expected initial Play context installation from replacement of an already bound
context has **not** been implemented. Without it, over-revocation prevents a
completed origin sequence; that is preferable to suppressing an unknown mutation.

## Exact capture points and ABI obligations

`sites.json` enumerates every origin scope and the finite invalidation set from
the fixed reports, with ordinal, RVA, pdata when present, 32-byte identity pins
and individually decoded complete prefix instructions. It does not claim that
these sites form a whole-program cut or run on one thread. New decoding is
limited to prefixes and capped at 4 KiB. Previously proved store/call instructions
are separately byte-checked against the file.

Decoding stops at an unconditional transfer/return/trap or a known function end,
even when fewer than 32 bytes were decoded. A 32-byte identity pin may therefore
include neighboring bytes; `identity_pin_extends_past_decoded_prefix` marks this.
Those neighboring bytes are not asserted to be part of the hooked function.

| Point | Scalar evidence required at an eventual adapter | Status |
|---|---|---|
| Play `1120dd0` | Entry RCX is callback; frontend is `[callback+30]`, not RCX. Bind its holder/game and exact mode/config, then a matched normal return. | Entry register/dereference and return adapter unsupported. |
| Fallback `113b350` → explicit context ctor `14c8940` | Type is ctor fourth argument R9D (`14c8969`, forwarded at `14c92be`). Bind RCX object and nested invocation, then context type/flags/transport/backlink after return. | Register/data extraction and return adapter unsupported. |
| Context install `811ab0` | Preserve RCX frontend and RDX owning-pointer container; identify holder before native write. `811add` publishes context; `811afa` may destroy the old one. A tail jump at `811b11` also exists. | No blanket RET-only hook: tail-return/unwind handling unresolved. |
| Frontend update `10da520` → server ctor `803270` | Caller `10daead`, normal return `10daeb2`; original R9 is holder, original `[RSP+28]` is config argument 5 = frontend+400. | The stack slot is defined at original callee entry, never after a recorder prolog. |
| Config copy `80b4c0` | Caller `803d27`, normal return `803d2c`; RCX=server+1708, RDX=that exact frontend+400. Bind to this constructor span. | Exact scalar call-site identity known; hook unsupported. |
| Holder publication `14c2530` | RCX=holder, RDX=input owning pointer. `14c2559` clears input, `14c2563` writes holder+70, `14c2573` can delete the old server. | Prefer matched helper entry/return over inventing a store patch. |
| Server deleting dtor `80b420` and body `80b570` | Compare preserved entry object identity; revoke before continuing. | Entry hook unsupported; no post-destruction dereference. |
| Frame `10a6ec0` | Only outside observed scopes; data snapshot and generation comparison still need a safe reader. Frame/helper have unknown virtual callbacks. | Frame location does not prove a lifetime lock. |

The normal-return addresses above identify the caller; neither is supplied as
a detour target. Site-specific source roles, default config `(1,0)` and exact
type2 profile come from the fixed reports. Steam's type1 SP path remains outside
the prototype; type1 is not automatically multiplayer.

## Trampoline contract, intentionally unimplemented

Before a single hook could be enabled, an independent implementation must:

1. Revalidate exact process creation identity/full image SHA and runtime bytes;
   establish installation before the first observed Play. A late map attachment
   cannot synthesize the missing origin sequence.
2. Select a whole-instruction overwrite region after explicit relocation
   analysis. Recompute RIP-relative operands and relative control flow, account
   for branches into/away from the region and pdata boundaries. No prefix length
   in this candidate is an approved overwrite region.
3. Preserve original machine state needed at that site, including flags,
   volatile/nonvolatile registers and applicable floating-point/vector/XSTATE
   control. Satisfy Windows x64 stack alignment, shadow space and unwind metadata.
   Saving a few GPRs or assuming a C++ callback preserves all state is insufficient.
4. Associate each normal exit with its exact invocation while handling tail
   jumps, C++/SEH unwinding, nested callbacks and applicable return protections.
   Do not merely replace `[RSP]` and assume every path executes a RET.
5. Revoke at entry before a known bound mutation. Establish thread quiescence
   and instruction-pointer exclusion for installation/removal separately.
   Atomic event publication does not make patching executable code atomic.
6. Provide static-lifetime buffers and a nonblocking capture fault path. No DLL
   unload, heap destruction or buffer reset is permitted while producers might
   still access them. A stopped consumer must disable witness use immediately.

No point currently meets this complete trampoline contract in executable code.
The next independently reviewable step is a platform adapter design plus
isolated compilation/synthetic testing of this core, not injection.

## Reproduce disk checks

```powershell
python -B work/candidates/origin-native-capture-1375/prepare.py --check
```

This checks the pinned observer/report inputs, site enumeration, complete
instruction bytes, call/return identities, generated pins and source hashes.
It is not a compiler or a test runner. `review.json` accurately keeps compiled,
linked, game access, strict-SP and production states false.
