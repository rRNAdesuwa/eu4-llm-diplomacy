"""Query native Declare War dialog details for a bounded set of recipients."""
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
from work.run_peace_empty_offer_queries import _has_private_fields
from work.validate_alliance_queries import PROBE_SPECS, _run_probe


_ACTOR = "FRA"
_PHASE = "initiate"
_DEFAULT_RECIPIENTS = ("ENG", "BUR", "MOR")
_TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
_CB_RE = re.compile(r"[A-Za-z0-9_]{1,128}\Z")
_SLICE_LIMIT = 16 * 1024 * 1024


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _normalize_recipients(raw: list[str]) -> list[str]:
    recipients: list[str] = []
    for item in raw:
        for candidate in item.split(","):
            tag = candidate.strip().upper()
            if not _TAG_RE.fullmatch(tag) or tag == _ACTOR:
                raise SystemExit("RECIPIENT_INVALID")
            if tag not in recipients:
                recipients.append(tag)
    if not recipients:
        raise SystemExit("RECIPIENT_REQUIRED")
    return recipients


def _selection_parameters(casus_belli: str, province_id: int,
                          beneficiary: str) -> dict:
    if _CB_RE.fullmatch(casus_belli) is None:
        raise ValueError("CASUS_BELLI_INVALID")
    if (isinstance(province_id, bool) or not isinstance(province_id, int)
            or not (province_id == -1 or province_id > 0)):
        raise ValueError("PROVINCE_ID_INVALID")
    if beneficiary != "---" and _TAG_RE.fullmatch(beneficiary) is None:
        raise ValueError("BENEFICIARY_INVALID")
    return {
        "casus_belli": casus_belli,
        "war_goal": {"province_id": province_id, "beneficiary": beneficiary},
        "call_allies": [],
    }


def _details_shape(details: object) -> bool:
    if not isinstance(details, dict):
        return False
    if not all(key in details for key in (
            "source", "complete", "casus_belli", "war_goal",
            "peace_conditions", "description", "description_complete")):
        return False
    if details.get("source") != "native_declare_war_dialog":
        return False
    if not isinstance(details.get("complete"), bool):
        return False
    casus = details.get("casus_belli")
    goal = details.get("war_goal")
    peace = details.get("peace_conditions")
    if (not isinstance(casus, dict)
            or not all(key in casus for key in ("name", "description", "complete"))
            or not isinstance(casus.get("complete"), bool)):
        return False
    if (not isinstance(goal, dict)
            or not all(key in goal for key in ("applicable", "name", "description", "complete"))
            or not isinstance(goal.get("applicable"), bool)
            or not isinstance(goal.get("complete"), bool)):
        return False
    if (not isinstance(peace, dict)
            or not all(key in peace for key in (
                "disabled_terms_description", "complete"))
            or not isinstance(peace.get("complete"), bool)):
        return False
    return isinstance(details.get("description_complete"), bool)


def _candidate_rows(result: object) -> list[dict]:
    if not isinstance(result, dict):
        return []
    parameters = result.get("parameters")
    rows = parameters.get("candidates") if isinstance(parameters, dict) else None
    if not isinstance(rows, list):
        rows = result.get("candidates")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _valid_candidate(row: dict) -> bool:
    casus = row.get("casus_belli_key")
    province = row.get("target_province_id")
    beneficiary = row.get("beneficiary_tag")
    return (
        isinstance(casus, str) and _CB_RE.fullmatch(casus) is not None
        and row.get("casus_belli_key_verified") is True
        and isinstance(province, int) and not isinstance(province, bool)
        and (province == -1 or province > 0)
        and row.get("province_identifier_verified") is True
        and isinstance(beneficiary, str)
        and (beneficiary == "---" or _TAG_RE.fullmatch(beneficiary) is not None)
        and row.get("beneficiary_identifier_verified") is True
    )


def _candidate_selections(result: object, limit: int = 6) -> list[dict]:
    selected: list[dict] = []
    seen_cb: set[str] = set()
    rows = []
    for index, row in enumerate(_candidate_rows(result)):
        if _valid_candidate(row):
            rows.append((row.get("casus_belli_key"), row.get("target_province_id"),
                         row.get("beneficiary_tag"), index, row))
    rows.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    for casus, province, beneficiary, _index, row in rows:
        if casus in seen_cb:
            continue
        seen_cb.add(casus)
        selected.append({
            "casus_belli": casus,
            "war_goal": {"province_id": province, "beneficiary": beneficiary},
            "call_allies": [],
            "candidate": row,
        })
        if len(selected) >= limit:
            break
    return selected


def _header(result: object, recipient: str, session_id: str,
            expected_date: object) -> tuple[dict, bool]:
    if not isinstance(result, dict):
        return {"available": False, "reason": "RESULT_NOT_OBJECT"}, False
    observed = {
        key: result.get(key)
        for key in ("event", "family", "action_id", "actor", "recipient",
                    "phase", "session_id", "query_id", "date_raw")
    }
    valid = (
        result.get("event") == "native_declare_war_inspection"
        and result.get("family") == "declare_war"
        and result.get("action_id") == "declare_war"
        and result.get("actor") == _ACTOR
        and result.get("recipient") == recipient
        and result.get("phase") == _PHASE
        and result.get("session_id") == session_id
        and isinstance(result.get("query_id"), str)
        and bool(result.get("query_id"))
        and (expected_date is None or result.get("date_raw") == expected_date)
    )
    return {"available": True, "observed": observed, "unchanged": valid}, valid


def _unavailable(result: object) -> bool:
    if not isinstance(result, dict):
        return False
    legality = result.get("legality")
    status = legality.get("status") if isinstance(legality, dict) else None
    code = result.get("error_code")
    return (status in {"unknown", "unavailable"}
            or result.get("status") in {"unknown", "unavailable"}
            or isinstance(code, str))


def _record_query(api: DiplomacyTools, evidence: Path, report: dict,
                  checks: dict, recipient: str, label: str,
                  parameters: dict, session_id: str, expected_date: object) -> dict:
    stem = _safe_name(f"{recipient}-{label}")
    input_path = evidence / f"{stem}-input.json"
    result_path = evidence / f"{stem}.json"
    write(input_path, parameters)
    error: str | None = None
    try:
        result = api.inspect_diplomatic_action(
            "declare_war", _ACTOR, recipient, phase=_PHASE, parameters=parameters)
    except Exception as exc:  # preserve the per-query artifact and continue other recipients
        result = {"status": "unknown", "error": f"{type(exc).__name__}:{exc}"}
        error = result["error"]
    write(result_path, result)
    header, header_ok = _header(result, recipient, session_id, expected_date)
    details = result.get("declaration_details") if isinstance(result, dict) else None
    unavailable = _unavailable(result)
    details_ok = _details_shape(details)
    public_ok = isinstance(result, dict) and not _has_private_fields(result)
    row = {
        "label": label,
        "recipient": recipient,
        "parameters": parameters,
        "result_path": str(result_path),
        "input_path": str(input_path),
        "status": result.get("legality", {}).get("status")
            if isinstance(result, dict) and isinstance(result.get("legality"), dict)
            else result.get("status") if isinstance(result, dict) else None,
        "legal_status": result.get("legality") if isinstance(result, dict) else None,
        "declaration_details": details,
        "details_present": details_ok,
        "public_projection": public_ok,
        "native_header": header,
        "native_unavailable": unavailable,
        "candidates": _candidate_rows(result),
    }
    if error is not None:
        row["error"] = error
        report.setdefault("query_errors", []).append({"recipient": recipient, "label": label, "error": error})
    if unavailable and error is None:
        report.setdefault("native_unavailable_cases", []).append(
            {"recipient": recipient, "label": label})
    report["cases"].append(row)
    key = f"{recipient}_{_safe_name(label)}"
    # A native-unavailable observation is recorded and retained, but does not
    # turn the query batch into a false failure.  A returned native header,
    # when present, must still match the fixed query context.
    checks[key + "_header"] = header_ok or (unavailable and error is None)
    checks[key + "_details"] = details_ok or (unavailable and error is None)
    checks[key + "_public"] = public_ok or (unavailable and error is None)
    return result if isinstance(result, dict) else {}


def _resolve_path(raw: object, base: Path) -> Path | None:
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else (base / path).resolve()


def _raw_details_contract(raw: object) -> dict:
    if not isinstance(raw, dict):
        return {"present": False, "complete": False, "action_unchanged": False}
    fields = (
        "casus_belli_name", "casus_belli_description",
        "war_goal_name", "war_goal_description",
        "disabled_peace_terms_description", "declaration_description",
    )
    records_complete = all(
        isinstance(raw.get(field), dict)
        and raw[field].get("called") is True
        and raw[field].get("return_verified") is True
        and raw[field].get("readable") is True
        and raw[field].get("truncated") is False
        for field in fields
        if isinstance(raw.get(field), dict) and raw[field].get("applicable") is True
    )
    return {
        "present": True,
        "complete": raw.get("complete") is True and records_complete,
        "action_unchanged": raw.get("action_unchanged") is True,
        "called": raw.get("called") is True,
    }


def _reconcile_case(case: dict, event: dict | None, report: dict,
                    recipient_event_index: int) -> dict:
    parameters = case.get("parameters") if isinstance(case.get("parameters"), dict) else {}
    public_status = case.get("status")
    public_details_present = case.get("details_present") is True
    base = {
        "label": case.get("label"),
        "recipient": case.get("recipient"),
        "source_case_index": recipient_event_index,
        "source_result_path": case.get("result_path"),
        "public_status": public_status,
        "public_details_present": public_details_present,
        "public_declaration_details": case.get("declaration_details"),
        "parameters": parameters,
    }
    if event is None:
        unknown = (not public_details_present
                   and public_status in {"unknown", "unavailable", None})
        base.update({
            "native_event_available": False,
            "outcome": "unknown_native_unavailable" if unknown else "source_event_missing",
            "header_verified": False,
            "action_unchanged": None,
            "date_unchanged": None,
            "details_raw": {"present": False, "complete": False,
                             "action_unchanged": False},
        })
        return base

    expected_date = None
    before = report.get("before")
    if isinstance(before, dict):
        expected_date = before.get("date_raw")
    details = _raw_details_contract(event.get("native_details"))
    header_verified = (
        event.get("event") == "native_declare_war_inspection"
        and event.get("family") == "declare_war"
        and event.get("action_id") == "declare_war"
        and event.get("actor") == _ACTOR
        and event.get("recipient") == case.get("recipient")
        and event.get("phase") == _PHASE
        and event.get("session_id") == report.get("session_id")
        and isinstance(event.get("query_id"), str)
        and bool(event.get("query_id"))
    )
    date_unchanged = expected_date is None or event.get("date_raw") == expected_date
    action_unchanged = details.get("action_unchanged") is True
    selection_expected = not (parameters == {})
    selection_verified = (
        event.get("selection_requested") is selection_expected
        and (not selection_expected or (
            event.get("selection_matched") is True
            and event.get("requested_casus_belli") == parameters.get("casus_belli")
            and event.get("requested_province_id") == (
                parameters.get("war_goal", {}).get("province_id")
                if isinstance(parameters.get("war_goal"), dict) else None)
            and event.get("requested_beneficiary") == (
                parameters.get("war_goal", {}).get("beneficiary")
                if isinstance(parameters.get("war_goal"), dict) else None))))
    base.update({
        "native_event_available": True,
        "outcome": "verified" if header_verified and date_unchanged and action_unchanged else "raw_event_mismatch",
        "raw_event_query_id": event.get("query_id"),
        "raw_event": {
            "event": event.get("event"),
            "session_id": event.get("session_id"),
            "query_id": event.get("query_id"),
            "action_id": event.get("action_id"),
            "family": event.get("family"),
            "actor": event.get("actor"),
            "recipient": event.get("recipient"),
            "phase": event.get("phase"),
            "date_raw": event.get("date_raw"),
            "selection_requested": event.get("selection_requested"),
            "selection_matched": event.get("selection_matched"),
            "requested_casus_belli": event.get("requested_casus_belli"),
            "requested_province_id": event.get("requested_province_id"),
            "requested_beneficiary": event.get("requested_beneficiary"),
            "object_unchanged": event.get("object_unchanged"),
        },
        "header_verified": header_verified,
        "action_unchanged": action_unchanged,
        "date_unchanged": date_unchanged,
        "selection_verified": selection_verified,
        "details_raw": details,
    })
    return base


def _parse_native_inspection_events(raw: bytes) -> tuple[list[dict], int]:
    events: list[dict] = []
    malformed_lines = 0
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed_lines += 1
            continue
        if isinstance(value, dict):
            events.append(value)
    return [
        event for event in events
        if event.get("event") == "native_declare_war_inspection"
    ], malformed_lines


def _native_case_reconciliation(report: dict, inspections: list[dict]) -> list[dict]:
    by_recipient: dict[str, list[dict]] = {}
    for event in inspections:
        recipient = event.get("recipient")
        if isinstance(recipient, str):
            by_recipient.setdefault(recipient, []).append(event)
    offsets: dict[str, int] = {}
    reconciled: list[dict] = []
    for case in report.get("cases", []):
        if not isinstance(case, dict):
            continue
        recipient = case.get("recipient")
        if not isinstance(recipient, str):
            reconciled.append(_reconcile_case(case, None, report, -1))
            continue
        index = offsets.get(recipient, 0)
        candidates = by_recipient.get(recipient, [])
        event = candidates[index] if index < len(candidates) else None
        offsets[recipient] = index + (1 if event is not None else 0)
        reconciled.append(_reconcile_case(case, event, report, index))
    return reconciled


def _reconcile_report(source_report: Path, output: Path) -> int:
    source_report = source_report.resolve()
    output = output.resolve()
    if output.exists():
        raise SystemExit("RECONCILIATION_OUTPUT_ALREADY_EXISTS")
    report = json.loads(source_report.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise SystemExit("SOURCE_REPORT_INVALID")
    slice_info = report.get("native_event_slice")
    slice_path = _resolve_path(
        slice_info.get("path") if isinstance(slice_info, dict) else None,
        source_report.parent)
    if slice_path is None or not slice_path.exists():
        raise SystemExit("NATIVE_EVENT_SLICE_MISSING")
    slice_size = slice_path.stat().st_size
    if slice_size > _SLICE_LIMIT:
        raise SystemExit("NATIVE_EVENT_SLICE_EXCEEDED")
    raw = slice_path.read_bytes()
    inspections, malformed_lines = _parse_native_inspection_events(raw)
    reconciled_cases = _native_case_reconciliation(report, inspections)
    by_recipient: dict[str, list[dict]] = {}
    for event in inspections:
        recipient = event.get("recipient")
        if isinstance(recipient, str):
            by_recipient.setdefault(recipient, []).append(event)

    source_case_count_by_recipient: dict[str, int] = {}
    for case in report.get("cases", []):
        if isinstance(case, dict) and isinstance(case.get("recipient"), str):
            source_case_count_by_recipient[case["recipient"]] = (
                source_case_count_by_recipient.get(case["recipient"], 0) + 1)
    event_count_by_recipient = {key: len(value) for key, value in by_recipient.items()}
    mapping_counts_ok = all(
        event_count_by_recipient.get(recipient, 0) <= count
        for recipient, count in source_case_count_by_recipient.items())
    verified_cases = [case for case in reconciled_cases if case.get("outcome") == "verified"]
    unknown_cases = [case for case in reconciled_cases
                     if case.get("outcome") == "unknown_native_unavailable"]
    mismatch_cases = [case for case in reconciled_cases
                      if case.get("outcome") == "raw_event_mismatch"]
    checks = {
        "source_report_readable": True,
        "bounded_slice_readable": True,
        "native_inspection_mapping_counts": mapping_counts_ok,
        "raw_native_headers_verified": len(mismatch_cases) == 0,
        "raw_action_unchanged_verified": all(
            case.get("action_unchanged") is True for case in verified_cases),
        "raw_dates_unchanged_verified": all(
            case.get("date_unchanged") is True for case in verified_cases),
        "unknown_country_queries_preserved": all(
            case.get("outcome") == "unknown_native_unavailable"
            for case in reconciled_cases
            if case.get("recipient") == "MOR"),
        "before_after_control_preserved": (
            (report.get("checks") or {}).get("paused_player_and_date_unchanged") is True),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "status": "passed" if all(checks.values()) else "failed",
        "kind": "offline_declare_war_details_reconciliation",
        "source_report": {
            "path": str(source_report),
            "bytes": source_report.stat().st_size,
            "sha256": hashlib.sha256(source_report.read_bytes()).hexdigest(),
        },
        "source_native_event_slice": {
            "path": str(slice_path),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "parsed_event_count": len(events),
            "malformed_line_count": malformed_lines,
            "inspection_event_count": len(inspections),
        },
        "session_id": report.get("session_id"),
        "actor": report.get("actor"),
        "phase": report.get("phase"),
        "recipients": report.get("recipients"),
        "summary": {
            "source_case_count": len(reconciled_cases),
            "raw_native_verified_count": len(verified_cases),
            "native_unavailable_unknown_count": len(unknown_cases),
            "raw_event_mismatch_count": len(mismatch_cases),
            "event_count_by_recipient": event_count_by_recipient,
        },
        "checks": checks,
        "cases": reconciled_cases,
    }
    write(output, result)
    print(json.dumps({
        "status": result["status"],
        "cases": len(reconciled_cases),
        "verified": len(verified_cases),
        "unknown": len(unknown_cases),
        "output": str(output),
    }, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reconcile-report", type=Path,
                        help="Reconcile an existing report against its bounded native slice.")
    parser.add_argument("--reconcile-output", type=Path,
                        help="Output path for offline reconciliation.")
    parser.add_argument("--recipients", nargs="+", default=list(_DEFAULT_RECIPIENTS),
                        type=lambda value: value.upper())
    args = parser.parse_args()
    if args.reconcile_report is not None:
        if args.installation is not None or args.output is not None:
            parser.error("RECONCILE_MODE_CANNOT_USE_INSTALLATION_OR_OUTPUT")
        output = args.reconcile_output or (
            args.reconcile_report.parent.parent
            / "r62-declarewar-details-query-reconciliation-20261019-001"
            / "report.json")
        return _reconcile_report(args.reconcile_report, output)
    if args.installation is None or args.output is None:
        parser.error("INSTALLATION_AND_OUTPUT_REQUIRED")
    recipients = _normalize_recipients(args.recipients)
    output = args.output.resolve()
    evidence = output.parent / (output.stem + "-evidence")
    if output.exists() or evidence.exists():
        raise SystemExit("OUTPUT_ALREADY_EXISTS")
    evidence.mkdir(parents=True)

    session = ObserverSession(args.installation, game_exe())
    report = {
        "status": "running",
        "installation": str(args.installation.resolve()),
        "session_id": session.session_id,
        "actor": _ACTOR,
        "phase": _PHASE,
        "recipients": recipients,
        "cases": [],
        "execute_call_count": 0,
        "advance_requested": False,
        "save_requested": False,
        "reload_requested": False,
        "query_only": True,
        "native_header_contract": {
            "event": "native_declare_war_inspection",
            "family": "declare_war",
            "action_id": "declare_war",
            "actor": _ACTOR,
            "phase": _PHASE,
            "session_id": "current_session",
            "date_raw": "before_health_date",
        },
        "candidate_policy": {
            "one_valid_candidate_per_casus_belli": True,
            "max_casus_belli_selections_per_recipient": 6,
        },
    }
    checks: dict[str, bool] = {}
    warnings: list[dict] = []
    log = session.directory / "control-probe.jsonl"
    start = log.stat().st_size
    before = None
    try:
        health = wait_runtime_ready(session, timeout=25, restore_minimized=True)
        if health.get("status") != "ready":
            raise RuntimeError("SESSION_NOT_READY")
        before = _control_from_probe(_run_probe(
            PROBE_SPECS[0], session.record["pid"], evidence / "before-control.json"))
        report["before"] = before
        expected_date = health.get("date_raw")
        if not _control_is_paused_por(before, expected_date):
            raise RuntimeError("PAUSED_POR_CONTEXT_REQUIRED")
        with DurableJournal(evidence / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            for recipient in recipients:
                discovery = _record_query(
                    api, evidence, report, checks, recipient, "discovery", {},
                    session.session_id, expected_date)
                no_cb_result = _record_query(
                    api, evidence, report, checks, recipient, "no-casus-belli",
                    _selection_parameters("no_casus_belli", -1, _ACTOR),
                    session.session_id, expected_date)
                no_cb_key = f"{recipient}_no-casus-belli_selection"
                no_cb_expected = (
                    no_cb_result.get("selection_matched") is True
                    and no_cb_result.get("requested_casus_belli") == "no_casus_belli"
                    and no_cb_result.get("requested_province_id") == -1
                    and no_cb_result.get("requested_beneficiary") == _ACTOR)
                checks[no_cb_key] = no_cb_expected or _unavailable(no_cb_result)
                for index, selected in enumerate(_candidate_selections(discovery), start=1):
                    candidate = selected.pop("candidate")
                    cb = selected["casus_belli"]
                    province = selected["war_goal"]["province_id"]
                    beneficiary = selected["war_goal"]["beneficiary"]
                    label = f"selected-{index}-{cb}-{province}-{beneficiary}"
                    row_result = _record_query(
                        api, evidence, report, checks, recipient, label, selected,
                        session.session_id, expected_date)
                    report["cases"][-1]["selected_candidate"] = candidate
                    report["cases"][-1]["selection_verified"] = (
                        isinstance(row_result, dict)
                        and row_result.get("selection_matched") is True
                        and row_result.get("requested_casus_belli") == cb
                        and row_result.get("requested_province_id") == province
                        and row_result.get("requested_beneficiary") == beneficiary)
                    selection_key = f"{recipient}_{_safe_name(label)}_selection"
                    checks[selection_key] = (
                        report["cases"][-1]["selection_verified"]
                        or _unavailable(row_result))
            write(output, report)
        after = _control_from_probe(_run_probe(
            PROBE_SPECS[0], session.record["pid"], evidence / "after-control.json"))
        report["after"] = after
        checks["paused_player_and_date_unchanged"] = before == after
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}:{error}")
    finally:
        report["checks"] = checks
        report["warnings"] = warnings
        length = log.stat().st_size - start
        if 0 <= length <= _SLICE_LIMIT:
            with log.open("rb") as stream:
                stream.seek(start)
                raw = stream.read(length)
            slice_path = evidence / "native-events-slice.jsonl"
            slice_path.write_bytes(raw)
            report["native_event_slice"] = {
                "path": str(slice_path),
                "bytes": length,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            inspections, malformed_lines = _parse_native_inspection_events(raw)
            reconciled = _native_case_reconciliation(report, inspections)
            verified_count = 0
            unknown_count = 0
            mismatch_count = 0
            for case, native_case in zip(report["cases"], reconciled):
                case["native_header_source"] = "native_event_slice"
                case["native_header"] = {
                    "available": native_case.get("native_event_available") is True,
                    "observed": native_case.get("raw_event"),
                    "unchanged": native_case.get("header_verified") is True,
                }
                case["native_unavailable"] = (
                    native_case.get("outcome") == "unknown_native_unavailable")
                case["native_action_unchanged"] = native_case.get("action_unchanged")
                case["native_date_unchanged"] = native_case.get("date_unchanged")
                key = f"{case.get('recipient')}_{_safe_name(case.get('label', 'case'))}"
                unknown = native_case.get("outcome") == "unknown_native_unavailable"
                checks[key + "_header"] = native_case.get("header_verified") is True or unknown
                if case.get("label") != "discovery":
                    checks[key + "_selection"] = (
                        native_case.get("selection_verified") is True or unknown)
                if native_case.get("outcome") == "verified":
                    verified_count += 1
                elif unknown:
                    unknown_count += 1
                else:
                    mismatch_count += 1
            report["native_header_reconciliation"] = {
                "inspection_event_count": len(inspections),
                "malformed_line_count": malformed_lines,
                "verified_case_count": verified_count,
                "unknown_case_count": unknown_count,
                "mismatch_case_count": mismatch_count,
            }
        else:
            report.update(status="failed", slice_error="BOUNDED_NATIVE_EVENT_SLICE_EXCEEDED")
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
