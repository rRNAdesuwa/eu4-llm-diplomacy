# Independent live diplomacy observer

This version composes the frozen R1 effects, R2 recipient replies and the new
allocation-guarded knowledge reader v2. No frozen file is changed. Native code
is never called; no command is reserved, loaded, published or retried.

Public Python interfaces:

- `LiveDiplomacyObserver(identity, store=..., allow_tag_host=False).prepare(command)`
  writes an exclusive local baseline. `command` has exactly `request_id`,
  `action`, `actor`, `target`.
- `.observe(request_id, record=True)` returns the original transport/audit facts,
  `native_receipt` in full for knowledge actions, main `effect`, and independent
  `supplement.r1_knowledge_effect`. `record=False` writes nothing.
- `KnowledgeRuntimeCapture.capture_knowledge(command, binding=None)` uses the
  existing held VM_READ port, one shared 4096-call/512-KiB budget, and the frozen
  exact-pair decoder's two complete passes. It opens no second process handle.
- `live_catalog()`, `live_source_pins()` and `make_live_server(...)` are separate
  from the unchanged R1/R2 modules.

CLI:

```text
python tools/observe_diplomacy_live.py catalog
python tools/observe_diplomacy_live.py --session-file SESSION.json --allow-tag-host prepare --request-id NEW_ID --action knowledge_sharing --actor FRA --target JOL
python tools/observe_diplomacy_live.py --session-file SESSION.json --allow-tag-host status --request-id NEW_ID --compact
python tools/observe_diplomacy_live.py --session-file SESSION.json --allow-tag-host watch --request-id NEW_ID --duration-seconds 30 --compact
python tools/observe_diplomacy_live.py --session-file SESSION.json --allow-tag-host serve --port 8775
python -m bridge.diplomacy_live_observer --check
python -m bridge.knowledge_effect_reader_v2 --check
```

`SESSION.json` contains the exact five-field V31 `identity`. The target must
have matching PID/creation, fixed game PE, manual pause and stable load/reset/
cache guards. By default no research DLL is allowed. `--allow-tag-host` permits
only the unique exact build-7 module and matching loaded PE header. Preparation
requires the native request intent and `publisher.lock` to be absent before and
after capture, and an absent exact pair in both typed indexes and the provider's
global bucket. Existing active/unknown state, old baselines, source changes,
missing TAGs and reservations are refused. This observer does not authorize a
dispatch or change the independent no-repeat policy.

For sharing, only a prepared absent exact pair followed by a new live typed
pair, both allocation-guarded indexes, full provider/recipient handles and the
complete closed original dispatch receipt may produce `effect.status=observed`
and `completion_stage=active_sharing_pair_observed`. Ask reverses the roles:
provider is target. Total counts cannot prove a selected effect. R1 counts stay
supplementary. No baseline, bad source, unstable reads, different receipt or
pre-existing active pair yields `unknown`; absence after dispatch is
`not_observed`, never automatic rejection/retry.

The task has no proven fixed institution ID. Active sharing does not mean
institution adoption completed. AI acceptance, exclusive external-request
causality, atomic world epoch, saved state and cold reload remain unproved.
Known cleanup facts are retained verbatim; transport ownership closure does
not change `known_cleanup_complete=false`.

HTTP reuses the frozen R1 handler's token/Origin/Host checks, write refusal,
bounded JSON and effects route. Only capabilities metadata is replaced by the
new catalog. Token comes from `EU4_OBSERVER_TOKEN`. There is no HTTP preparation
or publication endpoint. CLI exits 0 for selected effect, 3 for recipient
waiting, 2 for unverified/unknown. Annex remains `in_progress`.

The v2 index guard is backed by retained constructor RVA289b50 and insert
RVA28d810 replayed against the fixed PE. Both containers root+2b8/+2d0 have vt
RVA1c3a538, data+8, signed capacity+10/count+14, 16-byte entries. Old R1 reader
did not validate capacity/type and is preserved as a historical version.
The new static extraction adds zero decoded bytes to the prior 28,117/32,768
byte budget. Verification is synthetic/file-only until a separate live receipt.
