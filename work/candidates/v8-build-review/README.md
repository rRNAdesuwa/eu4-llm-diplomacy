# v8 isolated build review

This is a compiled research candidate. It has not been installed or injected,
and no marker, mailbox request or live process operation was performed here.

The 14 native sources are independent copies under `work/native/v8/` plus
`work/native/test-fixture-v8-1375.{h,cpp}`. They differ from v7 only in versioned
include/output/purpose names and the fixed fixture digest. Engine callbacks,
main-thread guards, ownership handling, session invalidation, lease constraints,
durable claims and operation whitelist retain the reviewed v7 behavior.

The event candidate adds one label-only `option = { name = OK }` to each fixed
fixture event. It retains `hidden = yes` and every existing immediate effect.
Its profile is `1375_test_fixture_v2`, SHA256
`68f5c90d63343fd2db64ccd64bd232877409dc43302bf5d40c854c30c84ae918`.
It does not include an unproven truce-removal effect.

New tooling:

- `work/native/lab_protocol_v8_1375.py`
- `work/native/record_lab_v8_build.py`
- `work/native/inject_lab_v8_1375.py`
- `work/native/run_lab_speed_v8_1375.py`
- `tools/request_diplomacy_lab_v8.py`

The protocol remains `EU4LAB/2`, but DLL name, output/session directory, purpose,
native source list and fixture digest are distinct from v7. Build verification
reads the five reviewed candidate copies under
`work/candidates/fixture-v8-1375/mod/llm_diplomacy_test/`. Manifest profile keys
remain `mod/llm_diplomacy_test/...`. Installation verification reads the actual
user mod directory, verifies all five SHA256 values, exact enabled descriptor,
enabled-mod settings and timestamps preceding process creation. Candidate files
alone cannot satisfy installed verification or establish engine-loaded state.

The loader now requires explicit `--test-save`. It retains the two earlier fixed
saves and adds only:

```text
llm_diplomacy_1375_v7_marriage_vassal_20261008a.eu4
F6A56C25FD366522C5F625BAFF086B33F02473EDCD34AAE3E3C2984D30436FB8
```

The `v7` inside that save basename is intentional. SHA/path/PID/creation checks
and serialized single-player FRA premise remain required. This premise is not
independent proof that the live world was loaded from the selected disk file.

Build: `work/native/v8/build-lab-1375.cmd` passed MSVC `/W4 /WX` and produced
`work/runtime/native1375-v8/eu4_pair_lab_v8_1375.dll`:

```text
DLL SHA256      43BFC582EE15E612410B2CC8D8F9B63CA6D47F2135CBD2301578718901E557A4
Manifest SHA256 6ddae83ec9a154cb597c70c118a6500440a2ee92c83e0b78cff9b13f99830240
```

`test-lab-request-1375.cmd` passed 74 checks with no failures and no game calls.
Python bytecode compilation passed for the new tools. The root agent independently
ran `bridge.tests.test_diplomacy_lab_v8`: 15 tests passed. It also confirmed the
native differences are confined to version names and the fixture digest.
`review.json` records that result. `frozen-before.json` records
64 existing source/mod file digests; post-build comparison found no changes.
The native copies were also compared against a narrowly normalized v7 source
(version names and fixture digest only), with no other differences.

The source and installed v7 mods remain unchanged by this work. Adoption,
restart, injected lifecycle checks, option-button verification and effect
readback belong to a separate explicitly reviewed runtime step. Do not mix the
v8 candidate mod with a host that pins the old v7 fixture profile.
