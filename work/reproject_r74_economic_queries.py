"""Rebuild public R74 economic queries from captured events, without game access."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession


class Replay:
    record = {"controlled_countries": ["FRA"]}

    def __init__(self, event):
        self.event = event

    def health(self):
        return {"status": "ready", "date_raw": self.event["date_raw"],
                "state_id": "offline-captured-state", "reasons": [], "complete": True}

    def installation_capabilities(self):
        return frozenset({"native_gift_query", "native_gift_submission",
                          "native_influence_query", "native_influence_submission"})

    def inspect_send_gift(self, *args):
        return ObserverSession._semantic_inspection(self.event, {}, codec="eu4_escape")

    inspect_influence_nation = inspect_send_gift


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = json.loads(args.source_report.read_text(encoding="utf-8"))
    assert source["status"] == "passed"
    rows = []
    for case in source["cases"]:
        raw_file = Path(case["native_file"])
        events = [json.loads(line) for line in raw_file.read_text(encoding="utf-8").splitlines()]
        raw = next(event for event in events if event.get("event") == "native_alliance_inspection"
                   and event.get("actor") == case["actor"] and event.get("recipient") == case["recipient"]
                   and event.get("action_id") == case["action_id"])
        public = DiplomacyTools(None, Replay(raw)).inspect_diplomatic_action(
            case["action_id"], case["actor"], case["recipient"], "initiate", case["parameters"])
        assert public["legality"] == case["public"]["legality"]
        assert public["visibility"] == {
            "status": "visible" if raw["native_visibility"] else "hidden", "complete": True}
        for key in ("gift", "influence", "costs", "acceptance"):
            assert public.get(key) == case["public"].get(key), key
        rows.append({"action_id": case["action_id"], "recipient": case["recipient"],
                     "parameters": case["parameters"], "public": public,
                     "source_native_file": str(raw_file), "checks": {"full_public_projection": True}})
    report = {"status": "passed", "source_report": str(args.source_report.resolve()),
              "game_queries": 0, "business_submissions": 0, "cases": rows}
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "passed", "cases": len(rows), "game_queries": 0}))


if __name__ == "__main__":
    main()
