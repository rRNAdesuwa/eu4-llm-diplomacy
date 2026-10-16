# Offered fleet response and yesman ABI: disk-only candidate

This candidate is static evidence for the pinned EU4 1.37.5 executable
`9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A`.
It contains no native implementation, request publisher, console invocation,
process reader or production registration. The frozen v14 files are unchanged.

The offered-fleet AI score explains why successful submission need not produce
a relationship. Its own acceptance virtual `+0x120`, RVA `0x534990`, returns
**−1000** on the ordinary path. With a reason buffer it emits
`DIPLO_STRATEGIC_INTERESTS` and the same score. There is no diplomatic-reputation
or opinion addition in this function. The distinct `+0xc8` virtual constructs
a reverse **ask** request; it is not evidence that the offer's own AI score can
be improved with modifiers.

The special return **99999** requires both:

- `BYTE game+0x23a1 != 0`;
- actor-country slot equals the selected effective-player slot. The selector
  uses `game+0x1e68` only when `BYTE+0x1e66 == 7` and `BYTE+0x1e6f != 0`;
  otherwise it uses `game+0x1e60`. The actual comparison is only the low 16 bits
  after shifting the handles right 32, not a full-identity check.

The generic acceptance predicate at `0x4ea1e0` requires signed score ≥ 1.
No current flag value is inferred here. In particular, a baseline or high
diplomatic reputation does not prove that the special branch was taken.

The common command's AI branch clones the request, tests this predicate, sets
the response state to 1 (reject) or 2 (accept), and queues a separate response.
The original request's transport return and ownership consumption are separate
from that response. For accepted positive offers, the persistent object has
**target as rights holder at +0x10** and **actor as port grantor at +0x18**.

The state-1 branch formats `RESULT` with `DIPLO_DENY` and publishes
`OFFER_FLEETBASING`; the state-2 branch uses `DIPLO_ACCEPT` with the **same key**.
Neither the key alone nor an absent relationship proves rejection. The root's
separate runtime/UI evidence is needed to identify the observed denial; it is
not incorporated into this static report as a native runtime result.

## Actual console call contract

The static command array begins at `0x1fc23e0`, contains 378 rows of 0xa0 bytes,
and has two pinned `yesman` rows. Name, description and callback resolve to
`0x1d34aec`, `0x1d34af8` and **`0xe50180`** respectively.
`0x1720b50` builds runtime records of 0xa8 bytes, placing wrapper `0x172b120` at
`+0x38` and the raw callback at `+0x40`.

The normal dispatcher at `0x1721320` receives manager in RCX, result storage in
RDX, and a vector of command tokens in R8. It excludes the first token (the
command name), then prepares the callback argument vector. With no remaining
tokens, the 24-byte vector is exactly three null pointers. It does not contain
the string `yesman`, an empty string element, or an arbitrary zero-length span.

At the actual callback boundary the inferred Windows x64 ABI is:

```text
RCX: Result40*                   fresh, exclusive caller storage; 8-byte alignment
RDX: const Vector24<String32>*   begin=0, end=0, capacity=0; 8-byte alignment
R8:  raw handler address         used by wrapper only, not by e50180
RAX: original Result40*          normal return

Result40: success byte at +0; padding +1..+7; EngineString32 at +8
String32: union/pointer +0; size +16; capacity +24; inline capacity 15
Vector24: begin +0; end +8; capacity/end-of-storage +16
```

This is a binary calling convention inference, not a claim about original
C++ source type names. The wrapper calls R8 with RCX/RDX intact and returns its
original RCX. Normal dispatcher call instructions `0x172175c..0x172176d` bind
the wrapper, raw callback, empty vector and result storage in one call chain.

The handler initializes its result itself. Its argument count uses
`(end-begin) >> 5` followed by a signed test on EAX; it takes the zero-argument
branch for nonpositive values. A future caller must reject all malformed
containers and supply the canonical all-null vector rather than relying on
that permissive arithmetic. Positive argument counts produce a false result
and a diagnostic without changing the flag.

On the zero-argument branch, `0xe502bf` writes `game+0x23a1 = (old == 0)`.
The handler then marks success and allocates/formats the message
`AI positive response is now ENABLED/DISABLED`. There is no native explicit
on/off API at this address. A planned fixed control would have to enforce
the desired state and canonical prior byte before deciding whether one call
is necessary; this candidate does not implement that control.

## Ownership and failure boundary

The handler moves its formatted local String32 into `result+8` and resets the
moved-from object. It cleans up its local temporary strings on normal return.
The dispatcher then copies the returned success/string into its own output
and destroys the temporary message through engine String32 destructor
**`0x95660`**, with RCX pointing to `result+8`. The Result40 itself is stack/caller
storage and must not be deleted. Output storage must be fresh: the handler
does not release an arbitrary old output string before overwriting it.

A direct caller would own the returned message and need exactly one engine
destructor call on a proven normal-return path. No string pointer may escape
into a later deferred cleanup or be passed to a foreign allocator.

**The flag changes before message allocation.** If the handler or result
cleanup faults, the flag may already have changed and ownership may be
unknown. No unwind recovery, blind second toggle, compensating callback or
speculative destructor is justified by this report. A future host needs
durable once-only intent, immediate pre/post flag observations, existing
thread/world/pause identity guards, and a terminal unknown outcome on failure.

The normal console dispatcher also has behavior that a raw call bypasses:

- Manager `+0x19` gates `yesman` with the message "Command not available in
  multiplayer or ironman mode." It is populated by a startup fragment from
  classifier `0x6eaa10` and `game+0x24d0`; this is not an independent proof of
  strict offline single-player world origin.
- It updates command bookkeeping and invokes an optional global callback at
  `0x2357b50`, whose lifecycle and semantics are not closed here.
- It rechecks the restricted-mode byte after the callback. The observed
  forbidden branch for a nonexception command deliberately writes to address
  zero. Calling the whole dispatcher is not proposed as a safety substitute.

The raw handler itself checks neither paused state nor strict SP nor world
lifetime. This report does not approve a production call path or general
console endpoint. Any future disposable acceptance fixture must retain that
limitation, make on/off explicit, constrain the permitted next experiment,
and prove a later healthy off boundary. Frozen v14 does not support it.

## Next valid test constraints

Do not resend the already-denied offered-fleet request, or revoke an absent
grant. Raising reputation/opinion is not a supported remedy for this ordinary
score. An accepted **ask-fleet** relation may support cancel-fleet testing;
it cannot validate the offered-fleet/revoke-fleet direction. No naturally
accepted AI offered-fleet setup is established by this report. A separately
reviewed future positive-response control would be an explicit test fixture,
and its outcome must never be labeled natural AI acceptance.

The report's readonly field whitelist is limited to the game pointer,
`+0x23a1` byte, and the effective-player selection fields used by this exact
score. A separate readonly observer still needs exact process creation,
module SHA, two consistent typed passes, same-world guards, and validated
full country handles. It must not turn a byte observation into strict-SP or
future runtime-readiness proof. This candidate performs no such observation.

## Reproduction and scope

From the repository root:

```powershell
python work/candidates/offered-fleet-ai-response-1375/trace.py --check
python -m unittest discover -s work/candidates/offered-fleet-ai-response-1375 -p test_report.py -v
```

Initial report creation uses `CREATE_NEW` (`xb`) and cannot replace a report.
`--check` recomputes the report and compares exact bytes. It hashes the pinned
EXE and six earlier reports/helpers, validates each fact's instruction
boundary, validates both raw command rows and the virtual table, and includes
bounded localization evidence. It decodes 16 selected functions/fragments,
3,973 unique instructions / 16,546 instruction bytes, with a 768 MiB process
memory stop. It does not recursively scan callees or read the old whole
disassembly. Exploratory `draft-*.json` are retained as drafts and are not
the authoritative report or validated cross-reference inventory.

Tests cover exact report recomputation, byte/pointer binding, role direction,
message-key ambiguity, score counterexamples and canonical argument rejection.
They cannot prove native execution, cleanup, thread safety or runtime effects.
`validation.json` records the offline commands and final source/output hashes.
