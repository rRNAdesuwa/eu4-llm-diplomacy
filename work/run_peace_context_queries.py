"""Query native peace war contexts through the four-tool interface.

One paused boundary surrounds the batch. The operator does not submit any
peace offer, advance time, install a DLL, or save the game.
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
from work.run_royal_marriage_execution import (
    _installation_binding, _public_probe_records, _snapshots_complete,
)
from work.validate_alliance_reload import _control_summary, _run_snapshots


WAR_ID = re.compile(r"war_[0-9a-f]{16}_[0-9a-f]{8}\Z")
FORBIDDEN_PUBLIC_KEYS = frozenset({
    "pid", "session_id", "creation_filetime", "native_war_reference",
    "native_reference", "module_base", "vtable_rva", "dll_sha256",
})


def _public_context_contract(value: object, action: str, target: str) -> bool:
    if not isinstance(value, dict):
        return False
    if any(value.get(key) != wanted for key, wanted in (
        ("action_id", action), ("actor", "FRA"), ("recipient", target),
        ("phase", "initiate"), ("family", "peace"),
        ("context_discovery", True), ("query_complete", True),
        ("war_context_enumeration_complete", True), ("native_offer_inspected", False),
    )):
        return False
    wars = value.get("war_contexts")
    if not isinstance(wars, list) or len(wars) > 32:
        return False
    for row in wars:
        if (not isinstance(row, dict) or not isinstance(row.get("war_id"), str)
                or WAR_ID.fullmatch(row["war_id"]) is None
                or row.get("identity_scope") != "observer_session"
                or row.get("actor") != "FRA" or row.get("recipient") != target
                or row.get("pair_at_war") is not True):
            return False
    return True


def _has_private_fields(value: object) -> bool:
    if isinstance(value, dict):
        return bool(FORBIDDEN_PUBLIC_KEYS.intersection(value)) or any(
            _has_private_fields(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_private_fields(item) for item in value)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    args = parser.parse_args()
    installation = args.installation.resolve(strict=True)
    session = ObserverSession(installation, game_exe())
    artifact = _new_artifact(installation.parent, "peace-context-queries")
    report: dict = {
        "validator": Path(__file__).name, "artifact": str(artifact),
        "installation": str(installation), "status": "running",
        "actor": "FRA", "expected_date_raw": args.expected_date_raw,
        "execute_call_count": 0, "business_submission": False,
        "query_call_count": 0,
    }
    log = session.directory / "control-probe.jsonl"
    log_start = None
    try:
        health = wait_runtime_ready(session, restore_minimized=True)
        if health.get("status") != "ready":
            raise RuntimeError("PEACE_QUERY_SESSION_UNREADY")
        report.update(_installation_binding(installation))
        report["session"] = {key: session.record.get(key) for key in (
            "pid", "session_id", "experiment_id", "dll_sha256")}
        report["before"] = {}
        report["after"] = {}
        before = _run_snapshots(session, artifact / "before" / "probes")
        control_before = _control_summary(before["control_state"]["snapshot"])
        report["before"] = {
            "control": control_before, "health": session.health(),
            "probes": _public_probe_records(before),
        }
        if (control_before != {"date_raw": args.expected_date_raw,
                               "paused_flag": 1, "player_slot": 189}
                or not _snapshots_complete(before)):
            raise RuntimeError("PEACE_QUERY_BASELINE_UNAVAILABLE")
        log_start = log.stat().st_size
        cases = (
            ("white_eng", "white_peace", "ENG"),
            ("ducats_eng", "demand_ducats", "ENG"),
            ("province_tyr", "cede_province", "TYR"),
            ("white_bur", "white_peace", "BUR"),
            ("white_por", "white_peace", "POR"),
            ("white_eng_repeat", "white_peace", "ENG"),
        )
        queries: dict[str, dict] = {}
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            for name, action, target in cases:
                report["query_call_count"] += 1
                query = api.inspect_diplomatic_action(action, "FRA", target,
                                                     phase="initiate", parameters={})
                queries[name] = query
                _write_json(artifact / f"{name}.json", query)
        after = _run_snapshots(session, artifact / "after" / "probes")
        control_after = _control_summary(after["control_state"]["snapshot"])
        health_after = session.health()
        report["queries"] = queries
        report["after"] = {
            "control": control_after, "health": health_after,
            "probes": _public_probe_records(after),
        }
        ids = {name: [row["war_id"] for row in value.get("war_contexts", [])]
               for name, value in queries.items()}
        report["checks"] = {
            "public_context_contracts": all(_public_context_contract(queries[name], action, target)
                                            for name, action, target in cases),
            "eng_one_war": len(ids["white_eng"]) == 1,
            "same_war_across_terms": ids["white_eng"] == ids["ducats_eng"],
            "same_war_enemy_ally": ids["white_eng"] == ids["province_tyr"],
            "same_war_repeat": ids["white_eng"] == ids["white_eng_repeat"],
            "noncombatant_pairs_empty": not ids["white_bur"] and not ids["white_por"],
            "no_private_identifiers": not _has_private_fields(queries),
            "control_unchanged": control_before == control_after,
            "health_ready_after": health_after.get("status") == "ready",
            "four_snapshots_complete": _snapshots_complete(before) and _snapshots_complete(after),
            "independent_war_state_unchanged": before["war_state"]["snapshot"]["countries"]
                                             == after["war_state"]["snapshot"]["countries"],
            "no_business_submission": report["execute_call_count"] == 0,
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if isinstance(log_start, int):
            report["native_events"] = _copy_log_slice(log, log_start, artifact / "native-events-slice.jsonl")
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
