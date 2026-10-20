"""Publish one bounded, native-rule-checked favor proposal to controlled FRA."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from work.local_config import game_exe
from work.run_peace_consequence_queries import _write_json, _copy_bounded_slice


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--installation", type=Path, required=True)
    p.add_argument("--proposer", choices=["PAP", "SAV", "LIT"], required=True)
    p.add_argument("--request-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    session = ObserverSession(args.installation.resolve(), game_exe())
    log = session.directory / "control-probe.jsonl"
    start = log.stat().st_size
    report = {"status": "running", "session_id": session.session_id,
              "proposer": args.proposer, "decision_country": "FRA",
              "fra_decision_submitted": False, "request_id": args.request_id}
    try:
        result = session._publish_atomic_request(
            f"TEST_ONLY FAVOR_GOLD_TO_FRA {args.proposer}\n", args.request_id,
            "alliance-inbound-test.req")
        if result != "published":
            raise ValueError("Fixture request was not published")
        api = DiplomacyTools(None, session)
        deadline = time.monotonic() + 8
        found = []
        while time.monotonic() < deadline:
            catalog = api.list_diplomatic_actions()
            found = [row for row in catalog["incoming_proposals"]
                     if row.get("action_id") == "trade_favors_for_gold"
                     and row.get("actor") == args.proposer and row.get("recipient") == "FRA"]
            if found:
                break
            time.sleep(.2)
        report["incoming_proposals"] = found
        report["status"] = "passed" if len(found) == 1 else "failed"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    report["native_slice"] = _copy_bounded_slice(log, start, output / "native.jsonl")
    _write_json(output / "report.json", report)
    print(json.dumps({key: report.get(key) for key in ("status", "incoming_proposals", "error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
