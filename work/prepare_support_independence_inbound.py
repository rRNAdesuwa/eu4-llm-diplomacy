"""Prepare one native inbound relation proposal for a later LLM response.

The operator uses the observer's fixed TEST_ONLY source. It creates no bridge
response request and never chooses FRA's answer. Support Independence,
Military Access, and Vassalization share the same proposal discovery and
inspection path; their native family and capability remain explicit. Separate
date observation and run_alliance_inbound_response.py calls provide the
cross-day decision evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_execution import ExperimentStop, _copy_log_slice, _sha256_file, _write_json
from work.run_alliance_inbound_response import control_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--action-id", choices=(
                        "support_independence", "ask_military_access",
                        "offer_vassalization"),
                        default="support_independence")
    parser.add_argument("--expected-date-raw", type=int, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Z]{3}", args.actor) or args.actor == "FRA":
        parser.error("actor must be a three-letter country other than FRA")
    installation = args.installation.resolve(strict=True)
    directory = installation.parent
    military = args.action_id == "ask_military_access"
    vassalization = args.action_id == "offer_vassalization"
    artifact = directory / (("military-access" if military
                             else "vassalization" if vassalization
                             else "support")
                            + "-inbound-preparation-" + uuid.uuid4().hex)
    artifact.mkdir()
    log = directory / "control-probe.jsonl"
    log_start = None
    report = {
        "status": "running", "actor": args.actor, "recipient": "FRA",
        "action_id": args.action_id, "expected_date_raw": args.expected_date_raw,
        "family": ("military_access" if military
                    else "vassalization" if vassalization
                    else "support_independence"),
        "test_source": True, "response_execute_call_count": 0,
        "installation": _sha256_file(installation), "checks": {},
    }
    try:
        session = ObserverSession(installation, game_exe())
        report["session_id"] = session.session_id
        health = wait_runtime_ready(session, restore_minimized=True)
        before = control_snapshot(int(session.record["pid"]), artifact / "before-control.json")
        report["before"] = {"health": health, "control": before}
        if (health.get("status") != "ready" or before.get("player_slot") != 189
                or before.get("paused_flag") != 1
                or before.get("date_raw") != args.expected_date_raw
                or health.get("date_raw") != args.expected_date_raw):
            raise ExperimentStop("BASELINE_NOT_READY_POR_PAUSED", str(before))
        capability = (
            "native_inbound_military_access_response" if military
            else "native_inbound_vassalization_response" if vassalization
            else "native_inbound_support_independence_response"
        )
        if capability not in session.installation_capabilities():
            raise ExperimentStop("INBOUND_ACK_MISSING", str(installation))
        log_start = log.stat().st_size
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            catalog_before = api.list_diplomatic_actions(recipient="FRA")
            existing = [p for p in catalog_before.get("incoming_proposals", [])
                        if p.get("actor") == args.actor
                        and p.get("action_id") == args.action_id]
            report["catalog_before"] = catalog_before
            if existing:
                raise ExperimentStop("PROPOSAL_ALREADY_PRESENT", str(len(existing)))
            with (directory / "alliance-inbound-test.req").open("xb") as request:
                kind = (
                    "MILITARY_ACCESS_TO_FRA" if military
                    else "VASSALIZATION_TO_FRA" if vassalization
                    else "SUPPORT_TO_FRA"
                )
                request.write(f"TEST_ONLY {kind} {args.actor}\n".encode("ascii"))
            report["fixed_test_source_published"] = True
            deadline = time.monotonic() + 10
            proposals = []
            while time.monotonic() < deadline:
                catalog = api.list_diplomatic_actions(recipient="FRA")
                proposals = [p for p in catalog.get("incoming_proposals", [])
                             if p.get("actor") == args.actor
                             and p.get("action_id") == args.action_id]
                if proposals:
                    break
                time.sleep(0.2)
            report["catalog_after"] = catalog
            if len(proposals) != 1:
                raise ExperimentStop("UNIQUE_PROPOSAL_NOT_FOUND", str(len(proposals)))
            report["proposal"] = proposals[0]
            parameters = {"proposal_id": proposals[0]["proposal_id"]}
            report["inspections"] = {
                decision: api.inspect_diplomatic_action(
                    args.action_id, args.actor, "FRA", decision, parameters)
                for decision in ("accept", "reject")
            }
        after = control_snapshot(int(session.record["pid"]), artifact / "after-control.json")
        report["after_control"] = after
        report["checks"] = {
            "unique_pending": len(proposals) == 1,
            "same_por_paused_date": all(
                after.get(k) == before.get(k) for k in ("player_slot", "paused_flag", "date_raw")),
            "both_decisions_available": all(
                q.get("legality", {}).get("status") == "available"
                for q in report["inspections"].values()),
            "no_response_request": report["response_execute_call_count"] == 0,
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if log_start is not None:
            report["native_events"] = _copy_log_slice(log, log_start, artifact / "native-events.jsonl")
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
