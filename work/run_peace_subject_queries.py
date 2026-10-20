"""Query release/transfer subject terms together in one paused native session."""
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

ACTIONS = ("release_subject", "transfer_subject")


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parameters(war_id: str, action: str, direction: str, country: str | None) -> dict:
    terms = [] if country is None else [{"action_id": action, "country": country}]
    return {"peace_context": {"war_id": war_id, "direction": direction, "terms": terms}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    evidence = output.parent / (output.stem + "-evidence")
    if output.exists() or evidence.exists():
        raise SystemExit("OUTPUT_ALREADY_EXISTS")
    evidence.mkdir(parents=True)
    session = ObserverSession(args.installation, game_exe())
    report = {"status": "running", "session_id": session.session_id,
              "installation": str(args.installation.resolve()), "cases": [],
              "execute_call_count": 0, "advance_requested": False,
              "save_requested": False, "save_reload_validation": False}
    log = session.directory / "control-probe.jsonl"
    start = log.stat().st_size
    checks = {}
    try:
        health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        report["health"] = health
        if health.get("status") != "ready":
            raise RuntimeError("SESSION_NOT_READY")
        before = _control_from_probe(_run_probe(PROBE_SPECS[0], session.record["pid"],
                                                evidence / "before-control.json"))
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

            def inspect(action, direction, country, kind):
                name = f"{action}-{direction}-{country or 'discover'}"
                params = parameters(war_id, action, direction, country)
                write(evidence / (name + "-input.json"), params)
                result = api.inspect_diplomatic_action(action, "FRA", "ENG", parameters=params)
                write(evidence / (name + ".json"), result)
                native = result.get("native_subject_terms")
                row = {"name": name, "kind": kind, "action_id": action,
                       "direction": direction, "country": country,
                       "legality": result.get("legality"),
                       "acceptance": result.get("acceptance"), "costs": result.get("costs"),
                       "native_subject_terms": native,
                       "private_fields_absent": not _has_private_fields(result)}
                report["cases"].append(row)
                write(output, report)
                checks[name + "_public_projection"] = row["private_fields_absent"]
                checks[name + "_native_metadata"] = isinstance(native, dict)
                if not isinstance(native, dict):
                    raise RuntimeError("SUBJECT_QUERY_NATIVE_RESULT_MISSING")
                status = (row["legality"] or {}).get("status")
                checks[name + "_complete_enumeration"] = native.get("candidate_enumeration_complete") is True
                if kind == "discovery":
                    checks[name + "_requires_selection"] = status == "unknown"
                    checks[name + "_no_selection"] = native.get("selected_term_count") == 0
                elif kind == "absent":
                    checks[name + "_native_absence"] = status == "unavailable"
                    checks[name + "_no_selection"] = (
                        native.get("selection_applied") is False
                        and native.get("selected_term_count") == 0)
                else:
                    checks[name + "_native_rules_decide"] = status in {"available", "unavailable"}
                    checks[name + "_selected_copy_matches"] = (
                        native.get("parameters_matched") is True
                        and native.get("action_copy_matched") is True
                        and native.get("selected_term_count") == 1)
                    checks[name + "_native_cost"] = native.get("selection_delta_available") is True
                    if status == "available":
                        acceptance = row["acceptance"] or {}
                        checks[name + "_acceptance_factors"] = (
                            type(acceptance.get("native_total")) is int
                            and bool(acceptance.get("items"))
                            and acceptance.get("details_complete") is True)
                return native

            for action in ACTIONS:
                for direction in ("demand", "offer"):
                    native = inspect(action, direction, None, "discovery")
                    countries = [row.get("country") for row in native.get("candidates", [])
                                 if row.get("record_complete") is True]
                    preferred = "TYR" if direction == "demand" else "AUV"
                    selected = preferred if preferred in countries else next(iter(countries), None)
                    if selected:
                        inspect(action, direction, selected, "selected")
                    absent = next(tag for tag in ("FRA", "ENG", "POR", "JAP") if tag not in countries)
                    inspect(action, direction, absent, "absent")
        after = _control_from_probe(_run_probe(PROBE_SPECS[0], session.record["pid"],
                                               evidence / "after-control.json"))
        report["after"] = after
        checks["paused_player_and_date_unchanged"] = before == after and _control_is_paused_por(after, before["date_raw"])
        report["status"] = "passed" if all(checks.values()) else "failed"
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}:{error}")
    finally:
        report["checks"] = checks
        length = log.stat().st_size - start
        if 0 <= length <= 8 * 1024 * 1024:
            with log.open("rb") as stream:
                stream.seek(start)
                raw = stream.read(length)
            (evidence / "native-events-slice.jsonl").write_bytes(raw)
            report["native_event_slice"] = {"bytes": length, "sha256": hashlib.sha256(raw).hexdigest()}
        else:
            report.update(status="failed", slice_error="BOUNDED_NATIVE_EVENT_SLICE_EXCEEDED")
        write(output, report)
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]),
                      "failed": [key for key, value in checks.items() if not value],
                      "error": report.get("error"), "output": str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
