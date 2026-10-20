"""One read-only public batch for Annul Treaties candidates, selections and native combinations."""
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
from work.run_peace_empty_offer_queries import _has_private_fields, _single_discovered_war_id
from work.run_peace_concession_queries import _control_from_probe, _control_is_paused_por
from work.validate_alliance_queries import PROBE_SPECS, _run_probe


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cases(war_id: str) -> list[dict]:
    def term(country: str, partners: list[str]) -> dict:
        return {"action_id": "annul_treaties", "country": country, "treaty_partners": partners}
    definitions = [
        ("demand-candidates", "annul_treaties", "demand", []),
        ("offer-candidates", "annul_treaties", "offer", []),
        ("demand-single", "annul_treaties", "demand", [term("ENG", ["GEL"])]),
        ("demand-multiple", "annul_treaties", "demand", [term("ENG", ["GEL", "SCO"])]),
        ("money-annul", "demand_ducats", "demand", [
            {"action_id": "demand_ducats", "amount": "1.0", "payer": "ENG", "claimant": "FRA"}, term("ENG", ["GEL"])]),
        ("concede-annul", "concede_defeat", "demand", [
            {"action_id": "concede_defeat", "conceding_country": "ENG", "beneficiary": "FRA"}, term("ENG", ["GEL"])]),
        ("wrong-country", "annul_treaties", "demand", [term("FRA", ["GEL"])]),
        ("offer-single", "annul_treaties", "offer", [term("FRA", ["GEN"])]),
        ("offer-multiple", "annul_treaties", "offer", [term("FRA", ["GEN", "PAP"])]),
    ]
    return [{"name": name, "action_id": action, "parameters": {"peace_context": {
        "war_id": war_id, "direction": direction, "terms": terms}}}
        for name, action, direction, terms in definitions]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("OUTPUT_ALREADY_EXISTS")
    evidence = output.parent / (output.stem + "-evidence")
    evidence.mkdir(parents=True, exist_ok=False)
    session = ObserverSession(args.installation, game_exe())
    report = {"validator": Path(__file__).name, "status": "unknown",
              "installation": str(args.installation.resolve()), "session_id": session.session_id,
              "business_submission": False, "execute_call_count": 0,
              "advance_requested": False, "save_requested": False, "cases": []}
    log = session.directory / "control-probe.jsonl"
    start = log.stat().st_size
    try:
        report["health"] = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        if report["health"].get("status") != "ready":
            raise RuntimeError("SESSION_NOT_READY")
        report["before"] = {spec.name: _run_probe(spec, session.record["pid"], evidence / "before" / (spec.name + ".json"))
                            for spec in PROBE_SPECS}
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
                write(evidence / (spec["name"] + "-input.json"), spec)
                result = api.inspect_diplomatic_action(spec["action_id"], "FRA", "ENG",
                                                       parameters=spec["parameters"])
                write(evidence / (spec["name"] + ".json"), result)
                report["cases"].append({"name": spec["name"], "action_id": spec["action_id"],
                                        "legality": result.get("legality"),
                                        "interface_support": result.get("interface_support"),
                                        "parameters": result.get("parameters"),
                                        "acceptance": result.get("acceptance"),
                                        "private_fields_absent": not _has_private_fields(result)})
        report["after"] = {spec.name: _run_probe(spec, session.record["pid"], evidence / "after" / (spec.name + ".json"))
                           for spec in PROBE_SPECS}
        available = log.stat().st_size - start
        if not 0 <= available <= 4 * 1024 * 1024:
            raise RuntimeError("NATIVE_EVENT_SLICE_LIMIT")
        with log.open("rb") as stream:
            stream.seek(start)
            raw = stream.read(available)
        (evidence / "native-events-slice.jsonl").write_bytes(raw)
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
        native = [event for event in events
                  if event.get("event") == "native_peace_annul_treaties_offer_inspection"
                  and event.get("session_id") == session.session_id]
        before_control = _control_from_probe(report["before"]["control_state"])
        after_control = _control_from_probe(report["after"]["control_state"])
        semantic_matches = len(native) == len(report["cases"])
        for public, observed in zip(report["cases"], native):
            selection = observed.get("native_annul_treaties", {})
            actual = public["parameters"].get("actual")
            terms = actual.get("peace_context", {}).get("terms", []) if isinstance(actual, dict) else []
            matched = any(term.get("action_id") == "annul_treaties"
                          and term.get("country") == selection.get("country")
                          and term.get("treaty_partners") == selection.get("treaty_partners") for term in terms)
            semantic_matches = semantic_matches and public["action_id"] == observed.get("action_id")
            if selection.get("parameters_matched") is True:
                semantic_matches = semantic_matches and matched
                expected = "available" if selection.get("rule_available") is True else "unavailable"
                semantic_matches = semantic_matches and public["legality"].get("status") == expected
            else:
                semantic_matches = semantic_matches and public["legality"].get("status") != "available"
        report["native_events"] = {"path": str(evidence / "native-events-slice.jsonl"),
                                   "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        report["checks"] = {
            "nine_public_cases": len(report["cases"]) == 9,
            "nine_native_queries": len(native) == 9,
            "native_copy_and_cleanup": len(native) == 9 and all(
                e.get("object_unchanged") is True and e.get("cleanup_verified") is True
                and e.get("native_payload", {}).get("source_copy_equal") is True for e in native),
            "native_annul_requested": len(native) == 9 and all(
                e.get("native_annul_treaties", {}).get("requested") is True for e in native),
            "public_private_fields_absent": all(c["private_fields_absent"] for c in report["cases"]),
            "control_unchanged": before_control == after_control and _control_is_paused_por(
                after_control, report["health"].get("date_raw")),
            "public_selection_matches_native": semantic_matches,
            "public_states_defined": all(c["legality"].get("status") in
                                         ("available", "unavailable", "unknown") for c in report["cases"]),
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "text": str(error)}
    write(output, report)
    print(json.dumps({"status": report["status"], "report": str(output)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
