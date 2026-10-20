"""Run a paused public-query batch for native Return/Revoke Core terms."""
from __future__ import annotations

import argparse
import hashlib
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
from work.run_peace_concession_queries import _control_from_probe, _control_is_paused_por
from work.run_peace_empty_offer_queries import _has_private_fields, _single_discovered_war_id
from work.validate_alliance_queries import PROBE_SPECS, _run_probe


def cases(war_id: str) -> list[dict]:
    specs = [
        ("revoke-discover-demand", "revoke_core", "demand", [], None, "discovery"),
        ("revoke-demand-175-eng", "revoke_core", "demand", [175], "ENG", "selected"),
        ("revoke-discover-offer", "revoke_core", "offer", [], None, "discovery"),
        ("revoke-offer-167-fra", "revoke_core", "offer", [167], "FRA", "selected"),
        ("revoke-offer-167-168-fra", "revoke_core", "offer", [167, 168], "FRA", "selected"),
        ("revoke-wrong-core-owner", "revoke_core", "demand", [175], "FRA", "absent"),
        ("revoke-absent-province", "revoke_core", "demand", [2147483647], "ENG", "absent"),
        ("revoke-partial-match", "revoke_core", "demand", [175, 173], "ENG", "absent"),
        ("return-discover-demand", "return_core", "demand", [], None, "discovery"),
        ("return-demand-173-amg", "return_core", "demand", [173], "AMG", "selected"),
        ("return-demand-177-pro", "return_core", "demand", [177], "PRO", "selected"),
        ("return-wrong-core-owner", "return_core", "demand", [173], "FRA", "absent"),
        ("return-discover-offer", "return_core", "offer", [], None, "discovery"),
        ("return-offer-204-pro", "return_core", "offer", [204], "PRO", "selected"),
    ]
    rows = []
    for name, action, direction, ids, owner, expectation in specs:
        terms = [{"action_id": action, "province_ids": ids, "core_owner": owner}] if ids else []
        rows.append({"name": name, "action_id": action, "expected_kind": expectation,
                     "parameters": {"peace_context": {"war_id": war_id, "direction": direction, "terms": terms}}})
    return rows


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", choices=[row["name"] for row in cases("query")])
    args = parser.parse_args()
    output = args.output.resolve()
    evidence = output.parent / (output.stem + "-evidence")
    if output.exists() or evidence.exists():
        raise SystemExit("OUTPUT_ALREADY_EXISTS")
    evidence.mkdir(parents=True)
    report = {"validator": Path(__file__).name, "status": "running", "cases": [],
              "installation": str(args.installation.resolve()), "business_submission": False,
              "execute_call_count": 0, "advance_requested": False, "save_requested": False}
    session = ObserverSession(args.installation, game_exe())
    report["session_id"] = session.session_id
    log = session.directory / "control-probe.jsonl"
    start = log.stat().st_size
    try:
        health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        report["health"] = health
        if health.get("status") != "ready":
            raise RuntimeError("SESSION_NOT_READY")
        before_probe = _run_probe(PROBE_SPECS[0], session.record["pid"], evidence / "before-control.json")
        before = _control_from_probe(before_probe)
        report["before"] = before
        if not _control_is_paused_por(before, health.get("date_raw")):
            raise RuntimeError("PAUSED_POR_CONTEXT_REQUIRED")
        with DurableJournal(evidence / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            discovery = api.inspect_diplomatic_action("white_peace", "FRA", "ENG", parameters={})
            write(evidence / "war-discovery.json", discovery)
            war_id = _single_discovered_war_id(discovery, "FRA", "ENG")
            if war_id is None:
                raise RuntimeError("UNIQUE_WAR_REQUIRED")
            report["war_id"] = war_id
            for spec in cases(war_id):
                if args.case and spec["name"] not in args.case:
                    continue
                write(evidence / (spec["name"] + "-input.json"), spec)
                result = api.inspect_diplomatic_action(spec["action_id"], "FRA", "ENG", parameters=spec["parameters"])
                write(evidence / (spec["name"] + ".json"), result)
                report["cases"].append({"name": spec["name"], "action_id": spec["action_id"],
                    "expected_kind": spec["expected_kind"], "legality": result.get("legality"),
                    "query_complete": result.get("query_complete"), "acceptance": result.get("acceptance"),
                    "costs": result.get("costs"),
                    "native_core_terms": result.get("native_core_terms"),
                    "private_fields_absent": not _has_private_fields(result)})
                if not isinstance(result.get("native_core_terms"), dict):
                    raise RuntimeError("CORE_QUERY_NATIVE_RESULT_MISSING")
        after_probe = _run_probe(PROBE_SPECS[0], session.record["pid"], evidence / "after-control.json")
        after = _control_from_probe(after_probe)
        report["after"] = after
        checks = {"paused_player_and_date_unchanged": before == after and _control_is_paused_por(after, before["date_raw"])}
        for row in report["cases"]:
            prefix = row["name"]
            checks[prefix + "_public_projection"] = row["private_fields_absent"]
            checks[prefix + "_native_metadata_present"] = isinstance(row["native_core_terms"], dict)
            legality = (row["legality"] or {}).get("status")
            if row["expected_kind"] == "discovery":
                checks[prefix + "_requires_selection"] = legality == "unknown"
            elif row["expected_kind"] == "absent":
                checks[prefix + "_native_absence"] = legality == "unavailable"
                core = row["native_core_terms"] or {}
                checks[prefix + "_no_partial_selection"] = (
                    core.get("selection_applied") is False
                    and core.get("selected_term_count") == 0)
            else:
                checks[prefix + "_selected_native_legal"] = legality == "available"
                core = row["native_core_terms"] or {}
                checks[prefix + "_requested_selection_matched"] = core.get("parameters_matched") is True
                acceptance = row["acceptance"] or {}
                checks[prefix + "_native_acceptance_exposed"] = (
                    type(acceptance.get("native_total")) is int
                    and bool(acceptance.get("items"))
                    and acceptance.get("details_complete") is True)
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}:{error}")
    finally:
        length = log.stat().st_size - start
        if 0 <= length <= 4 * 1024 * 1024:
            with log.open("rb") as stream:
                stream.seek(start)
                raw = stream.read(length)
            (evidence / "native-events-slice.jsonl").write_bytes(raw)
            report["native_event_slice"] = {"bytes": length, "sha256": hashlib.sha256(raw).hexdigest()}
        else:
            report.update(status="failed", slice_error="BOUNDED_NATIVE_EVENT_SLICE_EXCEEDED")
        write(output, report)
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]), "output": str(output),
                      "failed": [key for key, value in report.get("checks", {}).items() if not value]}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
