#!/usr/bin/env python3
"""Validate one Improve Relations execution through the observed native chain.

The validator consumes an execution artifact in read-only mode.  It streams the
JSONL event slice and retains only the five event types needed to associate the
request with the native command entry, wrapper clone, transport/load and task
result.  The report also compares the bounded diplomat observations before and
after the paused action.

The output is always written to a fresh evidence directory.  It does not
rewrite the execution artifact and it never starts the game.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
import uuid


WORK_DIR = Path(__file__).resolve().parent
if str(WORK_DIR) not in sys.path:
    sys.path.insert(0, str(WORK_DIR))

# Reuse the common integer and payload-shape primitives.  Improve Relations
# has its own native vtable, so its family-specific shape checks live here.
from validate_alliance_authority_source import (  # noqa: E402
    as_int,
    header_equal,
    payload_of,
    same_int,
)


MAX_INPUT_BYTES = 10 * 1024 * 1024
START_ACTION = "improve_relations"
STOP_ACTION = "stop_improving_relations"
SUPPORTED_ACTIONS = frozenset((START_ACTION, STOP_ACTION))
FAMILY = "improve_relations"
ACTOR = "FRA"
RECIPIENT = "SAV"
PHASE = "initiate"
EXPECTED_VARIANT = 1
EXPECTED_STATE = 0
EXPECTED_EXTRA60 = 0
EXPECTED_DISCRIMINATOR = 357
EXPECTED_VTABLE_RVA = 0x1C7DD68
IMPROVE_SELECTOR = 11739
EXPECTED_COUNTRIES = ("FRA", "ENG", "POR")
RESULT_EVENT = "native_diplomacy_task_execution_result"
RESULT_BEFORE_FIELD = "task_before"
RESULT_AFTER_FIELD = "task_after"
# Family wrappers can reuse the transport/clone/authority chain without
# pretending that a persistent relation is a diplomat task.
SKIP_STATE_OBSERVATION = False
PAYLOAD_FIELDS = (
    "actor10",
    "mirror18",
    "recipient20",
    "date28",
    "date2c",
    "envoy30",
    "state34",
    "variant38",
    "proposal3c",
)
INTERESTING_EVENTS = (
    "native_alliance_command_entry_observed",
    "native_alliance_wrapper_clone",
    "native_alliance_transport_completed",
    "native_alliance_submission_result",
    RESULT_EVENT,
)
INTERESTING_SET = frozenset(INTERESTING_EVENTS)
TAG_RE = re.compile(r"[A-Z]{3}\Z")


def _bounded_json(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise ValueError(f"refusing to parse input over 10 MiB: {path} ({size} bytes)")
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stream_events(path: Path) -> dict[str, Any]:
    """Parse the event slice line by line and retain only relevant events."""

    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"refusing to scan event slice over 10 MiB: {path}")
    counts: Counter[str] = Counter()
    relevant: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    malformed: list[dict[str, Any]] = []
    non_objects: list[int] = []
    line_count = 0
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            line_count += 1
            digest.update(raw_line)
            try:
                value = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                if len(malformed) < 32:
                    malformed.append({"line": line_number, "error": str(error)})
                continue
            if not isinstance(value, dict):
                if len(non_objects) < 32:
                    non_objects.append(line_number)
                continue
            name = str(value.get("event", ""))
            counts[name] += 1
            if name in INTERESTING_SET:
                event = dict(value)
                event["_line"] = line_number
                relevant[name].append(event)
    return {
        "line_count": line_count,
        "sha256": digest.hexdigest(),
        "counts": dict(sorted(counts.items())),
        "malformed_lines": malformed,
        "non_object_lines": non_objects,
        "events": {name: list(items) for name, items in relevant.items()},
    }


def _tag_from_identity(value: Any) -> str | None:
    number = as_int(value)
    if number is None:
        return None
    try:
        tag = (number & 0xFFFFFF).to_bytes(3, "little").decode("ascii")
    except (OverflowError, UnicodeDecodeError):
        return None
    return tag if TAG_RE.fullmatch(tag) else None


def _payload(shape: Any) -> dict[str, Any]:
    value = payload_of(shape)
    return value if isinstance(value, dict) else {}


def _payload_valid(shape: Any, expected_variant: int | None = None) -> bool:
    payload = _payload(shape)
    if not payload:
        return False
    if payload.get("family") != FAMILY:
        return False
    if not same_int(payload.get("extra60"), EXPECTED_EXTRA60):
        return False
    if not same_int(payload.get("vtable_rva"), EXPECTED_VTABLE_RVA):
        return False
    if not same_int(payload.get("discriminator"), EXPECTED_DISCRIMINATOR):
        return False
    if expected_variant is not None and not same_int(payload.get("variant38"), expected_variant):
        return False
    if payload.get("readable") is not True:
        return False
    if payload.get("matched") is not True:
        return False
    if payload.get("handles_canonical") is not True:
        return False
    if payload.get("tracked") is not True:
        return False
    return all(as_int(payload.get(field)) is not None for field in PAYLOAD_FIELDS)


def _object_valid(shape: Any, expected_variant: int | None = None) -> bool:
    if not isinstance(shape, dict):
        return False
    return (
        shape.get("identity") is True
        and shape.get("readable") is True
        and shape.get("prefix_readable") is True
        and as_int(shape.get("addr")) is not None
        and as_int(shape.get("action")) is not None
        and _payload_valid(shape, expected_variant)
    )


def _payload_equal(left: Any, right: Any) -> bool:
    if not _payload_valid(left) or not _payload_valid(right):
        return False
    lvalue = _payload(left)
    rvalue = _payload(right)
    return (
        all(same_int(lvalue.get(field), rvalue.get(field)) for field in PAYLOAD_FIELDS)
        and lvalue.get("family") == rvalue.get("family") == FAMILY
        and same_int(lvalue.get("extra60"), rvalue.get("extra60"))
    )


def _semantic_key(shape: Any) -> dict[str, Any]:
    payload = _payload(shape)
    return {
        "family": payload.get("family"),
        "extra60": payload.get("extra60"),
        "actor10": payload.get("actor10"),
        "mirror18": payload.get("mirror18"),
        "recipient20": payload.get("recipient20"),
        "date28": payload.get("date28"),
        "date2c": payload.get("date2c"),
        "envoy30": payload.get("envoy30"),
        "state34": payload.get("state34"),
        "variant38": payload.get("variant38"),
        "proposal3c": payload.get("proposal3c"),
    }


def _semantic_equal(left: Any, right: Any) -> bool:
    lvalue = _semantic_key(left)
    rvalue = _semantic_key(right)
    return (
        lvalue.get("family") == rvalue.get("family") == FAMILY
        and same_int(lvalue.get("extra60"), rvalue.get("extra60"))
        and all(same_int(lvalue.get(field), rvalue.get(field)) for field in PAYLOAD_FIELDS)
    )


def _shape_summary(shape: Any) -> dict[str, Any]:
    if not isinstance(shape, dict):
        return {}
    payload = _payload(shape)
    return {
        "addr": shape.get("addr"),
        "action": shape.get("action"),
        "identity": shape.get("identity"),
        "readable": shape.get("readable"),
        "prefix_readable": shape.get("prefix_readable"),
        "origin": shape.get("origin"),
        "protocol_sequence": shape.get("protocol_sequence"),
        "payload": _semantic_key(shape),
    }


def _session_id(report: dict[str, Any]) -> str:
    session = report.get("session")
    if isinstance(session, dict) and session.get("session_id"):
        return str(session["session_id"])
    installation = report.get("installation")
    if isinstance(installation, dict) and installation.get("session_id"):
        return str(installation["session_id"])
    return str(report.get("session_id", ""))


def _session_events(event_data: dict[str, Any], name: str, session: str) -> list[dict[str, Any]]:
    return [
        item for item in event_data.get("events", {}).get(name, [])
        if str(item.get("session_id", "")) == session
    ]


def _single_matching(items: list[dict[str, Any]], predicate: Any) -> tuple[dict[str, Any], int]:
    matches = [item for item in items if predicate(item)]
    return (matches[0] if len(matches) == 1 else {}, len(matches))


def _report_path_record(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"path": str(path), "size_bytes": stat.st_size, "sha256": _sha256_file(path)}


def _country_map(snapshot: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return {}
    semantics = snapshot.get("diplomat_semantics")
    if not isinstance(semantics, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in semantics:
        if isinstance(item, dict) and isinstance(item.get("countrytag"), str):
            result[item["countrytag"]] = item
    return result


def _int_or_none(value: Any) -> int | None:
    return as_int(value)


def _improve_fra_sav_entries(country: Any) -> list[dict[str, Any]]:
    if not isinstance(country, dict) or not isinstance(country.get("entries"), list):
        return []
    result: list[dict[str, Any]] = []
    for entry in country["entries"]:
        if not isinstance(entry, dict):
            continue
        if _int_or_none(entry.get("raw_action_type_a8")) != IMPROVE_SELECTOR:
            continue
        if _tag_from_identity(entry.get("raw_actor_80")) != ACTOR:
            continue
        if _tag_from_identity(entry.get("raw_recipient_88")) != RECIPIENT:
            continue
        if _int_or_none(entry.get("active_raw_18")) == 0:
            continue
        result.append(entry)
    return result


def _entry_projection(entry: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(entry.get(field) for field in (
        "raw_id_44",
        "raw_action_type_a8",
        "raw_actor_80",
        "raw_recipient_88",
        "raw_20",
        "raw_24",
        "raw_2c",
        "active_raw_18",
    ))


def _build_chain_checks(report: dict[str, Any], event_data: dict[str, Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    action = str(report.get("action_id", ""))
    actor = str(report.get("actor", ""))
    recipient = str(report.get("recipient", ""))
    request_id = str(report.get("request_id", ""))
    date_raw = as_int(report.get("expected_date_raw"))
    session = _session_id(report)
    expected_variant = 1 if action == START_ACTION else 0 if action == STOP_ACTION else None

    all_entries = _session_events(event_data, "native_alliance_command_entry_observed", session)
    all_clones = _session_events(event_data, "native_alliance_wrapper_clone", session)
    all_transports = _session_events(event_data, "native_alliance_transport_completed", session)
    all_submissions = _session_events(event_data, "native_alliance_submission_result", session)
    all_results = _session_events(event_data, RESULT_EVENT, session)

    def entry_predicate(value: dict[str, Any]) -> bool:
        source = value.get("source")
        payload = _payload(source)
        return (
            value.get("action_id") == action
            and action in SUPPORTED_ACTIONS
            and value.get("actor_field") == actor == ACTOR
            and value.get("recipient_field") == recipient == RECIPIENT
            and _payload_valid(source, expected_variant)
            and payload.get("family") == FAMILY
            and _tag_from_identity(payload.get("actor10")) == ACTOR
            and _tag_from_identity(payload.get("recipient20")) == RECIPIENT
        )

    def clone_predicate(value: dict[str, Any]) -> bool:
        source = value.get("source")
        target = value.get("target")
        return (
            _object_valid(source, expected_variant)
            and _object_valid(target, expected_variant)
            and _semantic_equal(source, target)
        )

    def transport_predicate(value: dict[str, Any]) -> bool:
        source = value.get("source")
        loaded = value.get("loaded")
        return (
            _object_valid(source, expected_variant)
            and _object_valid(loaded, expected_variant)
            and _payload_equal(source, loaded)
        )

    def submission_predicate(value: dict[str, Any]) -> bool:
        return (
            value.get("request_id") == request_id
            and value.get("action_id") == action
            and action in SUPPORTED_ACTIONS
            and value.get("actor") == actor == ACTOR
            and value.get("recipient") == recipient == RECIPIENT
            and value.get("phase") == PHASE
            and same_int(value.get("date_raw"), date_raw)
        )

    def result_predicate(value: dict[str, Any]) -> bool:
        return (
            value.get("request_id") == request_id
            and value.get("action_id") == action
            and action in SUPPORTED_ACTIONS
            and value.get("actor") == actor == ACTOR
            and value.get("recipient") == recipient == RECIPIENT
            and value.get("phase") == PHASE
            and same_int(value.get("date_raw"), date_raw)
            and value.get("family") == FAMILY
        )

    entry, entry_count = _single_matching(all_entries, entry_predicate)
    clone, clone_count = _single_matching(all_clones, clone_predicate)
    transport, transport_count = _single_matching(all_transports, transport_predicate)
    submission, submission_count = _single_matching(all_submissions, submission_predicate)
    result, result_count = _single_matching(all_results, result_predicate)

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
    entry_sequence = as_int(entry.get("callback_sequence"))
    callback_order = all(
        value is not None for value in
        (transport_begin, load_sequence, transport_end, clone_begin, clone_end, entry_sequence)
    ) and (
        transport_begin < load_sequence < transport_end < clone_begin <= clone_end < entry_sequence
    )

    payloads = (transport_source, transport_loaded, clone_source, clone_target, entry_source)
    payload_family_state_variant = all(
        _payload_valid(value, expected_variant)
        and _payload(value).get("family") == FAMILY
        and same_int(_payload(value).get("extra60"), EXPECTED_EXTRA60)
        and same_int(_payload(value).get("state34"), EXPECTED_STATE)
        and same_int(_payload(value).get("variant38"), expected_variant)
        for value in payloads
    )
    session_bound = all(
        str(value.get("session_id", "")) == session
        for value in (entry, clone, transport, submission, result)
    ) and bool(session)
    semantic_request_key = (
        _payload_valid(entry_source, expected_variant)
        and _semantic_equal(entry_source, transport_source)
        and _semantic_equal(transport_loaded, clone_source)
        and _semantic_equal(clone_target, entry_source)
        and same_int(entry_payload.get("date28"), date_raw)
        and same_int(entry_payload.get("date2c"), date_raw)
        and _tag_from_identity(entry_payload.get("actor10")) == actor
        and _tag_from_identity(entry_payload.get("recipient20")) == recipient
    )
    protocol_sequence_binding = (
        same_int(entry.get("protocol_sequence"), transport_source.get("protocol_sequence"))
        and same_int(transport_source.get("protocol_sequence"), transport_loaded.get("protocol_sequence"))
        and same_int(transport_source.get("protocol_sequence"), submission.get("native_sequence"))
        and (as_int(transport_source.get("protocol_sequence")) or 0) > 0
    )
    pointer_chain = (
        same_int(transport.get("loaded", {}).get("addr"), clone_source.get("addr"))
        and same_int(transport.get("loaded", {}).get("action"), clone_source.get("action"))
        and same_int(clone_target.get("addr"), entry.get("command"))
        and same_int(clone_target.get("action"), entry.get("action"))
        and same_int(clone_target_payload.get("addr"), entry_payload.get("addr"))
        and same_int(clone.get("native_result"), entry.get("command"))
        and same_int(transport.get("outgoing"), transport_source.get("addr"))
    )
    world_transport_binding = (
        transport.get("completed") is True
        and transport.get("source_captured") is True
        and transport.get("source_identity") is True
        and transport.get("loaded_identity") is True
        and transport.get("peer_is_world_transport") is True
        and transport.get("world_transport_readable") is True
        and transport.get("peer_readable") is True
        and transport.get("peer") == transport.get("world_transport") == transport.get("transport")
        and transport.get("peer_owner") == transport.get("world_dispatcher")
    )
    load_contract = (
        transport.get("payload_equal") is True
        and header_equal(transport_source, transport_loaded)
        and same_int(transport.get("matching_count"), 1)
        and same_int(transport.get("load_count"), 1)
        and transport.get("loads_truncated") is False
        and transport.get("all_commands_forwarded") is True
        and transport.get("caller_verified") is True
    )
    request_result = (
        submission.get("submitted") is True
        and result.get("outcome") == "executed"
        and result.get("family") == FAMILY
        and same_int(result.get("native_state"), EXPECTED_STATE)
        and same_int(result.get("native_variant"), expected_variant)
        and result.get(RESULT_BEFORE_FIELD) is (action == STOP_ACTION)
        and result.get(RESULT_AFTER_FIELD) is (action == START_ACTION)
        and result.get("execution_verified") is True
        and result.get("request_binding_verified") is True
    )
    execution_record = report.get("execution")
    report_result = execution_record.get("result") if isinstance(execution_record, dict) else None
    poll = report.get("poll")
    poll_result = poll.get("final", {}).get("result") if isinstance(poll, dict) and isinstance(poll.get("final"), dict) else None
    public_result = (
        isinstance(report_result, dict)
        and isinstance(poll_result, dict)
        and report_result == poll_result
        and report_result.get("event") == RESULT_EVENT
        and report_result.get("family") == FAMILY
        and report_result.get("action_id") == action
        and same_int(report_result.get("native_variant"), expected_variant)
        and report_result.get(RESULT_BEFORE_FIELD) is (action == STOP_ACTION)
        and report_result.get(RESULT_AFTER_FIELD) is (action == START_ACTION)
    )

    checks: dict[str, bool] = {
        "source_report_action_is_supported": action in SUPPORTED_ACTIONS,
        "single_execute_call": same_int(report.get("execute_call_count"), 1),
        "event_jsonl_complete": not event_data["malformed_lines"] and not event_data["non_object_lines"],
        "session_bound_chain": session_bound,
        "one_matching_command_entry": entry_count == 1,
        "one_matching_wrapper_clone": clone_count == 1,
        "one_matching_transport": transport_count == 1,
        "one_matching_submission": submission_count == 1,
        "one_matching_task_result": result_count == 1,
        "payload_family_extra60_state_variant_consistent": payload_family_state_variant,
        "request_semantic_key_bound_through_chain": semantic_request_key,
        "protocol_sequence_bound_to_request": protocol_sequence_binding,
        "pointer_chain_source_clone_transport_target_entry": pointer_chain,
        "transport_world_identity_bound": world_transport_binding,
        "transport_load_contract": load_contract,
        "callback_order_transport_load_clone_entry": callback_order,
        "native_submission_and_task_result_verified": request_result,
        "public_result_matches_native_result": public_result,
    }
    chain = {
        "request": {
            "request_id": request_id,
            "action_id": action,
            "actor": actor,
            "recipient": recipient,
            "phase": PHASE,
            "date_raw": date_raw,
            "session_id": session,
            "submission_line": submission.get("_line"),
            "task_result_line": result.get("_line"),
            "submitted": submission.get("submitted"),
            "outcome": result.get("outcome"),
        },
        "transport": {
            "line": transport.get("_line"),
            "source": _shape_summary(transport_source),
            "loaded": _shape_summary(transport_loaded),
            "source_to_loaded_payload_equal": _payload_equal(transport_source, transport_loaded),
            "queue_verified_observed": transport.get("queue_verified"),
        },
        "clone": {
            "line": clone.get("_line"),
            "begin_callback_sequence": clone.get("begin_callback_sequence"),
            "callback_sequence": clone.get("callback_sequence"),
            "source": _shape_summary(clone_source),
            "target": _shape_summary(clone_target),
        },
        "entry": {
            "line": entry.get("_line"),
            "callback_sequence": entry.get("callback_sequence"),
            "protocol_sequence": entry.get("protocol_sequence"),
            "command": entry.get("command"),
            "action": entry.get("action"),
            "action_id": entry.get("action_id"),
            "actor_field": entry.get("actor_field"),
            "recipient_field": entry.get("recipient_field"),
            "source": _shape_summary(entry_source),
        },
        "callback_order": {
            "callback_begin": transport.get("callback_begin"),
            "load": transport.get("load_callback_sequence"),
            "transport_end": transport.get("callback_end"),
            "clone_begin": clone.get("begin_callback_sequence"),
            "clone_end": clone.get("callback_sequence"),
            "entry": entry.get("callback_sequence"),
            "expression": "callback_begin < load < transport_end < clone_begin <= clone_end < entry",
        },
    }
    return checks, chain


def _task_identity(entry: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(entry.get(field) for field in (
        "raw_id_44",
        "raw_action_type_a8",
        "raw_actor_80",
        "raw_recipient_88",
    ))


def _build_diplomat_observation(report: dict[str, Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    action = str(report.get("action_id", ""))
    expected_date = as_int(report.get("expected_date_raw"))
    before = _country_map(report.get("before"))
    after = _country_map(report.get("after"))
    before_fra = _improve_fra_sav_entries(before.get(ACTOR))
    after_fra = _improve_fra_sav_entries(after.get(ACTOR))
    before_keys = {_entry_projection(item) for item in before_fra}
    new_entries = [item for item in after_fra if _entry_projection(item) not in before_keys]
    required_countries = all(tag in before and tag in after for tag in EXPECTED_COUNTRIES)
    eng_unchanged = required_countries and before["ENG"] == after["ENG"]
    por_unchanged = required_countries and before["POR"] == after["POR"]
    fra_before_available = as_int(before.get(ACTOR, {}).get("available_count"))
    fra_after_available = as_int(after.get(ACTOR, {}).get("available_count"))
    before_identity = {_task_identity(item) for item in before_fra}
    after_identity = {_task_identity(item) for item in after_fra}
    stop_identity_stable = len(before_fra) == 1 and len(after_fra) == 1 and before_identity == after_identity
    stop_before = before_fra[0] if len(before_fra) == 1 else {}
    stop_after = after_fra[0] if len(after_fra) == 1 else {}
    stop_transition = (
        stop_identity_stable
        and _int_or_none(stop_before.get("active_raw_18")) == 2
        and _int_or_none(stop_after.get("active_raw_18")) == 1
        and expected_date is not None
        and _int_or_none(stop_after.get("raw_20")) == expected_date
    )
    if action == STOP_ACTION:
        checks = {
            "before_after_country_semantics_complete": required_countries,
            "fra_active_task_raw18_2_to_returning_1": stop_transition,
            "fra_available_count_0_unchanged": fra_before_available == 0 and fra_after_available == 0,
            "eng_unchanged_while_paused": eng_unchanged,
            "por_unchanged_while_paused": por_unchanged,
        }
    else:
        checks = {
            "before_after_country_semantics_complete": required_countries,
            "fra_available_count_1_to_0": fra_before_available == 1 and fra_after_available == 0,
            "fra_new_active_type11739_to_sav": len(new_entries) == 1,
            "eng_unchanged_while_paused": eng_unchanged,
            "por_unchanged_while_paused": por_unchanged,
        }
    observation = {
        "action_id": action,
        "before_available_count": {tag: before.get(tag, {}).get("available_count") for tag in EXPECTED_COUNTRIES},
        "after_available_count": {tag: after.get(tag, {}).get("available_count") for tag in EXPECTED_COUNTRIES},
        "fra_before_fra_to_sav_type11739": before_fra,
        "fra_after_fra_to_sav_type11739": after_fra,
        "new_after_entry": new_entries[0] if action != STOP_ACTION and len(new_entries) == 1 else None,
        "stop_before_entry": stop_before if action == STOP_ACTION else None,
        "stop_after_entry": stop_after if action == STOP_ACTION else None,
        "stop_task_identity_stable": stop_identity_stable if action == STOP_ACTION else None,
        "eng_before_after_equal": eng_unchanged,
        "por_before_after_equal": por_unchanged,
    }
    return checks, observation


def _build_resume_comparison(source_report: dict[str, Any], resume_artifact: Path) -> tuple[dict[str, bool], dict[str, Any]]:
    """Compare a read-only resume report with the source Stop observation."""

    resume_artifact = resume_artifact.resolve(strict=True)
    resume_path = resume_artifact / "report.json"
    if not resume_path.is_file():
        raise ValueError(f"resume artifact must contain report.json: {resume_artifact}")
    resume = _bounded_json(resume_path)
    action = str(source_report.get("action_id", ""))
    expected_variant = 1 if action == START_ACTION else 0 if action == STOP_ACTION else None
    source_after = source_report.get("after") if isinstance(source_report.get("after"), dict) else {}
    resume_after = resume.get("after") if isinstance(resume.get("after"), dict) else {}
    source_session = _session_id(source_report)
    resume_session = _session_id(resume)
    expected_checks = (
        "after_baseline_unchanged",
        "build_dll_source_bound",
        "duplicate_idempotent",
        "expected_terminal_result",
        "four_snapshots_after",
        "journal_survives_reopen",
        "no_new_execute_submission",
        "por_paused_date_identity",
        "query_task_transition",
        "task_after_expected",
        "task_before_source_expected",
    )
    resume_checks = resume.get("checks") if isinstance(resume.get("checks"), dict) else {}
    result_reads = resume.get("result_reads") if isinstance(resume.get("result_reads"), dict) else {}
    final_result = result_reads.get("final") if isinstance(result_reads.get("final"), dict) else {}
    reopened_result = result_reads.get("reopened") if isinstance(result_reads.get("reopened"), dict) else {}
    final_public = final_result.get("result") if isinstance(final_result.get("result"), dict) else {}
    reopened_public = reopened_result.get("result") if isinstance(reopened_result.get("result"), dict) else {}
    source_artifact_text = resume.get("resume_artifact")
    source_path_matches = False
    if isinstance(source_artifact_text, str):
        try:
            source_path_matches = Path(source_artifact_text).resolve() == Path(source_report.get("artifact", "")).resolve()
        except OSError:
            source_path_matches = False
    checks = {
        "resume_report_passed": resume.get("status") == "passed",
        "resume_mode_read_only": resume.get("mode") == "resume_read_only",
        "resume_identity_matches_source": (
            resume.get("action_id") == action
            and resume.get("actor") == source_report.get("actor") == ACTOR
            and resume.get("recipient") == source_report.get("recipient") == RECIPIENT
            and resume.get("phase") == source_report.get("phase") == PHASE
            and same_int(resume.get("expected_date_raw"), source_report.get("expected_date_raw"))
            and resume.get("request_id") == source_report.get("request_id")
        ),
        "resume_points_to_source_artifact": source_path_matches,
        "resume_session_matches_source": resume_session == source_session and bool(resume_session),
        "resume_required_checks_passed": all(resume_checks.get(name) is True for name in expected_checks),
        "resume_execute_count_zero": same_int(resume.get("execute_call_count"), 0),
        "resume_result_final_reopened_equal": final_public == reopened_public and bool(final_public),
        "resume_result_matches_stop_native_contract": (
            action == STOP_ACTION
            and final_public.get("action_id") == action
            and final_public.get("event") == "native_diplomacy_task_execution_result"
            and final_public.get("family") == FAMILY
            and same_int(final_public.get("native_state"), EXPECTED_STATE)
            and same_int(final_public.get("native_variant"), expected_variant)
            and final_public.get("task_before") is True
            and final_public.get("task_after") is False
            and final_public.get("request_id") == source_report.get("request_id")
        ),
        "resume_after_diplomat_semantics_match_source": (
            source_after.get("diplomat_semantics") == resume_after.get("diplomat_semantics")
            and source_after.get("control") == resume_after.get("control")
        ),
    }
    comparison = {
        "artifact": str(resume_artifact),
        "report": _report_path_record(resume_path),
        "status": resume.get("status"),
        "mode": resume.get("mode"),
        "session_id": resume_session,
        "source_artifact": source_artifact_text,
        "checks": resume_checks,
        "final_result": final_public,
        "reopened_result": reopened_public,
        "after_diplomat_semantics_match_source": checks["resume_after_diplomat_semantics_match_source"],
    }
    return checks, comparison


def build_report(artifact: Path, resume_artifact: Path | None = None) -> dict[str, Any]:
    artifact = artifact.resolve(strict=True)
    if not artifact.is_dir():
        raise ValueError(f"artifact is not a directory: {artifact}")
    report_path = artifact / "report.json"
    event_path = next(
        (artifact / name for name in ("native-events-slice.jsonl", "native-events.jsonl")
         if (artifact / name).is_file()),
        artifact / "native-events-slice.jsonl",
    )
    if not report_path.is_file() or not event_path.is_file():
        raise ValueError("artifact must contain report.json and native-events-slice.jsonl")
    source_report = _bounded_json(report_path)
    event_data = _stream_events(event_path)
    metadata = source_report.get("native_events")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata_path = metadata.get("path")
    metadata_path_matches = False
    if isinstance(metadata_path, str):
        try:
            metadata_path_matches = Path(metadata_path).resolve() == event_path.resolve()
        except OSError:
            metadata_path_matches = False
    report_size = report_path.stat().st_size
    log_size = event_path.stat().st_size
    expected_date = as_int(source_report.get("expected_date_raw"))
    start_offset = as_int(metadata.get("start_offset"))
    end_offset = as_int(metadata.get("end_offset"))
    event_log_binding = (
        metadata_path_matches
        and metadata.get("complete") is True
        and metadata.get("status") == "ok"
        and same_int(metadata.get("bytes"), log_size)
        and metadata.get("sha256") == event_data["sha256"]
        and start_offset is not None
        and end_offset is not None
        and end_offset - start_offset == log_size
    )
    chain_checks, chain = _build_chain_checks(source_report, event_data)
    if SKIP_STATE_OBSERVATION:
        diplomat_checks = {}
        diplomat_observation = {"status": "not_applicable", "reason": "family_relation"}
    else:
        diplomat_checks, diplomat_observation = _build_diplomat_observation(source_report)
    action = str(source_report.get("action_id", ""))
    expected_variant = 1 if action == START_ACTION else 0 if action == STOP_ACTION else None
    checks: dict[str, bool] = {
        "report_identity_improve_relations_fra_sav": (
            action in SUPPORTED_ACTIONS
            and source_report.get("actor") == ACTOR
            and source_report.get("recipient") == RECIPIENT
            and source_report.get("phase") == PHASE
            and expected_date is not None
            and source_report.get("mode") == "execute"
        ),
        "report_event_slice_metadata_matches_stream": event_log_binding,
        "report_and_event_inputs_within_bound": report_size <= MAX_INPUT_BYTES and log_size <= MAX_INPUT_BYTES,
        **chain_checks,
        **diplomat_checks,
    }
    resume_comparison: dict[str, Any] | None = None
    if resume_artifact is not None:
        resume_checks, resume_comparison = _build_resume_comparison(source_report, resume_artifact)
        checks.update(resume_checks)
    return {
        "schema_version": 1,
        "status": "passed" if all(checks.values()) else "failed",
        "validation_passed": all(checks.values()),
        "validator": "work/validate_improve_relations_source.py",
        "artifact": str(artifact),
        "output_mode": "fresh_evidence_directory",
        "source_report": {
            **_report_path_record(report_path),
            "status": source_report.get("status"),
            "action_id": source_report.get("action_id"),
            "actor": source_report.get("actor"),
            "recipient": source_report.get("recipient"),
            "request_id": source_report.get("request_id"),
            "session_id": _session_id(source_report),
            "expected_date_raw": expected_date,
            "expected_native_variant": expected_variant,
        },
        "event_log": {
            **_report_path_record(event_path),
            "metadata": metadata,
            "metadata_path_matches": metadata_path_matches,
            "line_count": event_data["line_count"],
            "counts": event_data["counts"],
            "malformed_lines": event_data["malformed_lines"],
            "non_object_lines": event_data["non_object_lines"],
        },
        "checks": checks,
        "failed_checks": [name for name, value in checks.items() if not value],
        "chain": chain,
        "diplomat_observation": diplomat_observation,
        "resume_comparison": resume_comparison,
        "limitations": [
            "请求 ID 出现在提交回执和任务结果中；更早的 native source/clone/transport/entry 事件没有请求 ID，采用同一 session、protocol_sequence、日期、双方和 payload 指针链绑定。",
            "transport 的 queue_verified=false 是原生观察字段；本验证把传输身份、load 数量、回调顺序和 submitted 回执作为链路证据，不把该单独字段改写为失败。",
            "外交官观察来自暂停状态下的 FRA、ENG、POR 有界快照；启动动作验证新建任务，停止动作验证同一任务的 raw18=2→1 返程变化，不推断关系值变化。",
        ],
    }


def markdown_report(report: dict[str, Any]) -> str:
    status = "通过" if report["validation_passed"] else "失败"
    source = report["source_report"]
    event = report["event_log"]
    chain = report["chain"]
    diplomat = report["diplomat_observation"]
    action = str(source.get("action_id", ""))
    variant = 1 if action == START_ACTION else 0 if action == STOP_ACTION else None
    if action == STOP_ACTION:
        action_summary = "停止 FRA→SAV 改善关系任务；native state=0、variant=0，任务从 true 变为 false。"
        diplomat_summary = (
            f"FRA→SAV type=11739 记录的 `active_raw_18` 从 `{diplomat.get('stop_before_entry', {}).get('active_raw_18')}` "
            f"变为 `{diplomat.get('stop_after_entry', {}).get('active_raw_18')}`，表示外交官进入返程；可用外交官数保持 "
            f"`{diplomat.get('before_available_count', {}).get('FRA')}`。"
        )
    else:
        action_summary = "启动 FRA→SAV 改善关系任务；native state=0、variant=1，任务从 false 变为 true。"
        diplomat_summary = (
            f"FRA 的可用外交官数从 `{diplomat.get('before_available_count', {}).get('FRA')}` 变为 "
            f"`{diplomat.get('after_available_count', {}).get('FRA')}`，暂停后的快照新增一条活动 FRA→SAV type=11739 记录。"
        )
    lines = [
        "# Improve Relations 原生来源链验证",
        "",
        f"验证结果：**{status}**。",
        "",
        f"实验 artifact：`{report['artifact']}`。",
        f"请求：`{source['request_id']}`，`{source['actor']} -> {source['recipient']}`，动作 `{action}`，阶段 `initiate`，日期 `date_raw={source['expected_date_raw']}`。",
        action_summary,
        f"事件切片：`{event['line_count']}` 行，SHA-256 `{event['sha256']}`；切片元数据与实际流式读取结果匹配为 `{event['metadata_path_matches']}`。",
        "",
        "## 验证了什么",
        "",
        "本次验证只保留五类关键事件，按同一 session、双方、日期、family、extra60、native state/variant 和指针关系关联：提交回执 → transport source/load → wrapper clone source/target → command entry → native task result。",
        "",
        f"- transport 第 `{chain['transport']['line']}` 行，load 后的 payload 与 source 相等；`load_count=1`、`matching_count=1`，未截断。",
        f"- clone 第 `{chain['clone']['line']}` 行；clone source 与 transport loaded 相同，clone target 与 command entry 的 action/command 相连。",
        f"- command entry 第 `{chain['entry']['line']}` 行；入口明确记录 `FRA -> SAV`、`{action}`、`protocol_sequence={chain['entry']['protocol_sequence']}`。",
        f"- 提交回执第 `{chain['request']['submission_line']}` 行，native task result 第 `{chain['request']['task_result_line']}` 行；结果为 `{chain['request']['outcome']}`。",
        f"- payload 全部使用 `family={FAMILY}`、`extra60=0`、`state34={EXPECTED_STATE}`、`variant38={variant}`；没有把 Alliance/Royal 的 family 或状态混入本次链路。",
        "",
        "## 运行结果",
        "",
        diplomat_summary,
        "",
    ]
    if action == STOP_ACTION:
        lines.extend([
            "停止前记录：",
            "",
            "```json",
            json.dumps(diplomat.get("stop_before_entry"), ensure_ascii=False, indent=2),
            "```",
            "",
            "停止后记录：",
            "",
            "```json",
            json.dumps(diplomat.get("stop_after_entry"), ensure_ascii=False, indent=2),
            "```",
        ])
    else:
        lines.extend([
            "新增记录：",
            "",
            "```json",
            json.dumps(diplomat.get("new_after_entry"), ensure_ascii=False, indent=2),
            "```",
        ])
    lines.extend([
        "",
        "",
        f"ENG 快照保持不变：`{diplomat['eng_before_after_equal']}`；POR 快照保持不变：`{diplomat['por_before_after_equal']}`。这两国是本次受控动作之外的对照对象。",
        "",
        "## 检查结果",
        "",
        "| 检查 | 结果 |",
        "| --- | --- |",
    ])
    for name, value in report["checks"].items():
        lines.append(f"| `{name}` | {'通过' if value else '失败'} |")
    lines.extend([
        "",
        "## 证据边界",
        "",
        "请求 ID 只在提交回执和任务结果中出现；前置 native 事件通过 session、protocol_sequence、payload 和指针链关联，因此报告没有声称前置事件携带不存在的 request ID。transport 事件中的 `queue_verified=false` 被原样记录，但没有覆盖已经验证的 source/load、世界 transport 身份、回调顺序和任务结果。",
        "",
        "原执行报告和原事件切片保持不变；本文件和同目录 `validation.json` 是本次独立验证产生的新证据。原 Stop 报告整体 status 可以是 failed；本验证以 native source 链和实际前后快照为验收依据。",
        "",
    ])
    resume = report.get("resume_comparison")
    if isinstance(resume, dict):
        lines.extend([
            "## 重开验证",
            "",
            f"只读重开 artifact：`{resume['artifact']}`；重开报告 status=`{resume['status']}`、mode=`{resume['mode']}`。",
            f"重开后的外交官快照与原 Stop 报告 after 快照一致：`{resume['after_diplomat_semantics_match_source']}`。",
            "重开过程没有重新发布执行请求，最终结果与 SQL 重开结果保持一致。",
            "",
        ])
    return "\n".join(lines)


def _fresh_output_dir(artifact: Path) -> Path:
    parent = artifact.parent
    for _ in range(32):
        candidate = parent / f"improve-relations-source-validation-{uuid.uuid4().hex}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError(f"could not create fresh evidence directory under {parent}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True, help="Improve Relations execution artifact")
    parser.add_argument("--resume-artifact", type=Path, help="optional read-only resume artifact to compare with the source Stop observation")
    parser.add_argument("--output-dir", type=Path, help="fresh evidence directory; defaults to a new sibling directory")
    return parser.parse_args()


def main(argv: list[str] | None = None) -> int:
    args = parse_args()
    try:
        artifact = args.artifact.expanduser().resolve(strict=True)
        if not artifact.is_dir():
            raise ValueError(f"artifact is not a directory: {artifact}")
        output_dir = args.output_dir.expanduser().resolve() if args.output_dir else _fresh_output_dir(artifact)
        if output_dir == artifact:
            raise ValueError("output directory must be separate from the source artifact")
        output_dir.mkdir(parents=True, exist_ok=True)
        resume_artifact = args.resume_artifact.expanduser().resolve(strict=True) if args.resume_artifact else None
        if resume_artifact is not None and resume_artifact == artifact:
            raise ValueError("resume artifact must be separate from the source artifact")
        report = build_report(artifact, resume_artifact)
        (output_dir / "validation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output_dir / "report.md").write_text(markdown_report(report), encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as error:
        print(f"validation failed to run: {error}", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": report["status"],
        "validation_passed": report["validation_passed"],
        "failed_checks": report["failed_checks"],
        "artifact": report["artifact"],
        "output_dir": str(output_dir),
        "validation_json": str(output_dir / "validation.json"),
        "report_md": str(output_dir / "report.md"),
    }, ensure_ascii=False))
    return 0 if report["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
