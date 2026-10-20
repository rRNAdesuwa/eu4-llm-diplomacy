"""Read the five final resource views after the R73 exchange batch."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import ObserverSession
from bridge.favor_resources import validate_query
from work.local_config import game_exe
from work.run_peace_consequence_queries import _copy_bounded_slice, _write_json

CASES = (("trust", "FRA", "PAP"), ("trust", "PAP", "FRA"),
         ("trust", "SAV", "FRA"), ("men", "FRA", "SAV"),
         ("men", "PAP", "FRA"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    session = ObserverSession(args.installation.resolve(), game_exe())
    log = session.directory / "control-probe.jsonl"
    report = {"status": "running", "session_id": session.session_id,
              "business_submission": False, "cases": []}
    for kind, actor, recipient in CASES:
        action = f"trade_favors_for_{kind}"
        directory = args.output / f"{kind}_{actor}_{recipient}"
        directory.mkdir()
        offset = log.stat().st_size
        semantic = session.inspect_alliance(
            action, actor, recipient, "initiate",
            frozenset({f"native_favor_{kind}_query"}), allow_recipient_scope=True)
        raw_path = directory / "native.jsonl"
        _copy_bounded_slice(log, offset, raw_path)
        candidates = [event for line in raw_path.read_text(encoding="utf-8").splitlines()
                      if isinstance(event := json.loads(line), dict)
                      and event.get("event") == "native_alliance_inspection"
                      and event.get("session_id") == session.session_id
                      and (event.get("action_id"), event.get("actor"), event.get("recipient"))
                      == (action, actor, recipient)]
        if len(candidates) != 1:
            raise ValueError("Expected one bound final resource event")
        raw = candidates[0]
        valid = (ObserverSession._valid_native_inspection(
            raw, action, actor, recipient, "initiate", raw.get("date_raw"),
            raw.get("query_id"), session.session_id)
            and validate_query(raw.get("native_favor_trade"))
            and raw["native_favor_trade"]["complete"] is True)
        _write_json(directory / "semantic.json", semantic)
        report["cases"].append({"action_id": action, "actor": actor,
                                "recipient": recipient, "valid": valid,
                                "date_raw": raw.get("date_raw"),
                                "native_file": str(raw_path.resolve())})
    report["checks"] = {
        "all_resources_valid": all(row["valid"] for row in report["cases"]),
        "same_date": len({row["date_raw"] for row in report["cases"]}) == 1,
    }
    report["status"] = "passed" if all(report["checks"].values()) else "failed"
    _write_json(args.output / "report.json", report)
    print(json.dumps({key: report[key] for key in ("status", "checks")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
