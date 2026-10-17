"""Validate one Rival execution's bounded native source/transport chain.

The validator is independent of the Python execution report's overall status.
It binds the native command entry and the native execution result to the
reported request, then validates the object lifecycle visible in the private
JSONL slice.  ``event_sequence`` on a command entry and ``sequence`` on an
observer object event are kept as separate counters; neither is compared with
the other, and file flush order is not treated as execution order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


_MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
_MAX_LINE_BYTES = 256 * 1024
_HEX_RE = re.compile(r"0x[0-9a-fA-F]+\Z")
_ACTIONS = ("set_rival", "remove_rival")
_SELECTORS = {"set_rival": "0x2fae", "remove_rival": "0x2faf"}
_RVA_LOAD = 0x15808F2
_RVA_RECEIVE_CLONE = 0x15801E2
_ACTOR = "FRA"
_FAMILY = "rival"

# This is the complete observed object header/payload surface for the Rival
# command.  raw4b/reserved4b are deliberately included in every equality.
_OBJECT_FIELDS = (
    "vtable_rva", "discriminator", "raw10", "raw38", "raw3c", "raw40",
    "raw44", "origin48", "flags4a", "raw4b", "reserved4b", "sequence4c",
    "actor", "target", "old_rival",
)


class SourceChainError(RuntimeError):
    """A bounded source-chain validation failure."""


def _strict_int(value: object) -> bool:
    return type(value) is int


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise SourceChainError(f"FILE_MISSING:{path}")
    if path.stat().st_size > _MAX_EVIDENCE_BYTES:
        raise SourceChainError(f"EVIDENCE_TOO_LARGE:{path}")
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceChainError(f"JSON_READ_FAILED:{path}:{type(error).__name__}") from error
    if not isinstance(value, dict):
        raise SourceChainError(f"JSON_NOT_OBJECT:{path}")
    return value


def _sha256_stream(path: Path, maximum: int = _MAX_EVIDENCE_BYTES) -> dict[str, object]:
    if not path.is_file():
        raise SourceChainError(f"FILE_MISSING:{path}")
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum:
                    raise SourceChainError(f"EVIDENCE_TOO_LARGE:{path}")
                digest.update(chunk)
    except OSError as error:
        raise SourceChainError(f"HASH_FAILED:{path}:{type(error).__name__}") from error
    return {"path": str(path), "bytes": total, "sha256": digest.hexdigest()}


def _read_events(path: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    metadata = _sha256_stream(path)
    events: list[dict[str, object]] = []
    invalid_lines = 0
    oversized_lines = 0
    line_count = 0
    try:
        with path.open("rb") as stream:
            for line_number, raw in enumerate(stream, 1):
                line_count = line_number
                if len(raw) > _MAX_LINE_BYTES:
                    oversized_lines += 1
                    continue
                try:
                    value = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    invalid_lines += 1
                    continue
                if isinstance(value, dict):
                    value = dict(value)
                    value["_line"] = line_number
                    events.append(value)
                else:
                    invalid_lines += 1
    except OSError as error:
        raise SourceChainError(f"EVENTS_READ_FAILED:{path}:{type(error).__name__}") from error
    metadata.update({
        "line_count": line_count,
        "json_object_count": len(events),
        "invalid_line_count": invalid_lines,
        "oversized_line_count": oversized_lines,
    })
    return events, metadata


def _event(events: list[dict[str, object]], name: str) -> list[dict[str, object]]:
    return [item for item in events if item.get("event") == name]


def _hex_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and _HEX_RE.fullmatch(value):
        return int(value, 16)
    return None


def _ref(value: object) -> tuple[object, object] | None:
    if not isinstance(value, dict):
        return None
    addr = value.get("addr")
    generation = value.get("generation")
    if _hex_int(addr) is None or not _strict_int(generation):
        return None
    return addr, generation


def _payload(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    if any(field not in value for field in _OBJECT_FIELDS):
        return None
    return {field: value.get(field) for field in _OBJECT_FIELDS}


def _payload_equal(left: object, right: object) -> bool:
    left_payload = _payload(left)
    right_payload = _payload(right)
    return left_payload is not None and left_payload == right_payload


def _object_summary(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {"present": False}
    result = {
        "present": True,
        "ref": {"addr": value.get("addr"), "generation": value.get("generation")},
    }
    payload = _payload(value)
    if payload is not None:
        result["payload"] = payload
    return result


def _expected_shape(action: str) -> dict[str, object]:
    if action == "set_rival":
        return {
            "vtable_rva": "0x1c55138", "raw44": 12206,
            "origin48": 15573, "sequence4c": 16,
        }
    return {
        "vtable_rva": "0x1c54a68", "raw44": 12207,
        "origin48": 5106, "sequence4c": 15,
    }


def _valid_business_object(value: object, action: str) -> bool:
    if not isinstance(value, dict):
        return False
    reference = _ref(value)
    payload = _payload(value)
    if reference is None or payload is None or reference[1] <= 0:
        return False
    if not all(value.get(key) is True for key in ("matched", "readable", "canonical")):
        return False
    expected = _expected_shape(action)
    generic = {
        "discriminator": 357, "raw10": 0, "raw38": 1, "raw3c": 0,
        "raw40": 0, "flags4a": 0, "raw4b": 0, "reserved4b": 0,
    }
    return (
        value.get("family") == action
        and all(payload.get(key) == expected_value for key, expected_value in expected.items())
        and all(payload.get(key) == expected_value for key, expected_value in generic.items())
        and isinstance(payload.get("actor"), str)
        and isinstance(payload.get("target"), str)
        and isinstance(payload.get("old_rival"), str)
    )


def _zero_ref(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        value.get("addr") == "0x0"
        and value.get("generation") == 0
        and value.get("matched") is False
    )


def _return_site(event: dict[str, object]) -> dict[str, object]:
    value = _hex_int(event.get("caller_return"))
    return {"absolute": event.get("caller_return"), "parsed": value}


def _lifecycle_chain(events: list[dict[str, object]], action: str) -> tuple[dict[str, object], dict[str, object]]:
    serializations = _event(events, "native_rival_command_serialization")
    loads = _event(events, "native_rival_command_load")
    clones = _event(events, "native_rival_command_clone")
    destructions = _event(events, "native_rival_command_destruction")
    serialization = serializations[0] if len(serializations) == 1 else {}
    load = loads[0] if len(loads) == 1 else {}
    # The receive hook carries the world transport in receiver while its own
    # transport field is zero.  The explicit receiver==serialization transport
    # condition is evaluated below after the unique receive clone is selected.
    receive_clones = [
        event for event in clones
        if event.get("native_return_matches") is True
        and event.get("receiver") not in (None, "0x0")
    ]
    receive = receive_clones[0] if len(receive_clones) == 1 else {}
    template_clones = [
        event for event in clones if event.get("native_return_matches") is False
    ]
    source = serialization.get("source")
    load_source = load.get("source")
    load_target = load.get("target")
    receive_source = receive.get("source")
    receive_target = receive.get("target")
    chain_checks: dict[str, bool] = {
        "one_serialization": len(serializations) == 1,
        "one_load": len(loads) == 1,
        "one_receive_clone": len(receive_clones) == 1,
        "template_clone_excluded": len(template_clones) >= 1,
        "template_clone_not_bound": all(
            event.get("native_return_matches") is False for event in template_clones
        ) if template_clones else False,
        "serialization_source_shape": _valid_business_object(source, action),
        "load_source_shape": _valid_business_object(load_source, action),
        "load_target_shape": _valid_business_object(load_target, action),
        "receive_source_shape": _valid_business_object(receive_source, action),
        "receive_target_shape": _valid_business_object(receive_target, action),
        "load_source_target_same_ref": _ref(load_source) == _ref(load_target),
        "load_source_target_payload_equal": _payload_equal(load_source, load_target),
        "serialization_to_load_payload_equal": _payload_equal(source, load_target),
        "loaded_ref_carried_to_receive_source": _ref(load_target) == _ref(receive_source),
        "loaded_payload_carried_to_receive_source": _payload_equal(load_target, receive_source),
        "receive_target_payload_equal": _payload_equal(receive_source, receive_target),
        "receive_target_new_generation": (
            _ref(receive_target) is not None
            and _ref(receive_source) is not None
            and _ref(receive_target)[1] != _ref(receive_source)[1]
        ),
        "receive_result_is_target": (
            isinstance(receive, dict)
            and receive.get("native_result") == receive_target.get("addr")
            if isinstance(receive_target, dict) else False
        ),
        "receive_return_matches": receive.get("native_return_matches") is True,
        "load_peer_is_transport": (
            isinstance(load, dict)
            and load.get("peer") == load.get("transport")
            and load.get("peer") not in (None, "0x0")
        ),
        "receive_receiver_is_serialization_transport": (
            isinstance(receive, dict)
            and receive.get("receiver") == serialization.get("transport")
            and receive.get("receiver") not in (None, "0x0")
        ),
        "all_full_header_fields_present": all(
            _payload(value) is not None
            for value in (source, load_source, load_target, receive_source, receive_target)
        ),
    }

    load_return = _hex_int(load.get("caller_return"))
    receive_return = _hex_int(receive.get("caller_return"))
    inferred_base = load_return - _RVA_LOAD if load_return is not None else None
    inferred_receive_rva = (
        receive_return - inferred_base
        if inferred_base is not None and receive_return is not None else None
    )
    chain_checks["load_return_site_known"] = load_return is not None
    chain_checks["receive_return_site_known"] = receive_return is not None
    chain_checks["caller_sites_share_page_aligned_image_base"] = (
        inferred_base is not None
        and inferred_receive_rva == _RVA_RECEIVE_CLONE
        and inferred_base % 0x1000 == 0
    )

    references = {
        "serialized_source": _object_summary(source),
        "loaded": _object_summary(load_target),
        "received_target": _object_summary(receive_target),
    }
    destruction_matches: dict[str, list[dict[str, object]]] = {}
    for name, reference in (
        ("serialized_source", source),
        ("loaded", load_target),
        ("received_target", receive_target),
    ):
        ref = _ref(reference)
        matching = [event for event in destructions if _ref(event.get("source")) == ref]
        destruction_matches[name] = matching
        chain_checks[f"{name}_destroyed_once"] = len(matching) == 1
        if matching:
            destruction = matching[0]
            chain_checks[f"{name}_destruction_payload_equal"] = _payload_equal(
                destruction.get("source"), reference
            )
            chain_checks[f"{name}_destruction_target_zero"] = _zero_ref(
                destruction.get("target")
            )
            chain_checks[f"{name}_destruction_result_matches_source"] = (
                destruction.get("native_result") == reference.get("addr")
                if isinstance(reference, dict) else False
            )
        else:
            chain_checks[f"{name}_destruction_payload_equal"] = False
            chain_checks[f"{name}_destruction_target_zero"] = False
            chain_checks[f"{name}_destruction_result_matches_source"] = False
    chain_checks["three_normal_destruction_events"] = len(destructions) == 3

    detail = {
        "event_lines": {
            "serialization": serialization.get("_line"),
            "load": load.get("_line"),
            "receive_clone": receive.get("_line"),
            "destructions": {
                name: [event.get("_line") for event in values]
                for name, values in destruction_matches.items()
            },
        },
        "object_refs": references,
        "caller_return_sites": {
            "load": _return_site(load),
            "receive_clone": _return_site(receive),
            "inferred_image_base": hex(inferred_base) if inferred_base is not None else None,
            "load_rva_expected": hex(_RVA_LOAD),
            "receive_clone_rva_expected": hex(_RVA_RECEIVE_CLONE),
            "receive_clone_rva_inferred": hex(inferred_receive_rva)
            if inferred_receive_rva is not None else None,
            "rva_field_present_in_log": False,
        },
        "template_clone_lines": [event.get("_line") for event in template_clones],
        "checks": chain_checks,
        "destruction_count": len(destructions),
    }
    return detail, chain_checks


def _validate_artifact(artifact: Path, native_slice: Path | None = None) -> dict[str, object]:
    artifact = artifact.expanduser().resolve(strict=True)
    report_path = artifact / "report.json"
    native_path = (native_slice.expanduser().resolve(strict=True)
                   if native_slice is not None
                   else artifact / "native-events-slice.jsonl")
    report = _read_json(report_path)
    events, event_file = _read_events(native_path)
    action = report.get("action_id")
    recipient = report.get("recipient")
    request_id = report.get("request_id")
    date_raw = report.get("expected_date_raw")
    session = report.get("session")
    session_id = session.get("session_id") if isinstance(session, dict) else None
    expected_shape = action in _ACTIONS and isinstance(recipient, str)
    entries = _event(events, "native_rival_command_entry")
    submissions = _event(events, "native_rival_submission_result")
    results = _event(events, "native_rival_execution_result")
    matching_entries = [
        event for event in entries
        if event.get("kind") == action
        and event.get("allowed") is True
        and event.get("canonical") is True
        and event.get("shape") is True
    ] if expected_shape else []
    matching_submissions = [
        event for event in submissions
        if event.get("action_id") == action
        and event.get("actor") == _ACTOR
        and event.get("recipient") == recipient
        and event.get("request_id") == request_id
        and event.get("family") == _FAMILY
        and event.get("session_id") == session_id
        and event.get("date_raw") == date_raw
    ] if expected_shape else []
    matching_results = [
        event for event in results
        if event.get("action_id") == action
        and event.get("actor") == _ACTOR
        and event.get("recipient") == recipient
        and event.get("request_id") == request_id
        and event.get("family") == _FAMILY
        and event.get("session_id") == session_id
        and event.get("date_raw") == date_raw
    ] if expected_shape else []
    entry = matching_entries[0] if len(matching_entries) == 1 else {}
    submission = matching_submissions[0] if len(matching_submissions) == 1 else {}
    execution = matching_results[0] if len(matching_results) == 1 else {}
    lifecycle, lifecycle_checks = _lifecycle_chain(events, action) if expected_shape else ({}, {})
    serialized = lifecycle.get("object_refs", {}).get("serialized_source") if isinstance(lifecycle, dict) else None
    serialized_payload = (
        serialized.get("payload") if isinstance(serialized, dict) else None
    )

    execution_checks: dict[str, bool] = {
        "one_matching_submission_result": len(matching_submissions) == 1,
        "submission_verified": (
            submission.get("submitted") is True
            and submission.get("protocol_verified") is True
            and submission.get("request_binding_verified") is True
        ),
        "one_matching_execution_result": len(matching_results) == 1,
        "execution_status_executed": (
            execution.get("executed") is True and execution.get("status") == "executed"
        ),
        "execution_relationship_verified": execution.get("relationship_verified") is True,
        "execution_request_binding_verified": execution.get("request_binding_verified") is True,
    }
    if action == "set_rival":
        expected_before, expected_after, expected_delta = False, True, 1
    else:
        expected_before, expected_after, expected_delta = True, False, -1
    count_before = execution.get("rival_count_before")
    count_after = execution.get("rival_count_after")
    dip_before = execution.get("dip_before")
    dip_after = execution.get("dip_after")
    cost_raw = execution.get("cost_raw")
    execution_checks.update({
        "entry_and_execution_result_action_match": (
            len(matching_entries) == 1
            and len(matching_results) == 1
            and entry.get("kind") == execution.get("action_id") == action
            and execution.get("family") == _FAMILY
        ),
        "membership_transition_matches_action": (
            execution.get("before_active") is expected_before
            and execution.get("after_active") is expected_after
        ),
        "membership_count_transition_verified": (
            _strict_int(count_before) and _strict_int(count_after)
            and count_after - count_before == expected_delta
        ),
        "diplomatic_power_and_cost_are_integers": all(
            _strict_int(value) for value in (dip_before, dip_after, cost_raw)
        ),
        "diplomatic_power_delta_matches_cost": (
            _strict_int(dip_before) and _strict_int(dip_after)
            and _strict_int(cost_raw) and dip_before - dip_after == cost_raw
        ),
    })

    if isinstance(serialized_payload, dict) and isinstance(entry, dict):
        entry_binding = (
            entry.get("actor") == serialized_payload.get("actor")
            and entry.get("target") == serialized_payload.get("target")
        )
    else:
        entry_binding = False
    entry_checks = {
        "one_native_command_entry_total": len(entries) == 1,
        "one_matching_native_command_entry": len(matching_entries) == 1,
        "entry_allowed_canonical_shape": (
            entry.get("allowed") is True
            and entry.get("canonical") is True
            and entry.get("shape") is True
        ),
        "entry_action_selector_bound": (
            entry.get("kind") == action
            and entry.get("selector") == _SELECTORS.get(action)
        ),
        "entry_actor_target_handle_bound_to_serialized_payload": entry_binding,
        "entry_session_bound": entry.get("session_id") == session_id,
        "entry_event_sequence_present": _strict_int(entry.get("event_sequence")),
    }
    report_checks = report.get("checks")
    metadata_checks = {
        "report_metadata_action_actor_recipient": (
            action in _ACTIONS and report.get("actor") == _ACTOR
            and isinstance(recipient, str) and report.get("family") == _FAMILY
            and report.get("phase") == "initiate"
        ),
        "report_metadata_date_request_session": (
            _strict_int(date_raw) and isinstance(request_id, str) and bool(request_id)
            and isinstance(session_id, str) and bool(session_id)
        ),
        "original_report_status_recorded_not_chain_gate": isinstance(report.get("status"), str),
        "original_report_checks_recorded": isinstance(report_checks, dict),
        "sequence_domains_kept_separate": True,
    }
    checks = {
        **metadata_checks,
        **entry_checks,
        **execution_checks,
        **lifecycle_checks,
        "native_slice_bounded_and_well_formed": (
            event_file.get("bytes", _MAX_EVIDENCE_BYTES + 1) <= _MAX_EVIDENCE_BYTES
            and event_file.get("invalid_line_count") == 0
            and event_file.get("oversized_line_count") == 0
        ),
    }
    status = "passed" if all(checks.values()) else "failed"
    result: dict[str, object] = {
        "validator": "validate_rival_source_chain.py",
        "version": 1,
        "status": status,
        "mode": "read_only_native_source_chain",
        "artifact": str(artifact),
        "execution_report": {
            "path": str(report_path),
            "status": report.get("status"),
            "action_id": action,
            "actor": report.get("actor"),
            "recipient": recipient,
            "family": report.get("family"),
            "request_id": request_id,
            "expected_date_raw": date_raw,
            "session_id": session_id,
            "checks": report_checks,
        },
        "native_slice": event_file,
        "source_chain": {
            "lifecycle": lifecycle,
            "entry": {
                "line": entry.get("_line"),
                "event_sequence": entry.get("event_sequence"),
                "kind": entry.get("kind"),
                "selector": entry.get("selector"),
                "allowed": entry.get("allowed"),
                "canonical": entry.get("canonical"),
                "shape": entry.get("shape"),
                "actor_handle": entry.get("actor"),
                "target_handle": entry.get("target"),
                "address_present": False,
            },
            "submission_result": {
                "line": submission.get("_line"),
                "submitted": submission.get("submitted"),
                "protocol_verified": submission.get("protocol_verified"),
            },
            "execution_result": {
                "line": execution.get("_line"),
                "status": execution.get("status"),
                "executed": execution.get("executed"),
                "before_active": execution.get("before_active"),
                "after_active": execution.get("after_active"),
                "rival_count_before": count_before,
                "rival_count_after": count_after,
                "dip_before": dip_before,
                "dip_after": dip_after,
                "cost_raw": cost_raw,
            },
            "association": {
                "strength": "semantic_action_request_plus_shared_actor_target_payload_handles",
                "entry_has_direct_object_address": False,
                "object_addresses_are_not_claimed_from_entry": True,
                "execution_result_bound_by_request_action_actor_recipient_date": True,
                "file_line_order_is_recorded_only": True,
            },
        },
        "checks": checks,
        "tamper_surface": {
            "full_header_includes_raw4b_and_reserved4b": True,
            "payload_equality_includes_raw4b_and_reserved4b": True,
            "generation_and_payload_are_checked_separately": True,
            "template_clone_native_return_false_is_excluded": True,
        },
    }
    return result


def _write_exclusive(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _write_markdown(path: Path, result: dict[str, object]) -> None:
    chain = result.get("source_chain", {})
    execution_report = result.get("execution_report", {})
    checks = result.get("checks", {})
    execution = chain.get("execution_result", {}) if isinstance(chain, dict) else {}
    lifecycle = chain.get("lifecycle", {}) if isinstance(chain, dict) else {}
    lines = [
        "# Rival 原生 source chain 独立核验",
        "",
        f"- 结果：`{result.get('status')}`",
        f"- 动作：`{execution_report.get('action_id')}`，FRA → `{execution_report.get('recipient')}`",
        f"- request：`{execution_report.get('request_id')}`",
        f"- 原执行报告状态：`{execution_report.get('status')}`（不作为本核验的成功条件）",
        "",
        "## 核验范围",
        "",
        "核验使用 execution artifact 中不超过 8MB 的 private native JSONL slice。",
        "验证序列化 source、load、接收 clone、三个对象析构，以及唯一允许的 native command entry 和 native execution result。",
        "对象事件的 `sequence` 与 command entry 的 `event_sequence` 属于不同计数域；本报告不比较两者，也不把 JSONL 刷新顺序解释为实际执行先后。",
        "",
        "## 关键结果",
        "",
        f"- native execution result：`{execution.get('status')}`，membership `{execution.get('before_active')}` → `{execution.get('after_active')}`。",
        f"- Rival 数量：`{execution.get('rival_count_before')}` → `{execution.get('rival_count_after')}`。",
        f"- 外交点：`{execution.get('dip_before')}` → `{execution.get('dip_after')}`，原生费用 `cost_raw={execution.get('cost_raw')}`。",
        f"- 对象生命周期检查：`{lifecycle.get('checks', {}) and all(lifecycle.get('checks', {}).values())}`。",
        f"- 总检查：`{sum(1 for value in checks.values() if value is True)}/{len(checks)}` 通过。",
        "",
        "## 关联强度",
        "",
        "command entry 没有直接输出对象地址，因此报告只使用 action、selector、FRA actor handle、recipient target handle、request 和 execution result 的共享语义进行关联；报告不声称 entry 直接携带对象地址。",
        "clone 模板事件的 `native_return_matches=false` 被明确排除；只有接收 clone 的 `native_return_matches=true`、receiver 与序列化事件的 transport 地址绑定的事件进入链。",
        "",
        "## 检查项",
        "",
    ]
    for key, value in checks.items():
        lines.append(f"- `{key}`：{'通过' if value is True else '失败'}")
    lines.extend(["", "## 证据路径", "", f"- artifact：`{result.get('artifact')}`", f"- native slice：`{result.get('native_slice', {}).get('path') if isinstance(result.get('native_slice'), dict) else None}`", ""])
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-artifact", type=Path, required=True,
                        help="one Rival execution artifact directory")
    parser.add_argument("--native-slice", type=Path,
                        help="optional bounded native-events-slice.jsonl")
    args = parser.parse_args(argv)
    artifact = args.execution_artifact.expanduser().resolve(strict=True)
    json_path = artifact / "source-validation-001.json"
    md_path = artifact / "source-validation-001.md"
    try:
        if json_path.exists() or md_path.exists():
            raise SourceChainError("SOURCE_VALIDATION_OUTPUT_ALREADY_EXISTS")
        result = _validate_artifact(artifact, args.native_slice)
        _write_exclusive(json_path, result)
        _write_markdown(md_path, result)
    except Exception as error:
        result = {
            "validator": "validate_rival_source_chain.py",
            "status": "failed",
            "artifact": str(artifact),
            "error": {"type": type(error).__name__, "message": str(error)},
        }
        if not json_path.exists():
            _write_exclusive(json_path, result)
        if not md_path.exists():
            _write_markdown(md_path, result)
    print(json.dumps({"status": result.get("status"), "artifact": str(artifact),
                      "report": str(json_path)}, ensure_ascii=False), flush=True)
    return 0 if result.get("status") == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
