#!/usr/bin/env python3
"""运行 R34 宿敌查询的只读、多目标验收。

脚本要求游戏已经运行并加载带观察 DLL 的安装记录。脚本只读取运行状态、
执行一组四快照和 ``set_rival``/``remove_rival`` 原生查询；不会发布外交执行
请求、推进日期、保存游戏、启动进程或安装 DLL。完整 UI 规则尚未恢复，
旧 schema1/2 的 ``full_rules_complete=false`` 仍表示查询不具备完整执行
证明。schema3 若同时给出 ``full_rules_complete=true`` 与
``native_action_available=true``，脚本会把该查询标记为可执行候选。需要
验证候选谓词时，可增加 ``--require-ui-candidates``；该选项接受
``rules_schema>=2`` 且明确调用候选检查的原生结果。

示例::

    python work/run_rival_queries.py \
        --installation work/runtime/r34-rival-build/installation.json \
        --expected-date-raw 56464872 \
        --recipient ENG --recipient BUR \
        --expected-rival ENG=active --expected-rival BUR=absent
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
from work.run_alliance_execution import (  # noqa: E402
    _copy_log_slice,
    _write_json,
)
from work.run_improve_relations_execution import _new_artifact  # noqa: E402
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
_FAMILY = "rival"
_ACTIONS = ("set_rival", "remove_rival")
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_NATIVE_QUERY_CAPABILITY = "native_rival_query"
_LOG_SLICE_MAX_BYTES = 8 * 1024 * 1024
_HEX_RE = re.compile(r"[0-9a-fA-F]*\Z")
_POINTER_KEY_TOKENS = ("pointer", "address", "vptr", "handle", "ptr")


class QueryValidationError(RuntimeError):
    """A bounded read-only query validation stop."""


def _parse_mapping(values: list[str] | None,
                   allowed: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise QueryValidationError(f"MAPPING_INVALID:{value}")
        tag, state = value.split("=", 1)
        if not _TAG_RE.fullmatch(tag) or state not in allowed:
            raise QueryValidationError(f"MAPPING_INVALID:{value}")
        if tag == _ACTOR:
            raise QueryValidationError("MAPPING_ACTOR_NOT_ALLOWED")
        if tag in result:
            raise QueryValidationError(f"MAPPING_DUPLICATE:{tag}")
        result[tag] = state
    return result


def _int_field(value: object, *, minimum: int | None = None) -> bool:
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    return minimum is None or value >= minimum


def _rival_candidate_shape(value: object,
                           *, require_ui_candidates: bool = False) -> dict[str, object]:
    """Validate schema 1/2/3 candidate fields without treating presence as true."""

    if not isinstance(value, dict):
        return {"complete": False, "rules_schema": None}
    raw_schema = value.get("rules_schema", 1)
    schema_valid = (isinstance(raw_schema, int) and not isinstance(raw_schema, bool)
                    and raw_schema in (1, 2, 3))
    schema = raw_schema if schema_valid else None
    available = value.get("candidate_eligibility_available")
    new_fields = {
        key: value.get(key)
        for key in ("candidate_eligible", "target_exists", "ui_war_allowed")
    }
    if schema == 1:
        # R34A may carry the old false marker, while older schema-1 output may
        # omit it.  Neither shape proves that the candidate method ran.
        fields_valid = (available is None or available is False)
        fields_valid = fields_valid and all(
            field is None or isinstance(field, bool) for field in new_fields.values())
    elif schema in (2, 3):
        fields_valid = (isinstance(available, bool)
                        and all(isinstance(field, bool) for field in new_fields.values()))
    else:
        fields_valid = False
    required_valid = (
        not require_ui_candidates
        or (schema is not None and schema >= 2 and available is True
            and all(isinstance(field, bool) for field in new_fields.values())))
    return {
        "complete": schema_valid and fields_valid and required_valid,
        "rules_schema": schema,
        "candidate_eligibility_available": available,
        "full_rules_complete": value.get("full_rules_complete"),
        "native_action_available": value.get("native_action_available"),
        **new_fields,
    }


def _query_rival_pair(api: DiplomacyTools, recipient: str,
                      destination: Path) -> dict[str, dict[str, object]]:
    """Query both Rival actions without creating an execution request."""

    result: dict[str, dict[str, object]] = {}
    for action_id in _ACTIONS:
        try:
            inspected = api.inspect_diplomatic_action(
                action_id, _ACTOR, recipient, phase="initiate", parameters={}
            )
            result[action_id] = inspected if isinstance(inspected, dict) else {
                "status": "unknown", "error": "INSPECTION_NOT_OBJECT",
            }
        except Exception as error:
            result[action_id] = {
                "status": "unknown",
                "error_type": type(error).__name__,
                "error": str(error),
            }
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json(destination, result)
    return result


def _pointer_keys(value: object, path: str = "") -> list[str]:
    """Find pointer-shaped public keys without inspecting native raw objects."""

    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if any(token in key_text.casefold() for token in _POINTER_KEY_TOKENS):
                found.append(child_path)
            found.extend(_pointer_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_pointer_keys(child, f"{path}[{index}]"))
    return found


def _rival_query_shape(query: object, action_id: str, recipient: str,
                       expected_date: int,
                       *, require_ui_candidates: bool = False) -> dict[str, object]:
    """Validate public Rival evidence while keeping UI completeness separate."""

    if not isinstance(query, dict):
        return {"complete": False, "action_id": action_id, "error": "QUERY_NOT_OBJECT"}
    session = query.get("session")
    support = query.get("interface_support")
    acceptance = query.get("acceptance")
    legality = query.get("legality")
    components = query.get("native_rule_components")
    relationship = query.get("relationship_state")
    candidate_shape = _rival_candidate_shape(
        query, require_ui_candidates=require_ui_candidates)
    component_shape = _rival_candidate_shape(
        components, require_ui_candidates=require_ui_candidates)
    active = query.get("rival_active")
    relationship_active = relationship.get("rival_active") if isinstance(relationship, dict) else None
    query_date = query.get("date_raw")
    session_date = session.get("date_raw") if isinstance(session, dict) else None
    pointers = _pointer_keys(query)

    # The public adapter keeps the query date in ``session.date_raw``.  The
    # top-level ``date_raw`` and ``event`` keys are not required by the
    # stable Rival public contract and are currently absent (the native
    # event slice below carries the independent event/date binding).  If a
    # producer emits either optional field, require the value to agree with
    # the native contract; otherwise validate the public family/action fields
    # and the session date only.
    public_event_compatible = (
        query.get("event") is None
        or query.get("event") == "native_rival_inspection"
    )
    public_date_compatible = (
        query_date is None
        or (_int_field(query_date) and query_date == expected_date)
    )
    rules_schema = candidate_shape.get("rules_schema")
    schema3 = rules_schema == 3
    full_rules_shape = (
        isinstance(query.get("full_rules_complete"), bool)
        and isinstance(query.get("native_action_available"), bool)
        if schema3 else query.get("full_rules_complete") is False)
    legality_shape = (
        isinstance(legality, dict)
        and legality.get("complete") is (
            query.get("native_action_available") is True)
        if schema3 and query.get("full_rules_complete") is True
        else isinstance(legality, dict)
        and legality.get("complete") is False)
    component_complete_shape = (
        components.get("complete") is True
        if schema3 and query.get("full_rules_complete") is True
        and query.get("native_action_available") is True
        else components.get("complete") is False)
    structural = (
        public_event_compatible
        and query.get("action_id") == action_id
        and query.get("family") == _FAMILY
        and query.get("actor") == _ACTOR
        and query.get("recipient") == recipient
        and query.get("phase") == "initiate"
        and public_date_compatible
        and isinstance(session, dict) and session.get("status") == "ready"
        and _int_field(session_date) and session_date == expected_date
        and isinstance(support, dict)
        and support.get("query") == "partial_native_rules"
        and query.get("native_command_validity_called") is True
        and isinstance(query.get("native_command_validity"), bool)
        and query.get("rival_state_verified") is True
        and isinstance(active, bool)
        and isinstance(relationship, dict)
        and relationship.get("complete") is True
        and relationship_active is active
        and _int_field(query.get("rival_count"), minimum=0)
        and _int_field(query.get("max_rivals"), minimum=0)
        and _int_field(query.get("diplomatic_power_raw"))
        and isinstance(query.get("at_war"), bool)
        and candidate_shape.get("complete") is True
        and full_rules_shape
        and query.get("submitted") is False
        and isinstance(acceptance, dict)
        and acceptance.get("applicability") == "not_applicable"
        and acceptance.get("prediction_available") is False
        and acceptance.get("complete") is True
        and isinstance(components, dict)
        and components.get("specific_validity_query_called") is True
        and components.get("rival_state_verified") is True
        and component_shape.get("complete") is True
        and components.get("full_rules_complete") == query.get("full_rules_complete")
        and component_complete_shape
        and legality_shape
        and not pointers
    )
    return {
        "complete": structural,
        "event": query.get("event"),
        "action_id": query.get("action_id"),
        "family": query.get("family"),
        "actor": query.get("actor"),
        "recipient": query.get("recipient"),
        "phase": query.get("phase"),
        "date_raw": query_date,
        "session_status": session.get("status") if isinstance(session, dict) else None,
        "session_date_raw": session_date,
        "interface_query": support.get("query") if isinstance(support, dict) else None,
        "legality_status": legality.get("status") if isinstance(legality, dict) else None,
        "legality_complete": legality.get("complete") if isinstance(legality, dict) else None,
        "native_command_validity_called": query.get("native_command_validity_called"),
        "native_command_validity": query.get("native_command_validity"),
        "rules_schema": candidate_shape.get("rules_schema"),
        "rival_state_verified": query.get("rival_state_verified"),
        "rival_active": active if isinstance(active, bool) else None,
        "relationship_state": relationship,
        "rival_since_date_raw": query.get("rival_since_date_raw"),
        "rival_count": query.get("rival_count"),
        "max_rivals": query.get("max_rivals"),
        "diplomatic_power_raw": query.get("diplomatic_power_raw"),
        "at_war": query.get("at_war"),
        "candidate_eligibility_available": query.get("candidate_eligibility_available"),
        "candidate_eligible": query.get("candidate_eligible"),
        "target_exists": query.get("target_exists"),
        "ui_war_allowed": query.get("ui_war_allowed"),
        "candidate_shape": candidate_shape,
        "component_candidate_shape": component_shape,
        "full_rules_complete": query.get("full_rules_complete"),
        "native_action_available": query.get("native_action_available"),
        "acceptance": acceptance,
        "native_rule_components": components,
        "submitted": query.get("submitted"),
        "pointer_keys": pointers,
    }


def _scan_native_events(path: Path, expected_date: int,
                        recipients: tuple[str, ...],
                        session_id: str,
                        *, require_ui_candidates: bool = False) -> dict[str, object]:
    """Read only the bounded copied JSONL slice and bind its Rival events."""

    expected = {(action, recipient) for recipient in recipients for action in _ACTIONS}
    matches: dict[tuple[str, str], list[dict[str, object]]] = {
        key: [] for key in expected
    }
    line_count = 0
    json_count = 0
    invalid_lines = 0
    oversized_lines = 0
    max_line_bytes = 256 * 1024
    with path.open("rb") as stream:
        for raw in stream:
            line_count += 1
            if len(raw) > max_line_bytes:
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
            if event.get("event") != "native_rival_inspection":
                continue
            key = (str(event.get("action_id")), str(event.get("recipient")))
            if key not in matches:
                continue
            candidate_shape = _rival_candidate_shape(
                event, require_ui_candidates=require_ui_candidates)
            schema = candidate_shape.get("rules_schema")
            full_shape = (
                isinstance(event.get("full_rules_complete"), bool)
                and isinstance(event.get("native_action_available"), bool)
                if schema == 3 else event.get("full_rules_complete") is False)
            required = (
                event.get("family") == _FAMILY
                and event.get("actor") == _ACTOR
                and event.get("phase") == "initiate"
                and event.get("date_raw") == expected_date
                and event.get("native_command_validity_called") is True
                and isinstance(event.get("native_command_validity"), bool)
                and event.get("rival_state_verified") is True
                and isinstance(event.get("rival_active"), bool)
                and _int_field(event.get("rival_count"), minimum=0)
                and _int_field(event.get("max_rivals"), minimum=0)
                and _int_field(event.get("diplomatic_power_raw"))
                and isinstance(event.get("at_war"), bool)
                and isinstance(event.get("native_diagnostic_hex"), str)
                and len(event["native_diagnostic_hex"]) <= 4096
                and len(event["native_diagnostic_hex"]) % 2 == 0
                and _HEX_RE.fullmatch(event["native_diagnostic_hex"]) is not None
                and isinstance(event.get("diagnostic_readable"), bool)
                and isinstance(event.get("diagnostic_truncated"), bool)
                and candidate_shape.get("complete") is True
                and full_shape
                and event.get("submitted") is False
                and isinstance(event.get("query_id"), str)
                and bool(event.get("query_id"))
                and event.get("session_id") == session_id
            )
            if required:
                matches[key].append(event)
    per_query = {
        f"{action}:{recipient}": {
            "count": len(events),
            "complete": len(events) == 1,
            "query_id": events[0].get("query_id") if len(events) == 1 else None,
            "active": events[0].get("rival_active") if len(events) == 1 else None,
            "native_command_validity": (
                events[0].get("native_command_validity") if len(events) == 1 else None),
            "rules_schema": events[0].get("rules_schema", 1) if len(events) == 1 else None,
            "candidate_eligibility_available": (
                events[0].get("candidate_eligibility_available") if len(events) == 1 else None),
            "candidate_eligible": (
                events[0].get("candidate_eligible") if len(events) == 1 else None),
            "target_exists": (
                events[0].get("target_exists") if len(events) == 1 else None),
            "ui_war_allowed": (
                events[0].get("ui_war_allowed") if len(events) == 1 else None),
            "full_rules_complete": (
                events[0].get("full_rules_complete") if len(events) == 1 else None),
            "native_action_available": (
                events[0].get("native_action_available") if len(events) == 1 else None),
        }
        for (action, recipient), events in sorted(matches.items())
    }
    return {
        "path": str(path),
        "line_count": line_count,
        "json_line_count": json_count,
        "invalid_line_count": invalid_lines,
        "oversized_line_count": oversized_lines,
        "expected_event_count": len(expected),
        "matched_event_count": sum(len(events) for events in matches.values()),
        "complete": all(len(events) == 1 for events in matches.values()),
        "queries": per_query,
    }


def _recipient_result(pair: dict[str, dict[str, object]], recipient: str,
                      expected_active: str | None,
                      expected_date: int,
                      *, require_ui_candidates: bool = False) -> dict[str, object]:
    summaries = {
        action: _rival_query_shape(
            pair.get(action), action, recipient, expected_date,
            require_ui_candidates=require_ui_candidates)
        for action in _ACTIONS
    }
    expected_value = expected_active == "active" if expected_active is not None else None
    expectation_checks = [
        summary.get("rival_active") is expected_value
        for summary in summaries.values()
    ] if expected_active is not None else []
    return {
        "queries": summaries,
        "all_query_shapes_complete": all(
            summary.get("complete") is True for summary in summaries.values()),
        "expected_rival": expected_active,
        "expected_rival_matches": all(expectation_checks) if expectation_checks else None,
        "rival_active_values": {
            action: summaries[action].get("rival_active") for action in _ACTIONS
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--recipient", action="append", required=True,
                        help="three-letter target; repeat for multiple Rival queries")
    parser.add_argument("--expected-rival", action="append",
                        metavar="TAG=active|absent")
    parser.add_argument("--require-ui-candidates", action="store_true",
                        help="要求 R34B schema=2 且原生候选方法明确返回字段")
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve()
    artifact = _new_artifact(installation.parent, "rival-queries")
    recipients = tuple(args.recipient)
    report: dict[str, object] = {
        "validator": "run_rival_queries.py",
        "version": 1,
        "status": "running",
        "mode": "read_only_native_rival_queries",
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
        "installation_requested": False,
        "business_submission": False,
        "require_ui_candidates": bool(args.require_ui_candidates),
        "checks": {},
    }
    log_path = installation.parent / "control-probe.jsonl"
    log_start_offset: int | None = None
    try:
        if not recipients or len(set(recipients)) != len(recipients):
            raise QueryValidationError("RECIPIENT_DUPLICATE_OR_EMPTY")
        if any(not _TAG_RE.fullmatch(tag) or tag == _ACTOR for tag in recipients):
            raise QueryValidationError("RECIPIENT_TAG_INVALID")
        expected_rivals = _parse_mapping(args.expected_rival, ("active", "absent"))
        if any(tag not in recipients for tag in expected_rivals):
            raise QueryValidationError("EXPECTED_RIVAL_RECIPIENT_NOT_QUERIED")
        report["expected_rival"] = expected_rivals

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
                if isinstance(diplomat_snapshot, dict) else None
            )
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
        if _NATIVE_QUERY_CAPABILITY not in capabilities:
            raise QueryValidationError("NATIVE_RIVAL_QUERY_CAPABILITY_MISSING")

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
                query_results[recipient] = _query_rival_pair(
                    api, recipient, artifact / "queries" / f"{recipient}.json")
        _write_json(artifact / "queries.json", query_results)
        report["queries"] = query_results

        recipient_results = {
            recipient: _recipient_result(
                query_results[recipient], recipient,
                expected_rivals.get(recipient), args.expected_date_raw,
                require_ui_candidates=args.require_ui_candidates)
            for recipient in recipients
        }
        report["recipient_results"] = recipient_results

        report["checks"] = {
            "new_process_ready": baseline_checks["health_ready"],
            "player_por": baseline_checks["player_por"],
            "paused": baseline_checks["paused"],
            "date_matches_expected": baseline_checks["date_matches_expected"],
            "four_snapshots_complete": baseline_checks["four_snapshots_complete"],
            "native_rival_query_acknowledged": _NATIVE_QUERY_CAPABILITY in capabilities,
            "all_native_rival_queries_complete": all(
                result["all_query_shapes_complete"] is True
                for result in recipient_results.values()),
            "expected_rival_matches": all(
                result["expected_rival_matches"] is not False
                for result in recipient_results.values()),
            "no_execution_request_published": (
                report["execute_call_count"] == 0
                and report["execution_requested"] is False
                and report["business_submission"] is False
            ),
            "no_advance_save_or_install": (
                report["advance_requested"] is False
                and report["save_requested"] is False
                and report["installation_requested"] is False
            ),
            "source_build_session_bound": (
                isinstance(report.get("build_binding"), dict)
                and report["build_binding"].get(
                    "installation_matches_build_manifest") is True
                and report["build_binding"].get("installation_dll_sha256")
                == report["build_binding"].get("build_manifest_dll_sha256")
                and report.get("session", {}).get("dll_sha256")
                == report["build_binding"].get("installation_dll_sha256")
            ),
            "public_results_do_not_expose_pointers": all(
                not result["queries"][action].get("pointer_keys")
                for result in recipient_results.values()
                for action in _ACTIONS
            ),
            "acceptance_not_applicable": all(
                all(
                    result["queries"][action].get("acceptance", {}).get(
                        "applicability") == "not_applicable"
                    and result["queries"][action].get("acceptance", {}).get(
                        "prediction_available") is False
                    for action in _ACTIONS
                )
                for result in recipient_results.values()
            ),
            "full_rules_schema_consistent": all(
                (isinstance(result["queries"][action].get("full_rules_complete"), bool)
                 and isinstance(result["queries"][action].get("native_action_available"), bool))
                if result["queries"][action].get("rules_schema") == 3 else
                (result["queries"][action].get("full_rules_complete") is False
                 and result["queries"][action].get("native_rule_components", {}).get(
                     "complete") is False)
                for result in recipient_results.values()
                for action in _ACTIONS
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
                    report["native_event_summary"] = _scan_native_events(
                        native_slice_path, args.expected_date_raw,
                        recipients, str(report.get("session", {}).get("session_id", "")),
                        require_ui_candidates=args.require_ui_candidates)
                except (OSError, UnicodeError, ValueError) as error:
                    report["native_event_summary"] = {
                        "complete": False,
                        "error": {"type": type(error).__name__, "message": str(error)},
                    }
                report.setdefault("checks", {})["native_event_slice_complete"] = (
                    report.get("native_event_summary", {}).get("complete") is True)
            else:
                report.setdefault("checks", {})["native_event_slice_complete"] = False
        else:
            report.setdefault("checks", {})["native_event_slice_complete"] = False
        if report.get("status") == "passed" and not all(report.get("checks", {}).values()):
            report["status"] = "failed"
        _write_json(artifact / "report.json", report)

    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
