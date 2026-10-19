"""Build an offline v8 fixture candidate; never installs or contacts the game."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from tools.build_diplomacy_catalog import parse_script, scalar

FILES = tuple("mod/llm_diplomacy_test/" + name for name in (
    "descriptor.mod", "common/defines/zz_llm_diplomacy_test.lua", "events/llmt_fixture.txt",
    "common/event_modifiers/llm_diplomacy_test.txt", "common/opinion_modifiers/llmt_fixture.txt"))
EVENTS = FILES[2]
OLD_PROFILE = "3a7f514eadacee07494fef32e8ebca62d1020c6936c9877490ddba0bd59223c1"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def shape(node):
    return [node.key, node.value, [shape(child) for child in node.children]]


def profile(profile_id, files):
    return {"profile_id": profile_id, "source_sha256": {key: sha(value).upper() for key, value in files.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare existing candidate without writing")
    args = parser.parse_args()
    before = {key: (ROOT / key).read_bytes() for key in FILES}
    old_profile = profile("1375_test_fixture_v1", before)
    if sha(canonical(old_profile).encode("ascii")) != OLD_PROFILE:
        raise ValueError("Source mod differs from reviewed frozen v7 profile; do not silently rebase")
    text = before[EVENTS].decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    nodes = parse_script(text)
    events = [node for node in nodes if node.key == "country_event"]
    if [scalar(node, "id") for node in events] != ["llmt.1", "llmt.2"]:
        raise ValueError("Unexpected fixed event IDs")
    lines = text.splitlines(keepends=True)
    option = ["    # Closing this console-triggered window must have no gameplay effect." + newline,
              "    option = { name = OK }" + newline]
    for event in reversed(events):
        if scalar(event, "hidden") != "yes" or any(child.key == "option" for child in event.children):
            raise ValueError("Source event must remain hidden and have no existing option")
        lines[event.end_line - 1:event.end_line - 1] = option
    after = dict(before)
    after[EVENTS] = "".join(lines).encode("utf-8")
    new_nodes = parse_script(after[EVENTS].decode("utf-8"))
    new_events = [node for node in new_nodes if node.key == "country_event"]
    event_checks = []
    for old, new in zip(events, new_events, strict=True):
        options = [child for child in new.children if child.key == "option"]
        if len(options) != 1 or [shape(child) for child in options[0].children] != [["name", "OK", []]]:
            raise ValueError("Closing option must contain exactly name=OK and no effect or trigger")
        without_option = [shape(child) for child in new.children if child.key != "option"]
        if without_option != [shape(child) for child in old.children]:
            raise ValueError("Existing event fields/effects changed")
        immediate = [shape(child) for child in old.children if child.key == "immediate"]
        event_checks.append({"id": scalar(new, "id"), "hidden": "yes", "option_name": "OK",
                             "option_effect_count": 0, "option_count": 1, "original_fields_unchanged": True,
                             "immediate_ast_sha256": sha(canonical(immediate).encode("ascii"))})
    new_profile = profile("1375_test_fixture_v2", after)
    report = {
        "purpose": "offline_candidate_only", "installed": False, "runtime_verified": False,
        "old_profile": old_profile, "old_profile_sha256": OLD_PROFILE,
        "fixture_profile": new_profile, "fixture_profile_sha256": sha(canonical(new_profile).encode("ascii")),
        "changed_files": [EVENTS], "event_checks": event_checks,
        "source_effects_repeated_in_options": False,
        "scope": "Five attested v7 files copied; only llmt_fixture.txt adds one label-only option per event",
        "limits": ["Does not close an already-loaded v7 event definition",
                   "Requires next process to load the candidate and a new host/profile attestation",
                   "Native console callback may still show hidden event UI; button presence needs runtime verification",
                   "fixture_off still does not remove the NAV alliance; baseline restore remains separate"],
        "local_examples": ["events/ConsortEvents.txt:3425 hidden=yes; same event has empty option at3481",
                           "localisation/text_l_english.yml:1882 defines OK=Ok"]}
    outputs = {HERE / key: value for key, value in after.items()}
    outputs[HERE / "fixture-profile.json"] = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    for path, raw in outputs.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != raw:
                raise ValueError(f"Candidate mismatch: {path.relative_to(HERE)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    if before != {key: (ROOT / key).read_bytes() for key in FILES}:
        raise ValueError("Source files changed during candidate generation")
    print(canonical({"fixture_profile_sha256": report["fixture_profile_sha256"],
                     "event_file_sha256": sha(after[EVENTS]).upper(), "checked": args.check,
                     "original_source_files_unchanged": True, "runtime_verified": False}))


if __name__ == "__main__":
    main()
