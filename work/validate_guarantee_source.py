#!/usr/bin/env python3
"""Validate one Guarantee execution through the observed native source chain.

The transport, load, clone, pointer and authority checks are supplied by the
existing bounded Improve validator.  This wrapper configures that common
validator for the Guarantee family and adds the relation result contract:
``native_diplomacy_relation_execution_result`` with ``native_state=0``,
variant 1/0, and a verified ``guarantee_before``/``guarantee_after`` change.
The event slice and report are streamed or bounded at 10 MiB.  The source
artifact is never rewritten and the validator never starts the game.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import uuid
from typing import Any


WORK_DIR = Path(__file__).resolve().parent
if str(WORK_DIR) not in sys.path:
    sys.path.insert(0, str(WORK_DIR))

import validate_improve_relations_source as common  # noqa: E402
from validate_alliance_authority_source import as_int, same_int  # noqa: E402


MAX_INPUT_BYTES = 10 * 1024 * 1024
START_ACTION = "proclaim_guarantee"
STOP_ACTION = "revoke_guarantee"
SUPPORTED_ACTIONS = frozenset((START_ACTION, STOP_ACTION))
FAMILY = "guarantee"
ACTOR = "FRA"
RECIPIENT = "SAV"
PHASE = "initiate"
SELECTOR = 0x2941
SELECTOR_INPUT_HEX = "7b006172616e746565616374696f6e00"
VTABLE_RVA = 0x1C7FE50
EXPECTED_VARIANT_BY_ACTION = {START_ACTION: 1, STOP_ACTION: 0}
RESULT_EVENT = "native_diplomacy_relation_execution_result"
PAYLOAD_EVENTS = (
    "native_alliance_command_entry_observed",
    "native_alliance_wrapper_clone",
    "native_alliance_transport_completed",
    "native_alliance_submission_result",
    RESULT_EVENT,
    "native_alliance_lifecycle",
    "native_wrapper_field_read_begin",
)
PAYLOAD_EVENT_SET = frozenset(PAYLOAD_EVENTS)

# The common validator keeps stable implementation-oriented check names for
# Improve Relations.  This adapter publishes a Guarantee-specific vocabulary
# so a standalone report cannot be mistaken for a task-family report.
CHECK_RENAMES = {
    "report_identity_improve_relations_fra_sav": "guarantee_report_identity_fra_sav",
    "report_event_slice_metadata_matches_stream": "guarantee_report_event_slice_metadata_matches_stream",
    "report_and_event_inputs_within_bound": "guarantee_report_and_event_inputs_within_bound",
    "source_report_action_is_supported": "guarantee_source_report_action_supported",
    "single_execute_call": "guarantee_single_execute_call",
    "event_jsonl_complete": "guarantee_event_jsonl_complete",
    "session_bound_chain": "guarantee_session_bound_chain",
    "one_matching_command_entry": "guarantee_one_matching_command_entry",
    "one_matching_wrapper_clone": "guarantee_one_matching_wrapper_clone",
    "one_matching_transport": "guarantee_one_matching_transport",
    "one_matching_submission": "guarantee_one_matching_submission",
    "one_matching_task_result": "guarantee_one_matching_relation_result_event",
    "payload_family_extra60_state_variant_consistent": "guarantee_payload_family_extra60_state_variant_consistent",
    "request_semantic_key_bound_through_chain": "guarantee_request_semantic_key_bound_through_chain",
    "protocol_sequence_bound_to_request": "guarantee_protocol_sequence_bound_to_request",
    "pointer_chain_source_clone_transport_target_entry": "guarantee_pointer_chain_source_clone_transport_target_entry",
    "transport_world_identity_bound": "guarantee_transport_world_identity_bound",
    "transport_load_contract": "guarantee_transport_load_contract",
    "callback_order_transport_load_clone_entry": "guarantee_callback_order_transport_load_clone_entry",
    "native_submission_and_task_result_verified": "guarantee_submission_and_relation_result_verified",
    "public_result_matches_native_result": "guarantee_public_result_matches_relation_result",
    "positive_validation_passed": "guarantee_positive_validation_passed",
    "source_report_family_guarantee": "guarantee_source_report_family",
    "source_report_selector_guarantee": "guarantee_source_report_selector",
    "native_selector_field_read": "guarantee_native_selector_field_read",
    "one_matching_relation_result": "guarantee_one_matching_relation_result",
    "relation_result_event_and_family": "guarantee_relation_result_event_and_family",
    "relation_result_request_binding": "guarantee_relation_result_request_binding",
    "relation_result_state_variant": "guarantee_relation_result_state_variant",
    "relation_result_transition": "guarantee_relation_result_transition",
    "relation_result_verified": "guarantee_relation_result_verified",
    "single_sided_no_accept_reject": "guarantee_single_sided_no_accept_reject",
    "submission_receipt_bound": "guarantee_submission_receipt_bound",
    "public_result_matches_native_relation": "guarantee_public_result_matches_native_relation",
    "one_matching_authority_entry": "guarantee_one_matching_authority_entry",
    "pre_entry_full_payload_strict": "guarantee_pre_entry_full_payload_strict",
    "pre_entry_envoy_sentinel_or_existing_id": "guarantee_pre_entry_envoy_sentinel_or_existing_id",
    "post_entry_envoy_native_id": "guarantee_post_entry_envoy_native_id",
    "post_entry_payload_core_preserved": "guarantee_post_entry_payload_core_preserved",
    "one_unauthorized_dispatch": "guarantee_one_unauthorized_dispatch",
    "dispatch_route_is_direct_or_transport": "guarantee_dispatch_route_is_direct_or_transport",
    "dispatcher_acceptance_matches_route": "guarantee_dispatcher_acceptance_matches_route",
    "no_authority_seed": "guarantee_no_authority_seed",
    "one_rejection": "guarantee_one_rejection",
    "rejection_not_submitted": "guarantee_rejection_not_submitted",
    "no_authorized_submission": "guarantee_no_authorized_submission",
    "no_relation_result": "guarantee_no_relation_result",
    "rejection_reason_is_unauthorized_guarantee": "guarantee_rejection_reason_unauthorized",
    "negative_validation_passed": "guarantee_negative_validation_passed",
}


def _guarantee_checks(checks: dict[str, Any]) -> dict[str, Any]:
    """Rename shared checks while preserving values and insertion order."""

    return {CHECK_RENAMES.get(name, name): value for name, value in checks.items()}


def _check_summary(checks: dict[str, Any]) -> dict[str, Any]:
    failed = [name for name, value in checks.items() if value is False]
    return {
        "total": len(checks),
        "passed": len(checks) - len(failed),
        "failed": failed,
    }


def _configure_common() -> None:
    """Configure the imported common validator in this process only."""

    common.START_ACTION = START_ACTION
    common.STOP_ACTION = STOP_ACTION
    common.SUPPORTED_ACTIONS = SUPPORTED_ACTIONS
    common.FAMILY = FAMILY
    common.ACTOR = ACTOR
    common.RECIPIENT = RECIPIENT
    common.PHASE = PHASE
    common.EXPECTED_VARIANT = 1
    common.EXPECTED_STATE = 0
    common.EXPECTED_EXTRA60 = 0
    common.EXPECTED_DISCRIMINATOR = 357
    common.EXPECTED_VTABLE_RVA = VTABLE_RVA
    common.RESULT_EVENT = RESULT_EVENT
    common.RESULT_BEFORE_FIELD = "guarantee_before"
    common.RESULT_AFTER_FIELD = "guarantee_after"
    common.SKIP_STATE_OBSERVATION = True
    common.INTERESTING_EVENTS = PAYLOAD_EVENTS
    common.INTERESTING_SET = PAYLOAD_EVENT_SET


def _event_path(artifact: Path) -> Path:
    for name in ("native-events-slice.jsonl", "native-events.jsonl"):
        path = artifact / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"no native event JSONL under {artifact}")


def _record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "size_bytes": path.stat().st_size,
            "sha256": digest.hexdigest()}


def _bounded_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"refusing to parse input over 10 MiB: {path}")
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _extra_events(path: Path, names: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Read selected lifecycle/negative events without retaining other lines."""

    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"refusing to scan event file over 10 MiB: {path}")
    result: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            try:
                value = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and value.get("event") in names:
                item = dict(value)
                item["_line"] = line_number
                result[str(value["event"])].append(item)
    return dict(result)


def _session(report: dict[str, Any]) -> str:
    return common._session_id(report)


def _payload(shape: Any) -> dict[str, Any]:
    return common._payload(shape)


def _action_variant(action: str) -> int | None:
    return EXPECTED_VARIANT_BY_ACTION.get(action)


def _core_payload_equal(left: Any, right: Any, expected_variant: int) -> bool:
    """Compare payloads while allowing the post-entry envoy assignment."""

    left_payload = _payload(left)
    right_payload = _payload(right)
    if not (common._payload_valid(left, expected_variant)
            and common._payload_valid(right, expected_variant)):
        return False
    if (left_payload.get("family") != FAMILY
            or right_payload.get("family") != FAMILY
            or not same_int(left_payload.get("extra60"), 0)
            or not same_int(right_payload.get("extra60"), 0)):
        return False
    return all(
        same_int(left_payload.get(field), right_payload.get(field))
        for field in common.PAYLOAD_FIELDS if field != "envoy30"
    )


def _result_checks(report: dict[str, Any], event_data: dict[str, Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    action = str(report.get("action_id", ""))
    expected_variant = _action_variant(action)
    session = _session(report)
    request_id = str(report.get("request_id", ""))
    actor = str(report.get("actor", ""))
    recipient = str(report.get("recipient", ""))
    date_raw = as_int(report.get("expected_date_raw"))
    candidates = common._session_events(event_data, RESULT_EVENT, session)
    matches = [value for value in candidates if (
        value.get("request_id") == request_id
        and value.get("action_id") == action
        and value.get("actor") == actor == ACTOR
        and value.get("recipient") == recipient == RECIPIENT
        and value.get("phase") == PHASE
        and same_int(value.get("date_raw"), date_raw)
        and value.get("family") == FAMILY
    )]
    result = matches[0] if len(matches) == 1 else {}
    before = result.get("guarantee_before")
    after = result.get("guarantee_after")
    expected_transition = (
        before is False and after is True
        if action == START_ACTION
        else before is True and after is False
        if action == STOP_ACTION
        else False
    )
    submission_candidates = common._session_events(
        event_data, "native_alliance_submission_result", session)
    submissions = [value for value in submission_candidates if (
        value.get("request_id") == request_id
        and value.get("action_id") == action
        and value.get("actor") == actor == ACTOR
        and value.get("recipient") == recipient == RECIPIENT
        and value.get("phase") == PHASE
        and same_int(value.get("date_raw"), date_raw)
    )]
    submission = submissions[0] if len(submissions) == 1 else {}
    selector_reads = [value for value in common._session_events(
        event_data, "native_wrapper_field_read_begin", session
    ) if same_int(value.get("field_id"), SELECTOR)]
    selector_matches = [value for value in selector_reads if (
        str(value.get("input16_hex", "")).lower() == SELECTOR_INPUT_HEX
    )]
    execution = report.get("execution")
    execution_result = execution.get("result") if isinstance(execution, dict) else None
    poll = report.get("poll")
    poll_final = poll.get("final") if isinstance(poll, dict) else None
    poll_result = poll_final.get("result") if isinstance(poll_final, dict) else None
    public_result_ok = (
        isinstance(execution_result, dict)
        and isinstance(poll_result, dict)
        and execution_result == poll_result
        and execution_result.get("event") == RESULT_EVENT
        and execution_result.get("family") == FAMILY
        and execution_result.get("action_id") == action
        and execution_result.get("phase") == PHASE
        and execution_result.get("request_id") == request_id
        and same_int(execution_result.get("date_raw"), date_raw)
        and execution_result.get("guarantee_before") is before
        and execution_result.get("guarantee_after") is after
    )
    no_accept_reject = all(
        field not in result for field in
        ("accepted", "rejected", "accept", "reject", "response")
    ) and result.get("outcome") not in ("accepted", "rejected")
    checks = {
        "source_report_family_guarantee": report.get("family") == FAMILY,
        # Execution artifacts from the current adapter do not serialize the
        # UI selector in report.json.  If a producer includes it, verify the
        # exact native selector; otherwise retain the omission as an explicit
        # observation while the action/family/event bindings below provide the
        # execution identity.
        "source_report_selector_guarantee": (
            report.get("selector") is None
            or same_int(report.get("selector"), SELECTOR)
        ),
        "native_selector_field_read": len(selector_matches) == 1,
        "one_matching_relation_result": len(matches) == 1,
        "relation_result_event_and_family": result.get("event") == RESULT_EVENT
        and result.get("family") == FAMILY,
        "relation_result_request_binding": (
            result.get("request_id") == request_id
            and result.get("session_id") == session
            and result.get("action_id") == action
            and result.get("actor") == ACTOR
            and result.get("recipient") == RECIPIENT
            and result.get("phase") == PHASE
            and same_int(result.get("date_raw"), date_raw)
        ),
        "relation_result_state_variant": (
            same_int(result.get("native_state"), 0)
            and same_int(result.get("native_variant"), expected_variant)
        ),
        "relation_result_transition": expected_transition,
        "relation_result_verified": (
            result.get("execution_verified") is True
            and result.get("request_binding_verified") is True
        ),
        "single_sided_no_accept_reject": no_accept_reject,
        "submission_receipt_bound": (
            len(submissions) == 1
            and submission.get("submitted") is True
            and submission.get("native_queue_verified") is True
        ),
        "public_result_matches_native_relation": public_result_ok,
    }
    detail = {
        "event_line": result.get("_line"),
        "submission_line": submission.get("_line"),
        "request_id": request_id,
        "session_id": session,
        "action_id": action,
        "family": result.get("family"),
        "native_state": result.get("native_state"),
        "native_variant": result.get("native_variant"),
        "guarantee_before": before,
        "guarantee_after": after,
        "outcome": result.get("outcome"),
        "execution_verified": result.get("execution_verified"),
        "request_binding_verified": result.get("request_binding_verified"),
        "accepted_or_rejected_fields": {
            field: result.get(field) for field in
            ("accepted", "rejected", "accept", "reject", "response")
            if field in result
        },
        "selector_field_read_line": (
            selector_matches[0].get("_line") if len(selector_matches) == 1 else None
        ),
        "selector_field_id": (
            selector_matches[0].get("field_id") if len(selector_matches) == 1 else None
        ),
    }
    return checks, detail


def _entry_envoy_checks(
        report: dict[str, Any], event_data: dict[str, Any], extra: dict[str, list[dict[str, Any]]]
        ) -> tuple[dict[str, bool], dict[str, Any]]:
    """Check strict pre-entry payload and the bounded post-entry envoy write."""

    action = str(report.get("action_id", ""))
    expected_variant = _action_variant(action)
    session = _session(report)
    entries = [value for value in common._session_events(
        event_data, "native_alliance_command_entry_observed", session)
                if value.get("action_id") == action
                and value.get("actor_field") == ACTOR
                and value.get("recipient_field") == RECIPIENT]
    entry = entries[0] if len(entries) == 1 else {}
    entry_source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    entry_payload = _payload(entry_source)
    entry_line = as_int(entry.get("_line"))
    entry_sequence = as_int(entry.get("callback_sequence"))
    lifecycle = []
    for value in extra.get("native_alliance_lifecycle", []):
        if str(value.get("session_id", "")) != session:
            continue
        source = value.get("source")
        payload = _payload(source)
        if (common._payload_valid(source, expected_variant)
                and payload.get("family") == FAMILY
                and same_int(payload.get("extra60"), 0)
                and entry_line is not None
                and as_int(value.get("_line")) is not None
                and as_int(value.get("_line")) > entry_line
                and (entry_sequence is None
                     or as_int(value.get("sequence")) is None
                     or as_int(value.get("sequence")) > entry_sequence)):
            lifecycle.append(value)
    mutations = [value for value in lifecycle if (
        _core_payload_equal(value.get("source"), entry_source, expected_variant)
        and as_int(_payload(value.get("source")).get("envoy30")) is not None
        and as_int(_payload(value.get("source")).get("envoy30")) >= 0
        and not same_int(_payload(value.get("source")).get("envoy30"),
                         entry_payload.get("envoy30"))
    )]
    pre_envoy = as_int(entry_payload.get("envoy30"))
    post_envoys = [as_int(_payload(value.get("source")).get("envoy30")) for value in mutations]
    strict_pre_entry = (
        len(entries) == 1
        and common._payload_valid(entry_source, expected_variant)
        and entry_payload.get("family") == FAMILY
        and same_int(entry_payload.get("extra60"), 0)
        and same_int(entry_payload.get("state34"), 0)
        and same_int(entry_payload.get("variant38"), expected_variant)
        and _payload(entry_source).get("envoy30") is not None
    )
    # The native creator uses -1 as the pre-entry sentinel for a new
    # Guarantee. Revoke may carry an existing relation slot, so it is checked
    # for a valid integer and the post-entry mutation remains observational.
    sentinel_check = pre_envoy == -1 if action == START_ACTION else pre_envoy is not None
    mutation_check = bool(mutations) and all(value is not None for value in post_envoys)
    checks = {
        "one_matching_authority_entry": len(entries) == 1,
        "pre_entry_full_payload_strict": strict_pre_entry,
        "pre_entry_envoy_sentinel_or_existing_id": sentinel_check,
        "post_entry_envoy_native_id": mutation_check if action == START_ACTION else (
            mutation_check or pre_envoy is not None),
        "post_entry_payload_core_preserved": (
            bool(mutations) and all(
                _core_payload_equal(value.get("source"), entry_source, expected_variant)
                for value in mutations
            )
        ) if mutations else action == STOP_ACTION,
    }
    detail = {
        "entry_line": entry.get("_line"),
        "entry_callback_sequence": entry.get("callback_sequence"),
        "pre_entry_envoy30": entry_payload.get("envoy30"),
        "post_entry_envoy30": post_envoys,
        "lifecycle_lines": [value.get("_line") for value in mutations],
        "lifecycle_sequences": [value.get("sequence") for value in mutations],
        "interpretation": (
            "proclaim pre-entry envoy30=-1 and post-entry native id observed"
            if action == START_ACTION else
            "revoke preserves an existing relation envoy slot when present"
        ),
    }
    return checks, detail


def _negative_validation(artifact: Path) -> dict[str, Any]:
    report = _bounded_json(artifact / "report.json")
    event_path = _event_path(artifact)
    event_data = common._stream_events(event_path)
    extra = _extra_events(event_path, {
        "native_alliance_authority_test_dispatched",
        "native_alliance_execution_rejected",
    })
    session = _session(report)
    action = str(report.get("action_id", ""))
    expected_variant = _action_variant(action)
    dispatches = [value for value in extra.get("native_alliance_authority_test_dispatched", [])
                  if str(value.get("session_id", "")) == session]
    rejections = [value for value in extra.get("native_alliance_execution_rejected", [])
                  if str(value.get("session_id", "")) == session]
    submissions = common._session_events(event_data, "native_alliance_submission_result", session)
    results = common._session_events(event_data, RESULT_EVENT, session)
    dispatch = dispatches[0] if len(dispatches) == 1 else {}
    rejection = rejections[0] if len(rejections) == 1 else {}
    route = dispatch.get("dispatch_route")
    route_ok = route in ("direct_entry", "transport", "direct", "transport_callback")
    dispatcher_expected = (
        dispatch.get("dispatcher_accepted") is False
        if route in ("direct_entry", "direct")
        else dispatch.get("dispatcher_accepted") is True
        if route in ("transport", "transport_callback")
        else False
    )
    checks = {
        "one_unauthorized_dispatch": len(dispatches) == 1,
        "dispatch_route_is_direct_or_transport": route_ok,
        "dispatcher_acceptance_matches_route": dispatcher_expected,
        "no_authority_seed": dispatch.get("authority_seed_created") is False,
        "guarantee_packet_identity": (
            dispatch.get("action_id") == action
            and action in SUPPORTED_ACTIONS
            and dispatch.get("actor") == ACTOR
            and dispatch.get("recipient") == RECIPIENT
            and dispatch.get("phase") == PHASE
            and same_int(dispatch.get("variant38"), expected_variant)
            and same_int(dispatch.get("state34"), 0)
        ),
        "one_rejection": len(rejections) == 1,
        "rejection_reason_is_unauthorized_guarantee": (
            rejection.get("reason") == "UNAUTHORIZED_FRA_GUARANTEE"
        ),
        "rejection_not_submitted": rejection.get("submitted") is False,
        "no_authorized_submission": len(submissions) == 0,
        "no_relation_result": len(results) == 0,
    }
    checks = _guarantee_checks(checks)
    checks["guarantee_negative_validation_passed"] = all(checks.values())
    return {
        "status": "passed" if checks["guarantee_negative_validation_passed"] else "failed",
        "artifact": _record(artifact / "report.json"),
        "event_file": _record(event_path),
        "session_id": session,
        "action_id": action,
        "checks": checks,
        "check_summary": _check_summary(checks),
        "dispatch": {
            "line": dispatch.get("_line"),
            "action_id": dispatch.get("action_id"),
            "recipient": dispatch.get("recipient"),
            "variant38": dispatch.get("variant38"),
            "state34": dispatch.get("state34"),
            "dispatch_route": route,
            "dispatcher_accepted": dispatch.get("dispatcher_accepted"),
            "authority_seed_created": dispatch.get("authority_seed_created"),
        },
        "rejection": {
            "line": rejection.get("_line"),
            "reason": rejection.get("reason"),
            "submitted": rejection.get("submitted"),
        },
    }


def build_report(artifact: Path, negative_artifacts: list[Path] | None = None) -> dict[str, Any]:
    _configure_common()
    artifact = artifact.resolve(strict=True)
    if not artifact.is_dir():
        raise ValueError(f"artifact is not a directory: {artifact}")
    source_report = _bounded_json(artifact / "report.json")
    event_path = _event_path(artifact)
    # The common validator reads the same bounded report and event window; it
    # is intentionally reused rather than duplicated here.
    result = common.build_report(artifact)
    event_data = common._stream_events(event_path)
    relation_checks, relation_detail = _result_checks(source_report, event_data)
    extra = _extra_events(event_path, {"native_alliance_lifecycle"})
    envoy_checks, envoy_detail = _entry_envoy_checks(source_report, event_data, extra)
    checks = _guarantee_checks(result.setdefault("checks", {}))
    checks.update(relation_checks)
    checks.update(envoy_checks)
    checks = _guarantee_checks(checks)
    checks["guarantee_positive_validation_passed"] = all(checks.values())
    result["checks"] = checks
    result["check_summary"] = _check_summary(checks)
    result["status"] = "passed" if checks["guarantee_positive_validation_passed"] else "failed"
    result["validation_passed"] = checks["guarantee_positive_validation_passed"]
    result["validator"] = "work/validate_guarantee_source.py"
    result["guarantee_relation"] = relation_detail
    result["post_entry_envoy"] = envoy_detail
    result["selector"] = SELECTOR
    result["selector_observation"] = (
        source_report.get("selector")
        if source_report.get("selector") is not None
        else "not_recorded_in_report"
    )
    result["vtable_rva"] = hex(VTABLE_RVA)
    result["family"] = FAMILY
    if negative_artifacts:
        negatives = [_negative_validation(path.resolve(strict=True)) for path in negative_artifacts]
        result["negatives"] = negatives
        result["status"] = (
            "passed"
            if result["status"] == "passed" and all(item["status"] == "passed" for item in negatives)
            else "failed"
        )
        result["validation_passed"] = result["status"] == "passed"
    return result


def _failed(checks: dict[str, Any]) -> list[str]:
    return [name for name, value in checks.items() if value is False]


def markdown_report(value: dict[str, Any]) -> str:
    relation = value.get("guarantee_relation", {})
    envoy = value.get("post_entry_envoy", {})
    summary = value.get("check_summary", {})
    lines = [
        "# Guarantee 原生来源核验",
        "",
        f"结论：{value.get('status', 'failed').upper()}。",
        "",
        "核验对象：proclaim_guarantee 或 revoke_guarantee，FRA→SAV，"
        "family=guarantee；查询和执行均为单方关系，不产生 accept/reject 响应。",
        f"request_id：{relation.get('request_id')}；native_state={relation.get('native_state')}；"
        f"variant={relation.get('native_variant')}；"
        f"guarantee_before={relation.get('guarantee_before')} → "
        f"guarantee_after={relation.get('guarantee_after')}。",
        "",
        "## 来源链",
        "",
        "报告检查 normal creator、wrapper clone、transport send/load、clone、"
        "authority entry、submission receipt 和 native relation result 的唯一绑定；"
        "入口前 payload 的 family、extra60、state、variant、双方和日期必须完全一致。",
        f"入口前 envoy30：{envoy.get('pre_entry_envoy30')}；"
        f"入口后观察到的 envoy30：{envoy.get('post_entry_envoy30')}。",
        "",
        "## 检查结果",
        "",
        f"正向检查：{summary.get('passed', 0)}/{summary.get('total', 0)} 通过。",
        f"失败检查：{', '.join(_failed(value.get('checks', {}))) or '无'}。",
    ]
    for index, negative in enumerate(value.get("negatives", []), 1):
        lines.extend([
            "",
            f"## 未授权负例 {index}",
            "",
            f"结论：{negative.get('status')}；"
            f"route={negative.get('dispatch', {}).get('dispatch_route')}；"
            f"reason={negative.get('rejection', {}).get('reason')}；"
            f"检查：{negative.get('check_summary', {}).get('passed', 0)}/"
            f"{negative.get('check_summary', {}).get('total', 0)} 通过；"
            f"失败检查：{', '.join(_failed(negative.get('checks', {}))) or '无'}。",
        ])
    event_log = value.get("event_log", {})
    lines.extend([
        "",
        "## 输入绑定",
        "",
        f"报告：{value.get('artifact')}；事件文件：{event_log.get('path')}；"
        f"事件 SHA-256：{event_log.get('sha256')}。",
        "程序以有界流式方式读取输入，未覆盖源 artifact。",
    ])
    return "\n".join(lines) + "\n"


def _fresh_output_dir(artifact: Path) -> Path:
    return artifact.parent / f"guarantee-source-validation-{uuid.uuid4().hex}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--negative-artifact", action="append", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    artifact = args.artifact.resolve(strict=True)
    negatives = [path.resolve(strict=True) for path in (args.negative_artifact or [])]
    output_dir = args.output_dir.resolve() if args.output_dir else _fresh_output_dir(artifact)
    output_dir.mkdir(parents=True, exist_ok=False)
    value = build_report(artifact, negatives)
    (output_dir / "validation.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(markdown_report(value), encoding="utf-8")
    print(json.dumps({
        "status": value["status"],
        "output_dir": str(output_dir),
        "validation": str(output_dir / "validation.json"),
        "report": str(output_dir / "report.md"),
    }, ensure_ascii=False))
    return 0 if value["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
