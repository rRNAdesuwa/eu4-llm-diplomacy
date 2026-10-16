# Isolated v9 build review

The v9 research candidate is built, with no installation or game-process action by
this preparation task. It keeps `EU4LAB/2`, the same ten pair IDs, fixed TAG set and
native host/engine/ownership behavior. Version paths/names and the fixed fixture
digest changed in the 14 native source files. The sole additional native delta is
the fixture core's read-only fixed NAV baseline guard described below.

- DLL: `work/runtime/native1375-v9/eu4_pair_lab_v9_1375.dll`.
- DLL SHA256: `6C2D8420525E7E3C21F2EB20DFEA9C991B86AF8AC82211F1557F89436FDA896A`.
- Manifest: `work/runtime/native1375-v9/build.json`.
- Manifest SHA256: `d4406614fdcad03d21350656f23d9a6ae90db12e719f16cad7c6b768a4a5815f`.
- Fixture: `1375_test_fixture_v3`, SHA256
  `f3507bb78f665443c5dad20efee0aef2dd86a8b6741130ee03e883b2ecc1a507`.

`prepare_build.py --check` verifies the exact expected v8→v9 transformation and all
52 recorded old source/build/mod hashes. Native/build/mod hashes remain unchanged.
One explicitly authorized offline v8 CLI discovery-source line and CRLF formatting
are recorded separately; reversing exactly that edit matches its original hash.
The original snapshot is not rewritten. The pinned v8 DLL remains
`43BFC582EE15E612410B2CC8D8F9B63CA6D47F2135CBD2301578718901E557A4`.

Validation completed:

- MSVC `/O2 /W4 /WX /MT` compile and link.
- Native request parser: 74 checks, 0 failures, no game calls.
- Fixed NAV baseline guard: 23 synthetic-memory checks, 0 failures.
- `bridge.tests.test_diplomacy_lab_v9`: 16 offline tests passed.
- Seven new Python tools compile; candidate, source transformation and both v8/v9
  build verifiers pass.

Python tools have separate v9 names/output/session purpose/candidate namespace.
The candidate source hashes read only `work/candidates/fixture-v9-1375`; installed
verification still checks the real user mod files, enabled descriptor and timestamps
before process creation. Loader `--test-save` remains mandatory and allows exactly:

1. `llm_diplomacy_1375_baseline.eu4` —
   `276F88AFECDBC1F1A24ED6314845351B1BA5640715B7ED1FD14513B3376664FB`.
2. `llm_diplomacy_1375_after_improve.eu4` —
   `7BFABE371E68AE502B806F9B80375FC8A4DAC638AD116D2506966FEF69633C5F`.

The positive NAV-vassal save is rejected before file hashing or process access.
No new command, event ID, console text, arbitrary pointer or native address is exposed.
`fixture_off` does not dissolve the resulting vassal. These build checks do not prove
live single-player origin, loaded save identity, effect application or absence of truce.
Those existing research limits remain unchanged.

## Fixed fixture-on baseline guard

`fixture-baseline.diff` is the complete additional native delta after the original
version/profile transform. `fixture-baseline-patch.json` is pinned by the source
preparer, and `trace_baseline_guard.py --check` replays 591 bytes of bounded disk
disassembly into `baseline-guard-evidence.json`. No additional native function is called.

Only `fixture_on` requires the fixed full NAV handle, invalid/absent overlord, no
active truce in either direction (record+0x45, mask **0x01**, zero-based bit 0), and
no matching alliance index entry (root+0x80 pointer/+0x8c DWORD count, stride 16).
The count is bounded to 4096; malformed pointers, handles, slots or index objects
reject. It runs before the begin record and again after fresh-world and host guard
checks immediately before the event. Both passes must satisfy the predicate and
agree on NAV pointer/overlord and bilateral record/root/index pointers, counts and
full truce flag bytes. Unrelated indexed objects/order are not compared.

A normal baseline rejection returns before native invocation with `wrong_world`
(first pass) or `guard_rejected` (second pass) and no unknown-state freeze. A memory
read exception follows the existing SEH freeze/no-retry path. `fixture_off` does
not impose this baseline, since its purpose includes removing buffs after setup.

The parent still checks that the intended loaded world has an existing independent
NAV and records state after fixture application. This guard does not prove a save
filename, strict single-player origin, effect application or all possible truce paths.

Parent independently reviewed the final baseline diff and repeated the 23 guard,
16 Python, bounded static and fixture checks successfully before installation.
This preparation record does not certify later runtime operations.
