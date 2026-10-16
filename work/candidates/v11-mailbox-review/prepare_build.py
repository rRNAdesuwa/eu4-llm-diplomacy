"""Deterministically merge reviewed v11 mailbox/action candidates; no game access or build."""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD_MANIFEST = ROOT / "work/runtime/native1375-v10/build.json"
OLD_MANIFEST_SHA = "ae68ffe9b59d6c6fcd4a464eea98d108bf5b700f77459773f1655bdcea7c9d46"
OLD_DLL_SHA = "A2345AFE7C3C8CAA8A8EBADDC29B068A90FF35E3E83AF07212A1E18C40CBC9B7"
ACTION_CANDIDATE = HERE.parent / "v11-action-extension-review"
ACTION_REVIEW_SHA = "5a367293b5b71e327b0496f700a43c2db5f5922231aee486b8c5f3a1e871eee7"
ACTION_FILES = (
    "pair-engine-1375.h", "pair-engine-1375.cpp", "pair-probe-v6-1375.cpp",
    "pair-preview-v6-1375.cpp", "pair-command-v6-1375.cpp",
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Ambiguous or missing source anchor: " + old[:100])
    return text.replace(old, new)


def reviewed_actions():
    raw = (ACTION_CANDIDATE / "review.json").read_bytes()
    if digest(raw) != ACTION_REVIEW_SHA:
        raise ValueError("Reviewed action candidate differs")
    review = json.loads(raw)
    for name, expected in review["generated_hashes"].items():
        if digest((ACTION_CANDIDATE / name).read_bytes()) != expected:
            raise ValueError("Reviewed action artifact differs: " + name)
    matrix = json.loads((ACTION_CANDIDATE / "mode-matrix.json").read_bytes())
    expected_counts = {"families": 20, "ids": 36, "lifecycle_count": 20,
                       "preview_count": 72, "command_count": 72}
    if any(type(matrix.get(key)) is not int or matrix[key] != value for key, value in expected_counts.items()):
        raise ValueError("Reviewed action matrix counts differ")
    expected_cases = {(target, family, value) for target in ("ENG", "POR") for family in range(20)
                      for value in ((True,) if family in (12, 13, 18, 19) else (True, False))}
    cases = [(item["target"], item["family_index"], item["value"]) for item in matrix["cases"]]
    if len(cases) != 72 or len(set(cases)) != 72 or set(cases) != expected_cases:
        raise ValueError("Reviewed action matrix membership differs")
    if review["runtime_verified"] or review["execution_verified"] or review["process_access"]:
        raise ValueError("Action candidate must remain static/offline")
    return review, {"work/native/v11/" + name: (ACTION_CANDIDATE / "generated" / name).read_bytes()
                    for name in ACTION_FILES}


def generate(check=False):
    before_raw = OLD_MANIFEST.read_bytes()
    if digest(before_raw) != OLD_MANIFEST_SHA:
        raise ValueError("Frozen v10 manifest differs")
    old = json.loads(before_raw)
    if digest((OLD_MANIFEST.parent / "eu4_pair_lab_v10_1375.dll").read_bytes()).upper() != OLD_DLL_SHA:
        raise ValueError("Frozen v10 DLL differs")
    if len(old["source_sha256"]) != 14:
        raise ValueError("Frozen source count differs")
    chunk = (HERE / "consume-input.inc").read_text(encoding="utf-8")
    generated, diffs = {}, []
    for name, expected in old["source_sha256"].items():
        raw = (ROOT / name).read_bytes()
        if digest(raw).upper() != expected:
            raise ValueError("Frozen source differs: " + name)
        destination = name.replace("v10", "v11")
        original = raw.decode("utf-8")
        text = original.replace("v10", "v11")
        if name.endswith("/research-lab-1375.cpp"):
            begin = text.index("// Request remains exclusively open through parsing and durable claim creation.")
            end = text.index("\nstatic void run_phase(", begin)
            text = text[:begin] + chunk + "\n" + text[end:]
            text = replace_one(text, "if (marker_absent(paths[phase])) return;", "if (!input_waits[phase].active && marker_absent(paths[phase])) return;")
            text = replace_one(text, "consume_input(paths[phase], claim, tokens[phase], strlen(tokens[phase]), raw, length);",
                "consume_input(paths[phase], claim, tokens[phase], strlen(tokens[phase]), raw, length,\n        input_waits[phase], phase == 0 ? \"lifecycle\" : (phase == 1 ? \"preview\" : \"command\"), 0);")
            text = replace_one(text, "consume_input(path, claim, nullptr, 0, raw, length);",
                "consume_input(path, claim, nullptr, 0, raw, length, input_waits[3], \"request\", last_sequence + 1);")
            text = replace_one(text, "if (state == InputState::absent) return;", "if (state == InputState::absent || state == InputState::deferred) return;")
            text = text.replace("Restricted, session-bound v6 research host", "Restricted, session-bound v11 research host")
            text = text.replace("canonical ten-ID/speed mailbox", "canonical twenty-four-ID/speed mailbox")
        result = text.encode("utf-8")
        generated[destination] = result
        if result != raw:
            diffs.extend(difflib.unified_diff(original.splitlines(True), text.splitlines(True), fromfile=name, tofile=destination))
    action_review, action_sources = reviewed_actions()
    action_diffs = []
    mailbox_native_sha256 = {name: digest(raw) for name, raw in generated.items()}
    for name, raw in action_sources.items():
        action_diffs.extend(difflib.unified_diff(generated[name].decode("utf-8").splitlines(True),
            raw.decode("utf-8").splitlines(True), fromfile=name + ".mailbox-only", tofile=name))
        generated[name] = raw
    # v11 Python protocol is owned by root. Its recorder uses that version only.
    recorder = (ROOT / "work/native/record_lab_v10_build.py").read_text(encoding="utf-8").replace("v10", "v11")
    generated["work/native/record_lab_v11_build.py"] = recorder.encode()
    for name, expected in old["fixture_profile"]["source_sha256"].items():
        suffix = name
        raw = (ROOT / "work/candidates/fixture-v10-1375" / suffix).read_bytes()
        if digest(raw).upper() != expected:
            raise ValueError("Frozen fixture differs: " + suffix)
        generated["work/candidates/fixture-v11-1375/" + suffix] = raw
    output = ROOT / "work/runtime/native1375-v11"
    if output.exists() and any(output.glob("session-*")):
        raise ValueError("Never rewrite a used v11 candidate")
    for name, raw in generated.items():
        path = ROOT / name
        if path.exists() and path.read_bytes() == raw:
            continue
        if check:
            raise ValueError("Generated candidate differs: " + name)
        if (output / "eu4_pair_lab_v11_1375.dll").exists() and name.startswith("work/native/"):
            raise ValueError("Refuse rewriting a built v11 native candidate")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    result = {"purpose": "v11_reviewed_mailbox_and_action_candidate", "native_source_count": 14,
              "research_action_count": 36, "native_family_count": 20,
              "phase_counts": {"lifecycle": 20, "preview": 72, "command": 72},
              "action_review_sha256": ACTION_REVIEW_SHA,
              "action_mode_matrix_sha256": action_review["generated_hashes"]["mode-matrix.json"],
              "action_overlay_source_count": len(action_sources),
              "mailbox_only_native_sha256": mailbox_native_sha256,
              "action_overlay_sha256": {name: digest(raw) for name, raw in action_sources.items()},
              "action_merge_diff_sha256": digest("".join(action_diffs).encode("utf-8")),
              "fixture_profile_id": "1375_test_fixture_v3",
              "fixture_profile_sha256": "f3507bb78f665443c5dad20efee0aef2dd86a8b6741130ee03e883b2ecc1a507",
              "input_wait_limit_ms": 250, "input_wait_max_attempts": 16, "native_invoked": False,
              "v10_manifest_sha256": OLD_MANIFEST_SHA, "v10_dll_sha256": OLD_DLL_SHA,
              "generated_sha256": {n: digest(v) for n, v in generated.items()}}
    if not check:
        (HERE / "native-mailbox.diff").write_text("".join(diffs), encoding="utf-8", newline="\n")
        (HERE / "native-action-merge.diff").write_text("".join(action_diffs), encoding="utf-8", newline="\n")
        (HERE / "candidate.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = generate(args.check)
    print(json.dumps({k: v for k, v in result.items() if k != "generated_sha256"}))
