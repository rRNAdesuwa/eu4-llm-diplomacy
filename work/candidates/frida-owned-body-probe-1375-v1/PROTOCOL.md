# Owned buffer body-only probe — source-only protocol v1

The JS/parser components are candidates and have not loaded Frida or called
game code. This directory also contains a separately prepared host awaiting
independent review; its sources and tests are owned and pinned by the root
agent, outside this component manifest. Loading the reviewed script would hook a game entry,
allocate and write two owned buffers, and attempt one game machine-function
call. It is **not** the old zero-native-call entry observation protocol.

## Host interface

Render exactly `const EU4_BODY_PROBE_CONFIG = <JSON>;` before `body_probe.js`.
The eight keys are `schema`, `pid`, `creation`, `game_sha256`, `base`,
`expected_prefix_hex`, `observer_nonce`, `max_attempts`.

- schema: `EU4-FRIDA-BODY-PROBE-CONFIG/1`.
- pid: exact integer `80340`; creation: `01dd5c075fcf8c26`.
- base: normalized `0x00007ff7034b0000` (equivalent hexadecimal accepted).
- game_sha256: `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`.
- expected_prefix_hex: `4c89442418555357488d6c24b04881ec50010000488b159d8f2901488bf9440f`.
- observer_nonce: fresh host-held 32 lowercase hex digits; max_attempts: `16`.

The script cannot authenticate creation, the image SHA, or nonce freshness.
The host must authenticate its held process/module identity, exact rendered
source, REA evidence, source guards, deadline/cleanup and independent code
restoration. The Python interface is `body_parser.py:evaluate(payload, config)`.
It replays this **whole** schema directly; it does not relabel native-call data
as an old observer record or invoke the old parser.

## Unique message

One ASCII JSON `send(payload)`, compact `{type:"send",payload:...}` at most
32768 bytes. `schema=EU4-FRIDA-BODY-PROBE-OBSERVATION/1`; status is
`raw_abi_postcondition_match` or `unknown`. Success reason is
`owned_body_postcondition_observed`. The old top-level identity, entry_rva,
attempts, observation, temporary_code_hook, budgets, counters and cleanup
fields retain their original shapes. `observation` is the original natural
onEnter Q/thread/depth/registers, five returns plus main-holder slot, and two
equal ordered world projections; these are copied during that callback.

New top-level fields:

- `native_game_calls_attempted`, `native_game_calls_returned`: exact integers
  in 0..1, returned <= attempted, equal to `probe.call` counters at emission.
- `requires_host_authentication: true`.
- `probe`: always the object described below, partial fields may be null on
  unknown. No old ambiguous `native_game_calls` scalar exists.

`probe` has exactly these keys:

```
profile: "owned-zero-A98-G60-body500560-v1"
spent: boolean
allocations: {A: null | {address, size:152}, G: null | {address, size:96}}
before: null | {code:[{rva,address,size,raw_hex},...],
                slot:{rva,address,raw8_hex,value}, owned:{A_hex,G_hex}}
after:  null | {code:[...],slot:{...},owned:{A_hex,G_hex}}
call: {entry_rva:"0x500560", signature:"void(pointer)",
       options:{abi:"win64",scheduling:"exclusive",exceptions:"propagate",traps:"none"},
       attempted:0|1, returned:0|1}
owned_writes: {attempts,returned,requested_bytes,completed_bytes}
```

`rva` values in code rows are the lowercase strings `0x500560`, `0x8eac0`,
`0x8f450` in that order. Full bytes/sizes are 109, 91, 3 and equal the sealed
R17 independent `profiles.json`. The slot rva is `0x1d20870`, size implicitly
8, value and raw little endian qword must equal authenticated base+0x8f450.
All addresses and qword values are normalized `0x` plus 16 lowercase hex.

## Synchronous sequence and limits

After the original entry chain and two projections match, permanently set
`spent=true`. Allocate A=152/G=96 with `Memory.alloc`, retain strong JS owning
references, require canonical 16-aligned spans that are pairwise disjoint.
Explicitly zero both complete buffers with `writeByteArray`; write A+0x48=G
and G+0=base+0x1d207f8 with two further 8-byte `writeByteArray` calls.
The expected four returned writes total 264 requested/completed bytes. An API
write exception records an attempted request, not assumed completed bytes.
These counts exclude code patching by Interceptor and native machine stores.

Read/check full code+slot and both full owned buffers before the call. Require
A initially entirely zero except A+0x48=G, and G zero except its vtable. This
also checks the nine vector qwords at 0x50/58/60, 68/70/78, 80/88/90.
Create exactly one NativeFunction for base+0x500560, void(pointer), with the
fixed options above. Increment attempted immediately before invoking it with
A; increment returned only after normal return. No scalar return is used.
Read both owned postimages then full code+slot again. Only A[0:8] may change,
and it must end at base+0x1c3e578; every other A byte and every G byte must be
unchanged. The before/after object field order is not the runtime read order;
raw read categories preserve counts, not a whole instruction trace.

Any failure is terminal, never retries, and preserves attempted/returned
counters (0/0, 1/0 or 1/1). A NativeFunction exception is unknown, not proof
that propagation safely recovered execution. There is no constructor,
deleting wrapper, free, sender, other explicit game call or world-field write.
The static nested leaf/helper calls are not runtime-measured invocation counts.

Explicit reads are bounded by 192 requests / 16384 bytes. Original categories
remain; add `code_before`, `code_after` (each 4 reads/211 bytes on success) and
`owned_before`, `owned_after` (each 2 reads/248 bytes). Counter scope is every
script `readByteArray`; allocation, implicit native reads and framework reads
are not counted. Successful null-optional entry: 56 reads/1290 bytes; both
optional pointers nonnull: 60/1322; 15 failed fifth slots followed by success:
135/1922. A 1000ms JS timer is a soft callback deadline, not a native-call
timeout; the future host must impose its independent outer bound.

Cleanup uses setImmediate after onEnter returns: detach once, flush, then
read original entry prefix32. Only owned copied data and fixed module code
addresses survive; no historical Q or world-pointer dereference in cleanup.
The old cleanup five booleans retain their names and host-required semantics.
Failed cleanup downgrades success to unknown. Host independent restoration is
still required even when all script cleanup booleans are true.

## Meaning and authority

This is a raw machine ABI test double, not a legal C++ CWarGoal/action object,
constructor equivalence, full native lifecycle, no-CB semantics or diplomacy
effect. Final postimage matching cannot observe the intermediate two stores.
Exclusive scheduling is a JS-lock option, not a world lock. No lifetime lease
or whole-world atomicity follows from matching pointers or two passes.

`field_game_data_writes=0` and `native_game_objects_constructed=0` refer only
to world fields and class construction; they do not deny owned-buffer writes.
The producer keeps pure_RPM, native_ready, native_entry_authenticated,
creation_authenticated_in_script, image_sha_verified_in_script,
lifetime_lease and atomic_snapshot false. The parser likewise keeps all
authentication/lease/effect/native-ready flags false, requires host evidence,
and reports only internally consistent supplied bytes. Unknown never matches.

The script and parser derive from the sealed entry v1 sources by independent
copy, retaining original slot/world layout rules. The immutable R17 profile
and source origins are pinned by this namespace's source manifest. R18 and
the future host own ABI/unwind/call authorization review; this protocol does
not grant execution permission or change any old gate.
