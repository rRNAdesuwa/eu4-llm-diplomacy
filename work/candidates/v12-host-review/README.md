# v12 isolated host draft

`prepare.py` copies the frozen v11 Python host into the v12 namespace. It does not copy native sources, compile a DLL, load a process, install a fixture or create a request. The separate native contract review owns any factory/clone correction.

Frozen inputs are pinned in `frozen-templates.json`: eight host Python files (protocol, loader, watchdog, recorder, request CLI and three validators), two HTTP files, five fixture definitions, fourteen native sources, the v11 DLL and manifest. Generation checks every pin before any write. Fixture definitions are copied byte for byte; profile remains `1375_test_fixture_v3`, SHA `f3507bb78f665443c5dad20efee0aef2dd86a8b6741130ee03e883b2ecc1a507`.

New identity is `restricted_pair_lab_1375_v12`, `work/runtime/native1375-v12`, `eu4_pair_lab_v12_1375.dll`, `EU4LAB/2`. `SOURCES` contains exactly fourteen v12 paths. Request TAGs, the 36 action IDs, 20/72/72 preflight matrix, all five fixed scalar audit fields, bounded unclaimed-input diagnostics, installed fixture guards, publication semantics and speed supervision are retained.

HTTP is separately bound to `/research/v12`, localhost port `8769`, using `tools/serve_diplomacy_lab_v12.py`. It has only capabilities, status, explicit sequence status and pair publication. No fixture/speed route exists; fixed gift 25.000, trade fraction 500, insult -1 and subsidy 1.000 per month for ten years cannot be supplied or overridden by clients. Discovery remains historical; neither an import nor a candidate build proves a current game session is ready.

Run `python work/candidates/v12-host-review/prepare.py --check` for a read-only exact comparison. If any destination differs, normal generation refuses to change it once a v12 `build.json`, DLL or `session-*` exists. It checks all differences before writing the first file; unchanged files are not rewritten. The generator never revises the frozen v11 snapshot. A missing native source/DLL/manifest remains not ready.

The v12 lifecycle validator requires three diagnostic groups: `factory`, `clone`, and `retained_original`. Each must have `*_contract_checked=true`, an integer `*_state` of 2 for `form_coalition` or 0 for other families, and integer `*_contract_failure_mask=0`. Missing/null fields, booleans standing in for integers and any failure mask are rejected. All existing factory/clone validity, destruction and exception checks remain. This concerns factory defaults and cloned/retained originals. A separate bounded static report now closes the normal AI construction and owned-queue path: helper `0x12b860` constructs coalition state `+0x34=2`, passes it through `0x129b60` and wrapper `0x4e9930`, and the clone retains that state before ownership moves into `owner+0xa68`. Cancellation changes only `value+0x38=false`. This supports the v12 candidate using state 2 for exact token `0x2de0` during initialization and checks, while the other nineteen families retain 0. It does not identify the human GUI click callback or prove final dispatch, effects, or DLL runtime acceptance. The source report is `work/reports/native-coalition-queue-1375.json`, SHA256 `b36c788c3eeb589abaa208df83cb3f97bf3697023188149588b41bb60dde5b65`. See [the bounded test plan](../../../docs/native-v12-extension-test-plan.md) for conditional effect checks.

The frozen v11 session PID40176 failed its lifecycle suite at `form_coalition` after fourteen completed families, before preview, command, fixture or diplomatic requests. Its summary is `work/runtime/native1375-v11/failed-lifecycle-summary-40176.json`. That failure is why v12 is isolated; neither the fourteen prior lifecycle records nor this candidate's 39 offline tests grant runtime readiness or a production capability.

Offline checks:

```text
python -m unittest bridge.tests.test_diplomacy_lab_v12 bridge.tests.test_diplomacy_lab_http_v12 bridge.tests.test_v12_host_candidate
```

These tests use synthetic temporary files. They do not open a process, create a listener or write a game request.

Subsequent historical result: PID17676 / creation `01dd56989186135c` completed the actual 20/72/72 no-send phases. The immutable `work/runtime/native1375-v12/preflight-only-17676` mirror and summary were independently reviewed, with zero pair/fixture requests. Shared discovery records this as `historical_preflight_passed` separately from the unchanged candidate/runtime-ready fields; it does not infer later effects or current permission. See [versioned research evidence](../../../docs/diplomacy-research-capabilities.md#v12-固定无发送预检). No frozen host/native file is changed by this documentation or discovery update.
