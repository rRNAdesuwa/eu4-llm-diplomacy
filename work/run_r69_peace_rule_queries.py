"""Batch native term justification and Release Nation net-OE previews."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from bridge.peace_consequences import validate_native_consequences, project_event_consequences
from bridge.peace_execution import normalize_peace_execution_parameters
from bridge.peace_country import COUNTRY_SELECTION_KEYS
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_inbound_response import control_snapshot
from work.run_peace_consequence_queries import _write_json, _copy_bounded_slice
from work.run_peace_empty_offer_queries import _single_discovered_war_id, _has_private_fields


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--installation", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--resume", type=Path, help="reuse retained cases and query only missing native observations")
    p.add_argument("--country-money", action="store_true", help="R70: require mixed money previews in both directions")
    args = p.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    session = ObserverSession(args.installation.resolve(strict=True), game_exe())
    log = session.directory / "control-probe.jsonl"
    report = {"status": "running", "session_id": session.session_id,
              "installation": str(args.installation.resolve()), "cases": [],
              "business_submission": False, "checks": {}}
    retained = {}
    if args.resume:
        source = json.loads(args.resume.read_text(encoding="utf-8"))
        assert source["session_id"] == session.session_id, "RESUME_SESSION_DIFFERS"
        retained = {row["name"]: row for row in source["cases"]}
        report["source_report"] = str(args.resume.resolve())
    report.update(live_query_count=0, reused_case_count=0)
    def persist():
        _write_json(output / "report.json", report)
    persist()
    try:
        report["health"] = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        before = control_snapshot(int(session.record["pid"]), output / "control-before.json")
        assert report["health"]["status"] == "ready" and before["paused_flag"] == 1 and before["player_slot"] == 189
        report["before"] = before
        with DurableJournal(output / "journal.sqlite3", session.experiment_id, session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            def query(name, action, parameters):
                directory = output / "cases" / name
                directory.mkdir(parents=True)
                previous = retained.get(name)
                previous_dir = Path(previous["public_path"]).parent if previous else None
                reuse = bool(previous_dir and (name == "war_discovery"
                    or (previous_dir / "native-event.json").is_file()))
                if reuse:
                    assert previous["parameters"] == parameters, "RESUMED_PARAMETERS_DIFFER"
                    public = json.loads((previous_dir / "public.json").read_text(encoding="utf-8"))
                    raw_path = previous_dir / "native-event.json"
                    raw = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.is_file() else None
                    raw_slice = copy.deepcopy(previous["native_slice"])
                    shutil.copyfile(previous_dir / "native.jsonl", directory / "native.jsonl")
                    if raw:
                        public["peace_consequences"] = project_event_consequences(raw, session.native_text_codec)
                        if raw.get("event") == "native_peace_combined_country_offer_query":
                            normalized = normalize_peace_execution_parameters(
                                action, "FRA", "BUR", "initiate", parameters)
                            fields = session._peace_execution_fields(normalized)
                            country_fields = session._peace_country_execution_fields(normalized, "FRA", "BUR")
                            assert fields is not None and country_fields is not None
                            selection = dict(zip(COUNTRY_SELECTION_KEYS, country_fields))
                            selection.update(action_id=action, war_id=fields[0], direction=fields[1],
                                             amount_raw=fields[2], term_mask=fields[-1] or raw["term_mask"])
                            assert session._valid_native_peace_combined_country_offer_query(
                                raw, action, "FRA", "BUR", "initiate", raw["date_raw"],
                                selection, raw["query_id"], session.session_id), "RETAINED_COUNTRY_EVENT_INVALID"
                            enriched = dict(raw)
                            enriched.update({key: selection[key] for key in COUNTRY_SELECTION_KEYS})
                            semantic = session._semantic_peace_combined_country_offer_query(
                                enriched, session.native_text_codec)
                            public = api._apply_peace_execution_inspection(public, semantic, normalized)
                    report["reused_case_count"] += 1
                else:
                    start = log.stat().st_size
                    public = api.inspect_diplomatic_action(action, "FRA", "BUR", parameters=parameters)
                    report["live_query_count"] += 1
                    raw_slice = _copy_bounded_slice(log, start, directory / "native.jsonl")
                    events = []
                    with (directory / "native.jsonl").open(encoding="utf-8") as stream:
                        for line in stream:
                            try:
                                event = json.loads(line)
                            except ValueError:
                                continue
                            if (event.get("session_id") == session.session_id
                                    and event.get("action_id") == action
                                    and "native_consequences" in event):
                                events.append(event)
                    raw = events[-1] if events else None
                _write_json(directory / "public.json", public)
                if raw:
                    _write_json(directory / "native-event.json", raw)
                consequences = public.get("peace_consequences") or {}
                legality = public.get("legality") or {}
                row = {"name": name, "action_id": action, "parameters": parameters,
                       "public_path": str(directory / "public.json"), "native_slice": raw_slice,
                       "raw_consequences_valid": bool(raw and validate_native_consequences(raw["native_consequences"])),
                       "object_unchanged": raw.get("object_unchanged") if raw else None,
                       "legality": legality, "diplomatic_power": consequences.get("diplomatic_power"),
                       "justification": consequences.get("justification"),
                       "overextension": consequences.get("overextension"),
                       "requested_terms_applied": consequences.get("requested_terms_applied"),
                       "public_native_query_supported": (public.get("interface_support") or {}).get("query")
                            == "native_peace_execution_inspection",
                       "private_fields_absent": not _has_private_fields(public)}
                report["cases"].append(row)
                persist()
                return public
            discovery = query("war_discovery", "white_peace", {})
            war = _single_discovered_war_id(discovery, "FRA", "BUR")
            assert war, "SINGLE_WAR_REQUIRED"
            report["war_id"] = war
            def context(direction, terms):
                return {"peace_context": {"war_id": war, "direction": direction, "terms": terms}}
            for direction in ("demand", "offer"):
                query(direction + "_white", "white_peace", context(direction, []))
                query(direction + "_money", "demand_ducats", context(direction, [{
                    "action_id": "demand_ducats", "amount": "1.0",
                    "payer": "BUR" if direction == "demand" else "FRA",
                    "claimant": "FRA" if direction == "demand" else "BUR"}]))
            for country in ("PIC", "HAI", "LUX"):
                query("release_" + country, "release_nation", context("demand", [{
                    "action_id": "release_nation", "country": country, "source": "BUR"}]))
            for province in (88, 91, 193):
                query("cede_FRA_" + str(province), "cede_province", context("demand", [{
                    "action_id": "cede_province", "province_ids": [province], "beneficiary": "FRA"}]))
            offer = query("release_offer_discovery", "release_nation", context("offer", []))
            candidates = ((offer.get("parameters") or {}).get("candidates") or {}).get("release_nation", {}).get("candidates", [])
            candidate = next((c for c in candidates if c.get("record_complete") is True and c.get("source") == "FRA"), None)
            if candidate:
                query("release_offer_selected", "release_nation", context("offer", [{
                    "action_id": "release_nation", "country": candidate["country"], "source": "FRA"}]))
            query("release_PIC_money", "release_nation", context("demand", [
                {"action_id": "release_nation", "country": "PIC", "source": "BUR"},
                {"action_id": "demand_ducats", "amount": "1.0", "payer": "BUR", "claimant": "FRA"}]))
            if args.country_money:
                assert candidate, "OFFER_COUNTRY_CANDIDATE_REQUIRED"
                query("release_offer_money", "release_nation", context("offer", [
                    {"action_id": "release_nation", "country": candidate["country"], "source": "FRA"},
                    {"action_id": "demand_ducats", "amount": "1.0", "payer": "FRA", "claimant": "BUR"}]))
                query("annex_BUR_release_PIC_money", "release_nation", context("demand", [
                    {"action_id": "release_nation", "country": "PIC", "source": "BUR"},
                    {"action_id": "full_annexation", "country": "BUR", "beneficiary": "FRA"},
                    {"action_id": "demand_ducats", "amount": "1.0", "payer": "BUR", "claimant": "FRA"}]))
        after = control_snapshot(int(session.record["pid"]), output / "control-after.json")
        report["after"] = after
        cases = report["cases"][1:]
        mixed = next(c for c in cases if c["name"] == "release_PIC_money")
        mixed_reasons = mixed["legality"].get("reasons", [])
        mixed_unsupported = any(r.get("code") ==
            "NATIVE_PEACE_EXECUTION_MIXED_INSPECTION_UNAVAILABLE" for r in mixed_reasons)
        supported = [c for c in cases if c is not mixed] if mixed_unsupported else cases
        report["scope"] = "supported_previews_and_explicit_mixed_protocol_boundary"
        report["mixed_country_money_preview_supported"] = not mixed_unsupported
        report["unsupported_combinations"] = ([{
            "case": mixed["name"], "reason_code":
                "NATIVE_PEACE_EXECUTION_MIXED_INSPECTION_UNAVAILABLE",
            "next": "extend_native_country_query_and_execution_in_next_related_build",
        }] if mixed_unsupported else [])
        release = next(c for c in cases if c["name"] == "release_PIC")
        countries = {r["country"]: r for r in (release.get("overextension") or {}).get("countries", [])}
        statuses = {t["status"] for c in cases for t in (c.get("justification") or {}).get("terms", []) if t.get("selected") is True}
        report["checks"] = {
            "same_paused_por_date": all(before[k] == after[k] for k in ("date_raw", "paused_flag", "player_slot")),
            "all_supported_raw_consequences_valid": all(c["raw_consequences_valid"] for c in supported),
            "all_supported_offer_objects_unchanged": all(c["object_unchanged"] is True for c in supported),
            "all_public_without_private_fields": all(c["private_fields_absent"] for c in report["cases"]),
            "all_supported_previews_have_justification": all(isinstance(c["justification"], dict) for c in supported),
            "all_supported_public_native_queries_accepted": all(c["public_native_query_supported"] for c in supported),
            "mixed_boundary_explicit_or_preview_valid": (
                (mixed_unsupported and mixed["native_slice"]["bytes"] == 0)
                or (mixed["raw_consequences_valid"] and mixed["requested_terms_applied"] is True)),
            "release_PIC_applied": release.get("requested_terms_applied") is True,
            "release_PIC_net_complete": (release.get("overextension") or {}).get("complete") is True,
            "BUR_loses_88": 88 in countries.get("BUR", {}).get("lost_province_ids", []),
            "PIC_gains_88": 88 in countries.get("PIC", {}).get("gained_province_ids", []),
            "BUR_OE_decreases": countries.get("BUR", {}).get("delta_raw", 0) < 0,
            "selected_justified_observed": "justified" in statuses,
            "selected_unjustified_observed": "unjustified" in statuses,
        }
        if args.country_money:
            report["checks"]["new_mixed_protocol_supported"] = not mixed_unsupported
            for name in ("release_PIC_money", "release_offer_money"):
                row = next(c for c in cases if c["name"] == name)
                report["checks"][name + "_parameters_applied"] = row["requested_terms_applied"] is True
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
    persist()
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]),
                      "checks": report["checks"], "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
