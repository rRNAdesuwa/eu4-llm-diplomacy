"""Query the five country-level peace families in one paused session."""
from __future__ import annotations

import argparse
import hashlib
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
from work.run_peace_concession_queries import _control_from_probe, _control_is_paused_por
from work.run_peace_empty_offer_queries import _has_private_fields, _single_discovered_war_id
from work.validate_alliance_queries import PROBE_SPECS, _run_probe

ACTIONS = ("release_nation", "force_vassalization", "form_personal_union",
           "grant_independence", "full_annexation")


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recipient", default="ENG", type=lambda tag: tag.upper())
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Z0-9]{3}", args.recipient) or args.recipient == "FRA":
        raise SystemExit("RECIPIENT_INVALID")
    output = args.output.resolve()
    evidence = output.parent / (output.stem + "-evidence")
    if output.exists() or evidence.exists():
        raise SystemExit("OUTPUT_ALREADY_EXISTS")
    evidence.mkdir(parents=True)
    session = ObserverSession(args.installation, game_exe())
    report = {"status": "running", "installation": str(args.installation.resolve()),
              "session_id": session.session_id, "cases": [], "execute_call_count": 0,
              "advance_requested": False, "save_requested": False,
              "save_reload_validation": False}
    log = session.directory / "control-probe.jsonl"
    start = log.stat().st_size
    checks = {}
    try:
        health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
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
            discovery = api.inspect_diplomatic_action("white_peace", "FRA", args.recipient, parameters={})
            write(evidence / "war-discovery.json", discovery)
            war_id = _single_discovered_war_id(discovery, "FRA", args.recipient)
            if war_id is None:
                raise RuntimeError("UNIQUE_WAR_REQUIRED")
            report["war_id"] = war_id

            def inspect(action, direction, terms, label):
                name = f"{action}-{direction}-{label}"
                parameters = {"peace_context": {"war_id": war_id, "direction": direction, "terms": terms}}
                write(evidence / (name + "-input.json"), parameters)
                result = api.inspect_diplomatic_action(action, "FRA", args.recipient, parameters=parameters)
                write(evidence / (name + ".json"), result)
                native = result.get("native_annexation") if action == "full_annexation" else (
                    result.get("native_country_terms") or {}).get(action)
                row = {"name": name, "parameters": parameters, "legality": result.get("legality"),
                       "costs": result.get("costs"), "acceptance": result.get("acceptance"),
                       "native": native, "selected_rules": result.get("native_selected_rules")}
                report["cases"].append(row)
                checks[name + "_public"] = not _has_private_fields(result)
                checks[name + "_native_record"] = isinstance(native, dict)
                if isinstance(native, dict):
                    checks[name + "_enumerated"] = native.get("candidate_enumeration_complete") is True
                    if not terms:
                        checks[name + "_discovery_did_not_select"] = native.get("selection_requested") is False
                    elif native.get("selection_applied") is True:
                        checks[name + "_copy"] = native.get("action_copy_matched") is True
                        checks[name + "_rules_observed"] = (row["selected_rules"] or {}).get("complete") is True
                    else:
                        checks[name + "_absence_reported"] = (row["legality"] or {}).get("status") == "unavailable"
                write(output, report)
                return native

            for action in ACTIONS:
                for direction in ("demand", "offer"):
                    native = inspect(action, direction, [], "discover")
                    if not isinstance(native, dict):
                        continue
                    rows = [row for row in native.get("candidates", []) if isinstance(row, dict)]
                    if action == "grant_independence":
                        inspect(action, direction, [{"action_id": action}], "selected")
                    elif action == "full_annexation":
                        owners = {row.get("owner") for row in rows if row.get("readcomplete") is True}
                        claimant = "FRA" if direction == "demand" else args.recipient
                        candidates = [tag for tag in ("UTR", "TYR", "AUV", "AMG", args.recipient, "FRA")
                                      if tag in owners and tag != claimant]
                        for country in candidates[:2]:
                            inspect(action, direction, [{"action_id": action, "country": country}], country)
                    else:
                        rows = [row for row in rows if row.get("record_complete") is True]
                        rows.sort(key=lambda row: (row.get("country") not in ("FLY", "ORD"),
                                                   row.get("country", ""), row.get("source", "")))
                        if rows:
                            term = {"action_id": action, "country": rows[0]["country"]}
                            if action == "release_nation":
                                term["source"] = rows[0]["source"]
                            inspect(action, direction, [term], term["country"])
        after = _control_from_probe(_run_probe(PROBE_SPECS[0], session.record["pid"],
                                               evidence / "after-control.json"))
        report["after"] = after
        checks["paused_player_and_date_unchanged"] = before == after
        report["status"] = "passed" if all(checks.values()) else "failed"
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}:{error}")
    finally:
        report["checks"] = checks
        length = log.stat().st_size - start
        if 0 <= length <= 16 * 1024 * 1024:
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
