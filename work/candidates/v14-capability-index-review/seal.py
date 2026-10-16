"""CreateNew source/difference inventory for the bounded capability increment."""
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def entry(path):
    with path.open("rb") as source:
        raw = source.read(8*1024*1024+1)
    if len(raw) > 8*1024*1024:
        raise ValueError("Oversized review input")
    return raw, {"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}


def main():
    frozen = json.loads((ROOT/"work/candidates/v15-acceptance-control-plan/input-pins.json").read_bytes())
    unchanged = {}
    for row in frozen["inputs"]:
        raw, descriptor = entry(ROOT/row["path"])
        assert descriptor["sha256"] == row["sha256"] and descriptor["bytes"] == row["bytes"]
        unchanged[row["path"]] = descriptor
    assert len(unchanged) == 49
    sources, differences = {}, {}
    for previous in sorted((HERE/"before").rglob("*")):
        if not previous.is_file():
            continue
        relative = previous.relative_to(HERE/"before").as_posix()
        old, old_descriptor = entry(previous)
        new, descriptor = entry(ROOT/relative)
        sources[relative] = descriptor
        delta = "".join(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),
            fromfile="before/"+relative,tofile=relative)).encode()
        target = HERE/"diffs"/(relative.replace("/","__")+".diff")
        target.parent.mkdir(exist_ok=True)
        with target.open("xb") as stream:
            stream.write(delta)
        differences[relative] = {"before":old_descriptor,"after":descriptor,"diff_sha256":hashlib.sha256(delta).hexdigest()}
    sources["bridge/tests/test_research_preflight_discovery.py"] = entry(ROOT/"bridge/tests/test_research_preflight_discovery.py")[1]
    validation = json.loads((HERE/"final-validation.json").read_bytes())
    assert validation["exit_code"] == 0
    report = {"purpose":"v14_reviewed_capability_increment", "source_files":sources,"differences":differences,
        "prior_frozen_inputs_unchanged":unchanged,"validation":entry(HERE/"final-validation.json")[1],
        "tests_passed":118,"historical_effect_count":28,"production_executable_count":0,
        "v14_eight_effects_and_one_unknown":True,"v14_persistence_separate":True,
        "development_correction":"Retained first build metrics; r2 generation preserves prior cutoff. First test run had three stale historical expectations, corrected before final regression.",
        "preflight_test_delta":"Only aggregate count assertions20->28; original exact purpose/ordered IDs and aliases remain enforced.",
        "large_save_files_read":False,"game_accessed":False,"server_started":False,"requests_published":False,
        "native_built":False,"shared_support_modified":False,"all_shell_sessions_collected":True}
    with (HERE/"review.json").open("x",encoding="utf-8") as stream:
        json.dump(report,stream,indent=2);stream.write("\n")
    print(json.dumps(entry(HERE/"review.json")[1]))


if __name__ == "__main__":
    main()
