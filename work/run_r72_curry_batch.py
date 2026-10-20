"""Query Curry task conditions together and execute an explicit serial plan.

An existing journal resumes requests by reading their results. It never sends a
request again. Saving and advancing the date remain separate batch operations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_inbound_response import control_snapshot
from work.run_peace_consequence_queries import _copy_bounded_slice, _write_json


ACTIONS = ("curry_favors", "stop_curry_favors")


def _pair(api: DiplomacyTools, target: str) -> dict:
    return {action: api.inspect_diplomatic_action(action, "FRA", target)
            for action in ACTIONS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--targets", nargs="+", default=["PAP", "SAV", "LIT", "GEN"])
    parser.add_argument("--plan", type=Path,
                        help="JSON list of request_id/action_id/recipient operations")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-discovery", action="store_true",
                        help="Reuse the batch preflight; execution still checks current rules")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.resume:
        if not (output / "diplomacy.sqlite3").is_file():
            raise ValueError("Resume requires the original journal")
    else:
        output.mkdir(parents=True, exist_ok=False)
    plan = json.loads(args.plan.read_text(encoding="utf-8")) if args.plan else []
    if (not isinstance(plan, list)
            or any(not isinstance(row, dict) or set(row) != {
                "request_id", "action_id", "recipient"} or row["action_id"] not in ACTIONS
                   for row in plan)
            or len({row["request_id"] for row in plan}) != len(plan)):
        raise ValueError("Plan must contain distinct Curry start/stop requests")
    session = ObserverSession(args.installation.resolve(), game_exe())
    log = session.directory / "control-probe.jsonl"
    start_offset = log.stat().st_size
    name = "resume-report.json" if args.resume else "report.json"
    report = {"status": "running", "session_id": session.session_id,
              "installation": str(args.installation.resolve()), "resume_only": args.resume,
              "plan": plan, "queries": {}, "operations": []}
    _write_json(output / name, report)
    try:
        health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        if health["status"] != "ready":
            raise ValueError("Session is not ready")
        report["health"] = health
        before = control_snapshot(int(session.record["pid"]), output / "control-before.json")
        report["before"] = before
        if before["paused_flag"] != 1:
            raise ValueError("Batch requires the paused experimental game")
        with DurableJournal(output / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            if not args.resume and not args.skip_discovery:
                report["catalog"] = api.list_diplomatic_actions()
                report["queries"] = {target: _pair(api, target) for target in args.targets}
                _write_json(output / name, report)
            for operation in plan:
                request_id, action, target = (
                    operation[key] for key in ("request_id", "action_id", "recipient"))
                if args.resume:
                    result = api.get_diplomatic_result(request_id)
                else:
                    result = api.execute_diplomatic_action(
                        request_id, action, "FRA", target)
                deadline = time.monotonic() + 20
                while (result.get("submitted") is True
                       and result.get("game_outcome") != "executed"
                       and result.get("status") not in ("invalidated", "rejected", "expired")
                       and time.monotonic() < deadline):
                    time.sleep(0.15)
                    result = api.get_diplomatic_result(request_id)
                proof = result.get("result", {})
                starts = action == "curry_favors"
                checks = {
                    "submitted": result.get("submitted") is True,
                    "executed": result.get("game_outcome") == "executed",
                    "family_bound": proof.get("family") == "curry_favors",
                    "request_bound": proof.get("request_binding_verified") is True,
                    "execution_verified": proof.get("execution_verified") is True,
                    "task_transition": proof.get("task_before") is (not starts)
                                       and proof.get("task_after") is starts,
                }
                report["operations"].append({**operation, "result": result, "checks": checks})
                _write_json(output / name, report)
                if not all(checks.values()):
                    raise ValueError(f"Operation did not complete: {request_id}")
            report["after_queries"] = {
                target: _pair(api, target) for target in dict.fromkeys(
                    row["recipient"] for row in plan)}
        with DurableJournal(output / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            for operation in report["operations"]:
                operation["checks"]["journal_reopen_equal"] = (
                    operation["result"] == api.get_diplomatic_result(operation["request_id"]))
        report["checks"] = {
            "all_operations_verified": all(all(row["checks"].values())
                                           for row in report["operations"]),
            "queries_consumed": all(
                query["legality"]["status"] in ("available", "unavailable")
                and query["acceptance"]["applicability"] == "not_applicable"
                for pair in report["queries"].values() for query in pair.values()),
        }
        after = control_snapshot(int(session.record["pid"]), output / "control-after.json")
        report["after"] = after
        report["checks"]["same_paused_date"] = all(
            before[key] == after[key] for key in ("date_raw", "paused_flag", "player_slot"))
        report["status"] = "passed" if all(report["checks"].values()) else "incomplete"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    report["native_slice"] = _copy_bounded_slice(
        log, start_offset, output / ("resume-native.jsonl" if args.resume else "native.jsonl"))
    _write_json(output / name, report)
    print(json.dumps({key: report.get(key) for key in ("status", "checks", "error")},
                     ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
