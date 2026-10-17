"""Execute a native unilateral Dissolve through the four public tools."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_execution import _copy_log_slice, _sha256_file, _stable_result, _write_json
from work.run_alliance_inbound_response import control_snapshot
from work.validate_alliance_reload import _run_snapshots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", required=True, type=Path)
    parser.add_argument("--recipient", default="PRO")
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--negative-request-id")
    args = parser.parse_args()
    installation = args.installation.resolve(strict=True)
    directory = installation.parent
    artifact = directory / ("dissolve-execution-" + uuid.uuid4().hex)
    artifact.mkdir()
    log = directory / "control-probe.jsonl"
    log_start = log.stat().st_size
    report = {"status": "unknown", "request_id": args.request_id, "checks": {}}
    try:
        session = ObserverSession(installation, game_exe())
        runtime_health = wait_runtime_ready(session, restore_minimized=True)
        report.update({"session_id": session.session_id,
                       "installation": _sha256_file(installation),
                       "manifest": _sha256_file(directory / "build-manifest.json")})
        before = control_snapshot(int(session.record["pid"]), artifact / "before-control.json")
        report["before"] = {"control": before, "health": runtime_health}
        if (report["before"]["health"].get("status") != "ready"
                or before.get("player_slot") != 189 or before.get("paused_flag") != 1):
            raise RuntimeError("POR_PAUSED_READY_BASELINE_REQUIRED")
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            if args.negative_request_id:
                # The independently loaded r3 baseline has no FRA-SAV alliance.
                negative = api.execute_diplomatic_action(
                    args.negative_request_id, "dissolve_alliance", "FRA", "SAV")
                report["negative_no_alliance"] = negative
                report["checks"]["no_alliance_not_submitted"] = (
                    negative.get("submitted") is False and negative.get("status") == "invalidated")
            inspection = api.inspect_diplomatic_action("dissolve_alliance", "FRA", args.recipient)
            report["inspection"] = inspection
            if (inspection.get("legality", {}).get("status") != "available"
                    or inspection.get("visibility", {}).get("status") != "visible"):
                raise RuntimeError("NATIVE_DISSOLVE_BASELINE_NOT_AVAILABLE")
            execution = api.execute_diplomatic_action(
                args.request_id, "dissolve_alliance", "FRA", args.recipient)
            report["execution"] = execution
            deadline = time.monotonic() + 10
            final = api.get_diplomatic_result(args.request_id)
            while final.get("submitted") is True and final.get("status") not in (
                    "executed", "invalidated", "expired") and time.monotonic() < deadline:
                time.sleep(0.1)
                final = api.get_diplomatic_result(args.request_id)
            report["result"] = final
            duplicate = api.execute_diplomatic_action(
                args.request_id, "dissolve_alliance", "FRA", args.recipient)
            report["duplicate"] = duplicate
            after_query = api.inspect_diplomatic_action("dissolve_alliance", "FRA", args.recipient)
            report["after_query"] = after_query
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            persisted = DiplomacyTools(journal, session).get_diplomatic_result(args.request_id)
        report["persisted"] = persisted
        after = control_snapshot(int(session.record["pid"]), artifact / "after-control.json")
        probes = _run_snapshots(session, artifact / "after" / "probes")
        report["after"] = {"control": after, "health": session.health(),
                           "probes": {name: item["snapshot_completeness"] for name, item in probes.items()}}
        report["checks"].update({
            "submitted": execution.get("submitted") is True,
            "actual_unilateral_execution": final.get("status") == final.get("game_outcome") == "executed"
                and final.get("result", {}).get("alliance_before") is True
                and final.get("result", {}).get("alliance_after") is False,
            "alliance_selector_hidden": after_query.get("visibility", {}).get("status") == "hidden"
                and after_query.get("visibility", {}).get("complete") is True
                and after_query.get("native_rule_components", {}).get("ui_action_selection") is False,
            "no_counterparty_acceptance": after_query.get("acceptance", {}).get("applicability") == "not_applicable",
            "journal_survives_reopen": _stable_result(final) == _stable_result(persisted),
            "duplicate_returns_existing_execution": duplicate.get("idempotent") is True
                and duplicate.get("status") == "executed",
            "por_paused_same_date": before.get("date_raw") == after.get("date_raw")
                and after.get("player_slot") == 189 and after.get("paused_flag") == 1,
            "after_snapshots_complete": all(item["snapshot_completeness"].get("complete") is True
                                            for item in probes.values()),
            "health_ready": report["after"]["health"].get("status") == "ready",
        })
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        report["native_events"] = _copy_log_slice(log, log_start, artifact / "native-events.jsonl")
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "checks": report["checks"],
                      "artifact": str(artifact)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
