"""Check an identity-only derivation of the frozen v14 offline reviewer."""
import argparse
import ast
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
BASE = "work/candidates/v14-preflight-review"
BASE_SHA = "499cde0e62012fb2dd97a5d3295e3a1db94d7221602c8bc002a500024dc3878c"
HEALTH = "work/runtime/native1375-v14/directional-health-after-command-18356.json"
HEALTH_SHA = "56760ffea16f6d4d732993187407b2e404b7a9c9a12847ccb4abda7b269cb18b"
EXPECTED = dict(pid=18356, creation="01dd56aa6f724ea8", world_cookie="0x221c8dac040",
                raw_date=56456976, window_thread=47264)
FILES = ("reviewer.py", "test_reviewer.py", "prepare.py", "verify_tests.py", "README.md",
         "runtime-pins.json", "binding-provenance.json")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Input budget exceeded")
    return raw


def render():
    baseline_raw = bounded(ROOT / BASE / "review.json")
    if sha(baseline_raw) != BASE_SHA:
        raise ValueError("Frozen baseline review changed")
    baseline = json.loads(baseline_raw)
    inputs = dict(baseline["input_pins"])
    inputs[BASE + "/review.json"] = BASE_SHA
    inputs[BASE + "/candidate.diff"] = baseline["diff_sha256"]
    inputs.update({BASE + "/" + row["path"]: row["sha256"] for row in baseline["sources"]})
    inputs[HEALTH] = HEALTH_SHA
    for name, digest in inputs.items():
        if sha(bounded(ROOT / name)) != digest:
            raise ValueError("Pinned input changed: " + name)
    health = json.loads(bounded(ROOT / HEALTH))["report"]
    frame = health["latest_frame"]
    identity = {key: frame[{"creation": "process_creation_filetime", "window_thread": "thread"}.get(key, key)]
                for key in EXPECTED}
    if json.dumps(identity, sort_keys=True) != json.dumps(EXPECTED, sort_keys=True):
        raise ValueError("Saved health identity differs")
    if type(health["last_sequence"]) is not int or health["last_sequence"] != 0:
        raise ValueError("Saved health was not the pre-request status")
    old = bounded(ROOT / BASE / "reviewer.py")
    before = (b'EXPECTED_SESSION = {"pid": 29492, "creation": "01dd56a7d38f2649", "world_cookie": "0x2f48cc3f030",\n'
              b'                    "raw_date": 56456976, "window_thread": 57620}')
    after = (b'EXPECTED_SESSION = {"pid": 18356, "creation": "01dd56aa6f724ea8", "world_cookie": "0x221c8dac040",\n'
             b'                    "raw_date": 56456976, "window_thread": 47264}')
    current = bounded(HERE / "reviewer.py")
    if old.count(before) != 1 or current != old.replace(before, after):
        raise ValueError("Reviewer has a delta other than the fixed identity")
    if bounded(HERE / "runtime-pins.json") != bounded(ROOT / BASE / "runtime-pins.json"):
        raise ValueError("Frozen runtime pins changed")
    spec = importlib.util.spec_from_file_location("directional_preflight_candidate", HERE / "reviewer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.fixed_build()
    if module.EXPECTED_SESSION != EXPECTED:
        raise ValueError("Reviewer identity mismatch")
    sources = []
    for name in FILES:
        raw = bounded(HERE / name)
        if name.endswith(".py"):
            ast.parse(raw)
        sources.append(dict(path=name, bytes=len(raw), sha256=sha(raw)))
    diff = b""
    for name in ("reviewer.py", "test_reviewer.py", "verify_tests.py", "README.md"):
        diff += "".join(difflib.unified_diff(bounded(ROOT / BASE / name).decode().splitlines(True),
            bounded(HERE / name).decode().splitlines(True), fromfile=BASE + "/" + name,
            tofile="work/candidates/v14-directional-preflight-review/" + name)).encode()
    record = dict(schema_version=1, purpose="v14_directional_four_stage_offline_preflight_review_candidate",
        base_review_sha256=BASE_SHA, sources=sources, input_pins=inputs, input_count=len(inputs),
        source_counts=dict(native=20, host=11, support=8), expected_session=EXPECTED,
        phase_case_counts=dict(lifecycle=20, owned_peace=1, preview=72, command=72),
        diff_sha256=sha(diff), reviewer_identity_only_delta=True, original_frozen_candidate_unchanged=True,
        actual_game_evidence_collected=False, actual_case_run=False, active_complete_log_read=False,
        game_accessed=False, native_build_performed=False, production_execution_verified=False,
        owned_peace_scope="default_owned_object_lifecycle_only")
    return {"candidate.diff": diff, "review.json": (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    outputs = render()
    for name, raw in outputs.items():
        path = HERE / name
        if args.check:
            if bounded(path) != raw:
                raise ValueError("Candidate needs regeneration: " + name)
        else:
            with path.open("xb") as stream:
                stream.write(raw)
    print(json.dumps(dict(check=args.check, review_sha256=sha(outputs["review.json"]),
                          game_accessed=False, built=False)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
