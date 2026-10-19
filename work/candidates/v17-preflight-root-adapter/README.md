# Formal-root import adapter for the fixed v17 preflight

Frozen reviewer `v17-acceptance-experiment-review/reviewer.py` inserts the candidate MIRROR first in sys.path. Its explicit-root build check succeeds, but `life.verify_phase` calls `lab.verify_build(output=...)` with the lab module's default root. In a clean interpreter that module came from the mirror; it searches for the acceptance static report below the mirror and fails. The older synthetic fixtures mocked verify_build and did not exercise this path. The failed real command is preserved by root; no success summary is manufactured.

This adapter checks the sealed builder/source inventory and exact formal build manifest, then preloads six formal protocol/phase modules with exact disk SHA and __file__ origin checks. After loading the unchanged frozen reviewer it removes only that reviewer's MIRROR entry from the search path, keeping later imports at the formal root. It does not patch any proof function, module ROOT/default parameter, manifest, source file or case. Formal modules are byte-identical to their reviewed mirror copies. A previously cached mirror module is rejected instead of replaced. Real `verify_build(output=...)` is exercised without a mock.

The preflight command accepts three explicit canonical repository-relative paths. PID63500/creation/world/date/thread/build/export/prefix remain fixed by the sealed builder. Case/scope/output must be distinct; scope must bind the case and output paths, output must be absent, and the existing frozen reviewer performs its entire 20/1/72/72 proof and exclusive output write. Case/scope and all reviewed dependencies are rehashed. No actual case is read during author tests.

```powershell
python -B work/candidates/v17-preflight-root-adapter/adapter.py preflight --case <same-existing-case.json> --scope <same-existing-scope.json> --output <exact-scope-summary-path.json>
```

For an independent fresh process import check only:

```powershell
python -B work/candidates/v17-preflight-root-adapter/adapter.py check-imports --output <new-import-report.json>
python -B -m unittest discover -s work/candidates/v17-preflight-root-adapter -p test_adapter.py -v
```

Six offline tests reproduce the original mirror failure, pass the real formal build from the actual phase function before deliberately failing on a nonexistent diagnostic, reject a pre-cached mirror module, compare all six formal/mirror byte copies, and reject existing/aliased output paths. The first test command failed to import a multiline subprocess-code string in the test harness; its exact source/failure is retained in history. Only that test literal was corrected. No DLL, game, request, actual prefix or actual case was touched. This adapter does not imply a successful actual preflight, diplomacy effect, whole-world stability or production capability.
