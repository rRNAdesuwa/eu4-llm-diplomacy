# Native peace repeat-send audit

Build: EU4 1.37.4, SHA-256 `b23fa0e1f698d31b01cdd1c3817a675805d8c6286cb66f9c231e6e2a42544d77`.

Scope was limited to the action vtable, the existing peace-send callback, the
command dispatcher, and the few `.pdata` ranges touching `country+0x24a0`.
No injection or UI operation was performed.

## Confirmed paths

The peace action vtable at RVA `0x1c7b840` has these relevant entries:

| vtable slot | target | observed role |
|---|---:|---|
| `+0x80` | `0x59b480` | execution validity/relationship checks; called by the command executor |
| `+0x90` | `0x59b900` | native “wait until next peace offer” date gate |
| `+0x98` | `0x59ba60` | returns action type `0x293c` |
| `+0x100` | `0x59bef0` | returns `action+0x40` as a boolean-like flag |
| `+0x120` | `0x59bf10` | native preview/legality calculation; returns raw preview value |

`0x59b900` compares the current game date (`game+0x1dd0`) with:

* `game+0x1d9c` when the action actor is the same country as
  `game+0x1da0`; otherwise
* `country_array[action.actor_slot]+0x24a0`.

Its two direct UI callers are `0x130bedc` and `0x130e3d2`. This is the same
date guard already reproduced in the bridge. It is a cooldown/eligibility
gate, not evidence of a separate pending-offer object.

The actual writer of `country+0x24a0` is in function range
`0x4e7c80–0x4e8453`, at RVA `0x4e8111`:

```asm
mov  eax, [game+0x1dd0]
mov  [country_array[action+0x10>>32]+0x24a0], eax
```

Immediately before this write, the executor calls action vtable `+0x98` and
branches on type `0x293c`; the alternate type `0x293d` writes `country+0x2494`
instead. Since `0x59ba60` returns `0x293c`, the tested white-peace action
uses the `+0x24a0` path. Therefore the first successful receipt updating FRA
from `56460528` is consistent with the command reaching native execution.

The same executor first calls action vtable `+0x80` and `+0x100`. The
`+0x80` method (`0x59b480`) performs additional relationship/war-side and
offer checks before the date write; it is the strongest remaining candidate
for a command that is accepted by the dispatcher but rejected before the
`+0x24a0` write. The limited disassembly does not identify a named
“duplicate proposal” flag there.

The preview method `0x59bf10` does not write `+0x24a0`. It checks the current
player/actor relationship and `action+0x208`, then calls `0x1bf180` with the
recipient country and embedded offer. It has no visible pending-offer queue
check in the inspected range.

## Repeat-send conclusion

The second bridge attempt passed the bridge’s date guard and returned
`submitted`, but the unchanged FRA `+0x24a0` means that no native executor
path reaching `0x4e8111` was observed. `submitted` therefore only proves that
`0x14ca110` accepted/queued the command container; it does not prove that the
command passed the later action gates or executed.

Within the inspected functions, no additional standalone pending flag or
duplicate-proposal check was located. The remaining concrete candidates are:

1. action vtable `+0x80` (`0x59b480`) or one of its indirect calls;
2. the dispatcher/queue path after `0x14ca110`, before the command executor
   `0x4e7c80`.

The string `OFFER_PEACE_PENDING_ENFORCE` has no direct static reference in the
current candidate map, so it cannot be assigned to a function from this audit.

## Implication for the probe

The unchanged `+0x24a0` is a useful execution receipt: after a future
submission, observing that field advance is stronger evidence than the
bridge’s `submitted` event. The next narrow diagnostic should record whether
the queued command reaches `0x4e7c80` and which of its vtable `+0x80`/`+0x100`
gates returns false; the current static evidence does not justify changing
the date guard or treating `submitted` as delivery.
