#!/usr/bin/env python3
"""Execute one parameter-bound outbound Peace action through the public API.

The operator is deliberately single-use.  It discovers the one public
FRA--ENG war context, inspects the selected Peace payload, calls
``execute_diplomatic_action`` exactly once, and polls only that same request
identifier.  It never retries, advances time, saves, installs, or restarts
the game.  A non-terminal or contradictory native result remains unknown in
the report instead of being treated as success.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import time
import uuid
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from bridge.peace_execution import normalize_peace_execution_parameters  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import (  # noqa: E402
    _copy_log_slice,
    _sha256_file,
    _write_json,
)
from work.run_peace_authority_test import _snapshot_stability  # noqa: E402
from work.run_peace_empty_offer_queries import (  # noqa: E402
    _has_private_fields,
    _public_context_contract,
    _single_discovered_war_id,
)
from work.run_peace_inbound_response import _war_pair_summary  # noqa: E402
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _public_probe_records,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _read_json,
    _run_snapshots,
)


_ACTOR = "FRA"
_RECIPIENT = "ENG"
_FAMILY = "peace"
_DISCOVERY_ACTION = "white_peace"
_ACTIONS = ("white_peace", "demand_ducats", "cede_province", "war_reparations")
_DIRECTIONS = ("demand", "offer")
_PLAYER_SLOT = 189  # POR in the controlled observer fixture
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
_WAR_ID_RE = re.compile(r"war_[0-9a-f]{16}_[0-9a-f]{8}\Z")
_TERMINAL_STATUSES = frozenset(
    ("accepted", "rejected", "executed", "invalidated", "expired", "conflict")
)
_POLL_SECONDS = 20.0
_POLL_INTERVAL_SECONDS = 0.20
_MAX_NATIVE_EVENT_BYTES = 8 * 1024 * 1024
_MAX_PROVINCE_IDS = 16
_MIN_PROVINCE_ID = 1
_MAX_PROVINCE_ID = 2_147_483_647


class PeaceExecutionError(RuntimeError):
    """A bounded preflight or report construction failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _output_paths(requested: Path) -> tuple[Path, Path]:
    """Create a new report/evidence location without overwriting artifacts."""

    target = requested.expanduser().resolve()
    if target.exists():
        raise PeaceExecutionError("OUTPUT_ALREADY_EXISTS", str(target))
    if target.suffix.casefold() == ".json":
        report_path = target
        evidence = target.parent / f"{target.stem}-evidence"
    else:
        evidence = target
        report_path = target / "report.json"
    if evidence.exists() or report_path.exists():
        raise PeaceExecutionError("OUTPUT_ALREADY_EXISTS", str(report_path))
    evidence.mkdir(parents=True, exist_ok=False)
    return report_path, evidence


def _normalize_province_ids(value: object) -> list[int]:
    """Validate and preserve one bounded, duplicate-free province sequence."""

    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= _MAX_PROVINCE_IDS:
        raise PeaceExecutionError("PROVINCE_IDS_INVALID", str(value))
    result: list[int] = []
    for province_id in value:
        if (isinstance(province_id, bool)
                or not isinstance(province_id, int)
                or not _MIN_PROVINCE_ID <= province_id <= _MAX_PROVINCE_ID):
            raise PeaceExecutionError("PROVINCE_ID_INVALID", str(province_id))
        if province_id in result:
            raise PeaceExecutionError("PROVINCE_IDS_DUPLICATE", str(province_id))
        result.append(province_id)
    return result


def _parse_province_ids_csv(value: str) -> list[int]:
    """Parse ``--province-ids`` without silently dropping an empty token."""

    if not isinstance(value, str) or not value.strip():
        raise PeaceExecutionError("PROVINCE_IDS_INVALID", value)
    tokens = value.split(",")
    parsed: list[int] = []
    for token in tokens:
        token = token.strip()
        if not token:
            raise PeaceExecutionError("PROVINCE_IDS_INVALID", value)
        try:
            parsed.append(int(token, 0))
        except ValueError as error:
            raise PeaceExecutionError("PROVINCE_ID_INVALID", token) from error
    return _normalize_province_ids(parsed)


def _build_parameters(action_id: str, war_id: str, amount: str,
                      province_id: int | None, beneficiary: str | None = None,
                      direction: str = "demand", *,
                      province_ids: list[int] | tuple[int, ...] | None = None,
                      with_money: str | None = None,
                      with_reparations: bool = False,
                      ) -> dict[str, object]:
    """Build and normalize the complete public execution parameter object."""

    if _WAR_ID_RE.fullmatch(war_id) is None:
        raise PeaceExecutionError("WAR_ID_INVALID", war_id)
    if direction not in _DIRECTIONS:
        raise PeaceExecutionError("PEACE_DIRECTION_INVALID", direction)
    if action_id not in _ACTIONS:
        raise PeaceExecutionError("ACTION_INVALID", action_id)
    if action_id == "white_peace":
        if with_money is not None or with_reparations or province_ids is not None:
            raise PeaceExecutionError(
                "WHITE_PEACE_TERMS_INVALID",
                "white_peace cannot include money, provinces, or reparations")
        terms: list[dict[str, object]] = []
    elif action_id == "demand_ducats":
        if with_money is not None or province_ids is not None:
            raise PeaceExecutionError(
                "MONEY_PRIMARY_COMBINATION_INVALID",
                "demand_ducats cannot add a second money or province term")
        terms = [{
            "action_id": "demand_ducats",
            "amount": amount,
            "payer": _ACTOR if direction == "offer" else _RECIPIENT,
            "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
        }]
        if with_reparations:
            terms.append({
                "action_id": "war_reparations",
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
    elif action_id == "cede_province":
        selected_ids = _normalize_province_ids(
            province_ids if province_ids is not None else [province_id])
        if beneficiary is None:
            beneficiary = _ACTOR if direction == "demand" else _RECIPIENT
        if _TAG_RE.fullmatch(beneficiary) is None:
            raise PeaceExecutionError("BENEFICIARY_INVALID", str(beneficiary))
        terms = []
        if with_money is not None:
            terms.append({
                "action_id": "demand_ducats",
                "amount": with_money,
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        terms.append({
            "action_id": "cede_province",
            "province_ids": selected_ids,
            "beneficiary": beneficiary,
        })
        if with_reparations:
            terms.append({
                "action_id": "war_reparations",
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
    elif action_id == "war_reparations":
        if with_reparations:
            raise PeaceExecutionError(
                "REPARATIONS_DUPLICATE_TERM",
                "war_reparations is already the primary term")
        terms = []
        if with_money is not None:
            terms.append({
                "action_id": "demand_ducats",
                "amount": with_money,
                "payer": _ACTOR if direction == "offer" else _RECIPIENT,
                "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
            })
        if province_ids is not None:
            selected_ids = _normalize_province_ids(province_ids)
            if beneficiary is None:
                beneficiary = _ACTOR if direction == "demand" else _RECIPIENT
            if _TAG_RE.fullmatch(beneficiary) is None:
                raise PeaceExecutionError("BENEFICIARY_INVALID", str(beneficiary))
            terms.append({
                "action_id": "cede_province",
                "province_ids": selected_ids,
                "beneficiary": beneficiary,
            })
        terms.append({
            "action_id": "war_reparations",
            "payer": _ACTOR if direction == "offer" else _RECIPIENT,
            "claimant": _RECIPIENT if direction == "offer" else _ACTOR,
        })
    else:  # guarded above; keeps the type narrowing explicit for callers
        raise PeaceExecutionError("ACTION_INVALID", action_id)
    raw = {
        "peace_context": {
            "war_id": war_id,
            "direction": direction,
            "terms": terms,
        }
    }
    try:
        normalized = normalize_peace_execution_parameters(
            action_id, _ACTOR, _RECIPIENT, "initiate", raw)
    except (TypeError, ValueError) as error:
        code = str(error.args[0]) if error.args else "PEACE_PARAMETERS_INVALID"
        raise PeaceExecutionError(code, str(error)) from error
    return normalized


def _query_parameters(action_id: str, execution_parameters: dict[str, object]) -> dict[str, object]:
    """Use the exact parameter shape for both inspection and execution.

    The public Peace adapter now routes an inspection with the complete
    executable context through its precise submission overlay.  Keeping the
    same object for inspection and execution prevents the white-peace legacy
    ``war_id + terms`` shape from being mistaken for an executable request.
    """
    return execution_parameters


def _selected_inspection_contract(value: object, action_id: str,
                                  query_parameters: dict[str, object],
                                  war_id: str) -> dict[str, object]:
    """Check the public selected Peace inspection without inferring legality."""

    if not isinstance(value, dict):
        return {"valid": False, "checks": {"object": False}}
    context = value.get("peace_context")
    session = value.get("session")
    interface = value.get("interface_support")
    checks: dict[str, bool] = {
        "object": True,
        "identity": all(value.get(key) == expected for key, expected in (
            ("action_id", action_id), ("actor", _ACTOR),
            ("recipient", _RECIPIENT), ("family", _FAMILY),
            ("phase", "initiate"))),
        "session_ready": isinstance(session, dict)
        and session.get("status") == "ready"
        and session.get("complete") is True,
        "native_query_interface": isinstance(interface, dict)
        and isinstance(interface.get("query"), str)
        and interface.get("query", "").startswith("native_peace_"),
        "context_object": isinstance(context, dict),
        "context_war_id": isinstance(context, dict)
        and context.get("war_id") == war_id,
        "context_complete": isinstance(context, dict)
        and context.get("complete") is True,
        "context_terms": isinstance(context, dict)
        and isinstance(context.get("terms"), list),
        "pair_at_war": value.get("pair_at_war") is True,
        "no_private_identifiers": not _has_private_fields(value),
        "parameters_recorded": (
            isinstance(value.get("parameters"), dict)
            and value["parameters"].get("requested") == query_parameters),
    }
    return {
        "valid": all(checks.values()),
        "checks": checks,
        "legality": value.get("legality"),
        "authorization": value.get("authorization"),
        "peace_context": context,
        "native_rule_components": value.get("native_rule_components"),
    }


def _poll_result(api: DiplomacyTools, request_id: str) -> dict[str, object]:
    """Poll one request journal entry; never calls execute again."""

    started = _utc_now()
    deadline = started + timedelta(seconds=_POLL_SECONDS)
    history: list[str] = []
    final: object = None
    calls = 0
    while _utc_now() < deadline:
        final = api.get_diplomatic_result(request_id)
        calls += 1
        status = final.get("status") if isinstance(final, dict) else None
        if isinstance(status, str) and (not history or history[-1] != status):
            history.append(status)
        if status in _TERMINAL_STATUSES:
            break
        remaining = max(0.0, (deadline - _utc_now()).total_seconds())
        if remaining <= 0:
            break
        time.sleep(min(_POLL_INTERVAL_SECONDS, remaining))
    completed = _utc_now()
    return {
        "started_utc": _utc_text(started),
        "deadline_utc": _utc_text(deadline),
        "completed_utc": _utc_text(completed),
        "timeout_seconds": _POLL_SECONDS,
        "poll_interval_seconds": _POLL_INTERVAL_SECONDS,
        "calls": calls,
        "status_history": history,
        "terminal": isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES,
        "final": final,
    }


def _public_result(final: object) -> dict[str, object] | None:
    if not isinstance(final, dict):
        return None
    result = final.get("result")
    return result if isinstance(result, dict) else None


def _native_effect_observation(public: dict[str, object]) -> dict[str, object]:
    """Retain effect projections without imposing a schema before native work lands."""

    values = {
        key: public[key]
        for key in ("effects", "native_effects", "peace_effects")
        if key in public
    }
    return {
        "present": bool(values),
        "values": values,
        "schema_validation": "effects_v1",
    }


def _execution_province_ids(report: dict[str, object]) -> list[int]:
    """Extract the normalized cede list from an immutable report."""

    parameters = report.get("parameters")
    execution = parameters.get("execute") if isinstance(parameters, dict) else None
    context = execution.get("peace_context") if isinstance(execution, dict) else None
    terms = context.get("terms") if isinstance(context, dict) else None
    if not isinstance(terms, list):
        return []
    for term in terms:
        if not isinstance(term, dict) or term.get("action_id") != "cede_province":
            continue
        values = term.get("province_ids")
        if not isinstance(values, list):
            return []
        if any(type(value) is not int for value in values):
            return []
        if len(values) != len(set(values)):
            return []
        return list(values)
    return []


def _wire_submission_correlation(report: dict[str, object],
                                  event_path: Path | None = None
                                  ) -> dict[str, object]:
    """Correlate only the exact request/session native receipt.

    ``business_submission`` is the bridge/API acknowledgement.  The native
    receipt is a separate wire observation: a receipt with ``submitted=false``
    still proves that the request reached and was consumed by the DLL, while
    ``transport_verified`` and ``request_binding_verified`` describe whether
    the business transport was accepted.  No unrelated log line contributes
    to these counts.
    """

    metadata = report.get("native_events")
    if event_path is None:
        value = metadata.get("path") if isinstance(metadata, dict) else None
        event_path = Path(value).expanduser().resolve() if isinstance(value, str) else None
    session = report.get("session")
    session_id = session.get("session_id") if isinstance(session, dict) else None
    request_id = report.get("request_id")
    result: dict[str, object] = {
        "status": "unknown",
        "event_path": str(event_path) if event_path is not None else None,
        "session_id": session_id,
        "request_id": request_id,
        "private": True,
        "matching_event_count": 0,
        "wire_publish_count": 0,
        "wire_consume_count": 0,
        "wire_published": None,
        "wire_consumed": None,
        "native_submitted": None,
        "transport_submitted": None,
        "checks": {},
        "events": [],
    }
    checks = result["checks"]
    if not isinstance(checks, dict):  # defensive type narrowing
        checks = {}
        result["checks"] = checks
    checks["event_path_is_file"] = event_path is not None and event_path.is_file()
    if not checks["event_path_is_file"]:
        checks["request_binding"] = False
        checks["single_matching_receipt"] = False
        return result
    try:
        size = event_path.stat().st_size
        checks["event_slice_bounded"] = size <= _MAX_NATIVE_EVENT_BYTES
        if not checks["event_slice_bounded"]:
            return result
        matching: list[dict[str, object]] = []
        with event_path.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if (event.get("event") == "native_peace_submission_result"
                        and event.get("session_id") == session_id
                        and event.get("request_id") == request_id):
                    matching.append(event)
                    if len(matching) > 16:
                        break
    except OSError as error:
        checks["event_slice_readable"] = False
        result["error"] = f"{type(error).__name__}: {error}"
        return result

    result["matching_event_count"] = len(matching)
    result["events"] = [{
        key: event.get(key)
        for key in (
            "event", "session_id", "request_id", "family", "action_id",
            "actor", "recipient", "phase", "date_raw", "war_id",
            "direction", "province_ids", "beneficiary", "submitted",
            "transport_verified", "request_binding_verified", "reason",
            "native_origin", "native_sequence")
        if key in event
    } for event in matching]
    checks["event_slice_readable"] = True
    checks["single_matching_receipt"] = len(matching) == 1
    if len(matching) != 1:
        checks["request_binding"] = False
        return result

    event = matching[0]
    expected = {
        "family": "peace",
        "action_id": report.get("action_id"),
        "actor": report.get("actor", _ACTOR),
        "recipient": report.get("recipient", _RECIPIENT),
        "phase": report.get("phase", "initiate"),
        "date_raw": report.get("expected_date_raw"),
        "war_id": report.get("war_id"),
        "direction": report.get("direction"),
    }
    field_checks = {
        key: (event.get(key) == value)
        for key, value in expected.items()
        if value is not None
    }
    expected_ids = _execution_province_ids(report)
    if expected_ids or report.get("action_id") == "cede_province":
        actual_ids = event.get("province_ids")
        field_checks["province_ids"] = (
            isinstance(actual_ids, list)
            and all(type(value) is int for value in actual_ids)
            and len(actual_ids) == len(expected_ids)
            and len(actual_ids) == len(set(actual_ids))
            and set(actual_ids) == set(expected_ids)
        )
    checks.update(field_checks)
    checks["request_binding"] = all(field_checks.values())
    # The exact session/request event proves that the wire reached the DLL;
    # native submitted/transport flags remain separate business results.
    result["wire_published"] = checks["request_binding"]
    result["wire_consumed"] = checks["request_binding"]
    result["wire_publish_count"] = 1 if result["wire_published"] else 0
    result["wire_consume_count"] = 1 if result["wire_consumed"] else 0
    result["native_submitted"] = event.get("submitted") \
        if type(event.get("submitted")) is bool else None
    result["transport_submitted"] = (
        event.get("submitted") is True
        and event.get("transport_verified") is True
        and event.get("request_binding_verified") is True
    ) if result["wire_consumed"] else None
    result["status"] = "observed" if result["wire_consumed"] else "mismatch"
    return result


def _derive_wire_correction(source_report: Path, output: Path) -> dict[str, object]:
    """Write a non-destructive correction artifact for an existing report."""

    if output.exists():
        raise PeaceExecutionError("OUTPUT_ALREADY_EXISTS", str(output))
    payload = _read_json(source_report, maximum=_MAX_NATIVE_EVENT_BYTES)
    if not isinstance(payload, dict):
        raise PeaceExecutionError("SOURCE_REPORT_NOT_OBJECT", str(source_report))
    correlation = _wire_submission_correlation(payload)
    correction = {
        "validator": Path(__file__).name,
        "version": 1,
        "mode": "read_only_wire_submission_correction",
        "source_report": str(source_report.resolve()),
        "source_report_sha256": _sha256_file(source_report),
        "source_status": payload.get("status"),
        "original": {
            "request_publish_count": payload.get("request_publish_count"),
            "business_submission": payload.get("business_submission"),
            "business_submission_count": payload.get("business_submission_count"),
        },
        "wire_submission": correlation,
        "corrected": {
            "request_publish_count": correlation.get("wire_publish_count", 0),
            "wire_publish_count": correlation.get("wire_publish_count", 0),
            "wire_consume_count": correlation.get("wire_consume_count", 0),
            "business_submission_count": (
                1 if payload.get("business_submission") is True else 0),
            "business_transport_submitted": correlation.get("transport_submitted"),
        },
        "note": (
            "request_publish_count now denotes an exact native wire receipt; "
            "business_submission and transport_submitted remain separate."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, correction)
    return correction


def _term_for_action(parameters: dict[str, object], action_id: str) -> dict[str, object] | None:
    context = parameters.get("peace_context")
    terms = context.get("terms") if isinstance(context, dict) else None
    if not isinstance(terms, list):
        return None
    for term in terms:
        if isinstance(term, dict) and term.get("action_id") == action_id:
            return term
    return None


def _effects_contract(public: dict[str, object], action_id: str,
                      parameters: dict[str, object], outcome: object) -> dict[str, object]:
    """Validate the bounded native settlement projection when success is claimed."""

    effects = public.get("effects")
    result: dict[str, object] = {
        "present": isinstance(effects, dict),
        "complete": False,
        "date_unchanged": False,
        "currency_scale": None,
        "terms_verified": public.get("terms_verified"),
        "checks": {},
    }
    if not isinstance(effects, dict):
        result["checks"] = {"object": False}
        result["all"] = outcome not in ("accepted", "executed")
        return result
    result["complete"] = effects.get("complete") is True
    result["date_unchanged"] = effects.get("date_unchanged") is True
    result["currency_scale"] = effects.get("currency_scale")
    checks: dict[str, bool] = {
        "object": True,
        "complete": result["complete"],
        "date_unchanged": result["date_unchanged"],
        "currency_scale_1000": effects.get("currency_scale") == 1000,
    }
    money_term = _term_for_action(parameters, "demand_ducats")
    province_term = _term_for_action(parameters, "cede_province")
    reparations_term = _term_for_action(parameters, "war_reparations")
    if money_term is not None:
        money = effects.get("money")
        expected_amount = _expected_native_fields(action_id, parameters).get("amount_raw")
        expected_payer = money_term.get("payer")
        checks.update({
            "money_object": isinstance(money, dict),
            "money_verified": isinstance(money, dict) and money.get("verified") is True,
            "money_amount": isinstance(money, dict) and money.get("amount_raw") == expected_amount,
            "money_payer": isinstance(money, dict) and money.get("payer") == expected_payer,
            "money_paid_raw": isinstance(money, dict)
            and isinstance(money.get("paid_raw"), int)
            and not isinstance(money.get("paid_raw"), bool),
            "money_credits": isinstance(money, dict)
            and isinstance(money.get("credits"), list)
            and all(
                isinstance(credit, dict)
                and isinstance(credit.get("country"), str)
                and _TAG_RE.fullmatch(credit["country"]) is not None
                and isinstance(credit.get("amount_raw"), int)
                and not isinstance(credit.get("amount_raw"), bool)
                for credit in money.get("credits", [])
            ),
        })
    if province_term is not None:
        provinces = effects.get("provinces")
        expected_ids = province_term.get("province_ids")
        expected_beneficiary = province_term.get("beneficiary")
        by_id = {
            item.get("province_id"): item
            for item in provinces
            if isinstance(item, dict)
        } if isinstance(provinces, list) else {}
        actual_ids = [
            item.get("province_id") for item in provinces
            if isinstance(item, dict)
        ] if isinstance(provinces, list) else []
        checks.update({
            "province_list": isinstance(provinces, list),
            "province_ids_exact": isinstance(expected_ids, list)
            and all(type(item) is int for item in expected_ids)
            and all(type(item) is int for item in actual_ids)
            and len(actual_ids) == len(expected_ids)
            and len(actual_ids) == len(set(actual_ids))
            and set(actual_ids) == set(expected_ids),
            "province_ids": isinstance(expected_ids, list)
            and all(item in by_id for item in expected_ids),
            "province_beneficiary": isinstance(expected_ids, list)
            and all(isinstance(by_id.get(item), dict)
                    and by_id[item].get("beneficiary") == expected_beneficiary
                    for item in expected_ids),
            "province_verified": isinstance(expected_ids, list)
            and all(isinstance(by_id.get(item), dict)
                    and by_id[item].get("verified") is True
                    for item in expected_ids),
            "province_owner_transition": isinstance(expected_ids, list)
            and all(isinstance(by_id.get(item), dict)
                    and isinstance(by_id[item].get("owner_before"), str)
                    and _TAG_RE.fullmatch(by_id[item]["owner_before"]) is not None
                    and by_id[item]["owner_before"] != expected_beneficiary
                    and by_id[item].get("owner_after") == expected_beneficiary
                    for item in expected_ids),
            "province_effect_fields": isinstance(expected_ids, list)
            and all(isinstance(by_id.get(item), dict)
                    and all(isinstance(by_id[item].get(field), str)
                            and _TAG_RE.fullmatch(by_id[item][field]) is not None
                            for field in ("owner_before", "owner_after",
                                          "controller_before", "controller_after"))
                    for item in expected_ids),
        })
    if reparations_term is not None:
        reparations = effects.get("war_reparations")
        checks.update({
            "war_reparations_object": isinstance(reparations, dict),
            "war_reparations_payer": (
                isinstance(reparations, dict)
                and reparations.get("payer") == reparations_term.get("payer")),
            "war_reparations_claimant": (
                isinstance(reparations, dict)
                and reparations.get("claimant") == reparations_term.get("claimant")),
            "war_reparations_active_before": (
                isinstance(reparations, dict)
                and type(reparations.get("active_before")) is bool),
            "war_reparations_active_after": (
                isinstance(reparations, dict)
                and type(reparations.get("active_after")) is bool),
            "war_reparations_verified": (
                isinstance(reparations, dict)
                and reparations.get("verified") is True),
        })
    if money_term is None and province_term is None:
        # White peace has no selected money/province term.  The native effect
        # object remains required for a claimed successful settlement, while
        # the empty lists are allowed to carry future effect metadata.
        checks.update({
            "money_empty": effects.get("money") is None,
            "provinces_list": isinstance(effects.get("provinces"), list),
        })
    if reparations_term is None:
        checks["war_reparations_empty"] = effects.get("war_reparations") is None
    result["checks"] = checks
    result["all"] = all(checks.values()) if outcome in ("accepted", "executed") else True
    return result


def _expected_native_fields(action_id: str, parameters: dict[str, object]) -> dict[str, object]:
    context = parameters.get("peace_context")
    if not isinstance(context, dict):
        return {}
    terms = context.get("terms")
    amount_raw = -1
    province_ids: list[int] = []
    beneficiary: str | None = None
    if isinstance(terms, list):
        for term in terms:
            if not isinstance(term, dict):
                continue
            if term.get("action_id") == "demand_ducats":
                amount = term.get("amount")
                if isinstance(amount, str) and re.fullmatch(r"[0-9]+\.[0-9]", amount):
                    whole, tenths = amount.split(".")
                    amount_raw = (int(whole) * 10 + int(tenths)) * 100
            elif term.get("action_id") == "cede_province":
                ids = term.get("province_ids")
                if isinstance(ids, list):
                    province_ids = list(ids)
                beneficiary = term.get("beneficiary") \
                    if isinstance(term.get("beneficiary"), str) else None
    return {
        "event": "native_peace_execution_result",
        "action_id": action_id,
        "family": _FAMILY,
        "actor": _ACTOR,
        "recipient": _RECIPIENT,
        "phase": "initiate",
        "war_id": context.get("war_id"),
        "direction": context.get("direction"),
        "amount_raw": amount_raw,
        "province_ids": province_ids,
        "beneficiary": beneficiary,
    }


def _province_id_sequence_matches(actual: object, expected: object) -> bool:
    """Compare selected province IDs as a complete duplicate-free set."""

    if not isinstance(actual, list) or not isinstance(expected, list):
        return False
    if any(type(value) is not int for value in actual + expected):
        return False
    return (len(actual) == len(expected)
            and len(actual) == len(set(actual))
            and len(expected) == len(set(expected))
            and set(actual) == set(expected))


def _result_contract(final: object, action_id: str,
                     parameters: dict[str, object], expected_date_raw: object,
                     before_war: dict[str, object], after_war: dict[str, object]) -> dict[str, object]:
    public = _public_result(final)
    expected = _expected_native_fields(action_id, parameters)
    checks: dict[str, bool] = {
        "public_result": isinstance(public, dict),
        "terminal_status": isinstance(final, dict)
        and final.get("status") in _TERMINAL_STATUSES,
        "binding": False,
        "native_result": False,
        "war_transition": False,
        "proof": False,
        "response_verified": False,
        "terms_verified": False,
        "effects_contract": False,
        "unknown_preserved": False,
    }
    if public is None:
        return {"checks": checks, "all": False, "public": None}
    checks["binding"] = all(
        (_province_id_sequence_matches(public.get(key), value)
         if key == "province_ids" else public.get(key) == value)
        for key, value in expected.items()) \
        and public.get("date_raw") == expected_date_raw \
        and public.get("request_id") == final.get("request_id")
    outcome = public.get("outcome")
    effects_contract = _effects_contract(public, action_id, parameters, outcome)
    checks["effects_contract"] = effects_contract.get("all") is True
    checks["native_result"] = outcome in ("executed", "accepted", "rejected", "unknown")
    if outcome in ("executed", "accepted"):
        expected_after = False
        checks["war_transition"] = (
            before_war.get("complete") is True
            and after_war.get("complete") is True
            and before_war.get("pair_at_war") is True
            and after_war.get("pair_at_war") is False
            and public.get("war_before") is True
            and public.get("war_after") is expected_after)
        checks["proof"] = (
            public.get("response_verified") is True
            and public.get("request_binding_verified") is True
            and public.get("execution_verified") is True
            and public.get("terms_verified") is True)
        checks["response_verified"] = public.get("response_verified") is True
        checks["terms_verified"] = public.get("terms_verified") is True
    elif outcome == "rejected":
        checks["war_transition"] = (
            before_war.get("complete") is True
            and after_war.get("complete") is True
            and before_war.get("pair_at_war") is True
            and after_war.get("pair_at_war") is True
            and public.get("war_before") is True
            and public.get("war_after") is True)
        checks["proof"] = (
            public.get("response_verified") is True
            and public.get("request_binding_verified") is True
            and public.get("execution_verified") is False)
        checks["response_verified"] = public.get("response_verified") is True
        # A refusal is a valid native response with no applied terms.
        checks["terms_verified"] = public.get("terms_verified") is False
    else:
        # A native unknown is retained as evidence, never promoted to a
        # successful transition.  The surrounding report remains unknown.
        checks["unknown_preserved"] = (
            outcome == "unknown"
            and public.get("execution_verified") is False
            and public.get("request_binding_verified") is False)
    # ``unknown_preserved`` is a branch-specific check.  It must not make a
    # proven executed/accepted/rejected result fail merely because the
    # unknown branch is inapplicable.  Conversely, an unknown native outcome
    # remains an incomplete verification even when its evidence is retained.
    if outcome == "unknown":
        checks["all"] = False
    else:
        checks["all"] = all(
            value for key, value in checks.items()
            if key not in ("unknown_preserved", "effects_contract")
        )
        checks["all"] = checks["all"] and checks["effects_contract"]
    return {
        "checks": checks,
        "all": checks["all"],
        "public": public,
        "native_effects": _native_effect_observation(public),
        "effects_contract": effects_contract,
    }


def _control_invariants(before: dict[str, object], after: dict[str, object],
                        expected_date_raw: int, before_probes: object,
                        after_probes: object) -> dict[str, bool]:
    return {
        "before_four_snapshots_complete": _snapshots_complete(before_probes),
        "after_four_snapshots_complete": _snapshots_complete(after_probes),
        "before_por_paused_date": before == {
            "date_raw": expected_date_raw, "paused_flag": 1,
            "player_slot": _PLAYER_SLOT},
        "after_por_paused_same_date": after == before
        and after == {
            "date_raw": expected_date_raw, "paused_flag": 1,
            "player_slot": _PLAYER_SLOT},
    }


def _offline_contract_assertions() -> None:
    war_id = "war_0123456789abcdef_01234567"
    white = _build_parameters("white_peace", war_id, "10.0", 177, _ACTOR)
    money = _build_parameters("demand_ducats", war_id, "10.0", 177, _ACTOR)
    province = _build_parameters("cede_province", war_id, "10.0", 177, _ACTOR)
    offer_money = _build_parameters(
        "demand_ducats", war_id, "10.0", 177, None, "offer")
    offer_province = _build_parameters(
        "cede_province", war_id, "10.0", 177, None, "offer")
    multi_province = _build_parameters(
        "cede_province", war_id, "10.0", 177, _ACTOR,
        province_ids=[177, 178, 185])
    mixed = _build_parameters(
        "cede_province", war_id, "10.0", 177, None, "offer",
        province_ids=[177, 178, 185], with_money="1.0")
    assert white["peace_context"]["terms"] == []
    assert money["peace_context"]["terms"][0]["amount"] == "10.0"
    assert province["peace_context"]["terms"][0]["province_ids"] == [177]
    assert offer_money["peace_context"]["direction"] == "offer"
    assert offer_money["peace_context"]["terms"][0]["payer"] == _ACTOR
    assert offer_money["peace_context"]["terms"][0]["claimant"] == _RECIPIENT
    assert offer_province["peace_context"]["terms"][0]["beneficiary"] == _RECIPIENT
    assert multi_province["peace_context"]["terms"][0]["province_ids"] == [177, 178, 185]
    assert [term["action_id"] for term in mixed["peace_context"]["terms"]] == [
        "demand_ducats", "cede_province"]
    assert mixed["peace_context"]["terms"][0]["amount"] == "1.0"
    try:
        _parse_province_ids_csv("177,,178")
    except PeaceExecutionError as error:
        assert error.code == "PROVINCE_IDS_INVALID"
    else:
        raise AssertionError("empty province CSV token was accepted")
    query = _query_parameters("white_peace", white)
    assert query == white
    selected = {
        "action_id": "white_peace", "family": "peace", "actor": "FRA",
        "recipient": "ENG", "phase": "initiate",
        "session": {"status": "ready", "complete": True},
        "interface_support": {"query": "native_peace_empty_offer_inspection"},
        "peace_context": {
            "war_id": war_id, "direction": "demand", "complete": True,
            "terms": [],
        },
        "pair_at_war": True, "parameters": {"requested": query},
    }
    assert _selected_inspection_contract(selected, "white_peace", query, war_id)["valid"]
    before_war = {"complete": True, "pair_at_war": True}
    after_war = {"complete": True, "pair_at_war": False}
    final = {
        "status": "executed", "request_id": "offline_peace_001",
        "result": {
            **_expected_native_fields("white_peace", white),
            "date_raw": 1, "request_id": "offline_peace_001",
            "outcome": "executed", "response_verified": True,
            "request_binding_verified": True, "execution_verified": True,
            "terms_verified": True,
            "war_before": True, "war_after": False,
            "effects": {
                "complete": True,
                "date_unchanged": True,
                "currency_scale": 1000,
                "money": None,
                "provinces": [],
            },
        },
    }
    assert _result_contract(final, "white_peace", white, 1,
                            before_war, after_war)["all"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--action", choices=_ACTIONS, required=True)
    parser.add_argument("--direction", choices=_DIRECTIONS, default="demand",
                        help="议和方向；demand 为 actor 向 recipient 索取，offer 为 actor 向 recipient 提供")
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="新的报告文件路径，或新的报告目录")
    parser.add_argument("--amount", default="10.0",
                        help="demand_ducats 的金额，默认 10.0 ducats")
    parser.add_argument("--with-money", default=None,
                        help="cede_province 或 war_reparations 主动作追加的金额条款（例如 1.0 ducats）")
    parser.add_argument("--with-reparations", action="store_true",
                        help="给 demand_ducats 或 cede_province 主动作追加战争赔款条款")
    parser.add_argument("--province-id", type=int, default=None,
                        help="兼容旧调用：cede_province 的单个省份编号；未给出时默认 177")
    parser.add_argument("--province-ids", default=None,
                        help="cede_province 的省份编号 CSV（1..16 个，例如 177,178,185）；与 --province-id 互斥")
    parser.add_argument("--beneficiary", default=None,
                        help="cede_province 的受益国；默认随 direction 选择 demand=FRA、offer=ENG")
    args = parser.parse_args(argv)
    _offline_contract_assertions()
    if _REQUEST_ID_RE.fullmatch(args.request_id) is None:
        parser.error("--request-id must match [A-Za-z0-9_-]{1,64}")
    try:
        if args.with_money is not None and args.action not in ("cede_province", "war_reparations"):
            raise PeaceExecutionError(
                "WITH_MONEY_ACTION_INVALID",
                "--with-money only applies when cede_province or war_reparations is primary")
        if args.with_reparations and args.action not in ("demand_ducats", "cede_province"):
            raise PeaceExecutionError(
                "WITH_REPARATIONS_ACTION_INVALID",
                "--with-reparations only applies when demand_ducats or cede_province is primary")
        if args.province_ids is not None and args.province_id is not None:
            raise PeaceExecutionError(
                "PROVINCE_OPTIONS_CONFLICT", "--province-id and --province-ids are mutually exclusive")
        if args.province_ids is not None:
            if args.action not in ("cede_province", "war_reparations"):
                raise PeaceExecutionError(
                    "PROVINCE_IDS_ACTION_INVALID",
                    "--province-ids only applies to cede_province or war_reparations")
            selected_province_ids = _parse_province_ids_csv(args.province_ids)
        elif args.province_id is not None:
            if args.action not in ("cede_province", "war_reparations"):
                raise PeaceExecutionError(
                    "PROVINCE_ID_ACTION_INVALID",
                    "--province-id only applies to cede_province or war_reparations")
            selected_province_ids = _normalize_province_ids([args.province_id])
        elif args.action == "war_reparations":
            selected_province_ids = []
        else:
            selected_province_ids = [177]
    except PeaceExecutionError as error:
        parser.error(f"{error.code}: {error.message}")

    report_path: Path | None = None
    evidence: Path | None = None
    report: dict[str, Any] = {
        "validator": Path(__file__).name,
        "version": 1,
        "status": "running",
        "mode": "public_peace_outbound_execution",
        "installation": str(args.installation),
        "action_id": args.action,
        "direction": args.direction,
        "actor": _ACTOR,
        "recipient": _RECIPIENT,
        "family": _FAMILY,
        "phase": "initiate",
        "request_id": args.request_id,
        "execute_call_count": 0,
        "request_publish_count": 0,
        "business_submission_count": 0,
        "wire_publish_count": 0,
        "wire_consume_count": 0,
        "wire_published": None,
        "wire_consumed": None,
        "business_transport_submitted": None,
        "business_submission": False,
        "advance_requested": False,
        "save_requested": False,
        "restart_requested": False,
        "installation_requested": False,
        "checks": {},
    }
    log_start: int | None = None
    log_path: Path | None = None
    before: dict[str, dict[str, object]] | None = None
    after: dict[str, dict[str, object]] | None = None
    try:
        report_path, evidence = _output_paths(args.output)
        installation = args.installation.expanduser().resolve(strict=True)
        binding = _installation_binding(installation)
        report.update(binding)
        installation_record = _read_json(installation)
        if not isinstance(installation_record, dict):
            raise PeaceExecutionError("INSTALLATION_METADATA_INVALID", str(installation))
        creation_filetime = installation_record.get("creation_filetime")
        if (isinstance(creation_filetime, bool)
                or not isinstance(creation_filetime, int)
                or creation_filetime < 0):
            raise PeaceExecutionError("INSTALLATION_CREATION_INVALID", str(creation_filetime))

        session = ObserverSession(installation, game_exe())
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "creation_filetime": session.record.get("creation_filetime"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        report["preflight_identity"] = {
            "session_matches_installation": session.session_id == installation_record.get("session_id"),
            "creation_matches_installation": session.record.get("creation_filetime") == creation_filetime,
            "dll_matches_installation_and_build": (
                session.record.get("dll_sha256") == binding.get("installation", {}).get("declared_dll_sha256")
                and binding.get("build_binding", {}).get("installation_matches_build_manifest") is True),
        }
        health_before = wait_runtime_ready(session, timeout=30.0, restore_minimized=False)
        before = _run_snapshots(session, evidence / "before" / "probes")
        before_control = _control_summary(before["control_state"]["snapshot"])
        report["before"] = {
            "health": health_before,
            "control": before_control,
            "probes": _public_probe_records(before),
            "war_state": _war_pair_summary(before),
        }
        if (health_before.get("status") != "ready"
                or health_before.get("complete") is not True
                or before_control != {
                    "date_raw": health_before.get("date_raw"),
                    "paused_flag": 1,
                    "player_slot": _PLAYER_SLOT,
                }
                or not _snapshots_complete(before)):
            raise PeaceExecutionError(
                "BASELINE_NOT_READY_POR_PAUSED_SNAPSHOTS",
                "before snapshots did not prove paused POR state")

        log_path = session.directory / "control-probe.jsonl"
        if not log_path.is_file():
            raise PeaceExecutionError("NATIVE_LOG_UNAVAILABLE", str(log_path))
        expected_date_raw = before_control.get("date_raw")
        if isinstance(expected_date_raw, bool) or not isinstance(expected_date_raw, int):
            raise PeaceExecutionError("DATE_RAW_INVALID", str(expected_date_raw))
        report["expected_date_raw"] = expected_date_raw
        report["public_query_has_no_private_identifiers"] = True
        report["public_inspection"] = {}

        with DurableJournal(evidence / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            discovery = api.inspect_diplomatic_action(
                _DISCOVERY_ACTION, _ACTOR, _RECIPIENT,
                phase="initiate", parameters={})
            _write_json(evidence / "war-discovery.json", discovery)
            report["war_discovery"] = discovery
            war_id = _single_discovered_war_id(discovery, _ACTOR, _RECIPIENT)
            if war_id is None or _WAR_ID_RE.fullmatch(war_id) is None:
                raise PeaceExecutionError(
                    "PEACE_WAR_DISCOVERY_INCOMPLETE",
                    "public white_peace discovery did not return one war id")
            report["war_id"] = war_id
            report["war_context_before"] = discovery.get("war_contexts") \
                if isinstance(discovery, dict) else None
            if _has_private_fields(discovery):
                raise PeaceExecutionError(
                    "PUBLIC_QUERY_CONTAINS_PRIVATE_IDENTIFIER",
                    "war discovery exposed native-only fields")

            execution_parameters = _build_parameters(
                args.action, war_id, args.amount,
                selected_province_ids[0] if selected_province_ids else None,
                args.beneficiary, args.direction,
                province_ids=selected_province_ids,
                with_money=args.with_money,
                with_reparations=args.with_reparations)
            effective_beneficiary = args.beneficiary
            effective_province_ids = list(selected_province_ids)
            if args.action in ("cede_province", "war_reparations"):
                effective_term = _term_for_action(
                    execution_parameters, "cede_province")
                if isinstance(effective_term, dict):
                    effective_beneficiary = effective_term.get("beneficiary")
                    term_ids = effective_term.get("province_ids")
                    if isinstance(term_ids, list):
                        effective_province_ids = list(term_ids)
            query_parameters = _query_parameters(args.action, execution_parameters)
            selected = api.inspect_diplomatic_action(
                args.action, _ACTOR, _RECIPIENT,
                phase="initiate", parameters=query_parameters)
            _write_json(evidence / "selected-inspection.json", selected)
            report["public_inspection"] = selected
            selected_contract = _selected_inspection_contract(
                selected, args.action, query_parameters, war_id)
            report["inspection_contract"] = selected_contract
            report["parameters"] = {
                "query": query_parameters,
                "execute": execution_parameters,
                "amount": args.amount,
                # Keep the old scalar field for artifact readers while the
                # complete list is the authoritative selection contract.
                "province_id": effective_province_ids[0]
                if effective_province_ids else None,
                "province_ids": effective_province_ids,
                "beneficiary": effective_beneficiary,
                "direction": args.direction,
                "with_money": args.with_money,
                "with_reparations": args.with_reparations,
            }
            if not selected_contract["valid"]:
                raise PeaceExecutionError(
                    "SELECTED_INSPECTION_INCOMPLETE",
                    "selected public Peace inspection did not prove full context")

            log_start = log_path.stat().st_size
            report["execute_call_count"] = 1
            report["request_attempt_count"] = 1
            try:
                submission = api.execute_diplomatic_action(
                    args.request_id, args.action, _ACTOR, _RECIPIENT,
                    phase="initiate", parameters=execution_parameters)
            except Exception as error:
                submission = {
                    "status": "unknown",
                    "submitted": False,
                    "game_outcome": "unknown",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            report["submission"] = submission
            report["business_submission"] = (
                isinstance(submission, dict) and submission.get("submitted") is True)
            report["business_submission_count"] = (
                1 if report["business_submission"] else 0)
            poll = _poll_result(api, args.request_id)
            report["poll"] = poll
            report["result"] = poll.get("final")
            try:
                after_discovery = api.inspect_diplomatic_action(
                    _DISCOVERY_ACTION, _ACTOR, _RECIPIENT,
                    phase="initiate", parameters={})
            except Exception as error:
                after_discovery = {
                    "status": "unknown",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            _write_json(evidence / "war-discovery-after.json", after_discovery)
            report["war_discovery_after"] = after_discovery

        after = _run_snapshots(session, evidence / "after" / "probes")
        health_after = session.health()
        after_control = _control_summary(after["control_state"]["snapshot"])
        report["after"] = {
            "health": health_after,
            "control": after_control,
            "probes": _public_probe_records(after),
            "war_state": _war_pair_summary(after),
        }
        public = _public_result(report.get("result"))
        before_war = _war_pair_summary(before)
        after_war = _war_pair_summary(after)
        result_contract = _result_contract(
            report.get("result"), args.action, execution_parameters,
            expected_date_raw, before_war, after_war)
        report["result_contract"] = result_contract
        report["native_effects"] = result_contract.get("native_effects")
        report["effects_contract"] = result_contract.get("effects_contract")
        report["snapshot_observations"] = {
            "semantic_stability": _snapshot_stability(before, after),
            "note": "和平执行可以改变战争状态；稳定性仅记录事实，不作为全快照相等要求。",
        }
        outcome = public.get("outcome") if isinstance(public, dict) else None
        control_checks = _control_invariants(
            before_control, after_control, expected_date_raw, before, after)
        checks: dict[str, bool] = {
            "preflight_health_ready": health_before.get("status") == "ready"
            and health_before.get("complete") is True,
            "session_identity_bound": report["preflight_identity"].get(
                "session_matches_installation") is True,
            "creation_identity_bound": report["preflight_identity"].get(
                "creation_matches_installation") is True,
            "dll_identity_bound": report["preflight_identity"].get(
                "dll_matches_installation_and_build") is True,
            "before_four_snapshots_complete": control_checks["before_four_snapshots_complete"],
            "before_war_pair_at_war": before_war.get("complete") is True
            and before_war.get("pair_at_war") is True,
            "public_war_discovery_contract": _public_context_contract(
                discovery, _ACTOR, _RECIPIENT),
            "public_war_discovery_one_war": (
                _single_discovered_war_id(discovery, _ACTOR, _RECIPIENT) == war_id),
            "selected_inspection_contract": selected_contract.get("valid") is True,
            "execute_called_once": report["execute_call_count"] == 1,
            "request_id_bound": isinstance(report.get("request_id"), str),
            "after_four_snapshots_complete": control_checks["after_four_snapshots_complete"],
            "por_paused_same_date": control_checks["after_por_paused_same_date"],
            "after_health_ready": health_after.get("status") == "ready"
            and health_after.get("complete") is True,
            "native_result_contract": result_contract.get("all") is True,
            "after_war_matches_native_result": (
                outcome in ("executed", "accepted", "rejected")
                and result_contract.get("checks", {}).get("war_transition") is True),
            "no_replay_or_world_control": (
                report["execute_call_count"] == 1
                and report["advance_requested"] is False
                and report["save_requested"] is False
                and report["restart_requested"] is False
                and report["installation_requested"] is False),
        }
        report["checks"] = checks
        if outcome == "unknown" or not poll.get("terminal"):
            report["status"] = "unknown"
        else:
            report["status"] = "passed" if all(checks.values()) else "failed"
    except PeaceExecutionError as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:  # retain bounded diagnostics for operator review
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_PEACE_OUTBOUND_EXECUTION_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if log_start is not None:
            if log_path is None:
                try:
                    log_path = (Path(str(args.installation)).expanduser().resolve().parent
                                / "control-probe.jsonl")
                except (OSError, ValueError):
                    log_path = None
            if log_path is not None and log_path.is_file() and evidence is not None:
                report["native_events"] = _copy_log_slice(
                    log_path, log_start, evidence / "native-events-slice.jsonl")
        # A native submission-result event is the only evidence used for wire
        # publication/consumption.  It is deliberately kept separate from
        # the API business-submission acknowledgement: a consumed request can
        # still be rejected before business transport is accepted.
        try:
            wire = _wire_submission_correlation(report)
            report["wire_submission"] = wire
            report["wire_published"] = wire.get("wire_published")
            report["wire_consumed"] = wire.get("wire_consumed")
            report["wire_publish_count"] = wire.get("wire_publish_count", 0)
            report["wire_consume_count"] = wire.get("wire_consume_count", 0)
            report["request_publish_count"] = report["wire_publish_count"]
            report["business_transport_submitted"] = wire.get(
                "transport_submitted")
        except Exception as error:  # keep final report even if correlation is unavailable
            report["wire_submission"] = {
                "status": "unknown",
                "error": f"{type(error).__name__}: {error}",
                "wire_publish_count": 0,
                "wire_consume_count": 0,
            }
        if report_path is not None:
            _write_json(report_path, report)
    print(json.dumps({
        "status": report["status"],
        "report": str(report_path) if report_path is not None else None,
        "request_id": args.request_id,
        "execute_call_count": report.get("execute_call_count"),
        "result_status": (report.get("result") or {}).get("status")
        if isinstance(report.get("result"), dict) else None,
    }, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 3 if report["status"] == "unknown" else 2


if __name__ == "__main__":
    raise SystemExit(main())
