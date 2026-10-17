#!/usr/bin/env python3
"""Record native Declare War queries and the unchanged experiment boundary.

This operator calls only inspect_diplomatic_action.  A passed report proves
the returned query layer, not complete parameter selection or war execution.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_execution import _copy_log_slice, _write_json
from work.run_improve_relations_execution import _new_artifact
from work.run_royal_marriage_execution import _installation_binding, _snapshots_complete
from work.validate_alliance_reload import _control_summary, _diplomat_semantics, _run_snapshots


def _boundary(probes: dict) -> dict:
    return {
        "control": _control_summary(probes["control_state"]["snapshot"]),
        "diplomats": _diplomat_semantics(probes["diplomats"]["snapshot"]),
        "wars": probes["war_state"]["snapshot"].get("countries"),
        "alliances": probes["alliance_state"]["snapshot"].get("countries"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", required=True, type=Path)
    parser.add_argument("--expected-date-raw", required=True, type=int)
    parser.add_argument("--recipient", action="append")
    args = parser.parse_args(argv)
    installation = args.installation.resolve()
    recipients = args.recipient or ["ENG", "BUR", "PRO", "ORL", "POR"]
    artifact = _new_artifact(installation.parent, "declare-war-queries")
    report = {
        "validator": "run_declare_war_queries.py", "version": 1,
        "status": "running", "layer": "native_default_object_query",
        "actor": "FRA", "recipients": recipients,
        "expected_date_raw": args.expected_date_raw,
        "execute_call_count": 0, "business_submission": False,
        "checks": {},
    }
    log = installation.parent / "control-probe.jsonl"
    offset = None
    try:
        if (not recipients or len(recipients) != len(set(recipients))
                or len(recipients) > 16
                or any(not re.fullmatch(r"[A-Z]{3}", tag) or tag == "FRA"
                       for tag in recipients)):
            raise ValueError("RECIPIENTS_INVALID")
        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe().resolve(strict=True))
        report["session_id"] = session.session_id
        report["pid"] = session.record["pid"]
        report["health"] = wait_runtime_ready(session, restore_minimized=False)
        if report["health"].get("status") != "ready":
            raise RuntimeError("SESSION_NOT_READY")
        report["capabilities"] = sorted(session.installation_capabilities())
        if "native_declare_war_query" not in report["capabilities"]:
            raise RuntimeError("DECLARE_WAR_QUERY_CAPABILITY_MISSING")
        before = _run_snapshots(session, artifact / "before")
        report["before_boundary"] = _boundary(before)
        control = report["before_boundary"]["control"]
        if control != {"date_raw": args.expected_date_raw, "player_slot": 189,
                       "paused_flag": 1}:
            raise RuntimeError("BASELINE_NOT_POR_PAUSED_EXPECTED_DATE")
        offset = log.stat().st_size
        results = {}
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            for recipient in recipients:
                results[recipient] = api.inspect_diplomatic_action(
                    "declare_war", "FRA", recipient, phase="initiate", parameters={})
        _write_json(artifact / "queries.json", results)
        report["queries"] = results
        after = _run_snapshots(session, artifact / "after")
        report["after_boundary"] = _boundary(after)
        report["native_events"] = _copy_log_slice(
            log, offset, artifact / "native-events-slice.jsonl")
        events = []
        with (artifact / "native-events-slice.jsonl").open("rb") as stream:
            for raw in stream:
                if len(raw) > 256 * 1024:
                    raise RuntimeError("NATIVE_EVENT_TOO_LARGE")
                event = json.loads(raw)
                if event.get("event") == "native_declare_war_inspection":
                    events.append(event)
        by_recipient = {tag: [e for e in events if e.get("recipient") == tag]
                        for tag in recipients}
        report["native_inspections"] = events
        identities = all(
            len(by_recipient[tag]) == 1
            and by_recipient[tag][0].get("actor") == "FRA"
            and by_recipient[tag][0].get("action_id") == "declare_war"
            and by_recipient[tag][0].get("family") == "declare_war"
            and by_recipient[tag][0].get("session_id") == session.session_id
            and by_recipient[tag][0].get("date_raw") == args.expected_date_raw
            for tag in recipients)
        report["checks"] = {
            "native_query_per_recipient": identities,
            "native_rule_checks_called": identities and all(
                all(e.get(key) is True for key in (
                    "ui_selection_checked", "ui_enabled_gate_checked", "validity_called",
                    "initiation_gate_checked", "object_unchanged"))
                and all(type(e.get(key)) is bool for key in (
                    "native_visibility", "common_action_gate", "native_validity", "initiation_gate"))
                for e in events),
            "native_query_did_not_submit": identities and all(
                e.get("submitted") is False for e in events),
            "snapshots_complete": _snapshots_complete(before) and _snapshots_complete(after),
            "experiment_boundary_unchanged": report["before_boundary"] == report["after_boundary"],
            "public_query_identity": all(
                q.get("action_id") == "declare_war" and q.get("actor") == "FRA"
                and q.get("recipient") == tag
                and q.get("session", {}).get("status") == "ready"
                for tag, q in results.items()),
            "public_acceptance_not_applicable": all(
                q.get("acceptance", {}).get("applicability") == "not_applicable"
                for q in results.values()),
            "parameter_gap_preserved": all(
                q.get("legality", {}).get("status") == "unknown"
                and q.get("legality", {}).get("complete") is False
                for q in results.values()),
            "source_build_bound": report.get("build_binding", {}).get(
                "installation_matches_build_manifest") is True,
        }
        if any(e.get("candidate_enumeration_called") for e in events):
            report["layer"] = "native_candidates_query"
            report["checks"]["native_candidate_capture_complete"] = identities and all(
                e.get("candidate_enumeration_called") is True
                and e.get("candidate_enumeration_complete") is True
                and e.get("candidate_cleanup_verified") is True
                and e.get("candidate_capture_truncated") is False
                and type(e.get("candidate_native_count")) is int
                and e["candidate_native_count"] == len(e.get("candidates", []))
                for e in events)
            report["checks"]["public_candidate_count_matches"] = identities and all(
                len(results[tag].get("candidates", []))
                == by_recipient[tag][0].get("candidate_native_count")
                for tag in recipients)
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        if offset is not None and "native_events" not in report:
            report["native_events"] = _copy_log_slice(
                log, offset, artifact / "native-events-slice.jsonl")
    _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "report": str(artifact / "report.json"),
                      "checks": report["checks"], "error": report.get("error")},
                     ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
