"""Read-only R66 Declare War CB and peace-rule query batch.

The runner binds every observation to one paused observer session.  It only
calls ``inspect_diplomatic_action`` and the catalog read; it never submits a
war, advances time, saves, or restarts the game.  Each native query gets a
bounded log slice so the public projection can be checked against the raw
``native_declare_war_inspection`` event without exposing private fields.
"""

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

from bridge.declarewar_peace_options import (  # noqa: E402
    project_native_peace_options,
    validate_native_peace_options,
)
from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_peace_concession_queries import (  # noqa: E402
    _control_from_probe,
    _control_is_paused_por,
)
from work.run_peace_empty_offer_queries import _has_private_fields  # noqa: E402
from work.validate_alliance_queries import PROBE_SPECS, _run_probe  # noqa: E402


ACTOR = "FRA"
PHASE = "initiate"
DEFAULT_RECIPIENTS = ("ENG", "MOR", "MLO")
TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
CB_RE = re.compile(r"[A-Za-z0-9_]{1,128}\Z")
MAX_SLICE_BYTES = 16 * 1024 * 1024
MAX_LINE_BYTES = 4 * 1024 * 1024


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _normalize_recipients(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        for raw in value.split(","):
            tag = raw.strip().upper()
            if TAG_RE.fullmatch(tag) is None or tag == ACTOR:
                raise SystemExit("RECIPIENT_INVALID")
            if tag not in result:
                result.append(tag)
    if not result:
        raise SystemExit("RECIPIENT_REQUIRED")
    return result


def _selection_parameters(casus_belli: str, province_id: int,
                           beneficiary: str) -> dict[str, object]:
    if CB_RE.fullmatch(casus_belli) is None:
        raise ValueError("CASUS_BELLI_INVALID")
    if isinstance(province_id, bool) or not isinstance(province_id, int):
        raise ValueError("PROVINCE_ID_INVALID")
    if province_id != -1 and province_id <= 0:
        raise ValueError("PROVINCE_ID_INVALID")
    if beneficiary != "---" and TAG_RE.fullmatch(beneficiary) is None:
        raise ValueError("BENEFICIARY_INVALID")
    return {
        "casus_belli": casus_belli,
        "war_goal": {
            "province_id": province_id,
            "beneficiary": beneficiary,
        },
        "call_allies": [],
    }


def _candidate_rows(result: object) -> list[dict[str, object]]:
    if not isinstance(result, dict):
        return []
    parameters = result.get("parameters")
    rows = parameters.get("candidates") if isinstance(parameters, dict) else None
    if not isinstance(rows, list):
        rows = result.get("candidates")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _valid_candidate(row: dict[str, object]) -> bool:
    cb = row.get("casus_belli_key")
    province = row.get("target_province_id")
    beneficiary = row.get("beneficiary_tag")
    return (
        isinstance(cb, str)
        and CB_RE.fullmatch(cb) is not None
        and row.get("casus_belli_key_verified") is True
        and isinstance(province, int)
        and not isinstance(province, bool)
        and (province == -1 or province > 0)
        and row.get("province_identifier_verified") is True
        and isinstance(beneficiary, str)
        and (beneficiary == "---" or TAG_RE.fullmatch(beneficiary) is not None)
        and row.get("beneficiary_identifier_verified") is True
    )


def _candidate_selections(result: object, recipient: str,
                          limit: int = 3) -> list[dict[str, object]]:
    """Choose distinct real CB rows, giving ENG's trade CB first priority."""

    rows: list[tuple[str, int, str, int, dict[str, object]]] = []
    for index, row in enumerate(_candidate_rows(result)):
        if _valid_candidate(row):
            rows.append((
                str(row["casus_belli_key"]),
                int(row["target_province_id"]),
                str(row["beneficiary_tag"]),
                index,
                row,
            ))
    rows.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    if recipient == "ENG":
        rows.sort(key=lambda item: (
            item[0] != "cb_trade_war_triggered",
            item[0], item[1], item[2], item[3],
        ))
    chosen: list[dict[str, object]] = []
    seen_cb: set[str] = set()
    for cb, province, beneficiary, _index, row in rows:
        if cb in seen_cb:
            continue
        seen_cb.add(cb)
        chosen.append({
            "casus_belli": cb,
            "war_goal": {
                "province_id": province,
                "beneficiary": beneficiary,
            },
            "call_allies": [],
            "candidate": row,
        })
        if len(chosen) >= limit:
            break
    return chosen


def _copy_bounded_slice(source: Path, start: int, destination: Path) -> dict[str, object]:
    """Copy one bounded append-only log range without loading it wholesale."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    copied = 0
    try:
        with source.open("rb") as stream, destination.open("wb") as output:
            stream.seek(max(0, start))
            while copied < MAX_SLICE_BYTES:
                chunk = stream.read(min(64 * 1024, MAX_SLICE_BYTES - copied))
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                copied += len(chunk)
    except OSError as error:
        return {
            "status": "failed",
            "error": f"{type(error).__name__}:{error}",
            "path": str(destination),
            "bytes": copied,
        }
    end_size = source.stat().st_size if source.exists() else start + copied
    return {
        "status": "ok",
        "path": str(destination),
        "start_offset": start,
        "end_offset": start + copied,
        "bytes": copied,
        "bounded": copied < MAX_SLICE_BYTES or end_size <= start + copied,
        "sha256": digest.hexdigest(),
    }


def _read_events(path: Path) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    total = 0
    with path.open("rb") as stream:
        while total < MAX_SLICE_BYTES and len(events) < 4096:
            line = stream.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            total += len(line)
            if len(line) > MAX_LINE_BYTES:
                continue
            try:
                value = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                events.append(value)
    return events


def _find_native_event(path: Path, recipient: str,
                       expected_date: object,
                       expected_selection: dict[str, object] | None) -> dict[str, object] | None:
    matches: list[dict[str, object]] = []
    for event in _read_events(path):
        if (
            event.get("event") == "native_declare_war_inspection"
            and event.get("family") == "declare_war"
            and event.get("action_id") == "declare_war"
            and event.get("actor") == ACTOR
            and event.get("recipient") == recipient
            and event.get("phase") == PHASE
            and event.get("date_raw") == expected_date
        ):
            if expected_selection is None:
                if event.get("selection_requested") in (False, None):
                    matches.append(event)
            elif (
                event.get("selection_requested") is True
                and event.get("requested_casus_belli") == expected_selection["casus_belli"]
                and event.get("requested_province_id") == expected_selection["province_id"]
                and event.get("requested_beneficiary") == expected_selection["beneficiary"]
            ):
                matches.append(event)
    return matches[-1] if matches else None


def _unavailable(result: object) -> bool:
    if not isinstance(result, dict):
        return False
    legality = result.get("legality")
    status = legality.get("status") if isinstance(legality, dict) else None
    return (
        status in {"unknown", "unavailable"}
        or result.get("status") in {"unknown", "unavailable"}
        or isinstance(result.get("error_code"), str)
    )


def _public_contract(result: object, recipient: str,
                     expected_date: object) -> bool:
    if not isinstance(result, dict):
        return False
    session = result.get("session")
    return (
        result.get("action_id") == "declare_war"
        and result.get("actor") == ACTOR
        and result.get("recipient") == recipient
        and result.get("phase") == PHASE
        and isinstance(session, dict)
        and session.get("date_raw") == expected_date
        and not _has_private_fields(result)
    )


def _selection_contract(result: object, expected: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(result, dict):
        return {
            "requested": expected is not None,
            "matched": False,
            "echo_verified": False,
            "explicit_unavailable": expected is not None,
        }
    if expected is None:
        return {
            "requested": result.get("selection_requested") is True,
            "matched": result.get("selection_matched") is False,
            "echo_verified": result.get("selection_requested") in (False, None),
            "explicit_unavailable": False,
        }
    echo_verified = (
        result.get("selection_requested") is True
        and result.get("requested_casus_belli") == expected["casus_belli"]
        and result.get("requested_province_id") == expected["province_id"]
        and result.get("requested_beneficiary") == expected["beneficiary"]
    )
    matched = result.get("selection_matched") is True
    return {
        "requested": result.get("selection_requested") is True,
        "matched": matched,
        "echo_verified": echo_verified,
        "explicit_unavailable": echo_verified and not matched and _unavailable(result),
    }


def _options_summary(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {
            "valid": False,
            "complete": False,
            "goal_double_sided_complete": False,
            "disabled_nonempty": False,
            "trade_power_disabled": False,
        }
    valid = validate_native_peace_options(raw)
    disabled = raw.get("disabled") if isinstance(raw.get("disabled"), dict) else {}
    attacker = raw.get("attacker_declared") if isinstance(raw.get("attacker_declared"), dict) else {}
    defender = raw.get("defender_declared") if isinstance(raw.get("defender_declared"), dict) else {}
    records = disabled.get("records") if isinstance(disabled.get("records"), list) else []
    trade_power_disabled = any(
        isinstance(row, dict)
        and row.get("kind") == 8
        and row.get("auxiliary_present") is False
        for row in records
    )
    return {
        "valid": valid,
        "complete": raw.get("complete") is True,
        "goal_double_sided_complete": (
            valid
            and attacker.get("complete") is True
            and defender.get("complete") is True
        ),
        "disabled_nonempty": bool(records),
        "trade_power_disabled": trade_power_disabled,
        "disabled_record_count": len(records),
        "attacker_record_count": len(attacker.get("records", []))
        if isinstance(attacker.get("records"), list) else 0,
        "defender_record_count": len(defender.get("records", []))
        if isinstance(defender.get("records"), list) else 0,
    }


def _native_summary(event: dict[str, object]) -> dict[str, object]:
    return {
        key: event.get(key)
        for key in (
            "event", "family", "action_id", "actor", "recipient", "phase",
            "session_id", "query_id", "date_raw", "object_unchanged",
            "selection_requested", "selection_matched", "selection_match_count",
            "requested_casus_belli", "requested_province_id",
            "requested_beneficiary",
        )
    }


def _catalog_contract(catalog: object) -> dict[str, object]:
    actions = catalog.get("actions") if isinstance(catalog, dict) else None
    if not isinstance(actions, list):
        return {"present": False, "acknowledged": False}
    row = next(
        (item for item in actions
         if isinstance(item, dict) and item.get("action_id") == "declare_war"),
        None,
    )
    phase = row.get("phases", {}).get("initiate", {}) if isinstance(row, dict) else {}
    return {
        "present": isinstance(row, dict),
        "query_peace_term_rules": phase.get("query_peace_term_rules"),
        "acknowledged": phase.get("query_peace_term_rules")
        == "native_declare_war_peace_options",
    }


def _record_case(api: DiplomacyTools, evidence: Path, report: dict[str, object],
                 log_path: Path, recipient: str, label: str,
                 parameters: dict[str, object], expected_selection: dict[str, object] | None,
                 session_id: str, expected_date: object) -> dict[str, object]:
    stem = _safe_name(f"{recipient}-{label}")
    input_path = evidence / "cases" / f"{stem}-input.json"
    public_path = evidence / "cases" / f"{stem}-public.json"
    slice_path = evidence / "cases" / f"{stem}-native.jsonl"
    _write_json(input_path, {
        "action_id": "declare_war",
        "actor": ACTOR,
        "recipient": recipient,
        "phase": PHASE,
        "parameters": parameters,
        "expected_selection": expected_selection,
    })
    start = log_path.stat().st_size if log_path.exists() else 0
    error: str | None = None
    try:
        result = api.inspect_diplomatic_action(
            "declare_war", ACTOR, recipient, phase=PHASE, parameters=parameters)
    except Exception as exc:  # preserve the failed query as bounded evidence
        result = {"status": "unknown", "error": f"{type(exc).__name__}:{exc}"}
        error = result["error"]
    _write_json(public_path, result)
    slice_info = _copy_bounded_slice(log_path, start, slice_path)
    native = _find_native_event(slice_path, recipient, expected_date, expected_selection)
    native_valid = False
    if isinstance(native, dict):
        native_valid = ObserverSession._valid_native_declare_war_inspection(
            native,
            "declare_war",
            ACTOR,
            recipient,
            PHASE,
            expected_date,
            expected_query_id=None,
            expected_session_id=session_id,
            expected_selection=expected_selection,
        )
    raw_options = native.get("native_peace_options") if isinstance(native, dict) else None
    options_public = project_native_peace_options(raw_options)
    public_rules = result.get("peace_term_rules") if isinstance(result, dict) else None
    options_valid = validate_native_peace_options(raw_options)
    options_parity = options_valid and options_public is not None and options_public == public_rules
    selection = _selection_contract(result, expected_selection)
    public_ok = _public_contract(result, recipient, expected_date)
    object_unchanged = (
        isinstance(native, dict)
        and native.get("object_unchanged") is True
        and isinstance(result, dict)
        # ``object_unchanged`` is a native provenance field.  Older public
        # projections intentionally omit it; if a producer exposes it, it
        # must agree with the native proof.
        and ("object_unchanged" not in result
             or result.get("object_unchanged") is True)
    )
    explicit_unavailable = bool(selection["explicit_unavailable"])
    selected_success = expected_selection is None or selection["matched"]
    checks = {
        "native_header_and_validator": native_valid,
        "native_session_query_date_actor_recipient": (
            isinstance(native, dict)
            and isinstance(native.get("query_id"), str)
            and bool(native.get("query_id"))
            and native.get("session_id") == session_id
            and native.get("date_raw") == expected_date
            and native.get("actor") == ACTOR
            and native.get("recipient") == recipient
        ),
        "object_unchanged": object_unchanged,
        "peace_options_valid": options_valid,
        "peace_options_public_parity": options_parity,
        "public_no_private_fields": public_ok,
        "selection_echo": selection["echo_verified"],
        "selection_matched_or_discovery": selected_success,
        "unavailable_is_explicit": not explicit_unavailable or not selected_success,
    }
    if expected_selection is None:
        # Default discovery intentionally has no selected clone.  It must be
        # a valid default inspection, while its legality may remain unknown.
        checks["selection_matched_or_discovery"] = selection["echo_verified"]
    case_status = "passed" if all(checks.values()) else (
        "unavailable" if explicit_unavailable and not selected_success else "failed")
    row: dict[str, object] = {
        "label": label,
        "recipient": recipient,
        "parameters": parameters,
        "expected_selection": expected_selection,
        "status": case_status,
        "public_status": (
            result.get("legality", {}).get("status")
            if isinstance(result, dict) and isinstance(result.get("legality"), dict)
            else result.get("status") if isinstance(result, dict) else None
        ),
        "public_path": str(public_path),
        "input_path": str(input_path),
        "native_slice": slice_info,
        "native_event": _native_summary(native) if isinstance(native, dict) else None,
        "native_options": _options_summary(raw_options),
        "selection": selection,
        "explicit_unavailable": explicit_unavailable,
        "checks": checks,
    }
    if error is not None:
        row["error"] = error
    report.setdefault("cases", []).append(row)
    return row


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--recipients",
        nargs="+",
        default=list(DEFAULT_RECIPIENTS),
        type=lambda value: value.upper(),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    recipients = _normalize_recipients(args.recipients)
    output = args.output.expanduser().resolve()
    evidence = output.parent / f"{output.stem}-evidence"
    if output.exists() or evidence.exists():
        raise SystemExit("OUTPUT_ALREADY_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True)
    (evidence / "cases").mkdir()
    installation = args.installation.expanduser().resolve(strict=True)

    report: dict[str, object] = {
        "status": "running",
        "schema": "r66_declare_war_cb_rule_queries_v1",
        "mode": "prepare_only_read_only_queries",
        "installation": str(installation),
        "actor": ACTOR,
        "phase": PHASE,
        "recipients": recipients,
        "cases": [],
        "query_call_count": 0,
        "execute_call_count": 0,
        "advance_requested": False,
        "save_requested": False,
        "restart_requested": False,
        "business_submission": False,
        "candidate_policy": {
            "max_distinct_casus_belli_per_recipient": 3,
            "eng_trade_casus_belli_priority": "cb_trade_war_triggered",
            "selection_source": "validated_discovery_candidates",
        },
    }
    checks: dict[str, bool] = {}
    session: ObserverSession | None = None
    log_path: Path | None = None
    try:
        session = ObserverSession(installation, game_exe())
        report["session"] = {
            key: session.record.get(key)
            for key in ("pid", "session_id", "experiment_id", "dll_sha256")
        }
        before_health = wait_runtime_ready(session, restore_minimized=True)
        before_probe = _run_probe(
            PROBE_SPECS[0], session.record["pid"], evidence / "before-control.json")
        before_control = _control_from_probe(before_probe)
        expected_date = before_health.get("date_raw")
        report["before"] = {
            "health": before_health,
            "control": before_control,
        }
        checks["before_por_paused"] = (
            before_health.get("status") == "ready"
            and _control_is_paused_por(before_control, expected_date)
        )
        if not checks["before_por_paused"]:
            raise RuntimeError("BASELINE_NOT_READY_POR_PAUSED")
        log_path = session.directory / "control-probe.jsonl"
        with DurableJournal(
            evidence / "diplomacy.sqlite3",
            session.experiment_id,
            session.session_id,
            global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            catalog = api.list_diplomatic_actions(ACTOR, "ENG")
            _write_json(evidence / "action-catalog.json", catalog)
            catalog_info = _catalog_contract(catalog)
            report["action_catalog"] = catalog_info
            checks["catalog_query_peace_term_rules"] = (
                catalog_info.get("acknowledged") is True
            )

            for recipient in recipients:
                discovery = _record_case(
                    api, evidence, report, log_path, recipient, "discovery", {},
                    None, session.session_id, expected_date,
                )
                report["query_call_count"] = int(report["query_call_count"]) + 1
                discovery_public_path = Path(str(discovery["public_path"]))
                try:
                    discovery_result = json.loads(
                        discovery_public_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    discovery_result = {}

                no_cb = _selection_parameters("no_casus_belli", -1, ACTOR)
                no_cb_row = _record_case(
                    api, evidence, report, log_path, recipient, "no-casus-belli",
                    no_cb,
                    {
                        "casus_belli": "no_casus_belli",
                        "province_id": -1,
                        "beneficiary": ACTOR,
                    },
                    session.session_id,
                    expected_date,
                )
                report["query_call_count"] = int(report["query_call_count"]) + 1
                # Keep a direct summary for finalization; the full result is in
                # the case artifact and the raw event is in its bounded slice.
                no_cb_row["explicit_no_casus_belli"] = True

                for index, selected in enumerate(
                    _candidate_selections(discovery_result, recipient), start=1
                ):
                    candidate = selected.pop("candidate")
                    selection = {
                        "casus_belli": str(selected["casus_belli"]),
                        "province_id": int(selected["war_goal"]["province_id"]),
                        "beneficiary": str(selected["war_goal"]["beneficiary"]),
                    }
                    label = (
                        f"selected-{index}-{selection['casus_belli']}-"
                        f"{selection['province_id']}-{selection['beneficiary']}"
                    )
                    row = _record_case(
                        api, evidence, report, log_path, recipient, label,
                        selected, selection, session.session_id, expected_date,
                    )
                    row["selected_candidate"] = candidate
                    row["selected_from_discovery"] = True
                    report["query_call_count"] = int(report["query_call_count"]) + 1

        after_health = wait_runtime_ready(session, restore_minimized=True)
        after_probe = _run_probe(
            PROBE_SPECS[0], session.record["pid"], evidence / "after-control.json")
        after_control = _control_from_probe(after_probe)
        report["after"] = {
            "health": after_health,
            "control": after_control,
        }
        checks["after_por_paused_same_date"] = (
            after_health.get("status") == "ready"
            and _control_is_paused_por(after_control, expected_date)
            and before_control == after_control
            and after_health.get("date_raw") == expected_date
        )
        cases = report["cases"] if isinstance(report.get("cases"), list) else []
        case_rows = [row for row in cases if isinstance(row, dict)]
        checks["all_native_public_parity"] = all(
            row.get("checks", {}).get("peace_options_public_parity") is True
            and row.get("checks", {}).get("native_header_and_validator") is True
            and row.get("checks", {}).get("public_no_private_fields") is True
            for row in case_rows
        )
        selected_rows = [
            row for row in case_rows
            if isinstance(row.get("expected_selection"), dict)
        ]
        checks["selected_requests_matched"] = all(
            row.get("selection", {}).get("matched") is True
            for row in selected_rows
        )
        checks["unmatched_requests_explicit_unavailable"] = all(
            row.get("status") != "passed"
            for row in selected_rows
            if row.get("selection", {}).get("explicit_unavailable") is True
        )
        option_summaries = [
            row.get("native_options") for row in case_rows
            if isinstance(row.get("native_options"), dict)
        ]
        checks["goal_double_sided_complete"] = any(
            summary.get("goal_double_sided_complete") is True
            for summary in option_summaries
        )
        checks["disabled_table_nonempty"] = any(
            summary.get("disabled_nonempty") is True
            for summary in option_summaries
        )
        eng_rows = [row for row in case_rows if row.get("recipient") == "ENG"]
        trade_discovery = any(
            isinstance(row.get("selected_candidate"), dict)
            and row["selected_candidate"].get("casus_belli_key")
            == "cb_trade_war_triggered"
            for row in eng_rows
        )
        trade_present = any(
            isinstance(candidate, dict)
            and candidate.get("casus_belli_key") == "cb_trade_war_triggered"
            for row in eng_rows
            for candidate in (
                _candidate_rows(json.loads(Path(str(row["public_path"])).read_text(encoding="utf-8")))
                if isinstance(row.get("public_path"), str) and Path(str(row["public_path"])).is_file()
                else []
            )
        )
        checks["eng_trade_candidate_selected_if_present"] = (
            not trade_present or trade_discovery
        )
        checks["no_business_submission"] = (
            report["execute_call_count"] == 0
            and report["business_submission"] is False
            and report["advance_requested"] is False
            and report["save_requested"] is False
            and report["restart_requested"] is False
        )
        report["summary"] = {
            "case_count": len(case_rows),
            "passed_case_count": sum(row.get("status") == "passed" for row in case_rows),
            "unavailable_case_count": sum(row.get("status") == "unavailable" for row in case_rows),
            "failed_case_count": sum(row.get("status") == "failed" for row in case_rows),
            "selected_case_count": len(selected_rows),
            "selected_matched_count": sum(
                row.get("selection", {}).get("matched") is True
                for row in selected_rows
            ),
            "recipients": recipients,
        }
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        report["checks"] = checks
        report["query_only"] = True
        _write_json(output, report)
    print(json.dumps({
        "status": report.get("status"),
        "report": str(output),
        "cases": len(report.get("cases", [])) if isinstance(report.get("cases"), list) else 0,
        "failed_checks": [key for key, value in checks.items() if value is not True],
    }, ensure_ascii=False))
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
