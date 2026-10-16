# Offline v8 fixture candidate

This directory is a candidate only. It has not been installed, loaded or exercised.
No frozen v7 native source, DLL, manifest, source mod or installed mod was changed.

`mod/llm_diplomacy_test/events/llmt_fixture.txt` adds exactly one option to each fixed
event, `llmt.1` and `llmt.2`:

```text
option = { name = OK }
```

The option has no trigger, effect, nested script, AI weighting or country mutation.
All existing event fields, including `hidden = yes` and the entire `immediate`
block, are structurally identical to v7. There is no duplicate modifier/opinion/
alliance effect in the new option. Existing log strings still say `fixture_v7`
because changing effect content is outside this minimal fix.

Installed primary examples support the syntax: `events/ConsortEvents.txt` event
`consort_events.206` has `hidden = yes` at line3425 and an empty `option` at line3481;
`localisation/text_l_english.yml:1882` defines `OK` as `Ok`. No invented
`hide_window` field is used. The console callback can still expose an event window
despite `hidden`; the new button and its closure need a new-process runtime test.

The canonical profile uses the same algorithm as v7: sorted compact JSON with
ASCII keys, `profile_id` and a mapping of the same five source paths to uppercase
SHA256 digests, then SHA256 over its ASCII bytes. Metadata is in
`fixture-profile.json`.

- Profile ID: `1375_test_fixture_v2`
- Profile SHA256: `68f5c90d63343fd2db64ccd64bd232877409dc43302bf5d40c854c30c84ae918`
- Event file SHA256: `D38AFBCF94E38379CFB2162C9A90A32A69D4165CCBAC2B143E2B69F7370F167D`

Run `python work/candidates/fixture-v8-1375/prepare.py --check` from the repository
to reproduce all byte and AST comparisons without writing. The generator pins
the original v7 profile and refuses to silently rebase if it changed. All four
other profile files are exact byte copies. This is not a complete mod package;
the unchanged existing decision, legacy events and localisation remain part of
the original mod and are outside the five-file attestation.

Before adoption, archive the loaded v7 artifact, apply this one changed event
file, update the next build's fixed profile ID/digest and manifest, install before
starting the next process, then re-attest installed bytes. Changing files cannot
repair an already-loaded optionless v7 event definition. Do not mix the new mod
with a host that still pins the v7 profile.

The requested truce-clearing effect is not included: neither `remove_truce` nor
`clear_truce` exists as a literal in this exact-build PE, and no such effect was
found in installed events/common/decisions or the extracted resource scripts.
The PE has `add_truce_with`, `truce_with`, `has_truce` and `truce` tokens; those names
do not prove a supported remove operation or negative-duration semantics.
Normal vassal-cancellation legality must keep rejecting an active truce. Any
future dedicated truce fixture needs separate primary evidence and a new profile.

As before, `fixture_off` removes modifiers and opinions but does not dissolve the
NAV alliance. Resetting the entire test scenario requires restoring its baseline.
