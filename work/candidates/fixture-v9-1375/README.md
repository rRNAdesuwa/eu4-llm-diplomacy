# v9 fixture candidate — offline preparation

This directory contains five independently attested mod files copied from the frozen
v8 candidate. The only script AST change is `llmt.1` immediate
`create_alliance = NAV` → `vassalize = NAV`. The pool/acceptance modifiers, reciprocal
NAV/FOI opinions, hidden flag, and one label-only `OK` option per event are unchanged.
The old `fixture_v7` log literal is intentionally unchanged so the one-effect claim
remains exact. Version identity comes from the attested profile, not that log label.

- Profile ID: `1375_test_fixture_v3`.
- Canonical profile SHA256: `f3507bb78f665443c5dad20efee0aef2dd86a8b6741130ee03e883b2ecc1a507`.
- Event SHA256: `86B8B187E446E06277B1602022B34BBB509677BE6F63FFB48E135243F1C70DA5`.
- `python work/candidates/fixture-v9-1375/prepare.py --check` reproduces all five files,
  the canonical profile and the AST-only-change proof without writing them.

Use only a separately verified disposable original baseline or `after_improve` save
where FRA is the current player, NAV exists and is independent, and FRA/NAV have no
alliance and no bilateral truce. Do not run this setup on the positive marriage/vassal
save. An existing alliance would be removed during vassalization and can add truce;
the static path is recorded in `docs/native-vassal-effects-1375.md` and its JSON report.

The native console callback is a fixed test-event invocation, not evidence that the
fixture effect applied. After running it in a future independently reviewed session,
observe both relation directions, `vassal` definition, full handles, dependency start,
and both truce values before testing native cancellation. A filename checksum alone
does not prove which world is loaded.

`llmt.2` removes modifiers and opinions. It does not undo the vassal relationship or
promise an immediate shrink of the diplomat object pool. Restore an audited baseline
to reset relationship setup. No option repeats an effect.

This preparation does not install files, start/stop the game, inject a DLL, publish a
request, or modify any frozen v6/v7/v8 source/profile. Runtime verification remains
false here.
