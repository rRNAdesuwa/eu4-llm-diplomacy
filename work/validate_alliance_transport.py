#!/usr/bin/env python3
"""Validate the observed native transport -> clone -> command source chain.

The validator consumes the independent lifecycle JSONL log.  It deliberately
does not consume transport-events.json, and it never treats a queue flag or a
pipeline observation as a submission or business acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


TRANSPORT_EVENT = "native_alliance_transport_completed"
CLONE_EVENT = "native_alliance_wrapper_clone"
ENTRY_EVENT = "native_alliance_command_entry_observed"
RELEVANT_EVENTS = {TRANSPORT_EVENT, CLONE_EVENT, ENTRY_EVENT}
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
ALLIANCE_VTABLE_RVA = 0x1C80720
ROYAL_VTABLE_RVA = 0x1C80AB0
SUPPORT_INDEPENDENCE_VTABLE_RVA = 0x1C805F0
MILITARY_ACCESS_VTABLE_RVA = 0x1C7FB70
VASSALIZATION_VTABLE_RVA = 0x1C7FD20
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def as_int(value: Any, default: int | None = None) -> int | None:
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
                return default
    return default


def same_int(left: Any, right: Any) -> bool:
    left_int = as_int(left)
    right_int = as_int(right)
    return left_int is not None and right_int is not None and left_int == right_int


def true_value(value: Any) -> bool:
    return value is True


def payload_of(shape: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(shape, dict):
        return {}
    payload = shape.get("payload")
    return payload if isinstance(payload, dict) else shape


def expected_vtable_for_family(family: str) -> int:
    if family == "royal_marriage":
        return ROYAL_VTABLE_RVA
    if family == "support_independence":
        return SUPPORT_INDEPENDENCE_VTABLE_RVA
    if family == "military_access":
        return MILITARY_ACCESS_VTABLE_RVA
    if family == "vassalization":
        return VASSALIZATION_VTABLE_RVA
    return ALLIANCE_VTABLE_RVA


def family_for_action(action_id: str | None) -> str | None:
    if action_id in ("offer_royal_marriage", "break_royal_ties"):
        return "royal_marriage"
    if action_id in ("offer_alliance", "dissolve_alliance"):
        return "alliance"
    if action_id in ("ask_military_access", "cancel_military_access"):
        return "military_access"
    if action_id in ("offer_vassalization", "cancel_vassalization"):
        return "vassalization"
    return None


def family_from_shape(shape: dict[str, Any] | None) -> str:
    payload = payload_of(shape)
    if payload.get(FAMILY_FIELD) in (
        "royal_marriage", "support_independence", "military_access",
        "vassalization",
    ):
        return str(payload.get(FAMILY_FIELD))
    return "alliance"


def payload_family_extra_valid(shape: dict[str, Any] | None,
                               family: str = "alliance") -> bool:
    payload = payload_of(shape)
    if family == "royal_marriage":
        return (
            FAMILY_FIELD in payload and EXTRA60_FIELD in payload
            and payload.get(FAMILY_FIELD) == "royal_marriage"
            and not isinstance(payload.get(EXTRA60_FIELD), bool)
            and as_int(payload.get(EXTRA60_FIELD)) == 0
        )
    if family == "support_independence":
        return (
            payload.get(FAMILY_FIELD) == "support_independence"
            and not isinstance(payload.get(EXTRA60_FIELD, 0), bool)
            and as_int(payload.get(EXTRA60_FIELD, 0)) == 0
        )
    if family == "military_access":
        return (
            payload.get(FAMILY_FIELD) == "military_access"
            and not isinstance(payload.get(EXTRA60_FIELD, 0), bool)
            and as_int(payload.get(EXTRA60_FIELD, 0)) == 0
        )
    if family == "vassalization":
        return (
            payload.get(FAMILY_FIELD) == "vassalization"
            and not isinstance(payload.get(EXTRA60_FIELD, 0), bool)
            and as_int(payload.get(EXTRA60_FIELD, 0)) == 0
        )
    return (
        payload.get(FAMILY_FIELD, "alliance") == "alliance"
        and not isinstance(payload.get(EXTRA60_FIELD, 0), bool)
        and as_int(payload.get(EXTRA60_FIELD, 0)) == 0
    )


def payload_readable(shape: dict[str, Any] | None, family: str = "alliance") -> bool:
    payload = payload_of(shape)
    return true_value(payload.get("readable")) and all(
        field in payload and as_int(payload.get(field)) is not None for field in PAYLOAD_FIELDS
    ) and payload_family_extra_valid(shape, family)


def payload_equal(left: dict[str, Any] | None, right: dict[str, Any] | None,
                  family: str = "alliance") -> bool:
    if not payload_readable(left, family) or not payload_readable(right, family):
        return False
    left_payload = payload_of(left)
    right_payload = payload_of(right)
    return (
        all(same_int(left_payload.get(field), right_payload.get(field)) for field in PAYLOAD_FIELDS)
        and left_payload.get(FAMILY_FIELD, "alliance")
        == right_payload.get(FAMILY_FIELD, "alliance") == family
        and not isinstance(left_payload.get(EXTRA60_FIELD, 0), bool)
        and not isinstance(right_payload.get(EXTRA60_FIELD, 0), bool)
        and same_int(left_payload.get(EXTRA60_FIELD, 0), right_payload.get(EXTRA60_FIELD, 0))
    )


def shape_valid(shape: dict[str, Any] | None, family: str = "alliance") -> bool:
    if not isinstance(shape, dict):
        return False
    payload = payload_of(shape)
    return (
        true_value(shape.get("identity"))
        and true_value(shape.get("readable"))
        and true_value(shape.get("prefix_readable"))
        and payload_readable(shape, family)
        and same_int(payload.get("vtable_rva"), expected_vtable_for_family(family))
        and same_int(payload.get("discriminator"), 0x165)
        and true_value(payload.get("handles_canonical"))
    )


def header_equal(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    if not (
        true_value(left.get("identity"))
        and true_value(right.get("identity"))
        and true_value(left.get("readable"))
        and true_value(right.get("readable"))
        and true_value(left.get("prefix_readable"))
        and true_value(right.get("prefix_readable"))
    ):
        return False
    return all(same_int(left.get(field), right.get(field)) for field in HEADER_FIELDS)


def header_summary(shape: dict[str, Any] | None) -> dict[str, Any]:
    shape = shape if isinstance(shape, dict) else {}
    return {
        "identity": shape.get("identity"),
        "readable": shape.get("readable"),
        "prefix_readable": shape.get("prefix_readable"),
        **{field: shape.get(field) for field in HEADER_FIELDS},
    }


def payload_summary(shape: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload_of(shape)
    return {
        "addr": payload.get("addr"),
        "vtable_rva": payload.get("vtable_rva"),
        "discriminator": payload.get("discriminator"),
        FAMILY_FIELD: payload.get(FAMILY_FIELD, "alliance"),
        EXTRA60_FIELD: payload.get(EXTRA60_FIELD, 0),
        **{field: payload.get(field) for field in PAYLOAD_FIELDS},
    }


def shape_summary(shape: dict[str, Any] | None) -> dict[str, Any]:
    shape = shape if isinstance(shape, dict) else {}
    return {
        "addr": shape.get("addr"),
        "action": shape.get("action"),
        "header": header_summary(shape),
        "payload": payload_summary(shape),
    }


def event_sequence(event: dict[str, Any], key: str) -> int | None:
    return as_int(event.get(key))


def load_events(path: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    sessions: set[str] = set()
    relevant: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    drops: list[dict[str, Any]] = []
    malformed: list[int] = []
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
            name = str(event.get("event", "<missing>"))
            counts[name] += 1
            session_id = event.get("session_id")
            if session_id is not None:
                sessions.add(str(session_id))
            if "drop" in name.lower():
                drops.append({"line": line_number, "event": name, "record": event})
            if name in RELEVANT_EVENTS:
                record = dict(event)
                record["_line"] = line_number
                relevant[name].append(record)
    return {
        "line_count": line_count,
        "malformed_lines": malformed,
        "event_counts": dict(counts),
        "session_ids": sorted(sessions),
        "drops": drops,
        "transport": relevant[TRANSPORT_EVENT],
        "clones": relevant[CLONE_EVENT],
        "entries": relevant[ENTRY_EVENT],
    }


def path_record(path: Path, root: Path | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path)}
    if root is not None:
        try:
            record["relative_to_runtime"] = str(path.relative_to(root))
        except ValueError:
            pass
    if path.is_file():
        record["size"] = path.stat().st_size
        record["sha256"] = sha256_file(path)
    else:
        record["missing"] = True
    return record


def find_observation_dir(runtime_root: Path) -> Path:
    candidates = sorted(path for path in runtime_root.glob("lifecycle-observation-*") if path.is_dir())
    if len(candidates) != 1:
        raise ValueError(f"expected one lifecycle-observation directory, found {len(candidates)}")
    return candidates[0]


def installation_binding(runtime_root: Path, observation_dir: Path) -> dict[str, Any]:
    installation_path = runtime_root / "installation.json"
    manifest_path = runtime_root / "build-manifest.json"
    installation = json.loads(installation_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dll_path = runtime_root / Path(str(manifest.get("dll", ""))).name
    if not dll_path.is_file():
        dll_path = Path(str(manifest.get("dll", "")))
    sources: list[dict[str, Any]] = []
    for item in manifest.get("sources", []):
        name = str(item.get("name", ""))
        source_path = runtime_root / name
        actual = sha256_file(source_path) if source_path.is_file() else None
        declared = str(item.get("sha256", ""))
        sources.append(
            {
                "name": name,
                "path": str(source_path),
                "declared_sha256": declared,
                "actual_sha256": actual,
                "hash_match": actual is not None and actual.lower() == declared.lower(),
            }
        )
    dll_actual = sha256_file(dll_path) if dll_path.is_file() else None
    dll_declared = str(manifest.get("dll_sha256", ""))
    installation_dll = str(installation.get("dll_sha256", ""))
    module_hashes = [str(item.get("sha256", "")) for item in installation.get("modules_after_install", [])]
    install_checks = {
        "installation_attempted": installation.get("installation_attempted") is True,
        "installation_started": installation.get("installation_started") is True,
        "installation_returncode_zero": installation.get("installation_returncode") == 0,
        "manifest_compiled": manifest.get("compiled") is True,
        "manifest_dll_hash_matches_file": dll_actual is not None and dll_actual.lower() == dll_declared.lower(),
        "installation_dll_hash_matches_manifest": installation_dll.lower() == dll_declared.lower(),
        "module_dll_hash_matches_manifest": bool(module_hashes) and all(
            value.lower() == dll_declared.lower() for value in module_hashes
        ),
        "source_copies_match_manifest": bool(sources) and all(item["hash_match"] for item in sources),
    }
    return {
        "installation": installation,
        "manifest": manifest,
        "checks": install_checks,
        "installation_file": path_record(installation_path, runtime_root),
        "manifest_file": path_record(manifest_path, runtime_root),
        "dll_file": path_record(dll_path, runtime_root),
        "dll_sha256_declared": dll_declared,
        "dll_sha256_actual": dll_actual,
        "sources": sources,
        "observation_report": path_record(observation_dir / "observation-report.json", observation_dir),
    }


def transport_base_checks(event: dict[str, Any], family: str = "alliance") -> dict[str, bool]:
    source = event.get("source")
    loaded = event.get("loaded")
    begin = event_sequence(event, "callback_begin")
    load_sequence = event_sequence(event, "load_callback_sequence")
    end = event_sequence(event, "callback_end")
    return {
        "completed": true_value(event.get("completed")),
        "loads_not_truncated": event.get("loads_truncated") is False,
        "load_count_present": (as_int(event.get("load_count"), 0) or 0) > 0,
        "selected_load_index_in_range": (
            event_sequence(event, "load_index") is not None
            and event_sequence(event, "load_index") < (as_int(event.get("load_count"), -1) or -1)
        ),
        "matching_count_present": (as_int(event.get("matching_count"), 0) or 0) > 0,
        "caller_verified": true_value(event.get("caller_verified")),
        "transport_return_site": same_int(event.get("native_return_rva"), 0x15808F2),
        "source_identity": true_value(event.get("source_identity")),
        "loaded_identity": true_value(event.get("loaded_identity")),
        "source_captured": true_value(event.get("source_captured")),
        "header_flag": true_value(event.get("header_equal")),
        "payload_flag": true_value(event.get("payload_equal")),
        "callback_order": (
            begin is not None and load_sequence is not None and end is not None and begin < load_sequence < end
        ),
        "source_is_outgoing": same_int(event.get("outgoing"), source.get("addr") if isinstance(source, dict) else None),
        "full_header_equal": header_equal(source, loaded),
        "full_payload_equal": payload_equal(source, loaded, family),
        "shape_source_valid": shape_valid(source, family),
        "shape_loaded_valid": shape_valid(loaded, family),
        "source_family_extra60_valid": payload_family_extra_valid(source, family),
        "loaded_family_extra60_valid": payload_family_extra_valid(loaded, family),
        "source_vtable_matches_family": same_int(
            payload_of(source).get("vtable_rva") if isinstance(source, dict) else None,
            expected_vtable_for_family(family)),
        "rebuild_has_distinct_wrapper": (
            isinstance(source, dict)
            and isinstance(loaded, dict)
            and not same_int(source.get("addr"), loaded.get("addr"))
        ),
        "rebuild_has_distinct_action": (
            isinstance(source, dict)
            and isinstance(loaded, dict)
            and not same_int(source.get("action"), loaded.get("action"))
        ),
        "peer_is_transport": same_int(event.get("peer"), event.get("transport")),
        "peer_world_transport_match": (
            true_value(event.get("peer_readable"))
            and true_value(event.get("world_transport_readable"))
            and true_value(event.get("peer_is_world_transport"))
            and same_int(event.get("peer"), event.get("world_transport"))
        ),
    }


def clone_receiver_checks(transport: dict[str, Any], clone: dict[str, Any]) -> dict[str, bool]:
    return {
        "clone_return_site": same_int(clone.get("caller_return_rva"), 0x15801E2),
        "clone_caller_matches": true_value(clone.get("caller_return_matches")),
        "clone_receiver_readable": true_value(clone.get("receiver_readable")),
        "clone_receiver_world_transport": (
            true_value(clone.get("world_transport_readable"))
            and true_value(clone.get("receiver_is_world_transport"))
        ),
        "receiver_matches_peer": same_int(clone.get("receiver"), transport.get("peer")),
        "receiver_host_matches_peer_owner": same_int(clone.get("receiver_host"), transport.get("peer_owner")),
        "receiver_ring_matches_peer_ring": same_int(
            clone.get("receiver_input_ring"), transport.get("peer_input_ring")
        ),
        "receiver_world_dispatcher_matches": same_int(
            clone.get("world_dispatcher"), transport.get("world_dispatcher")
        ),
        "receiver_world_transport_matches": same_int(
            clone.get("world_transport"), transport.get("world_transport")
        ),
        "receiver_vtable_rva_expected": same_int(clone.get("receiver_vtable_rva"), 0x1D95FD8),
    }


def target_checks(loaded: dict[str, Any], clone: dict[str, Any],
                  family: str = "alliance") -> dict[str, bool]:
    target = clone.get("target")
    source = clone.get("source")
    native_result = clone.get("native_result")
    return {
        "clone_source_wrapper_identity": same_int(
            source.get("addr") if isinstance(source, dict) else None, loaded.get("addr")
        ),
        "clone_source_action_identity": same_int(
            source.get("action") if isinstance(source, dict) else None, loaded.get("action")
        ),
        "clone_source_header_equal": header_equal(loaded, source),
        "clone_source_payload_equal": payload_equal(loaded, source, family),
        "clone_source_payload_identity": same_int(
            payload_of(source).get("addr"), payload_of(loaded).get("addr")
        ),
        "clone_target_valid": shape_valid(target, family),
        "clone_target_marker": (
            isinstance(target, dict)
            and same_int(target.get("origin"), 0xFFFF)
            and same_int(target.get("protocol_flags"), 0)
            and same_int(target.get("protocol_sequence"), 0)
        ),
        "clone_target_payload_equal": payload_equal(target, loaded, family),
        "clone_target_family_extra60_valid": payload_family_extra_valid(target, family),
        "clone_native_result_is_target": same_int(native_result, target.get("addr") if isinstance(target, dict) else None),
    }


def entry_checks(source: dict[str, Any], target: dict[str, Any], entry: dict[str, Any],
                 family: str = "alliance") -> dict[str, bool]:
    target_payload = payload_of(target)
    entry_source = entry.get("source")
    allowed_actions = (
        ("offer_royal_marriage", "break_royal_ties")
        if family == "royal_marriage" else
        ("support_independence", "revoke_support_independence")
        if family == "support_independence" else
        ("ask_military_access", "cancel_military_access")
        if family == "military_access" else
        ("offer_vassalization", "cancel_vassalization")
        if family == "vassalization" else
        ("offer_alliance", "dissolve_alliance")
    )
    return {
        "entry_action_id_family_bound": (
            entry.get("action_id") in allowed_actions
        ),
        "entry_readable": true_value(entry.get("readable")),
        "entry_prefix_readable": true_value(entry.get("prefix_readable")),
        "entry_marker_origin": same_int(entry.get("origin"), 0xFFFF),
        "entry_marker_flags": same_int(entry.get("protocol_flags"), 0),
        "entry_source_sequence": same_int(entry.get("protocol_sequence"), source.get("protocol_sequence")),
        "entry_prefix_matches_target": all(
            same_int(entry.get(field), target.get(field))
            for field in ("raw10", "raw38", "raw3c", "raw40", "raw44")
        ),
        "entry_command_is_target": same_int(entry.get("command"), target.get("addr")),
        "entry_action_is_target": same_int(entry.get("action"), target.get("action")),
        "entry_source_payload_identity": same_int(
            entry_source.get("addr") if isinstance(entry_source, dict) else None, target_payload.get("addr")
        ),
        "entry_source_payload_equal": payload_equal(entry_source, target, family),
        "entry_payload_complete": payload_readable(entry_source, family),
        "entry_family_extra60_valid": payload_family_extra_valid(entry_source, family),
    }


def stage_order_checks(transport: dict[str, Any], clone: dict[str, Any], entry: dict[str, Any]) -> dict[str, bool]:
    transport_end = event_sequence(transport, "callback_end")
    clone_begin = event_sequence(clone, "begin_callback_sequence")
    clone_end = event_sequence(clone, "callback_sequence")
    entry_sequence = event_sequence(entry, "callback_sequence")
    return {
        "transport_before_clone": (
            transport_end is not None and clone_begin is not None and transport_end < clone_begin
        ),
        "clone_begin_before_clone_end": (
            clone_begin is not None and clone_end is not None and clone_begin < clone_end
        ),
        "clone_before_entry": clone_end is not None and entry_sequence is not None and clone_end < entry_sequence,
    }


def chain_for_transport(
    transport: dict[str, Any], clones: Iterable[dict[str, Any]], entries: Iterable[dict[str, Any]],
    session_id: str, expected_family: str | None = None
) -> tuple[dict[str, Any] | None, str]:
    family = expected_family or family_from_shape(transport.get("source"))
    base_checks = transport_base_checks(transport, family)
    if not all(base_checks.values()):
        return None, "transport_base_checks_failed"
    loaded = transport.get("loaded")
    sorted_clones = sorted(
        (clone for clone in clones if str(clone.get("session_id")) == session_id),
        key=lambda item: event_sequence(item, "begin_callback_sequence") or -1,
    )
    transport_end = event_sequence(transport, "callback_end")
    for clone in sorted_clones:
        clone_begin = event_sequence(clone, "begin_callback_sequence")
        if clone_begin is None or transport_end is None or clone_begin <= transport_end:
            continue
        checks = dict(base_checks)
        checks.update(clone_receiver_checks(transport, clone))
        checks.update(target_checks(loaded, clone, family))
        target = clone.get("target")
        if not all(checks.values()):
            continue
        sorted_entries = sorted(
            (entry for entry in entries if str(entry.get("session_id")) == session_id),
            key=lambda item: event_sequence(item, "callback_sequence") or -1,
        )
        for entry in sorted_entries:
            entry_sequence = event_sequence(entry, "callback_sequence")
            clone_end = event_sequence(clone, "callback_sequence")
            if entry_sequence is None or clone_end is None or entry_sequence <= clone_end:
                continue
            entry_result = entry_checks(loaded, target, entry, family)
            order_result = stage_order_checks(transport, clone, entry)
            all_checks = {**checks, **entry_result, **order_result}
            if not all(all_checks.values()):
                continue
            chain = {
                "transport": {
                    "line": transport["_line"],
                    "callback_begin": transport.get("callback_begin"),
                    "load_callback_sequence": transport.get("load_callback_sequence"),
                    "callback_end": transport.get("callback_end"),
                    "transport": transport.get("transport"),
                    "outgoing": transport.get("outgoing"),
                    "source": shape_summary(transport.get("source")),
                    "loaded": shape_summary(loaded),
                    "peer": {
                        "peer": transport.get("peer"),
                        "owner": transport.get("peer_owner"),
                        "input_ring": transport.get("peer_input_ring"),
                        "world_dispatcher": transport.get("world_dispatcher"),
                        "world_transport": transport.get("world_transport"),
                    },
                },
                "clone": {
                    "line": clone["_line"],
                    "begin_callback_sequence": clone.get("begin_callback_sequence"),
                    "callback_sequence": clone.get("callback_sequence"),
                    "caller_return_rva": clone.get("caller_return_rva"),
                    "native_result": clone.get("native_result"),
                    "receiver": clone.get("receiver"),
                    "source": shape_summary(clone.get("source")),
                    "target": shape_summary(target),
                },
                "entry": {
                    "line": entry["_line"],
                    "callback_sequence": entry.get("callback_sequence"),
                    "protocol_sequence": entry.get("protocol_sequence"),
                    "command": entry.get("command"),
                    "action": entry.get("action"),
                    "action_id": entry.get("action_id"),
                    "source": payload_summary(entry.get("source")),
                    "business_result": entry.get("business_result"),
                    "rule_result": entry.get("rule_result"),
                    "complete": entry.get("complete"),
                },
                    "family": family,
                    "expected_vtable_rva": expected_vtable_for_family(family),
                    "expected_extra60": 0,
                "checks": all_checks,
                "native_flow": [
                    "transport.source/outgoing",
                    "transport.loaded",
                    "wrapper_clone.source",
                    "wrapper_clone.native_result/target",
                    "command_entry.source",
                ],
                "bridge_submission": False,
                "business_acceptance": False,
            }
            return chain, "complete"
    return None, "no_strict_clone_entry_pair"


def build_report(runtime_root: Path, observation_dir: Path, source_root: Path) -> dict[str, Any]:
    installation_path = runtime_root / "installation.json"
    manifest_path = runtime_root / "build-manifest.json"
    observed_path = observation_dir / "observed-events.jsonl"
    observation_report_path = observation_dir / "observation-report.json"
    installation = installation_binding(runtime_root, observation_dir)
    event_data = load_events(observed_path)
    session_id = str(installation["installation"].get("session_id", ""))
    log_sessions = event_data["session_ids"]
    session_checks = {
        "installation_session_present": bool(session_id),
        "log_has_installation_session": session_id in log_sessions,
        "log_has_single_session": log_sessions == [session_id],
    }
    install_checks = installation["checks"]
    observation_report: dict[str, Any] = {}
    if observation_report_path.is_file():
        try:
            observation_report = json.loads(observation_report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            observation_report = {}
    runtime_action_id = observation_report.get("action_id")
    expected_family = family_for_action(runtime_action_id)
    transport_events = sorted(
        (event for event in event_data["transport"] if str(event.get("session_id")) == session_id),
        key=lambda event: event_sequence(event, "callback_begin") or -1,
    )
    clones = event_data["clones"]
    entries = event_data["entries"]
    chains: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    used_clone_lines: set[int] = set()
    used_entry_lines: set[int] = set()
    for transport in transport_events:
        available_clones = [clone for clone in clones if clone["_line"] not in used_clone_lines]
        available_entries = [entry for entry in entries if entry["_line"] not in used_entry_lines]
        chain, reason = chain_for_transport(
            transport, available_clones, available_entries, session_id, expected_family)
        if chain is None:
            unmatched.append(
                {
                    "transport_line": transport.get("_line"),
                    "callback_begin": transport.get("callback_begin"),
                    "outgoing": transport.get("outgoing"),
                    "reason": reason,
                }
            )
        else:
            chains.append(chain)
            used_clone_lines.add(chain["clone"]["line"])
            used_entry_lines.add(chain["entry"]["line"])
    event_log_checks = {
        "jsonl_fully_parsed": not event_data["malformed_lines"],
        "no_event_drop": not event_data["drops"],
        "transport_event_present": bool(transport_events),
        "transport_events_all_session_bound": len(transport_events) == len(event_data["transport"]),
        "observation_report_binds_log": False,
    }
    log_hash = sha256_file(observed_path)
    event_log_checks["observation_report_binds_log"] = observation_report.get("events_sha256") == log_hash
    chain_count = len(chains)
    overall_checks = {
        **{f"installation.{key}": value for key, value in install_checks.items()},
        **{f"session.{key}": value for key, value in session_checks.items()},
        **{f"event_log.{key}": value for key, value in event_log_checks.items()},
        "complete_native_source_chain_count_positive": chain_count > 0,
        "all_transport_events_complete_chains": len(unmatched) == 0 and chain_count == len(transport_events),
        "runtime_action_id_family_binding": (
            runtime_action_id is None or expected_family in (
                "alliance", "royal_marriage", "support_independence", "military_access"
            )
        ),
    }
    source_bindings: list[dict[str, Any]] = []
    for name in ("diplomacy-observer-v10.cpp", "alliance-transport.inc", "alliance-lifecycle.inc", "alliance-protocol-observer.inc", "alliance-entry-observer.inc", "frame_stub.S"):
        source_path = runtime_root / name
        current_path = source_root / name
        source_bindings.append(
            {
                "name": name,
                "runtime_copy": path_record(source_path, runtime_root),
                "current_workspace": path_record(current_path, source_root),
            }
        )
    return {
        "validator": {
            "name": "validate_alliance_transport.py",
            "version": 2,
            "transport_summary_used": False,
            "payload_fields": list(PAYLOAD_FIELDS),
            "family_fields": [FAMILY_FIELD, EXTRA60_FIELD],
            "header_fields": list(HEADER_FIELDS),
            "runtime_action_id": runtime_action_id,
            "runtime_family": expected_family,
        },
        "inputs": {
            "runtime_root": str(runtime_root),
            "observation_dir": str(observation_dir),
            "installation": path_record(installation_path, runtime_root),
            "build_manifest": path_record(manifest_path, runtime_root),
            "observed_events": path_record(observed_path, observation_dir),
            "observation_report": path_record(observation_report_path, observation_dir),
            "source_bindings": source_bindings,
            "dll_sha256_declared": installation["dll_sha256_declared"],
            "dll_sha256_actual": installation["dll_sha256_actual"],
        },
        "installation": installation,
        "event_log": {
            "line_count": event_data["line_count"],
            "malformed_lines": event_data["malformed_lines"],
            "sha256": log_hash,
            "event_counts": event_data["event_counts"],
            "session_ids": event_data["session_ids"],
            "drop_events": event_data["drops"],
        },
        "criteria": {
            "installation": install_checks,
            "session": session_checks,
            "event_log": event_log_checks,
            "complete_native_source_chain_count": chain_count,
            "unmatched_transport_events": unmatched,
            "overall": overall_checks,
        },
        "complete_native_source_chain_count": chain_count,
        "chains": chains,
        "boundary": {
            "queue_verified_false_is_not_submission": True,
            "pipeline_observation_is_not_business_acceptance": True,
            "business_submission": False,
            "business_acceptance": False,
            "runtime_business_submission_flag": installation["manifest"].get("runtime_verified") is True,
        },
        "validation_passed": all(overall_checks.values()),
    }


def markdown_report(report: dict[str, Any]) -> str:
    inputs = report["inputs"]
    criteria = report["criteria"]
    lines = [
        "# Native alliance transport validation 001",
        "",
        f"- 完整 native source chain 数量：**{report['complete_native_source_chain_count']}**",
        f"- validator 结果：**{'通过' if report['validation_passed'] else '未通过'}**",
        f"- runtime action_id：{report['validator']['runtime_action_id']}；family：{report['validator']['runtime_family'] or '按对象字段识别'}",
        "- 关联来源：独立 `observed-events.jsonl`；未使用 `transport-events.json` 摘要。",
        "- 边界：`queue_verified=false` 与 pipeline 观察不构成 bridge submission 或业务接受。",
        "",
        "## 证据绑定",
        "",
        f"- installation：`{inputs['installation']['path']}`，SHA-256 `{inputs['installation']['sha256']}`",
        f"- observed log：`{inputs['observed_events']['path']}`，{inputs['observed_events']['size']} bytes，SHA-256 `{inputs['observed_events']['sha256']}`",
        f"- DLL：`{inputs['dll_sha256_actual']}`（manifest declared `{inputs['dll_sha256_declared']}`）",
        f"- JSONL 行数：{report['event_log']['line_count']}；解析错误：{len(report['event_log']['malformed_lines'])}；drop 事件：{len(report['event_log']['drop_events'])}",
        "",
        "## 验收条件",
        "",
        "| 条件 | 结果 |",
        "| --- | --- |",
    ]
    for name, value in criteria["overall"].items():
        lines.append(f"| `{name}` | {'PASS' if value else 'FAIL'} |")
    lines.extend(
        [
            "",
            "## 完整链",
            "",
            "| # | transport | loaded | clone | target/native_result | entry | callback 顺序 |",
            "| ---: | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for index, chain in enumerate(report["chains"], 1):
        transport = chain["transport"]
        clone = chain["clone"]
        entry = chain["entry"]
        order = (
            f"{transport['callback_begin']} < {transport['load_callback_sequence']} < "
            f"{transport['callback_end']} < {clone['begin_callback_sequence']} < "
            f"{clone['callback_sequence']} < {entry['callback_sequence']}"
        )
        lines.append(
            f"| {index} | {chain['family']} / line {transport['line']} `{transport['source']['addr']}` | "
            f"line {transport['line']} `{transport['loaded']['addr']}` | "
            f"line {clone['line']} `{clone['source']['addr']}` | "
            f"`{clone['target']['addr']}` / `{clone['native_result']}` | "
            f"line {entry['line']} `{entry['command']}` | `{order}` |"
        )
    lines.extend(
        [
            "",
            "每条链均重新核对 transport source/outgoing 与 loaded 的完整 header（含 raw10/raw38/raw3c/raw40/raw44）及九项数字 payload、family 字符串和 serialized extra60；Alliance 历史缺失字段按 alliance/0 兼容，Royal 必须明确为 royal_marriage/0；loaded wrapper/action 与 clone source 相同；clone target 的 ffff/0/0 marker、native result、world transport/ring/owner 与 command entry 的 ffff/0/source_seq 和 payload 均通过。",
            "",
            "业务边界仍保持为观察证据：报告没有把 `queue_verified`、`complete`、`business_result` 或 pipeline 通过解释为提交或业务接受。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=repo_root / "work/runtime/alliance-query-20261014-r19",
    )
    parser.add_argument("--observation-dir", type=Path, default=None)
    parser.add_argument("--source-root", type=Path, default=repo_root / "work/native")
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime_root = args.runtime_root.resolve()
    observation_dir = (args.observation_dir or find_observation_dir(runtime_root)).resolve()
    source_root = args.source_root.resolve()
    output_json = (args.output_json or observation_dir / "transport-validation-001.json").resolve()
    output_md = (args.output_md or observation_dir / "transport-validation-001.md").resolve()
    try:
        report = build_report(runtime_root, observation_dir, source_root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"validation setup failed: {error}", file=sys.stderr)
        return 2
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(markdown_report(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "validation_passed": report["validation_passed"],
                "complete_native_source_chain_count": report["complete_native_source_chain_count"],
                "output_json": str(output_json),
                "output_md": str(output_md),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
