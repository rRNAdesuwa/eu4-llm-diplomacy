"""Inspect each implemented native family once after a shared observer change."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_execution import _write_json
from work.run_royal_marriage_execution import _installation_binding, _query_is_complete
from work.run_alliance_inbound_response import control_snapshot

# The targets exercise active and absent relationships and working diplomats.
CASES = (
    ("alliance", "offer_alliance", "SAV"),
    ("alliance", "dissolve_alliance", "PRO"),
    ("royal_marriage", "offer_royal_marriage", "SAV"),
    ("royal_marriage", "break_royal_ties", "PRO"),
    ("improve_relations", "improve_relations", "SAV"),
    ("improve_relations", "stop_improving_relations", "AMG"),
    ("spy_network", "build_spy_network", "SAV"),
    ("spy_network", "stop_building_spy_network", "BUR"),
    ("guarantee", "proclaim_guarantee", "SAV"),
    ("guarantee", "revoke_guarantee", "SAV"),
    ("support_independence", "support_independence", "HOL"),
    ("support_independence", "revoke_support_independence", "NOR"),
    ("military_access", "ask_military_access", "SAV"),
    ("military_access", "cancel_military_access", "SAV"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    args = parser.parse_args()
    installation = args.installation.resolve(strict=True)
    artifact = installation.parent / ("family-query-regression-" + uuid.uuid4().hex)
    artifact.mkdir()
    report = {"status": "running", "execute_call_count": 0, "queries": {}, "checks": {}}
    try:
        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session_id"] = session.session_id
        health = wait_runtime_ready(session, restore_minimized=False)
        before = control_snapshot(int(session.record["pid"]), artifact / "before-control.json")
        report["health"] = health
        report["before"] = before
        if (health.get("status") != "ready" or before.get("player_slot") != 189
                or before.get("paused_flag") != 1
                or before.get("date_raw") != args.expected_date_raw):
            raise RuntimeError("POR_PAUSED_EXPECTED_DATE_REQUIRED")
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            for family, action, recipient in CASES:
                query = api.inspect_diplomatic_action(action, "FRA", recipient)
                report["queries"][action] = {
                    "expected_family": family, "recipient": recipient,
                    "query": query, "native_query_complete": _query_is_complete(query, action),
                }
        after = control_snapshot(int(session.record["pid"]), artifact / "after-control.json")
        report["after"] = after
        report["checks"] = {
            "all_native_queries_complete": len(report["queries"]) == len(CASES)
            and all(q["native_query_complete"] for q in report["queries"].values()),
            "seven_distinct_families": len({f for f, _, _ in CASES}) == 7,
            "same_por_paused_date": all(before.get(k) == after.get(k)
                                         for k in ("player_slot", "paused_flag", "date_raw")),
            "source_build_matches_loaded_session": report["build_binding"].get(
                "installation_matches_build_manifest") is True,
            "no_execution_requests": report["execute_call_count"] == 0,
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
