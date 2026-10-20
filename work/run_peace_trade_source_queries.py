#!/usr/bin/env python3
"""Run one bounded, read-only batch of Peace trade-power source queries.

The operator discovers the one shared FRA--ENG war context and then sends
exactly five ``inspect_diplomatic_action`` calls through the public adapter.
The first query leaves the trade-power terms empty so the native source
candidate list can be observed.  The remaining queries bind the source and
beneficiary explicitly, including a third-country source and an R+T payload.
No query is submitted, and this operator never advances time, saves, or
restarts the game.
"""
from __future__ import annotations

import argparse
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
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import _copy_log_slice, _write_json  # noqa: E402
from work.run_peace_empty_offer_queries import (  # noqa: E402
    _has_private_fields,
    _public_context_contract,
    _single_discovered_war_id,
)
from work.run_royal_marriage_execution import _installation_binding  # noqa: E402
from work.validate_alliance_queries import PROBE_SPECS, _run_probe  # noqa: E402
from work.run_peace_concession_queries import (  # noqa: E402
    _compact_control_probe,
    _control_from_probe,
    _control_is_paused_por,
)


_ACTOR = "FRA"
_RECIPIENT = "ENG"
_TRADE_POWER_ACTION = "transfer_trade_power"
_REPARATIONS_ACTION = "war_reparations"
_DISCOVERY_ACTION = "white_peace"
_PLAYER_SLOT = 189  # POR in the controlled observer fixture
_WAR_ID = re.compile(r"war_[0-9a-f]{16}_[0-9a-f]{8}\Z")
_MAX_CANDIDATES = 128
_MAX_REASON_ITEMS = 32
_CASE_NAMES = (
    "primary-trade-power-candidates",
    "demand-trade-power-utr",
    "demand-trade-power-default-eng",
    "offer-trade-power-fra",
    "demand-reparations-trade-power-utr",
)


class TradeSourceQueryError(RuntimeError):
    """A bounded setup or output error; no business operation is retried."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _output_paths(requested: Path) -> tuple[Path, Path]:
    """Create a new report/evidence pair without overwriting artifacts."""

    target = requested.expanduser().resolve()
    if target.exists():
        raise TradeSourceQueryError("OUTPUT_ALREADY_EXISTS", str(target))
    if target.suffix.casefold() == ".json":
        report_path = target
        evidence = target.parent / f"{target.stem}-evidence"
    else:
        report_path = target / "report.json"
        evidence = target
    if report_path.exists() or evidence.exists():
        raise TradeSourceQueryError("OUTPUT_ALREADY_EXISTS", str(report_path))
    evidence.mkdir(parents=True, exist_ok=False)
    return report_path, evidence


def _query_file_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name) + ".json"


def _case_specs(war_id: str) -> list[dict[str, object]]:
    """Build the five public parameter objects for one discovered war."""

    return [
        {
            "name": _CASE_NAMES[0],
            "mode": "candidate",
            "action_id": _TRADE_POWER_ACTION,
            "direction": "demand",
            "requested_source": "-",
            "expected_beneficiary": _ACTOR,
            "parameters": {
                "peace_context": {
                    "war_id": war_id,
                    "direction": "demand",
                    "terms": [],
                },
            },
        },
        {
            "name": _CASE_NAMES[1],
            "mode": "explicit",
            "action_id": _TRADE_POWER_ACTION,
            "direction": "demand",
            "requested_source": "UTR",
            "expected_beneficiary": _ACTOR,
            "parameters": {
                "peace_context": {
                    "war_id": war_id,
                    "direction": "demand",
                    "terms": [{
                        "action_id": _TRADE_POWER_ACTION,
                        "source": "UTR",
                        "beneficiary": _ACTOR,
                    }],
                },
            },
        },
        {
            "name": _CASE_NAMES[2],
            "mode": "default-source",
            "action_id": _TRADE_POWER_ACTION,
            "direction": "demand",
            "requested_source": _RECIPIENT,
            "expected_beneficiary": _ACTOR,
            "parameters": {
                "peace_context": {
                    "war_id": war_id,
                    "direction": "demand",
                    "terms": [{
                        "action_id": _TRADE_POWER_ACTION,
                        "source": _RECIPIENT,
                        "beneficiary": _ACTOR,
                    }],
                },
            },
        },
        {
            "name": _CASE_NAMES[3],
            "mode": "explicit",
            "action_id": _TRADE_POWER_ACTION,
            "direction": "offer",
            "requested_source": _ACTOR,
            "expected_beneficiary": _RECIPIENT,
            "parameters": {
                "peace_context": {
                    "war_id": war_id,
                    "direction": "offer",
                    "terms": [{
                        "action_id": _TRADE_POWER_ACTION,
                        "source": _ACTOR,
                        "beneficiary": _RECIPIENT,
                    }],
                },
            },
        },
        {
            "name": _CASE_NAMES[4],
            "mode": "explicit-combination",
            "action_id": _TRADE_POWER_ACTION,
            "direction": "demand",
            "requested_source": "UTR",
            "expected_beneficiary": _ACTOR,
            "expected_reparations_payer": _RECIPIENT,
            "expected_reparations_claimant": _ACTOR,
            "parameters": {
                "peace_context": {
                    "war_id": war_id,
                    "direction": "demand",
                    "terms": [
                        {
                            "action_id": _REPARATIONS_ACTION,
                            "payer": _RECIPIENT,
                            "claimant": _ACTOR,
                        },
                        {
                            "action_id": _TRADE_POWER_ACTION,
                            "source": "UTR",
                            "beneficiary": _ACTOR,
                        },
                    ],
                },
            },
        },
    ]


def _reason_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    for row in value[:_MAX_REASON_ITEMS]:
        if not isinstance(row, dict):
            continue
        compact: dict[str, object] = {}
        for key in (
                "code", "source", "complete", "native_value",
                "native_value_verified", "identifier_verified", "text"):
            if key in row:
                value = row.get(key)
                if key == "text" and isinstance(value, str):
                    compact[key] = value[:512]
                elif key != "text" or value is None or isinstance(value, (str, int, bool)):
                    compact[key] = value
        result.append(compact)
    return result


def _native_trade_power(value: object) -> dict[str, object] | None:
    """Return the public trade-power projection without traversing native data."""

    if not isinstance(value, dict):
        return None
    for key in (
            "native_trade_power", "trade_power", "native_trade_power_sources",
            "native_peace_trade_power_sources", "native_trade_power_candidates"):
        candidate = value.get(key)
        if isinstance(candidate, dict):
            return candidate
        if isinstance(candidate, list):
            return {"candidates": candidate}
    parameters = value.get("parameters")
    candidates = parameters.get("candidates") if isinstance(parameters, dict) else None
    if isinstance(candidates, dict):
        # QUERY10's public adapter keeps the bounded candidate enumeration in
        # ``parameters.candidates`` even when the native projection itself is
        # intentionally minimal.  Preserve that contract for the summary.
        return candidates
    return None


def _candidate_rows(native: dict[str, object] | None) -> list[object]:
    if not isinstance(native, dict):
        return []
    for key in ("candidates", "candidate_sources", "source_candidates",
                "available_sources", "sources", "entries"):
        rows = native.get(key)
        if isinstance(rows, list):
            return rows[:_MAX_CANDIDATES]
    return []


def _candidate_list_complete(native: dict[str, object] | None,
                             rows: list[object]) -> bool:
    if not isinstance(native, dict):
        return False
    if any(native.get(key) is True for key in (
            "candidate_enumeration_complete", "candidate_list_complete",
            "candidates_complete", "source_candidates_complete",
            "sources_complete")):
        return len(rows) <= _MAX_CANDIDATES
    count = native.get("candidate_count")
    return (isinstance(count, int) and not isinstance(count, bool)
            and count == len(rows) and len(rows) <= _MAX_CANDIDATES)


def _term_records(value: object) -> list[dict[str, object]]:
    if not isinstance(value, dict):
        return []
    contexts: list[object] = [value.get("peace_context")]
    parameters = value.get("parameters")
    if isinstance(parameters, dict):
        contexts.append(parameters.get("actual"))
        contexts.append(parameters.get("requested"))
    for context in contexts:
        terms = context.get("terms") if isinstance(context, dict) else None
        if isinstance(terms, list):
            return [term for term in terms[:16] if isinstance(term, dict)]
    return []


def _actual_trade_pair(value: object,
                       native: dict[str, object] | None) -> tuple[object, object]:
    source: object = None
    beneficiary: object = None
    native_source_present = False
    native_beneficiary_present = False
    if isinstance(native, dict):
        for key in ("actual_source", "source", "selected_source"):
            if isinstance(native.get(key), str):
                source = native.get(key)
                native_source_present = True
                break
        for key in ("actual_beneficiary", "beneficiary", "selected_beneficiary"):
            if isinstance(native.get(key), str):
                beneficiary = native.get(key)
                native_beneficiary_present = True
                break
    # ``parameters.requested`` and the top-level execution context can echo
    # a failed request.  Prefer the native selected record, then the adapter's
    # explicit ``parameters.actual`` projection; only synthetic/legacy
    # results without a parameters wrapper use the top-level terms.
    contexts: list[object] = []
    parameters = value.get("parameters") if isinstance(value, dict) else None
    if isinstance(parameters, dict) and isinstance(parameters.get("actual"), dict):
        contexts.append(parameters["actual"])
    elif not isinstance(parameters, dict) and isinstance(value, dict):
        contexts.append(value.get("peace_context"))
    for context in contexts:
        terms = context.get("terms") if isinstance(context, dict) else None
        terms = terms if isinstance(terms, list) else []
        for term in terms[:16]:
            if not isinstance(term, dict):
                continue
            if term.get("action_id") != _TRADE_POWER_ACTION:
                continue
            if not native_source_present and isinstance(term.get("source"), str):
                source = term.get("source")
            if (not native_beneficiary_present
                    and isinstance(term.get("beneficiary"), str)):
                beneficiary = term.get("beneficiary")
    return source, beneficiary


def _actual_reparations_pair(value: object) -> tuple[object, object]:
    payer: object = None
    claimant: object = None
    for term in _term_records(value):
        if term.get("action_id") != _REPARATIONS_ACTION:
            continue
        payer = term.get("payer")
        claimant = term.get("claimant")
    native = value.get("native_reparations") if isinstance(value, dict) else None
    if isinstance(native, dict):
        payer = native.get("payer") or payer
        claimant = native.get("claimant") or claimant
    return payer, claimant


def _summary(value: object, spec: dict[str, object], *,
             source_capability_acknowledged: bool = False) -> dict[str, object]:
    """Project one public result and normalize only the two required unknown cases.

    ``native_source_query_ack`` is evidence about this installation, not a
    label chosen by the public query adapter.  Keep it explicit so a route
    rename cannot turn an acknowledged source-capability installation into a
    false negative in the operator report.
    """

    result = value if isinstance(value, dict) else {}
    legality = result.get("legality")
    legality = legality if isinstance(legality, dict) else {}
    native = _native_trade_power(result)
    rows = _candidate_rows(native)
    candidate_found = None
    matching_count = None
    if isinstance(native, dict):
        candidate_found = native.get("candidate_found")
        if candidate_found is None:
            candidate_found = native.get("requested_candidate_found")
        matching_count = native.get("matching_candidate_count")
        if matching_count is None:
            matching_count = native.get("matching_candidates_count")
    raw_status = legality.get("status")
    requested_source = spec.get("requested_source")
    candidate_mode = spec.get("mode") == "candidate"
    missing_default = (
        spec.get("mode") == "default-source"
        and (candidate_found is False or matching_count == 0))
    normalized_status = "unknown" if candidate_mode or missing_default else raw_status
    actual_source, actual_beneficiary = _actual_trade_pair(result, native)
    expected_source = None if requested_source == "-" else requested_source
    source_match = (
        actual_source == expected_source
        if expected_source is not None and actual_source is not None else None)
    beneficiary_match = (
        actual_beneficiary == spec.get("expected_beneficiary")
        if actual_beneficiary is not None else None)
    reparations_payer, reparations_claimant = _actual_reparations_pair(result)
    context = result.get("peace_context")
    context_complete = context.get("complete") if isinstance(context, dict) else None
    parameters_complete = result.get("parameters_complete")
    if parameters_complete is None:
        parameters_complete = context_complete
    parameters = result.get("parameters")
    if parameters_complete is None and isinstance(parameters, dict):
        parameters_complete = parameters.get("complete")
    return {
        "action_id": result.get("action_id"),
        "family": result.get("family"),
        "actor": result.get("actor"),
        "recipient": result.get("recipient"),
        "phase": result.get("phase"),
        "query_complete": result.get("query_complete"),
        "native_source_query_ack": source_capability_acknowledged is True,
        "parameters_complete": parameters_complete,
        "raw_legality_status": raw_status,
        "legality_status": normalized_status,
        "legality_complete": legality.get("complete"),
        "legality_reasons": _reason_list(legality.get("reasons")),
        "requested_source": requested_source,
        "expected_source": expected_source,
        "expected_beneficiary": spec.get("expected_beneficiary"),
        "candidate_mode": candidate_mode,
        "candidate_found": candidate_found,
        "matching_candidate_count": matching_count,
        "candidate_sources": rows,
        "candidate_count": native.get("candidate_count") if isinstance(native, dict) else None,
        "candidate_list_complete": _candidate_list_complete(native, rows),
        "actual_source": actual_source,
        "actual_beneficiary": actual_beneficiary,
        "actual_source_matches": source_match,
        "actual_beneficiary_matches": beneficiary_match,
        "rule_available": (
            native.get("rule_available") if isinstance(native, dict) else None),
        "reparations_payer": reparations_payer,
        "reparations_claimant": reparations_claimant,
        "reparations_pair_matches": (
            reparations_payer == spec.get("expected_reparations_payer")
            and reparations_claimant == spec.get("expected_reparations_claimant")
            if "expected_reparations_payer" in spec else None),
        "submitted": result.get("submitted"),
        "private_fields_present": _has_private_fields(result),
    }


def _identity_contract(value: object, spec: dict[str, object], war_id: str) -> bool:
    if not isinstance(value, dict):
        return False
    return all(value.get(key) == expected for key, expected in (
        ("family", "peace"), ("action_id", spec.get("action_id")),
        ("actor", _ACTOR), ("recipient", _RECIPIENT),
        ("phase", "initiate"))) and (
            value.get("selected_war_id", war_id) == war_id
            or (isinstance(value.get("peace_context"), dict)
                and value["peace_context"].get("war_id") == war_id))


def _case_contract(spec: dict[str, object], value: object,
                   summary: dict[str, object], war_id: str,
                   source_capability_acknowledged: bool = True) -> dict[str, bool]:
    raw_status = summary.get("raw_legality_status")
    source_match = summary.get("actual_source_matches")
    source_ok = (
        True if spec.get("mode") == "candidate" else
        source_match is True or (
            source_match is None and raw_status in ("unavailable", "unknown")))
    beneficiary_match = summary.get("actual_beneficiary_matches")
    beneficiary_ok = (
        True if spec.get("mode") == "candidate" else
        beneficiary_match is True or (
            beneficiary_match is None and raw_status in ("unavailable", "unknown")))
    reparations_ok = summary.get("reparations_pair_matches")
    if "expected_reparations_payer" in spec:
        reparations_ok = reparations_ok is True or (
            reparations_ok is None and raw_status in ("unavailable", "unknown"))
    else:
        reparations_ok = True
    return {
        "object": isinstance(value, dict),
        "identity": _identity_contract(value, spec, war_id),
        "source_match_or_explicit_unknown": source_ok,
        "beneficiary_match_or_explicit_unknown": beneficiary_ok,
        "reparations_pair_match_or_explicit_unknown": reparations_ok is True,
        "candidate_unknown_when_requested": (
            summary.get("legality_status") == "unknown"
            if spec.get("mode") == "candidate" else True),
        "candidate_list_complete": (
            summary.get("candidate_list_complete") is True
            if spec.get("mode") == "candidate" else True),
        "no_business_submission": summary.get("submitted") is not True,
        "no_private_fields": summary.get("private_fields_present") is False,
        "native_source_capability_ack": source_capability_acknowledged is True,
    }


def _offline_contract_assertions() -> None:
    war_id = "war_0123456789abcdef_01234567"
    specs = _case_specs(war_id)
    assert [spec["name"] for spec in specs] == list(_CASE_NAMES)
    assert specs[0]["parameters"]["peace_context"]["terms"] == []
    assert specs[1]["parameters"]["peace_context"]["terms"][0]["source"] == "UTR"
    assert specs[2]["parameters"]["peace_context"]["terms"][0]["source"] == "ENG"
    assert specs[3]["parameters"]["peace_context"]["terms"][0]["beneficiary"] == "ENG"
    terms = specs[4]["parameters"]["peace_context"]["terms"]
    assert [term["action_id"] for term in terms] == [_REPARATIONS_ACTION, _TRADE_POWER_ACTION]
    assert terms[0]["payer"] == "ENG" and terms[0]["claimant"] == "FRA"
    assert terms[1]["source"] == "UTR" and terms[1]["beneficiary"] == "FRA"
    candidate_result = {
        "action_id": _TRADE_POWER_ACTION,
        "family": "peace", "actor": _ACTOR, "recipient": _RECIPIENT,
        "phase": "initiate", "selected_war_id": war_id,
        "interface_support": {"query": "native_peace_execution_inspection"},
        "legality": {"status": "unavailable", "complete": True},
        "native_trade_power": {
            "candidate_count": 1,
            "candidate_enumeration_complete": True,
            "candidates": [{"source": "ENG"}],
        },
        "peace_context": {"war_id": war_id, "terms": []},
    }
    candidate_summary = _summary(
        candidate_result, specs[0], source_capability_acknowledged=True)
    assert candidate_summary["legality_status"] == "unknown"
    assert candidate_summary["candidate_list_complete"] is True


def _control_is_expected(value: object, expected_date: object) -> bool:
    return _control_is_paused_por(value, expected_date)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="唯一报告文件路径（建议 .../report.json）或新报告目录")
    args = parser.parse_args(argv)
    _offline_contract_assertions()

    report_path: Path | None = None
    evidence: Path | None = None
    session: ObserverSession | None = None
    log_start: int | None = None
    log_path: Path | None = None
    report: dict[str, Any] = {
        "validator": Path(__file__).name,
        "version": 1,
        "mode": "read_only_peace_trade_power_source_queries",
        "status": "running",
        "installation": str(args.installation),
        "actor": _ACTOR,
        "recipient": _RECIPIENT,
        "discovery_query_count": 0,
        "query_call_count": 0,
        "candidate_mode_source": "-",
        "case_count": len(_CASE_NAMES),
        "cases": {},
        "request_parameters": {},
        "execute_call_count": 0,
        "business_submission": False,
        "advance_requested": False,
        "save_requested": False,
        "restart_requested": False,
    }

    try:
        report_path, evidence = _output_paths(args.output)
        installation = args.installation.expanduser().resolve(strict=True)
        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session"] = {
            key: session.record.get(key)
            for key in ("pid", "session_id", "experiment_id", "dll_sha256")
        }
        capabilities = sorted(session.installation_capabilities())
        report["installation_capabilities"] = capabilities
        report["source_capability_acknowledged"] = (
            "native_peace_trade_power_sources" in capabilities)
        health_before = wait_runtime_ready(
            session, timeout=25.0, restore_minimized=True)
        _write_json(evidence / "health-before.json", health_before)
        before_probe = _run_probe(
            PROBE_SPECS[0], session.record["pid"],
            evidence / "before" / "control_state.json")
        control_before = _control_from_probe(before_probe)
        expected_date = health_before.get("date_raw")
        report["expected_date_raw"] = expected_date
        report["before"] = {
            "health": health_before,
            "control": control_before,
            "control_probe": _compact_control_probe(before_probe),
        }
        if (health_before.get("status") != "ready"
                or health_before.get("complete") is not True
                or not _control_is_expected(control_before, expected_date)):
            raise TradeSourceQueryError(
                "BASELINE_NOT_READY_POR_PAUSED", str(control_before))
        log_path = session.directory / "control-probe.jsonl"
        if not log_path.is_file():
            raise TradeSourceQueryError("NATIVE_LOG_UNAVAILABLE", str(log_path))
        log_start = log_path.stat().st_size

        with DurableJournal(evidence / "diplomacy.sqlite3",
                            session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            try:
                discovery = api.inspect_diplomatic_action(
                    _DISCOVERY_ACTION, _ACTOR, _RECIPIENT,
                    phase="initiate", parameters={})
            except Exception as error:
                discovery = {
                    "error_code": "QUERY_WAR_DISCOVERY_FAILED",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            _write_json(evidence / "war-discovery.json", discovery)
            report["war_discovery"] = discovery
            report["discovery_query_count"] = 1
            war_id = _single_discovered_war_id(
                discovery, _ACTOR, _RECIPIENT)
            if war_id is None or _WAR_ID.fullmatch(war_id) is None:
                raise TradeSourceQueryError(
                    "PEACE_WAR_DISCOVERY_INCOMPLETE", "no unique FRA/ENG war")
            report["war_id"] = war_id
            if _has_private_fields(discovery):
                raise TradeSourceQueryError(
                    "PUBLIC_QUERY_CONTAINS_PRIVATE_IDENTIFIER",
                    "war discovery exposed native-only fields")

            for spec in _case_specs(war_id):
                name = str(spec["name"])
                parameters = spec["parameters"]
                input_path = evidence / f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', name)}-input.json"
                result_path = evidence / _query_file_name(name)
                _write_json(input_path, {
                    "action_id": spec["action_id"],
                    "actor": _ACTOR,
                    "recipient": _RECIPIENT,
                    "phase": "initiate",
                    "mode": spec["mode"],
                    "requested_source": spec["requested_source"],
                    "expected_beneficiary": spec["expected_beneficiary"],
                    "parameters": parameters,
                })
                try:
                    result = api.inspect_diplomatic_action(
                        str(spec["action_id"]), _ACTOR, _RECIPIENT,
                        phase="initiate", parameters=parameters)
                except Exception as error:
                    result = {
                        "error_code": "QUERY_TRADE_POWER_SOURCE_FAILED",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                report["query_call_count"] += 1
                _write_json(result_path, result)
                summary = _summary(
                    result, spec,
                    source_capability_acknowledged=(
                        report.get("source_capability_acknowledged") is True))
                report["request_parameters"][name] = parameters
                report["cases"][name] = {
                    "input_path": str(input_path),
                    "result_path": str(result_path),
                    "native_events_slice": "native-events-slice.jsonl",
                    "input": {
                        "action_id": spec["action_id"],
                        "direction": spec["direction"],
                        "requested_source": spec["requested_source"],
                        "expected_beneficiary": spec["expected_beneficiary"],
                        "parameters": parameters,
                    },
                    "summary": summary,
                    "checks": _case_contract(
                        spec, result, summary, war_id,
                        report.get("source_capability_acknowledged") is True),
                }
            report["total_inspection_call_count"] = (
                report["discovery_query_count"] + report["query_call_count"])

        health_after = session.health()
        _write_json(evidence / "health-after.json", health_after)
        after_probe = _run_probe(
            PROBE_SPECS[0], session.record["pid"],
            evidence / "after" / "control_state.json")
        control_after = _control_from_probe(after_probe)
        report["after"] = {
            "health": health_after,
            "control": control_after,
            "control_probe": _compact_control_probe(after_probe),
        }
        case_checks = [
            row.get("checks", {})
            for row in report["cases"].values()
            if isinstance(row, dict)
        ]
        candidate = report["cases"].get(_CASE_NAMES[0], {})
        default = report["cases"].get(_CASE_NAMES[2], {})
        candidate_summary = candidate.get("summary", {}) if isinstance(candidate, dict) else {}
        default_summary = default.get("summary", {}) if isinstance(default, dict) else {}
        report["checks"] = {
            "before_health_ready": health_before.get("status") == "ready"
            and health_before.get("complete") is True,
            "before_por_paused": _control_is_expected(control_before, expected_date),
            "discovery_public_contract": _public_context_contract(
                report.get("war_discovery"), _ACTOR, _RECIPIENT),
            "discovery_one_war": _single_discovered_war_id(
                report.get("war_discovery"), _ACTOR, _RECIPIENT)
                == report.get("war_id"),
            "five_case_batch": report["query_call_count"] == len(_CASE_NAMES)
            and len(report["cases"]) == len(_CASE_NAMES),
            "case_contracts": all(
                all(checks.values()) for checks in case_checks),
            "candidate_status_unknown": (
                candidate_summary.get("legality_status") == "unknown"),
            "candidate_list_complete": (
                candidate_summary.get("candidate_list_complete") is True),
            "source_capability_acknowledged": (
                report.get("source_capability_acknowledged") is True),
            "default_missing_candidate_unknown": (
                default_summary.get("candidate_found") is not False
                or default_summary.get("legality_status") == "unknown"),
            "after_health_ready": health_after.get("status") == "ready"
            and health_after.get("complete") is True,
            "after_por_paused_same_date": (
                _control_is_expected(control_after, expected_date)
                and control_after.get("date_raw") == control_before.get("date_raw")),
            "public_queries_no_private_identifiers": not _has_private_fields(
                report.get("cases")),
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
            "code": error.code if isinstance(error, TradeSourceQueryError)
            else "UNEXPECTED_TRADE_SOURCE_QUERY_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if isinstance(log_start, int) and log_path is not None and evidence is not None:
            try:
                report["native_events"] = _copy_log_slice(
                    log_path, log_start, evidence / "native-events-slice.jsonl")
            except Exception as error:
                report["native_events"] = {
                    "status": "unknown", "error_type": type(error).__name__,
                    "error": str(error),
                }
        if report_path is not None:
            _write_json(report_path, report)
    print(json.dumps({
        "status": report["status"],
        "report": str(report_path) if report_path is not None else None,
        "war_id": report.get("war_id"),
        "query_call_count": report.get("query_call_count"),
    }, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
