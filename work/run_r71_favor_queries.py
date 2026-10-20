"""Query several native favor actions/targets in one paused observer session."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.favor_trade import validate_query
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_inbound_response import control_snapshot
from work.run_peace_consequence_queries import _write_json, _copy_bounded_slice
from work.run_peace_empty_offer_queries import _has_private_fields


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--installation", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--actions", nargs="+", default=["trade_favors_for_gold"])
    p.add_argument("--targets", nargs="+", default=["SAV", "GEN", "PAP", "LIT", "MLO", "POR", "ENG", "ORL"])
    args = p.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    session = ObserverSession(args.installation.resolve(), game_exe())
    log = session.directory / "control-probe.jsonl"
    report = {"status": "running", "session_id": session.session_id,
              "installation": str(args.installation.resolve()), "cases": [],
              "business_submission": False}
    def persist():
        _write_json(output / "report.json", report)
    persist()
    try:
        report["health"] = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        before = control_snapshot(int(session.record["pid"]), output / "control-before.json")
        report["before"] = before
        assert report["health"]["status"] == "ready" and before["paused_flag"] == 1
        api = DiplomacyTools(None, session)
        _write_json(output / "catalog.json", api.list_diplomatic_actions())
        for action in args.actions:
            for target in args.targets:
                directory = output / "cases" / (action + "_" + target)
                directory.mkdir(parents=True)
                start = log.stat().st_size
                public = api.inspect_diplomatic_action(action, "FRA", target)
                raw_slice = _copy_bounded_slice(log, start, directory / "native.jsonl")
                events = []
                for line in (directory / "native.jsonl").read_text(encoding="utf-8").splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if (event.get("session_id") == session.session_id
                            and event.get("event") == "native_alliance_inspection"
                            and event.get("action_id") == action and event.get("recipient") == target):
                        events.append(event)
                raw = events[-1] if events else None
                _write_json(directory / "public.json", public)
                if raw:
                    _write_json(directory / "native-event.json", raw)
                report["cases"].append({
                    "name": action + "_" + target, "action_id": action, "recipient": target,
                    "public_path": str(directory / "public.json"), "native_slice": raw_slice,
                    "raw_identity_valid": bool(raw and session._valid_native_inspection(
                        raw, action, "FRA", target, "initiate", raw["date_raw"],
                        raw["query_id"], session.session_id)),
                    "raw_resource_valid": bool(raw and validate_query(raw.get("native_favor_trade"))),
                    "legality": public["legality"], "favor_trade": public.get("favor_trade"),
                    "acceptance": public["acceptance"], "public_private_fields_absent": not _has_private_fields(public),
                })
                persist()
        after = control_snapshot(int(session.record["pid"]), output / "control-after.json")
        report["after"] = after
        report["checks"] = {
            "same_paused_date": all(before[k] == after[k] for k in ("date_raw", "paused_flag", "player_slot")),
            "all_raw_identity_valid": all(c["raw_identity_valid"] for c in report["cases"]),
            "all_raw_resource_valid": all(c["raw_resource_valid"] for c in report["cases"]),
            "all_public_trade_present": all(isinstance(c["favor_trade"], dict) for c in report["cases"]),
            "public_private_fields_absent": all(c["public_private_fields_absent"] for c in report["cases"]),
        }
        report["available_targets"] = [c["recipient"] for c in report["cases"]
                                       if c["legality"]["status"] == "available"]
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    persist()
    print(json.dumps({k: report.get(k) for k in ("status", "checks", "available_targets", "error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
