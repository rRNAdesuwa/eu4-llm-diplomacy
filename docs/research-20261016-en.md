# EU4 1.37.5 research checkpoint — 2026-10-16

This source snapshot collects diplomacy research completed since the upstream October 7 checkpoint. Reverse engineering is paused at the user's request. Full action-effect validation and a callable war/peace executor for 1.37.5 remain incomplete. Existing 1.37.4 release metadata is unchanged.

| Area | Current result | Limit |
| --- | --- | --- |
| TAG commands | 120 bindings; the original batch recorded 41 dispatches, 77 refusals and 2 unknowns | Dispatch does not establish a gameplay effect |
| Historical validation | 48 selected effect signals, 44 historical persistence records, 42 repair candidates | All 120 effects are not complete; successful, dispatched, unknown and unclosed actions must not be replayed |
| Direct observation | 15 stable request-effect profiles and scoped current relation/war readers | Original receipts and pre-request baselines are required for causal claims |
| Current peace inbox | v2 empty-target-inbox path independently reviewed from real reads | Nonempty bodies and original request outcomes remain unverified |
| Support-heir task | Bilateral missing-key path independently reviewed from real reads | No positive task body or final heir outcome was verified |
| Offline lookup | Accepted v6: 60 records, 94 fixed JSON sources, 346 references | Research evidence only; callable/native-ready flags remain false |
| Native static work | R86/R87 raw bytes and conditional contracts independently accepted | Final header/storage/ownership semantics remain unknown |

Direct memory observation now separates current state, request replies and selected effects. Save/reload checks are reserved for persistence. The [v8 tool catalog](runtime-capability-map-1375-v8.json) lists seven tools with scoped acceptance; it grants no execution authority or current-process authentication.

R89 passed source review, but its fixed 256-byte target window has not been acquired or authorized for actual acquisition. Lookup v7 is only a plan for 61 records and 95 sources under the existing 96-source ceiling; it has not been built or run.

See the [Chinese checkpoint and evidence links](research-20261016.md), [machine-readable summary](research-20261016/summary.json), and [source provenance](research-20261016/source-provenance.json). All 94 direct v6 evidence JSON files retain their original paths and hashes. Selected original contracts preserve their historical pending labels; later independent reviews and root acceptance files provide the updated status.

This publication includes original source, build tools, test source, lookup data and selected review results. Credentials, local configuration, saves, game files, third-party engines, full process captures, large analysis and duplicate build trees stay local. Documentation paths use configuration placeholders. Immutable historical JSON may record the original game installation path as evidence; it is not runtime configuration. Sealed manifests describe the original local evidence graph; missing public dependencies must fail closed. Do not regenerate pins or reuse consumed one-time grants to bypass that boundary.

Publication checks only parse standalone Python source and JSON, compare file hashes and inspect the exported tree. Include fragments are not standalone programs. No old tests, query engine, game read, dispatch, save or reload was repeated. Uploading this checkpoint does not resume research.
