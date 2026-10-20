"""Read only bounded FRA country blocks to compare serialized diplomats."""
from __future__ import annotations
import json
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import inspect_dissolve_save_pair as reader
from work.local_config import user_data


def scan(path):
    scanner = reader.SaveScanner()
    with path.open(encoding="utf-8-sig", errors="replace") as stream:
        scanner.consume(stream)
    capture = scanner.country_captures["FRA"]
    assert capture.complete and capture.bytes_captured <= reader.MAX_COUNTRY_CAPTURE
    body = reader.extract_block(capture.text, capture.text.index("{"))
    holder = next(e.body for e in reader.top_level_entries(body) if e.key == "diplomats")
    envoys = []
    for envoy in reader.top_level_entries(holder):
        if envoy.key == "envoy":
            envoys.append(reader.parse_field_body(envoy.body)["fields"])
    return {"path": str(path), "date": scanner.save_date,
            "country_bytes": capture.bytes_captured, "envoys": envoys}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path)
    args = p.parse_args()
    if args.source:
        result = json.loads(args.source.read_text(encoding="utf-8"))
        states = result["saves"]
        for state in states.values():
            state["envoys"] = [{k: e[k] for k in ("id", "type", "action") if k in e}
                                for e in state["envoys"]]
        by = {name: {int(e["id"]): e.get("action") for e in state["envoys"]}
              for name, state in states.items()}
        checks = {
            "three_complete_bounded_country_reads": all(0 < s["country_bytes"] < reader.MAX_COUNTRY_CAPTURE for s in states.values()),
            "four_diplomats_each": all(len(s["envoys"]) == 4 for s in states.values()),
            "before_one_without_action": sum(v is None for v in by["before"].values()) == 1,
            "zero_none_without_action": all(v is not None for v in by["zero"].values()),
            "returned_two_without_action": sum(v is None for v in by["returned"].values()) == 2,
            "new_improve_diplomat_3_started": by["before"][3] is None and by["zero"][3] == "2",
            "recalled_diplomat_3_returned": by["returned"][3] is None,
            "prior_returning_diplomat_2_returned": by["zero"][2] == "1" and by["returned"][2] is None,
            "existing_tasks_0_1_unchanged": all(by[n][i] == "2" for n in by for i in (0, 1)),
            "before_and_zero_same_date": states["before"]["date"] == states["zero"]["date"] == "1455.10.11",
            "returned_date": states["returned"]["date"] == "1455.10.18",
        }
        result.update(status="passed" if all(checks.values()) else "failed", checks=checks,
                      source_observation=str(args.source.resolve()), live_game_access=False)
        output = ROOT / "work/runtime/r68-diplomat-save-fields-20261019-002/report.json"
        assert not output.exists(), "OUTPUT_EXISTS"
        output.parent.mkdir(parents=True, exist_ok=False)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": result["status"], "checks": checks, "report": str(output)}, ensure_ascii=False))
        return
    output = ROOT / "work/runtime/r68-diplomat-save-fields-20261019-001/report.json"
    assert not output.exists(), "OUTPUT_EXISTS"
    saves = user_data() / "save games"
    result = {"status": "observed", "country": "FRA", "saves": {}}
    for name, filename in (("before", "llm_diplomacy_r67_ally_request_rejected_20261019.eu4"),
        ("zero", "llm_diplomacy_r68_zero_diplomats_checkpoint_20261019.eu4"),
        ("returned", "llm_diplomacy_r68_diplomats_returned_20261019.eu4")):
        result["saves"][name] = scan(saves / filename)
    output.parent.mkdir(parents=True, exist_ok=False)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
