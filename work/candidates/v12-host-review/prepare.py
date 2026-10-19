"""Copy the pinned frozen v11 host profile to an isolated v12 draft.

No native sources, builds, process access or requests. All changed destinations
are checked before the first write; built/used v12 profiles cannot be revised.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HOST_FILES = (
    "work/native/lab_protocol_v11_1375.py",
    "work/native/inject_lab_v11_1375.py",
    "work/native/run_lab_speed_v11_1375.py",
    "work/native/record_lab_v11_build.py",
    "tools/request_diplomacy_lab_v11.py",
    "tools/verify_diplomacy_lifecycle_v11.py",
    "tools/verify_diplomacy_preview_v11.py",
    "tools/verify_diplomacy_command_v11.py",
    "bridge/diplomacy_lab_http_v11.py",
    "tools/serve_diplomacy_lab_v11.py",
)
FIXTURE_FILES = tuple("work/candidates/fixture-v11-1375/mod/llm_diplomacy_test/" + name for name in (
    "descriptor.mod", "common/defines/zz_llm_diplomacy_test.lua", "events/llmt_fixture.txt",
    "common/event_modifiers/llm_diplomacy_test.txt", "common/opinion_modifiers/llmt_fixture.txt"))
NATIVE_FILES = tuple("work/native/v11/" + name for name in (
    "research-lab-1375.cpp", "research-lab-bootstrap-1375.inc", "research-frame-v6-1375.asm",
    "pair-probe-v6-1375.cpp", "pair-preview-v6-1375.cpp", "pair-command-v6-1375.cpp",
    "pair-engine-1375.h", "pair-engine-1375.cpp", "test-controls-1375.h", "test-controls-1375.cpp",
    "lab-request-1375.h", "build-lab-1375.cmd")) + (
    "work/native/test-fixture-v11-1375.h", "work/native/test-fixture-v11-1375.cpp")
FROZEN_FILES = HOST_FILES + FIXTURE_FILES + NATIVE_FILES + (
    "work/runtime/native1375-v11/build.json", "work/runtime/native1375-v11/eu4_pair_lab_v11_1375.dll")


def bounded(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Candidate input exceeds 1 MiB: " + str(path))
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def protected(root):
    output = Path(root) / "work/runtime/native1375-v12"
    return ((output / "build.json").exists() or (output / "eu4_pair_lab_v12_1375.dll").exists()
            or next(output.glob("session-*"), None) is not None)


def extend_lifecycle_contract(text):
    anchor = '            self.check(fixed_extra_valid(event, action), "Fixed gift/trade/insult evidence differs", line)'
    if text.count(anchor) != 1:
        raise ValueError("Missing or ambiguous v12 lifecycle diagnostic anchor")
    checks = '''
            expected_state = 2 if action == "form_coalition" else 0
            for stage in ("factory", "clone", "retained_original"):
                self.check(event.get(stage + "_contract_checked") is True,
                           f"{action}: {stage} contract was not fully checked", line)
                self.check(type(event.get(stage + "_state")) is int and event[stage + "_state"] == expected_state,
                           f"{action}: {stage} default state differs", line)
                self.check(type(event.get(stage + "_contract_failure_mask")) is int and event[stage + "_contract_failure_mask"] == 0,
                           f"{action}: {stage} contract failure mask is missing or nonzero", line)'''
    return text.replace(anchor, anchor + checks)


def generate(check=False, *, root=ROOT, pins_path=None):
    root = Path(root)
    pins_path = Path(pins_path) if pins_path is not None else HERE / "frozen-templates.json"
    pins = json.loads(bounded(pins_path))
    if set(pins) != {"purpose", "sha256"} or pins["purpose"] != "v12_frozen_v11_templates" or set(pins["sha256"]) != set(FROZEN_FILES):
        raise ValueError("Frozen v11 snapshot has a different exact file set")
    frozen = {name: bounded(root / name) for name in FROZEN_FILES}
    if any(sha(raw) != pins["sha256"][name] for name, raw in frozen.items()):
        raise ValueError("A frozen v11 source, fixture, DLL or manifest changed")
    candidates = {}
    for name in HOST_FILES:
        text = frozen[name].decode("utf-8").replace("v11", "v12").replace("V11", "V12").replace("8768", "8769")
        if name == "tools/verify_diplomacy_lifecycle_v11.py":
            text = extend_lifecycle_contract(text)
        candidates[name.replace("v11", "v12")] = text.encode("utf-8")
    for name in FIXTURE_FILES:
        candidates[name.replace("fixture-v11", "fixture-v12")] = frozen[name]
    changed = {name: raw for name, raw in candidates.items()
               if not (root / name).exists() or bounded(root / name) != raw}
    if changed and check:
        raise ValueError("Generated v12 file differs: " + next(iter(changed)))
    if changed and protected(root):
        raise ValueError("Refuse changing a built or used v12 host profile")
    for name, raw in changed.items():
        if protected(root):
            raise ValueError("V12 build/session appeared; stop candidate generation")
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    result = {"purpose": "isolated_v12_host_candidate", "native_sources_generated": False,
              "game_process_accessed": False, "native_invoked": False, "build_performed": False,
              "action_count": 36, "family_count": 20, "phase_counts": {"lifecycle": 20, "preview": 72, "command": 72},
              "protocol": "EU4LAB/2", "fixture_profile_sha256": "f3507bb78f665443c5dad20efee0aef2dd86a8b6741130ee03e883b2ecc1a507",
              "lifecycle_contract_diagnostics": {"stages": ["factory", "clone", "retained_original"],
                  "checked_required": True, "form_coalition_default_state": 2, "other_default_state": 0, "success_failure_mask": 0},
              "expected_native_sources": [name.replace("v11", "v12") for name in NATIVE_FILES],
              "frozen_v11_sha256": pins["sha256"],
              "generated_sha256": {name: sha(raw) for name, raw in candidates.items()}}
    report = root / "work/candidates/v12-host-review/candidate.json"
    raw = (json.dumps(result, indent=2) + "\n").encode("utf-8")
    if not check and (not report.exists() or bounded(report) != raw):
        if protected(root):
            raise ValueError("Refuse changing candidate report after a v12 build/session")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_bytes(raw)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = generate(args.check)
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ("frozen_v11_sha256", "generated_sha256", "expected_native_sources")}))
