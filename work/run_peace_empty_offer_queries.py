"""Run read-only empty-white-peace inspections for one paused batch.

The operator first discovers the one shared opaque war id for each requested
country pair, then sends the same id back through the unified diplomatic
inspection interface with an empty ``peace_context``.  It never submits an
offer, advances time, saves the game, or changes the controlled country.

``--require-evaluation`` enables the later R38C score/factor contract while
leaving the R38B construction-only acceptance unchanged by default.
"""
from __future__ import annotations

import argparse
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
from work.run_alliance_execution import _copy_log_slice, _write_json
from work.run_improve_relations_execution import _new_artifact
from work.run_royal_marriage_execution import (
    _installation_binding, _public_probe_records, _snapshots_complete,
)
from work.validate_alliance_reload import _control_summary, _run_snapshots


WAR_ID = re.compile(r"war_[0-9a-f]{16}_[0-9a-f]{8}\Z")
FORBIDDEN_PUBLIC_KEYS = frozenset({
    "pid", "session_id", "creation_filetime", "native_war_reference",
    "native_reference", "module_base", "vtable_rva", "dll_sha256",
})

CASES = (
    ("fra_eng", "FRA", "ENG"),
    ("eng_fra", "ENG", "FRA"),
    ("fra_tyr", "FRA", "TYR"),
    ("fra_eng_repeat", "FRA", "ENG"),
)


def _has_private_fields(value: object) -> bool:
    """Return whether a public query projection contains native-only data."""

    if isinstance(value, dict):
        return bool(FORBIDDEN_PUBLIC_KEYS.intersection(value)) or any(
            _has_private_fields(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_private_fields(item) for item in value)
    return False


def _public_context_contract(value: object, actor: str, recipient: str) -> bool:
    """Validate the public QUERY1 projection without inferring war roles."""

    if not isinstance(value, dict):
        return False
    if any(value.get(key) != wanted for key, wanted in (
        ("family", "peace"), ("action_id", "white_peace"),
        ("actor", actor), ("recipient", recipient), ("phase", "initiate"),
        ("context_discovery", True), ("query_complete", True),
        ("war_context_enumeration_complete", True),
        ("native_offer_inspected", False),
    )):
        return False
    interface_support = value.get("interface_support")
    if (not isinstance(interface_support, dict)
            or interface_support.get("query")
                != "native_peace_context_inspection"):
        return False
    for field in ("full_rules_complete", "submitted"):
        if field in value and value.get(field) is not False:
            return False
    wars = value.get("war_contexts")
    if not isinstance(wars, list) or len(wars) > 32:
        return False
    for row in wars:
        if not isinstance(row, dict):
            return False
        war_id = row.get("war_id")
        if (not isinstance(war_id, str)
                or WAR_ID.fullmatch(war_id) is None
                or row.get("identity_scope") != "observer_session"
                or row.get("actor") != actor
                or row.get("recipient") != recipient
                or row.get("pair_at_war") is not True):
            return False
        # The current public contract intentionally leaves roles and leaders
        # unknown.  If a producer includes those fields, it must keep them
        # explicitly unknown rather than turning a context query into role
        # evidence.
        for field in ("actor_war_role", "recipient_war_role",
                      "actor_is_war_leader", "recipient_is_war_leader"):
            if field in row and row.get(field) is not None:
                return False
        for field in ("roles_verified", "leaders_verified", "context_complete"):
            if field in row and not isinstance(row.get(field), bool):
                return False
    return True


def _single_discovered_war_id(value: object, actor: str, recipient: str) -> str | None:
    """Return the sole public war id, or ``None`` for an incomplete result."""

    if not _public_context_contract(value, actor, recipient):
        return None
    wars = value["war_contexts"]
    if len(wars) != 1:
        return None
    return wars[0]["war_id"]


def _public_empty_offer_contract(
        value: object, actor: str, recipient: str, expected_war_id: str) -> bool:
    """Validate QUERY4 construction evidence and its three bool gate values."""

    if not isinstance(value, dict) or not isinstance(expected_war_id, str):
        return False
    if (WAR_ID.fullmatch(expected_war_id) is None
            or any(value.get(key) != wanted for key, wanted in (
                ("family", "peace"), ("action_id", "white_peace"),
                ("actor", actor), ("recipient", recipient),
                ("phase", "initiate"),
                ("selected_war_id", expected_war_id),
                ("identity_scope", "observer_session"),
            ))):
        return False
    interface_support = value.get("interface_support")
    if (not isinstance(interface_support, dict)
            or interface_support.get("query")
                != "native_peace_empty_offer_inspection"):
        return False
    context = value.get("peace_context")
    if (not isinstance(context, dict)
            or context.get("war_id") != expected_war_id
            or context.get("terms") != []
            or context.get("complete") is not False):
        return False
    required_true = (
        "query_complete", "native_offer_inspected", "pair_at_war",
        "unique_shared_war", "offer_constructed", "action_constructed",
        "participant_copy_verified", "offer_identity_verified",
        "object_unchanged", "cleanup_verified", "validity_called",
        "common_gate_checked", "initiation_gate_checked",
    )
    if any(value.get(field) is not True for field in required_true):
        return False
    if any(value.get(field) is not False for field in (
            "full_rules_complete", "reasons_complete", "submitted")):
        return False
    # The values are observations of three separate native gates.  A query
    # operator may record false without converting it into a submission or an
    # inferred acceptance decision.
    if any(not isinstance(value.get(field), bool) for field in (
            "native_validity", "common_action_gate", "initiation_gate")):
        return False
    return True


def _is_scope_refusal(value: object) -> bool:
    """Recognize the public controlled-country refusal without weakening it."""

    if not isinstance(value, dict):
        return False
    if value.get("error_code") == "QUERY_INFORMATION_SCOPE_UNAVAILABLE":
        return True
    legality = value.get("legality")
    reasons = legality.get("reasons") if isinstance(legality, dict) else None
    return isinstance(reasons, list) and any(
        isinstance(item, dict)
        and item.get("code") == "QUERY_INFORMATION_SCOPE_UNAVAILABLE"
        for item in reasons)


def _control_is_expected(control: object, expected_date_raw: int) -> bool:
    return control == {
        "date_raw": expected_date_raw,
        "paused_flag": 1,
        "player_slot": 189,
    }


def _evaluation_projection(value: object) -> dict[str, object] | None:
    """Read the explicit public R38C evaluation projection.

    The native score and the aggregate score are different values.  This
    function therefore reads each value only from its specified public path;
    it deliberately has no aliases or fallback between preview and aggregate
    fields.
    """

    if not isinstance(value, dict):
        return None
    native = value.get("native_evaluation")
    if not isinstance(native, dict):
        return None
    acceptance = value.get("acceptance")
    acceptance = acceptance if isinstance(acceptance, dict) else {}
    costs = value.get("costs")
    costs = costs if isinstance(costs, dict) else {}
    cost_evaluation = costs.get("native_evaluation")
    cost_evaluation = (
        cost_evaluation if isinstance(cost_evaluation, dict) else {})
    cross_fields_present = (
        all(key in native for key in (
            "aggregate_score_available", "aggregate_score_raw", "native_total"))
        and "native_total" in acceptance
        and all(key in cost_evaluation for key in (
            "aggregate_score_available", "aggregate_score_raw")))
    result: dict[str, object] = {
        "called": native.get("called"),
        "score_available": native.get("score_available"),
        "score_raw": native.get("score_raw"),
        "native_total": native.get("native_total"),
        "score_representation": native.get("score_representation"),
        "factor_native_count": native.get("factor_native_count"),
        "factor_capture_truncated": native.get("factor_capture_truncated"),
        "factors_available": native.get("factors_available"),
        "items": native.get("items"),
        "native_aggregate_score_available": native.get(
            "aggregate_score_available"),
        "native_aggregate_score_raw": native.get("aggregate_score_raw"),
        "acceptance_native_total": acceptance.get("native_total"),
        "costs_aggregate_score_available": cost_evaluation.get(
            "aggregate_score_available"),
        "costs_aggregate_score_raw": cost_evaluation.get(
            "aggregate_score_raw"),
        "cross_projection_equal": (
            cross_fields_present
            and native.get("aggregate_score_available")
                == cost_evaluation.get("aggregate_score_available")
            and native.get("aggregate_score_raw")
                == cost_evaluation.get("aggregate_score_raw")
            and native.get("native_total") == acceptance.get("native_total")),
    }
    return result


def _evaluation_observation(value: object) -> dict[str, object]:
    """Return bounded public evaluation fields for the final report."""

    projection = _evaluation_projection(value)
    if projection is None:
        return {"present": False, "factor_native_count": None,
                "item_count": None}
    items = projection.get("items")
    return {
        "present": True,
        "called": projection.get("called"),
        "score_available": projection.get("score_available"),
        "score_raw": projection.get("score_raw"),
        "native_total": projection.get("native_total"),
        "native_aggregate_score_available": projection.get(
            "native_aggregate_score_available"),
        "native_aggregate_score_raw": projection.get(
            "native_aggregate_score_raw"),
        "acceptance_native_total": projection.get("acceptance_native_total"),
        "costs_aggregate_score_available": projection.get(
            "costs_aggregate_score_available"),
        "costs_aggregate_score_raw": projection.get(
            "costs_aggregate_score_raw"),
        "cross_projection_equal": projection.get("cross_projection_equal"),
        "factor_native_count": projection.get("factor_native_count"),
        "factors_available": projection.get("factors_available"),
        "item_count": len(items) if isinstance(items, list) else None,
    }


def _evaluation_items_are_valid(projection: dict[str, object]) -> bool:
    """Validate factor item text/value types without requiring any count."""

    items = projection.get("items")
    factors_available = projection.get("factors_available")
    if factors_available is True and not isinstance(items, list):
        return False
    if items is None:
        return factors_available is not True
    if not isinstance(items, list) or len(items) > 64:
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        value = item.get("native_value")
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        text = item.get("text")
        if text is not None and not isinstance(text, str):
            return False
        decoded = item.get("text_decoded")
        if decoded is not None and not isinstance(decoded, bool):
            return False
        if decoded is True and not isinstance(text, str):
            return False
        truncated = item.get("text_truncated")
        if truncated is not None and not isinstance(truncated, bool):
            return False
        for field in ("identifier_verified", "native_value_verified",
                      "native_flag", "native_flag_verified",
                      "row_binding_verified"):
            if field in item and not isinstance(item.get(field), bool):
                return False
    count = projection.get("factor_native_count")
    if (isinstance(count, bool) or not isinstance(count, int)
            or count < 0 or count > 4096 or len(items) > count):
        return False
    return True


def _eng_evaluation_contract(value: object) -> bool:
    """Require a usable aggregate evaluation for one ENG query."""

    projection = _evaluation_projection(value)
    if projection is None:
        return False
    if (projection.get("called") is not True
            or projection.get("score_available") is not True
            or projection.get("score_representation") != "signed_int32"
            or projection.get("cross_projection_equal") is not True):
        return False
    for field in ("score_raw", "native_total",
                  "native_aggregate_score_raw",
                  "acceptance_native_total",
                  "costs_aggregate_score_raw"):
        raw = projection.get(field)
        if isinstance(raw, bool) or not isinstance(raw, int):
            return False
    if (projection.get("native_aggregate_score_available") is not True
            or projection.get("costs_aggregate_score_available") is not True):
        return False
    if (isinstance(projection.get("factor_native_count"), bool)
            or not isinstance(projection.get("factor_native_count"), int)
            or not 0 <= projection["factor_native_count"] <= 4096):
        return False
    if (not isinstance(projection.get("factor_capture_truncated"), bool)
            or not isinstance(projection.get("factors_available"), bool)):
        return False
    return _evaluation_items_are_valid(projection)


def _tyr_evaluation_contract(value: object) -> bool:
    """Ensure invalid native validity does not become a score evaluation."""

    if not isinstance(value, dict) or value.get("native_validity") is not False:
        return False
    projection = _evaluation_projection(value)
    if projection is not None:
        if (projection.get("called") is True
                or projection.get("score_available") is True
                or projection.get("cross_projection_equal") is not True):
            return False
        if (projection.get("native_aggregate_score_available") is True
                or projection.get("costs_aggregate_score_available") is True):
            return False
    acceptance = value.get("acceptance")
    if isinstance(acceptance, dict):
        if acceptance.get("prediction_available") is True:
            return False
        native_total = acceptance.get("native_total")
        if native_total is not None:
            return False
    costs = value.get("costs")
    if isinstance(costs, dict):
        native_eval = costs.get("native_evaluation")
        if (isinstance(native_eval, dict)
                and native_eval.get("aggregate_score_available") is True):
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument(
        "--require-evaluation", action="store_true",
        help="require the optional native counterparty score/factor contract")
    args = parser.parse_args()
    installation = args.installation.resolve(strict=True)
    session = ObserverSession(installation, game_exe())
    artifact = _new_artifact(installation.parent, "peace-empty-offer-queries")
    report: dict = {
        "validator": Path(__file__).name,
        "artifact": str(artifact),
        "installation": str(installation),
        "status": "running",
        "action_id": "white_peace",
        "phase": "initiate",
        "cases": [
            {"name": name, "actor": actor, "recipient": recipient}
            for name, actor, recipient in CASES
        ],
        "expected_date_raw": args.expected_date_raw,
        "evaluation_required": args.require_evaluation,
        "execute_call_count": 0,
        "business_submission": False,
        "time_advance_call_count": 0,
        "save_call_count": 0,
        "discovery_call_count": 0,
        "selected_call_count": 0,
        "query_call_count": 0,
        "queries": {},
    }
    log = session.directory / "control-probe.jsonl"
    log_start: int | None = None
    try:
        health = wait_runtime_ready(session, restore_minimized=True)
        if health.get("status") != "ready":
            raise RuntimeError("PEACE_EMPTY_OFFER_QUERY_SESSION_UNREADY")
        report.update(_installation_binding(installation))
        report["session"] = {
            key: session.record.get(key)
            for key in ("pid", "session_id", "experiment_id", "dll_sha256")
        }
        before = _run_snapshots(session, artifact / "before" / "probes")
        control_before = _control_summary(before["control_state"]["snapshot"])
        report["before"] = {
            "control": control_before,
            "health": session.health(),
            "probes": _public_probe_records(before),
        }
        if (not _control_is_expected(control_before, args.expected_date_raw)
                or not _snapshots_complete(before)):
            raise RuntimeError("PEACE_EMPTY_OFFER_QUERY_BASELINE_UNAVAILABLE")
        log_start = log.stat().st_size

        discovery: dict[str, dict] = {}
        with DurableJournal(artifact / "diplomacy.sqlite3",
                            session.experiment_id, session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            # Complete all discoveries before selecting any war.  The repeated
            # FRA->ENG discovery is an explicit identity consistency check.
            for name, actor, recipient in CASES:
                report["discovery_call_count"] += 1
                report["query_call_count"] += 1
                result = api.inspect_diplomatic_action(
                    "white_peace", actor, recipient,
                    phase="initiate", parameters={})
                discovery[name] = result
                report["queries"][f"discovery_{name}"] = result
                _write_json(artifact / f"discovery-{name}.json", result)

            discovered_ids = {
                name: _single_discovered_war_id(
                    discovery[name], actor, recipient)
                for name, actor, recipient in CASES
            }
            report["discovery_war_ids"] = discovered_ids
            # A non-controlled reverse pair may be refused by the public
            # scope policy.  Keep that result as an explicit comparison and
            # continue the three usable selections; every other incomplete
            # discovery remains a failed contract check below.
            scope_refused = {
                name: _is_scope_refusal(discovery[name])
                for name, _, _ in CASES
            }
            scope_comparison = {
                name: (name == "eng_fra" and scope_refused[name])
                for name, _, _ in CASES
            }

            selected: dict[str, dict] = {}
            selected_parameters: dict[str, dict] = {}
            for name, actor, recipient in CASES:
                war_id = discovered_ids[name]
                if war_id is None:
                    continue
                parameters = {
                    "peace_context": {"war_id": war_id, "terms": []},
                }
                selected_parameters[name] = parameters
                report["selected_call_count"] += 1
                report["query_call_count"] += 1
                result = api.inspect_diplomatic_action(
                    "white_peace", actor, recipient,
                    phase="initiate", parameters=parameters)
                selected[name] = result
                report["queries"][f"selected_{name}"] = result
                _write_json(artifact / f"selected-{name}.json", result)

        after = _run_snapshots(session, artifact / "after" / "probes")
        control_after = _control_summary(after["control_state"]["snapshot"])
        health_after = session.health()
        report["discovery"] = discovery
        report["selected"] = selected
        report["selected_parameters"] = selected_parameters
        report["scope_refusals"] = scope_refused
        report["scope_refusal_comparison"] = scope_comparison
        report["before_after"] = {
            "control_before": control_before,
            "control_after": control_after,
            "war_countries_unchanged": (
                before["war_state"]["snapshot"].get("countries")
                == after["war_state"]["snapshot"].get("countries")),
        }
        report["after"] = {
            "control": control_after,
            "health": health_after,
            "probes": _public_probe_records(after),
        }
        discovery_ids = {
            name: _single_discovered_war_id(
                discovery[name], actor, recipient)
            for name, actor, recipient in CASES
        }
        selected_contracts = {
            name: _public_empty_offer_contract(
                selected.get(name), actor, recipient, discovery_ids[name])
            if discovery_ids[name] is not None else False
            for name, actor, recipient in CASES
        }
        evaluation_observations = {
            name: _evaluation_observation(selected.get(name))
            for name, _, _ in CASES
        }
        report["evaluation_observations"] = evaluation_observations
        report["checks"] = {
            "discovery_public_contracts": all(
                _public_context_contract(discovery[name], actor, recipient)
                or scope_comparison[name]
                for name, actor, recipient in CASES),
            "discovery_one_war_or_scope_refusal": all(
                discovery_ids[name] is not None or scope_comparison[name]
                for name, _, _ in CASES),
            "same_war_id_across_discoveries": (
                len(set(value for value in discovery_ids.values()
                        if value is not None)) == 1
                and any(value is not None for value in discovery_ids.values())),
            "eng_fra_scope_or_discovery_contract": (
                _public_context_contract(discovery["eng_fra"], "ENG", "FRA")
                or scope_comparison["eng_fra"]),
            "selected_public_contracts": all(
                (scope_comparison[name] and name not in selected)
                or selected_contracts[name]
                for name in selected_contracts),
            "selected_war_id_consistent": all(
                (scope_comparison[name] and name not in selected)
                or (isinstance(selected.get(name), dict)
                and selected[name].get("selected_war_id") == discovery_ids[name]
                and selected[name].get("peace_context", {}).get("war_id")
                    == discovery_ids[name])
                for name, _, _ in CASES),
            "three_native_gates_are_bool": all(
                (scope_comparison[name] and name not in selected)
                or all(isinstance(selected.get(name, {}).get(field), bool)
                    for field in ("native_validity", "common_action_gate",
                                  "initiation_gate"))
                for name, _, _ in CASES),
            "construction_participant_cleanup_verified": all(
                (scope_comparison[name] and name not in selected)
                or all(selected.get(name, {}).get(field) is True
                    for field in ("offer_constructed", "action_constructed",
                                  "participant_copy_verified", "cleanup_verified"))
                for name, _, _ in CASES),
            "no_private_identifiers": not _has_private_fields(
                {"discovery": discovery, "selected": selected}),
            "control_unchanged": control_before == control_after,
            "health_ready_after": health_after.get("status") == "ready",
            "four_snapshots_complete": (
                _snapshots_complete(before) and _snapshots_complete(after)),
            "independent_war_state_unchanged": (
                before["war_state"]["snapshot"].get("countries")
                == after["war_state"]["snapshot"].get("countries")),
            "no_business_submission": (
                report["execute_call_count"] == 0
                and report["business_submission"] is False
                and report["time_advance_call_count"] == 0
                and report["save_call_count"] == 0),
        }
        if args.require_evaluation:
            evaluation_checks = {
                "eng_fra_evaluation": _eng_evaluation_contract(
                    selected.get("fra_eng")),
                "eng_fra_repeat_evaluation": _eng_evaluation_contract(
                    selected.get("fra_eng_repeat")),
                "tyr_invalid_skips_evaluation": _tyr_evaluation_contract(
                    selected.get("fra_tyr")),
            }
            evaluation_checks["passed"] = all(evaluation_checks.values())
            report["evaluation_checks"] = evaluation_checks
            report["checks"]["evaluation_contract"] = evaluation_checks["passed"]
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if isinstance(log_start, int):
            report["native_events"] = _copy_log_slice(
                log, log_start, artifact / "native-events-slice.jsonl")
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
