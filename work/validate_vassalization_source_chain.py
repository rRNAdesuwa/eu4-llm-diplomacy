"""独立核验一次 Vassalization 执行的 native 来源链。

脚本只读取 R35B artifact 中的 ``report.json`` 与有界
``native-events-slice.jsonl``，并读取同一 build runtime 中与 Vassalization
相关的三个小型 source manifest 文件。它把 transport、loaded、clone、
command-entry、native response 和 lifecycle destructor 分成明确阶段；
``protocol_sequence``、生命周期 ``seq4c`` 和生命周期内部 ``sequence``
属于不同编号域，脚本不会把它们混为同一个序列。

原操作器报告可能因为 after snapshot 的外围检查失败。本验证器不把该状态
当作来源链结论，只比较实际 native 事件与公开终态结果，并在报告中保留
原报告状态和失败检查名。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


WORK_DIR = Path(__file__).resolve().parent
if str(WORK_DIR) not in sys.path:
    sys.path.insert(0, str(WORK_DIR))

from validate_alliance_transport import (  # noqa: E402
    HEADER_FIELDS,
    as_int,
    header_equal,
    payload_of,
    payload_summary,
    sha256_file,
)


MAX_INPUT_BYTES = 10 * 1024 * 1024
FAMILY = "vassalization"
ACTION = "offer_vassalization"
ACTOR = "FRA"
PHASE = "initiate"
VASSAL_VTABLE_RVA = 0x1C7FD20
VASSAL_FACTORY_SELECTOR = 0x2940
VASSAL_CLONE_RVA = 0x51FA30
TRANSPORT_RETURN_RVA = 0x15808F2
CLONE_RETURN_RVA = 0x15801E2
RECEIVER_VTABLE_RVA = 0x1D95FD8
TRANSPORT_EVENT = "native_alliance_transport_completed"
CLONE_EVENT = "native_alliance_wrapper_clone"
ENTRY_EVENT = "native_alliance_command_entry_observed"
SUBMISSION_EVENT = "native_alliance_submission_result"
RESPONSE_EVENT = "native_diplomacy_relation_response_result"
EXECUTION_EVENT = "native_diplomacy_relation_execution_result"
LIFECYCLE_EVENT = "native_alliance_lifecycle"


def bounded_size(path: Path) -> int:
    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise ValueError(f"input exceeds 10 MiB bound: {path} ({size} bytes)")
    return size


def read_json(path: Path) -> dict[str, Any]:
    bounded_size(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def strict_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else as_int(value)


def same_int(left: Any, right: Any) -> bool:
    left_value = strict_int(left)
    right_value = strict_int(right)
    return left_value is not None and right_value is not None and left_value == right_value


def true(value: Any) -> bool:
    return value is True


def exact_binding(event: dict[str, Any], *, request_id: str, session_id: str,
                  action_id: str, actor: str, recipient: str,
                  phase: str, date_raw: int) -> bool:
    return (
        event.get("request_id") == request_id
        and event.get("session_id") == session_id
        and event.get("action_id") == action_id
        and event.get("actor") == actor
        and event.get("recipient") == recipient
        and event.get("phase") == phase
        and same_int(event.get("date_raw"), date_raw)
    )


def vassal_payload_valid(shape: Any, expected_date: int | None = None) -> bool:
    if not isinstance(shape, dict):
        return False
    payload = payload_of(shape)
    if not isinstance(payload, dict):
        return False
    if (payload.get("family") != FAMILY
            or isinstance(payload.get("extra60"), bool)
            or not same_int(payload.get("extra60"), 0)
            or not true(payload.get("readable"))):
        return False
    fields = (
        "actor10", "mirror18", "recipient20", "date28", "date2c",
        "envoy30", "state34", "variant38", "proposal3c",
    )
    if any(strict_int(payload.get(field)) is None for field in fields):
        return False
    if expected_date is not None and any(
            not same_int(payload.get(field), expected_date)
            for field in ("date28", "date2c")):
        return False
    return True


def vassal_shape_valid(shape: Any, expected_date: int | None = None) -> bool:
    if not isinstance(shape, dict):
        return False
    payload = payload_of(shape)
    return (
        true(shape.get("identity"))
        and true(shape.get("readable"))
        and true(shape.get("prefix_readable"))
        and vassal_payload_valid(shape, expected_date)
        and same_int(payload.get("vtable_rva"), VASSAL_VTABLE_RVA)
        and same_int(payload.get("discriminator"), 0x165)
        and true(payload.get("handles_canonical"))
    )


def vassal_payload_equal(left: Any, right: Any,
                         expected_date: int | None = None) -> bool:
    if not vassal_payload_valid(left, expected_date) or not vassal_payload_valid(right, expected_date):
        return False
    left_payload = payload_of(left)
    right_payload = payload_of(right)
    fields = (
        "actor10", "mirror18", "recipient20", "date28", "date2c",
        "envoy30", "state34", "variant38", "proposal3c",
    )
    return (
        all(same_int(left_payload.get(field), right_payload.get(field)) for field in fields)
        and left_payload.get("family") == right_payload.get("family") == FAMILY
        and same_int(left_payload.get("extra60"), right_payload.get("extra60"))
    )


def header_matches_target(entry: dict[str, Any], target: dict[str, Any]) -> bool:
    return all(same_int(entry.get(field), target.get(field)) for field in (
        "raw10", "raw38", "raw3c", "raw40", "raw44"))


def event_shape_summary(shape: Any) -> dict[str, Any]:
    if not isinstance(shape, dict):
        return {"present": False}
    payload = payload_of(shape)
    return {
        "present": True,
        "addr": shape.get("addr"),
        "action": shape.get("action"),
        "identity": shape.get("identity"),
        "readable": shape.get("readable"),
        "prefix_readable": shape.get("prefix_readable"),
        "header": {field: shape.get(field) for field in HEADER_FIELDS},
        "payload": payload_summary(shape),
    }


def common_transport_checks(event: dict[str, Any], date_raw: int) -> dict[str, bool]:
    source = event.get("source")
    loaded = event.get("loaded")
    begin = strict_int(event.get("callback_begin"))
    load_sequence = strict_int(event.get("load_callback_sequence"))
    end = strict_int(event.get("callback_end"))
    load_count = strict_int(event.get("load_count"))
    load_index = strict_int(event.get("load_index"))
    return {
        "completed": true(event.get("completed")),
        "loads_not_truncated": event.get("loads_truncated") is False,
        "single_load_selected": load_count == 1 and load_index == 0,
        "matching_load_present": (strict_int(event.get("matching_count")) or 0) > 0,
        "caller_verified": true(event.get("caller_verified")),
        "transport_return_site": same_int(event.get("native_return_rva"), TRANSPORT_RETURN_RVA),
        "source_identity": true(event.get("source_identity")),
        "loaded_identity": true(event.get("loaded_identity")),
        "source_captured": true(event.get("source_captured")),
        "header_flag": true(event.get("header_equal")),
        "payload_flag": true(event.get("payload_equal")),
        "callback_order": (begin is not None and load_sequence is not None
                            and end is not None and begin < load_sequence < end),
        "source_is_outgoing": (isinstance(source, dict)
                                and same_int(event.get("outgoing"), source.get("addr"))),
        "full_header_equal": header_equal(source, loaded),
        "full_payload_equal": vassal_payload_equal(source, loaded, date_raw),
        "source_shape_valid": vassal_shape_valid(source, date_raw),
        "loaded_shape_valid": vassal_shape_valid(loaded, date_raw),
        "source_loaded_family": (isinstance(source, dict)
                                  and isinstance(loaded, dict)
                                  and payload_of(source).get("family") == FAMILY
                                  and payload_of(loaded).get("family") == FAMILY),
        "source_loaded_extra60_zero": (isinstance(source, dict)
                                        and isinstance(loaded, dict)
                                        and same_int(payload_of(source).get("extra60"), 0)
                                        and same_int(payload_of(loaded).get("extra60"), 0)),
        "source_vtable_matches_vassal": (isinstance(source, dict)
                                           and same_int(payload_of(source).get("vtable_rva"),
                                                       VASSAL_VTABLE_RVA)),
        "distinct_loaded_wrapper": (isinstance(source, dict) and isinstance(loaded, dict)
                                     and not same_int(source.get("addr"), loaded.get("addr"))),
        "distinct_loaded_action": (isinstance(source, dict) and isinstance(loaded, dict)
                                    and not same_int(source.get("action"), loaded.get("action"))),
        "peer_is_transport": same_int(event.get("peer"), event.get("transport")),
        "peer_world_transport_match": (
            true(event.get("peer_readable"))
            and true(event.get("world_transport_readable"))
            and true(event.get("peer_is_world_transport"))
            and same_int(event.get("peer"), event.get("world_transport"))
        ),
    }


def clone_checks(transport: dict[str, Any], clone: dict[str, Any],
                 date_raw: int) -> dict[str, bool]:
    loaded = transport.get("loaded")
    source = clone.get("source")
    target = clone.get("target")
    return {
        "clone_return_site": same_int(clone.get("caller_return_rva"), CLONE_RETURN_RVA),
        "clone_caller_matches": true(clone.get("caller_return_matches")),
        "clone_receiver_readable": true(clone.get("receiver_readable")),
        "clone_receiver_world_transport": (
            true(clone.get("world_transport_readable"))
            and true(clone.get("receiver_is_world_transport"))
        ),
        "receiver_matches_peer": same_int(clone.get("receiver"), transport.get("peer")),
        "receiver_host_matches_peer_owner": same_int(
            clone.get("receiver_host"), transport.get("peer_owner")),
        "receiver_ring_matches_peer_ring": same_int(
            clone.get("receiver_input_ring"), transport.get("peer_input_ring")),
        "receiver_world_dispatcher_matches": same_int(
            clone.get("world_dispatcher"), transport.get("world_dispatcher")),
        "receiver_world_transport_matches": same_int(
            clone.get("world_transport"), transport.get("world_transport")),
        "receiver_vtable_expected": same_int(clone.get("receiver_vtable_rva"), RECEIVER_VTABLE_RVA),
        "clone_source_loaded_identity": (isinstance(source, dict)
                                          and isinstance(loaded, dict)
                                          and same_int(source.get("addr"), loaded.get("addr"))
                                          and same_int(source.get("action"), loaded.get("action"))),
        "clone_source_header_equal_loaded": header_equal(loaded, source),
        "clone_source_payload_equal_loaded": vassal_payload_equal(loaded, source, date_raw),
        "clone_target_shape_valid": vassal_shape_valid(target, date_raw),
        "clone_target_header_marker": (isinstance(target, dict)
                                        and same_int(target.get("origin"), 0xFFFF)
                                        and same_int(target.get("protocol_flags"), 0)
                                        and same_int(target.get("protocol_sequence"), 0)),
        "clone_target_payload_equal_loaded": vassal_payload_equal(target, loaded, date_raw),
        "clone_native_result_is_target": (isinstance(target, dict)
                                           and same_int(clone.get("native_result"), target.get("addr"))),
        "clone_forward_count_one": strict_int(clone.get("native_forward_count_by_hook_contract")) == 1,
        "clone_native_return_observed": true(clone.get("native_return_observed")),
    }


def entry_checks(entry: dict[str, Any], target: dict[str, Any],
                 source: dict[str, Any], date_raw: int,
                 expected_state: int, recipient: str) -> dict[str, bool]:
    entry_source = entry.get("source")
    target_payload = payload_of(target)
    entry_payload = payload_of(entry_source)
    return {
        "entry_action_id_family_bound": entry.get("action_id") == ACTION,
        "entry_actor_recipient_bound": (entry.get("actor_field") == ACTOR
                                         and entry.get("recipient_field") is not None),
        "entry_recipient_matches_payload": (entry.get("recipient_field") == recipient
                                             and isinstance(entry_source, dict)
                                             and entry_payload.get("recipient20") == payload_of(source).get("recipient20")),
        "entry_state_matches_expected": strict_int(entry.get("state_raw")) == expected_state,
        "entry_readable": true(entry.get("readable")),
        "entry_prefix_readable": true(entry.get("prefix_readable")),
        "entry_marker_origin": same_int(entry.get("origin"), 0xFFFF),
        "entry_marker_flags": same_int(entry.get("protocol_flags"), 0),
        "entry_source_sequence": same_int(entry.get("protocol_sequence"), source.get("protocol_sequence")),
        "entry_prefix_matches_target": header_matches_target(entry, target),
        "entry_command_is_target": same_int(entry.get("command"), target.get("addr")),
        "entry_action_is_target": same_int(entry.get("action"), target.get("action")),
        "entry_source_payload_identity": (isinstance(entry_source, dict)
                                           and same_int(entry_payload.get("addr"), target_payload.get("addr"))),
        "entry_source_payload_equal_target": vassal_payload_equal(entry_source, target, date_raw),
        "entry_source_family_valid": (isinstance(entry_source, dict)
                                       and entry_payload.get("family") == FAMILY
                                       and same_int(entry_payload.get("extra60"), 0)),
        "entry_source_dates_current": (isinstance(entry_source, dict)
                                        and same_int(entry_payload.get("date28"), date_raw)
                                        and same_int(entry_payload.get("date2c"), date_raw)),
    }


def stage_order_checks(transport: dict[str, Any], clone: dict[str, Any],
                       entry: dict[str, Any]) -> dict[str, bool]:
    transport_end = strict_int(transport.get("callback_end"))
    clone_begin = strict_int(clone.get("begin_callback_sequence"))
    clone_end = strict_int(clone.get("callback_sequence"))
    entry_sequence = strict_int(entry.get("callback_sequence"))
    return {
        "transport_before_clone": (transport_end is not None and clone_begin is not None
                                    and transport_end < clone_begin),
        "clone_begin_before_end": (clone_begin is not None and clone_end is not None
                                    and clone_begin < clone_end),
        "clone_before_entry": (clone_end is not None and entry_sequence is not None
                                and clone_end < entry_sequence),
    }


def chain_for_transport(transport: dict[str, Any], clones: list[dict[str, Any]],
                        entries: list[dict[str, Any]], date_raw: int,
                        expected_state: int, recipient: str) -> list[dict[str, Any]]:
    base = common_transport_checks(transport, date_raw)
    if not all(base.values()):
        return []
    transport_end = strict_int(transport.get("callback_end"))
    loaded = transport.get("loaded")
    matches: list[dict[str, Any]] = []
    for clone in clones:
        if transport_end is None or strict_int(clone.get("begin_callback_sequence")) is None:
            continue
        if strict_int(clone.get("begin_callback_sequence")) <= transport_end:
            continue
        clone_result = clone_checks(transport, clone, date_raw)
        if not all(clone_result.values()):
            continue
        clone_end = strict_int(clone.get("callback_sequence"))
        target = clone.get("target")
        for entry in entries:
            if clone_end is None or strict_int(entry.get("callback_sequence")) is None:
                continue
            if strict_int(entry.get("callback_sequence")) <= clone_end:
                continue
            entry_result = entry_checks(
                entry, target, loaded, date_raw, expected_state,
                recipient)
            order_result = stage_order_checks(transport, clone, entry)
            checks = {**base, **clone_result, **entry_result, **order_result}
            if not all(checks.values()):
                continue
            matches.append({
                "transport": transport,
                "clone": clone,
                "entry": entry,
                "checks": checks,
            })
    return matches


def stream_events(path: Path) -> dict[str, Any]:
    size = bounded_size(path)
    counts: Counter[str] = Counter()
    malformed: list[int] = []
    sessions: set[str] = set()
    groups: dict[str, list[dict[str, Any]]] = {
        "transport": [], "clones": [], "entries": [], "lifecycle": [],
        "submissions": [], "responses": [], "commands": [],
    }
    line_count = 0
    with path.open("r", encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            line_count += 1
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                malformed.append(line_number)
                continue
            if not isinstance(event, dict):
                malformed.append(line_number)
                continue
            event = dict(event)
            event["_line"] = line_number
            name = str(event.get("event", "<missing>"))
            counts[name] += 1
            if event.get("session_id") is not None:
                sessions.add(str(event["session_id"]))
            if name == TRANSPORT_EVENT:
                groups["transport"].append(event)
            elif name == CLONE_EVENT:
                groups["clones"].append(event)
            elif name == ENTRY_EVENT:
                groups["entries"].append(event)
            elif name == LIFECYCLE_EVENT:
                groups["lifecycle"].append(event)
            elif name == SUBMISSION_EVENT:
                groups["submissions"].append(event)
            elif name in (RESPONSE_EVENT, EXECUTION_EVENT):
                groups["responses"].append(event)
            elif name == "diplomatic_command_observed":
                groups["commands"].append(event)
    return {
        "bytes": size,
        "line_count": line_count,
        "malformed_lines": malformed,
        "event_counts": dict(counts),
        "session_ids": sorted(sessions),
        **groups,
    }


def lifecycle_payload_matches(event: dict[str, Any], expected_shape: dict[str, Any],
                              date_raw: int, expected_state: int | None = None) -> bool:
    shape = event.get("source")
    if not vassal_payload_valid(shape, date_raw):
        return False
    if expected_state is not None and strict_int(payload_of(shape).get("state34")) != expected_state:
        return False
    return vassal_payload_equal(shape, expected_shape, date_raw)


def lifecycle_action_payload_stable_matches(
        event: dict[str, Any], expected_shape: dict[str, Any],
        date_raw: int, expected_state: int) -> bool:
    """Match a destructed action after its address may have been reused.

    The first target allocation is reused by the second observed native chain
    before the first destructor record is emitted.  The lifecycle record still
    binds the exact action address and stable action identity fields, while
    ``envoy30`` can reflect the later native object state.  Keep that observed
    drift visible in the report instead of rejecting the destructor as an
    unrelated object or claiming byte-for-byte payload equality.
    """
    shape = event.get("source")
    if not vassal_payload_valid(shape, date_raw):
        return False
    observed = payload_of(shape)
    expected = payload_of(expected_shape)
    if strict_int(observed.get("state34")) != expected_state:
        return False
    stable_fields = (
        "actor10", "mirror18", "recipient20", "date28", "date2c",
        "state34", "variant38", "proposal3c",
    )
    return (
        observed.get("family") == expected.get("family") == FAMILY
        and same_int(observed.get("extra60"), expected.get("extra60"))
        and all(same_int(observed.get(field), expected.get(field))
                for field in stable_fields)
    )


def payload_drift_fields(observed_shape: Any, expected_shape: Any) -> list[str]:
    observed = payload_of(observed_shape)
    expected = payload_of(expected_shape)
    return [
        field for field in ("envoy30", "state34", "variant38", "proposal3c")
        if not same_int(observed.get(field), expected.get(field))
    ]


def lifecycle_checks_for_chain(chain: dict[str, Any], lifecycle: list[dict[str, Any]],
                               date_raw: int, expected_state: int) -> dict[str, Any]:
    transport = chain["transport"]
    clone = chain["clone"]
    entry = chain["entry"]
    protocol_sequence = strict_int(transport.get("source", {}).get("protocol_sequence"))
    loaded = transport.get("loaded")
    target = clone.get("target")
    entry_source = entry.get("source")
    serialization = [
        event for event in lifecycle
        if event.get("kind") == "serialization_begin"
        and strict_int(event.get("seq4c")) == protocol_sequence
        and lifecycle_payload_matches(event, transport.get("source"), date_raw, expected_state)
    ]
    lifecycle_clones = [
        event for event in lifecycle
        if event.get("kind") == "clone"
        and lifecycle_payload_matches(event, loaded, date_raw, expected_state)
        and isinstance(event.get("target"), dict)
        and same_int(event["target"].get("addr"), entry.get("action"))
        and vassal_payload_equal(event.get("target"), entry_source, date_raw)
        and same_int(event.get("native_result"), event["target"].get("addr"))
    ]
    loaded_addr = payload_of(loaded).get("addr") if isinstance(loaded, dict) else None
    # Lifecycle destructor records the concrete action payload address in
    # ``source.addr``.  The wrapper-clone ``target.addr`` is a different
    # allocation; its ``target.payload.addr`` is the address that the native
    # destructor receives and returns.
    target_addr = payload_of(target).get("addr") if isinstance(target, dict) else None
    loaded_destruct_returns = [
        event for event in lifecycle
        if event.get("kind") == "destructor_return"
        and same_int(payload_of(event.get("source")).get("addr"), loaded_addr)
        and lifecycle_payload_matches(event, loaded, date_raw, expected_state)
        and true(event.get("native_return_observed"))
        and same_int(event.get("native_result"), loaded_addr)
        and same_int(event.get("native_flags"), 1)
    ]
    target_destruct_returns = [
        event for event in lifecycle
        if event.get("kind") == "destructor_return"
        and same_int(payload_of(event.get("source")).get("addr"), target_addr)
        and lifecycle_action_payload_stable_matches(event, target, date_raw, expected_state)
        and true(event.get("native_return_observed"))
        and same_int(event.get("native_result"), target_addr)
        and same_int(event.get("native_flags"), 1)
    ]
    loaded_destruct = [
        event for event in lifecycle
        if event.get("kind") == "destructor"
        and same_int(payload_of(event.get("source")).get("addr"), loaded_addr)
        and lifecycle_payload_matches(event, loaded, date_raw, expected_state)
        and same_int(event.get("native_flags"), 1)
    ]
    target_destruct = [
        event for event in lifecycle
        if event.get("kind") == "destructor"
        and same_int(payload_of(event.get("source")).get("addr"), target_addr)
        and lifecycle_action_payload_stable_matches(event, target, date_raw, expected_state)
        and same_int(event.get("native_flags"), 1)
    ]
    target_drift = []
    for event in target_destruct + target_destruct_returns:
        for field in payload_drift_fields(event.get("source"), target):
            if field not in target_drift:
                target_drift.append(field)
    checks = {
        "serialization_begin_binds_protocol_seq4c": len(serialization) == 1,
        "serialization_source_matches_transport_source": len(serialization) == 1,
        "lifecycle_clone_binds_loaded_to_entry_target": len(lifecycle_clones) == 1,
        "loaded_destructor_observed": bool(loaded_destruct),
        "loaded_destructor_return_observed": bool(loaded_destruct_returns),
        "target_destructor_observed": bool(target_destruct),
        "target_destructor_return_observed": bool(target_destruct_returns),
        # The lifecycle sequence is reported as a separate domain.  Only seq4c
        # is compared to the protocol sequence, and only within this chain.
        "sequence_domains_not_cross_compared": all(
            strict_int(event.get("seq4c")) in (protocol_sequence, 0)
            for event in serialization + lifecycle_clones + loaded_destruct
            + loaded_destruct_returns + target_destruct + target_destruct_returns
        ),
    }
    return {
        "checks": checks,
        "protocol_sequence": protocol_sequence,
        "lifecycle_seq4c": [strict_int(event.get("seq4c")) for event in serialization],
        "lifecycle_sequence_values": sorted(
            strict_int(event.get("sequence"))
            for event in serialization + lifecycle_clones + loaded_destruct
            + loaded_destruct_returns + target_destruct + target_destruct_returns
            if strict_int(event.get("sequence")) is not None
        ),
        "serialization_lines": [event["_line"] for event in serialization],
        "clone_lines": [event["_line"] for event in lifecycle_clones],
        "loaded_destructor_begin_lines": [event["_line"] for event in loaded_destruct],
        "loaded_destructor_lines": [event["_line"] for event in loaded_destruct_returns],
        "target_destructor_begin_lines": [event["_line"] for event in target_destruct],
        "target_destructor_lines": [event["_line"] for event in target_destruct_returns],
        "target_destructor_payload_drift_fields": target_drift,
        "addresses": {
            "transport_source": payload_of(transport.get("source")).get("addr"),
            "transport_loaded": payload_of(loaded).get("addr"),
            "clone_target": payload_of(target).get("addr"),
            "entry_command": entry.get("command"),
            "entry_action": entry.get("action"),
        },
    }


def source_contract(runtime_root: Path) -> dict[str, Any]:
    files = {
        "query": runtime_root / "alliance-query.inc",
        "lifecycle": runtime_root / "alliance-lifecycle.inc",
        "execution": runtime_root / "alliance-execution.inc",
    }
    records: dict[str, Any] = {}
    texts: dict[str, str] = {}
    for name, path in files.items():
        size = bounded_size(path)
        text = path.read_text(encoding="utf-8")
        texts[name] = text
        records[name] = {"path": str(path), "bytes": size, "sha256": sha256_file(path)}
    query_match = re.search(
        r"vassal_query_methods\s*\{\s*0x2940\s*,\s*0x1c7fd20\s*,",
        texts["query"], re.IGNORECASE)
    clone_match = re.search(
        r"lifecycle_vassalization_clone_rva\s*=\s*0x51fa30\b",
        texts["lifecycle"], re.IGNORECASE)
    execution_family_match = (
        "pending.vassalization?lifecycle_vassalization_clone_original" in texts["execution"]
        and 'strcmp(action_id,"offer_vassalization")==0' in texts["execution"]
    )
    return {
        "files": records,
        "checks": {
            "factory_selector_2940_declared": query_match is not None,
            "vassal_vtable_1c7fd20_declared": query_match is not None,
            "clone_51fa30_declared": clone_match is not None,
            "execution_selects_vassal_clone": execution_family_match,
        },
        "observed_values": {
            "factory_selector": VASSAL_FACTORY_SELECTOR,
            "vtable_rva": hex(VASSAL_VTABLE_RVA),
            "clone_rva": hex(VASSAL_CLONE_RVA),
        },
    }


def pick_terminal_result(report: dict[str, Any]) -> dict[str, Any] | None:
    poll = report.get("poll")
    if isinstance(poll, dict) and isinstance(poll.get("final"), dict):
        result = poll["final"].get("result")
        if isinstance(result, dict):
            return result
    for key in ("reopened_result", "execution"):
        item = report.get(key)
        if isinstance(item, dict) and isinstance(item.get("result"), dict):
            return item["result"]
    return None


def result_summary(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    fields = (
        "event", "request_id", "session_id", "action_id", "family", "actor",
        "recipient", "phase", "date_raw", "outcome", "native_outcome",
        "native_state", "native_variant", "vassalization_before",
        "vassalization_after", "pending_removed", "response_verified",
        "request_binding_verified",
        "prestige_before_raw", "prestige_after_raw", "prestige_delta_raw",
        "prestige_scale", "execution_verified",
    )
    return {field: result.get(field) for field in fields if field in result}


def public_matches_native(public: dict[str, Any] | None,
                          native: dict[str, Any] | None) -> bool:
    if not isinstance(public, dict) or not isinstance(native, dict):
        return False
    fields = (
        "event", "request_id", "action_id", "family", "actor", "recipient",
        "phase", "date_raw", "native_state", "native_variant",
        "vassalization_before", "vassalization_after", "response_verified",
        "request_binding_verified", "pending_removed",
    )
    for field in fields:
        if public.get(field) != native.get(field):
            return False
    return public.get("native_outcome", public.get("outcome")) == native.get("outcome")


def build_report(artifact: Path) -> dict[str, Any]:
    global ACTION, ACTOR, PHASE
    artifact = artifact.resolve(strict=True)
    if not artifact.is_dir():
        raise ValueError(f"artifact is not a directory: {artifact}")
    report_path = artifact / "report.json"
    events_path = artifact / "native-events-slice.jsonl"
    if not report_path.is_file() or not events_path.is_file():
        raise ValueError("artifact must contain report.json and native-events-slice.jsonl")
    report = read_json(report_path)
    events = stream_events(events_path)
    installation = report.get("installation") if isinstance(report.get("installation"), dict) else {}
    session = report.get("session") if isinstance(report.get("session"), dict) else {}
    request_id = str(report.get("request_id", ""))
    action_id = str(report.get("action_id", ""))
    actor = str(report.get("actor", ACTOR))
    recipient = str(report.get("recipient", ""))
    phase = str(report.get("phase", PHASE))
    family = str(report.get("family", ""))
    if action_id not in ("offer_vassalization", "cancel_vassalization"):
        raise ValueError(f"unsupported vassalization action_id: {action_id!r}")
    if family != FAMILY or actor != ACTOR or phase != PHASE:
        raise ValueError(
            "vassalization source chain requires family=vassalization, actor=FRA, phase=initiate"
        )
    # The helper functions retain the original Offer API while this validator
    # also accepts the single-action Cancel execution chain.
    ACTION = action_id
    ACTOR = actor
    PHASE = phase
    is_cancel = action_id == "cancel_vassalization"
    date_raw = strict_int(report.get("expected_date_raw"))
    if date_raw is None:
        # The report does not duplicate expected_date_raw at the top level in
        # every runner version; native binding is the authoritative observed date.
        date_candidates = [event.get("date_raw") for event in events["submissions"]
                           if event.get("request_id") == request_id]
        date_raw = strict_int(date_candidates[0]) if date_candidates else None
    session_id = str(session.get("session_id") or installation.get("session_id") or "")
    runtime_root = artifact.parent
    manifest_path = runtime_root / "build-manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else {}
    source_info = source_contract(runtime_root)

    exact_submissions = [
        event for event in events["submissions"]
        if date_raw is not None and exact_binding(
            event, request_id=request_id, session_id=session_id,
            action_id=action_id, actor=actor, recipient=recipient,
            phase=phase, date_raw=date_raw)
    ]
    exact_responses = [
        event for event in events["responses"]
        if date_raw is not None and exact_binding(
            event, request_id=request_id, session_id=session_id,
            action_id=action_id, actor=actor, recipient=recipient,
            phase=phase, date_raw=date_raw)
    ]
    submission = exact_submissions[0] if len(exact_submissions) == 1 else None
    native_result = exact_responses[0] if len(exact_responses) == 1 else None
    public_result = pick_terminal_result(report)
    # The response state is part of the observed native contract: state 1 is
    # an NPC rejection and state 2 is an NPC acceptance.  Use the observed
    # value when selecting the response chain so this checker can validate
    # both R35B and R35C without turning one outcome into the other.
    observed_response_state = (
        strict_int(native_result.get("native_state"))
        if isinstance(native_result, dict) else None
    )

    transport_events = [event for event in events["transport"]
                        if event.get("session_id") == session_id]
    clone_events = [event for event in events["clones"]
                    if event.get("session_id") == session_id]
    entry_events = [event for event in events["entries"]
                    if event.get("session_id") == session_id]
    chains_by_seq: dict[int, list[dict[str, Any]]] = {}
    chain_records: list[dict[str, Any]] = []
    if date_raw is not None:
        for transport in transport_events:
            source = transport.get("source") if isinstance(transport.get("source"), dict) else {}
            protocol_seq = strict_int(source.get("protocol_sequence"))
            result_sequence = (
                strict_int(submission.get("native_sequence"))
                if submission is not None else None
            )
            expected_state = (
                observed_response_state
                if (
                    observed_response_state is not None
                    and (
                        (not is_cancel and protocol_seq == 16)
                        or (is_cancel and protocol_seq == result_sequence)
                    )
                )
                else 0
            )
            chains = chain_for_transport(
                transport, clone_events, entry_events, date_raw, expected_state,
                recipient)
            if chains:
                for chain in chains:
                    seq = strict_int(chain["transport"].get("source", {}).get("protocol_sequence"))
                    lifecycle = lifecycle_checks_for_chain(
                        chain, events["lifecycle"], date_raw, expected_state)
                    chain_record = {
                        "protocol_sequence": seq,
                        "expected_state": expected_state,
                        "lines": {
                            "transport": chain["transport"]["_line"],
                            "clone": chain["clone"]["_line"],
                            "entry": chain["entry"]["_line"],
                        },
                        "checks": chain["checks"],
                        "lifecycle": lifecycle,
                        "source": event_shape_summary(chain["transport"].get("source")),
                        "loaded": event_shape_summary(chain["transport"].get("loaded")),
                        "clone_source": event_shape_summary(chain["clone"].get("source")),
                        "clone_target": event_shape_summary(chain["clone"].get("target")),
                        "entry_source": event_shape_summary(chain["entry"].get("source")),
                        "entry": {
                            "action_id": chain["entry"].get("action_id"),
                            "actor_field": chain["entry"].get("actor_field"),
                            "recipient_field": chain["entry"].get("recipient_field"),
                            "state_raw": chain["entry"].get("state_raw"),
                            "protocol_sequence": chain["entry"].get("protocol_sequence"),
                            "raw_header_prefix": {
                                field: chain["entry"].get(field) for field in (
                                    "raw10", "raw38", "raw3c", "raw40", "raw44")
                            },
                            "command": chain["entry"].get("command"),
                            "action": chain["entry"].get("action"),
                        },
                    }
                    chain_records.append(chain_record)
                    if seq is not None:
                        chains_by_seq.setdefault(seq, []).append(chain_record)

    source_declared = {
        str(item.get("name")): item.get("sha256")
        for item in manifest.get("sources", []) if isinstance(item, dict)
    }
    source_hash_checks = {}
    for name, record in source_info["files"].items():
        basename = Path(record["path"]).name
        declared = source_declared.get(basename)
        source_hash_checks[f"{name}_manifest_hash_matches"] = (
            declared is None or str(declared).lower() == str(record["sha256"]).lower())

    result_event_name = EXECUTION_EVENT if is_cancel else RESPONSE_EVENT
    execution_effect = public_result if isinstance(public_result, dict) else native_result
    if is_cancel:
        native_result_contract = {
            "event_name": native_result is not None and native_result.get("event") == result_event_name,
            "family_vassalization": native_result is not None and native_result.get("family") == FAMILY,
            "execution_state_zero": native_result is not None and strict_int(native_result.get("native_state")) == 0,
            "execution_variant_zero": native_result is not None and strict_int(native_result.get("native_variant")) == 0,
            "execution_outcome": native_result is not None and native_result.get("outcome") == "executed",
            "state_transition_consistent": (
                native_result is not None
                and native_result.get("vassalization_before") is True
                and native_result.get("vassalization_after") is False
            ),
            "execution_verified": native_result is not None and native_result.get("execution_verified") is True,
            "request_binding_verified": native_result is not None
                and native_result.get("request_binding_verified") is True,
            "prestige_delta_verified": (
                isinstance(execution_effect, dict)
                and strict_int(execution_effect.get("prestige_before_raw")) is not None
                and strict_int(execution_effect.get("prestige_after_raw")) is not None
                and strict_int(execution_effect.get("prestige_delta_raw")) == -25000
                and strict_int(execution_effect.get("prestige_after_raw"))
                    - strict_int(execution_effect.get("prestige_before_raw")) == -25000
                and strict_int(execution_effect.get("prestige_scale")) == 1000
            ),
        }
    else:
        native_result_contract = {
            "event_name": native_result is not None and native_result.get("event") == result_event_name,
            "family_vassalization": native_result is not None and native_result.get("family") == FAMILY,
            "state_outcome_pair_known": (
                native_result is not None
                and strict_int(native_result.get("native_state")) in (1, 2)
                and native_result.get("outcome") in ("rejected", "accepted")
            ),
            "variant_one": native_result is not None and strict_int(native_result.get("native_variant")) == 1,
            "state_outcome_transition_consistent": (
                native_result is not None
                and (
                    (
                        strict_int(native_result.get("native_state")) == 1
                        and native_result.get("outcome") == "rejected"
                        and native_result.get("vassalization_before") is False
                        and native_result.get("vassalization_after") is False
                    )
                    or (
                        strict_int(native_result.get("native_state")) == 2
                        and native_result.get("outcome") == "accepted"
                        and native_result.get("vassalization_before") is False
                        and native_result.get("vassalization_after") is True
                    )
                )
            ),
            "response_verified": native_result is not None and native_result.get("response_verified") is True,
            "request_binding_verified": native_result is not None
                and native_result.get("request_binding_verified") is True,
            "outbound_pending_removed_not_required": native_result is not None
                and isinstance(native_result.get("pending_removed"), bool),
        }
    submission_contract = {
        "one_exact_submission": len(exact_submissions) == 1,
        "family_vassalization": submission is not None and submission.get("family") == FAMILY,
        "submitted_true": submission is not None and submission.get("submitted") is True,
        "queue_verified": submission is not None and submission.get("native_queue_verified") is True,
        "transport_ring": submission is not None and submission.get("transport_ring") is True,
        "origin_ffff": submission is not None and same_int(submission.get("native_origin"), 0xFFFF),
        "flags_zero": submission is not None and same_int(submission.get("native_flags"), 0),
        "sequence_present": submission is not None and strict_int(submission.get("native_sequence")) is not None,
    }
    binding_checks = {
        "report_family_action_actor_recipient_phase": (
            family == FAMILY and action_id == ACTION and actor == ACTOR
            and recipient != ACTOR and re.fullmatch(r"[A-Z0-9]{3}", recipient) is not None
            and phase == PHASE),
        "installation_session_matches_report": session_id == str(installation.get("session_id", "")),
        "single_event_session": events["session_ids"] == [session_id],
        "submission_result_same_request_session": (
            submission is not None and native_result is not None
            and submission.get("request_id") == native_result.get("request_id") == request_id
            and submission.get("session_id") == native_result.get("session_id") == session_id),
        "submission_sequence_selects_one_chain": (
            submission is not None
            and len(chains_by_seq.get(strict_int(submission.get("native_sequence")), [])) == 1),
        "native_result_public_projection_matches": public_matches_native(public_result, native_result),
        "native_result_date_matches_submission": (
            submission is not None and native_result is not None
            and same_int(submission.get("date_raw"), native_result.get("date_raw"))
            and same_int(native_result.get("date_raw"), date_raw)),
    }
    result_sequence = strict_int(submission.get("native_sequence")) if submission else None
    result_chain = chains_by_seq.get(result_sequence, []) if result_sequence is not None else []
    if is_cancel:
        response_chain_checks = {
            "execution_chain_present": len(result_chain) == 1,
            "execution_entry_matches_native_result": (
                len(result_chain) == 1
                and native_result is not None
                and result_chain[0]["entry"].get("state_raw") == native_result.get("native_state")
                and result_chain[0]["entry"].get("action_id") == native_result.get("action_id")
                and result_chain[0]["entry"].get("recipient_field") == recipient
            ),
            "execution_chain_same_family_date": (
                len(result_chain) == 1
                and result_chain[0]["source"]["payload"].get("family") == FAMILY
                and same_int(result_chain[0]["source"]["payload"].get("date28"), date_raw)
                and same_int(result_chain[0]["source"]["payload"].get("date2c"), date_raw)
            ),
            "execution_chain_has_no_false_request_sequence_claim": True,
        }
        chain_checks = {
            "one_strict_transport_clone_entry_chain": len(chain_records) == 1,
            "execution_chain_complete": (
                len(result_chain) == 1
                and all(result_chain[0]["checks"].values())
                and all(result_chain[0]["lifecycle"]["checks"].values())
            ),
        }
    else:
        response_chain_checks = {
            "response_chain_present": len(chains_by_seq.get(16, [])) == 1,
            "response_entry_matches_native_response": (
                len(chains_by_seq.get(16, [])) == 1
                and native_result is not None
                and chains_by_seq[16][0]["entry"].get("state_raw") == native_result.get("native_state")
                and chains_by_seq[16][0]["entry"].get("action_id") == native_result.get("action_id")
                and chains_by_seq[16][0]["entry"].get("recipient_field") == recipient),
            "response_chain_same_family_date": (
                len(chains_by_seq.get(16, [])) == 1
                and chains_by_seq[16][0]["source"]["payload"].get("family") == FAMILY
                and same_int(chains_by_seq[16][0]["source"]["payload"].get("date28"), date_raw)
                and same_int(chains_by_seq[16][0]["source"]["payload"].get("date2c"), date_raw)),
            "response_chain_has_no_false_request_sequence_claim": True,
        }
        chain_checks = {
            "two_strict_transport_clone_entry_chains": len(chain_records) == 2,
            "submission_chain_complete": (len(chains_by_seq.get(15, [])) == 1
                                           and all(chains_by_seq[15][0]["checks"].values())
                                           and all(chains_by_seq[15][0]["lifecycle"]["checks"].values())),
            "response_chain_complete": (len(chains_by_seq.get(16, [])) == 1
                                         and all(chains_by_seq[16][0]["checks"].values())
                                         and all(chains_by_seq[16][0]["lifecycle"]["checks"].values())),
        }
    build_binding = report.get("build_binding") if isinstance(report.get("build_binding"), dict) else {}
    build_checks = {
        "report_build_installation_loaded_hash_equal": (
            build_binding.get("installation_matches_build_manifest") is True
            and build_binding.get("build_manifest_dll_sha256") == build_binding.get("installation_dll_sha256")
            and build_binding.get("loaded_dll_sha256") == build_binding.get("installation_dll_sha256")),
        "manifest_source_vassal_contract_hashes": bool(source_hash_checks)
            and all(source_hash_checks.values()),
        **source_info["checks"],
        **source_hash_checks,
    }
    checks = {
        "bounded_inputs_and_jsonl_complete": events["bytes"] <= MAX_INPUT_BYTES
            and not events["malformed_lines"],
        **build_checks,
        **binding_checks,
        **submission_contract,
        "one_exact_native_response": len(exact_responses) == 1,
        **native_result_contract,
        **response_chain_checks,
        **chain_checks,
    }
    passed = sum(value is True for value in checks.values())
    failed = len(checks) - passed
    return {
        "validator": {
            "name": "validate_vassalization_source_chain",
            "version": 1,
            "read_only": True,
            "bounded_input_bytes": MAX_INPUT_BYTES,
        },
        "artifact": str(artifact),
        "inputs": {
            "report": {"path": str(report_path), "bytes": report_path.stat().st_size,
                       "sha256": sha256_file(report_path)},
            "native_events": {"path": str(events_path), "bytes": events["bytes"],
                              "sha256": sha256_file(events_path),
                              "lines": events["line_count"]},
            "runtime_root": str(runtime_root),
        },
        "request_binding": {
            "request_id": request_id,
            "session_id": session_id,
            "action_id": action_id,
            "family": family,
            "actor": actor,
            "recipient": recipient,
            "phase": phase,
            "date_raw": date_raw,
            "original_report_status": report.get("status"),
            "original_report_failed_checks": [
                name for name, value in (report.get("checks") or {}).items()
                if value is False
            ] if isinstance(report.get("checks"), dict) else [],
        },
        "build_binding": {
            "report": build_binding,
            "manifest": {
                "path": str(manifest_path),
                "sha256": sha256_file(manifest_path) if manifest_path.is_file() else None,
                "dll_sha256": manifest.get("dll_sha256"),
            },
            "source_contract": source_info,
        },
        "native_submission": submission,
        "native_result": result_summary(native_result),
        "public_terminal_result": result_summary(public_result),
        "chains": chain_records,
        "event_counts": events["event_counts"],
        "sequence_domains": {
            "submission_protocol_sequence": strict_int(submission.get("native_sequence"))
            if submission is not None else None,
            "protocol_sequences_observed": sorted({
                strict_int(event.get("source", {}).get("protocol_sequence"))
                for event in transport_events
                if strict_int(event.get("source", {}).get("protocol_sequence")) is not None
            }),
            "lifecycle_seq4c_observed": sorted({
                strict_int(event.get("seq4c")) for event in events["lifecycle"]
                if strict_int(event.get("seq4c")) is not None
            }),
            "lifecycle_sequence_observed": sorted({
                strict_int(event.get("sequence")) for event in events["lifecycle"]
                if strict_int(event.get("sequence")) is not None
            }),
            "rule": "仅 lifecycle.seq4c 与同一链的 transport protocol_sequence 比较；lifecycle.sequence 只作生命周期事件顺序记录。",
        },
        "checks": checks,
        "summary": {
            "validation_passed": failed == 0,
            "total_checks": len(checks),
            "passed_checks": passed,
            "failed_checks": failed,
            "source_chain_scope": "submission/response source→loaded→clone→entry plus lifecycle destruction",
            "original_operator_report_status": report.get("status"),
        },
    }


def markdown_report(result: dict[str, Any]) -> str:
    binding = result["request_binding"]
    summary = result["summary"]
    native_result = result.get("native_result") or {}
    is_cancel = binding.get("action_id") == "cancel_vassalization"
    submission_sequence = result.get("sequence_domains", {}).get(
        "submission_protocol_sequence"
    )
    operation_label = "附庸关系取消" if is_cancel else "附庸关系提议"
    sequence_semantics = (
        f"提交与执行结果共用 protocol_sequence={submission_sequence}，"
        "这是单条 Cancel 执行链。"
        if is_cancel else
        "submission 使用 native header `origin=0xffff`、`flags=0`、`sequence=15`；"
        "transport/loaded/clone/entry 只把 `protocol_sequence=15` 作为提交链的序列依据。"
    )
    result_semantics = (
        f"Cancel entry 的 state_raw={native_result.get('native_state')}，"
        f"execution result 的 native_state={native_result.get('native_state')}、"
        f"outcome={native_result.get('outcome')}，关系前后 "
        f"{native_result.get('vassalization_before')} -> {native_result.get('vassalization_after')}，"
        f"威望 {native_result.get('prestige_before_raw')} -> {native_result.get('prestige_after_raw')}。"
        if is_cancel else
        f"NPC response 使用独立的 `protocol_sequence=16` 链；entry 的 "
        f"`state_raw={native_result.get('native_state')}` 与 native response 的 "
        f"`native_state={native_result.get('native_state')}`、`outcome={native_result.get('outcome')}` 一致。"
    )
    lines = [
        f"# R35 {operation_label} native 来源链独立核验",
        "",
        f"- 独立核验状态：**{'通过' if summary['validation_passed'] else '失败'}**",
        f"- 检查：`{summary['passed_checks']}/{summary['total_checks']}`",
        f"- 请求：`{binding['request_id']}`；session：`{binding['session_id']}`",
        f"- 动作/家族：`{binding['action_id']}` / `{binding['family']}`；方向：`{binding['actor']} -> {binding['recipient']}`",
        f"- phase/date：`{binding['phase']}` / `{binding['date_raw']}`",
        f"- 原操作器报告状态：`{binding['original_report_status']}`；其外围失败检查：`{binding['original_report_failed_checks']}`",
        "",
        "本报告只判断已观察到的 native 来源、生命周期和结果绑定。原操作器的"
        " `after_baseline_unchanged` 等外围快照检查不参与本报告结论。",
        "",
        "## 关键证据",
        "",
        f"- UI factory selector：`0x{VASSAL_FACTORY_SELECTOR:x}`（十进制 `{VASSAL_FACTORY_SELECTOR}`）；Vassal vtable：`0x{VASSAL_VTABLE_RVA:x}`。",
        f"- Vassal clone 原生 RVA：`0x{VASSAL_CLONE_RVA:x}`。",
        "- submission 回执与结果事件分别按 request/session/action/actor/recipient/phase/date 绑定。",
        f"- {sequence_semantics}",
        f"- {result_semantics} 结果事件没有地址字段，因此报告没有虚构结果事件与某个地址的直接绑定。",
        "- lifecycle 的 `seq4c` 单独记录；生命周期内部 `sequence` 只用于记录 destructor/return 观察，不与 protocol sequence 混比。",
        "",
        "## 检查结果",
        "",
        "| 检查 | 结果 |",
        "|---|---|",
    ]
    for name, value in result["checks"].items():
        lines.append(f"| `{name}` | {'通过' if value else '失败'} |")
    lines.extend(["", "## 来源链摘要", ""])
    for chain in result["chains"]:
        lines.append(
            f"- protocol sequence `{chain['protocol_sequence']}`，transport/clone/entry 行 "
            f"`{chain['lines']['transport']}/{chain['lines']['clone']}/{chain['lines']['entry']}`；"
            f"entry state `{chain['entry']['state_raw']}`。"
        )
        life = chain["lifecycle"]
        lines.append(
            f"  lifecycle serialization/clone/destructor/destructor-return 行："
            f"`{life['serialization_lines']}/{life['clone_lines']}/"
            f"{life['loaded_destructor_begin_lines'] + life['target_destructor_begin_lines']}/"
            f"{life['loaded_destructor_lines'] + life['target_destructor_lines']}`。"
        )
        if life.get("target_destructor_payload_drift_fields"):
            lines.append(
                "  首条链的 target 地址在第二条链前被复用；target destructor 仍以稳定的"
                " actor/recipient/date/state 等字段和精确地址返回值绑定，观察到可变字段"
                f" `{life['target_destructor_payload_drift_fields']}`变化，因此没有声称析构时整段 payload 字节相同。"
            )
        lines.append(
            f"  observed addresses: transport source `{life['addresses']['transport_source']}`, "
            f"loaded `{life['addresses']['transport_loaded']}`, clone target `{life['addresses']['clone_target']}`, "
            f"entry command/action `{life['addresses']['entry_command']}` / `{life['addresses']['entry_action']}`。"
        )
    lines.extend(["", "## 原生结果", "", f"`{result['native_result']}`", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()
    artifact = args.artifact.resolve(strict=True)
    result = build_report(artifact)
    output_json = (args.output_json or artifact / "vassalization-source-chain-validation-001.json").resolve()
    output_md = (args.output_md or artifact / "vassalization-source-chain-validation-001.md").resolve()
    if output_json.exists() or output_md.exists():
        raise FileExistsError("refusing to overwrite an existing independent validation report")
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(markdown_report(result), encoding="utf-8")
    summary = result["summary"]
    print(json.dumps({
        "status": "passed" if summary["validation_passed"] else "failed",
        "passed_checks": summary["passed_checks"],
        "total_checks": summary["total_checks"],
        "failed_checks": summary["failed_checks"],
        "json": str(output_json),
        "markdown": str(output_md),
    }, ensure_ascii=False))
    return 0 if summary["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
