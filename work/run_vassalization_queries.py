#!/usr/bin/env python3
"""Run bounded, read-only native Vassalization inspections.

The operator inspects ``offer_vassalization`` and ``cancel_vassalization``
for each repeated recipient.  The native result decides whether the current
target is available; this script records that result and never assumes that
an Offer is legal or that the target will accept it.  Cancel is a one-sided
action, so its public acceptance block must explicitly be
``not_applicable``.

The game must already be running with the requested observer installation.
This script performs one readiness check and the standard four bounded
snapshots, publishes only read-only query requests, and copies a bounded
native JSONL slice for independent request/date/family validation.  It never
executes an action, advances the date, saves, restarts, or installs anything.

Example::

    python work/run_vassalization_queries.py \
        --installation work/runtime/r35-vassal-build/installation.json \
        --expected-date-raw 56500000 \
        --recipient PRO --recipient SAV --recipient ORL --recipient AMG \
        --recipient POR \
        --expected-vassal SAV=absent
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
from work.run_improve_relations_execution import (  # noqa: E402
    _new_artifact,
    _query_improve_pair,
)
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _diplomat_semantics,
    _run_snapshots,
)


_ACTOR = "FRA"
_PLAYER_SLOT = 189  # POR in the controlled experiment
_FAMILY = "vassalization"
_ACTIONS = ("offer_vassalization", "cancel_vassalization")
_QUERY_CAPABILITY = "native_vassalization_query"
_DEFAULT_RECIPIENTS = ("PRO", "SAV", "ORL", "AMG", "POR")
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_HEX_RE = re.compile(r"[0-9a-fA-F]*\Z")
_MAX_LOG_SLICE_BYTES = 8 * 1024 * 1024
_MAX_EVENT_LINE_BYTES = 256 * 1024


class QueryValidationError(RuntimeError):
    """A bounded read-only operator validation stop."""


def _parse_mapping(values: list[str] | None,
                   allowed: tuple[str, ...], recipients: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise QueryValidationError(f"MAPPING_INVALID:{value}")
        tag, state = value.split("=", 1)
        if (not _TAG_RE.fullmatch(tag) or tag == _ACTOR
                or tag not in recipients or state not in allowed):
            raise QueryValidationError(f"MAPPING_INVALID:{value}")
        if tag in result:
            raise QueryValidationError(f"MAPPING_DUPLICATE:{tag}")
        result[tag] = state
    return result


def _query_vassalization_pair(api: DiplomacyTools, recipient: str,
                              destination: Path) -> dict[str, dict[str, object]]:
    """Query both Vassalization variants with empty parameters."""

    result = _query_improve_pair(api, recipient, destination, _ACTIONS)
    # The shared helper writes the pair itself.  Keeping this wrapper local
    # makes the action family explicit at the call site and prevents an
    # accidental execution helper from being imported into this operator.
    return result


def _is_bool(value: object) -> bool:
    return type(value) is bool


def _component_shape(value: object) -> dict[str, object]:
    """Validate the stable public native-rule component shape.

    ``executor_validity`` and the gates can be ``None`` when the adapter has
    not obtained a component, but the component record itself must preserve
    the booleans that say which checks were called.  This keeps an unavailable
    target distinct from a malformed or missing native response.
    """

    if not isinstance(value, dict):
        return {"complete": False, "present": False, "errors": ["NOT_OBJECT"]}
    errors: list[str] = []
    for field in ("ui_enabled_gate_verified", "specific_validity_query_called"):
        if not _is_bool(value.get(field)):
            errors.append(f"{field}:BOOL_REQUIRED")
    for field in ("ui_action_selection", "common_action_gate", "initiation_gate",
                  "executor_validity", "tooltip_gate"):
        if field in value and value[field] is not None and not _is_bool(value[field]):
            errors.append(f"{field}:BOOL_OR_NULL_REQUIRED")
    if not _is_bool(value.get("complete")):
        errors.append("complete:BOOL_REQUIRED")
    return {
        "complete": not errors and value.get("complete") is True,
        "present": True,
        "errors": errors,
        "value": value,
    }


def _relationship_shape(query: object) -> dict[str, object]:
    relationship = query.get("relationship_state") if isinstance(query, dict) else None
    active = query.get("vassal_active") if isinstance(query, dict) else None
    verified = query.get("vassal_state_verified") if isinstance(query, dict) else None
    relation_active = relationship.get("vassal_active") \
        if isinstance(relationship, dict) else None
    relation_complete = relationship.get("complete") is True \
        if isinstance(relationship, dict) else False
    complete = (
        _is_bool(active)
        and verified is True
        and isinstance(relationship, dict)
        and relation_active is active
        and relation_complete
    )
    return {
        "vassal_active": active if _is_bool(active) else None,
        "vassal_state_verified": verified if _is_bool(verified) else None,
        "relationship_state": relationship,
        "complete": complete,
        "source": "relationship_state",
    }


def _acceptance_shape(query: object, action_id: str) -> dict[str, object]:
    acceptance = query.get("acceptance") if isinstance(query, dict) else None
    if not isinstance(acceptance, dict):
        return {"complete": False, "applicability": None, "errors": ["NOT_OBJECT"]}
    errors: list[str] = []
    if action_id == "cancel_vassalization":
        expected = {
            "applicability": "not_applicable",
            "prediction_available": False,
            "predicted_response": "not_applicable",
            "complete": True,
        }
        for field, value in expected.items():
            if acceptance.get(field) != value:
                errors.append(f"{field}:EXPECTED_{value}")
    else:
        if acceptance.get("applicability") != "applicable":
            errors.append("applicability:APPLICABLE_REQUIRED")
        if not _is_bool(acceptance.get("prediction_available")):
            errors.append("prediction_available:BOOL_REQUIRED")
        predicted = acceptance.get("predicted_response")
        if predicted not in ("accept", "reject", "unknown"):
            errors.append("predicted_response:KNOWN_STATE_REQUIRED")
        if acceptance.get("prediction_available") is True \
                and predicted not in ("accept", "reject"):
            errors.append("predicted_response:PREDICTION_MUST_BE_DECIDED")
        if not _is_bool(acceptance.get("complete")):
            errors.append("complete:BOOL_REQUIRED")
    return {
        "complete": not errors,
        "applicability": acceptance.get("applicability"),
        "prediction_available": acceptance.get("prediction_available"),
        "predicted_response": acceptance.get("predicted_response"),
        "errors": errors,
        "value": acceptance,
    }


def _query_shape(query: object, action_id: str, recipient: str,
                 expected_date: int) -> dict[str, object]:
    """Validate one stable public result without assuming Offer legality."""

    if not isinstance(query, dict):
        return {
            "complete": False,
            "action_id": action_id,
            "family": None,
            "actor": None,
            "recipient": recipient,
            "phase": None,
            "errors": ["QUERY_NOT_OBJECT"],
        }
    session = query.get("session")
    visibility = query.get("visibility")
    legality = query.get("legality")
    components = query.get("native_rule_components")
    relation = _relationship_shape(query)
    acceptance = _acceptance_shape(query, action_id)
    component = _component_shape(components)
    errors: list[str] = []
    if query.get("action_id") != action_id:
        errors.append("action_id:MISMATCH")
    if query.get("family") != _FAMILY:
        errors.append("family:MISMATCH")
    if query.get("actor") != _ACTOR:
        errors.append("actor:MISMATCH")
    if query.get("recipient") != recipient:
        errors.append("recipient:MISMATCH")
    if query.get("phase") != "initiate":
        errors.append("phase:MISMATCH")
    if not isinstance(session, dict) or session.get("status") != "ready":
        errors.append("session:NOT_READY")
    session_date = session.get("date_raw") if isinstance(session, dict) else None
    if not isinstance(session_date, int) or isinstance(session_date, bool) \
            or session_date != expected_date:
        errors.append("session.date_raw:MISMATCH")
    public_date = query.get("date_raw")
    if public_date is not None and (
            not isinstance(public_date, int) or isinstance(public_date, bool)
            or public_date != expected_date):
        errors.append("date_raw:MISMATCH")
    if not isinstance(visibility, dict) \
            or visibility.get("status") not in ("visible", "hidden") \
            or visibility.get("complete") is not True:
        errors.append("visibility:INCOMPLETE")
    if not isinstance(legality, dict) \
            or legality.get("status") not in ("available", "unavailable") \
            or legality.get("complete") is not True:
        errors.append("legality:INCOMPLETE_OR_UNKNOWN")
    if not component.get("complete"):
        errors.append("native_rule_components:INCOMPLETE")
    if not relation.get("complete"):
        errors.append("relationship_state:INCOMPLETE")
    if not acceptance.get("complete"):
        errors.extend(f"acceptance:{item}" for item in acceptance.get("errors", []))
    for field in ("actor_is_overlord", "actor_is_subject"):
        if field in query and not _is_bool(query.get(field)):
            errors.append(f"{field}:BOOL_REQUIRED")
    subject_type = query.get("subject_type")
    if subject_type is not None and (
            not isinstance(subject_type, str) or not subject_type or len(subject_type) > 64):
        errors.append("subject_type:BOUNDED_STRING_REQUIRED")
    submitted = query.get("submitted")
    if submitted is not None and submitted is not False:
        errors.append("submitted:MUST_BE_FALSE")
    return {
        "complete": not errors,
        "action_id": query.get("action_id"),
        "family": query.get("family"),
        "actor": query.get("actor"),
        "recipient": query.get("recipient"),
        "phase": query.get("phase"),
        "session_status": session.get("status") if isinstance(session, dict) else None,
        "session_date_raw": session_date,
        "date_raw": public_date,
        "visibility": visibility,
        "legality": legality,
        "native_rule_components": components,
        "component_shape": component,
        "relationship": relation,
        "acceptance": acceptance,
        "actor_is_overlord": query.get("actor_is_overlord"),
        "actor_is_subject": query.get("actor_is_subject"),
        "subject_type": subject_type,
        "errors": errors,
    }


def _native_event_shape(event: object, action_id: str, recipient: str,
                        expected_date: int, session_id: str) -> tuple[bool, list[str]]:
    if not isinstance(event, dict):
        return False, ["EVENT_NOT_OBJECT"]
    errors: list[str] = []
    exact = {
        "event": "native_alliance_inspection",
        "action_id": action_id,
        "family": _FAMILY,
        "actor": _ACTOR,
        "recipient": recipient,
        "phase": "initiate",
        "date_raw": expected_date,
        "session_id": session_id,
    }
    for field, expected in exact.items():
        if event.get(field) != expected:
            errors.append(f"{field}:MISMATCH")
    if not isinstance(event.get("query_id"), str) or not event.get("query_id"):
        errors.append("query_id:REQUIRED")
    for field in (
            "ui_selection_checked", "native_visibility", "ui_enabled_gate_checked",
            "initiation_gate", "tooltip_gate", "validity_called", "native_validity",
            "full_rules_complete", "submitted", "vassal_active",
            "vassal_state_verified"):
        if not _is_bool(event.get(field)):
            errors.append(f"{field}:BOOL_REQUIRED")
    common_gate = event.get("common_action_gate", event.get("display_predicate"))
    if not _is_bool(common_gate):
        errors.append("common_action_gate:BOOL_REQUIRED")
    for field in ("actor_is_overlord", "actor_is_subject"):
        if field in event and not _is_bool(event.get(field)):
            errors.append(f"{field}:BOOL_REQUIRED")
    subject_type = event.get("subject_type")
    if subject_type is not None and (
            not isinstance(subject_type, str) or not subject_type or len(subject_type) > 64):
        errors.append("subject_type:BOUNDED_STRING_REQUIRED")
    if event.get("vassal_state_verified") is not True:
        errors.append("vassal_state_verified:TRUE_REQUIRED")
    for field in ("diagnostic_readable", "diagnostic_truncated"):
        if not _is_bool(event.get(field)):
            errors.append(f"{field}:BOOL_REQUIRED")
    diagnostic = event.get("native_diagnostic_hex")
    if (not isinstance(diagnostic, str) or len(diagnostic) > 4096
            or len(diagnostic) % 2 or _HEX_RE.fullmatch(diagnostic) is None):
        errors.append("native_diagnostic_hex:BOUNDED_HEX_REQUIRED")
    if event.get("submitted") is not False:
        errors.append("submitted:MUST_BE_FALSE")
    for field in ("score_applicable", "score_available", "acceptance_predicate_available"):
        if field in event and not _is_bool(event.get(field)):
            errors.append(f"{field}:BOOL_OR_MISSING_REQUIRED")
    if action_id == "cancel_vassalization":
        for field in ("score_applicable", "score_available", "acceptance_predicate_available"):
            if event.get(field) is not False:
                errors.append(f"{field}:CANCEL_MUST_BE_FALSE")
    reason_count = event.get("reason_count")
    if reason_count is not None and (
            not isinstance(reason_count, int) or isinstance(reason_count, bool)
            or not 0 <= reason_count <= 4096):
        errors.append("reason_count:BOUNDED_INT_REQUIRED")
    return not errors, errors


def _scan_native_events(path: Path, expected_date: int,
                        recipients: tuple[str, ...], session_id: str) -> dict[str, object]:
    """Validate only the copied bounded JSONL suffix, never the live log."""

    expected = {(action, recipient) for recipient in recipients for action in _ACTIONS}
    matches: dict[tuple[str, str], list[dict[str, object]]] = {
        key: [] for key in expected
    }
    line_count = json_count = invalid_lines = oversized_lines = 0
    with path.open("rb") as stream:
        for raw in stream:
            line_count += 1
            if len(raw) > _MAX_EVENT_LINE_BYTES:
                oversized_lines += 1
                continue
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                invalid_lines += 1
                continue
            if not isinstance(event, dict):
                continue
            json_count += 1
            if event.get("event") != "native_alliance_inspection":
                continue
            key = (str(event.get("action_id")), str(event.get("recipient")))
            if key not in matches:
                continue
            valid, errors = _native_event_shape(
                event, key[0], key[1], expected_date, session_id)
            if valid:
                matches[key].append(event)
            else:
                # Keep malformed matching events visible for diagnosis while
                # ensuring that they cannot make the source check pass.
                matches[key].append({"_invalid": errors, **event})
    queries: dict[str, dict[str, object]] = {}
    for action, recipient in sorted(expected):
        events = matches[(action, recipient)]
        valid_events = [event for event in events if "_invalid" not in event]
        queries[f"{action}:{recipient}"] = {
            "count": len(events),
            "valid_count": len(valid_events),
            "complete": len(valid_events) == 1 and len(events) == 1,
            "query_id": valid_events[0].get("query_id") if len(valid_events) == 1 else None,
            "vassal_active": valid_events[0].get("vassal_active") if len(valid_events) == 1 else None,
            "invalid_reasons": events[0].get("_invalid") if len(events) == 1
                and "_invalid" in events[0] else [],
        }
    return {
        "path": str(path),
        "line_count": line_count,
        "json_line_count": json_count,
        "invalid_line_count": invalid_lines,
        "oversized_line_count": oversized_lines,
        "expected_event_count": len(expected),
        "matched_event_count": sum(len(events) for events in matches.values()),
        "complete": all(item["complete"] for item in queries.values()),
        "queries": queries,
    }


def _relation_matches_native(recipient_results: dict[str, object],
                             native_summary: dict[str, object]) -> bool:
    queries = native_summary.get("queries") if isinstance(native_summary, dict) else None
    if not isinstance(queries, dict):
        return False
    for recipient, result in recipient_results.items():
        if not isinstance(result, dict):
            return False
        for action in _ACTIONS:
            key = f"{action}:{recipient}"
            native = queries.get(key)
            public = result.get(action)
            if not isinstance(native, dict) or not isinstance(public, dict):
                return False
            if native.get("complete") is not True \
                    or native.get("vassal_active") is not public.get("relationship", {}).get(
                        "vassal_active"):
                return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument(
        "--recipient", action="append",
        help="三字母目标国家；可重复，省略时使用 PRO,SAV,ORL,AMG,POR",
    )
    parser.add_argument(
        "--expected-vassal", action="append", metavar="TAG=active|absent",
        help="可选的关系状态断言；没有断言的目标只记录原生结果",
    )
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve()
    recipients = tuple(args.recipient or _DEFAULT_RECIPIENTS)
    artifact = _new_artifact(installation.parent, "vassalization-queries")
    report: dict[str, object] = {
        "validator": "run_vassalization_queries.py",
        "version": 1,
        "status": "running",
        "mode": "read_only_native_vassalization_queries",
        "installation": str(installation),
        "actor": _ACTOR,
        "recipients": list(recipients),
        "actions": list(_ACTIONS),
        "family": _FAMILY,
        "expected_date_raw": args.expected_date_raw,
        "artifact": str(artifact),
        "execute_call_count": 0,
        "execution_requested": False,
        "advance_requested": False,
        "save_requested": False,
        "restart_requested": False,
        "installation_requested": False,
        "business_submission": False,
        "checks": {},
    }
    log_path = installation.parent / "control-probe.jsonl"
    log_start_offset: int | None = None
    try:
        if not recipients or len(set(recipients)) != len(recipients):
            raise QueryValidationError("RECIPIENT_DUPLICATE_OR_EMPTY")
        if any(not _TAG_RE.fullmatch(tag) or tag == _ACTOR for tag in recipients):
            raise QueryValidationError("RECIPIENT_TAG_INVALID")
        expected_vassal = _parse_mapping(
            args.expected_vassal, ("active", "absent"), recipients)
        report["expected_vassal"] = expected_vassal

        installation_binding = _installation_binding(installation)
        report.update(installation_binding)
        executable = game_exe().expanduser().resolve(strict=True)
        report["source"] = {
            "game_executable": str(executable),
            "bytes": executable.stat().st_size,
            "source_binding": "local_config.game_exe",
        }
        session = ObserverSession(installation, executable)
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        if isinstance(report.get("build_binding"), dict):
            report["build_binding"]["loaded_dll_sha256"] = session.record.get("dll_sha256")

        health = wait_runtime_ready(session, restore_minimized=False)
        if health.get("status") != "ready":
            raise QueryValidationError("SESSION_NOT_READY")
        capabilities = sorted(session.installation_capabilities())
        report["capabilities"] = capabilities

        probes = _run_snapshots(session, artifact / "probes")
        control_snapshot = probes.get("control_state", {}).get("snapshot")
        control = _control_summary(control_snapshot) if isinstance(control_snapshot, dict) else {}
        diplomat_snapshot = probes.get("diplomats", {}).get("snapshot")
        try:
            diplomat_semantics = (
                _diplomat_semantics(diplomat_snapshot)
                if isinstance(diplomat_snapshot, dict) else None)
            diplomat_error = None
        except Exception as error:
            diplomat_semantics = None
            diplomat_error = {"type": type(error).__name__, "message": str(error)}
        report["probes"] = {
            name: {
                "status": item.get("status"),
                "snapshot_path": item.get("snapshot_path"),
                "snapshot_completeness": item.get("snapshot_completeness"),
                "snapshot_sha256": item.get("snapshot_sha256"),
            }
            for name, item in probes.items()
        }
        report["control"] = control
        report["diplomat_semantics"] = diplomat_semantics
        report["diplomat_semantics_error"] = diplomat_error
        report["four_snapshot_boundary"] = "before_queries"

        baseline_checks = {
            "health_ready": health.get("status") == "ready"
            and health.get("complete") is True,
            "player_por": control.get("player_slot") == _PLAYER_SLOT,
            "paused": control.get("paused_flag") == 1,
            "date_matches_expected": (
                control.get("date_raw") == args.expected_date_raw
                and health.get("date_raw") == args.expected_date_raw
            ),
            "four_snapshots_complete": _snapshots_complete(probes),
        }
        report["baseline_checks"] = baseline_checks
        if not all(baseline_checks.values()):
            raise QueryValidationError("BASELINE_NOT_READY_POR_PAUSED")
        if _QUERY_CAPABILITY not in capabilities:
            raise QueryValidationError("NATIVE_VASSALIZATION_QUERY_CAPABILITY_MISSING")

        try:
            log_start_offset = log_path.stat().st_size
        except OSError as error:
            raise QueryValidationError(f"NATIVE_LOG_UNAVAILABLE:{error}") from error
        report["log_start_offset"] = log_start_offset

        query_results: dict[str, dict[str, dict[str, object]]] = {}
        with DurableJournal(
            artifact / "diplomacy.sqlite3", session.experiment_id,
            session.session_id, global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            for recipient in recipients:
                query_results[recipient] = _query_vassalization_pair(
                    api, recipient, artifact / "queries" / f"{recipient}.json")
        _write_json(artifact / "queries.json", query_results)
        report["queries"] = query_results

        recipient_results: dict[str, dict[str, object]] = {}
        for recipient in recipients:
            pair = query_results[recipient]
            offer = _query_shape(
                pair.get(_ACTIONS[0]), _ACTIONS[0], recipient, args.expected_date_raw)
            cancel = _query_shape(
                pair.get(_ACTIONS[1]), _ACTIONS[1], recipient, args.expected_date_raw)
            observed = offer["relationship"].get("vassal_active") \
                if isinstance(offer.get("relationship"), dict) else None
            cancel_observed = cancel["relationship"].get("vassal_active") \
                if isinstance(cancel.get("relationship"), dict) else None
            expected = expected_vassal.get(recipient)
            recipient_results[recipient] = {
                "offer_vassalization": offer,
                "cancel_vassalization": cancel,
                "vassal_active": observed if observed is cancel_observed else None,
                "expected_vassal": expected,
                "expected_vassal_matches": (
                    observed is (expected == "active")
                    and cancel_observed is (expected == "active")
                    if expected is not None else None
                ),
            }
        report["recipient_results"] = recipient_results
        report["checks"] = {
            "new_process_ready": baseline_checks["health_ready"],
            "player_por": baseline_checks["player_por"],
            "paused": baseline_checks["paused"],
            "date_matches_expected": baseline_checks["date_matches_expected"],
            "four_snapshots_complete": baseline_checks["four_snapshots_complete"],
            "native_vassalization_query_acknowledged": _QUERY_CAPABILITY in capabilities,
            "all_public_queries_complete": all(
                result[action]["complete"]
                for result in recipient_results.values() for action in _ACTIONS),
            "all_relationship_states_complete_and_consistent": all(
                result[action]["relationship"].get("complete") is True
                for result in recipient_results.values() for action in _ACTIONS
            ) and all(
                result["vassal_active"] is not None
                for result in recipient_results.values()),
            "cancel_acceptance_not_applicable": all(
                result[_ACTIONS[1]]["acceptance"].get("applicability") == "not_applicable"
                and result[_ACTIONS[1]]["acceptance"].get("prediction_available") is False
                and result[_ACTIONS[1]]["acceptance"].get("predicted_response") == "not_applicable"
                for result in recipient_results.values()),
            "expected_vassal_matches": all(
                result["expected_vassal_matches"] is not False
                for result in recipient_results.values()),
            "no_execution_request_published": (
                report["execute_call_count"] == 0
                and report["execution_requested"] is False
                and report["business_submission"] is False
            ),
            "no_advance_save_restart_or_install": (
                report["advance_requested"] is False
                and report["save_requested"] is False
                and report["restart_requested"] is False
                and report["installation_requested"] is False
            ),
            "source_build_session_bound": (
                isinstance(report.get("build_binding"), dict)
                and report["build_binding"].get("installation_matches_build_manifest") is True
                and report["build_binding"].get("installation_dll_sha256")
                == report["build_binding"].get("build_manifest_dll_sha256")
                and report.get("session", {}).get("dll_sha256")
                == report["build_binding"].get("installation_dll_sha256")
            ),
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except QueryValidationError as error:
        report["status"] = "failed"
        report["error"] = {"code": str(error)}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_OPERATOR_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if log_start_offset is not None:
            native_slice_path = artifact / "native-events-slice.jsonl"
            report["native_events"] = _copy_log_slice(
                log_path, log_start_offset, native_slice_path)
            if report["native_events"].get("status") == "ok":
                try:
                    native_summary = _scan_native_events(
                        native_slice_path, args.expected_date_raw, recipients,
                        str(report.get("session", {}).get("session_id", "")))
                except (OSError, UnicodeError, ValueError) as error:
                    native_summary = {
                        "complete": False,
                        "error": {"type": type(error).__name__, "message": str(error)},
                    }
                report["native_event_summary"] = native_summary
                report.setdefault("checks", {})["native_event_slice_complete"] = (
                    native_summary.get("complete") is True)
                report.setdefault("checks", {})["public_native_relation_binding"] = (
                    _relation_matches_native(
                        report.get("recipient_results", {}), native_summary)
                    if native_summary.get("complete") is True else False)
            else:
                report.setdefault("checks", {})["native_event_slice_complete"] = False
                report.setdefault("checks", {})["public_native_relation_binding"] = False
        else:
            report.setdefault("checks", {})["native_event_slice_complete"] = False
            report.setdefault("checks", {})["public_native_relation_binding"] = False
        if report.get("status") == "passed" and not all(report.get("checks", {}).values()):
            report["status"] = "failed"
        _write_json(artifact / "report.json", report)

    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
