#!/usr/bin/env python3
"""Validate the native Support Independence source and response chains.

The positive artifact contains the player request followed by the native NPC
response.  This validator checks both serialized payload chains independently
of the Python consumer receipt:

``creator command -> transport source/load -> wrapper clone -> command entry``
``-> native response proof -> support relation result``.

The optional negative artifact is an unauthorized authority fixture.  It must
be rejected at the native gate without an authorized submission or relation
result.  Input JSONL is streamed and bounded at 10 MiB; source artifacts are
never rewritten and the game is never started.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
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
from validate_alliance_authority_source import (  # noqa: E402
    as_int,
    header_equal,
    same_int,
)


MAX_INPUT_BYTES = 10 * 1024 * 1024
FAMILY = "support_independence"
START_ACTION = "support_independence"
STOP_ACTION = "revoke_support_independence"
SUPPORTED_ACTIONS = frozenset((START_ACTION, STOP_ACTION))
ACTOR = "FRA"
PHASE = "initiate"
SELECTOR = 0x2F2E
VTABLE_RVA = 0x1C805F0
DISCRIMINATOR = 0x165
EXPECTED_EXTRA60 = 0
SELECTOR_INPUT_HEX = "7b0070706f72745f696e646570656e64"
RESPONSE_EVENT = "native_diplomacy_relation_response_result"
EXECUTION_EVENT = "native_diplomacy_relation_execution_result"
SUBMISSION_EVENT = "native_alliance_submission_result"
ENTRY_EVENT = "native_alliance_command_entry_observed"
CLONE_EVENT = "native_alliance_wrapper_clone"
TRANSPORT_EVENT = "native_alliance_transport_completed"
COMMAND_EVENT = "diplomatic_command_observed"
AUTHORITY_EVENT = "native_alliance_authority_test_dispatched"
REJECTION_EVENT = "native_alliance_execution_rejected"
LIFECYCLE_EVENT = "native_alliance_lifecycle"
FIELD_READ_EVENT = "native_wrapper_field_read_begin"
INTERESTING_EVENTS = (
    ENTRY_EVENT,
    CLONE_EVENT,
    TRANSPORT_EVENT,
    SUBMISSION_EVENT,
    RESPONSE_EVENT,
    EXECUTION_EVENT,
    COMMAND_EVENT,
    AUTHORITY_EVENT,
    REJECTION_EVENT,
    LIFECYCLE_EVENT,
    FIELD_READ_EVENT,
)
INTERESTING_SET = frozenset(INTERESTING_EVENTS)


def _configure_common() -> None:
    """Configure imported bounded payload primitives for this family only."""

    common.FAMILY = FAMILY
    common.EXPECTED_EXTRA60 = EXPECTED_EXTRA60
    common.EXPECTED_DISCRIMINATOR = DISCRIMINATOR
    common.EXPECTED_VTABLE_RVA = VTABLE_RVA
    common.INTERESTING_EVENTS = INTERESTING_EVENTS
    common.INTERESTING_SET = INTERESTING_SET


def _bounded_json(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise ValueError(f"refusing to parse input over 10 MiB: {path}")
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


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


def _shape_summary(shape: Any) -> dict[str, Any]:
    return common._shape_summary(shape)


def _core_payload_equal(left: Any, right: Any) -> bool:
    """Compare serialized identity while allowing the post-entry envoy write."""

    left_payload = _payload(left)
    right_payload = _payload(right)
    if not (common._payload_valid(left) and common._payload_valid(right)):
        return False
    return (
        left_payload.get("family") == right_payload.get("family") == FAMILY
        and _strict_int(left_payload.get("extra60"), EXPECTED_EXTRA60)
        and _strict_int(right_payload.get("extra60"), EXPECTED_EXTRA60)
        and all(
            same_int(left_payload.get(field), right_payload.get(field))
            for field in common.PAYLOAD_FIELDS
            if field != "envoy30"
        )
    )


def _payload_matches(shape: Any, *, variant: int, state: int,
                     actor: str, recipient: str, date_raw: int) -> bool:
    payload = _payload(shape)
    return (
        common._payload_valid(shape, variant)
        and payload.get("family") == FAMILY
        and _strict_int(payload.get("extra60"), EXPECTED_EXTRA60)
        and _strict_int(payload.get("state34"), state)
        and _strict_int(payload.get("variant38"), variant)
        and _strict_int(payload.get("date28"), date_raw)
        and _strict_int(payload.get("date2c"), date_raw)
        and _tag(payload.get("actor10")) == actor
        and _tag(payload.get("mirror18")) == actor
        and _tag(payload.get("recipient20")) == recipient
    )


def _shape_matches(shape: Any, *, variant: int, state: int,
                   actor: str, recipient: str, date_raw: int) -> bool:
    return common._object_valid(shape, variant) and _payload_matches(
        shape, variant=variant, state=state, actor=actor,
        recipient=recipient, date_raw=date_raw,
    )


def _session_events(event_data: dict[str, Any], name: str,
                    session: str) -> list[dict[str, Any]]:
    return [
        value for value in event_data.get("events", {}).get(name, [])
        if str(value.get("session_id", "")) == session
    ]


def _single(values: list[dict[str, Any]], predicate: Any) -> tuple[dict[str, Any], int]:
    matches = [value for value in values if predicate(value)]
    return (matches[0] if len(matches) == 1 else {}, len(matches))


def _chain(
        event_data: dict[str, Any], session: str, sequence: int,
        *, variant: int, state: int, actor: str, recipient: str,
        action: str, date_raw: int,
        result_line: int | None = None) -> tuple[dict[str, bool], dict[str, Any]]:
    """Validate one protocol sequence from creator to command entry."""

    entries = _session_events(event_data, ENTRY_EVENT, session)
    clones = _session_events(event_data, CLONE_EVENT, session)
    transports = _session_events(event_data, TRANSPORT_EVENT, session)
    commands = _session_events(event_data, COMMAND_EVENT, session)

    entry, entry_count = _single(entries, lambda value: (
        value.get("action_id") == action
        and value.get("actor_field") == actor
        and value.get("recipient_field") == recipient
        and _strict_int(value.get("protocol_sequence"), sequence)
        and _payload_matches(value.get("source"), variant=variant, state=state,
                             actor=actor, recipient=recipient, date_raw=date_raw)
    ))
    transport, transport_count = _single(transports, lambda value: (
        _strict_int(value.get("source", {}).get("protocol_sequence"), sequence)
        and _shape_matches(value.get("source"), variant=variant, state=state,
                           actor=actor, recipient=recipient, date_raw=date_raw)
        and _shape_matches(value.get("loaded"), variant=variant, state=state,
                           actor=actor, recipient=recipient, date_raw=date_raw)
    ))
    clone, clone_count = _single(clones, lambda value: (
        _strict_int(value.get("source", {}).get("protocol_sequence"), sequence)
        and _shape_matches(value.get("source"), variant=variant, state=state,
                           actor=actor, recipient=recipient, date_raw=date_raw)
        and common._object_valid(value.get("target"), variant)
        and _payload(value.get("target")).get("family") == FAMILY
        and _strict_int(_payload(value.get("target")).get("state34"), state)
    ))
    command, command_count = _single(commands, lambda value: (
        _strict_int(value.get("protocol_sequence"), sequence)
        and same_int(value.get("action_vtable_rva"), VTABLE_RVA)
        and same_int(value.get("origin"), 0xFFFF)
    ))

    entry_source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    clone_source = clone.get("source") if isinstance(clone.get("source"), dict) else {}
    clone_target = clone.get("target") if isinstance(clone.get("target"), dict) else {}
    transport_source = transport.get("source") if isinstance(transport.get("source"), dict) else {}
    transport_loaded = transport.get("loaded") if isinstance(transport.get("loaded"), dict) else {}
    entry_payload = _payload(entry_source)
    clone_target_payload = _payload(clone_target)

    transport_begin = as_int(transport.get("callback_begin"))
    load_sequence = as_int(transport.get("load_callback_sequence"))
    transport_end = as_int(transport.get("callback_end"))
    clone_begin = as_int(clone.get("begin_callback_sequence"))
    clone_end = as_int(clone.get("callback_sequence"))
    entry_callback = as_int(entry.get("callback_sequence"))
    callback_order = (
        None not in (transport_begin, load_sequence, transport_end,
                     clone_begin, clone_end, entry_callback)
        and transport_begin < load_sequence < transport_end
        < clone_begin <= clone_end < entry_callback
    )
    command_pointer = (
        command_count == 1
        and same_int(command.get("command"), entry.get("command"))
        and same_int(command.get("action"), entry.get("action"))
    )
    source_loaded_equal = (
        transport_count == 1
        and transport.get("payload_equal") is True
        and header_equal(transport_source, transport_loaded)
        and common._payload_equal(transport_source, transport_loaded)
    )
    pointer_chain = (
        transport_count == 1 and clone_count == 1 and entry_count == 1
        and same_int(transport_loaded.get("addr"), clone_source.get("addr"))
        and same_int(transport_loaded.get("action"), clone_source.get("action"))
        and same_int(clone_target.get("addr"), entry.get("command"))
        and same_int(clone_target.get("action"), entry.get("action"))
        and same_int(clone.get("native_result"), entry.get("command"))
        and same_int(transport.get("outgoing"), transport_source.get("addr"))
    )
    payload_chain = (
        _core_payload_equal(transport_source, transport_loaded)
        and _core_payload_equal(transport_loaded, clone_source)
        and _core_payload_equal(clone_source, clone_target)
        and _core_payload_equal(clone_target, entry_source)
        and _strict_int(entry_payload.get("date28"), date_raw)
        and _strict_int(entry_payload.get("date2c"), date_raw)
    )
    world_transport = (
        transport.get("completed") is True
        and transport.get("source_captured") is True
        and transport.get("source_identity") is True
        and transport.get("loaded_identity") is True
        and transport.get("peer_is_world_transport") is True
        and transport.get("peer_readable") is True
        and transport.get("world_transport_readable") is True
        and same_int(transport.get("peer"), transport.get("transport"))
        and same_int(transport.get("peer"), transport.get("world_transport"))
        and same_int(transport.get("peer_owner"), transport.get("world_dispatcher"))
    )
    load_contract = (
        transport.get("matching_count") == 1
        and transport.get("load_count") == 1
        and transport.get("loads_truncated") is False
        and transport.get("all_commands_forwarded") is True
        and transport.get("caller_verified") is True
    )
    wrapper_contract = (
        clone.get("caller_return_matches") is True
        and clone.get("native_return_observed") is True
        and clone.get("native_forward_count_by_hook_contract") == 1
        and clone.get("receiver_is_world_transport") is True
        and clone.get("receiver_readable") is True
        and clone.get("world_transport_readable") is True
    )
    authority_observed = (
        isinstance(transport.get("authority"), bool)
        and transport.get("authority") is False
        and clone.get("authorization") == "unknown"
    )
    checks = {
        "one_matching_command_entry": entry_count == 1,
        "one_matching_wrapper_clone": clone_count == 1,
        "one_matching_transport": transport_count == 1,
        "one_matching_creator_command": command_count == 1,
        "family_extra60_vtable_discriminator": (
            entry_count == clone_count == transport_count == 1
            and all(
                _payload(value).get("family") == FAMILY
                and _strict_int(_payload(value).get("extra60"), EXPECTED_EXTRA60)
                and _strict_int(_payload(value).get("vtable_rva"), VTABLE_RVA)
                and _strict_int(_payload(value).get("discriminator"), DISCRIMINATOR)
                for value in (entry_source, clone_source, clone_target,
                              transport_source, transport_loaded)
            )
        ),
        "creator_command_bound_to_entry": command_pointer,
        "transport_source_loaded_equal": source_loaded_equal,
        "pointer_chain_source_clone_transport_entry": pointer_chain,
        "pre_entry_core_payload_equal": payload_chain,
        "transport_world_identity_bound": world_transport,
        "transport_load_contract": load_contract,
        "wrapper_clone_contract": wrapper_contract,
        "authority_observation_bound": authority_observed,
        "callback_order_transport_load_clone_entry": callback_order,
        "result_after_entry": (
            result_line is None
            or (entry_count == 1 and as_int(entry.get("_line")) is not None
                and result_line > as_int(entry.get("_line")))
        ),
    }
    detail = {
        "sequence": sequence,
        "state34": state,
        "variant38": variant,
        "entry_line": entry.get("_line"),
        "clone_line": clone.get("_line"),
        "transport_line": transport.get("_line"),
        "creator_command_line": command.get("_line"),
        "callback": {
            "transport_begin": transport.get("callback_begin"),
            "load": transport.get("load_callback_sequence"),
            "transport_end": transport.get("callback_end"),
            "clone_begin": clone.get("begin_callback_sequence"),
            "clone_end": clone.get("callback_sequence"),
            "entry": entry.get("callback_sequence"),
        },
        "source": _shape_summary(transport_source),
        "loaded": _shape_summary(transport_loaded),
        "clone_source": _shape_summary(clone_source),
        "clone_target": _shape_summary(clone_target),
        "entry_source": _shape_summary(entry_source),
        "transport": {
            "authority": transport.get("authority"),
            "queue_verified": transport.get("queue_verified"),
            "world_transport": transport.get("world_transport"),
        },
        "wrapper": {
            "authorization": clone.get("authorization"),
            "native_forward_count_by_hook_contract": clone.get(
                "native_forward_count_by_hook_contract"),
        },
        "checks": checks,
    }
    return checks, detail


def _selector_checks(event_data: dict[str, Any], session: str,
                     report: dict[str, Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    reads = [value for value in _session_events(event_data, FIELD_READ_EVENT, session)
             if same_int(value.get("field_id"), SELECTOR)]
    exact = [value for value in reads
             if str(value.get("input16_hex", "")).lower() == SELECTOR_INPUT_HEX]
    reported = report.get("selector")
    checks = {
        "native_selector_2f2e_read": len(reads) >= 1,
        "native_selector_input_matches": len(exact) >= 1,
        "optional_report_selector_matches": (
            reported is None or same_int(reported, SELECTOR)
        ),
    }
    return checks, {
        "selector": hex(SELECTOR),
        "field_read_lines": [value.get("_line") for value in reads],
        "exact_input_lines": [value.get("_line") for value in exact],
        "reported_selector": reported,
    }


def _relation_active(section: Any) -> Any:
    if not isinstance(section, dict):
        return None
    relation = section.get("relation")
    if not isinstance(relation, dict):
        return None
    direct = relation.get("support_independence_active")
    if isinstance(direct, bool):
        return direct
    by_action = relation.get("by_action")
    if isinstance(by_action, dict):
        item = by_action.get(START_ACTION)
        if isinstance(item, dict) and isinstance(item.get("support_independence_active"), bool):
            return item["support_independence_active"]
    return None


def _relation_snapshot_checks(
    report: dict[str, Any], expected_before: bool, expected_after: bool
) -> tuple[dict[str, bool], dict[str, Any]]:
    before = _relation_active(report.get("before"))
    after = _relation_active(report.get("after"))
    checks = {
        "before_relation_boolean": isinstance(before, bool),
        "after_relation_boolean": isinstance(after, bool),
        "before_relation_matches_native": before is expected_before,
        "after_relation_matches_native": after is expected_after,
    }
    return checks, {
        "before": before,
        "after": after,
        "expected_before": expected_before,
        "expected_after": expected_after,
    }


def _native_result(
        report: dict[str, Any], event_data: dict[str, Any],
        session: str, recipient: str, action: str, date_raw: int,
        request_id: str) -> tuple[dict[str, bool], dict[str, Any], dict[str, Any]]:
    result_event_name = RESPONSE_EVENT if action == START_ACTION else EXECUTION_EVENT
    candidates = [value for value in _session_events(event_data, result_event_name, session)
                  if value.get("request_id") == request_id
                  and value.get("action_id") == action
                  and value.get("family") == FAMILY
                  and value.get("actor") == ACTOR
                  and value.get("recipient") == recipient
                  and value.get("phase") == PHASE
                  and _strict_int(value.get("date_raw"), date_raw)]
    result = candidates[0] if len(candidates) == 1 else {}
    expected_outcome = report.get("expected_outcome")
    if action == START_ACTION:
        if expected_outcome not in ("accepted", "rejected"):
            expected_outcome = result.get("outcome")
        expected_state = 2 if expected_outcome == "accepted" else 1
        expected_before = False
        expected_after = expected_outcome == "accepted"
        checks = {
            "one_matching_relation_response": len(candidates) == 1,
            "response_event_and_family": (
                result.get("event") == RESPONSE_EVENT
                and result.get("family") == FAMILY
            ),
            "response_request_binding": (
                result.get("request_id") == request_id
                and result.get("session_id") == session
                and result.get("action_id") == action
                and result.get("actor") == ACTOR
                and result.get("recipient") == recipient
                and result.get("phase") == PHASE
                and _strict_int(result.get("date_raw"), date_raw)
            ),
            "response_native_state_1_or_2": (
                _strict_int(result.get("native_state"))
                and as_int(result.get("native_state")) in (1, 2)
            ),
            "response_variant_1": _strict_int(result.get("native_variant"), 1),
            "response_outcome_expected": result.get("outcome") == expected_outcome,
            "response_transition": (
                result.get("support_independence_before") is False
                and result.get("support_independence_after") is expected_after
            ),
            "response_verification_flags": (
                result.get("response_verified") is True
                and result.get("request_binding_verified") is True
            ),
            "outbound_pending_removed_false": result.get("pending_removed") is False,
        }
    else:
        expected_outcome = "executed"
        expected_state = 0
        expected_before = True
        expected_after = False
        checks = {
            "one_matching_relation_execution": len(candidates) == 1,
            "execution_event_and_family": (
                result.get("event") == EXECUTION_EVENT
                and result.get("family") == FAMILY
            ),
            "execution_request_binding": (
                result.get("request_id") == request_id
                and result.get("session_id") == session
                and result.get("action_id") == action
                and result.get("actor") == ACTOR
                and result.get("recipient") == recipient
                and result.get("phase") == PHASE
                and _strict_int(result.get("date_raw"), date_raw)
            ),
            "execution_state_0_variant_0": (
                _strict_int(result.get("native_state"), 0)
                and _strict_int(result.get("native_variant"), 0)
            ),
            "execution_outcome_executed": result.get("outcome") == expected_outcome,
            "execution_transition": (
                result.get("support_independence_before") is True
                and result.get("support_independence_after") is expected_after
            ),
            "execution_verification_flags": (
                result.get("execution_verified") is True
                and result.get("request_binding_verified") is True
            ),
        }
    return checks, {
        "event": result,
        "event_name": result_event_name,
        "expected_outcome": expected_outcome,
        "expected_state": expected_state,
        "expected_before": expected_before,
        "expected_after": expected_after,
    }, result


def _public_result_from(value: object, expected_event: str, action: str,
                        depth: int = 0) -> dict[str, Any] | None:
    """Find the terminal public relation result in execute or resume schema."""
    if depth > 8 or not isinstance(value, dict):
        return None
    if (
        value.get("event") == expected_event
        and value.get("family") == FAMILY
        and value.get("action_id") == action
    ):
        return value
    for key in ("result", "final", "persisted", "reopened_result", "public_result"):
        candidate = value.get(key)
        found = _public_result_from(candidate, expected_event, action, depth + 1)
        if found is not None:
            return found
    return None


def _terminal_status_present(value: object, depth: int = 0) -> bool:
    if depth > 8 or not isinstance(value, dict):
        return False
    if value.get("status") in ("accepted", "rejected", "executed"):
        return True
    return any(
        _terminal_status_present(value.get(key), depth + 1)
        for key in ("result", "final", "persisted", "reopened_result", "public_result")
    )


def _public_checks(report: dict[str, Any], native_result: dict[str, Any],
                   action: str, resume_report: dict[str, Any] | None = None
                   ) -> tuple[dict[str, bool], dict[str, Any]]:
    execution = report.get("execution") if isinstance(report.get("execution"), dict) else {}
    poll = report.get("poll") if isinstance(report.get("poll"), dict) else {}
    execution_result = execution.get("result") if isinstance(execution.get("result"), dict) else {}
    final = poll.get("final") if isinstance(poll.get("final"), dict) else {}
    expected_event = RESPONSE_EVENT if action == START_ACTION else EXECUTION_EVENT
    consumer = resume_report if isinstance(resume_report, dict) else report
    public = _public_result_from(consumer, expected_event, action) or {}
    # A pending public response is still wrapped in final.result, but it has
    # no native relation-result event.  Treat only the terminal public event
    # as a consumed result so the source validator can distinguish the native
    # chain from the API association gap.
    has_public = bool(public)
    if resume_report is not None:
        execution_result = public
        resume_result_checks = resume_report.get("result_checks")
        if isinstance(resume_result_checks, dict) and isinstance(
            resume_result_checks.get("public_result"), dict
        ):
            execution_result = resume_result_checks["public_result"]
    public_matches = (
        has_public
        and execution_result == public
        and public.get("event") == expected_event
        and public.get("family") == FAMILY
        and public.get("action_id") == action
        and public.get("request_id") == native_result.get("request_id")
        and public.get("native_state") == native_result.get("native_state")
        and public.get("native_variant") == native_result.get("native_variant")
    )
    checks = {
        "public_result_matches_native": public_matches,
        "public_result_terminal": has_public and _terminal_status_present(consumer),
    }
    pending = resume_report is None and not has_public and report.get("status") == "pending"
    return checks, {
        "execution_result": execution_result,
        "poll_final": final,
        "public_result": public,
        "public_pending": pending,
        "consumer_status": report.get("status"),
        "resume_consumer": resume_report is not None,
    }


def _metadata_checks(artifact: Path, event_path: Path,
                     report: dict[str, Any], event_data: dict[str, Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    metadata = report.get("native_events") if isinstance(report.get("native_events"), dict) else {}
    actual = _record(event_path)
    path_matches = False
    metadata_path = metadata.get("path")
    if isinstance(metadata_path, str):
        try:
            path_matches = Path(metadata_path).resolve() == event_path.resolve()
        except OSError:
            path_matches = False
    start_offset = as_int(metadata.get("start_offset"))
    end_offset = as_int(metadata.get("end_offset"))
    checks = {
        "input_report_bounded": (artifact / "report.json").stat().st_size <= MAX_INPUT_BYTES,
        "input_events_bounded": event_path.stat().st_size <= MAX_INPUT_BYTES,
        "event_jsonl_complete": not event_data.get("malformed_lines")
        and not event_data.get("non_object_lines"),
        "event_sha256_matches_report": metadata.get("sha256") == actual["sha256"],
        "event_bytes_matches_report": same_int(metadata.get("bytes"), actual["size_bytes"]),
        "event_path_matches_report": path_matches,
        "event_window_offsets_valid": (
            start_offset is not None and end_offset is not None
            and end_offset >= start_offset
            and end_offset - start_offset == actual["size_bytes"]
        ),
        "event_status_complete": metadata.get("status") == "ok"
        and metadata.get("complete") is True,
    }
    return checks, {"metadata": metadata, "actual": actual,
                    "line_count": event_data.get("line_count"),
                    "event_counts": event_data.get("counts")}


def _same_path(value: object, expected: Path) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return Path(value).expanduser().resolve() == expected.resolve()
    except OSError:
        return False


def _resume_binding_checks(
    source_artifact: Path,
    resume_artifact: Path | None,
    source_report: dict[str, Any],
    resume_report: dict[str, Any] | None,
    native_result: dict[str, Any],
    action: str,
    recipient: str,
    request_id: str,
    date_raw: int,
    session: str,
) -> tuple[dict[str, bool], dict[str, Any]]:
    if resume_artifact is None or resume_report is None:
        return {"resume_not_supplied": True}, {"supplied": False}
    expected_event = RESPONSE_EVENT if action == START_ACTION else EXECUTION_EVENT
    public = _public_result_from(resume_report, expected_event, action) or {}
    source_session = source_report.get("session")
    source_session_id = source_session.get("session_id") if isinstance(source_session, dict) else None
    resume_session = resume_report.get("session")
    resume_session_id = resume_session.get("session_id") if isinstance(resume_session, dict) else None
    referenced_source = resume_report.get("source_report")
    referenced_source_path = referenced_source.get("path") if isinstance(referenced_source, dict) else None
    resume_source_ref = resume_report.get("resume_artifact")
    result_checks = resume_report.get("result_checks")
    resume_public_record = result_checks.get("public_result") if isinstance(result_checks, dict) else None
    fields = (
        "event", "family", "action_id", "actor", "recipient", "phase",
        "request_id", "date_raw", "native_state", "native_variant", "outcome",
        "support_independence_before", "support_independence_after",
    )
    checks = {
        "resume_report_mode": resume_report.get("mode") == "resume_read_only",
        "resume_report_terminal": resume_report.get("status") == "passed",
        "resume_references_source": (
            _same_path(resume_source_ref, source_artifact)
            and _same_path(referenced_source_path, source_artifact)
        ),
        "resume_identity_matches_source": (
            resume_report.get("family") == source_report.get("family") == FAMILY
            and resume_report.get("actor") == source_report.get("actor") == ACTOR
            and resume_report.get("recipient") == recipient
            and resume_report.get("action_id") == action
            and resume_report.get("request_id") == request_id
            and resume_report.get("expected_date_raw") == date_raw
        ),
        "resume_session_matches_source": (
            isinstance(source_session_id, str)
            and resume_session_id == source_session_id == session
        ),
        "resume_public_result_present": bool(public),
        "resume_public_result_matches_native": (
            bool(public)
            and all(public.get(field) == native_result.get(field) for field in fields)
        ),
        "resume_public_record_matches_extracted": (
            isinstance(resume_public_record, dict)
            and resume_public_record == public
        ),
        "resume_result_checks_passed": (
            isinstance(result_checks, dict) and result_checks.get("all") is True
        ),
        "resume_persistence_stable": (
            isinstance(resume_report.get("persistence"), dict)
            and resume_report["persistence"].get("same_public_result") is True
        ),
    }
    return checks, {
        "supplied": True,
        "artifact": _record(resume_artifact / "report.json"),
        "public_result": public,
        "session_id": resume_session_id,
        "source_report": referenced_source,
        "result_checks": result_checks,
    }


def _positive_report(artifact: Path, resume_artifact: Path | None = None) -> dict[str, Any]:
    _configure_common()
    report_path = artifact / "report.json"
    event_path = _event_path(artifact)
    report = _bounded_json(report_path)
    resume_report = None
    if resume_artifact is not None:
        resume_report = _bounded_json(resume_artifact / "report.json")
    event_data = _stream(event_path)
    session = _session(report)
    action = str(report.get("action_id", ""))
    recipient = str(report.get("recipient", ""))
    request_id = str(report.get("request_id", ""))
    date_raw = as_int(report.get("expected_date_raw"))
    if action not in SUPPORTED_ACTIONS:
        raise ValueError(f"unsupported Support action: {action!r}")
    if date_raw is None or not request_id or not session:
        raise ValueError("source report lacks request_id/session/date_raw")

    metadata_checks, metadata_detail = _metadata_checks(
        artifact, event_path, report, event_data
    )
    selector_checks, selector_detail = _selector_checks(event_data, session, report)
    submissions = [value for value in _session_events(event_data, SUBMISSION_EVENT, session)
                   if value.get("request_id") == request_id
                   and value.get("action_id") == action
                   and value.get("actor") == ACTOR
                   and value.get("recipient") == recipient
                   and value.get("phase") == PHASE
                   and _strict_int(value.get("date_raw"), date_raw)]
    submission = submissions[0] if len(submissions) == 1 else {}
    submission_checks = {
        "one_matching_submission": len(submissions) == 1,
        "submission_bound_and_submitted": (
            submission.get("submitted") is True
            and submission.get("session_id") == session
            and _strict_int(submission.get("native_origin"), 0xFFFF)
            and _strict_int(submission.get("native_flags"), 0)
            and _strict_int(submission.get("native_sequence"))
        ),
    }
    request_sequence = as_int(submission.get("native_sequence"))
    if request_sequence is None:
        request_sequence = 0
    expected_outcome = report.get("expected_outcome")
    if action == START_ACTION and expected_outcome not in ("accepted", "rejected"):
        expected_outcome = None
    expected_response_state = (
        2 if expected_outcome == "accepted" else 1 if expected_outcome == "rejected" else None
    )
    entries = _session_events(event_data, ENTRY_EVENT, session)
    response_sequences = sorted({
        as_int(value.get("protocol_sequence")) for value in entries
        if as_int(value.get("protocol_sequence")) is not None
        and as_int(value.get("protocol_sequence")) > request_sequence
        and value.get("action_id") == action
        and value.get("actor_field") == ACTOR
        and value.get("recipient_field") == recipient
        and _strict_int(_payload(value.get("source")).get("state34"), expected_response_state)
        if expected_response_state is not None
    })
    result_checks, result_detail, result_event = _native_result(
        report, event_data, session, recipient, action, date_raw, request_id
    )
    if action == START_ACTION and expected_response_state is None:
        expected_response_state = as_int(result_event.get("native_state"))
        response_sequences = sorted({
            as_int(value.get("protocol_sequence")) for value in entries
            if as_int(value.get("protocol_sequence")) is not None
            and as_int(value.get("protocol_sequence")) > request_sequence
            and value.get("action_id") == action
            and value.get("actor_field") == ACTOR
            and value.get("recipient_field") == recipient
            and _strict_int(_payload(value.get("source")).get("state34"), expected_response_state)
        }) if expected_response_state is not None else []
    response_sequence = response_sequences[0] if len(response_sequences) == 1 else None
    request_variant = 1 if action == START_ACTION else 0
    request_checks, request_chain = _chain(
        event_data, session, request_sequence, variant=request_variant, state=0,
        actor=ACTOR, recipient=recipient, action=action, date_raw=date_raw,
    )
    if action == START_ACTION:
        response_checks, response_chain = _chain(
            event_data, session, response_sequence or -1, variant=1,
            state=expected_response_state or -1, actor=ACTOR,
            recipient=recipient, action=action, date_raw=date_raw,
            result_line=as_int(result_event.get("_line")),
        )
    else:
        response_checks, response_chain = {}, {}
    response_proof_checks = {
        "one_matching_response_protocol_sequence": (
            action != START_ACTION or response_sequence is not None
        ),
        "response_sequence_follows_request": (
            action != START_ACTION
            or (response_sequence is not None and response_sequence > request_sequence)
        ),
        "response_state_binds_native_result": (
            action != START_ACTION
            or (response_sequence is not None
                and as_int(result_event.get("native_state")) == expected_response_state
                and response_chain.get("state34") == expected_response_state)
        ),
        "response_is_native_subproof": (
            action != START_ACTION
            or (result_event.get("response_verified") is True
                and result_event.get("request_binding_verified") is True
                and bool(response_chain)
                and all(response_checks.values()))
        ),
    }
    report_checks = {
        "source_report_identity": (
            report.get("family") == FAMILY
            and report.get("actor") == ACTOR
            and report.get("recipient") == recipient
            and report.get("phase") == PHASE
            and report.get("mode") == "execute"
            and report.get("selector") in (None, SELECTOR)
        ),
        "source_report_submitted": report.get("checks", {}).get("submitted_true") is True
        or report.get("execution", {}).get("submitted") is True,
        "paused_date_identity": (
            report.get("before", {}).get("control", {}).get("player_slot") == 189
            and report.get("after", {}).get("control", {}).get("player_slot") == 189
            and report.get("before", {}).get("control", {}).get("paused_flag") == 1
            and report.get("after", {}).get("control", {}).get("paused_flag") == 1
            and report.get("before", {}).get("control", {}).get("date_raw") == date_raw
            and report.get("after", {}).get("control", {}).get("date_raw") == date_raw
        ),
        "four_snapshots_before_after": (
            report.get("before", {}).get("baseline", {}).get("four_snapshots_complete") is True
            and report.get("after", {}).get("baseline", {}).get("four_snapshots_complete") is True
        ),
    }
    relation_checks, relation_detail = _relation_snapshot_checks(
        report,
        result_detail.get("expected_before") is True,
        result_detail.get("expected_after") is True,
    )
    resume_checks, resume_detail = _resume_binding_checks(
        artifact, resume_artifact, report, resume_report, result_event,
        action, recipient, request_id, date_raw, session,
    )
    public_checks, public_detail = _public_checks(
        report, result_event, action, resume_report
    )
    native_checks: dict[str, bool] = {
        **report_checks,
        **metadata_checks,
        **selector_checks,
        **submission_checks,
        **request_checks,
        **response_checks,
        **response_proof_checks,
        **result_checks,
        **relation_checks,
        **resume_checks,
    }
    native_source_passed = all(native_checks.values())
    public_pending = public_detail["public_pending"]
    public_passed = all(public_checks.values())
    source_report_status = report.get("status")
    result_status = (
        "passed" if native_source_passed and public_passed else
        "pending" if native_source_passed and public_pending else
        "failed"
    )
    return {
        "status": result_status,
        "validation_passed": result_status == "passed",
        "native_source_passed": native_source_passed,
        "public_result_passed": public_passed,
        "public_result_pending": public_pending,
        "artifact": _record(report_path),
        "event_file": _record(event_path),
        "resume_artifact": resume_detail,
        "session_id": session,
        "action_id": action,
        "actor": report.get("actor"),
        "recipient": recipient,
        "request_id": request_id,
        "expected_outcome": result_detail.get("expected_outcome"),
        "native_result": result_detail,
        "request_chain": request_chain,
        "response_chain": response_chain if action == START_ACTION else None,
        "request_sequence": request_sequence,
        "response_sequence": response_sequence,
        "relation_snapshot": relation_detail,
        "selector": selector_detail,
        "public_consumer": public_detail,
        "metadata": metadata_detail,
        "checks": native_checks,
        "public_checks": public_checks,
        "failed_checks": [name for name, value in native_checks.items() if value is False],
        "source_report_status": source_report_status,
        "limitations": [
            "正向 Support 请求的 request_id 只出现在 submission/result；响应 protocol sequence 通过同一 session、双方、日期、family、payload 和指针链绑定。",
            "native NPC 响应以独立的 state1/state2 payload 子链和 verified/request_binding_verified 字段证明；不把 Python LLM 或 public pending 状态当作原生响应证据。",
            "本次 Support 是法国主动请求后的 NPC 响应，不是入站 pending 提议；因此 pending_removed=false 是预期的出站语义。",
        ],
    }


def _negative_report(artifact: Path) -> dict[str, Any]:
    _configure_common()
    report_path = artifact / "report.json"
    event_path = _event_path(artifact)
    report = _bounded_json(report_path)
    event_data = _stream(event_path)
    session = _session(report)
    dispatches = _session_events(event_data, AUTHORITY_EVENT, session)
    rejections = _session_events(event_data, REJECTION_EVENT, session)
    entries = _session_events(event_data, ENTRY_EVENT, session)
    submissions = _session_events(event_data, SUBMISSION_EVENT, session)
    responses = _session_events(event_data, RESPONSE_EVENT, session)
    executions = _session_events(event_data, EXECUTION_EVENT, session)
    dispatch = dispatches[0] if len(dispatches) == 1 else {}
    rejection = rejections[0] if len(rejections) == 1 else {}
    action = str(report.get("action_id") or dispatch.get("action_id") or START_ACTION)
    if action not in SUPPORTED_ACTIONS:
        action = START_ACTION
    expected_variant = 1 if action == START_ACTION else 0
    expected_route = "direct_entry" if action == START_ACTION else "transport"
    expected_dispatch_accepted = False if action == START_ACTION else True
    expected_reason = (
        "UNAUTHORIZED_FRA_SUPPORT_OFFER"
        if action == START_ACTION else "UNAUTHORIZED_FRA_SUPPORT_REVOKE"
    )
    actor = dispatch.get("actor", ACTOR)
    recipient = dispatch.get("recipient")
    entry_matches = [value for value in entries if (
        value.get("action_id") == action
        and value.get("actor_field") == actor
        and value.get("recipient_field") == recipient
        and _payload_matches(value.get("source"), variant=expected_variant, state=0,
                             actor=actor, recipient=recipient,
                             date_raw=as_int(value.get("source", {}).get("date28")) or 0)
    )]
    entry = entry_matches[0] if len(entry_matches) == 1 else {}
    entry_payload = _payload(entry.get("source"))
    checks = {
        "one_authority_dispatch": len(dispatches) == 1,
        "support_dispatch_identity": (
            dispatch.get("action_id") == action
            and dispatch.get("actor") == ACTOR
            and isinstance(dispatch.get("recipient"), str)
            and dispatch.get("phase") == PHASE
            and _strict_int(dispatch.get("state34"), 0)
            and _strict_int(dispatch.get("variant38"), expected_variant)
        ),
        "dispatch_route_expected": dispatch.get("dispatch_route") == expected_route,
        "dispatcher_authority_gate_expected": (
            dispatch.get("dispatcher_accepted") is expected_dispatch_accepted
        ),
        "no_authority_seed": dispatch.get("authority_seed_created") is False,
        "one_support_command_entry": len(entry_matches) == 1,
        "entry_family5_vtable_extra60": (
            common._payload_valid(entry.get("source"), expected_variant)
            and entry_payload.get("family") == FAMILY
            and _strict_int(entry_payload.get("vtable_rva"), VTABLE_RVA)
            and _strict_int(entry_payload.get("extra60"), EXPECTED_EXTRA60)
            and _strict_int(entry_payload.get("state34"), 0)
            and _strict_int(entry_payload.get("variant38"), expected_variant)
        ),
        "one_native_rejection": len(rejections) == 1,
        "rejection_reason_unauthorized_support": (
            rejection.get("reason") == expected_reason
        ),
        "rejection_not_submitted": rejection.get("submitted") is False,
        "no_authorized_submission": not [value for value in submissions
                                          if value.get("action_id") == action],
        "no_native_relation_response": not [value for value in responses
                                             if value.get("action_id") == action],
        "no_native_relation_execution": not [value for value in executions
                                              if value.get("action_id") == action],
        "native_ai_self_choice_false": report.get("native_ai_self_choice_evidence") is False,
        "relation_unchanged": report.get("checks", {}).get("support_relationship_unchanged") is True
        and report.get("checks", {}).get("relation_visibility_unchanged") is True,
        "diplomat_and_pause_unchanged": (
            report.get("checks", {}).get("diplomat_availability_unchanged") is True
            and report.get("checks", {}).get("diplomat_tasks_unchanged") is True
            and report.get("checks", {}).get("por_paused_same_date") is True
        ),
    }
    passed = all(checks.values())
    return {
        "status": "passed" if passed else "failed",
        "validation_passed": passed,
        "artifact": _record(report_path),
        "event_file": _record(event_path),
        "session_id": session,
        "action_id": action,
        "dispatch": {key: dispatch.get(key) for key in (
            "_line", "action_id", "actor", "recipient", "phase",
            "dispatch_route", "dispatcher_accepted", "authority_seed_created",
            "state34", "variant38")},
        "rejection": {key: rejection.get(key) for key in (
            "_line", "reason", "submitted", "request_id", "action_id")},
        "authorized_result_counts": {
            "support_submissions": len([value for value in submissions
                                         if value.get("action_id") == START_ACTION]),
            "support_responses": len([value for value in responses
                                       if value.get("action_id") == START_ACTION]),
            "revoke_executions": len([value for value in executions
                                       if value.get("action_id") == STOP_ACTION]),
        },
        "checks": checks,
        "failed_checks": [name for name, value in checks.items() if value is False],
    }


def build_report(
    artifact: Path,
    negative_artifacts: list[Path] | None = None,
    resume_artifact: Path | None = None,
) -> dict[str, Any]:
    artifact = artifact.resolve(strict=True)
    if not artifact.is_dir():
        raise ValueError(f"artifact is not a directory: {artifact}")
    if resume_artifact is not None:
        resume_artifact = resume_artifact.resolve(strict=True)
        if not resume_artifact.is_dir():
            raise ValueError(f"resume artifact is not a directory: {resume_artifact}")
    positive = _positive_report(artifact, resume_artifact)
    negatives = [_negative_report(path.resolve(strict=True))
                 for path in (negative_artifacts or [])]
    negative_passed = all(value.get("validation_passed") is True for value in negatives)
    if positive["native_source_passed"] and positive["public_result_passed"] and negative_passed:
        status = "passed"
    elif positive["native_source_passed"] and positive["public_result_pending"] and negative_passed:
        status = "pending"
    else:
        status = "failed"
    result = {
        "schema_version": 1,
        "validator": "work/validate_support_independence_source.py",
        "status": status,
        "validation_passed": status == "passed",
        "native_source_passed": positive["native_source_passed"],
        "public_result_passed": positive["public_result_passed"],
        "public_result_pending": positive["public_result_pending"],
        "positive": positive,
        "negative": negatives,
        "family": FAMILY,
        "selector": SELECTOR,
        "vtable_rva": hex(VTABLE_RVA),
        "limitations": positive["limitations"],
    }
    if negatives:
        result["negative_validation_passed"] = negative_passed
    return result


def _failed(checks: dict[str, Any]) -> list[str]:
    return [name for name, value in checks.items() if value is False]


def _chain_line(chain: Any) -> str:
    if not isinstance(chain, dict):
        return "未建立"
    return (
        f"entry={chain.get('entry_line')}，transport={chain.get('transport_line')}，"
        f"clone={chain.get('clone_line')}，creator={chain.get('creator_command_line')}，"
        f"sequence={chain.get('sequence')}，state34={chain.get('state34')}"
    )


def markdown_report(value: dict[str, Any]) -> str:
    positive = value.get("positive", {})
    native = positive.get("native_result", {})
    event = native.get("event", {}) if isinstance(native, dict) else {}
    lines = [
        "# Support Independence 原生来源链验证",
        "",
        f"总体状态：**{str(value.get('status', 'failed')).upper()}**。",
        "",
        f"原生来源链：**{'通过' if value.get('native_source_passed') else '失败'}**；"
        f"public 消费端：**{'通过' if value.get('public_result_passed') else '待修正/失败'}**。",
        f"family=`{FAMILY}`，selector=`0x{SELECTOR:x}`，vtable=`{hex(VTABLE_RVA)}`。",
        f"请求：`{positive.get('request_id')}`，`{positive.get('actor')} -> {positive.get('recipient')}`，"
        f"action=`{positive.get('action_id')}`，expected=`{positive.get('expected_outcome')}`。",
        "",
        "## 原生来源和 NPC 响应",
        "",
        "正向链路按同一 session、双方、date、family、extra60、协议序号和指针关系绑定。"
        "请求链证明创建、transport source/load、wrapper clone 和 command entry；"
        "Support 请求动作之后的另一条 state1/state2 子链证明原生 NPC 响应。",
        f"请求链：{_chain_line(positive.get('request_chain'))}。",
        f"响应链：{_chain_line(positive.get('response_chain'))}。",
        f"原生结果：event=`{event.get('event')}`，native_state=`{event.get('native_state')}`，"
        f"native_variant=`{event.get('native_variant')}`，outcome=`{event.get('outcome')}`，"
        f"support=`{event.get('support_independence_before')}` -> `"
        f"{event.get('support_independence_after')}`，pending_removed=`{event.get('pending_removed')}`。",
        "",
        "## Public 结果边界",
        "",
        f"原始执行报告 status=`{positive.get('source_report_status')}`；"
        f"public_result_pending=`{positive.get('public_result_pending')}`。",
        "native response 的 state 和 relation 字段来自独立原生事件及其 response payload 子链。"
        "当前消费端若仍处于 pending，本报告保留该缺口，不把整体状态标记为 passed。",
        "",
        "## 未授权负例",
        "",
    ]
    negatives = value.get("negative", [])
    if isinstance(negatives, list) and negatives:
        for index, negative in enumerate(negatives, 1):
            lines.extend([
                f"负例 {index}：`{negative.get('status')}`；"
                f"失败检查：{', '.join(negative.get('failed_checks', [])) or '无'}。",
                f"route=`{negative.get('dispatch', {}).get('dispatch_route')}`；"
                f"reason=`{negative.get('rejection', {}).get('reason')}`；"
                f"authorized result counts=`{negative.get('authorized_result_counts')}`。",
                "",
            ])
    else:
        lines.append("未提供 negative artifact。")
        lines.append("")
    lines.extend([
        "## 检查结果",
        "",
        f"native 失败检查：{', '.join(positive.get('failed_checks', [])) or '无'}。",
        "",
        "| 检查 | 结果 |",
        "|---|---|",
    ])
    for name, result in positive.get("checks", {}).items():
        lines.append(f"| `{name}` | {'通过' if result else '失败'} |")
    lines.extend([
        "",
        "输入文件使用有界流式读取并记录 SHA-256；原始 artifact 未被覆盖。",
        "",
    ])
    return "\n".join(lines)


def _fresh_output_dir(artifact: Path) -> Path:
    return artifact.parent / f"support-independence-source-validation-{uuid.uuid4().hex}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path,
                        help="positive Support execution artifact")
    parser.add_argument("--negative-artifact", action="append", type=Path,
                        help="unauthorized authority-test artifact; repeatable")
    parser.add_argument("--resume-artifact", type=Path,
                        help="read-only terminal resume artifact for the same request")
    parser.add_argument("--output-dir", type=Path,
                        help="fresh evidence directory; defaults to a new sibling")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        artifact = args.artifact.expanduser().resolve(strict=True)
        negatives = [path.expanduser().resolve(strict=True)
                     for path in (args.negative_artifact or [])]
        resume_artifact = (
            args.resume_artifact.expanduser().resolve(strict=True)
            if args.resume_artifact else None
        )
        output_dir = (
            args.output_dir.expanduser().resolve()
            if args.output_dir else _fresh_output_dir(artifact)
        )
        if output_dir == artifact or output_dir in negatives or output_dir == resume_artifact:
            raise ValueError("output directory must be separate from source artifacts")
        output_dir.mkdir(parents=True, exist_ok=False)
        value = build_report(artifact, negatives, resume_artifact)
        (output_dir / "validation.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output_dir / "report.md").write_text(markdown_report(value), encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as error:
        print(f"validation failed to run: {error}", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": value["status"],
        "validation_passed": value["validation_passed"],
        "native_source_passed": value["native_source_passed"],
        "public_result_passed": value["public_result_passed"],
        "public_result_pending": value["public_result_pending"],
        "output_dir": str(output_dir),
        "validation": str(output_dir / "validation.json"),
        "report": str(output_dir / "report.md"),
    }, ensure_ascii=False))
    return 0 if value["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
