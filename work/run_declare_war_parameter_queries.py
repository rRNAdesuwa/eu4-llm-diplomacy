#!/usr/bin/env python3
"""Inspect default, selected, missing, and explicit no-CB contexts in one batch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_execution import _copy_log_slice, _write_json
from work.run_declare_war_queries import _boundary
from work.run_improve_relations_execution import _new_artifact
from work.run_royal_marriage_execution import _installation_binding, _snapshots_complete
from work.validate_alliance_reload import _run_snapshots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    args = parser.parse_args()
    installation = args.installation.resolve()
    artifact = _new_artifact(installation.parent, "declare-war-parameter-queries")
    cases = [
        ("default", {}),
        ("core_177", {"casus_belli": "cb_core", "war_goal": {
            "province_id": 177, "beneficiary": "FRA"}, "call_allies": []}),
        ("missing_province", {"casus_belli": "cb_core", "war_goal": {
            "province_id": 2147483647, "beneficiary": "FRA"}, "call_allies": []}),
        ("no_cb", {"casus_belli": "no_casus_belli", "war_goal": {
            "province_id": -1, "beneficiary": "FRA"}, "call_allies": []}),
    ]
    report = {"validator": "run_declare_war_parameter_queries.py", "version": 1,
              "status": "running", "mode": "read_only_selected_context_queries",
              "actor": "FRA", "recipient": "ENG", "cases": dict(cases),
              "expected_date_raw": args.expected_date_raw,
              "execute_call_count": 0, "business_submission": False, "checks": {}}
    log = installation.parent / "control-probe.jsonl"
    offset = None
    try:
        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe().resolve(strict=True))
        report["session_id"] = session.session_id
        report["pid"] = session.record["pid"]
        report["health"] = wait_runtime_ready(session, restore_minimized=False)
        if report["health"].get("status") != "ready":
            raise RuntimeError("SESSION_NOT_READY")
        before = _run_snapshots(session, artifact / "before")
        report["before_boundary"] = _boundary(before)
        if report["before_boundary"]["control"] != {
                "date_raw": args.expected_date_raw, "paused_flag": 1, "player_slot": 189}:
            raise RuntimeError("BASELINE_NOT_POR_PAUSED_EXPECTED_DATE")
        offset = log.stat().st_size
        queries = {}
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            for label, parameters in cases:
                queries[label] = api.inspect_diplomatic_action(
                    "declare_war", "FRA", "ENG", phase="initiate", parameters=parameters)
                _write_json(artifact / (label + ".json"), queries[label])
        report["queries"] = queries
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
        report["native_inspections"] = events
        if len(events) != len(cases):
            raise RuntimeError("NATIVE_QUERY_COUNT_MISMATCH")
        by_case = dict(zip((label for label, _ in cases), events))
        identities = all(e.get("session_id") == session.session_id
                         and e.get("date_raw") == args.expected_date_raw
                         and e.get("actor") == "FRA" and e.get("recipient") == "ENG"
                         and e.get("action_id") == "declare_war" for e in events)
        matched = ("core_177", "no_cb")
        expected = lambda e: "available" if all(e.get(k) is True for k in (
            "native_visibility", "common_action_gate", "native_validity", "initiation_gate")) else "unavailable"
        report["checks"] = {
            "four_unique_native_queries": identities and len({e.get("query_id") for e in events}) == 4,
            "exact_selected_parameters": all(
                by_case[label].get("selection_requested") is True
                and by_case[label].get("requested_casus_belli") == parameters["casus_belli"]
                and by_case[label].get("requested_province_id") == parameters["war_goal"]["province_id"]
                and by_case[label].get("requested_beneficiary") == "FRA"
                for label, parameters in cases if parameters),
            "selected_contexts_complete": all(
                by_case[label].get("selection_matched") is True
                and by_case[label].get("selection_match_count") == 1
                and by_case[label].get("parameter_context_complete") is True
                and by_case[label].get("full_rules_complete") is True for label in matched),
            "selected_public_legality_matches_native": all(
                queries[label].get("legality", {}).get("status") == expected(by_case[label])
                for label in matched),
            "missing_candidate_rejected": by_case["missing_province"].get("selection_matched") is False
                and by_case["missing_province"].get("selection_match_count") == 0
                and queries["missing_province"].get("legality", {}).get("status") == "unavailable",
            "missing_candidate_has_no_default_cost": queries["missing_province"].get("costs", {}).get("items") == []
                and queries["missing_province"].get("costs", {}).get("context") == "requested_selection_unavailable",
            "native_candidates_complete": all(e.get("candidate_enumeration_complete") is True
                and e.get("candidate_cleanup_verified") is True for e in events),
            "native_cost_calls_returned": all(all(e.get("native_costs", {}).get(k) is True
                for k in ("called", "action_unchanged", "stability_available", "warex_available", "primary_available"))
                for e in events),
            "core_has_owned_candidate": by_case["core_177"].get("owned_payload_present") is True,
            "no_cb_uses_native_empty_context": by_case["no_cb"].get("native_default_payload") is True,
            "public_acceptance_not_applicable": all(q.get("acceptance", {}).get("applicability") == "not_applicable"
                for q in queries.values()),
            "all_queries_read_only": all(e.get("submitted") is False and e.get("object_unchanged") is True for e in events),
            "four_snapshots_complete": _snapshots_complete(before) and _snapshots_complete(after),
            "experiment_boundary_unchanged": report["before_boundary"] == report["after_boundary"],
            "source_build_bound": report.get("build_binding", {}).get("installation_matches_build_manifest") is True,
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        if offset is not None and "native_events" not in report:
            report["native_events"] = _copy_log_slice(log, offset, artifact / "native-events-slice.jsonl")
    _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "report": str(artifact / "report.json"),
                      "checks": report["checks"], "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
