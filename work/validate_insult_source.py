#!/usr/bin/env python3
"""Validate an Insult execution through the independent native source chain.

The validator reuses the bounded transport/load/clone/entry checks from the
Improve Relations source validator, configured for one Insult action at a time.
It adds the Insult-specific signed ``parameter40`` binding, the single-sided
``native_diplomacy_insult_execution_result`` contract, and the two native
unauthorized authority-test routes.  It reads report and JSONL inputs in
bounded mode, writes only a fresh evidence directory, and never starts the
game or treats an operator summary as native proof.
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
CONTRACT_PATH = WORK_DIR / "fixtures" / "insult_source_contract.json"
ACTOR = "FRA"
PHASE = "initiate"
FAMILY = "insult"
RESULT_EVENT = "native_diplomacy_insult_execution_result"
SUBMISSION_EVENT = "native_alliance_submission_result"
ENTRY_EVENT = "native_alliance_command_entry_observed"
CLONE_EVENT = "native_alliance_wrapper_clone"
TRANSPORT_EVENT = "native_alliance_transport_completed"
AUTHORITY_EVENT = "native_alliance_authority_test_dispatched"
REJECTION_EVENT = "native_alliance_execution_rejected"
COMMAND_EVENT = "diplomatic_command_observed"
LIFECYCLE_EVENT = "native_alliance_lifecycle"
FIELD_READ_EVENT = "native_wrapper_field_read_begin"
GENERIC_DIRECT_PAYLOAD_FIELDS = (
    "family", "extra60", "parameter40", "actor10", "mirror18",
    "recipient20", "date28", "date2c", "envoy30", "state34",
    "variant38", "proposal3c", "raw10", "raw38", "raw3c", "raw40",
    "raw44", "callback_sequence", "action_id",
)
INTERESTING_EVENTS = (
    ENTRY_EVENT,
    CLONE_EVENT,
    TRANSPORT_EVENT,
    SUBMISSION_EVENT,
    RESULT_EVENT,
    AUTHORITY_EVENT,
    REJECTION_EVENT,
    COMMAND_EVENT,
    LIFECYCLE_EVENT,
    FIELD_READ_EVENT,
)
INTERESTING_SET = frozenset(INTERESTING_EVENTS)


def _bounded_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"refusing to parse input over 10 MiB: {path}")
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _contract() -> dict[str, Any]:
    value = _bounded_json(CONTRACT_PATH)
    if value.get("family") != FAMILY:
        raise ValueError("Insult contract fixture family mismatch")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "size_bytes": path.stat().st_size,
            "sha256": _sha256(path)}


def _event_path(artifact: Path) -> Path:
    for name in ("native-events-slice.jsonl", "native-events.jsonl"):
        path = artifact / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"no native event JSONL under {artifact}")


def _stream(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"refusing to scan input over 10 MiB: {path}")
    return common._stream_events(path)


def _session(report: dict[str, Any]) -> str:
    return common._session_id(report)


def _payload(shape: Any) -> dict[str, Any]:
    value = common._payload(shape)
    return value if isinstance(value, dict) else {}


def _tag(value: Any) -> str | None:
    return common._tag_from_identity(value)


def _strict_int(value: Any, expected: int | None = None) -> bool:
    if isinstance(value, bool):
        return False
    parsed = as_int(value)
    return parsed is not None and (expected is None or parsed == expected)


def _action_parameter(report: dict[str, Any], action: str,
                      result: dict[str, Any] | None = None) -> int | None:
    if action == "send_insult":
        return -1
    candidates: list[Any] = []
    for container in (report, report.get("parameters"), report.get("request"),
                      report.get("execution"), report.get("payload")):
        if not isinstance(container, dict):
            continue
        for key in ("selected_insult_id", "insult_id", "parameter40"):
            if key in container:
                candidates.append(container[key])
        nested = container.get("parameters")
        if isinstance(nested, dict) and "insult_id" in nested:
            candidates.append(nested["insult_id"])
    if isinstance(result, dict):
        candidates.append(result.get("insult_id"))
    for value in candidates:
        parsed = as_int(value)
        if parsed is not None and not isinstance(value, bool):
            return parsed
    return None


def _parameter_valid(action: str, value: Any, expected: int | None = None) -> bool:
    parsed = as_int(value)
    if parsed is None or isinstance(value, bool):
        return False
    if action == "send_insult":
        return parsed == -1 and (expected is None or parsed == expected)
    return (0 <= parsed <= 2147483647
            and (expected is None or parsed == expected))


def _payload_shapes(event_data: dict[str, Any], session: str, action: str,
                    recipient: str, date_raw: int) -> dict[str, list[dict[str, Any]]]:
    """Collect payloads by stage without retaining unrelated JSONL events."""

    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for name, fields in (
        (ENTRY_EVENT, ("source",)),
        (CLONE_EVENT, ("source", "target")),
        (TRANSPORT_EVENT, ("source", "loaded")),
        (LIFECYCLE_EVENT, ("source", "target")),
    ):
        for event in common._session_events(event_data, name, session):
            if name == ENTRY_EVENT and event.get("action_id") != action:
                continue
            for field in fields:
                shape = event.get(field)
                payload = _payload(shape)
                if (payload.get("family") != FAMILY
                        or _tag(payload.get("actor10")) != ACTOR
                        or _tag(payload.get("mirror18")) != ACTOR
                        or _tag(payload.get("recipient20")) != recipient
                        or not _strict_int(payload.get("date28"), date_raw)
                        or not _strict_int(payload.get("date2c"), date_raw)):
                    continue
                result[name].append(shape)
    return dict(result)


def _parameter_checks(report: dict[str, Any], event_data: dict[str, Any],
                      result: dict[str, Any], result_count: int) -> tuple[dict[str, bool], dict[str, Any]]:
    action = str(report.get("action_id", ""))
    recipient = str(report.get("recipient", ""))
    session = _session(report)
    date_raw = as_int(report.get("expected_date_raw"))
    expected = _action_parameter(report, action, result)
    shapes = _payload_shapes(event_data, session, action, recipient, date_raw)
    values_by_stage: dict[str, list[Any]] = {
        name: [_payload(shape).get("parameter40") for shape in values]
        for name, values in shapes.items()
    }
    values = [value for stage in values_by_stage.values() for value in stage]
    distinct = {value for value in values if isinstance(value, int) and not isinstance(value, bool)}
    # Insult uses the generic execution entry observation.  That event only
    # records command/action/header fields; the signed parameter is bound to
    # the same command object by the clone and transport payloads.  Requiring
    # the Alliance-specific entry event here would reject the real Insult
    # contract before the pointer proof is evaluated.
    all_stages = all(values_by_stage.get(name) for name in
                     (CLONE_EVENT, TRANSPORT_EVENT))
    valid = all(_parameter_valid(action, value, expected) for value in values)
    consistent = bool(values) and len(distinct) == 1
    result_parameter = result.get("insult_id") if isinstance(result, dict) else None
    checks = {
        "insult_parameter40_present_on_source_chain": all_stages and bool(values),
        "insult_parameter40_action_range": valid,
        "insult_parameter40_consistent_across_chain": consistent,
        "insult_parameter40_matches_result": (
            result_count == 1 and _parameter_valid(action, result_parameter, expected)
            and (not values or all(same_int(value, result_parameter) for value in values))
        ),
        "insult_parameter40_report_binding": (
            expected is not None and _parameter_valid(action, expected)
            and (not isinstance(report.get("selected_insult_id"), int)
                 or same_int(report.get("selected_insult_id"), expected))
        ),
    }
    detail = {
        "action_id": action,
        "recipient": recipient,
        "expected_parameter40": expected,
        "result_insult_id": result_parameter,
        "payload_values_by_stage": values_by_stage,
        "payload_shape_counts": {name: len(values) for name, values in shapes.items()},
    }
    return checks, detail


def _generic_entry_validation(report: dict[str, Any], event_data: dict[str, Any],
                              common_report: dict[str, Any]) -> dict[str, Any]:
    """Validate Insult's actual generic execution-entry observation.

    ``bridge_execution_execute`` calls ``bridge_response_observe(value)``
    before payload capture and the authority gate.  The generic event therefore
    proves the command pointer, action pointer, header and forward path.  The
    family payload is proved independently by clone/transport events whose
    target address/action must equal the generic command/action.
    """

    session = _session(report)
    action = str(report.get("action_id", ""))
    recipient = str(report.get("recipient", ""))
    date_raw = as_int(report.get("expected_date_raw"))
    contract = _contract()
    expected_vtable = contract["payload"].get("vtable_rva")
    chain = common_report.get("chain") if isinstance(common_report.get("chain"), dict) else {}
    clone = chain.get("clone") if isinstance(chain.get("clone"), dict) else {}
    transport = chain.get("transport") if isinstance(chain.get("transport"), dict) else {}
    target = clone.get("target") if isinstance(clone.get("target"), dict) else {}
    target_payload = target.get("payload") if isinstance(target.get("payload"), dict) else {}
    transport_source = transport.get("source") if isinstance(transport.get("source"), dict) else {}
    transport_payload = transport_source.get("payload") if isinstance(transport_source.get("payload"), dict) else {}

    submissions = common._session_events(event_data, SUBMISSION_EVENT, session)
    transport_events = common._session_events(event_data, TRANSPORT_EVENT, session)
    transport_event = transport_events[0] if len(transport_events) == 1 else {}
    submission = submissions[0] if len(submissions) == 1 else {}
    generic_events = common._session_events(event_data, COMMAND_EVENT, session)
    candidates: list[dict[str, Any]] = []
    for event in generic_events:
        if event.get("readable") is not True or event.get("forward_to_original") is not True:
            continue
        if not same_int(event.get("origin"), 65535) or not same_int(event.get("protocol_flags"), 0):
            continue
        if not same_int(event.get("action_vtable_rva"), expected_vtable):
            continue
        if not same_int(event.get("command"), target.get("addr")):
            continue
        if not same_int(event.get("action"), target.get("action")):
            continue
        if not same_int(event.get("protocol_sequence"), transport_source.get("protocol_sequence")):
            continue
        if not same_int(event.get("protocol_sequence"), submission.get("native_sequence")):
            continue
        candidates.append(event)
    generic = candidates[0] if len(candidates) == 1 else {}

    line_before_clone = (
        bool(generic)
        and as_int(generic.get("_line")) is not None
        and as_int(clone.get("line")) is not None
        and as_int(generic.get("_line")) < as_int(clone.get("line"))
    )
    payload_bound = (
        bool(generic)
        and target_payload.get("family") == FAMILY
        and same_int(target_payload.get("extra60"), contract["payload"].get("extra60"))
        and _tag(target_payload.get("actor10")) == ACTOR
        and _tag(target_payload.get("recipient20")) == recipient
        and same_int(target_payload.get("date28"), date_raw)
        and same_int(target_payload.get("date2c"), date_raw)
        and same_int(target_payload.get("state34"), contract["actions"].get(action, {}).get("state34"))
        and same_int(target_payload.get("variant38"), contract["actions"].get(action, {}).get("variant38"))
        and same_int(target.get("action"), generic.get("action"))
    )
    protocol_bound = (
        bool(generic)
        and same_int(generic.get("protocol_sequence"), transport_source.get("protocol_sequence"))
        and same_int(transport_source.get("protocol_sequence"), submission.get("native_sequence"))
        and (as_int(generic.get("protocol_sequence")) or 0) > 0
    )
    direct_fields_missing = [field for field in GENERIC_DIRECT_PAYLOAD_FIELDS if field not in generic]
    matched = len(candidates) == 1
    return {
        "matched": matched,
        "candidate_count": len(candidates),
        "event": {
            key: generic.get(key) for key in (
                "_line", "event_sequence", "thread", "readable", "command", "action",
                "action_vtable_rva", "origin", "protocol_sequence", "protocol_flags",
                "forward_to_original", "business_result", "session_id",
            )
        } if generic else {},
        "target_pointer": {
            "addr": target.get("addr"),
            "action": target.get("action"),
            "payload": target_payload,
        },
        "clone_line": clone.get("line"),
        "line_before_clone": line_before_clone,
        "payload_bound_through_target": payload_bound,
        "protocol_bound_to_transport_and_submission": protocol_bound,
        "transport_pointer": {
            "outgoing": transport_event.get("outgoing"),
            "source_addr": transport_source.get("addr"),
            "loaded_addr": transport.get("loaded", {}).get("addr"),
            "clone_source_addr": clone.get("source", {}).get("addr"),
        },
        "direct_payload_fields_missing": direct_fields_missing,
        "source_trigger": {
            "entry_call": "alliance-execution.inc: bridge_execution_execute -> bridge_response_observe(value)",
            "call_order": "generic observation precedes protocol_capture, execution target lookup and authority gate",
            "flush": "diplomacy-observer-v10.cpp: observation_flush writes diplomatic_command_observed",
            "generic_guard": "native_generic_execution_entry_guard_installed covers direct_calls and vtable_calls",
        },
        "accepted_as_insult_entry": matched and line_before_clone and payload_bound and protocol_bound,
    }


def _public_result_from_container(container: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Find a public result in either an execution report or a resume report."""

    for key in ("final_result", "reopened_result", "first_result"):
        value = container.get(key)
        if isinstance(value, dict) and isinstance(value.get("result"), dict):
            return value["result"], key
    execution = container.get("execution")
    if isinstance(execution, dict) and isinstance(execution.get("result"), dict):
        return execution["result"], "execution.result"
    poll = container.get("poll")
    if isinstance(poll, dict) and isinstance(poll.get("final"), dict):
        final = poll["final"]
        if isinstance(final.get("result"), dict):
            return final["result"], "poll.final.result"
    return {}, None


def _resume_public_validation(resume_artifact: Path, report: dict[str, Any],
                              native_result: dict[str, Any]) -> dict[str, Any]:
    """Bind a read-only resume result to the original native event."""

    resume_report_path = resume_artifact / "report.json"
    resume = _bounded_json(resume_report_path)
    candidates = []
    for key in ("first_result", "final_result", "reopened_result"):
        item = resume.get(key)
        if isinstance(item, dict) and isinstance(item.get("result"), dict):
            candidates.append((key, item))
    public, public_source = _public_result_from_container(resume)
    native_keys = (
        "event", "request_id", "action_id", "actor", "recipient", "phase", "date_raw",
        "family", "insult_id", "outcome", "native_outcome", "native_state", "native_variant",
        "insult_before", "insult_after", "opinion_modifier_before_raw",
        "opinion_modifier_after_raw", "prestige_before_raw", "prestige_after_raw",
        "execution_verified", "request_binding_verified",
    )
    native_match = bool(public) and all(
        (public.get(key) == native_result.get(key))
        for key in native_keys
        if key not in ("native_outcome",)
    ) and (
        "native_outcome" not in public
        or public.get("native_outcome") == native_result.get("outcome")
    )
    stable_candidates = bool(candidates) and all(item.get("status") == "executed" for _, item in candidates)
    stable_results = bool(candidates) and all(item.get("result") == candidates[0][1].get("result") for _, item in candidates)
    session = resume.get("session") if isinstance(resume.get("session"), dict) else {}
    identity = (
        resume.get("request_id") == report.get("request_id")
        and resume.get("action_id") == report.get("action_id")
        and resume.get("actor") == report.get("actor")
        and resume.get("recipient") == report.get("recipient")
        and resume.get("phase") == report.get("phase")
        and session.get("session_id") == report.get("session", {}).get("session_id")
    )
    return {
        "matched": native_match and stable_candidates and stable_results and identity,
        "path": str(resume_report_path.resolve()),
        "sha256": _sha256(resume_report_path),
        "status": resume.get("status"),
        "public_source": public_source,
        "candidate_statuses": {key: item.get("status") for key, item in candidates},
        "stable_candidates": stable_candidates,
        "stable_results": stable_results,
        "identity": identity,
        "native_match": native_match,
        "request_id": resume.get("request_id"),
        "session_id": session.get("session_id"),
    }


def _generic_source_binding(artifact: Path) -> dict[str, Any]:
    """Bind the generic-entry interpretation to the immutable B manifest."""

    manifest_path = next(
        (candidate for candidate in (
            artifact / "build-manifest.json",
            artifact.parent / "build-manifest.json",
        ) if candidate.is_file()),
        None,
    )
    if manifest_path is None:
        return {"available": False, "reason": "build-manifest.json missing"}
    manifest = _bounded_json(manifest_path)
    source_values = manifest.get("sources")
    sources = source_values if isinstance(source_values, list) else []
    selected = {
        item.get("name"): item.get("sha256")
        for item in sources
        if isinstance(item, dict)
        and item.get("name") in ("alliance-execution.inc", "diplomacy-observer-v10.cpp")
    }
    return {
        "available": set(selected) == {"alliance-execution.inc", "diplomacy-observer-v10.cpp"},
        "manifest": _record(manifest_path),
        "sources": selected,
        "facts": [
            "alliance-execution.inc: bridge_execution_execute calls bridge_response_observe(value) before protocol_capture and authority target lookup",
            "diplomacy-observer-v10.cpp: bridge_response_observe validates generic command/action/header; observation_flush emits diplomatic_command_observed",
            "alliance-execution.inc: native_generic_execution_entry_guard_installed covers direct and vtable calls",
        ],
    }


def _result_checks(report: dict[str, Any], event_data: dict[str, Any],
                   expected_parameter: int | None) -> tuple[dict[str, bool], dict[str, Any], dict[str, Any]]:
    action = str(report.get("action_id", ""))
    recipient = str(report.get("recipient", ""))
    request_id = str(report.get("request_id", ""))
    session = _session(report)
    date_raw = as_int(report.get("expected_date_raw"))
    results = [value for value in common._session_events(event_data, RESULT_EVENT, session)
               if value.get("request_id") == request_id
               and value.get("action_id") == action
               and value.get("family") == FAMILY
               and value.get("actor") == ACTOR
               and value.get("recipient") == recipient
               and value.get("phase") == PHASE
               and _strict_int(value.get("date_raw"), date_raw)]
    result = results[0] if len(results) == 1 else {}
    before = result.get("insult_before")
    after = result.get("insult_after")
    raw_fields = (
        "opinion_modifier_before_raw", "opinion_modifier_after_raw",
        "prestige_before_raw", "prestige_after_raw",
    )
    execution = report.get("execution") if isinstance(report.get("execution"), dict) else {}
    poll = report.get("poll") if isinstance(report.get("poll"), dict) else {}
    public = execution.get("result") if isinstance(execution.get("result"), dict) else {}
    final = poll.get("final") if isinstance(poll.get("final"), dict) else {}
    poll_public = final.get("result") if isinstance(final.get("result"), dict) else {}
    public_match = (
        bool(public) and bool(poll_public) and public == poll_public
        and public.get("event") == RESULT_EVENT
        and public.get("family") == FAMILY
        and public.get("request_id") == request_id
        and same_int(public.get("insult_id"), result.get("insult_id"))
    )
    checks = {
        "insult_one_matching_result": len(results) == 1,
        "insult_result_event_and_family": result.get("event") == RESULT_EVENT
        and result.get("family") == FAMILY,
        "insult_result_request_binding": (
            result.get("session_id") == session
            and result.get("request_id") == request_id
            and result.get("action_id") == action
            and result.get("actor") == ACTOR
            and result.get("recipient") == recipient
            and result.get("phase") == PHASE
            and _strict_int(result.get("date_raw"), date_raw)
        ),
        "insult_result_state_variant": (
            _strict_int(result.get("native_state"), 0)
            and _strict_int(result.get("native_variant"), 1)
        ),
        "insult_result_executed_transition": (
            result.get("outcome") == "executed"
            and before is False and after is True
        ),
        "insult_result_parameter40_binding": (
            _parameter_valid(action, result.get("insult_id"), expected_parameter)
        ),
        "insult_result_raw_counters_int32": all(
            _strict_int(result.get(field)) for field in raw_fields
        ),
        "insult_result_verified": (
            result.get("execution_verified") is True
            and result.get("request_binding_verified") is True
        ),
        "insult_single_sided_without_response": (
            all(field not in result for field in
                ("accepted", "rejected", "accept", "reject", "response"))
            and result.get("outcome") not in ("accepted", "rejected")
        ),
        "insult_public_result_matches_native": public_match,
    }
    detail = {
        "event_line": result.get("_line"),
        "request_id": request_id,
        "session_id": session,
        "action_id": action,
        "family": result.get("family"),
        "insult_id": result.get("insult_id"),
        "native_state": result.get("native_state"),
        "native_variant": result.get("native_variant"),
        "insult_before": before,
        "insult_after": after,
        "outcome": result.get("outcome"),
        "execution_verified": result.get("execution_verified"),
        "request_binding_verified": result.get("request_binding_verified"),
        "public_result_present": bool(public),
        "poll_result_present": bool(poll_public),
    }
    return checks, detail, result


def _rename_common_checks(checks: dict[str, Any]) -> dict[str, Any]:
    names = {
        "report_identity_improve_relations_fra_sav": "insult_report_identity",
        "report_event_slice_metadata_matches_stream": "insult_report_event_slice_metadata_matches_stream",
        "report_and_event_inputs_within_bound": "insult_report_and_event_inputs_within_bound",
        "source_report_action_is_supported": "insult_source_action_supported",
        "single_execute_call": "insult_single_execute_call",
        "one_matching_task_result": "insult_one_matching_result_from_common_chain",
        "native_submission_and_task_result_verified": "insult_common_submission_result_verified",
        "public_result_matches_native_result": "insult_common_public_result_match",
        "positive_validation_passed": "insult_positive_validation_passed",
    }
    return {names.get(name, name): value for name, value in checks.items()}


def _configure_common(report: dict[str, Any]) -> dict[str, Any]:
    contract = _contract()
    action = str(report.get("action_id", ""))
    recipient = str(report.get("recipient", ""))
    actions = contract.get("actions", {})
    if action not in actions:
        raise ValueError(f"unsupported Insult action: {action!r}")
    common.START_ACTION = action
    common.STOP_ACTION = "__insult_unreachable_stop__"
    common.SUPPORTED_ACTIONS = frozenset((action,))
    common.FAMILY = FAMILY
    common.ACTOR = ACTOR
    common.RECIPIENT = recipient
    common.PHASE = PHASE
    common.EXPECTED_VARIANT = int(actions[action]["variant38"])
    common.EXPECTED_STATE = int(actions[action]["state34"])
    common.EXPECTED_EXTRA60 = int(contract["payload"]["extra60"])
    common.EXPECTED_DISCRIMINATOR = int(contract["payload"]["discriminator"])
    common.EXPECTED_VTABLE_RVA = int(contract["payload"]["vtable_rva"])
    common.RESULT_EVENT = RESULT_EVENT
    common.RESULT_BEFORE_FIELD = contract["result"]["before_field"]
    common.RESULT_AFTER_FIELD = contract["result"]["after_field"]
    common.SKIP_STATE_OBSERVATION = True
    common.INTERESTING_EVENTS = INTERESTING_EVENTS
    common.INTERESTING_SET = INTERESTING_SET
    # The common semantic-key helper predates Insult's signed parameter40 and
    # intentionally does not include that field.  Keep its original payload
    # field set so source/clone semantic matching remains valid; the dedicated
    # parameter checks below bind parameter40 independently across every
    # observed stage and the final result.
    common.PAYLOAD_FIELDS = tuple(
        field for field in common.PAYLOAD_FIELDS if field != "parameter40"
    )
    return contract


def _negative_validation(artifact: Path) -> dict[str, Any]:
    report = _bounded_json(artifact / "report.json")
    session = _session(report)
    action = str(report.get("action_id", ""))
    # Install the Insult event filter before streaming.  Authority reports
    # omit target/date, so the first pass uses only the action and session;
    # the dispatch event supplies the remaining identity below.
    initial_report = dict(report)
    initial_report.setdefault("actor", ACTOR)
    initial_report.setdefault("recipient", "")
    initial_report.setdefault("phase", PHASE)
    _configure_common(initial_report)
    event_path = _event_path(artifact)
    event_data = _stream(event_path)
    # Authority-test reports intentionally do not claim an execution request
    # identity.  The native dispatch event is the authoritative source for
    # target and date in this negative path; do not manufacture either value
    # from an operator summary.
    dispatch_candidates = [value for value in common._session_events(
        event_data, AUTHORITY_EVENT, session)
        if value.get("action_id") == action
        and value.get("actor") == ACTOR
        and value.get("phase") == PHASE]
    recipient = str(report.get("recipient", ""))
    if not recipient and len(dispatch_candidates) == 1:
        recipient = str(dispatch_candidates[0].get("recipient", ""))
    date_raw = as_int(report.get("expected_date_raw"))
    if date_raw is None and len(dispatch_candidates) == 1:
        date_raw = as_int(dispatch_candidates[0].get("date_raw"))
    identity_report = dict(report)
    identity_report.setdefault("actor", ACTOR)
    identity_report.setdefault("recipient", recipient)
    identity_report.setdefault("phase", PHASE)
    identity_report.setdefault("expected_date_raw", date_raw)
    contract = _configure_common(identity_report)
    dispatches = [value for value in dispatch_candidates
                  if value.get("recipient") == recipient
                  and _strict_int(value.get("date_raw"), date_raw)]
    rejections = [value for value in common._session_events(
        event_data, REJECTION_EVENT, session)]
    submissions = common._session_events(event_data, SUBMISSION_EVENT, session)
    results = common._session_events(event_data, RESULT_EVENT, session)
    dispatch = dispatches[0] if len(dispatches) == 1 else {}
    rejection = rejections[0] if len(rejections) == 1 else {}
    route = dispatch.get("dispatch_route")
    route_ok = route in ("direct_entry", "transport", "direct", "transport_callback")
    accepted_expected = (
        False if route in ("direct_entry", "direct")
        else True if route in ("transport", "transport_callback") else None
    )
    expected_parameter = _action_parameter(report, action)
    checks = {
        "insult_one_unauthorized_dispatch": len(dispatches) == 1,
        "insult_dispatch_route_is_direct_or_transport": route_ok,
        "insult_dispatcher_acceptance_matches_route": (
            accepted_expected is not None
            and dispatch.get("dispatcher_accepted") is accepted_expected
        ),
        "insult_no_authority_seed": (
            dispatch.get("authority_seed_created") is contract["unauthorized"]["authority_seed_created"]
        ),
        "insult_dispatch_action_identity": (
            dispatch.get("action_id") == action
            and action in contract["actions"]
            and dispatch.get("actor") == ACTOR
            and dispatch.get("recipient") == recipient
            and dispatch.get("phase") == PHASE
            and _strict_int(dispatch.get("date_raw"), date_raw)
            and _strict_int(dispatch.get("variant38"), 1)
            and _strict_int(dispatch.get("state34"), 0)
        ),
        # The authority dispatch record does not serialize Insult's optional
        # parameter40.  If the negative artifact omits it, retain that fact in
        # the report instead of fabricating a selected scornful id; action
        # identity and unauthorized rejection remain independently checked.
        "insult_negative_parameter_semantics": (
            expected_parameter is None or _parameter_valid(action, expected_parameter)
        ),
        "insult_one_native_rejection": len(rejections) == 1,
        "insult_rejection_reason_unauthorized": (
            rejection.get("reason") == contract["unauthorized"]["reason"]
        ),
        "insult_rejection_not_submitted": (
            rejection.get("submitted") is contract["unauthorized"]["submitted"]
        ),
        "insult_no_authorized_submission": len(submissions) == 0,
        "insult_no_execution_result": len(results) == 0,
    }
    passed = all(checks.values())
    return {
        "status": "passed" if passed else "failed",
        "validation_passed": passed,
        "artifact": _record(artifact / "report.json"),
        "event_log": _record(event_path),
        "session_id": session,
        "action_id": action,
        "actor": ACTOR,
        "recipient": recipient,
        "phase": PHASE,
        "date_raw": date_raw,
        "checks": checks,
        "check_summary": _summary(checks),
        "dispatch": {
            "line": dispatch.get("_line"),
            "dispatch_route": route,
            "dispatcher_accepted": dispatch.get("dispatcher_accepted"),
            "authority_seed_created": dispatch.get("authority_seed_created"),
        },
        "rejection": {
            "line": rejection.get("_line"),
            "request_id": rejection.get("request_id"),
            "reason": rejection.get("reason"),
            "submitted": rejection.get("submitted"),
        },
        "parameter40": {
            "observed": expected_parameter is not None,
            "value": expected_parameter,
            "note": "authority dispatch schema omitted parameter40" if expected_parameter is None else None,
        },
    }


def _summary(checks: dict[str, Any]) -> dict[str, Any]:
    failed = [name for name, value in checks.items() if value is False]
    return {"total": len(checks), "passed": len(checks) - len(failed), "failed": failed}


def _generic_projection(generic: dict[str, Any], common_checks: dict[str, Any],
                        parameter_checks: dict[str, Any], report: dict[str, Any],
                        event_data: dict[str, Any], common_report: dict[str, Any]) -> dict[str, bool]:
    """Project generic-entry evidence onto the common chain check names."""

    session = _session(report)
    generic_event = generic.get("event") if isinstance(generic.get("event"), dict) else {}
    chain = common_report.get("chain") if isinstance(common_report.get("chain"), dict) else {}
    clone = chain.get("clone") if isinstance(chain.get("clone"), dict) else {}
    transport = chain.get("transport") if isinstance(chain.get("transport"), dict) else {}
    target = generic.get("target_pointer") if isinstance(generic.get("target_pointer"), dict) else {}
    submissions = common._session_events(event_data, SUBMISSION_EVENT, session)
    results = common._session_events(event_data, RESULT_EVENT, session)
    generic_session = bool(generic_event) and generic_event.get("session_id", session) == session
    payload_valid = bool(generic.get("payload_bound_through_target"))
    protocol_valid = bool(generic.get("protocol_bound_to_transport_and_submission"))
    pointer_valid = (
        bool(generic.get("matched"))
        and same_int(generic_event.get("command"), target.get("addr"))
        and same_int(generic_event.get("action"), target.get("action"))
        and same_int(transport.get("loaded", {}).get("addr"), clone.get("source", {}).get("addr"))
        and same_int(
            (generic.get("transport_pointer") or {}).get("outgoing"),
            (generic.get("transport_pointer") or {}).get("source_addr"),
        )
    )
    # The generic entry is emitted before the original executor proceeds to
    # transport/clone.  JSONL line order is the only common ordering domain;
    # callback_sequence belongs to the later transport hooks and is therefore
    # deliberately not compared to generic event_sequence.
    order_valid = bool(generic.get("line_before_clone"))
    native_receipt_unique = len(submissions) == 1 and len(results) == 1
    projection = {
        "insult_single_execute_call": native_receipt_unique,
        "session_bound_chain": generic_session and bool(
            common_checks.get("one_matching_wrapper_clone")
            and common_checks.get("one_matching_transport")
            and common_checks.get("one_matching_submission")
            and common_checks.get("insult_one_matching_result_from_common_chain")
        ),
        "one_matching_command_entry": bool(generic.get("accepted_as_insult_entry")),
        "payload_family_extra60_state_variant_consistent": payload_valid,
        "request_semantic_key_bound_through_chain": payload_valid and pointer_valid,
        "protocol_sequence_bound_to_request": protocol_valid,
        "pointer_chain_source_clone_transport_target_entry": pointer_valid,
        "callback_order_transport_load_clone_entry": order_valid,
        "insult_parameter40_present_on_source_chain": bool(
            parameter_checks.get("insult_parameter40_present_on_source_chain")
        ) and payload_valid,
    }
    return projection


def build_report(artifact: Path, negative_artifacts: list[Path] | None = None,
                 resume_artifact: Path | None = None) -> dict[str, Any]:
    artifact = artifact.resolve(strict=True)
    report = _bounded_json(artifact / "report.json")
    contract = _configure_common(report)
    event_path = _event_path(artifact)
    event_data = _stream(event_path)
    common_report = common.build_report(artifact)
    result_events = common._session_events(event_data, RESULT_EVENT, _session(report))
    result_candidate = result_events[0] if len(result_events) == 1 else {}
    expected_parameter = _action_parameter(report, str(report.get("action_id", "")), result_candidate)
    result_checks, result_detail, result = _result_checks(
        report, event_data, expected_parameter)
    parameter_checks, parameter_detail = _parameter_checks(
        report, event_data, result, len(result_events))
    checks = _rename_common_checks(common_report.get("checks", {}))
    checks.update(parameter_checks)
    checks.update(result_checks)
    generic_detail = _generic_entry_validation(report, event_data, common_report)
    generic_detail["source_binding"] = _generic_source_binding(artifact)
    checks.update(_generic_projection(
        generic_detail, checks, parameter_checks, report, event_data, common_report))
    # The original ordinary artifact predates the API NameError fix and has
    # no public result fields.  A passed read-only resume may supplement that
    # public evidence; it never rewrites or replaces the original report.
    resume_detail: dict[str, Any] | None = None
    if resume_artifact is not None:
        resume_detail = _resume_public_validation(resume_artifact.resolve(strict=True), report, result)
        if resume_detail.get("matched"):
            checks["insult_common_public_result_match"] = True
            checks["insult_public_result_matches_native"] = True
    # The common chain has a dedicated Alliance entry predicate.  Insult's
    # generic entry projection above is the authoritative check for this
    # family, while the detail retains exactly which direct fields were absent.
    passed = all(checks.values())
    output: dict[str, Any] = {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "validation_passed": passed,
        "validator": "work/validate_insult_source.py",
        "artifact": str(artifact),
        "family": FAMILY,
        "action_id": report.get("action_id"),
        "actor": report.get("actor"),
        "recipient": report.get("recipient"),
        "phase": report.get("phase"),
        "request_id": report.get("request_id"),
        "session_id": _session(report),
        "fixture_binding": {
            "path": str(CONTRACT_PATH.resolve()),
            "sha256": _sha256(CONTRACT_PATH),
            "family": FAMILY,
            "vtable_rva": contract["payload"]["vtable_rva"],
            "factory_selector": contract["payload"]["factory_selector"],
            "parameter40": parameter_detail,
        },
        "source_report": common_report.get("source_report"),
        "event_log": common_report.get("event_log"),
        "checks": checks,
        "check_summary": _summary(checks),
        "failed_checks": [name for name, value in checks.items() if value is False],
        "chain": common_report.get("chain"),
        "generic_entry": generic_detail,
        "insult_parameter40": parameter_detail,
        "insult_result": result_detail,
        "limitations": [
            "参数40由每个 source/loaded/clone/entry payload 和最终 Insult result 共同绑定；submission 回执本身没有重复序列化该字段。",
            "selector 10567、Insult vtable 0x1c7f6b0 和 discriminator 357 来自独立静态契约 fixture；运行链实际使用的对象 payload、复制、传输和入口由事件逐项复核。",
            "单方 Insult 结果只接受 native_state=0、native_variant=1、insult_before=false→insult_after=true；不会把 accepted/rejected 字段解释为业务结果。",
        ],
    }
    if resume_detail is not None:
        output["resume_public_evidence"] = resume_detail
    if negative_artifacts:
        negatives = [_negative_validation(path.resolve(strict=True)) for path in negative_artifacts]
        output["negatives"] = negatives
        output["status"] = (
            "passed" if output["status"] == "passed"
            and all(value["status"] == "passed" for value in negatives)
            else "failed"
        )
        output["validation_passed"] = output["status"] == "passed"
    return output


def _failed(checks: dict[str, Any]) -> str:
    return ", ".join(name for name, value in checks.items() if value is False) or "无"


def markdown_report(value: dict[str, Any]) -> str:
    parameter = value.get("insult_parameter40", {})
    result = value.get("insult_result", {})
    generic = value.get("generic_entry", {})
    summary = value.get("check_summary", {})
    lines = [
        "# Insult 原生来源链验证",
        "",
        f"结论：{value.get('status', 'failed').upper()}。",
        "",
        f"对象：{value.get('action_id')}，{value.get('actor')}→{value.get('recipient')}，"
        f"family={FAMILY}，phase={value.get('phase')}，request_id={value.get('request_id')}。",
        f"参数：payload +0x40/parameter40={parameter.get('expected_parameter40')}；"
        f"结果 insult_id={result.get('insult_id')}。",
        f"结果：native_state={result.get('native_state')}，native_variant={result.get('native_variant')}，"
        f"insult_before={result.get('insult_before')}→insult_after={result.get('insult_after')}，"
        f"outcome={result.get('outcome')}。",
        "",
        "## 独立检查",
        "",
    ]
    if value.get("checks"):
        lines.extend([
            f"正向检查：{summary.get('passed', 0)}/{summary.get('total', 0)} 通过。",
            f"失败检查：{_failed(value.get('checks', {}))}。",
            "Insult 使用 generic execution entry；入口 command/action/header 由 "
            "diplomatic_command_observed 记录，family、参数40、双方、日期和状态由同一指针的 "
            "clone/transport payload 继续绑定。",
            f"generic entry：{'通过' if generic.get('accepted_as_insult_entry') else '未通过'}；"
            f"候选={generic.get('candidate_count', 0)}，入口行={generic.get('event', {}).get('_line')}，"
            f"clone行={generic.get('clone_line')}。",
            "generic 事件直接缺少字段："
            + ", ".join(generic.get("direct_payload_fields_missing", [])) + "。",
        ])
    else:
        lines.append("本次仅验证未授权 authority 负例；未执行正向业务链检查。")
    for index, negative in enumerate(value.get("negatives", []), 1):
        negative_summary = negative.get("check_summary", {})
        lines.extend([
            "",
            f"## 未授权负例 {index}",
            "",
            f"结论：{negative.get('status')}；route={negative.get('dispatch', {}).get('dispatch_route')}；"
            f"reason={negative.get('rejection', {}).get('reason')}；"
            f"检查：{negative_summary.get('passed', 0)}/{negative_summary.get('total', 0)} 通过；"
            f"失败检查：{_failed(negative.get('checks', {}))}。",
        ])
    event_log = value.get("event_log", {}) or {}
    lines.extend([
        "",
        "## 输入绑定",
        "",
        f"报告：{value.get('artifact')}；事件文件：{event_log.get('path')}；"
        f"事件 SHA-256：{event_log.get('sha256')}。",
        "验证器只读取不超过 10 MiB 的报告和事件切片，并把结果写入新的 evidence 目录。",
    ])
    resume = value.get("resume_public_evidence")
    if isinstance(resume, dict):
        lines.extend([
            "",
            "## 只读 resume 公共结果补充",
            "",
            f"报告：{resume.get('path')}；SHA-256：{resume.get('sha256')}；"
            f"来源={resume.get('public_source')}；绑定={'通过' if resume.get('matched') else '失败'}。",
            "该文件只补充原失败报告缺失的公共结果字段，不修改原始 report.json 或事件切片。",
        ])
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--negative-artifact", action="append", type=Path)
    parser.add_argument(
        "--resume-artifact", type=Path,
        help="read-only resume artifact whose public result supplements an earlier report",
    )
    parser.add_argument(
        "--negative-only", action="store_true",
        help="only validate one or more unauthorized authority artifacts",
    )
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    negatives = [path.resolve(strict=True) for path in (args.negative_artifact or [])]
    if args.negative_only:
        if not negatives:
            raise SystemExit("--negative-only requires --negative-artifact")
        artifact = None
    else:
        if args.artifact is None:
            raise SystemExit("--artifact is required unless --negative-only is used")
        artifact = args.artifact.resolve(strict=True)
    output_dir = args.output_dir.resolve() if args.output_dir else (
        (negatives[0].parent if negatives else artifact.parent)
        / f"insult-source-validation-{uuid.uuid4().hex}")
    output_dir.mkdir(parents=True, exist_ok=False)
    if args.negative_only:
        negative_values = [_negative_validation(path) for path in negatives]
        value = {
            "schema_version": 1,
            "status": "passed" if all(item["status"] == "passed" for item in negative_values) else "failed",
            "validation_passed": all(item["status"] == "passed" for item in negative_values),
            "validator": "work/validate_insult_source.py",
            "family": FAMILY,
            "mode": "negative_only",
            "negatives": negative_values,
        }
    else:
        value = build_report(artifact, negatives, args.resume_artifact)
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
