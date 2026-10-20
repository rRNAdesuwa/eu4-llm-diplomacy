#!/usr/bin/env python3
"""Run one bounded, read-only batch of Peace consequence inspections.

The operator discovers the single FRA--recipient war and then queries white
peace, money, and cede-province terms in both demand and offer directions.
Province selections are made only from the native candidate rows returned by
the same paused session.  Every selected query is paired with a bounded raw
event slice and checked through the production consequence validator and
public projection.  No offer is submitted, time is advanced, or save is made.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from bridge.peace_consequences import (  # noqa: E402
    project_native_consequences,
    project_event_consequences,
    validate_native_consequences,
)
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_peace_concession_queries import (  # noqa: E402
    _control_from_probe,
    _control_is_paused_por,
)
from work.run_peace_empty_offer_queries import (  # noqa: E402
    _has_private_fields,
    _single_discovered_war_id,
)
from work.run_royal_marriage_execution import _installation_binding  # noqa: E402
from work.validate_alliance_queries import PROBE_SPECS, _run_probe  # noqa: E402


_ACTOR = "FRA"
_PLAYER_SLOT = 189  # POR in the observer fixture
_WAR_ID = re.compile(r"war_[0-9a-f]{16}_[0-9a-f]{8}\Z")
_TAG = re.compile(r"[A-Z0-9]{3}\Z")
_MAX_CASE_SLICE = 4 * 1024 * 1024
_MAX_LINE = 2 * 1024 * 1024
_MONEY_AMOUNT = "10.0"
_MAX_PROVINCE_SELECTIONS = 16


class ConsequenceQueryError(RuntimeError):
    """A bounded setup or evidence error; no business operation is retried."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _output_paths(requested: Path) -> tuple[Path, Path]:
    target = requested.expanduser().resolve()
    if target.exists():
        raise ConsequenceQueryError("OUTPUT_ALREADY_EXISTS", str(target))
    if target.suffix.casefold() == ".json":
        report = target
        evidence = target.parent / f"{target.stem}-evidence"
    else:
        report = target / "report.json"
        evidence = target
    if report.exists() or evidence.exists():
        raise ConsequenceQueryError("OUTPUT_ALREADY_EXISTS", str(report))
    evidence.mkdir(parents=True, exist_ok=False)
    return report, evidence


def _money_raw(value: str) -> int:
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ConsequenceQueryError("MONEY_AMOUNT_INVALID", value) from error
    if (not amount.is_finite() or amount <= 0
            or amount.as_tuple().exponent < -1):
        raise ConsequenceQueryError("MONEY_AMOUNT_INVALID", value)
    raw = amount * Decimal(1000)
    if raw != raw.to_integral_value():
        raise ConsequenceQueryError("MONEY_AMOUNT_INVALID", value)
    result = int(raw)
    if result <= 0 or result > 2_147_483_647 or result % 100:
        raise ConsequenceQueryError("MONEY_AMOUNT_INVALID", value)
    return result


def _compact_probe(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {"status": "unknown"}
    return {
        "status": value.get("status"),
        "name": value.get("name"),
        "script": value.get("script"),
        "snapshot_path": value.get("snapshot_path"),
        "snapshot_completeness": value.get("snapshot_completeness"),
    }


def _bounded_text(value: object, limit: int = 128) -> str | None:
    if not isinstance(value, str):
        return None
    return value if len(value) <= limit else value[:limit]


def _candidate_rows(value: object, beneficiary: str | None = None) -> list[dict[str, object]]:
    native = value.get("native_provinces") if isinstance(value, dict) else None
    rows = native.get("candidates") if isinstance(native, dict) else None
    if not isinstance(rows, list):
        return []
    result: list[dict[str, object]] = []
    seen: set[int] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        province_id = row.get("province_id")
        actual_beneficiary = row.get("beneficiary")
        if (isinstance(province_id, bool) or not isinstance(province_id, int)
                or province_id <= 0 or province_id in seen
                or not isinstance(actual_beneficiary, str)
                or _TAG.fullmatch(actual_beneficiary) is None):
            continue
        if beneficiary is not None and actual_beneficiary != beneficiary:
            continue
        # An explicit native selectability=false is a reason to leave the
        # candidate out.  An unchecked row remains an observed candidate and
        # will be tested through the selected query itself.
        if (row.get("native_selectability_checked") is True
                and row.get("native_selectable") is not True):
            continue
        seen.add(province_id)
        result.append(row)
    return result


def _candidate_summary(row: dict[str, object]) -> dict[str, object]:
    return {
        key: row.get(key)
        for key in (
            "province_id", "beneficiary", "selected", "name_readable",
            "name_truncated", "native_selectability_checked",
            "native_selectable",
        )
        if key in row
    }


def _copy_bounded_slice(log: Path, start: int, destination: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    copied = 0
    try:
        with log.open("rb") as source, destination.open("xb") as output:
            source.seek(0, 2)
            initial_size = source.tell()
            if initial_size < start:
                return {"status": "unknown", "reason": "LOG_TRUNCATED",
                        "start_offset": start}
            source.seek(start)
            while copied < _MAX_CASE_SLICE:
                chunk = source.read(min(64 * 1024, _MAX_CASE_SLICE - copied))
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                copied += len(chunk)
            source.seek(0, 2)
            end_size = source.tell()
    except OSError as error:
        return {"status": "unknown", "reason": "LOG_SLICE_FAILED",
                "error": str(error)}
    return {
        "status": "ok",
        "start_offset": start,
        "end_offset": start + copied,
        "bytes": copied,
        "bounded": copied >= _MAX_CASE_SLICE,
        "complete": end_size <= start + copied,
        "sha256": digest.hexdigest(),
    }


def _read_slice_events(path: Path) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    with path.open("rb") as stream:
        # A single native query emits private provenance rows before the final
        # public inspection event.  The old 64-row cap could stop before that
        # terminal event in a bounded slice and made a valid query look absent.
        # The slice itself is capped by _MAX_CASE_SLICE, so this remains a
        # bounded read while allowing the complete event sequence through.
        while len(events) < 4096:
            line = stream.readline(_MAX_LINE + 1)
            if not line:
                break
            if len(line) > _MAX_LINE:
                continue
            try:
                value = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                events.append(value)
    return events


def _matching_event(path: Path, *, action_id: str, actor: str,
                    recipient: str, direction: str, war_id: str) -> dict[str, object] | None:
    event_names = {
        "white_peace": "native_peace_empty_offer_inspection",
        "demand_ducats": "native_peace_money_offer_inspection",
        "cede_province": "native_peace_province_offer_inspection",
    }
    matches: list[dict[str, object]] = []
    for event in _read_slice_events(path):
        name = event.get("event")
        if (event.get("action_id") == action_id
                and event.get("actor") == actor
                and event.get("recipient") == recipient
                and event.get("direction") == direction
                and event.get("war_id") == war_id
                and event.get("family") == "peace"
                and name == event_names.get(action_id)):
            matches.append(event)
    return matches[-1] if matches else None


def _public_contract(value: object, action_id: str, actor: str,
                     recipient: str, war_id: str, direction: str) -> bool:
    if not isinstance(value, dict):
        return False
    if any(value.get(key) != expected for key, expected in (
            ("family", "peace"), ("action_id", action_id),
            ("actor", actor), ("recipient", recipient),
            ("phase", "initiate"), ("selected_war_id", war_id))):
        return False
    context = value.get("peace_context")
    return (
        isinstance(context, dict)
        and context.get("war_id") == war_id
        and context.get("direction") == direction
        and isinstance(context.get("terms"), list)
        and isinstance(value.get("peace_consequences"), dict)
    )


def _raw_header_contract(event: object, *, action_id: str, actor: str,
                         recipient: str, direction: str, war_id: str,
                         expected_date: object,
                         session_id: str) -> bool:
    if not isinstance(event, dict):
        return False
    if (not isinstance(event.get("query_id"), str)
            or not event.get("query_id")
            or len(event["query_id"]) > 128):
        return False
    return all(event.get(key) == expected for key, expected in (
        ("family", "peace"), ("action_id", action_id), ("actor", actor),
        ("recipient", recipient), ("phase", "initiate"),
        ("direction", direction), ("war_id", war_id),
        ("date_raw", expected_date),
        ("session_id", session_id), ("identity_scope", "observer_session"),
    ))


def _native_validator(event: dict[str, object], *, action_id: str,
                      actor: str, recipient: str, direction: str,
                      war_id: str, expected_date: object, query_id: str,
                      session_id: str, amount_raw: int | None,
                      province_ids: list[int] | None,
                      beneficiary: str | None) -> bool:
    if action_id == "white_peace":
        return ObserverSession._valid_native_peace_empty_offer_inspection(
            event, "white_peace", actor, recipient, "initiate", expected_date,
            war_id, query_id, session_id, expected_direction=direction)
    if action_id == "demand_ducats":
        if amount_raw is None:
            return False
        return ObserverSession._valid_native_peace_money_offer_inspection(
            event, "demand_ducats", actor, recipient, "initiate", expected_date,
            {"war_id": war_id, "direction": direction,
             "amount_raw": amount_raw, "payer": (actor if direction == "offer"
                                                   else recipient),
             "claimant": (recipient if direction == "offer" else actor)},
            query_id, session_id)
    if action_id == "cede_province":
        return ObserverSession._valid_native_peace_province_offer_inspection(
            event, "cede_province", actor, recipient, "initiate", expected_date,
            {"war_id": war_id, "direction": direction,
             "province_ids": province_ids or [], "beneficiary": beneficiary},
            query_id, session_id)
    return False


def _consequence_summary(value: object) -> dict[str, object]:
    consequences = value if isinstance(value, dict) else {}
    ae = consequences.get("aggressive_expansion")
    dip = consequences.get("diplomatic_power")
    coalition = consequences.get("coalition")
    territorial = consequences.get("territorial")
    coalition_rows = coalition.get("countries") if isinstance(coalition, dict) else []
    territorial_rows = territorial if isinstance(territorial, list) else []
    coalition_rows = coalition_rows if isinstance(coalition_rows, list) else []
    return {
        "complete": consequences.get("complete"),
        "aggressive_expansion": {
            "available": ae.get("available") if isinstance(ae, dict) else None,
            "maximum_raw": ae.get("maximum_raw") if isinstance(ae, dict) else None,
            "scale": ae.get("scale") if isinstance(ae, dict) else None,
            "coalition_possible": (ae.get("coalition_possible")
                                   if isinstance(ae, dict) else None),
        },
        "diplomatic_power": {
            "country": dip.get("country") if isinstance(dip, dict) else None,
            "available": dip.get("available") if isinstance(dip, dict) else None,
            "value": dip.get("value") if isinstance(dip, dict) else None,
            "unit": dip.get("unit") if isinstance(dip, dict) else None,
        },
        "territorial": [
            {
                "country": row.get("country"),
                "administrative_power": row.get("administrative_power"),
                "overextension_added_raw": row.get("overextension_added_raw"),
                "scale": row.get("scale"),
                "complete": row.get("complete"),
                "province_count": (len(row.get("provinces", []))
                                   if isinstance(row.get("provinces"), list)
                                   else None),
            }
            for row in territorial_rows if isinstance(row, dict)
        ],
        "coalition": {
            "available": coalition.get("available") if isinstance(coalition, dict) else None,
            "complete": coalition.get("complete") if isinstance(coalition, dict) else None,
            "native_count": coalition.get("native_count") if isinstance(coalition, dict) else None,
            "countries": [
                {
                    "tag": row.get("tag"),
                    "aggressive_expansion_delta": row.get("aggressive_expansion_delta"),
                    "current_value": row.get("current_value"),
                }
                for row in coalition_rows if isinstance(row, dict)
            ],
        },
    }


def _coverage(cases: list[dict[str, object]]) -> dict[str, object]:
    valid = [row for row in cases if row.get("consequence_contract") is True]
    fields: dict[str, dict[str, list[str]]] = {}
    for field in ("aggressive_expansion", "diplomatic_power", "territorial", "coalition"):
        fields[field] = {"zero": [], "nonzero": [], "unknown": []}
    for row in valid:
        name = str(row.get("name"))
        summary = row.get("consequence_summary")
        if not isinstance(summary, dict):
            continue
        ae = summary.get("aggressive_expansion")
        if (isinstance(ae, dict) and ae.get("available") is True
                and isinstance(ae.get("maximum_raw"), int)):
            fields["aggressive_expansion"][
                "zero" if ae["maximum_raw"] == 0 else "nonzero"].append(name)
        else:
            fields["aggressive_expansion"]["unknown"].append(name)
        dip = summary.get("diplomatic_power")
        if (isinstance(dip, dict) and dip.get("available") is True
                and isinstance(dip.get("value"), int)):
            fields["diplomatic_power"]["zero" if dip["value"] == 0 else "nonzero"].append(name)
        else:
            fields["diplomatic_power"]["unknown"].append(name)
        territorial = summary.get("territorial")
        if (isinstance(territorial, list)
                and summary.get("complete") is True
                and all(isinstance(item, dict) and item.get("complete") is True
                        for item in territorial)):
            has_nonzero = any(
                isinstance(item, dict)
                and ((isinstance(item.get("administrative_power"), int)
                      and item["administrative_power"] != 0)
                     or (isinstance(item.get("overextension_added_raw"), int)
                         and item["overextension_added_raw"] != 0))
                for item in territorial)
            fields["territorial"]["nonzero" if has_nonzero else "zero"].append(name)
        else:
            fields["territorial"]["unknown"].append(name)
        coalition = summary.get("coalition")
        rows = coalition.get("countries") if isinstance(coalition, dict) else None
        if (isinstance(rows, list) and isinstance(coalition, dict)
                and coalition.get("complete") is True):
            fields["coalition"]["nonzero" if rows else "zero"].append(name)
        else:
            fields["coalition"]["unknown"].append(name)
    for field, states in fields.items():
        states["status"] = (
            "covered_zero_and_nonzero" if states["zero"] and states["nonzero"]
            else "covered_zero_only" if states["zero"]
            else "covered_nonzero_only" if states["nonzero"]
            else "unknown")
    return {"valid_case_count": len(valid), "by_field": fields}


_OFFLINE_CASES = (
    "demand-white-peace",
    "demand-money",
    "demand-province-candidates",
)


def _offline_recompute(source_report_path: Path, output: Path) -> int:
    """Revalidate existing bounded evidence without contacting the game.

    This is intentionally limited to the three C002 cases that have complete
    native slices.  It does not turn missing selected-province or offer cases
    into successes, and it never opens an ObserverSession.
    """
    report_path: Path | None = None
    try:
        source_report_path = source_report_path.expanduser().resolve(strict=True)
        source = json.loads(source_report_path.read_text(encoding="utf-8"))
        if not isinstance(source, dict):
            raise ConsequenceQueryError("SOURCE_REPORT_INVALID", "report is not an object")
        report_path, evidence = _output_paths(output)
        actor = source.get("actor")
        recipient = source.get("recipient")
        war_id = source.get("war_id")
        expected_date = source.get("expected_date_raw")
        session_record = source.get("session")
        if not isinstance(session_record, dict):
            session_record = {}
        installation_record = source.get("installation")
        if not isinstance(installation_record, dict):
            installation_record = {}
        session_id = session_record.get("session_id") or installation_record.get("session_id")
        if not all(isinstance(value, str) and value for value in
                   (actor, recipient, war_id, session_id)):
            raise ConsequenceQueryError(
                "SOURCE_REPORT_HEADER_INCOMPLETE",
                "actor/recipient/war/session binding is incomplete",
            )
        source_cases = source.get("cases")
        if not isinstance(source_cases, list):
            raise ConsequenceQueryError("SOURCE_CASES_INVALID", "cases is not a list")
        by_name = {
            row.get("name"): row for row in source_cases
            if isinstance(row, dict) and isinstance(row.get("name"), str)
        }
        codec = source.get("native_text_codec")
        if not isinstance(codec, str):
            codec = session_record.get("native_text_codec")
        if not isinstance(codec, str):
            codec = "utf8"
        report: dict[str, object] = {
            "validator": Path(__file__).name,
            "version": 1,
            "mode": "offline_recompute_existing_peace_consequence_evidence",
            "status": "running",
            "source_report": str(source_report_path),
            "source_batch_status": source.get("status"),
            "live_query_replayed": False,
            "business_submission": False,
            "save_requested": False,
            "advance_requested": False,
            "restart_requested": False,
            "actor": actor,
            "recipient": recipient,
            "war_id": war_id,
            "expected_date_raw": expected_date,
            "session": {
                "session_id": session_id,
                "pid": session_record.get("pid") or installation_record.get("pid"),
                "experiment_id": session_record.get("experiment_id")
                or installation_record.get("experiment_id"),
            },
            "cases": [],
            "unobserved_cases": [
                name for name in by_name
                if name not in _OFFLINE_CASES
                or not isinstance(by_name[name].get("native_slice"), dict)
                or not by_name[name]["native_slice"].get("bytes")
            ],
        }
        _write_json(evidence / "offline-input.json", {
            "source_report": str(source_report_path),
            "source_cases": list(_OFFLINE_CASES),
            "note": "references existing bounded slices; no live query was issued",
        })
        for name in _OFFLINE_CASES:
            parent = by_name.get(name)
            row: dict[str, object] = {
                "name": name,
                "parent_case": name,
                "offline_recomputed": True,
                "raw_slice_reused": False,
                "public_reused": False,
                "status": "failed",
            }
            if not isinstance(parent, dict):
                row["error"] = "PARENT_CASE_MISSING"
                report["cases"].append(row)
                continue
            input_path = Path(str(parent.get("input_path", "")))
            public_path = Path(str(parent.get("public_path", "")))
            native_slice = parent.get("native_slice")
            if (not input_path.is_file() or not public_path.is_file()
                    or not isinstance(native_slice, dict)
                    or not native_slice.get("bytes")):
                row["error"] = "PARENT_EVIDENCE_INCOMPLETE"
                row["input_path"] = str(input_path)
                row["public_path"] = str(public_path)
                report["cases"].append(row)
                continue
            try:
                input_record = json.loads(input_path.read_text(encoding="utf-8"))
                public = json.loads(public_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                row["error"] = f"PARENT_JSON_INVALID:{type(error).__name__}"
                report["cases"].append(row)
                continue
            action_id = input_record.get("action_id")
            direction = input_record.get("direction")
            expected_amount_raw = input_record.get("expected_amount_raw")
            province_ids = input_record.get("expected_province_ids")
            beneficiary = input_record.get("expected_beneficiary")
            if not isinstance(province_ids, list):
                province_ids = []
            raw_path = input_path.parent / "native-events-slice.jsonl"
            raw_event = _matching_event(
                raw_path, action_id=action_id, actor=actor, recipient=recipient,
                direction=direction, war_id=war_id)
            row.update({
                "action_id": action_id,
                "direction": direction,
                "input_path": str(input_path),
                "public_path": str(public_path),
                "native_slice_path": str(raw_path),
                "native_query_id": raw_event.get("query_id")
                if isinstance(raw_event, dict) else None,
                "raw_slice_reused": raw_event is not None,
                "public_reused": isinstance(public, dict),
            })
            raw_header = _raw_header_contract(
                raw_event, action_id=action_id, actor=actor, recipient=recipient,
                direction=direction, war_id=war_id, expected_date=expected_date,
                session_id=session_id)
            raw_for_validator = raw_event
            if (isinstance(raw_event, dict) and isinstance(public, dict)
                    and "native_evaluation" not in public
                    and "native_evaluation" in raw_event):
                raw_for_validator = dict(raw_event)
                raw_for_validator.pop("native_evaluation", None)
            native_valid = (
                isinstance(raw_for_validator, dict)
                and isinstance(action_id, str)
                and isinstance(direction, str)
                and _native_validator(
                    raw_for_validator, action_id=action_id, actor=actor,
                    recipient=recipient, direction=direction, war_id=war_id,
                    expected_date=expected_date,
                    query_id=(raw_event.get("query_id")
                              if isinstance(raw_event, dict) else ""),
                    session_id=session_id, amount_raw=expected_amount_raw
                    if isinstance(expected_amount_raw, int) else None,
                    province_ids=province_ids, beneficiary=beneficiary))
            raw_consequences = (raw_event.get("native_consequences")
                                if isinstance(raw_event, dict) else None)
            consequence_valid = validate_native_consequences(raw_consequences)
            projected = (project_native_consequences(raw_consequences, codec=codec)
                         if consequence_valid else None)
            public_consequences = (public.get("peace_consequences")
                                   if isinstance(public, dict) else None)
            parity = consequence_valid and projected == public_consequences
            public_contract = (
                isinstance(action_id, str) and isinstance(direction, str)
                and _public_contract(
                    public, action_id, actor, recipient, war_id, direction))
            object_unchanged = (
                isinstance(public, dict)
                and public.get("object_unchanged") is True
                and isinstance(raw_event, dict)
                and raw_event.get("object_unchanged") is True)
            private_absent = isinstance(public, dict) and not _has_private_fields(public)
            checks = {
                "public_contract": public_contract,
                "raw_header_contract": raw_header,
                "native_validator": native_valid,
                "consequence_validator": consequence_valid,
                "raw_public_parity": parity,
                "object_unchanged": object_unchanged,
                "public_queries_no_private_identifiers": private_absent,
            }
            row.update(checks)
            row["consequence_contract"] = consequence_valid
            row["raw_public_parity"] = parity
            row["private_fields_absent"] = private_absent
            row["consequence_summary"] = (
                _consequence_summary(public_consequences)
                if consequence_valid else None)
            row["status"] = "passed" if all(checks.values()) else "failed"
            report["cases"].append(row)
        case_rows = report["cases"]
        observed_passed = [row for row in case_rows if row.get("status") == "passed"]
        report["checks"] = {
            "source_report_present": True,
            "exact_parent_cases_selected": len(case_rows) == len(_OFFLINE_CASES),
            "three_parent_cases_recomputed": len(observed_passed) == len(_OFFLINE_CASES),
            "no_live_query_or_business_action": True,
            "unobserved_cases_kept_unknown": bool(report["unobserved_cases"]),
        }
        report["coverage"] = _coverage(case_rows)
        report["scope"] = {
            "observed_cases": list(_OFFLINE_CASES),
            "observed_case_count": len(case_rows),
            "passed_case_count": len(observed_passed),
            "batch_complete": False,
            "selected_province_and_offer_cases_not_replayed": True,
        }
        report["status"] = (
            "passed_partial"
            if all(report["checks"].values()) else "failed")
    except Exception as error:
        report = locals().get("report", {
            "validator": Path(__file__).name,
            "mode": "offline_recompute_existing_peace_consequence_evidence",
        })
        report["status"] = "failed"
        report["error"] = {
            "code": error.code if isinstance(error, ConsequenceQueryError)
            else "UNEXPECTED_OFFLINE_RECOMPUTE_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if report_path is not None:
            _write_json(report_path, report)
    print(json.dumps({
        "status": report.get("status"),
        "report": str(report_path) if report_path else None,
        "observed_cases": report.get("scope", {}).get("observed_case_count")
        if isinstance(report.get("scope"), dict) else None,
        "failed_checks": [key for key, value in report.get("checks", {}).items()
                          if value is not True],
    }, ensure_ascii=False))
    return 0 if report.get("status") == "passed_partial" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path,
                        help="live installation manifest for a new read-only batch")
    parser.add_argument(
        "--offline-report", type=Path,
        help="existing report.json whose bounded evidence is revalidated offline",
    )
    parser.add_argument("--output", type=Path, required=True,
                        help="新的报告文件路径或报告目录")
    parser.add_argument("--recipient", default="BUR",
                        help="被查询国家，默认 BUR；actor 固定为 FRA")
    args = parser.parse_args(argv)
    if bool(args.installation) == bool(args.offline_report):
        parser.error("exactly one of --installation or --offline-report is required")
    if args.offline_report is not None:
        return _offline_recompute(args.offline_report, args.output)
    recipient = str(args.recipient).upper()
    if _TAG.fullmatch(recipient) is None or recipient == _ACTOR:
        parser.error("--recipient must be a three-letter tag other than FRA")
    report_path: Path | None = None
    evidence: Path | None = None
    report: dict[str, Any] = {
        "validator": Path(__file__).name,
        "version": 1,
        "mode": "read_only_peace_consequence_queries",
        "status": "running",
        "installation": str(args.installation),
        "actor": _ACTOR,
        "recipient": recipient,
        "query_call_count": 0,
        "execute_call_count": 0,
        "business_submission": False,
        "advance_requested": False,
        "save_requested": False,
        "restart_requested": False,
        "cases": [],
        "coverage": {},
    }
    session: ObserverSession | None = None
    log_path: Path | None = None
    try:
        report_path, evidence = _output_paths(args.output)
        installation = args.installation.expanduser().resolve(strict=True)
        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session"] = {
            key: session.record.get(key)
            for key in ("pid", "session_id", "experiment_id", "dll_sha256")
        }
        health_before = wait_runtime_ready(session, restore_minimized=True)
        before_probe = _run_probe(
            PROBE_SPECS[0], session.record["pid"],
            evidence / "before" / "control_state.json")
        control_before = _control_from_probe(before_probe)
        expected_date = health_before.get("date_raw")
        report["expected_date_raw"] = expected_date
        report["before"] = {
            "health": health_before,
            "control": control_before,
            "control_probe": _compact_probe(before_probe),
        }
        if (health_before.get("status") != "ready"
                or health_before.get("complete") is not True
                or not _control_is_paused_por(control_before, expected_date)):
            raise ConsequenceQueryError(
                "BASELINE_NOT_READY_POR_PAUSED", str(control_before))
        log_path = session.directory / "control-probe.jsonl"

        with DurableJournal(evidence / "diplomacy.sqlite3",
                            session.experiment_id, session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            discovery = api.inspect_diplomatic_action(
                "white_peace", _ACTOR, recipient,
                phase="initiate", parameters={})
            _write_json(evidence / "war-discovery.json", discovery)
            report["query_call_count"] += 1
            war_id = _single_discovered_war_id(discovery, _ACTOR, recipient)
            if war_id is None or _WAR_ID.fullmatch(war_id) is None:
                raise ConsequenceQueryError(
                    "PEACE_WAR_DISCOVERY_INCOMPLETE",
                    f"no unique {_ACTOR}-{recipient} war")
            report["war_id"] = war_id
            report["discovery"] = {
                "public_contract": isinstance(discovery, dict)
                and discovery.get("family") == "peace",
                "path": str(evidence / "war-discovery.json"),
            }

            def run_case(name: str, action_id: str, direction: str,
                         parameters: dict[str, object], *, amount_raw: int | None = None,
                         province_ids: list[int] | None = None,
                         beneficiary: str | None = None,
                         discovery_case: bool = False) -> dict[str, object]:
                case_dir = evidence / "cases" / name
                case_dir.mkdir(parents=True, exist_ok=False)
                query_id = f"r65_consequence_{name.replace('-', '_')}"
                input_record = {
                    "query_id": query_id,
                    "action_id": action_id,
                    "actor": _ACTOR,
                    "recipient": recipient,
                    "phase": "initiate",
                    "direction": direction,
                    "parameters": parameters,
                    "expected_war_id": war_id,
                    "expected_amount_raw": amount_raw,
                    "expected_province_ids": province_ids or [],
                    "expected_beneficiary": beneficiary,
                }
                _write_json(case_dir / "input.json", input_record)
                start = log_path.stat().st_size
                result: object
                error: dict[str, object] | None = None
                report["query_call_count"] += 1
                try:
                    result = api.inspect_diplomatic_action(
                        action_id, _ACTOR, recipient,
                        phase="initiate", parameters=parameters)
                except Exception as exc:  # one query failure must stay bounded
                    result = {"status": "error", "error_type": type(exc).__name__,
                              "error": str(exc)}
                    error = {"type": type(exc).__name__, "message": str(exc)}
                _write_json(case_dir / "public.json", result)
                end = log_path.stat().st_size
                slice_meta = _copy_bounded_slice(
                    log_path, start, case_dir / "native-events-slice.jsonl")
                raw_event = _matching_event(
                    case_dir / "native-events-slice.jsonl",
                    action_id=action_id, actor=_ACTOR, recipient=recipient,
                    direction=direction, war_id=war_id)
                if isinstance(raw_event, dict):
                    _write_json(case_dir / "native-event.json", raw_event)
                public_contract = _public_contract(
                    result, action_id, _ACTOR, recipient, war_id, direction)
                raw_header = _raw_header_contract(
                    raw_event, action_id=action_id, actor=_ACTOR,
                    recipient=recipient, direction=direction, war_id=war_id,
                    expected_date=expected_date,
                    session_id=session.session_id)
                raw_consequences = (raw_event.get("native_consequences")
                                    if isinstance(raw_event, dict) else None)
                raw_for_validator = raw_event
                # DiplomacyTools removes the optional evaluator payload before
                # invoking the production validator when that capability was
                # not ACKed.  Apply the same normalization to this offline
                # replay instead of treating an otherwise valid event as a
                # different contract.
                if (isinstance(raw_event, dict) and isinstance(result, dict)
                        and "native_evaluation" not in result
                        and "native_evaluation" in raw_event):
                    raw_for_validator = dict(raw_event)
                    raw_for_validator.pop("native_evaluation", None)
                raw_validator = (
                    not discovery_case
                    and isinstance(raw_for_validator, dict)
                    and _native_validator(
                        raw_for_validator, action_id=action_id, actor=_ACTOR,
                        recipient=recipient, direction=direction, war_id=war_id,
                        expected_date=expected_date,
                        query_id=(raw_event.get("query_id")
                                  if isinstance(raw_event, dict) else ""),
                        session_id=session.session_id, amount_raw=amount_raw,
                        province_ids=province_ids, beneficiary=beneficiary))
                consequence_valid = (not discovery_case
                                     and validate_native_consequences(raw_consequences))
                projected = (project_event_consequences(
                    raw_event, codec=session.native_text_codec)
                    if consequence_valid else None)
                public_consequences = (result.get("peace_consequences")
                                       if isinstance(result, dict) else None)
                parity = (consequence_valid and projected == public_consequences)
                object_unchanged = (
                    isinstance(result, dict)
                    and result.get("object_unchanged") is True
                    and isinstance(raw_event, dict)
                    and raw_event.get("object_unchanged") is True)
                private_absent = isinstance(result, dict) and not _has_private_fields(result)
                case_record: dict[str, object] = {
                    "name": name,
                    "action_id": action_id,
                    "direction": direction,
                    "query_id": query_id,
                    "native_query_id": (raw_event.get("query_id")
                                         if isinstance(raw_event, dict) else None),
                    "input_path": str(case_dir / "input.json"),
                    "public_path": str(case_dir / "public.json"),
                    "native_event_path": (str(case_dir / "native-event.json")
                                          if isinstance(raw_event, dict) else None),
                    "native_slice": slice_meta,
                    "error": error,
                    "public_contract": public_contract,
                    "raw_header_contract": raw_header,
                    "native_validator": raw_validator,
                    "consequence_contract": consequence_valid,
                    "raw_public_parity": parity,
                    "object_unchanged": object_unchanged,
                    "private_fields_absent": private_absent,
                    "consequence_summary": (_consequence_summary(public_consequences)
                                             if consequence_valid else None),
                }
                report["cases"].append(case_record)
                return result if isinstance(result, dict) else {}

            for direction in ("demand", "offer"):
                context = {"war_id": war_id, "direction": direction, "terms": []}
                run_case(f"{direction}-white-peace", "white_peace", direction,
                         {"peace_context": context})
                payer = recipient if direction == "demand" else _ACTOR
                claimant = _ACTOR if direction == "demand" else recipient
                money_context = {
                    "war_id": war_id, "direction": direction,
                    "terms": [{"action_id": "demand_ducats", "amount": _MONEY_AMOUNT,
                               "payer": payer, "claimant": claimant}],
                }
                run_case(f"{direction}-money", "demand_ducats", direction,
                         {"peace_context": money_context},
                         amount_raw=_money_raw(_MONEY_AMOUNT))

                candidate_name = f"{direction}-province-candidates"
                candidate_context = {"war_id": war_id, "direction": direction, "terms": []}
                candidate = run_case(
                    candidate_name, "cede_province", direction,
                    {"peace_context": candidate_context},
                    province_ids=[], beneficiary=None)
                rows = _candidate_rows(candidate,
                                       _ACTOR if direction == "demand" else recipient)
                for row in report["cases"]:
                    if row.get("name") == candidate_name:
                        row["candidate_discovery"] = True
                        row["candidate_count"] = len(rows)
                        row["candidate_rows"] = [
                            _candidate_summary(item) for item in rows[:64]]
                        break

                beneficiary = _ACTOR if direction == "demand" else recipient
                selected_rows = rows[:2]
                if selected_rows:
                    province_ids = [int(selected_rows[0]["province_id"])]
                    terms = [{"action_id": "cede_province",
                              "province_ids": province_ids,
                              "beneficiary": beneficiary}]
                    run_case(
                        f"{direction}-province-one", "cede_province", direction,
                        {"peace_context": {"war_id": war_id, "direction": direction,
                                            "terms": terms}},
                        province_ids=province_ids, beneficiary=beneficiary)
                    if len(selected_rows) >= 2:
                        province_ids = [int(row["province_id"])
                                        for row in selected_rows]
                        terms = [{"action_id": "cede_province",
                                  "province_ids": province_ids,
                                  "beneficiary": beneficiary}]
                        run_case(
                            f"{direction}-province-two", "cede_province", direction,
                            {"peace_context": {"war_id": war_id, "direction": direction,
                                                "terms": terms}},
                            province_ids=province_ids, beneficiary=beneficiary)
                    # Keep the many-province case bounded by the native
                    # selection contract and distinct from the one/two cases.
                    many_ids = [int(row["province_id"]) for row in rows[
                        :_MAX_PROVINCE_SELECTIONS]]
                    if len(many_ids) > 2:
                        terms = [{"action_id": "cede_province",
                                  "province_ids": many_ids,
                                  "beneficiary": beneficiary}]
                        run_case(
                            f"{direction}-province-many", "cede_province", direction,
                            {"peace_context": {"war_id": war_id, "direction": direction,
                                                "terms": terms}},
                            province_ids=many_ids, beneficiary=beneficiary)
                orl_rows = [row for row in _candidate_rows(candidate, "ORL")]
                if orl_rows:
                    orl_id = int(orl_rows[0]["province_id"])
                    run_case(
                        f"{direction}-province-orl", "cede_province", direction,
                        {"peace_context": {"war_id": war_id, "direction": direction,
                                            "terms": [{"action_id": "cede_province",
                                                       "province_ids": [orl_id],
                                                       "beneficiary": "ORL"}]}},
                        province_ids=[orl_id], beneficiary="ORL")
                else:
                    report.setdefault("uncovered", []).append(
                        f"{direction}-third-country-ORL-cede")

        health_after = session.health()
        after_probe = _run_probe(
            PROBE_SPECS[0], session.record["pid"],
            evidence / "after" / "control_state.json")
        control_after = _control_from_probe(after_probe)
        report["after"] = {
            "health": health_after,
            "control": control_after,
            "control_probe": _compact_probe(after_probe),
        }
        report["before_after"] = {
            "same_session_id": (report.get("session", {}).get("session_id")
                                 == session.session_id),
            "same_date_raw": (control_before.get("date_raw")
                               == control_after.get("date_raw")),
            "paused_por_before": _control_is_paused_por(
                control_before, expected_date),
            "paused_por_after": _control_is_paused_por(
                control_after, expected_date),
        }
        report["coverage"] = _coverage(report["cases"])
        case_rows = list(report["cases"])
        report["checks"] = {
            "before_health_ready": health_before.get("status") == "ready"
            and health_before.get("complete") is True,
            "before_por_paused": _control_is_paused_por(control_before, expected_date),
            "same_session_and_date": (
                report["before_after"]["same_session_id"] is True
                and report["before_after"]["same_date_raw"] is True),
            "discovery_one_war": isinstance(report.get("war_id"), str),
            "case_count_nonzero": bool(case_rows),
            "case_public_contracts": all(row.get("public_contract") is True
                                           for row in case_rows),
            "case_raw_headers": all(row.get("raw_header_contract") is True
                                     for row in case_rows),
            "case_native_validators": all(row.get("native_validator") is True
                                           for row in case_rows),
            "case_consequence_validators": all(
                row.get("consequence_contract") is True for row in case_rows),
            "case_raw_public_parity": all(row.get("raw_public_parity") is True
                                           for row in case_rows),
            "case_object_unchanged": all(row.get("object_unchanged") is True
                                          for row in case_rows),
            "public_queries_no_private_identifiers": all(
                row.get("private_fields_absent") is True
                for row in report["cases"]),
            "after_health_ready": health_after.get("status") == "ready"
            and health_after.get("complete") is True,
            "after_por_paused_same_date": (
                _control_is_paused_por(control_after, expected_date)
                and control_after.get("date_raw") == control_before.get("date_raw")),
            "no_business_submission": (
                report["execute_call_count"] == 0
                and report["business_submission"] is False
                and report["advance_requested"] is False
                and report["save_requested"] is False
                and report["restart_requested"] is False),
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "code": error.code if isinstance(error, ConsequenceQueryError)
            else "UNEXPECTED_CONSEQUENCE_QUERY_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if report_path is not None:
            _write_json(report_path, report)
    print(json.dumps({
        "status": report["status"],
        "report": str(report_path) if report_path else None,
        "war_id": report.get("war_id"),
        "query_call_count": report.get("query_call_count"),
        "failed_checks": [key for key, value in report.get("checks", {}).items()
                          if value is not True],
    }, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
