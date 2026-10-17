#!/usr/bin/env python3
"""独立验证未授权联盟动作的 native source -> entry 来源链。

本脚本只消费一个实验 artifact 目录中的 ``report.json`` 和
``native-events.jsonl``。JSONL 采用逐行流式读取；脚本不会把事件日志整体
读入内存，也不会把 ``request_id=unknown`` 的入口拦截解释成业务拒绝或
原生 AI 的自主选择。

默认输出 ``authority-source-validation-001.json`` 和同名 Markdown 报告，
与实验原有的 ``report.json``、``native-events.jsonl`` 保持独立。
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable


MAX_REPORT_BYTES = 10 * 1024 * 1024

DISPATCH_EVENT = "native_alliance_authority_test_dispatched"
REJECT_EVENT = "native_alliance_execution_rejected"
COMMAND_EVENT = "diplomatic_command_observed"
TRANSPORT_EVENT = "native_alliance_transport_completed"
CLONE_EVENT = "native_alliance_wrapper_clone"
ENTRY_EVENT = "native_alliance_command_entry_observed"

EVENTS_OF_INTEREST = {
    DISPATCH_EVENT,
    REJECT_EVENT,
    COMMAND_EVENT,
    TRANSPORT_EVENT,
    CLONE_EVENT,
    ENTRY_EVENT,
}

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

FAMILY_FIELD = "family"
EXTRA60_FIELD = "extra60"

# origin/flags/sequence plus the five observed prefix fields.
HEADER_FIELDS = (
    "origin",
    "protocol_flags",
    "protocol_sequence",
    "raw10",
    "raw38",
    "raw3c",
    "raw40",
    "raw44",
)

PREFIX_FIELDS = ("raw10", "raw38", "raw3c", "raw40", "raw44")

ALLIANCE_VTABLE_RVA = 0x1C80720
ROYAL_VTABLE_RVA = 0x1C80AB0
VASSALIZATION_VTABLE_RVA = 0x1C7FD20
EXPECTED_DISCRIMINATOR = 0x165

EXPECTED_FIXTURES = {
    "dissolve_alliance": {
        "recipient": "PRO",
        "variant38": 0,
        "rejection_reason": "UNAUTHORIZED_FRA_DISSOLVE",
        "family": "alliance",
        "extra60": 0,
        "vtable_rva": ALLIANCE_VTABLE_RVA,
    },
    "offer_alliance": {
        "recipient": "SAV",
        "variant38": 1,
        "rejection_reason": "UNAUTHORIZED_FRA_OFFER",
        "family": "alliance",
        "extra60": 0,
        "vtable_rva": ALLIANCE_VTABLE_RVA,
    },
    "offer_royal_marriage": {
        "recipient": "SAV",
        "variant38": 1,
        "rejection_reason": "UNAUTHORIZED_FRA_ROYAL_OFFER",
        "family": "royal_marriage",
        "extra60": 0,
        "vtable_rva": ROYAL_VTABLE_RVA,
    },
    "break_royal_ties": {
        "recipient": "PRO",
        "variant38": 0,
        "rejection_reason": "UNAUTHORIZED_FRA_ROYAL_BREAK",
        "family": "royal_marriage",
        "extra60": 0,
        "vtable_rva": ROYAL_VTABLE_RVA,
    },
    "offer_vassalization": {
        "recipient": "GEN",
        "variant38": 1,
        "rejection_reason": "UNAUTHORIZED_FRA_VASSALIZATION_OFFER",
        "family": "vassalization",
        "extra60": 0,
        "vtable_rva": VASSALIZATION_VTABLE_RVA,
    },
    "cancel_vassalization": {
        "recipient": "LEI",
        "variant38": 0,
        "rejection_reason": "UNAUTHORIZED_FRA_VASSALIZATION_CANCEL",
        "family": "vassalization",
        "extra60": 0,
        "vtable_rva": VASSALIZATION_VTABLE_RVA,
    },
}


def as_int(value: Any) -> int | None:
    """Parse native integer fields without accepting missing values."""

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 0)
        except ValueError:
            try:
                return int(text, 10)
            except ValueError:
                return None
    return None


def same_int(left: Any, right: Any) -> bool:
    left_value = as_int(left)
    right_value = as_int(right)
    return left_value is not None and right_value is not None and left_value == right_value


def true_value(value: Any) -> bool:
    return value is True


def json_file(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    if size > MAX_REPORT_BYTES:
        raise ValueError(f"refusing full parse of report larger than 10 MiB: {path} ({size} bytes)")
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "sha256": sha256_file(path),
    }


def stream_events(path: Path) -> dict[str, Any]:
    """Parse JSONL one line at a time while retaining only relevant events."""

    counts: Counter[str] = Counter()
    relevant: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    malformed: list[dict[str, Any]] = []
    non_object: list[int] = []
    line_count = 0
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            line_count += 1
            digest.update(raw_line)
            try:
                text = raw_line.decode("utf-8")
                value = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                if len(malformed) < 32:
                    malformed.append({"line": line_number, "error": str(error)})
                continue
            if not isinstance(value, dict):
                if len(non_object) < 32:
                    non_object.append(line_number)
                continue
            name = str(value.get("event", ""))
            counts[name] += 1
            if name in EVENTS_OF_INTEREST:
                event = dict(value)
                event["_line"] = line_number
                relevant[name].append(event)

    return {
        "line_count": line_count,
        "sha256": digest.hexdigest(),
        "counts": dict(sorted(counts.items())),
        "malformed_lines": malformed,
        "non_object_lines": non_object,
        "events": {name: list(values) for name, values in relevant.items()},
    }


def payload_of(shape: Any) -> dict[str, Any]:
    if not isinstance(shape, dict):
        return {}
    nested = shape.get("payload")
    return nested if isinstance(nested, dict) else shape


def payload_fields_present(shape: Any) -> bool:
    payload = payload_of(shape)
    return all(field in payload and as_int(payload.get(field)) is not None for field in PAYLOAD_FIELDS)


def family_for_action(action: str) -> str:
    if action in ("offer_royal_marriage", "break_royal_ties"):
        return "royal_marriage"
    if action in ("offer_vassalization", "cancel_vassalization"):
        return "vassalization"
    return "alliance"


def expected_vtable_for_family(family: str) -> int:
    if family == "royal_marriage":
        return ROYAL_VTABLE_RVA
    if family == "vassalization":
        return VASSALIZATION_VTABLE_RVA
    return ALLIANCE_VTABLE_RVA


def payload_family_extra_valid(shape: Any, family: str = "alliance") -> bool:
    """Validate family identity and the Royal serialized +0x60 flag.

    Historical Alliance artifacts predate these two fields.  They are
    normalized to ``family=alliance`` and ``extra60=0``.  Royal artifacts
    must carry both fields explicitly so a shared type discriminator cannot
    authorize an Alliance object as a Royal object.
    """

    payload = payload_of(shape)
    if family == "royal_marriage":
        if FAMILY_FIELD not in payload or EXTRA60_FIELD not in payload:
            return False
        return (payload.get(FAMILY_FIELD) == "royal_marriage"
                and not isinstance(payload.get(EXTRA60_FIELD), bool)
                and as_int(payload.get(EXTRA60_FIELD)) == 0)
    if family == "vassalization":
        return (payload.get(FAMILY_FIELD) == "vassalization"
                and not isinstance(payload.get(EXTRA60_FIELD, 0), bool)
                and as_int(payload.get(EXTRA60_FIELD, 0)) == 0)
    family_value = payload.get(FAMILY_FIELD, "alliance")
    extra_value = payload.get(EXTRA60_FIELD, 0)
    return (family_value == "alliance"
            and not isinstance(extra_value, bool)
            and as_int(extra_value) == 0)


def payload_shape_valid(shape: Any, family: str = "alliance") -> bool:
    """Validate the inner action payload shape used by all chain events."""

    if not isinstance(shape, dict):
        return False
    payload = payload_of(shape)
    return (
        true_value(payload.get("readable"))
        and true_value(payload.get("matched"))
        and true_value(payload.get("handles_canonical"))
        and same_int(payload.get("vtable_rva"), expected_vtable_for_family(family))
        and same_int(payload.get("discriminator"), EXPECTED_DISCRIMINATOR)
        and payload_fields_present(shape)
        and payload_family_extra_valid(shape, family)
    )


def object_shape_valid(shape: Any, family: str = "alliance") -> bool:
    """Validate wrapper/action identity and its readable canonical payload."""

    if not isinstance(shape, dict):
        return False
    return (
        true_value(shape.get("identity"))
        and true_value(shape.get("readable"))
        and true_value(shape.get("prefix_readable"))
        and as_int(shape.get("addr")) is not None
        and as_int(shape.get("action")) is not None
        and payload_shape_valid(shape, family)
    )


def header_values(shape: Any) -> dict[str, Any]:
    shape = shape if isinstance(shape, dict) else {}
    return {field: shape.get(field) for field in HEADER_FIELDS}


def header_equal(left: Any, right: Any) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    if not (true_value(left.get("identity")) and true_value(right.get("identity"))):
        return False
    if not (true_value(left.get("readable")) and true_value(right.get("readable"))):
        return False
    if not (true_value(left.get("prefix_readable")) and true_value(right.get("prefix_readable"))):
        return False
    return all(same_int(left.get(field), right.get(field)) for field in HEADER_FIELDS)


def payload_values(shape: Any) -> dict[str, Any]:
    payload = payload_of(shape)
    return {
        **{field: payload.get(field) for field in PAYLOAD_FIELDS},
        FAMILY_FIELD: payload.get(FAMILY_FIELD, "alliance"),
        EXTRA60_FIELD: payload.get(EXTRA60_FIELD, 0),
    }


def payload_equal(left: Any, right: Any, family: str = "alliance") -> bool:
    if not payload_shape_valid(left, family) or not payload_shape_valid(right, family):
        return False
    left_payload = payload_of(left)
    right_payload = payload_of(right)
    numeric_equal = all(same_int(left_payload.get(field), right_payload.get(field))
                        for field in PAYLOAD_FIELDS)
    left_family = left_payload.get(FAMILY_FIELD, "alliance")
    right_family = right_payload.get(FAMILY_FIELD, "alliance")
    left_extra = left_payload.get(EXTRA60_FIELD, 0)
    right_extra = right_payload.get(EXTRA60_FIELD, 0)
    return (numeric_equal and left_family == right_family == family
            and not isinstance(left_extra, bool) and not isinstance(right_extra, bool)
            and same_int(left_extra, right_extra))


def shape_summary(shape: Any) -> dict[str, Any]:
    shape = shape if isinstance(shape, dict) else {}
    payload = payload_of(shape)
    return {
        "addr": shape.get("addr"),
        "action": shape.get("action"),
        "identity": shape.get("identity"),
        "readable": shape.get("readable"),
        "prefix_readable": shape.get("prefix_readable"),
        "matched": payload.get("matched"),
        "handles_canonical": payload.get("handles_canonical"),
        "vtable_rva": payload.get("vtable_rva"),
        "discriminator": payload.get("discriminator"),
        "header": header_values(shape),
        "payload": payload_values(shape),
    }


def payload_from_entry(entry: Any) -> dict[str, Any]:
    payload = payload_of(entry)
    return payload


def report_check_map(report: dict[str, Any]) -> dict[str, bool]:
    checks = report.get("checks")
    if not isinstance(checks, dict):
        return {}
    return {str(name): value is True for name, value in checks.items()}


def query_binding(query: Any, action: str, actor: str, recipient: str, date_raw: int) -> bool:
    if not isinstance(query, dict):
        return False
    session = query.get("session")
    return (
        query.get("action_id") == action
        and query.get("actor") == actor
        and query.get("recipient") == recipient
        and query.get("phase") == "initiate"
        and isinstance(session, dict)
        and same_int(session.get("date_raw"), date_raw)
    )


def check_report_binding(
    report: dict[str, Any], action: str, actor: str, recipient: str, date_raw: int,
    *, reconciliation: dict[str, Any] | None = None,
    source_report_sha256: str | None = None,
    family: str | None = None,
) -> dict[str, bool]:
    before_query = report.get("before_query")
    after_query = report.get("after_query")
    before_resources = before_query.get("resources") if isinstance(before_query, dict) else None
    after_resources = after_query.get("resources") if isinstance(after_query, dict) else None
    before_visibility = before_query.get("visibility") if isinstance(before_query, dict) else None
    after_visibility = after_query.get("visibility") if isinstance(after_query, dict) else None
    before_legality = before_query.get("legality") if isinstance(before_query, dict) else None
    after_legality = after_query.get("legality") if isinstance(after_query, dict) else None
    before_relation = before_query.get("relationship_state") if isinstance(before_query, dict) else None
    after_relation = after_query.get("relationship_state") if isinstance(after_query, dict) else None
    before_control = report.get("before")
    after_control = report.get("after")
    report_checks = report_check_map(report)
    reconciliation_checks = (
        reconciliation.get("checks")
        if isinstance(reconciliation, dict)
        and isinstance(reconciliation.get("checks"), dict)
        else {}
    )
    reconciliation_ok = (
        isinstance(reconciliation, dict)
        and reconciliation.get("status") == "passed"
        and (
            source_report_sha256 is None
            or str(reconciliation.get("source_sha256", "")).lower()
            == source_report_sha256.lower()
        )
        and bool(reconciliation_checks)
        and all(value is True for value in reconciliation_checks.values())
        and reconciliation.get("request_republished") is False
        and reconciliation.get("game_operations") is False
    )
    return {
        "source_report_status_passed": report.get("status") == "passed" or reconciliation_ok,
        "source_report_checks_all_passed": (
            bool(report_checks) and all(report_checks.values())
        ) or reconciliation_ok,
        "reconciliation_if_present_valid": (
            reconciliation is None or reconciliation_ok
        ),
        "report_session_present": bool(str(report.get("session_id", ""))),
        "report_action_matches": report.get("action_id") == action,
        "before_query_binding": query_binding(before_query, action, actor, recipient, date_raw),
        "after_query_binding": query_binding(after_query, action, actor, recipient, date_raw),
        "relation_visibility_unchanged": isinstance(before_visibility, dict)
        and before_visibility == after_visibility,
        "relationship_state_unchanged": (
            family != "vassalization"
            or (
                isinstance(before_relation, dict)
                and before_relation == after_relation
            )
        ),
        "prestige_unchanged": (
            family != "vassalization"
            or (
                isinstance(before_query, dict)
                and isinstance(after_query, dict)
                and same_int(before_query.get("prestige_raw"), after_query.get("prestige_raw"))
            )
        ),
        "legality_unchanged": isinstance(before_legality, dict) and before_legality == after_legality,
        "diplomat_resources_unchanged": isinstance(before_resources, dict)
        and before_resources == after_resources,
        "control_date_unchanged": isinstance(before_control, dict)
        and isinstance(after_control, dict)
        and same_int(before_control.get("date_raw"), after_control.get("date_raw"))
        and same_int(after_control.get("date_raw"), date_raw),
        "control_player_paused": isinstance(after_control, dict)
        and same_int(after_control.get("player_slot"), 189)
        and same_int(after_control.get("paused_flag"), 1),
    }


def check_chain(
    report: dict[str, Any],
    event_data: dict[str, Any],
    *,
    reconciliation: dict[str, Any] | None = None,
    source_report_sha256: str | None = None,
) -> tuple[dict[str, bool], dict[str, Any], dict[str, Any]]:
    action = str(report.get("action_id", ""))
    fixture = EXPECTED_FIXTURES.get(action)
    if fixture is None:
        raise ValueError(f"unsupported authority fixture action_id: {action!r}")
    actor = "FRA"
    expected_recipient = str(fixture["recipient"])
    expected_reason = str(fixture["rejection_reason"])
    expected_variant = int(fixture["variant38"])
    expected_family = str(fixture["family"])
    expected_extra60 = int(fixture["extra60"])
    expected_vtable = int(fixture["vtable_rva"])
    session_id = str(report.get("session_id", ""))

    events = event_data["events"]

    def session_events(name: str) -> list[dict[str, Any]]:
        return [item for item in events.get(name, []) if str(item.get("session_id")) == session_id]

    dispatches = session_events(DISPATCH_EVENT)
    rejects = session_events(REJECT_EVENT)
    commands = session_events(COMMAND_EVENT)
    transports = session_events(TRANSPORT_EVENT)
    clones = session_events(CLONE_EVENT)
    entries = session_events(ENTRY_EVENT)

    dispatch = dispatches[0] if len(dispatches) == 1 else {}
    reject = rejects[0] if len(rejects) == 1 else {}
    command = commands[0] if len(commands) == 1 else {}
    transport = transports[0] if len(transports) == 1 else {}
    clone = clones[0] if len(clones) == 1 else {}
    entry = entries[0] if len(entries) == 1 else {}
    dispatch_route = str(
        dispatch.get("dispatch_route") or report.get("dispatch_route") or ""
    )
    direct_entry = dispatch_route == "direct_entry"

    transport_source = transport.get("source")
    transport_loaded = transport.get("loaded")
    clone_source = clone.get("source")
    clone_target = clone.get("target")
    entry_source = entry.get("source")
    transport_begin = as_int(transport.get("callback_begin"))
    load_sequence = as_int(transport.get("load_callback_sequence"))
    transport_end = as_int(transport.get("callback_end"))
    clone_begin = as_int(clone.get("begin_callback_sequence"))
    clone_end = as_int(clone.get("callback_sequence"))
    entry_sequence = as_int(entry.get("callback_sequence"))

    checks: dict[str, bool] = {
        "jsonl_fully_parsed": not event_data["malformed_lines"] and not event_data["non_object_lines"],
        "session_bound_dispatch_once": len(dispatches) == 1,
        "session_bound_rejection_once": len(rejects) == 1,
        "session_bound_command_once": len(commands) == 1,
        "session_bound_transport_once": len(transports) == (0 if direct_entry else 1),
        "session_bound_clone_once": len(clones) == (0 if direct_entry else 1),
        "session_bound_entry_once": len(entries) == 1,
        "dispatch_action_actor_recipient_phase_date": (
            dispatch.get("action_id") == action
            and dispatch.get("actor") == actor
            and dispatch.get("recipient") == expected_recipient
            and dispatch.get("phase") == "initiate"
            and same_int(dispatch.get("date_raw"), report.get("before_query", {}).get("session", {}).get("date_raw"))
        ),
        "dispatch_without_authority_seed": dispatch.get("authority_seed_created") is False,
        "route_contract": (
            (
                direct_entry
                and not transports
                and not clones
                and dispatch.get("dispatcher_accepted") is False
                and same_int(dispatch.get("source_wrapper"), entry.get("command"))
                and same_int(dispatch.get("source_action"), entry.get("action"))
            )
            or (
                not direct_entry
                and len(transports) == 1
                and len(clones) == 1
                and dispatch.get("dispatcher_accepted") is True
            )
        ),
        "dispatcher_accepted": dispatch.get("dispatcher_accepted") is (False if direct_entry else True),
        "dispatch_variant_and_state": same_int(dispatch.get("variant38"), expected_variant)
        and same_int(dispatch.get("state34"), 0),
        "fixture_family_matches_action": expected_family == family_for_action(action),
        "dispatch_source_binds_transport_source": (
            (
                same_int(dispatch.get("source_wrapper"), transport_source.get("addr") if isinstance(transport_source, dict) else None)
                and same_int(dispatch.get("source_action"), transport_source.get("action") if isinstance(transport_source, dict) else None)
            )
            if not direct_entry else (
                same_int(dispatch.get("source_wrapper"), entry.get("command"))
                and same_int(dispatch.get("source_action"), entry.get("action"))
            )
        ),
        "rejection_is_expected_authority_gate": reject.get("reason") == expected_reason,
        "rejection_submitted_false": reject.get("submitted") is False,
        "rejection_request_id_is_unknown": reject.get("request_id") == "unknown",
        "command_origin_marker": same_int(command.get("origin"), 0xFFFF),
        "command_flags_marker": same_int(command.get("protocol_flags"), 0),
        "transport_completed": transport.get("completed") is True if not direct_entry else not transports,
        "transport_loads_not_truncated": transport.get("loads_truncated") is False if not direct_entry else not transports,
        "transport_caller_verified": transport.get("caller_verified") is True if not direct_entry else not transports,
        "transport_world_identity": (
            same_int(transport.get("peer"), transport.get("transport"))
            and same_int(transport.get("peer"), transport.get("world_transport"))
            and same_int(transport.get("peer_owner"), transport.get("world_dispatcher"))
            and true_value(transport.get("peer_readable"))
            and true_value(transport.get("world_transport_readable"))
            and true_value(transport.get("peer_is_world_transport"))
        ) if not direct_entry else not transports,
        "transport_authority_observed_false": transport.get("authority") is False if not direct_entry else not transports,
        "transport_forwarding_observed_true": transport.get("all_commands_forwarded") is True if not direct_entry else not transports,
        "transport_source_is_outgoing": same_int(
            transport.get("outgoing"), transport_source.get("addr") if isinstance(transport_source, dict) else None
        ) if not direct_entry else not transports,
        "transport_source_shape_valid": object_shape_valid(transport_source, expected_family) if not direct_entry else not transports,
        "transport_loaded_shape_valid": object_shape_valid(transport_loaded, expected_family) if not direct_entry else not transports,
        "transport_source_vtable_matches_family": same_int(
            payload_of(transport_source).get("vtable_rva")
            if isinstance(transport_source, dict) else None, expected_vtable) if not direct_entry else not transports,
        "transport_source_family_extra60_valid": payload_family_extra_valid(
            transport_source, expected_family) if not direct_entry else not transports,
        "transport_loaded_family_extra60_valid": payload_family_extra_valid(
            transport_loaded, expected_family) if not direct_entry else not transports,
        "transport_source_loaded_headers_equal": header_equal(transport_source, transport_loaded) if not direct_entry else not transports,
        "transport_source_loaded_payload_equal": payload_equal(
            transport_source, transport_loaded, expected_family) if not direct_entry else not transports,
        "transport_source_loaded_wrapper_action_distinct": (
            isinstance(transport_source, dict)
            and isinstance(transport_loaded, dict)
            and not same_int(transport_source.get("addr"), transport_loaded.get("addr"))
            and not same_int(transport_source.get("action"), transport_loaded.get("action"))
        ) if not direct_entry else not transports,
        "observed_command_binds_entry": (
            same_int(command.get("command"), entry.get("command"))
            and same_int(command.get("action"), entry.get("action"))
            and same_int(command.get("protocol_sequence"), entry.get("protocol_sequence"))
        ),
        "clone_source_matches_loaded_identity": (
            isinstance(clone_source, dict)
            and isinstance(transport_loaded, dict)
            and same_int(clone_source.get("addr"), transport_loaded.get("addr"))
            and same_int(clone_source.get("action"), transport_loaded.get("action"))
        ) if not direct_entry else not clones,
        "clone_source_shape_valid": object_shape_valid(clone_source, expected_family) if not direct_entry else not clones,
        "clone_source_headers_equal_loaded": header_equal(clone_source, transport_loaded) if not direct_entry else not clones,
        "clone_source_payload_equal_loaded": payload_equal(
            clone_source, transport_loaded, expected_family) if not direct_entry else not clones,
        "clone_target_shape_valid": object_shape_valid(clone_target, expected_family) if not direct_entry else not clones,
        "clone_target_payload_equal_loaded": payload_equal(
            clone_target, transport_loaded, expected_family) if not direct_entry else not clones,
        "clone_target_family_extra60_valid": payload_family_extra_valid(
            clone_target, expected_family) if not direct_entry else not clones,
        "clone_target_marker_origin_flags_sequence_zero": (
            isinstance(clone_target, dict)
            and same_int(clone_target.get("origin"), 0xFFFF)
            and same_int(clone_target.get("protocol_flags"), 0)
            and same_int(clone_target.get("protocol_sequence"), 0)
        ) if not direct_entry else not clones,
        "clone_target_is_native_result": same_int(
            clone.get("native_result"), clone_target.get("addr") if isinstance(clone_target, dict) else None
        ) if not direct_entry else not clones,
        "clone_receiver_worldtransport_dispatcher_ring_equal": (
            same_int(clone.get("receiver"), transport.get("peer"))
            and same_int(clone.get("receiver_host"), transport.get("peer_owner"))
            and same_int(clone.get("receiver_input_ring"), transport.get("peer_input_ring"))
            and same_int(clone.get("world_dispatcher"), transport.get("world_dispatcher"))
            and same_int(clone.get("world_transport"), transport.get("world_transport"))
            and true_value(clone.get("receiver_readable"))
            and true_value(clone.get("world_transport_readable"))
            and true_value(clone.get("receiver_is_world_transport"))
        ) if not direct_entry else not clones,
        "clone_callback_contract": (
            same_int(clone.get("caller_return_rva"), 0x15801E2)
            and clone.get("caller_return_matches") is True
        ) if not direct_entry else not clones,
        "entry_shape_payload_valid": payload_shape_valid(entry_source, expected_family),
        "entry_family_extra60_valid": payload_family_extra_valid(entry_source, expected_family),
        "entry_action_id_bound": entry.get("action_id") == action,
        "entry_actor_recipient_bound": entry.get("actor_field") == actor
        and entry.get("recipient_field") == expected_recipient,
        "entry_command_is_clone_target": (
            same_int(entry.get("command"), clone_target.get("addr") if isinstance(clone_target, dict) else None)
            and same_int(entry.get("action"), clone_target.get("action") if isinstance(clone_target, dict) else None)
        ) if not direct_entry else (
            same_int(entry.get("command"), dispatch.get("source_wrapper"))
            and same_int(entry.get("action"), dispatch.get("source_action"))
        ),
        "entry_prefix_matches_clone_target": (
            isinstance(clone_target, dict)
            and all(same_int(entry.get(field), clone_target.get(field)) for field in PREFIX_FIELDS)
        ) if not direct_entry else (
            entry.get("raw10") == 0
            and entry.get("raw38") == -1
            and entry.get("raw3c") == 0
            and entry.get("raw40") == 0
            and entry.get("raw44") is not None
        ),
        "entry_marker_origin_flags": same_int(entry.get("origin"), 0xFFFF)
        and same_int(entry.get("protocol_flags"), 0),
        "entry_sequence_matches_source_header": same_int(
            entry.get("protocol_sequence"), transport_source.get("protocol_sequence")
            if isinstance(transport_source, dict)
            else None
        ) if not direct_entry else same_int(entry.get("protocol_sequence"), 0),
        "entry_payload_matches_clone_target": payload_equal(
            entry_source, clone_target, expected_family) if not direct_entry else payload_shape_valid(entry_source, expected_family),
        "entry_payload_date_matches_dispatch": (
            same_int(payload_from_entry(entry_source).get("date28"),
                     43808760 if expected_family == "royal_marriage" else dispatch.get("date_raw"))
            and same_int(payload_from_entry(entry_source).get("date2c"), dispatch.get("date_raw"))
        ),
        "entry_business_result_unknown": entry.get("business_result") == "unknown"
        and entry.get("rule_result") == "unknown"
        and entry.get("complete") is False,
        "callback_order_load_transport_clone_entry": (
            None not in (transport_begin, load_sequence, transport_end, clone_begin, clone_end, entry_sequence)
            and transport_begin < load_sequence < transport_end < clone_begin <= clone_end < entry_sequence
        ) if not direct_entry else entry_sequence is not None,
    }

    # Keep the first boundary separate in the report so a missing field cannot
    # be hidden by a later stage comparison.
    checks["callback_begin_before_load"] = (
        entry_sequence is not None
        if direct_entry else
        transport_begin is not None and load_sequence is not None and transport_begin < load_sequence
    )

    checks.update(
        check_report_binding(
            report,
            action,
            actor,
            expected_recipient,
            as_int(dispatch.get("date_raw")) or -1,
            reconciliation=reconciliation,
            source_report_sha256=source_report_sha256,
            family=expected_family,
        )
    )

    # This is deliberately an observation, not a gate.  The native log says
    # queue_verified=false because this fixture tests entry authorization;
    # that fact must not invalidate the matched source chain.
    queue_observation = {
        "queue_verified": transport.get("queue_verified"),
        "queue_verified_is_gate": False,
        "authority": transport.get("authority"),
        "business_submission": False,
        "business_acceptance": False,
        "native_ai_self_choice_evidence": False,
        "rejection_interpretation": "入口授权拦截；request_id=unknown，不是业务拒绝。",
    }

    chain = {
        "dispatch": {
            "line": dispatch.get("_line"),
            "session_id": dispatch.get("session_id"),
            "action_id": dispatch.get("action_id"),
            "actor": dispatch.get("actor"),
            "recipient": dispatch.get("recipient"),
            "phase": dispatch.get("phase"),
            "date_raw": dispatch.get("date_raw"),
            "source_wrapper": dispatch.get("source_wrapper"),
            "source_action": dispatch.get("source_action"),
            "variant38": dispatch.get("variant38"),
            "state34": dispatch.get("state34"),
            "dispatch_route": dispatch_route,
            "authority_seed_created": dispatch.get("authority_seed_created"),
            "dispatcher_accepted": dispatch.get("dispatcher_accepted"),
            "family": expected_family,
            "expected_vtable_rva": expected_vtable,
            "extra60": expected_extra60,
        },
        "transport": {
            "line": transport.get("_line"),
            "callback_begin": transport.get("callback_begin"),
            "load_callback_sequence": transport.get("load_callback_sequence"),
            "callback_end": transport.get("callback_end"),
            "source": shape_summary(transport_source),
            "loaded": shape_summary(transport_loaded),
            "world": {
                "peer": transport.get("peer"),
                "peer_owner": transport.get("peer_owner"),
                "peer_input_ring": transport.get("peer_input_ring"),
                "world_dispatcher": transport.get("world_dispatcher"),
                "world_transport": transport.get("world_transport"),
            },
            "queue_verified": transport.get("queue_verified"),
        },
        "clone": {
            "line": clone.get("_line"),
            "begin_callback_sequence": clone.get("begin_callback_sequence"),
            "callback_sequence": clone.get("callback_sequence"),
            "source": shape_summary(clone_source),
            "target": shape_summary(clone_target),
            "native_result": clone.get("native_result"),
            "receiver": clone.get("receiver"),
        },
        "entry": {
            "line": entry.get("_line"),
            "callback_sequence": entry.get("callback_sequence"),
            "origin": entry.get("origin"),
            "protocol_flags": entry.get("protocol_flags"),
            "protocol_sequence": entry.get("protocol_sequence"),
            "command": entry.get("command"),
            "action": entry.get("action"),
            "action_id": entry.get("action_id"),
            "actor_field": entry.get("actor_field"),
            "recipient_field": entry.get("recipient_field"),
            "source": shape_summary(entry_source),
            "business_result": entry.get("business_result"),
            "rule_result": entry.get("rule_result"),
        },
        "rejection": {
            "line": reject.get("_line"),
            "reason": reject.get("reason"),
            "request_id": reject.get("request_id"),
            "submitted": reject.get("submitted"),
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
    return checks, chain, queue_observation


def build_report(artifact: Path) -> dict[str, Any]:
    artifact = artifact.resolve(strict=True)
    if not artifact.is_dir():
        raise ValueError(f"artifact is not a directory: {artifact}")
    report_path = artifact / "report.json"
    events_path = artifact / "native-events.jsonl"
    if not report_path.is_file() or not events_path.is_file():
        raise ValueError("artifact must contain report.json and native-events.jsonl")

    source_report = json_file(report_path)
    event_data = stream_events(events_path)
    reconciliation_path = artifact / "query-contract-reconciliation-001.json"
    reconciliation = (
        json_file(reconciliation_path)
        if reconciliation_path.is_file() else None
    )
    checks, chain, queue_observation = check_chain(
        source_report,
        event_data,
        reconciliation=reconciliation,
        source_report_sha256=sha256_file(report_path),
    )
    action = str(source_report.get("action_id", ""))
    fixture = EXPECTED_FIXTURES[action]
    expected_family = str(fixture["family"])
    expected_vtable = int(fixture["vtable_rva"])
    expected_extra60 = int(fixture["extra60"])

    return {
        "schema_version": 1,
        "status": "passed" if all(checks.values()) else "failed",
        "validation_passed": all(checks.values()),
        "validator": "work/validate_alliance_authority_source.py",
        "artifact": str(artifact),
        "output_mode": "exclusive",
        "source_report": {
            **file_record(report_path),
            "status": source_report.get("status"),
            "action_id": source_report.get("action_id"),
            "session_id": source_report.get("session_id"),
            "checks": source_report.get("checks"),
        },
        "query_contract_reconciliation": (
            {
                **file_record(reconciliation_path),
                "status": reconciliation.get("status"),
                "source_sha256": reconciliation.get("source_sha256"),
                "request_republished": reconciliation.get("request_republished"),
                "game_operations": reconciliation.get("game_operations"),
            }
            if reconciliation is not None else None
        ),
        "event_log": {
            **file_record(events_path),
            "line_count": event_data["line_count"],
            "counts": event_data["counts"],
            "malformed_lines": event_data["malformed_lines"],
            "non_object_lines": event_data["non_object_lines"],
        },
        "fixture_binding": {
            "actor": "FRA",
            "phase": "initiate",
            "family": expected_family,
            "expected_vtable_rva": expected_vtable,
            "expected_extra60": expected_extra60,
            "dispatch_route": chain["dispatch"].get("dispatch_route"),
            "accepted_by_native_dispatcher": chain["dispatch"].get("dispatcher_accepted"),
            "authority_seed_created": False,
            "unauthorized_gate_only": True,
            "native_ai_self_choice_evidence": False,
        },
        "checks": checks,
        "failed_checks": [name for name, value in checks.items() if not value],
        "chain": chain,
        "queue_observation": queue_observation,
        "limitations": [
            "该报告验证 native source→transport loaded→clone target→command entry 来源链。",
            "UNAUTHORIZED 拒绝发生在入口授权门；request_id=unknown 不表示业务拒绝。",
            "queue_verified=false 是当前观察事实，不作为来源链匹配门槛。",
            "报告不证明原生 AI 自发接受/拒绝，也不证明桥接业务提交或业务后果。",
        ],
    }


def markdown_report(report: dict[str, Any]) -> str:
    status = "PASS" if report["validation_passed"] else "FAIL"
    lines = [
        "# Alliance authority source validation",
        "",
        f"- Status: **{status}**",
        f"- Artifact: `{report['artifact']}`",
        "- Output mode: `exclusive`",
        f"- Source report SHA-256: `{report['source_report']['sha256']}`",
        f"- Native event log SHA-256: `{report['event_log']['sha256']}`",
        f"- JSONL lines: `{report['event_log']['line_count']}`",
        "",
        "## Binding",
        "",
        f"- action: `{report['source_report']['action_id']}`; session: `{report['source_report']['session_id']}`",
        f"- family: `{report['fixture_binding']['family']}`; expected action vtable: `0x{report['fixture_binding']['expected_vtable_rva']:x}`; expected `extra60`: `{report['fixture_binding']['expected_extra60']}`",
        "- actor/phase: `FRA` / `initiate`",
        "- dispatch: `authority_seed_created=false`, `dispatcher_accepted=true`",
        "- gate semantics: one `UNAUTHORIZED_*` entry rejection with `submitted=false`; `request_id=unknown` is not a business rejection",
        "",
        "## Checks",
        "",
        "| Check | Result |",
        "| --- | --- |",
    ]
    for name, value in report["checks"].items():
        lines.append(f"| `{name}` | {'PASS' if value else 'FAIL'} |")
    lines.extend(
        [
            "",
            "## Callback chain",
            "",
            "`callback_begin < load < transport_end < clone_begin <= clone_end < entry`",
            "",
            "```json",
            json.dumps(report["chain"], ensure_ascii=False, indent=2),
            "```",
            "",
            "## Boundary",
            "",
            "- Nine numeric payload fields, the family string, and the serialized `extra60` flag are compared between transport source/loaded and clone source/loaded.",
            "- Clone target uses the observed `origin=65535`, `protocol_flags=0`, `protocol_sequence=0` marker; command entry must expose the source sequence and the five target prefix fields.",
            "- `queue_verified=false` remains an observation and does not fail the chain.",
            "- This is an unauthorized entry-gate fixture. It does not prove native AI choice, bridge submission, acceptance, rejection, or game outcome.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True, help="authority-test artifact directory")
    parser.add_argument("--json-out", type=Path, help="exclusive JSON output path")
    parser.add_argument("--md-out", type=Path, help="exclusive Markdown output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        artifact = args.artifact.resolve(strict=True)
        output_json = (args.json_out or artifact / "authority-source-validation-001.json").resolve()
        output_md = (args.md_out or artifact / "authority-source-validation-001.md").resolve()
        forbidden = {artifact / "report.json", artifact / "native-events.jsonl"}
        if output_json in forbidden or output_md in forbidden:
            raise ValueError("exclusive output cannot overwrite report.json or native-events.jsonl")
        report = build_report(artifact)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output_md.write_text(markdown_report(report), encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"validation failed to run: {error}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "status": report["status"],
                "validation_passed": report["validation_passed"],
                "failed_checks": report["failed_checks"],
                "action_id": report["source_report"]["action_id"],
                "artifact": report["artifact"],
                "output_json": str(output_json),
                "output_md": str(output_md),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
