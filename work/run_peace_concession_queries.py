#!/usr/bin/env python3
"""Run one bounded, read-only batch of explicit-offer Peace inspections.

The operator discovers the single public FRA--ENG war context and then uses
the native QUERY7-backed offer inspectors in the same paused session:
white-peace, 10/20/100 ducats, and an empty cede-province candidate query.
It selects a bounded number of native candidate provinces and inspects each with
beneficiary ENG.  It never executes an offer, advances time, saves, restarts,
or chooses a province that was not returned by the native candidate query.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
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


_ACTOR = "FRA"
_RECIPIENT = "ENG"
_PLAYER_SLOT = 189  # POR in the controlled observer fixture
_ACTIONS = frozenset(("white_peace", "demand_ducats", "cede_province"))
_WAR_ID = re.compile(r"war_[0-9a-f]{16}_[0-9a-f]{8}\Z")
_TAG = re.compile(r"[A-Z0-9]{3}\Z")
_MAX_REASON_ITEMS = 32
_MAX_CANDIDATES = 64
_MONEY_AMOUNTS = ("10.0", "20.0", "100.0")


class ConcessionQueryError(RuntimeError):
    """A bounded setup or output error; no business operation is retried."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _output_paths(requested: Path) -> tuple[Path, Path]:
    """Create a new report/evidence pair without overwriting an artifact."""

    target = requested.expanduser().resolve()
    if target.exists():
        raise ConcessionQueryError("OUTPUT_ALREADY_EXISTS", str(target))
    if target.suffix.casefold() == ".json":
        report_path = target
        evidence = target.parent / f"{target.stem}-evidence"
    else:
        report_path = target / "report.json"
        evidence = target
    if report_path.exists() or evidence.exists():
        raise ConcessionQueryError("OUTPUT_ALREADY_EXISTS", str(report_path))
    evidence.mkdir(parents=True, exist_ok=False)
    return report_path, evidence


def _money_raw(amount: str) -> int:
    """Convert a one-decimal ducat string to the native 1/1000 scale."""

    try:
        value = Decimal(amount)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ConcessionQueryError("MONEY_AMOUNT_INVALID", str(amount)) from error
    if not value.is_finite() or value <= 0 or value.as_tuple().exponent < -1:
        raise ConcessionQueryError("MONEY_AMOUNT_INVALID", str(amount))
    raw = value * Decimal(1000)
    if raw != raw.to_integral_value():
        raise ConcessionQueryError("MONEY_AMOUNT_INVALID", str(amount))
    result = int(raw)
    if result <= 0 or result > 2_147_483_647 or result % 100:
        raise ConcessionQueryError("MONEY_AMOUNT_INVALID", str(amount))
    return result


def _control_from_probe(value: object) -> dict[str, object]:
    snapshot = value.get("snapshot") if isinstance(value, dict) else None
    if not isinstance(snapshot, dict):
        return {"date_raw": None, "paused_flag": None, "player_slot": None}
    return {
        "date_raw": snapshot.get("date_raw"),
        "paused_flag": snapshot.get("paused_flag"),
        "player_slot": snapshot.get("player_slot"),
    }


def _compact_control_probe(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {"status": "unknown", "snapshot_completeness": None}
    return {
        "status": value.get("status"),
        "name": value.get("name"),
        "script": value.get("script"),
        "snapshot_path": value.get("snapshot_path"),
        "snapshot_completeness": value.get("snapshot_completeness"),
    }


def _control_is_paused_por(value: object, expected_date: object) -> bool:
    return (isinstance(value, dict)
            and type(expected_date) is int
            and value.get("date_raw") == expected_date
            and value.get("paused_flag") == 1
            and value.get("player_slot") == _PLAYER_SLOT)


def _bounded_text(value: object, limit: int = 512) -> str | None:
    if not isinstance(value, str):
        return None
    return value if len(value) <= limit else value[:limit]


def _reason_item(value: object) -> dict[str, object] | None:
    """Keep only public, stable reason fields for the human summary."""

    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    for key in (
            "code", "native_identifier", "source", "complete", "native_value",
            "native_value_verified", "identifier_verified", "row_binding_verified",
            "native_flag", "native_flag_verified", "text_decoded", "text_truncated"):
        if key in value:
            result[key] = value[key]
    if "text" in value:
        result["text"] = _bounded_text(value.get("text"))
    return result


def _reason_list(value: object, *, limit: int = _MAX_REASON_ITEMS) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    for item in value[:limit]:
        compact = _reason_item(item)
        if compact is not None:
            result.append(compact)
    return result


def _acceptance_summary(value: object) -> dict[str, object]:
    acceptance = value if isinstance(value, dict) else {}
    return {
        "applicability": acceptance.get("applicability"),
        "complete": acceptance.get("complete"),
        "details_available": acceptance.get("details_available"),
        "details_complete": acceptance.get("details_complete"),
        "native_total": acceptance.get("native_total"),
        "predicted_response": acceptance.get("predicted_response"),
        "prediction_available": acceptance.get("prediction_available"),
        "scale_verified": acceptance.get("scale_verified"),
        "unit": acceptance.get("unit"),
        "reasons": _reason_list(acceptance.get("items")),
    }


def _native_evaluation_summary(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {
        "called": value.get("called"),
        "score_available": value.get("score_available"),
        "score_raw": value.get("score_raw"),
        "native_total": value.get("native_total"),
        "aggregate_score_available": value.get("aggregate_score_available"),
        "aggregate_score_raw": value.get("aggregate_score_raw"),
        "factor_native_count": value.get("factor_native_count"),
        "factors_available": value.get("factors_available"),
        "factors_complete": value.get("factors_complete"),
        "factor_capture_truncated": value.get("factor_capture_truncated"),
        "reasons": _reason_list(value.get("items")),
    }


def _peace_context_summary(value: object) -> dict[str, object]:
    context = value if isinstance(value, dict) else {}
    terms = context.get("terms")
    compact_terms: list[dict[str, object]] = []
    if isinstance(terms, list):
        for term in terms[:4]:
            if not isinstance(term, dict):
                continue
            compact: dict[str, object] = {
                "action_id": term.get("action_id"),
                "amount": term.get("amount"),
                "amount_raw": term.get("amount_raw"),
                "payer": term.get("payer"),
                "claimant": term.get("claimant"),
                "province_ids": list(term.get("province_ids", []))
                if isinstance(term.get("province_ids"), list) else None,
                "beneficiary": term.get("beneficiary"),
            }
            compact_terms.append(compact)
    return {
        "war_id": context.get("war_id"),
        "direction": context.get("direction"),
        "complete": context.get("complete"),
        "terms": compact_terms,
    }


def _candidate_summary(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    for key in ("province_id", "beneficiary", "selected", "name_readable",
                "name_truncated", "native_selectability_checked", "native_selectable"):
        if key in value:
            result[key] = value[key]
    if "name" in value:
        result["name"] = _bounded_text(value.get("name"), 128)
    return result


def _native_province_summary(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    candidates = value.get("candidates")
    compact_candidates = []
    if isinstance(candidates, list):
        for row in candidates[:_MAX_CANDIDATES]:
            compact = _candidate_summary(row)
            if compact is not None:
                compact_candidates.append(compact)
    return {
        "query_complete": value.get("query_complete"),
        "candidate_enumeration_complete": value.get("candidate_enumeration_complete"),
        "candidate_count": value.get("candidate_count"),
        "direction": value.get("direction"),
        "direction_verified": value.get("direction_verified"),
        "selection_requested": value.get("selection_requested"),
        "requested_province_ids": list(value.get("requested_province_ids", []))
        if isinstance(value.get("requested_province_ids"), list) else None,
        "requested_beneficiary": value.get("requested_beneficiary"),
        "requested_candidates_found": value.get("requested_candidates_found"),
        "toggle_called": value.get("toggle_called"),
        "parameters_matched": value.get("parameters_matched"),
        "selected_province_ids": list(value.get("selected_province_ids", []))
        if isinstance(value.get("selected_province_ids"), list) else None,
        "selected_beneficiary": value.get("selected_beneficiary"),
        "selection_copy_verified": value.get("selection_copy_verified"),
        "selected_term_records_complete": value.get("selected_term_records_complete"),
        "reason_code": value.get("reason_code"),
        "selection_delta_raw": value.get("selection_delta_raw"),
        "candidates": compact_candidates,
    }


def _query_summary(value: object, *, amount_raw: int | None = None) -> dict[str, object]:
    """Project the public inspection into bounded selection evidence."""

    inspection = value if isinstance(value, dict) else {}
    context = inspection.get("peace_context")
    context_summary = _peace_context_summary(context)
    terms = context_summary.get("terms")
    actual_payer = None
    actual_claimant = None
    if isinstance(terms, list) and terms and isinstance(terms[0], dict):
        actual_payer = terms[0].get("payer")
        actual_claimant = terms[0].get("claimant")
    native_money = inspection.get("native_money")
    if isinstance(native_money, dict):
        actual_payer = native_money.get("payer") or actual_payer
        actual_claimant = native_money.get("claimant") or actual_claimant
    acceptance = _acceptance_summary(inspection.get("acceptance"))
    evaluation = _native_evaluation_summary(inspection.get("native_evaluation"))
    native_total = acceptance.get("native_total")
    if native_total is None and isinstance(evaluation, dict):
        native_total = evaluation.get("native_total")
    result: dict[str, object] = {
        "event": inspection.get("event"),
        "family": inspection.get("family"),
        "action_id": inspection.get("action_id"),
        "actor": inspection.get("actor"),
        "recipient": inspection.get("recipient"),
        "phase": inspection.get("phase"),
        "selected_war_id": inspection.get("selected_war_id"),
        "pair_at_war": inspection.get("pair_at_war"),
        "query_complete": inspection.get("query_complete"),
        "peace_context": context_summary,
        "legality": {
            "status": inspection.get("legality", {}).get("status")
            if isinstance(inspection.get("legality"), dict) else None,
            "complete": inspection.get("legality", {}).get("complete")
            if isinstance(inspection.get("legality"), dict) else None,
            "reasons": _reason_list(
                inspection.get("legality", {}).get("reasons")
                if isinstance(inspection.get("legality"), dict) else None),
        },
        "acceptance": acceptance,
        "acceptance_reasons": acceptance.get("reasons"),
        "native_total": native_total,
        "native_evaluation": evaluation,
        "actual_payer": actual_payer,
        "actual_claimant": actual_claimant,
        "native_money": None,
        "amount_cap": None,
        "native_provinces": _native_province_summary(
            inspection.get("native_provinces")),
    }
    if isinstance(native_money, dict):
        result["native_money"] = {
            "query_complete": native_money.get("query_complete"),
            "requested_amount_raw": native_money.get("requested_amount_raw"),
            "direction": native_money.get("direction"),
            "direction_verified": native_money.get("direction_verified"),
            "payer": native_money.get("payer"),
            "claimant": native_money.get("claimant"),
            "parameters_matched": native_money.get("parameters_matched"),
            "amount_within_limit": native_money.get("amount_within_limit"),
            "setter_called": native_money.get("setter_called"),
            "source_readback_matches": native_money.get("source_readback_matches"),
            "action_copy_verified": native_money.get("action_copy_verified"),
        }
        result["amount_cap"] = {
            "requested_amount_raw": native_money.get("requested_amount_raw"),
            "currency_scale": native_money.get("currency_scale"),
            "currency_precision_raw": native_money.get("currency_precision_raw"),
            "ceiling_input_raw": native_money.get("ceiling_input_raw"),
            "currency_ceiling_raw": native_money.get("currency_ceiling_raw"),
            "amount_within_limit": native_money.get("amount_within_limit"),
            "observed_amount_raw": amount_raw,
        }
    return result


def _offer_identity_contract(value: object, action_id: str,
                             war_id: str) -> bool:
    if not isinstance(value, dict):
        return False
    if any(value.get(key) != expected for key, expected in (
            ("family", "peace"), ("action_id", action_id),
            ("actor", _ACTOR), ("recipient", _RECIPIENT),
            ("phase", "initiate"), ("selected_war_id", war_id),
            ("pair_at_war", True))):
        return False
    interface = value.get("interface_support")
    if (not isinstance(interface, dict)
            or not isinstance(interface.get("query"), str)
            or not interface["query"].startswith("native_peace_")):
        return False
    context = value.get("peace_context")
    if (not isinstance(context, dict)
            or context.get("war_id") != war_id
            or context.get("direction") != "offer"
            or not isinstance(context.get("terms"), list)):
        return False
    return not _has_private_fields(value)


def _money_offer_contract(value: object, war_id: str, amount_raw: int) -> bool:
    if not _offer_identity_contract(value, "demand_ducats", war_id):
        return False
    native = value.get("native_money") if isinstance(value, dict) else None
    return (isinstance(native, dict)
            and native.get("requested_amount_raw") == amount_raw
            and native.get("direction") == "offer"
            and native.get("direction_verified") is True
            and native.get("payer") == _ACTOR
            and native.get("claimant") == _RECIPIENT)


def _province_offer_contract(value: object, war_id: str,
                             province_ids: list[int] | None = None) -> bool:
    if not _offer_identity_contract(value, "cede_province", war_id):
        return False
    native = value.get("native_provinces") if isinstance(value, dict) else None
    if not isinstance(native, dict):
        return False
    if (native.get("direction") != "offer"
            or native.get("direction_verified") is not True):
        return False
    if province_ids is not None:
        return (native.get("requested_province_ids") == province_ids
                and native.get("requested_beneficiary") == _RECIPIENT)
    return (native.get("requested_province_ids") == []
            and native.get("requested_beneficiary") is None)


def _candidate_rows(value: object) -> list[dict[str, object]]:
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
        if (isinstance(province_id, bool) or not isinstance(province_id, int)
                or not 1 <= province_id <= 2_147_483_647
                or province_id in seen
                or row.get("beneficiary") != _RECIPIENT):
            continue
        # The native candidate list is the authoritative availability list.
        # If a future producer adds a per-row selectability check, keep only
        # rows it explicitly marks selectable; an unchecked row remains a
        # native candidate and is tested by the selected inspection below.
        if (row.get("native_selectability_checked") is True
                and row.get("native_selectable") is not True):
            continue
        seen.add(province_id)
        result.append(row)
    return result


def _query_file_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name) + ".json"


def _offline_contract_assertions() -> None:
    assert _money_raw("10.0") == 10000
    assert _money_raw("20.0") == 20000
    assert _money_raw("100.0") == 100000
    synthetic = {
        "family": "peace", "action_id": "cede_province", "actor": "FRA",
        "recipient": "ENG", "phase": "initiate", "selected_war_id":
        "war_0123456789abcdef_01234567", "pair_at_war": True,
        "interface_support": {"query": "native_peace_province_offer_inspection"},
        "peace_context": {"war_id": "war_0123456789abcdef_01234567",
                           "direction": "offer", "terms": []},
        "native_provinces": {
            "direction": "offer", "direction_verified": True,
            "candidates": [
                {"province_id": 185, "beneficiary": "FRA",
                 "native_selectability_checked": False},
                {"province_id": 186, "beneficiary": "ENG",
                 "native_selectability_checked": False},
            ],
        },
    }
    rows = _candidate_rows(synthetic)
    assert [row["province_id"] for row in rows] == [186]
    assert _province_offer_contract(
        {**synthetic, "native_provinces": {**synthetic["native_provinces"],
            "requested_province_ids": [], "requested_beneficiary": None}},
        "war_0123456789abcdef_01234567")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="新的报告文件路径或报告目录")
    parser.add_argument("--max-province-queries", type=int, default=2,
                        help="逐项查询原生省份候选的上限，1..64，默认2")
    args = parser.parse_args(argv)
    if not 1 <= args.max_province_queries <= _MAX_CANDIDATES:
        parser.error("--max-province-queries must be within 1..64")
    _offline_contract_assertions()

    report_path: Path | None = None
    evidence: Path | None = None
    report: dict[str, Any] = {
        "validator": Path(__file__).name,
        "version": 1,
        "mode": "read_only_peace_concession_queries",
        "status": "running",
        "installation": str(args.installation),
        "actor": _ACTOR,
        "recipient": _RECIPIENT,
        "direction": "offer",
        "query_call_count": 0,
        "province_query_limit": args.max_province_queries,
        "execute_call_count": 0,
        "business_submission": False,
        "advance_requested": False,
        "save_requested": False,
        "restart_requested": False,
        "queries": {},
        "summaries": {},
        "request_parameters": {},
    }
    log_start: int | None = None
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
            "control_probe": _compact_control_probe(before_probe),
        }
        if (health_before.get("status") != "ready"
                or health_before.get("complete") is not True
                or not _control_is_paused_por(control_before, expected_date)):
            raise ConcessionQueryError(
                "BASELINE_NOT_READY_POR_PAUSED", str(control_before))
        log_path = session.directory / "control-probe.jsonl"
        log_start = log_path.stat().st_size

        with DurableJournal(evidence / "diplomacy.sqlite3",
                            session.experiment_id, session.session_id) as journal:
            api = DiplomacyTools(journal, session)

            def store(name: str, value: object) -> dict[str, object]:
                report["query_call_count"] += 1
                output = value if isinstance(value, dict) else {
                    "status": "unknown", "error": "INSPECTION_NOT_OBJECT",
                }
                _write_json(evidence / _query_file_name(name), output)
                report["queries"][name] = {
                    "path": str(evidence / _query_file_name(name)),
                    "object": isinstance(value, dict),
                }
                report["summaries"][name] = _query_summary(output)
                return output

            discovery = store(
                "discovery-white-peace",
                api.inspect_diplomatic_action(
                    "white_peace", _ACTOR, _RECIPIENT,
                    phase="initiate", parameters={}),
            )
            report["request_parameters"]["discovery-white-peace"] = {}
            war_id = _single_discovered_war_id(
                discovery, _ACTOR, _RECIPIENT)
            if war_id is None or _WAR_ID.fullmatch(war_id) is None:
                raise ConcessionQueryError(
                    "PEACE_WAR_DISCOVERY_INCOMPLETE", "no unique FRA/ENG war")
            report["war_id"] = war_id

            white_parameters = {
                "peace_context": {
                    "war_id": war_id,
                    "direction": "offer",
                    "terms": [],
                },
            }
            try:
                # Keep every selected query on the public unified interface.
                # The private QUERY helper methods are implementation details
                # of DiplomacyTools and are intentionally not part of this
                # operator's wire contract.
                white = api.inspect_diplomatic_action(
                    "white_peace", _ACTOR, _RECIPIENT,
                    phase="initiate", parameters=white_parameters)
            except Exception as error:
                white = {"error_code": "QUERY_WHITE_OFFER_FAILED",
                         "error_type": type(error).__name__, "error": str(error)}
            store("offer-white-peace", white)
            report["request_parameters"]["offer-white-peace"] = white_parameters

            for amount in _MONEY_AMOUNTS:
                amount_raw = _money_raw(amount)
                selection = {
                    "war_id": war_id,
                    "direction": "offer",
                    "amount_raw": amount_raw,
                    "payer": _ACTOR,
                    "claimant": _RECIPIENT,
                }
                parameters = {
                    "peace_context": {
                        "war_id": war_id,
                        "direction": "offer",
                        "terms": [{
                            "action_id": "demand_ducats",
                            "amount": amount,
                            "payer": _ACTOR,
                            "claimant": _RECIPIENT,
                        }],
                    },
                }
                try:
                    result = api.inspect_diplomatic_action(
                        "demand_ducats", _ACTOR, _RECIPIENT,
                        phase="initiate", parameters=parameters)
                except Exception as error:
                    result = {"error_code": "QUERY_MONEY_OFFER_FAILED",
                              "error_type": type(error).__name__, "error": str(error)}
                name = f"offer-money-{amount.replace('.', '_')}"
                report["summaries"][name] = _query_summary(
                    result, amount_raw=amount_raw)
                _write_json(evidence / _query_file_name(name), result)
                report["queries"][name] = {
                    "path": str(evidence / _query_file_name(name)),
                    "object": isinstance(result, dict),
                    "requested_amount": amount,
                    "requested_amount_raw": amount_raw,
                }
                report["request_parameters"][name] = parameters
                report["query_call_count"] += 1

            candidate_selection = {
                "war_id": war_id,
                "direction": "offer",
                "province_ids": [],
                "beneficiary": None,
            }
            candidate_parameters = {
                "peace_context": {
                    "war_id": war_id,
                    "direction": "offer",
                    "terms": [],
                },
            }
            try:
                candidates = api.inspect_diplomatic_action(
                    "cede_province", _ACTOR, _RECIPIENT,
                    phase="initiate", parameters=candidate_parameters)
            except Exception as error:
                candidates = {"error_code": "QUERY_PROVINCE_CANDIDATES_FAILED",
                              "error_type": type(error).__name__, "error": str(error)}
            store("offer-province-candidates", candidates)
            report["request_parameters"]["offer-province-candidates"] = candidate_parameters
            available = _candidate_rows(candidates)
            report["candidate_selection"] = {
                "offer_beneficiary": _RECIPIENT,
                "candidate_count_considered": len(available),
                "available_candidates": [
                    _candidate_summary(row) for row in available[:_MAX_CANDIDATES]
                ],
                "selection_basis": "native_candidate_beneficiary_ENG",
                "selected_ids": [],
            }
            for row in available[:args.max_province_queries]:
                province_id = row["province_id"]
                selection = {
                    "war_id": war_id,
                    "direction": "offer",
                    "province_ids": [province_id],
                    "beneficiary": _RECIPIENT,
                }
                parameters = {
                    "peace_context": {
                        "war_id": war_id,
                        "direction": "offer",
                        "terms": [{
                            "action_id": "cede_province",
                            "province_ids": [province_id],
                            "beneficiary": _RECIPIENT,
                        }],
                    },
                }
                try:
                    result = api.inspect_diplomatic_action(
                        "cede_province", _ACTOR, _RECIPIENT,
                        phase="initiate", parameters=parameters)
                except Exception as error:
                    result = {"error_code": "QUERY_PROVINCE_SELECTION_FAILED",
                              "error_type": type(error).__name__, "error": str(error)}
                name = f"offer-province-{province_id}"
                _write_json(evidence / _query_file_name(name), result)
                report["queries"][name] = {
                    "path": str(evidence / _query_file_name(name)),
                    "object": isinstance(result, dict),
                    "requested_province_id": province_id,
                    "requested_beneficiary": _RECIPIENT,
                }
                report["request_parameters"][name] = parameters
                report["summaries"][name] = _query_summary(result)
                report["candidate_selection"]["selected_ids"].append(province_id)
                report["query_call_count"] += 1

        health_after = session.health()
        after_probe = _run_probe(
            PROBE_SPECS[0], session.record["pid"],
            evidence / "after" / "control_state.json")
        control_after = _control_from_probe(after_probe)
        report["after"] = {
            "health": health_after,
            "control": control_after,
            "control_probe": _compact_control_probe(after_probe),
        }

        queries = {}
        for name, metadata in report["queries"].items():
            path = Path(metadata["path"])
            try:
                queries[name] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                queries[name] = None
        discovery = queries.get("discovery-white-peace")
        white = queries.get("offer-white-peace")
        candidate_query = queries.get("offer-province-candidates")
        money_names = [f"offer-money-{amount.replace('.', '_')}"
                       for amount in _MONEY_AMOUNTS]
        selected_names = [
            name for name in queries
            if name.startswith("offer-province-")
            and name != "offer-province-candidates"
        ]
        candidate_native = (candidate_query.get("native_provinces")
                            if isinstance(candidate_query, dict) else None)
        report["checks"] = {
            "before_health_ready": health_before.get("status") == "ready"
            and health_before.get("complete") is True,
            "before_por_paused": _control_is_paused_por(control_before, expected_date),
            "discovery_public_contract": _public_context_contract(
                discovery, _ACTOR, _RECIPIENT),
            "discovery_one_war": _single_discovered_war_id(
                discovery, _ACTOR, _RECIPIENT) == report.get("war_id"),
            "white_offer_contract": _offer_identity_contract(
                white, "white_peace", report.get("war_id")),
            "money_offer_contracts": all(
                _money_offer_contract(
                    queries.get(name), report.get("war_id"), _money_raw(amount))
                for name, amount in zip(money_names, _MONEY_AMOUNTS)),
            "candidate_query_contract": _province_offer_contract(
                candidate_query, report.get("war_id")),
            "candidate_enumeration_complete": isinstance(candidate_native, dict)
            and candidate_native.get("candidate_enumeration_complete") is True,
            "selected_queries_bound_to_candidates": all(
                _province_offer_contract(
                    queries.get(name), report.get("war_id"),
                    [int(name.rsplit("-", 1)[1])])
                for name in selected_names),
            "selected_queries_within_requested_limit": len(selected_names) <= args.max_province_queries,
            "after_health_ready": health_after.get("status") == "ready"
            and health_after.get("complete") is True,
            "after_por_paused_same_date": (
                _control_is_paused_por(control_after, expected_date)
                and control_after.get("date_raw") == control_before.get("date_raw")),
            "public_queries_no_private_identifiers": not _has_private_fields(queries),
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
            "code": error.code if isinstance(error, ConcessionQueryError)
            else "UNEXPECTED_CONCESSION_QUERY_ERROR",
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
