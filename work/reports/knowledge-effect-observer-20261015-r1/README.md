# Exact knowledge-sharing pair effects and normal termination

Fixed executable SHA256 `9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a`. This is ordinary bounded Capstone 5.0.7 file evidence, separate from REA identity evidence. No game process/function, UI or command was accessed. The final new decode scope is 25 explicit ranges / 28,117 bytes, below 32 KiB; peak committed memory across the new trace stages stayed below 81 MiB. Partial caller/helper ranges and unfollowed targets are retained as partial evidence.

## Actual pair object

Offer vtable RVA `1c7f320`, slot +48 `528120`, is a 7-byte wrapper into `528130` with the original actor as provider and recipient as target. The shared positive effect requires native state 2 and value 1 (`52869e..5286b0`). It allocates 0x48 bytes, calls `a70930`, then writes the full provider/recipient handles and dates (`5286e5..52871a`). Ask vtable RVA `1c7f0c0`, effect `52be20`, requires state 2 and builds the reverse offer, provider=original target and recipient=original actor, preserving state 2/value 1, then calls the shared effect. Neither initial dispatch nor a nonzero aggregate count proves this object was applied.

| Object offset | Width | Proven meaning |
|---|---:|---|
| `+0` | QWORD | Vtable RVA `1cde0a0` |
| `+8` | DWORD | Constructor marker 357 |
| `+10` | QWORD | Full provider country handle |
| `+18` | QWORD | Full recipient country handle |
| `+20` | DWORD | Start raw date copied from the action |
| `+24` | DWORD | Deadline raw date: action date plus native global233f814 × 8760 |
| `+28` | BYTE | Activation writes 0; removal writes 1 |
| `+29` | BYTE | Constructor clears it; failed duplicate global insertion writes 1 |
| `+30` | QWORD | Constructor initializes 0; later semantic role unresolved |
| `+38` / `+3c` | DWORD each | Constructor initializes -1 / 0; later semantic roles unresolved |
| `+40` | BYTE | Constructor argument, normal positive creation supplies 0; serialized token31dc. Nonzero has additional termination context, so the reader leaves it unknown |

The object kind getter slot +48 is `529fa0`, returning token `0x3776`. Expiry slot +40 is `a70470`, exactly `deadline <= game.now`. A deadline equal to now is expired, even if cleanup has not removed its indexes yet. The object does not store a proven fixed institution identity; a task's presence is not proof that the recipient completed or embraced an institution.

## Bilateral and global membership

`a70a40` registers both indexes. `a70ad0` registers the same object and sets removed byte28=0. `a70b70` removes global and both indexes and sets byte28=1.

Country relation root is the typed embedded object at country+14f8. Provider outgoing sharing container is root+2d0; recipient reverse incoming container is root+2b8. Each container uses array QWORD+8 and signed count DWORD+14. Each 16-byte item is counterpart slot DWORD+0 and object QWORD+8. The reader validates selected full country generations, relation owners/endpoints, unique slot membership and both selected object pointers. Container raw field+10 is retained without inventing a capacity contract.

The global manager is game+1bb8. Its QWORD+10/+18 vector bounds select 24-byte buckets indexed by provider's native country slot. Bucket head/tail/count/iteration offsets are +0/+8/+10/+14. Each 0x20-byte list node contains object+0, previous+8, next+10, deleted BYTE+18. Deleted payloads are never dereferenced. Active proof requires the same typed exact-pair object in both selected indexes and one undeleted global node, lifecycle flags28/29=0, normal flag40=0 and a future deadline. A missing side, generation mismatch, duplicate object/slot, changing read or incomplete global membership remains unknown.

## Normal completion / release of the provider slot

Relation maintenance `a6bee0` looks up the provider index, then the reverse recipient index (`a6c09f..a6c11d`). Its sharing path ends the object when the pair-war index is found, deadline has elapsed, or `a70c30(provider,recipient)` returns null (`a6c130..a6c17f`). The terminal branch calls object+60 and then its destructor (`a6caa6..a6cabe`), which removes global and bilateral membership through the fixed task callback. For the special nonzero byte40 case, a separate relation predicate `28bfb0` is involved; its full business meaning is not claimed.

The existing fixed `knowledge-layout-static.json` contains the complete 358-byte `a70c30` helper. It scans institution registry order and returns the first institution satisfying **all** of these native conditions:

- provider country+c68[id] is nonzero;
- recipient country+c68[id] is zero;
- at least one province in the recipient capital's exact area is owned by the recipient and has that institution's raw local progress below 100000.

If no such institution remains, it returns null. Therefore embracing the current institution frees the task only when no further candidate exists. A sharing task can move to another eligible institution; it does not bind one fixed institution object. Completing all relevant owned capital-area progress for every remaining eligible institution can also make the helper return null. The script fixture should first identify all current candidates, use an ordinary recipient embrace effect for the required institution(s), then let normal game relation maintenance run and observe **both indexes and global membership disappear**. It must not delete the task, call a native helper, or infer release from a counter alone.

The new bounded country caller prefix proves a normal relation update call at `2f408e`; its DL flag is set by native country context immediately before the call. An additional normal country job caller is recorded at `468795`. The complete scheduling chain/frequency is not closed: this report does not promise immediate paused cleanup, exactly one day, or exactly the next month. Keep polling the precise pair during ordinary bounded time progression until the provider's slot is demonstrably absent. The area/global registry/TLS helpers are not invoked by the observer.

## Pure reader and effect predicate

`bridge/knowledge_effect_reader.py` opens no process and has no runtime adapter. The caller must supply an already-held identity-verified read-only port.

```python
state = read_knowledge_pair(reader, module_base, action, actor_full_handle, target_full_handle, identity)
effect = evaluate_knowledge_effect(action, before_state, after_state, full_backend_receipt)
```

Two full passes must match. Status is `active_pair_observed`, `pair_absent_observed`, `expired_pair_observed` or `unknown`. `exact_pair_active_verified` describes current selected state. `evaluate_knowledge_effect` passes only a retained absent→active transition with the same full session/pair and a matching dispatched, consumed, ownership-closed original receipt. Existing active state, aggregate counts, missing baseline and unclosed ownership never become a new request effect. Institution completion, AI acceptance, exact external request causality, exclusive causality, atomic world epoch and persistence remain unverified. R1's original diagnostic knowledge profiles are not edited.

Limits: shared 4096 reads / 512 KiB / 64 KiB single read, 256 index entries, 512 global nodes. Bounds, links, type identities, loaded kind/expiry code, full endpoints, root/guard stability and manual pause are checked. Unknown types only have their vtable read; deleted nodes have no payload read.

Offline verification uses `python -m bridge.knowledge_effect_reader --check`, compilation and `python -m unittest bridge.tests.test_knowledge_effect_reader -v`. No real memory sampling was run by this agent.
