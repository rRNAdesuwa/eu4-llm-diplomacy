# V21 NativePairEngineDraft private port

This isolated candidate implements the unchanged private V21 R2 `SyntheticEngine`
interface with a real, compile-only Win32 native call platform and a distinct fake
memory/call platform. It has no DLL, entry point into EU4, loader, sender, context,
transport, queue operation, HTTP route, publisher, public backend or runtime grant.
The real platform object is **not linked into the test executable**.

The R2 header/cpp are byte-identical private versioned copies. Their independent
review is `work/review-results/v21-pair-r2-action-catalog-20261008a/review.json`
(`d60e69164605b6505d891448029622b3e7a2baa18a7dce397c79460cecb46e4f`).
This adapter is a new implementation and requires its own independent review.

**Confirmed integration blocker:** sealed R2 expects `envoy=-1` immediately after
the negative spy setter, before a synthetic explicit bind. Actual `586330(false)`
writes the resolved entry ID at `586424`. The adapter preserves that value and
its binder only verifies equality; it never clears, masks or overwrites a different
ID. `test_r2_spy_setter.cpp` reproduces the full R2 freeze with faithful fake native
behavior (`envoy_binding_changed`, two native-shaped fake entries, zero preview
or cleanup). Eleven R2 component modes integrate; StopSpyNetwork stays unsupported
at the R2 component integration boundary. Twelve direct adapter modes can be tested
in isolation. A new separately reviewed R3 caller/binder revision is required;
this candidate does not modify the sealed R2 source or claim that issue is fixed.

## Narrow native ABI

| Operation | Fixed target and arguments | Ownership/result interpretation |
|---|---|---|
| Factory | `35d210(uint32 token, NULL)` | Normal non-null candidate, validate private RW storage + type + explicit defaults before issuing a key. Normal NULL returns no key. |
| Mode | exact profile setter `void(object,bool)` | No invented return bool. Only initialized owned original; once. Spy negative mode reads its actual native-written nonnegative int32 envoy; the private graph result must independently match it. |
| Full preview | profile vtable `+88(object,NULL,false)` | Normal false is a legal rejection. May change caches/String32. It is not a read-only query. Never substitutes local `+80` or generic `4e9d00`. |
| Wrapper | `4e9930(object, &local_slot)` | Return must equal `&local_slot`. Owns an independent clone and a `0x58` command on known success. No memcpy cloning. |
| Command gate | `4e8630(command)` / command vtable `+40` | Normal AL false is a legal rejection. No send. |
| Original dtor | exact deleting dtor `(original,1)` | Discard return pointer; no host allocator/free. Marriage uses its dedicated dtor. |
| Command dtor | `4e7470(command,1)` | Native destructor owns clone destruction; the adapter never separately destroys a clone. |

| Profile | token / object bytes | vtable | full +88 | mode setter | original dtor |
|---|---|---|---|---|---|
| Vassal | 2940 / 40 | 1c7fd20 | 51f4a0 | 4e99d0 | 129450 |
| Marriage | 28df / 68 | 1c80ab0 | 4ef7b0 | 4e99d0 | 4ed5b0 |
| Improve | 2ddb / 40 | 1c7dd68 | 5746d0 | 4e99d0 | 129450 |
| Guarantee | 2941 / 40 | 1c7fe50 | 521f00 | 4e99d0 | 129450 |
| Spy network | 3378 / 40 | 1c7cc48 | 5858e0 | 586330 | 129450 |
| Curry favors | 3acc / 40 | 1c7aef8 | 5ae110 | 4e99d0 | 129450 |

All numbers in the profile table are hexadecimal. Positive and negative modes
remain those of the R2 registry; they are not arbitrary public state/token input.
The new static `core-five-full88-and-spy-entry-1375` report is pinned as a separate
author supplement, pending its independent review. Its normal AI originals are
stack objects; that fact is not used to establish heap ownership or a heap dtor.
Heap default/clone/deleting-dtor contracts retain the existing pinned sources.

## Ownership, views and limits

An `OwnedId` combines a process-local adapter serial and ordinal, with at most 64
issued objects per adapter. It is not a pointer, country handle or public credential.
IDs are never recycled; foreign adapter IDs, dead IDs and clone-as-original
destruction are rejected. The private fixed registry stores exact original,
command and clone addresses and prevents overlap of every live typed extent.

Factory normal return and wrapper's known native control flow provide allocation
provenance. `VirtualQuery` alone does not establish allocator provenance or the
precise size of a heap allocation. The adapter checks the complete expected typed
extent in a committed `MEM_PRIVATE` / `PAGE_READWRITE` region, exact vtable and
marker `0x165`, and selected fields. It does not claim OS memory as independent
proof of ownership. Unknown return candidates remain privately retained, without
freeing them or exposing addresses in diagnostics.

Every read is at most 64 bytes; total adapter lifetime limits are 16,384 reads and
1 MiB of read bytes. Action fields are read individually at their actual widths.
No object padding is compared. Marriage String32 reads length/capacity/force,
validates inline or private heap storage and reads every selected character plus
the present terminator. Original preview output is bounded to 128 characters;
factory and wrapper clone must have the empty `length=0,capacity=15` contract.
Only the nine fixed original init writes exist. The native setter supplies the
value byte and negative-spy envoy. `bind_envoy_owned` validates the same ID without
writing. No String32 storage is copied or written.

Every native exception, callback exception, reentry, failed read/write, alias,
inconsistent command/clone or changed current type terminally freezes the adapter.
Known IDs and unresolved return candidates are quarantined. There is no guessed
destructor, cleanup after uncertainty, retry, automatic reset or destructor cleanup
on C++ scope exit. A normal native false is separate from an exception. A normal
NULL factory/wrapper result follows the R2 caller's explicit no-object path.

## Required private Host integration

`native_platform.h` is the fixed composition interface. `Authority` is not a
permission flag accepted from a request. A future separately reviewed private
Host must supply callbacks from its held process/session and one immutable lease
baseline established by its native owner callback:

* `fresh(user,base,owner)` must freshly verify owner/pause/current roots/date,
  held PID/creation, full disk SHA and loaded PE identity. It must not reject
  already-known normal cleanup merely because work TTL expired.
* `final_operation(user,Call)` runs after loaded prefixes, slots and all other
  platform preparation, immediately before the fixed ABI call. The callback
  obtains a new monotonic clock **after its own identity reads**, and checks the
  original expiry. Only the two deleting-dtor calls may ignore expiry; neither
  may ignore time rollback or identity change.
* `final_owned_write(user)` is the corresponding final barrier after private RW
  range validation and before each scalar memcpy. Expiry in the middle of init
  freezes with partial owned state retained; it does not guess cleanup.

The compiled platform rejects absent callbacks. It checks `GetCurrentThreadId`,
20 bounded loaded code prefixes and 26 loaded vtable slots. The copied R2 Guard's
earlier clock cannot replace the final callback. Mock tests explicitly expire or
change identity in the last read/preparation and verify no native entry occurs.
The callbacks and repeated equality checks are **not** an atomic lifetime lock,
world epoch, ABA exclusion, strict single-player proof or runtime authorization.
No real Host/Authority, TAG resolver, five cancellation readers or spy graph reader
is implemented or invoked by this candidate. Root is developing those separately.

`pin-provenance.json` records only 820 fixed bytes from the full SHA-pinned offline
EXE (20 code prefixes, 26 slots); before/after whole-file SHA is streamed. No new
instruction decoding occurred. Prefix comparison is not whole-function proof.

## Offline validation and preserved development

```powershell
python -B work/candidates/v21-native-pair-port-1375/prepare.py --check
python -B work/candidates/v21-native-pair-port-1375/validate.py validation-independent-1
```

The second command creates a new directory. It compiles the unchanged component,
adapter, and real platform as MSVC `/std:c++17 /O2 /W4 /WX /MT /GS /EHsc` objects.
Only the component, adapter and fake platform are linked into the mock executable.
The exact child tree is assigned while suspended to a kill-on-close Job with a
768 MiB per-process and whole-job cap and 55 second bound. Compiler helper children
that outlive their completed command are stopped within that job only and recorded.

Tests cover six profiles/twelve modes, normal full/gate false, marriage inline and
heap text/empty clone, sequential component use, int32 spy endpoints, forged/foreign
IDs, alias/type/size/storage violations, original/command clone cleanup, injected
native failure and C++ exceptions at all call types, reentry, read budget, final
barriers and partial writes. Check totals include repeated per-read assertions;
they are not that many independent scenarios. The real platform is compiled, not
executed; mock success does not validate live ABI, game allocator or current state.

`development-draft0`, four development build attempts, their source hashes,
compiler outputs and fake outputs remain preserved. All four development builds
passed; the final version adds the required final private callback barriers and
adapter-scoped keys and the truthful spy setter integration counterexample. An initial exploratory report-key lookup printed a KeyError
(`binary` vs actual `game_sha256`); it did not modify data or execute native code.
The final seal reports exact source/inputs before and after validation. All game,
runtime, sending, production, SP and world-lifetime claims remain false.
