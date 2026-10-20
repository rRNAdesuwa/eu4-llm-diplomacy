"""Capture one paused batch of native gift/influence public inspections."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.gift_influence import project_query, validate_query
from work.local_config import game_exe
from work.run_alliance_inbound_response import control_snapshot
from work.run_peace_consequence_queries import _copy_bounded_slice, _write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--targets", nargs="+", default=["PAP", "SAV", "LIT", "GEN"])
    parser.add_argument("--gift-ducats", nargs="+", type=int, default=[25, 1000])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    session = ObserverSession(args.installation.resolve(), game_exe())
    api = DiplomacyTools(None, session)
    log = session.directory / "control-probe.jsonl"
    report = {"status": "running", "session_id": session.session_id,
              "business_submission": False, "cases": []}
    try:
        before = control_snapshot(int(session.record["pid"]), args.output / "control-before.json")
        if before["paused_flag"] != 1:
            raise ValueError("The economic query batch requires the paused experiment")
        report["before"] = before
        _write_json(args.output / "catalog.json", api.list_diplomatic_actions())
        for recipient in args.targets:
            cases = [("send_gift", {"ducats": value}) for value in args.gift_ducats]
            cases.append(("influence_nation", {}))
            for action, parameters in cases:
                suffix = str(parameters["ducats"]) if parameters else "default"
                directory = args.output / "cases" / f"{action}_FRA_{recipient}_{suffix}"
                directory.mkdir(parents=True)
                offset = log.stat().st_size
                public = api.inspect_diplomatic_action(
                    action, "FRA", recipient, "initiate", parameters)
                raw_path = directory / "native.jsonl"
                raw_slice = _copy_bounded_slice(log, offset, raw_path)
                events = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()
                          if line.strip()]
                native = [event for event in events if isinstance(event, dict)
                          and event.get("session_id") == session.session_id
                          and event.get("action_id") == action
                          and event.get("actor") == "FRA"
                          and event.get("recipient") == recipient
                          and event.get("event") == "native_alliance_inspection"]
                _write_json(directory / "public.json", public)
                _write_json(directory / "native-events.json", native)
                raw = native[0] if len(native) == 1 else {}
                family = "gift" if action == "send_gift" else "influence"
                resource = raw.get(f"native_{family}")
                resource_valid = validate_query(action, resource)
                checks = {
                    "raw_identity_bound": ObserverSession._valid_native_inspection(
                        raw, action, "FRA", recipient, "initiate", before["date_raw"],
                        raw.get("query_id"), session.session_id),
                    "native_resource_valid": resource_valid,
                    "native_resource_complete": resource_valid and resource["complete"] is True,
                    "public_resource_consumed": resource_valid and public.get(family)
                    == project_query(action, resource, "FRA", recipient),
                    "unilateral_acceptance": public.get("acceptance", {}).get("applicability")
                    == "not_applicable",
                    "public_legality_known": public.get("legality", {}).get("status")
                    in ("available", "unavailable"),
                    "gift_requested_amount_bound": action != "send_gift" or resource_valid
                    and resource["ducats"] == parameters["ducats"]
                    and resource["amount_raw"] == parameters["ducats"] * 1000,
                }
                report["cases"].append({
                    "action_id": action, "actor": "FRA", "recipient": recipient,
                    "parameters": parameters, "public": public,
                    "checks": checks, "native_event_count": len(native), "native_slice": raw_slice,
                    "native_file": str(raw_path.resolve()),
                })
                _write_json(args.output / "report.json", report)
        after = control_snapshot(int(session.record["pid"]), args.output / "control-after.json")
        report["after"] = after
        report["capture_checks"] = {
            "same_paused_date": all(before[key] == after[key]
                                    for key in ("date_raw", "paused_flag", "player_slot")),
            "one_bound_native_inspection_per_case": all(
                row["native_event_count"] == 1 for row in report["cases"]),
            "public_legality_known": all(
                row["public"].get("legality", {}).get("status") in ("available", "unavailable")
                for row in report["cases"]),
            "all_typed_public_contracts_passed": all(
                all(row["checks"].values()) for row in report["cases"]),
        }
        report["status"] = "passed" if all(report["capture_checks"].values()) else "incomplete"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    _write_json(args.output / "report.json", report)
    print(json.dumps({key: report.get(key) for key in ("status", "capture_checks", "error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
