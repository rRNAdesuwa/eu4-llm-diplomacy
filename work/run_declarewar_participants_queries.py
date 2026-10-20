"""Query bounded native Declare War participant candidates in one paused session."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.diplomacy_journal import DurableJournal
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_peace_concession_queries import _control_from_probe, _control_is_paused_por
from work.run_peace_empty_offer_queries import _has_private_fields
from work.validate_alliance_queries import PROBE_SPECS, _run_probe


_ACTOR = "FRA"
_PHASE = "initiate"
_DEFAULT_RECIPIENTS = ("ENG", "BUR", "MOR")
_TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
_CB_RE = re.compile(r"[A-Za-z0-9_]{1,128}\Z")
_SLICE_LIMIT = 16 * 1024 * 1024


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _safe_name(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value))


def _normalize_recipients(raw: list[str]) -> list[str]:
    recipients: list[str] = []
    for item in raw:
        for candidate in item.split(","):
            tag = candidate.strip().upper()
            if _TAG_RE.fullmatch(tag) is None or tag == _ACTOR:
                raise SystemExit("RECIPIENT_INVALID")
            if tag not in recipients:
                recipients.append(tag)
    if not recipients:
        raise SystemExit("RECIPIENT_REQUIRED")
    return recipients


def _selection_parameters(casus_belli: str, province_id: int,
                          beneficiary: str,
                          call_allies: list[str] | None = None,
                          promise_land_to: list[str] | None = None,
                          co_belligerents: list[str] | None = None) -> dict:
    if _CB_RE.fullmatch(casus_belli) is None:
        raise ValueError("CASUS_BELLI_INVALID")
    if (isinstance(province_id, bool) or not isinstance(province_id, int)
            or (province_id != -1 and province_id <= 0)):
        raise ValueError("PROVINCE_ID_INVALID")
    if beneficiary != "---" and _TAG_RE.fullmatch(beneficiary) is None:
        raise ValueError("BENEFICIARY_INVALID")
    return {
        "casus_belli": casus_belli,
        "war_goal": {"province_id": province_id, "beneficiary": beneficiary},
        "call_allies": list(call_allies or []),
        "promise_land_to": list(promise_land_to or []),
        "co_belligerents": list(co_belligerents or []),
    }


def _result_value(result: object, key: str) -> object:
    if not isinstance(result, dict):
        return None
    value = result.get(key)
    if value is not None:
        return value
    session = result.get("session")
    if isinstance(session, dict):
        return session.get(key)
    return None


def _header(result: object, recipient: str, session_id: str,
            expected_date: object) -> tuple[dict, bool]:
    if not isinstance(result, dict):
        return {"available": False, "reason": "RESULT_NOT_OBJECT"}, False
    observed = {key: _result_value(result, key)
                for key in ("event", "family", "action_id", "actor", "recipient",
                            "phase", "session_id", "query_id", "date_raw")}
    valid = (
        observed["event"] == "native_declare_war_inspection"
        and observed["family"] == "declare_war"
        and observed["action_id"] == "declare_war"
        and observed["actor"] == _ACTOR
        and observed["recipient"] == recipient
        and observed["phase"] == _PHASE
        and observed["session_id"] == session_id
        and isinstance(observed["query_id"], str)
        and bool(observed["query_id"])
        and (expected_date is None or observed["date_raw"] == expected_date)
    )
    return {"available": True, "observed": observed, "unchanged": valid}, valid


def _unavailable(result: object) -> bool:
    if not isinstance(result, dict):
        return False
    legality = result.get("legality")
    status = legality.get("status") if isinstance(legality, dict) else None
    interface = result.get("interface_support")
    interface_status = interface.get("query") if isinstance(interface, dict) else None
    return (status in {"unknown", "unavailable"}
            or result.get("status") in {"unknown", "unavailable"}
            or interface_status in {"unknown", "unimplemented"}
            or isinstance(result.get("error_code"), str))


def _candidate_rows(result: object) -> list[dict]:
    if not isinstance(result, dict):
        return []
    rows = result.get("candidates")
    if not isinstance(rows, list):
        parameters = result.get("parameters")
        if isinstance(parameters, dict):
            rows = parameters.get("candidates")
            if isinstance(rows, dict):
                rows = rows.get("items")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _candidate_selection_rows(result: object, limit: int = 2) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    rows: list[tuple[str, int, str, int, dict]] = []
    for index, row in enumerate(_candidate_rows(result)):
        cb = row.get("casus_belli_key")
        province = row.get("target_province_id")
        beneficiary = row.get("beneficiary_tag")
        if (not isinstance(cb, str) or _CB_RE.fullmatch(cb) is None
                or cb == "no_casus_belli"
                or row.get("casus_belli_key_verified", True) is not True
                or isinstance(province, bool) or not isinstance(province, int)
                or (province != -1 and province <= 0)
                or row.get("province_identifier_verified", True) is not True
                or not isinstance(beneficiary, str)
                or (beneficiary != "---" and _TAG_RE.fullmatch(beneficiary) is None)
                or row.get("beneficiary_identifier_verified", True) is not True):
            continue
        rows.append((cb, province, beneficiary, index, row))
    rows.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    for cb, province, beneficiary, _index, row in rows:
        if cb in seen:
            continue
        seen.add(cb)
        selected.append({
            "casus_belli": cb,
            "war_goal": {"province_id": province, "beneficiary": beneficiary},
            "call_allies": [],
            "promise_land_to": [],
            "co_belligerents": [],
            "candidate": row,
        })
        if len(selected) >= limit:
            break
    return selected


def _looks_like_participants(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (value.get("source") == "native_declare_war_participants"
            or ("candidates" in value and
                ("selection" in value or "enumeration_complete" in value
                 or "candidate_count" in value)))


def _participant_view(result: object) -> dict | None:
    if not isinstance(result, dict):
        return None
    paths = (
        ("participants",), ("declare_war_participants",),
        ("native_declare_war_participants",),
        ("parameters", "participants"),
        ("parameters", "declare_war_participants"),
        ("parameters", "native_declare_war_participants"),
    )
    for path in paths:
        value: object = result
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if _looks_like_participants(value):
            return value
    for value in result.values():
        if _looks_like_participants(value):
            return value
    return None


def _participant_rows(view: dict | None) -> list[dict]:
    if not isinstance(view, dict):
        return []
    rows = view.get("candidates")
    if not isinstance(rows, list):
        rows = view.get("items")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _tag(row: dict) -> str | None:
    for key in ("country", "country_tag", "tag"):
        value = row.get(key)
        if isinstance(value, str) and _TAG_RE.fullmatch(value):
            return value
    return None


def _side(row: dict) -> str | None:
    value = row.get("side")
    return value if value in {"attacker", "defender"} else None


def _native_legality(row: dict) -> bool:
    if row.get("native_legality") is True:
        return True
    legality = row.get("legality")
    return isinstance(legality, dict) and legality.get("native_legality") is True


def _willingness_positive(row: dict) -> bool:
    if row.get("willingness_positive") is True or row.get("would_call") is True:
        return True
    willingness = row.get("willingness")
    if not isinstance(willingness, dict):
        return False
    total = willingness.get("native_total_raw")
    threshold = willingness.get("acceptance_threshold_raw", 1)
    return (isinstance(total, int) and not isinstance(total, bool)
            and isinstance(threshold, int) and not isinstance(threshold, bool)
            and total >= threshold)


def _promise_available(row: dict) -> bool:
    if row.get("promise_available") is True:
        return True
    promise = row.get("promise_land")
    return isinstance(promise, dict) and promise.get("available") is True


def _choose_attacker(view: dict | None) -> dict | None:
    rows = _participant_rows(view)
    candidates = []
    for row in rows:
        tag = _tag(row)
        if (_side(row) == "attacker" and tag not in {None, _ACTOR}
                and row.get("automatic") is False
                and _native_legality(row)
                and (_willingness_positive(row) or _promise_available(row))):
            candidates.append(row)
    candidates.sort(key=lambda row: (not _willingness_positive(row), _tag(row) or ""))
    return candidates[0] if candidates else None


def _choose_defenders(view: dict | None, limit: int = 2) -> list[dict]:
    rows = []
    seen: set[str] = set()
    for row in _participant_rows(view):
        tag = _tag(row)
        if (_side(row) == "defender" and tag not in {None, _ACTOR}
                and row.get("automatic") is False and tag not in seen):
            rows.append(row)
            seen.add(tag)  # type: ignore[arg-type]
    rows.sort(key=lambda row: _tag(row) or "")
    return rows[:limit]


def _participant_condition(view: dict | None,
                           parameters: dict) -> dict[str, object]:
    requested = {
        "call_allies": list(parameters.get("call_allies", [])),
        "promise_land_to": list(parameters.get("promise_land_to", [])),
        "co_belligerents": list(parameters.get("co_belligerents", [])),
    }
    if view is None:
        return {
            "present": False, "complete": False, "enumeration_complete": False,
            "selection_applied": None, "selection_matches": False,
            "candidate_count": None, "candidate_rows": 0,
        }
    selection = view.get("selection")
    if not isinstance(selection, dict):
        selection = view
    selected = {
        key: selection.get(key, []) for key in requested
    }
    matches = all(selected[key] == requested[key] for key in requested)
    applied = selection.get("applied")
    if not isinstance(applied, bool):
        applied = view.get("selection_applied")
    # The observer binds all three vectors, including a complete empty choice.
    applied_ok = applied is True
    complete = view.get("complete") is True
    enumeration_complete = view.get("enumeration_complete") is True
    if "enumeration_complete" not in view:
        enumeration_complete = complete
    return {
        "present": True,
        "complete": complete,
        "enumeration_complete": enumeration_complete,
        "selection_applied": applied,
        "selection_applied_expected": True,
        "selection_matches": matches and applied_ok,
        "candidate_count": view.get("candidate_count"),
        "candidate_rows": len(_participant_rows(view)),
        "legality_complete": view.get("legality_complete"),
    }


def _record_query(api: DiplomacyTools, evidence: Path, report: dict,
                  checks: dict[str, bool], recipient: str, label: str,
                  parameters: dict, session_id: str, expected_date: object,
                  source: dict | None = None) -> dict:
    stem = _safe_name(f"{recipient}-{label}")
    input_path = evidence / f"{stem}-input.json"
    result_path = evidence / f"{stem}.json"
    write(input_path, parameters)
    error: str | None = None
    log = api.session.directory / "control-probe.jsonl"
    query_start = log.stat().st_size
    try:
        result = api.inspect_diplomatic_action(
            "declare_war", _ACTOR, recipient, phase=_PHASE, parameters=parameters)
    except Exception as exc:  # preserve per-query evidence and continue the batch
        result = {"status": "unknown", "error": f"{type(exc).__name__}:{exc}"}
        error = result["error"]
    write(result_path, result)
    query_end = log.stat().st_size
    native_query_id = None
    raw_parent = None
    if 0 <= query_end - query_start <= _SLICE_LIMIT:
        with log.open("rb") as stream:
            stream.seek(query_start)
            query_events, _ = _parse_events(stream.read(query_end - query_start))
        final_events = [item for item in query_events
                        if item.get("event") in {"native_declare_war_inspection", "native_alliance_inspection_failed"}
                        and item.get("session_id") == session_id]
        if len(final_events) == 1:
            native_query_id = final_events[0].get("query_id")
            if final_events[0].get("event") == "native_declare_war_inspection":
                raw_parent = final_events[0]
    header, header_ok = _header(raw_parent, recipient, session_id, expected_date)
    unavailable = _unavailable(result)
    participants = _participant_view(result)
    participant_check = _participant_condition(participants, parameters)
    public_ok = isinstance(result, dict) and not _has_private_fields(result)
    query_id = native_query_id
    case = {
        "label": label,
        "recipient": recipient,
        "parameters": parameters,
        "query_id": query_id,
        "log_start": query_start,
        "log_end": query_end,
        "session_id": _result_value(result, "session_id"),
        "input_path": str(input_path),
        "result_path": str(result_path),
        "status": (result.get("legality", {}).get("status")
                   if isinstance(result, dict)
                   and isinstance(result.get("legality"), dict)
                   else result.get("status") if isinstance(result, dict) else None),
        "legal_status": result.get("legality") if isinstance(result, dict) else None,
        "public_result": result,
        "public_projection": public_ok,
        "native_unavailable": unavailable,
        "native_header": header,
        "participants": participants,
        "participant_condition": participant_check,
        "candidate_rows": _candidate_rows(result),
    }
    if source is not None:
        case["selection_source"] = source
    if error is not None:
        case["error"] = error
        report.setdefault("query_errors", []).append(
            {"recipient": recipient, "label": label, "error": error})
    report["cases"].append(case)
    key = f"{recipient}_{_safe_name(label)}"
    checks[key + "_public"] = public_ok
    checks[key + "_header"] = header_ok
    checks[key + "_participants"] = participant_check["present"]
    checks[key + "_participant_selection"] = participant_check["selection_matches"] is True
    return result if isinstance(result, dict) else {}


def _csv(tags: list[str]) -> str:
    return ",".join(tags) if tags else "-"


def _parse_events(raw: bytes) -> tuple[list[dict], int]:
    events: list[dict] = []
    malformed = 0
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed += 1
            continue
        if isinstance(value, dict):
            events.append(value)
    return events, malformed


def _raw_participant_contract(parent: dict, rows: list[dict],
                              parameters: dict, session_id: str,
                              recipient: str, date_raw: object) -> bool:
    native = parent.get("native_participants")
    if not isinstance(native, dict):
        return False
    if native.get("called") is not True or native.get("action_unchanged") is not True:
        return False
    expected = {
        "requested_call_allies_csv": _csv(parameters.get("call_allies", [])),
        "requested_promise_land_to_csv": _csv(parameters.get("promise_land_to", [])),
        "requested_co_belligerents_csv": _csv(parameters.get("co_belligerents", [])),
    }
    if any(native.get(key) != value for key, value in expected.items()):
        return False
    if native.get("candidate_count") != len(rows):
        return False
    wanted_call = set(parameters.get("call_allies", []))
    wanted_promise = set(parameters.get("promise_land_to", []))
    wanted_co = set(parameters.get("co_belligerents", []))
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        if (row.get("event") != "native_declare_war_participant"
                or row.get("session_id") != session_id
                or row.get("query_id") != parent.get("query_id")
                or row.get("actor") != _ACTOR
                or row.get("recipient") != recipient
                or row.get("date_raw") != date_raw
                or row.get("index") != index
                or row.get("side") not in {"attacker", "defender"}
                or not isinstance(row.get("country"), str)
                or _TAG_RE.fullmatch(row["country"]) is None):
            return False
        key = (row["side"], row["country"])
        if key in seen:
            return False
        seen.add(key)
        expected_selected = (row["country"] in wanted_call
                             if row["side"] == "attacker"
                             else row["country"] in wanted_co)
        expected_promise = row["side"] == "attacker" and row["country"] in wanted_promise
        if (row.get("selected") is not expected_selected
                or row.get("promise_land") is not expected_promise):
            return False
    return True


def _reconcile_native_slice(report: dict, raw: bytes, checks: dict[str, bool]) -> None:
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
        rows = sorted([event for event in group
                       if event.get("event") == "native_declare_war_participant"],
                      key=lambda row: row.get("index", -1))
        parent = parents[0] if len(parents) == 1 else None
        recipient = case.get("recipient")
        header_ok = bool(parent) and parent.get("family") == "declare_war" \
            and parent.get("action_id") == "declare_war" \
            and parent.get("actor") == _ACTOR \
            and parent.get("recipient") == recipient \
            and parent.get("phase") == _PHASE \
            and parent.get("session_id") == report.get("session_id")
        unavailable = case.get("native_unavailable") is True
        expected_date = report.get("before", {}).get("date_raw") \
            if isinstance(report.get("before"), dict) else None
        date_ok = parent is not None and (expected_date is None
                                          or parent.get("date_raw") == expected_date)
        participant_ok = False
        if parent is not None and isinstance(recipient, str):
            participant_ok = _raw_participant_contract(
                parent, rows, case.get("parameters", {}), report.get("session_id", ""),
                recipient, parent.get("date_raw"))
        key = f"{recipient}_{_safe_name(case.get('label', 'case'))}"
        checks[key + "_raw_header"] = header_ok and date_ok
        checks[key + "_raw_participants"] = participant_ok
        case["native_event_binding"] = {
            "query_id": query_id,
            "session_id": report.get("session_id"),
            "parent_event_count": len(parents),
            "participant_event_count": len(rows),
            "header_verified": header_ok and date_ok,
            "participant_contract_verified": participant_ok,
            "unavailable_preserved": unavailable and not parents,
        }
    report["native_event_slice_summary"] = {
        "parsed_event_count": len(events),
        "malformed_line_count": malformed,
        "query_count": len(by_query),
        "parent_event_count": sum(
            1 for event in events if event.get("event") == "native_declare_war_inspection"),
        "participant_event_count": sum(
            1 for event in events if event.get("event") == "native_declare_war_participant"),
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
        "participant_query_contract": {
            "public_source": "native_declare_war_participants",
            "max_cb_selections_per_recipient": 2,
            "max_defender_candidates_per_cb": 2,
            "nonempty_queries": "attacker_call,promise_when_available,defender_co,attacker_call_plus_defender_co",
        },
    }
    checks: dict[str, bool] = {}
    log = session.directory / "control-probe.jsonl"
    start = log.stat().st_size
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
        with DurableJournal(evidence / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            for recipient in recipients:
                discovery = _record_query(
                    api, evidence, report, checks, recipient, "discovery", {},
                    session.session_id, health.get("date_raw"))
                _record_query(
                    api, evidence, report, checks, recipient, "no-casus-belli",
                    _selection_parameters("no_casus_belli", -1, _ACTOR),
                    session.session_id, health.get("date_raw"))
                selections = _candidate_selection_rows(discovery)
                report.setdefault("candidate_selection_plan", {})[recipient] = selections
                for index, planned_selection in enumerate(selections, start=1):
                    selection = dict(planned_selection)
                    candidate = selection.pop("candidate", None)
                    cb = selection["casus_belli"]
                    goal = selection["war_goal"]
                    base_label = f"cb-{index}-{cb}-{goal['province_id']}-{goal['beneficiary']}"
                    selected_result = _record_query(
                        api, evidence, report, checks, recipient, base_label,
                        selection, session.session_id, health.get("date_raw"),
                        {"candidate": candidate})
                    participant_view = _participant_view(selected_result)
                    participant_case = report["cases"][-1]
                    participant_case["participant_candidate_source"] = {
                        "attacker": _tag(_choose_attacker(participant_view))
                        if _choose_attacker(participant_view) else None,
                        "defenders": [_tag(row) for row in _choose_defenders(participant_view)],
                    }
                    attacker = _choose_attacker(participant_view)
                    if attacker is not None:
                        attacker_tag = _tag(attacker)
                        assert attacker_tag is not None
                        call_selection = _selection_parameters(
                            cb, goal["province_id"], goal["beneficiary"], [attacker_tag])
                        _record_query(
                            api, evidence, report, checks, recipient,
                            f"{base_label}-call-{attacker_tag}", call_selection,
                            session.session_id, health.get("date_raw"),
                            {"candidate": attacker, "base_case": base_label})
                        if _promise_available(attacker):
                            promise_selection = _selection_parameters(
                                cb, goal["province_id"], goal["beneficiary"],
                                [attacker_tag], [attacker_tag])
                            _record_query(
                                api, evidence, report, checks, recipient,
                                f"{base_label}-promise-{attacker_tag}", promise_selection,
                                session.session_id, health.get("date_raw"),
                                {"candidate": attacker, "base_case": base_label})
                    for defender in _choose_defenders(participant_view):
                        defender_tag = _tag(defender)
                        assert defender_tag is not None
                        co_selection = _selection_parameters(
                            cb, goal["province_id"], goal["beneficiary"],
                            co_belligerents=[defender_tag])
                        _record_query(
                            api, evidence, report, checks, recipient,
                            f"{base_label}-co-{defender_tag}", co_selection,
                            session.session_id, health.get("date_raw"),
                            {"candidate": defender, "base_case": base_label})
                        if attacker is not None:
                            attacker_tag = _tag(attacker)
                            assert attacker_tag is not None
                            call_co_selection = _selection_parameters(
                                cb, goal["province_id"], goal["beneficiary"],
                                [attacker_tag], co_belligerents=[defender_tag])
                            _record_query(
                                api, evidence, report, checks, recipient,
                                f"{base_label}-call-{attacker_tag}-co-{defender_tag}",
                                call_co_selection, session.session_id,
                                health.get("date_raw"),
                                {"candidate": defender, "attacker": attacker,
                                 "base_case": base_label})
        after = _control_from_probe(_run_probe(
            PROBE_SPECS[0], session.record["pid"], evidence / "after-control.json"))
        report["after"] = after
        checks["paused_player_and_date_unchanged"] = before == after
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}:{error}")
    finally:
        report["checks"] = checks
        length = log.stat().st_size - start
        if 0 <= length <= _SLICE_LIMIT:
            with log.open("rb") as stream:
                stream.seek(start)
                raw = stream.read(length)
            slice_path = evidence / "native-events-slice.jsonl"
            slice_path.write_bytes(raw)
            report["native_event_slice"] = {
                "path": str(slice_path), "bytes": length,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            _reconcile_native_slice(report, raw, checks)
        else:
            report.update(status="failed", slice_error="BOUNDED_NATIVE_EVENT_SLICE_EXCEEDED")
        if report.get("status") != "failed":
            report["status"] = "passed" if all(checks.values()) else "failed"
        write(output, report)
    print(json.dumps({
        "status": report["status"], "cases": len(report["cases"]),
        "failed": [key for key, value in checks.items() if not value],
        "error": report.get("error"), "output": str(output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
