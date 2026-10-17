"""Run native Offer/Break Royal Marriage queries in a paused experiment."""
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
    parser.add_argument("--installation", required=True, type=Path)
    parser.add_argument("--expected-date-raw", type=int, default=56459880)
    parser.add_argument("--recipient", action="append",
                        help="Additional test tag; SAV and GEN remain the baseline pair.")
    args = parser.parse_args()
    if args.recipient and any(not re.fullmatch(r"[A-Z]{3}", tag) for tag in args.recipient):
        parser.error("Recipients must be three uppercase letters.")
    recipients = (tuple(dict.fromkeys(("SAV", "GEN", *args.recipient))) if args.recipient
                  else ("SAV", "LIT", "GEN", "LAN", "MOR", "PRO", "ENG"))
    installation = args.installation.resolve(strict=True)
    artifact = installation.parent / ("royal-marriage-queries-" + uuid.uuid4().hex)
    artifact.mkdir()
    log = installation.parent / "control-probe.jsonl"
    start = log.stat().st_size
    report = {"status": "unknown", "checks": {}, "queries": {}, "business_submission": False}
    try:
        session = ObserverSession(installation, game_exe())
        report["session_id"] = session.session_id
        health = wait_runtime_ready(session, restore_minimized=True)
        before = control_snapshot(session.record["pid"], artifact / "before-control.json")
        if (health.get("status") != "ready" or before.get("player_slot") != 189
                or before.get("paused_flag") != 1 or before.get("date_raw") != args.expected_date_raw):
            raise RuntimeError("POR_PAUSED_EXPECTED_DATE_REQUIRED")
        snapshots_before = _run_snapshots(session, artifact / "before" / "probes")
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id, session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            report["catalog"] = api.list_diplomatic_actions(actor="FRA", recipient="SAV")
            for recipient in recipients:
                for action in ("offer_royal_marriage", "break_royal_ties"):
                    report["queries"][action + ":" + recipient] = api.inspect_diplomatic_action(
                        action, "FRA", recipient)
        snapshots_after = _run_snapshots(session, artifact / "after" / "probes")
        after = control_snapshot(session.record["pid"], artifact / "after-control.json")
        queries = report["queries"]
        offers = [q for key, q in queries.items() if key.startswith("offer_")]
        breaks = [q for key, q in queries.items() if key.startswith("break_")]
        report["checks"] = {
            "exact_native_query_capability": "native_royal_marriage_query" in session.installation_capabilities(),
            "legal_offer_observed": any(q.get("legality", {}).get("status") == "available" for q in offers),
            "unavailable_offer_observed": any(q.get("legality", {}).get("status") == "unavailable" for q in offers),
            "sav_native_rules_complete": queries["offer_royal_marriage:SAV"].get("legality", {}).get("complete") is True,
            "sav_native_prediction_observed": queries["offer_royal_marriage:SAV"].get("acceptance", {}).get("prediction_available") is True,
            "sav_reason_text_observed": queries["offer_royal_marriage:SAV"].get("acceptance", {}).get("details_available") is True,
            "sav_reason_identifiers_verified": all(item.get("identifier_verified") is True
                and item.get("native_value_verified") is True
                for item in queries["offer_royal_marriage:SAV"].get("acceptance", {}).get("items", []))
                and len(queries["offer_royal_marriage:SAV"].get("acceptance", {}).get("items", [])) == 5,
            "break_acceptance_not_applicable": all(q.get("acceptance", {}).get("applicability") == "not_applicable" for q in breaks),
            "queries_grant_no_execution": all(q.get("interface_support", {}).get("execute") not in
                ("native_offer_submission", "native_dissolve_submission", "native_royal_marriage_submission") for q in queries.values()),
            "por_paused_same_date": before.get("date_raw") == after.get("date_raw")
                and after.get("player_slot") == 189 and after.get("paused_flag") == 1,
            "snapshots_complete": all(record.get("snapshot_completeness", {}).get("complete") is True
                for group in (snapshots_before, snapshots_after) for record in group.values()),
            "diplomat_tasks_unchanged": _diplomat_semantics(snapshots_before["diplomats"]["snapshot"])
                == _diplomat_semantics(snapshots_after["diplomats"]["snapshot"]),
            "alliance_snapshot_unchanged": snapshots_before["alliance_state"]["snapshot"]
                == snapshots_after["alliance_state"]["snapshot"],
            "health_ready": session.health().get("status") == "ready",
        }
        if "offer_royal_marriage:LAN" in queries:
            report["checks"]["florence_signoria_offer_legal"] = queries[
                "offer_royal_marriage:LAN"].get("legality", {}).get("status") == "available"
        report.update(before=before, after=after)
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        report["native_events"] = _copy_log_slice(log, start, artifact / "native-events.jsonl")
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "checks": report["checks"], "artifact": str(artifact)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
