"""Run a bounded live Declare War force-query batch in one paused session.

The runner is query-only.  It keeps the public projection and the native
inspection event at the same control-log offset so a later reviewer can
replay the force contract without starting another game process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.declarewar_forces import (  # noqa: E402
    project_declare_war_forces,
    valid_declare_war_forces,
)
from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_declarewar_participants_queries import (  # noqa: E402
    _ACTOR,
    _PHASE,
    _CB_RE,
    _TAG_RE,
    _header,
    _has_private_fields,
    _native_legality,
    _normalize_recipients,
    _parse_events,
    _participant_rows,
    _participant_view,
    _selection_parameters,
    _side,
    _tag,
)
from work.run_peace_concession_queries import (  # noqa: E402
    _control_from_probe,
    _control_is_paused_por,
)
from work.validate_alliance_queries import PROBE_SPECS, _run_probe  # noqa: E402


_DEFAULT_RECIPIENTS = ("ENG", "BUR", "MOR")
_SLICE_LIMIT = 4 * 1024 * 1024
_MAX_COUNTRIES = 128
_FORCE_TOP_FIELDS = frozenset({
    "source", "complete", "attackers", "defenders",
})


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _safe_name(value: object) -> str:
    value = str(value)
    return "".join(char if char.isalnum() or char in "._-" else "_"
                   for char in value)


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _public_force_side(value: object) -> tuple[bool, dict[str, object]]:
    if not isinstance(value, dict):
        return False, {"reason": "SIDE_NOT_OBJECT"}
    countries = value.get("countries")
    deployed = value.get("deployed")
    reserve = value.get("reserve_manpower")
    if (not isinstance(countries, list) or len(countries) > _MAX_COUNTRIES
            or any(not isinstance(tag, str) or _TAG_RE.fullmatch(tag) is None
                   for tag in countries)
            or len(set(countries)) != len(countries)):
        return False, {"reason": "COUNTRY_LIST_INVALID", "countries": countries}
    if not isinstance(deployed, dict) or not isinstance(reserve, dict):
        return False, {"reason": "UNIT_BLOCK_MISSING"}
    unit_fields = ("infantry", "cavalry", "artillery", "total")
    if (deployed.get("unit") != "men"
            or any(not _nonnegative_int(deployed.get(field))
                   for field in unit_fields)
            or deployed.get("total") != sum(
                int(deployed.get(field, -1)) for field in unit_fields[:3])):
        return False, {
            "reason": "UNIT_TOTAL_INVALID",
            "deployed": deployed,
        }
    if (reserve.get("unit") != "men"
            or not _nonnegative_int(reserve.get("amount"))):
        return False, {"reason": "RESERVE_INVALID", "reserve": reserve}
    if (not isinstance(value.get("scope_complete"), bool)
            or not isinstance(deployed.get("complete"), bool)
            or not isinstance(reserve.get("complete"), bool)):
        return False, {"reason": "COMPLETENESS_FLAGS_INVALID"}
    return True, {
        "countries": list(countries),
        "deployed_total": deployed.get("total"),
        "deployed_complete": deployed.get("complete"),
        "reserve_complete": reserve.get("complete"),
        "scope_complete": value.get("scope_complete"),
    }


def _public_force_contract(result: object, actor: str,
                           recipient: str) -> tuple[bool, dict[str, object]]:
    if not isinstance(result, dict):
        return False, {"reason": "RESULT_NOT_OBJECT"}
    if _has_private_fields(result):
        return False, {"reason": "PRIVATE_PUBLIC_FIELD"}
    forces = result.get("forces")
    if not isinstance(forces, dict) or not _FORCE_TOP_FIELDS.issubset(forces):
        return False, {"reason": "FORCES_MISSING"}
    if forces.get("source") != "native_declare_war_dialog":
        return False, {"reason": "FORCE_SOURCE_INVALID", "source": forces.get("source")}
    if not isinstance(forces.get("complete"), bool):
        return False, {"reason": "FORCE_COMPLETE_INVALID"}
    attacker_ok, attacker_detail = _public_force_side(forces.get("attackers"))
    defender_ok, defender_detail = _public_force_side(forces.get("defenders"))
    if not attacker_ok or not defender_ok:
        return False, {"reason": "SIDE_INVALID", "attackers": attacker_detail,
                       "defenders": defender_detail}
    attackers = forces["attackers"]
    defenders = forces["defenders"]
    attacker_tags = set(attackers["countries"])
    defender_tags = set(defenders["countries"])
    if attacker_tags.intersection(defender_tags):
        return False, {"reason": "COUNTRY_CROSSES_SIDES",
                       "overlap": sorted(attacker_tags.intersection(defender_tags))}
    if actor not in attacker_tags or recipient not in defender_tags:
        return False, {"reason": "ACTION_SEEDS_MISSING",
                       "actor": actor, "recipient": recipient,
                       "attackers": sorted(attacker_tags),
                       "defenders": sorted(defender_tags)}
    return True, {
        "complete": forces.get("complete"),
        "attackers": attacker_detail,
        "defenders": defender_detail,
    }


def _first_cb_conquest(result: object) -> dict | None:
    if not isinstance(result, dict):
        return None
    rows = result.get("candidates")
    if not isinstance(rows, list):
        parameters = result.get("parameters")
        rows = parameters.get("candidates") if isinstance(parameters, dict) else None
    usable: list[tuple[int, int, str, dict]] = []
    for index, row in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(row, dict):
            continue
        cb = row.get("casus_belli_key")
        province = row.get("target_province_id")
        beneficiary = row.get("beneficiary_tag")
        if (cb != "cb_conquest" or not isinstance(cb, str)
                or _CB_RE.fullmatch(cb) is None
                or row.get("casus_belli_key_verified", True) is not True
                or isinstance(province, bool) or not isinstance(province, int)
                or province <= 0
                or row.get("province_identifier_verified", True) is not True
                or not isinstance(beneficiary, str)
                or (beneficiary != "---" and
                    _TAG_RE.fullmatch(beneficiary) is None)
                or row.get("beneficiary_identifier_verified", True) is not True):
            continue
        usable.append((province, index, beneficiary, row))
    usable.sort(key=lambda item: (item[0], item[2], item[1]))
    if not usable:
        return None
    return usable[0][3]


def _candidate_parameters(row: dict) -> dict:
    return _selection_parameters(
        "cb_conquest", int(row["target_province_id"]),
        str(row["beneficiary_tag"]))


def _selection_base_label(selection_kind: str, candidate: dict | None) -> str:
    if selection_kind == "no_casus_belli":
        return "no-casus-belli"
    if isinstance(candidate, dict):
        return (f"cb-conquest-{candidate['target_province_id']}-"
                f"{candidate['beneficiary_tag']}")
    return selection_kind


def _find_sav(view: dict | None) -> dict | None:
    for row in _participant_rows(view):
        if (_side(row) == "attacker" and _tag(row) == "SAV"
                and row.get("automatic") is False and _native_legality(row)):
            return row
    return None


def _find_co(view: dict | None) -> dict | None:
    rows: list[dict] = []
    for row in _participant_rows(view):
        tag = _tag(row)
        if (_side(row) == "defender" and tag not in {None, _ACTOR}
                and row.get("automatic") is False and _native_legality(row)):
            rows.append(row)
    rows.sort(key=lambda row: _tag(row) or "")
    return rows[0] if rows else None


def _force_public_summary(result: object) -> dict | None:
    """Keep only comparable country and unit fields for batch differences."""

    if not isinstance(result, dict) or not isinstance(result.get("forces"), dict):
        return None
    forces = result["forces"]
    summary: dict[str, object] = {"complete": forces.get("complete")}
    for side_name in ("attackers", "defenders"):
        side = forces.get(side_name)
        if not isinstance(side, dict):
            return None
        deployed = side.get("deployed")
        reserve = side.get("reserve_manpower")
        if not isinstance(deployed, dict) or not isinstance(reserve, dict):
            return None
        summary[side_name] = {
            "countries": list(side.get("countries", [])),
            "deployed": {
                field: deployed.get(field)
                for field in ("infantry", "cavalry", "artillery", "total")
            },
            "reserve_manpower": reserve.get("amount"),
        }
    return summary


def _build_force_comparisons(report: dict) -> list[dict]:
    variants = report.get("selection_variants")
    if not isinstance(variants, dict) or variants.get("status") != "selected":
        return []
    base_label = variants.get("base_label")
    recipient = variants.get("recipient")
    if not isinstance(base_label, str) or not isinstance(recipient, str):
        return []
    cases = {
        (case.get("recipient"), case.get("label")): case
        for case in report.get("cases", []) if isinstance(case, dict)
    }
    base_case = cases.get((recipient, base_label))
    base_summary = _force_public_summary(
        base_case.get("public_result") if isinstance(base_case, dict) else None)
    rows: list[dict] = []
    for label in variants.get("queries", []):
        case = cases.get((recipient, label))
        variant_summary = _force_public_summary(
            case.get("public_result") if isinstance(case, dict) else None)
        rows.append({
            "label": label,
            "base_label": base_label,
            "base_status": base_case.get("status") if isinstance(base_case, dict) else None,
            "variant_status": case.get("status") if isinstance(case, dict) else None,
            "base_forces": base_summary,
            "variant_forces": variant_summary,
            "country_sets_changed": (
                base_summary is not None and variant_summary is not None
                and any(base_summary[side]["countries"] != variant_summary[side]["countries"]
                        for side in ("attackers", "defenders"))),
            "deployed_values_changed": (
                base_summary is not None and variant_summary is not None
                and any(base_summary[side]["deployed"] != variant_summary[side]["deployed"]
                        for side in ("attackers", "defenders"))),
            "comparison_complete": base_summary is not None and variant_summary is not None,
        })
    return rows


def _record_query(api: DiplomacyTools, evidence: Path, report: dict,
                  checks: dict[str, bool], recipient: str, label: str,
                  parameters: dict, session_id: str, expected_date: object,
                  source: dict | None = None) -> dict:
    stem = _safe_name(f"{recipient}-{label}")
    input_path = evidence / f"{stem}-input.json"
    result_path = evidence / f"{stem}.json"
    write(input_path, parameters)
    log = api.session.directory / "control-probe.jsonl"
    log_start = log.stat().st_size
    error: str | None = None
    try:
        result = api.inspect_diplomatic_action(
            "declare_war", _ACTOR, recipient, phase=_PHASE,
            parameters=parameters)
    except Exception as exc:  # Keep all query evidence in the batch.
        result = {"status": "unknown", "error": f"{type(exc).__name__}:{exc}"}
        error = result["error"]
    write(result_path, result)
    log_end = log.stat().st_size
    raw_parent: dict | None = None
    raw_failure: dict | None = None
    native_query_id: str | None = None
    raw_bytes = b""
    if 0 <= log_end - log_start <= _SLICE_LIMIT:
        with log.open("rb") as stream:
            stream.seek(log_start)
            raw_bytes = stream.read(log_end - log_start)
        events, _malformed = _parse_events(raw_bytes)
        parents = [item for item in events
                   if item.get("event") == "native_declare_war_inspection"
                   and item.get("session_id") == session_id]
        failures = [item for item in events
                    if item.get("event") == "native_declare_war_inspection_failed"
                    and item.get("session_id") == session_id]
        if len(parents) == 1:
            raw_parent = parents[0]
            native_query_id = raw_parent.get("query_id")
        elif len(failures) == 1:
            raw_failure = failures[0]
            native_query_id = raw_failure.get("query_id")
    raw_path = evidence / f"{stem}-native.json"
    write(raw_path, raw_parent if raw_parent is not None else
          raw_failure if raw_failure is not None else {
              "event": None, "log_start": log_start, "log_end": log_end,
          })
    header, header_ok = _header(raw_parent, recipient, session_id, expected_date)
    public_ok = isinstance(result, dict) and not _has_private_fields(result)
    force_ok, force_detail = _public_force_contract(result, _ACTOR, recipient)
    unavailable = False
    if isinstance(result, dict):
        legality = result.get("legality")
        status = legality.get("status") if isinstance(legality, dict) else None
        unavailable = (status in {"unknown", "unavailable"}
                       or result.get("status") in {"unknown", "unavailable"})
    case: dict[str, Any] = {
        "label": label,
        "recipient": recipient,
        "parameters": parameters,
        "query_id": native_query_id,
        "log_start": log_start,
        "log_end": log_end,
        "input_path": str(input_path),
        "result_path": str(result_path),
        "native_event_path": str(raw_path),
        "status": (result.get("legality", {}).get("status")
                   if isinstance(result, dict)
                   and isinstance(result.get("legality"), dict)
                   else result.get("status") if isinstance(result, dict) else None),
        "public_result": result,
        "public_projection": public_ok,
        "native_unavailable": unavailable,
        "native_header": header,
        "forces_public": force_detail,
    }
    if source is not None:
        case["selection_source"] = source
    if error is not None:
        case["error"] = error
        report.setdefault("query_errors", []).append({
            "recipient": recipient, "label": label, "error": error})
    report["cases"].append(case)
    key = f"{recipient}_{_safe_name(label)}"
    checks[key + "_public"] = public_ok
    checks[key + "_header"] = header_ok
    checks[key + "_forces_public"] = force_ok
    return result if isinstance(result, dict) else {}


def _reconcile_native_slice(report: dict, raw: bytes,
                            checks: dict[str, bool]) -> None:
    events, malformed = _parse_events(raw)
    by_query: dict[str, list[dict]] = {}
    for event in events:
        query_id = event.get("query_id")
        if isinstance(query_id, str) and query_id:
            by_query.setdefault(query_id, []).append(event)
    for case in report.get("cases", []):
        if not isinstance(case, dict):
            continue
        query_id = case.get("query_id")
        group = by_query.get(query_id, []) if isinstance(query_id, str) else []
        parents = [event for event in group
                   if event.get("event") == "native_declare_war_inspection"]
        parent = parents[0] if len(parents) == 1 else None
        recipient = case.get("recipient")
        expected_date = report.get("before", {}).get("date_raw") \
            if isinstance(report.get("before"), dict) else None
        header_ok = (
            parent is not None
            and parent.get("family") == "declare_war"
            and parent.get("action_id") == "declare_war"
            and parent.get("actor") == _ACTOR
            and parent.get("recipient") == recipient
            and parent.get("phase") == _PHASE
            and parent.get("session_id") == report.get("session_id")
            and (expected_date is None or parent.get("date_raw") == expected_date))
        native_forces = parent.get("native_forces") if parent is not None else None
        raw_valid = isinstance(native_forces, dict) and valid_declare_war_forces(native_forces)
        public_result = case.get("public_result")
        public_forces = (public_result.get("forces")
                         if isinstance(public_result, dict) else None)
        expected_public = (project_declare_war_forces(native_forces)
                           if raw_valid else None)
        parity = (raw_valid and isinstance(expected_public, dict)
                  and public_forces == expected_public)
        key = f"{recipient}_{_safe_name(case.get('label', 'case'))}"
        checks[key + "_raw_header"] = header_ok
        checks[key + "_forces_raw"] = raw_valid
        checks[key + "_forces_public_parity"] = parity
        case["native_force_binding"] = {
            "query_id": query_id,
            "parent_event_count": len(parents),
            "native_forces_present": isinstance(native_forces, dict),
            "public_forces_present": isinstance(public_forces, dict),
            "public_missing_when_native_present": (
                isinstance(native_forces, dict) and not isinstance(public_forces, dict)),
            "header_verified": header_ok,
            "native_force_contract_verified": raw_valid,
            "public_projection_matches_native": parity,
        }
    report["native_event_slice_summary"] = {
        "parsed_event_count": len(events),
        "malformed_line_count": malformed,
        "query_count": len(by_query),
        "inspection_event_count": sum(
            1 for event in events if event.get("event") == "native_declare_war_inspection"),
        "inspection_failure_count": sum(
            1 for event in events
            if event.get("event") == "native_declare_war_inspection_failed"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recipients", nargs="+", default=list(_DEFAULT_RECIPIENTS),
                        type=lambda value: value.upper())
    args = parser.parse_args()
    recipients = _normalize_recipients(args.recipients)
    output = args.output.resolve()
    evidence = output.parent / (output.stem + "-evidence")
    if output.exists() or evidence.exists():
        raise SystemExit("OUTPUT_ALREADY_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True)

    session = ObserverSession(args.installation, game_exe())
    report: dict[str, Any] = {
        "status": "running",
        "installation": str(args.installation.resolve()),
        "session_id": session.session_id,
        "actor": _ACTOR,
        "phase": _PHASE,
        "recipients": recipients,
        "cases": [],
        "query_only": True,
        "execute_call_count": 0,
        "advance_requested": False,
        "save_requested": False,
        "reload_requested": False,
        "force_contract": {
            "public_source": "native_declare_war_dialog",
            "unit": "men",
            "raw_event_field": "native_forces",
            "raw_slice_limit_bytes": _SLICE_LIMIT,
        },
    }
    checks: dict[str, bool] = {}
    log = session.directory / "control-probe.jsonl"
    batch_start = log.stat().st_size
    before: dict | None = None
    try:
        health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        if health.get("status") != "ready":
            raise RuntimeError("SESSION_NOT_READY")
        before = _control_from_probe(_run_probe(
            PROBE_SPECS[0], session.record["pid"], evidence / "before-control.json"))
        report["before"] = before
        if not _control_is_paused_por(before, health.get("date_raw")):
            raise RuntimeError("PAUSED_POR_CONTEXT_REQUIRED")
        report["session_date_raw"] = health.get("date_raw")
        with DurableJournal(evidence / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            candidate_contexts: list[dict[str, Any]] = []
            for recipient in recipients:
                discovery = _record_query(
                    api, evidence, report, checks, recipient, "discovery", {},
                    session.session_id, health.get("date_raw"))
                no_cb_selection = _selection_parameters(
                    "no_casus_belli", -1, _ACTOR)
                no_cb_result = _record_query(
                    api, evidence, report, checks, recipient, "no-casus-belli",
                    no_cb_selection,
                    session.session_id, health.get("date_raw"))
                candidate = _first_cb_conquest(discovery)
                if candidate is None:
                    report.setdefault("candidate_selection_plan", {})[recipient] = {
                        "status": "explicit_no_casus_belli",
                        "reason": "NO_CB_CONQUEST_CANDIDATE",
                        "candidate": None,
                        "base_label": "no-casus-belli",
                    }
                    candidate_contexts.append({
                        "recipient": recipient,
                        "candidate": None,
                        "selection": no_cb_selection,
                        "base_result": no_cb_result,
                        "view": _participant_view(no_cb_result),
                        "selection_kind": "no_casus_belli",
                        "base_label": "no-casus-belli",
                    })
                    continue
                selection = _candidate_parameters(candidate)
                base_label = _selection_base_label("cb_conquest", candidate)
                base_result = _record_query(
                    api, evidence, report, checks, recipient, base_label,
                    selection, session.session_id, health.get("date_raw"),
                    {"candidate": candidate})
                view = _participant_view(base_result)
                candidate_contexts.append({
                    "recipient": recipient,
                    "candidate": candidate,
                    "selection": selection,
                    "base_result": base_result,
                    "view": view,
                    "selection_kind": "cb_conquest",
                    "base_label": base_label,
                })
                report.setdefault("candidate_selection_plan", {})[recipient] = {
                    "status": "selected", "candidate": candidate,
                    "base_label": base_label,
                }

            variant_owner: dict[str, Any] | None = None
            for context in candidate_contexts:
                sav = _find_sav(context["view"])
                co = _find_co(context["view"])
                if sav is not None or co is not None:
                    variant_owner = {**context, "sav": sav, "co": co}
                    break
            if variant_owner is None:
                report["selection_variants"] = {
                    "status": "unavailable",
                    "reason": "NO_LEGAL_SAV_OR_CO_CANDIDATE",
                }
            else:
                recipient = variant_owner["recipient"]
                candidate = variant_owner["candidate"]
                base = variant_owner["selection"]
                selection_kind = variant_owner["selection_kind"]
                base_label = variant_owner["base_label"]
                sav = variant_owner["sav"]
                co = variant_owner["co"]
                variant_report: dict[str, Any] = {
                    "status": "selected",
                    "recipient": recipient,
                    "selection_kind": selection_kind,
                    "candidate": candidate,
                    "base_label": base_label,
                    "call_ally": _tag(sav) if sav is not None else None,
                    "co_belligerent": _tag(co) if co is not None else None,
                    "queries": [],
                }
                if sav is not None:
                    sav_tag = _tag(sav)
                    assert sav_tag is not None
                    call = dict(base)
                    call["call_allies"] = [sav_tag]
                    label = f"{selection_kind}-call-{sav_tag}"
                    _record_query(api, evidence, report, checks, recipient, label,
                                  call, session.session_id, health.get("date_raw"),
                                  {"candidate": candidate, "attacker": sav})
                    variant_report["queries"].append(label)
                    if (sav.get("promise_available") is True
                            or isinstance(sav.get("promise_land"), dict)
                            and sav["promise_land"].get("available") is True):
                        promise = dict(call)
                        promise["promise_land_to"] = [sav_tag]
                        label = (f"{selection_kind}-call-{sav_tag}"
                                 f"-promise-{sav_tag}")
                        _record_query(api, evidence, report, checks, recipient, label,
                                      promise, session.session_id, health.get("date_raw"),
                                      {"candidate": candidate, "attacker": sav})
                        variant_report["queries"].append(label)
                if co is not None:
                    co_tag = _tag(co)
                    assert co_tag is not None
                    co_selection = dict(base)
                    co_selection["co_belligerents"] = [co_tag]
                    label = f"{selection_kind}-co-{co_tag}"
                    _record_query(api, evidence, report, checks, recipient, label,
                                  co_selection, session.session_id, health.get("date_raw"),
                                  {"candidate": candidate, "co_belligerent": co})
                    variant_report["queries"].append(label)
                    if sav is not None:
                        sav_tag = _tag(sav)
                        assert sav_tag is not None
                        combined = dict(co_selection)
                        combined["call_allies"] = [sav_tag]
                        promise_available = (
                            sav.get("promise_available") is True
                            or isinstance(sav.get("promise_land"), dict)
                            and sav["promise_land"].get("available") is True)
                        if promise_available:
                            combined["promise_land_to"] = [sav_tag]
                            label = (f"{selection_kind}-call-{sav_tag}"
                                     f"-promise-{sav_tag}"
                                     f"-co-{co_tag}")
                            _record_query(api, evidence, report, checks, recipient, label,
                                          combined, session.session_id,
                                          health.get("date_raw"),
                                          {"candidate": candidate, "attacker": sav,
                                           "co_belligerent": co})
                            variant_report["queries"].append(label)
                report["selection_variants"] = variant_report
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}:{error}")
    finally:
        if before is not None:
            try:
                after = _control_from_probe(_run_probe(
                    PROBE_SPECS[0], session.record["pid"], evidence / "after-control.json"))
                report["after"] = after
                checks["paused_player_and_date_unchanged"] = before == after
            except Exception as error:
                checks["paused_player_and_date_unchanged"] = False
                report["after_error"] = f"{type(error).__name__}:{error}"
        log_end = log.stat().st_size
        length = log_end - batch_start
        if 0 <= length <= _SLICE_LIMIT:
            with log.open("rb") as stream:
                stream.seek(batch_start)
                raw = stream.read(length)
            slice_path = evidence / "native-events-slice.jsonl"
            slice_path.write_bytes(raw)
            report["native_event_slice"] = {
                "path": str(slice_path),
                "bytes": length,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            _reconcile_native_slice(report, raw, checks)
        else:
            report["status"] = "failed"
            report["slice_error"] = "BOUNDED_NATIVE_EVENT_SLICE_EXCEEDED"
        report["checks"] = checks
        if isinstance(report.get("selection_variants"), dict):
            report["selection_variants"]["force_comparisons"] = (
                _build_force_comparisons(report))
        report["summary"] = {
            "case_count": len(report["cases"]),
            "passed_check_count": sum(1 for value in checks.values() if value),
            "check_count": len(checks),
            "failed_checks": [key for key, value in checks.items() if not value],
            "recipients_with_cb_conquest": sum(
                1 for value in report.get("candidate_selection_plan", {}).values()
                if isinstance(value, dict) and value.get("status") == "selected"),
        }
        if report.get("status") != "failed":
            report["status"] = "passed" if all(checks.values()) else "failed"
        write(output, report)
    print(json.dumps({
        "status": report["status"],
        "cases": len(report["cases"]),
        "failed": [key for key, value in checks.items() if not value],
        "error": report.get("error"),
        "output": str(output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
