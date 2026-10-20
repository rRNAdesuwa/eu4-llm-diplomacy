"""One read-only public batch for Humiliate, Show Strength and Force Religion native rules and combinations."""
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


_ACTOR = "FRA"
_DEFAULT_RECIPIENT = "ENG"


def _recipient_arg(value: str) -> str:
    """Normalize a target tag while keeping the historical ENG default."""

    value = value.upper()
    if (len(value) != 3 or not value.isascii() or not value.isalnum()
            or value == _ACTOR):
        raise argparse.ArgumentTypeError(
            "recipient must be a three-character canonical tag other than FRA")
    return value


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cases(war_id: str, recipient: str = _DEFAULT_RECIPIENT) -> list[dict]:
    def term(action: str, direction: str = "demand") -> dict:
        return {"action_id": action,
                "country": recipient if direction == "demand" else _ACTOR,
                "beneficiary": _ACTOR if direction == "demand" else recipient}
    definitions = []
    for action in ("humiliate_rival", "show_strength", "force_religion"):
        for direction in ("demand", "offer"):
            definitions.append((action + "-" + direction, action, direction, [term(action, direction)]))
    definitions.extend([
        ("money-humiliate", "humiliate_rival", "demand", [
            {"action_id": "demand_ducats", "amount": "1.0",
             "payer": recipient, "claimant": _ACTOR},
            term("humiliate_rival")]),
        ("concede-humiliate", "humiliate_rival", "demand", [
            {"action_id": "concede_defeat", "conceding_country": recipient,
             "beneficiary": _ACTOR},
            term("humiliate_rival")]),
        ("humiliate-strength", "humiliate_rival", "demand", [term("humiliate_rival"), term("show_strength")]),
    ])
    return [{"name": name, "action_id": action, "parameters": {"peace_context": {
        "war_id": war_id, "direction": direction, "terms": terms}}}
        for name, action, direction, terms in definitions]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recipient", type=_recipient_arg,
                        default=_DEFAULT_RECIPIENT,
                        help="议和目标国；默认 ENG，FRA 为固定 actor")
    parser.add_argument("--case", action="append",
                        choices=[row["name"] for row in cases("query")],
                        help="只运行指定查询；可重复指定，默认运行全部九项")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("OUTPUT_ALREADY_EXISTS")
    evidence = output.parent / (output.stem + "-evidence")
    evidence.mkdir(parents=True, exist_ok=False)
    session = ObserverSession(args.installation, game_exe())
    report = {"validator": Path(__file__).name, "status": "unknown",
              "installation": str(args.installation.resolve()), "session_id": session.session_id,
              "actor": _ACTOR, "recipient": args.recipient,
              "business_submission": False, "execute_call_count": 0,
              "advance_requested": False, "save_requested": False, "cases": []}
    log = session.directory / "control-probe.jsonl"
    start = log.stat().st_size
    try:
        report["health"] = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        if report["health"].get("status") != "ready":
            raise RuntimeError("SESSION_NOT_READY")
        # The reviewed war probe is target-aware through this bounded
        # environment input.  Other probes remain unchanged and read-only.
        import os
        os.environ["EU4_WAR_PAIR_RECIPIENT"] = args.recipient
        report["before"] = {spec.name: _run_probe(spec, session.record["pid"], evidence / "before" / (spec.name + ".json"))
                            for spec in PROBE_SPECS}
        with DurableJournal(evidence / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            discovery = api.inspect_diplomatic_action(
                "white_peace", _ACTOR, args.recipient, parameters={})
            write(evidence / "war-discovery.json", discovery)
            war_id = _single_discovered_war_id(
                discovery, _ACTOR, args.recipient)
            if war_id is None:
                raise RuntimeError("UNIQUE_WAR_REQUIRED")
            report["war_id"] = war_id
            selected_cases = [spec for spec in cases(war_id, args.recipient)
                              if not args.case or spec["name"] in args.case]
            report["requested_cases"] = [spec["name"] for spec in selected_cases]
            for spec in selected_cases:
                write(evidence / (spec["name"] + "-input.json"), spec)
                result = api.inspect_diplomatic_action(
                    spec["action_id"], _ACTOR, args.recipient,
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
                  if event.get("event") == "native_peace_special_offer_inspection"
                  and event.get("session_id") == session.session_id]
        before_control = _control_from_probe(report["before"]["control_state"])
        after_control = _control_from_probe(report["after"]["control_state"])
        expected_count = len(report["requested_cases"])
        semantic_matches = len(native) == len(report["cases"])
        for public, observed in zip(report["cases"], native):
            actual = public["parameters"].get("actual")
            terms = actual.get("peace_context", {}).get("terms", []) if isinstance(actual, dict) else []
            selections = [observed[key] for key in (
                "native_humiliate_rival", "native_show_strength", "native_force_religion")
                if isinstance(observed.get(key), dict)]
            selected = bool(selections) and all(row.get("parameters_matched") is True for row in selections)
            semantic_matches = semantic_matches and public["action_id"] == observed.get("action_id")
            if selected:
                for key, action in (("native_humiliate_rival", "humiliate_rival"),
                                    ("native_show_strength", "show_strength"),
                                    ("native_force_religion", "force_religion")):
                    row = observed.get(key)
                    if isinstance(row, dict):
                        semantic_matches = semantic_matches and any(
                            term.get("action_id") == action and term.get("country") == row.get("country")
                            and term.get("beneficiary") == row.get("beneficiary") for term in terms)
            if selected and observed.get("full_rules_complete") is True:
                allowed = all(row.get("rule_available") is True for row in selections) and all(
                    observed.get(key) is True for key in (
                        "native_validity", "common_action_gate", "initiation_gate", "native_wrapper_gate"))
                expected = "available" if allowed else "unavailable"
                semantic_matches = semantic_matches and public["legality"].get("status") == expected
            else:
                semantic_matches = semantic_matches and public["legality"].get("status") != "available"
        report["native_events"] = {"path": str(evidence / "native-events-slice.jsonl"),
                                   "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        report["checks"] = {
            "requested_public_cases": len(report["cases"]) == expected_count,
            "requested_native_queries": len(native) == expected_count,
            "native_copy_and_cleanup": len(native) == expected_count and all(
                e.get("object_unchanged") is True and e.get("cleanup_verified") is True
                and e.get("native_payload", {}).get("source_copy_equal") is True for e in native),
            "native_special_requested": len(native) == expected_count and all(
                any(isinstance(e.get(key), dict) and e[key].get("requested") is True
                    for key in ("native_humiliate_rival", "native_show_strength", "native_force_religion"))
                for e in native),
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
