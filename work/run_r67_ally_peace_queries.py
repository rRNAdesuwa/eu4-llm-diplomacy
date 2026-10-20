"""Query the real beneficiaries and rules of ally-occupied peace provinces."""
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
from work.run_peace_consequence_queries import (
    _output_paths, _write_json, _copy_bounded_slice, _single_discovered_war_id,
    _has_private_fields,
)
from work.run_peace_concession_queries import _control_from_probe, _control_is_paused_por
from work.validate_alliance_queries import PROBE_SPECS, _run_probe


def raw_parent(path: Path, session: ObserverSession, date: int) -> dict:
    assert path.stat().st_size <= 4 * 1024 * 1024, "SLICE_TOO_LARGE"
    matches = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (row.get("event") == "native_peace_province_offer_inspection"
                and row.get("session_id") == session.session_id
                and row.get("date_raw") == date
                and row.get("actor") == "FRA" and row.get("recipient") == "BUR"):
            matches.append(row)
    assert len(matches) == 1, "UNIQUE_NATIVE_PARENT_REQUIRED"
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output, evidence = _output_paths(args.output)
    session = ObserverSession(args.installation.resolve(strict=True), game_exe())
    report = {"status": "running", "session_id": session.session_id,
              "installation": str(args.installation), "cases": [], "checks": {},
              "business_submission": False, "save_requested": False,
              "advance_requested": False, "restart_requested": False}
    try:
        health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        date = health["date_raw"]
        before = _control_from_probe(_run_probe(
            PROBE_SPECS[0], session.record["pid"], evidence / "before.json"))
        assert _control_is_paused_por(before, date), "BASELINE_NOT_PAUSED_POR"
        report["before"] = before
        with DurableJournal(evidence / "journal.sqlite3", session.experiment_id,
                            session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            discovery = api.inspect_diplomatic_action("white_peace", "FRA", "BUR", parameters={})
            war = _single_discovered_war_id(discovery, "FRA", "BUR")
            assert war, "WAR_DISCOVERY_FAILED"
            empty = {"peace_context": {"war_id": war, "direction": "demand", "terms": []}}
            candidates = api.inspect_diplomatic_action("cede_province", "FRA", "BUR", parameters=empty)
            _write_json(evidence / "candidates.json", candidates)
            rows = candidates.get("parameters", {}).get("candidates", [])
            beneficiary_by_id = {row["province_id"]: row["beneficiary"] for row in rows}
            report.update(war_id=war, candidate_beneficiaries=beneficiary_by_id)
            for name, province, beneficiary in (
                    ("actor_94_FRA", 94, "FRA"), ("subject_88_ORL", 88, "ORL"),
                    ("ally_193_SAV", 193, "SAV"), ("ally_91_SAV", 91, "SAV")):
                directory = evidence / "cases" / name
                directory.mkdir(parents=True, exist_ok=False)
                parameters = {"peace_context": {"war_id": war, "direction": "demand", "terms": [
                    {"action_id": "cede_province", "province_ids": [province], "beneficiary": beneficiary}]}}
                _write_json(directory / "input.json", parameters)
                log = session.directory / "control-probe.jsonl"
                start = log.stat().st_size
                result = api.inspect_diplomatic_action("cede_province", "FRA", "BUR", parameters=parameters)
                _write_json(directory / "public.json", result)
                meta = _copy_bounded_slice(log, start, directory / "native.jsonl")
                raw = raw_parent(directory / "native.jsonl", session, date)
                _write_json(directory / "native-event.json", raw)
                selection = {"war_id": war, "direction": "demand", "province_ids": [province],
                             "beneficiary": beneficiary}
                valid = ObserverSession._valid_native_peace_province_offer_inspection(
                    raw, "cede_province", "FRA", "BUR", "initiate", date, selection,
                    raw["query_id"], session.session_id, require_wrapper_rule=True)
                report["cases"].append({"name": name, "province_id": province,
                    "beneficiary": beneficiary, "native_beneficiary_matches": beneficiary_by_id.get(province) == beneficiary,
                    "native_validator": valid, "object_unchanged": raw.get("object_unchanged") is True,
                    "native_slice": meta, "native_event_path": str(directory / "native-event.json"),
                    "public_path": str(directory / "public.json"), "parameters": parameters,
                    "legality": result.get("legality"), "requested_terms_applied": result.get(
                        "peace_consequences", {}).get("requested_terms_applied"),
                    "private_fields_absent": not _has_private_fields(result)})
        after = _control_from_probe(_run_probe(
            PROBE_SPECS[0], session.record["pid"], evidence / "after.json"))
        report["after"] = after
        cases = report["cases"]
        report["checks"] = {"four_real_queries": len(cases) == 4,
            "all_native_parents_valid": all(case["native_validator"] for case in cases),
            "all_requested_beneficiaries_native": all(case["native_beneficiary_matches"] for case in cases),
            "all_objects_unchanged": all(case["object_unchanged"] for case in cases),
            "all_public_no_private_fields": all(case["private_fields_absent"] for case in cases),
            "third_country_selectable": any(case["beneficiary"] != "FRA"
                and case["legality"].get("status") == "available" for case in cases),
            "ally_unwilling_reason_observed": any(case["beneficiary"] == "SAV"
                and case["legality"].get("status") == "unavailable"
                and any(word in reason.get("text", "") for reason in case["legality"].get("reasons", [])
                        for word in ("不想", "不希望", "不愿", "does not want")) for case in cases),
            "paused_por_same_date": _control_is_paused_por(after, date) and before["date_raw"] == after["date_raw"],
            "no_business_submission": True}
        report["status"] = "passed" if all(report["checks"].values()) else "partial"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    _write_json(output, report)
    print(json.dumps({"status": report["status"], "report": str(output),
                      "checks": report["checks"]}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
