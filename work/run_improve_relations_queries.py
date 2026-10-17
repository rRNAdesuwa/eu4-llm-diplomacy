"""Inspect native Improve/Stop tasks without submitting a diplomatic command."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_execution import _copy_log_slice, _write_json
from work.run_alliance_inbound_response import control_snapshot
from work.validate_alliance_reload import _diplomat_semantics, _run_snapshots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, default=56459880)
    parser.add_argument("--recipient", action="append")
    args = parser.parse_args()
    recipients = tuple(dict.fromkeys(("SAV", *(args.recipient or ("PRO", "ENG")))))
    if any(not re.fullmatch(r"[A-Z]{3}", tag) for tag in recipients):
        parser.error("Recipients must be three uppercase letters")
    installation = args.installation.resolve(strict=True)
    directory = installation.parent / ("improve-relations-queries-" + uuid.uuid4().hex)
    directory.mkdir()
    log = installation.parent / "control-probe.jsonl"
    offset = log.stat().st_size
    report = {"status": "unknown", "business_submission": False,
              "checks": {}, "queries": {}}
    try:
        session = ObserverSession(installation, game_exe())
        report["session_id"] = session.session_id
        report["health_before"] = wait_runtime_ready(session, restore_minimized=True)
        before = control_snapshot(session.record["pid"], directory / "before-control.json")
        if (report["health_before"].get("status") != "ready"
                or before.get("player_slot") != 189 or before.get("paused_flag") != 1
                or before.get("date_raw") != args.expected_date_raw):
            raise RuntimeError("POR_PAUSED_EXPECTED_DATE_REQUIRED")
        snapshots_before = _run_snapshots(session, directory / "before" / "probes")
        with DurableJournal(directory / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            report["catalog"] = api.list_diplomatic_actions(actor="FRA", recipient="SAV")
            for recipient in recipients:
                for action in ("improve_relations", "stop_improving_relations"):
                    report["queries"][action + ":" + recipient] = api.inspect_diplomatic_action(
                        action, "FRA", recipient, parameters={})
        snapshots_after = _run_snapshots(session, directory / "after" / "probes")
        after = control_snapshot(session.record["pid"], directory / "after-control.json")
        queries = report["queries"]
        report["checks"] = {
            "dedicated_native_query_ack": "native_improve_relations_query"
                in session.installation_capabilities(),
            "sav_start_available": queries["improve_relations:SAV"]["legality"]["status"] == "available",
            "sav_stop_unavailable_without_task": queries["stop_improving_relations:SAV"]["legality"]["status"] == "unavailable",
            "sav_native_rules_complete": queries["improve_relations:SAV"]["legality"]["complete"] is True,
            "all_queries_have_native_rules": all(q["interface_support"]["query"] in
                ("native_rules", "partial_native_rules") for q in queries.values()),
            "unilateral_acceptance_not_applicable": all(q["acceptance"]["applicability"] == "not_applicable" for q in queries.values()),
            "snapshots_complete": all(v["snapshot_completeness"]["complete"] is True
                for group in (snapshots_before, snapshots_after) for v in group.values()),
            "diplomat_tasks_unchanged": _diplomat_semantics(snapshots_before["diplomats"]["snapshot"])
                == _diplomat_semantics(snapshots_after["diplomats"]["snapshot"]),
            "por_paused_same_date": after["date_raw"] == before["date_raw"]
                and after["player_slot"] == 189 and after["paused_flag"] == 1,
            "health_ready": session.health()["status"] == "ready",
        }
        report.update(before=before, after=after)
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    finally:
        report["native_events"] = _copy_log_slice(log, offset, directory / "native-events.jsonl")
        _write_json(directory / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(directory),
                      "checks": report["checks"]}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
