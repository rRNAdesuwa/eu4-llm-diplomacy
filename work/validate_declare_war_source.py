#!/usr/bin/env python3
"""独立核验 Declare War 的原生来源链和可见战争后果。

这个脚本只读一个 execution artifact 及其 native JSONL。它不重新发送请求，也不把
原 operator 的 overall status 当作原生证据。native_war_reference、wrapper/action
地址和其它对象地址始终作为不透明字符串保留；脚本不会把指针转换成 war_id。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable


MAX_REPORT_BYTES = 10 * 1024 * 1024
MAX_EVENT_LINE_BYTES = 4 * 1024 * 1024
MAX_HASH_BYTES = 256 * 1024 * 1024
MAX_EVENTS_PER_KIND = 2048
FAMILY = "declare_war"
ACTION = "declare_war"
ACTOR = "FRA"
RECIPIENT = "ENG"
VTABLE_RVA = 0x1C80D90
DISCRIMINATOR = 357
CLONE_RETURN_RVA = 0x15801E2
TRANSPORT_RETURN_RVA = 0x15808F2
POINTER_RE = re.compile(r"^0x[0-9a-fA-F]+$")


class ValidationError(RuntimeError):
    pass


def _read_json(path: Path, limit: int = MAX_REPORT_BYTES) -> Any:
    size = path.stat().st_size
    if size > limit:
        raise ValidationError(f"JSON 超过有界读取上限: {path} ({size} bytes)")
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _stream_hash(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_HASH_BYTES:
                raise ValidationError(f"哈希文件超过有界读取上限: {path}")
            digest.update(chunk)
    return digest.hexdigest(), total


def _strict_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            if text.lower().startswith("0x"):
                return int(text, 16)
            if re.fullmatch(r"-?[0-9]+", text):
                return int(text, 10)
        except ValueError:
            return None
    return None


def _same_scalar(left: Any, right: Any) -> bool:
    li = _integer(left)
    ri = _integer(right)
    if li is not None and ri is not None:
        return li == ri
    return left == right


def _load_events(path: Path, session_id: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    if not path.is_file():
        raise ValidationError(f"native event slice 不存在: {path}")
    digest = hashlib.sha256()
    total_bytes = 0
    line_count = 0
    by_kind: dict[str, list[dict[str, Any]]] = {}
    with path.open("rb") as stream:
        for raw in stream:
            total_bytes += len(raw)
            if len(raw) > MAX_EVENT_LINE_BYTES:
                raise ValidationError(f"native event 单行超过上限: {path}")
            digest.update(raw)
            line_count += 1
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValidationError(f"native event JSONL 无效，第 {line_count} 行: {exc}") from exc
            if not isinstance(event, dict):
                continue
            if session_id and event.get("session_id") != session_id:
                continue
            name = str(event.get("event", ""))
            bucket = by_kind.setdefault(name, [])
            if len(bucket) < MAX_EVENTS_PER_KIND:
                bucket.append(event)
    return by_kind, {
        "path": str(path),
        "bytes": total_bytes,
        "lines": line_count,
        "sha256": digest.hexdigest(),
        "session_filtered": True,
    }


def _event(events: dict[str, list[dict[str, Any]]], name: str) -> list[dict[str, Any]]:
    return list(events.get(name, []))


def _payload(shape: Any) -> dict[str, Any] | None:
    if not isinstance(shape, dict):
        return None
    nested = shape.get("payload")
    return nested if isinstance(nested, dict) else shape


def _war_summary(war: Any) -> dict[str, Any] | None:
    if not isinstance(war, dict):
        return None
    keys = (
        "payload_complete", "valid", "flag40", "flag41", "flag42",
        "owned_present", "owned_fields_captured", "container50_count",
        "container68_count", "container80_count",
    )
    return {key: war.get(key) for key in keys}


def _shape_signature(shape: Any) -> dict[str, Any] | None:
    value = _payload(shape)
    if value is None:
        return None
    keys = (
        "family", "declare_war", "extra60", "parameter40", "vtable_rva",
        "discriminator", "actor10", "mirror18", "recipient20", "date28",
        "date2c", "envoy30", "state34", "variant38", "proposal3c",
    )
    result = {key: value.get(key) for key in keys}
    result["war"] = _war_summary(value.get("war"))
    return result


def _shape_is_valid(shape: Any, expected_date: int) -> tuple[bool, str]:
    value = _payload(shape)
    if value is None:
        return False, "缺少 action payload"
    for key in ("family", "declare_war", "vtable_rva", "discriminator", "actor10",
                "mirror18", "recipient20", "date28", "date2c", "envoy30",
                "state34", "variant38", "proposal3c", "war"):
        if key not in value:
            return False, f"payload 缺少 {key}"
    for key in ("readable", "matched", "handles_canonical"):
        if key in value and _strict_bool(value[key]) is not True:
            return False, f"payload {key} 不是 true"
    if value.get("family") != FAMILY or value.get("declare_war") is not True:
        return False, "family/declare_war 标志不匹配"
    if _integer(value.get("vtable_rva")) != VTABLE_RVA:
        return False, "vtable_rva 不匹配"
    if _integer(value.get("discriminator")) != DISCRIMINATOR:
        return False, "discriminator 不匹配"
    if _integer(value.get("date28")) != expected_date or _integer(value.get("date2c")) != expected_date:
        return False, "date28/date2c 不匹配"
    if value.get("extra60") not in (0, "0") or value.get("parameter40") not in (0, "0"):
        return False, "Declare War 的额外参数不是零"
    war = value.get("war")
    if not isinstance(war, dict):
        return False, "缺少完整 War payload"
    for key in ("payload_complete", "valid", "owned_present", "owned_fields_captured"):
        if war.get(key) is not True:
            return False, f"War payload {key} 不是 true"
    for key in ("flag40", "flag41", "flag42"):
        if _integer(war.get(key)) != 0:
            return False, f"War payload {key} 非零"
    for key in ("container50_count", "container68_count", "container80_count"):
        count = _integer(war.get(key))
        if count is None or count < 0 or count > 128:
            return False, f"War payload {key} 越界"
    return True, "完整 Declare War payload 可读"


def _shapes_equal(left: Any, right: Any, expected_date: int) -> bool:
    valid_left, _ = _shape_is_valid(left, expected_date)
    valid_right, _ = _shape_is_valid(right, expected_date)
    if not valid_left or not valid_right:
        return False
    a = _shape_signature(left)
    b = _shape_signature(right)
    if a is None or b is None:
        return False
    for key, value in a.items():
        if key == "war":
            if value != b.get(key):
                return False
        elif not _same_scalar(value, b.get(key)):
            return False
    return True


def _shape_brief(shape: Any) -> dict[str, Any]:
    value = _payload(shape) or {}
    # 地址和 action 只作为 opaque 文本输出，绝不转成整数 ID。
    result = {key: value.get(key) for key in ("addr", "action", "family", "date28", "date2c", "vtable_rva")}
    if isinstance(shape, dict):
        for key in ("addr", "action"):
            if key in shape and key not in result:
                result[key] = shape[key]
    result["address_semantics"] = "opaque_pointer_text"
    return result


def _check(ok: bool, detail: str, **extra: Any) -> dict[str, Any]:
    result = {"ok": bool(ok), "detail": detail}
    result.update(extra)
    return result


def _event_matches(event: dict[str, Any], *, session: str, request: str, date: int | None = None) -> bool:
    if event.get("session_id") != session or event.get("request_id") != request:
        return False
    return date is None or _integer(event.get("date_raw")) == date


def _find_raw_snapshot(report: dict[str, Any], phase: str, name: str) -> Path | None:
    phase_data = report.get(phase)
    if not isinstance(phase_data, dict):
        return None
    probes = phase_data.get("probes")
    if not isinstance(probes, dict):
        return None
    item = probes.get(name)
    if not isinstance(item, dict):
        return None
    path = item.get("snapshot_path")
    return Path(path) if isinstance(path, str) else None


def _contract_report(report: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Resume report 只保存 after；把 source_report 作为 before/请求合同来源。

    source_report 的 overall status 仍然不会成为通过条件。这里只读取其中的
    request、before snapshot 和 execute_call_count，原生 submission/execution
    始终来自当前 resume 的 native slice。
    """
    source = report.get("source_report")
    if not isinstance(source, dict) or not isinstance(source.get("path"), str):
        return report, None
    path = Path(source["path"])
    if path.is_dir():
        path = path / "report.json"
    if not path.is_file():
        return report, str(path)
    try:
        value = _read_json(path)
    except (OSError, ValidationError, json.JSONDecodeError):
        return report, str(path)
    return value if isinstance(value, dict) else report, str(path)


def _war_pair_from_snapshot(path: Path | None, actor_slot: int = 122, recipient_slot: int = 46) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"ok": False, "detail": "war_state snapshot 不存在", "path": str(path) if path else None}
    try:
        value = _read_json(path, 8 * 1024 * 1024)
    except (OSError, ValidationError, json.JSONDecodeError) as exc:
        return {"ok": False, "detail": f"war_state snapshot 无法读取: {exc}", "path": str(path)}
    countries = value.get("countries") if isinstance(value, dict) else None
    if not isinstance(countries, list):
        return {"ok": False, "detail": "war_state snapshot 缺少 countries", "path": str(path)}
    rows = {row.get("slot"): row for row in countries if isinstance(row, dict)}
    actor = rows.get(actor_slot)
    recipient = rows.get(recipient_slot)
    if not isinstance(actor, dict) or not isinstance(recipient, dict):
        return {"ok": False, "detail": "FRA/ENG slot row 缺失", "path": str(path)}
    def pair(row: dict[str, Any], other_slot: int) -> tuple[Any, Any]:
        for item in row.get("pairs", []) if isinstance(row.get("pairs"), list) else []:
            if isinstance(item, dict) and item.get("slot") == other_slot:
                item_flag = item.get("pair_at_war")
                # 当前 probe schema 把 pair_at_war 放在国家行；pair 行只
                # 保存对手 slot 和 opaque war reference。
                if not isinstance(item_flag, bool):
                    item_flag = row.get("pair_at_war")
                return item_flag, item.get("war")
        # 原始 before snapshot 在和平时可能不写 FRA/ENG 的 pair 行；该国家行的
        # pair_at_war=false 仍是有效的双向和平证据。
        top_level = row.get("pair_at_war")
        return (top_level, None) if isinstance(top_level, bool) else (None, None)
    actor_at, actor_war = pair(actor, recipient_slot)
    recipient_at, recipient_war = pair(recipient, actor_slot)
    symmetric = actor_at is not None and recipient_at is not None and actor_at == recipient_at and actor_war == recipient_war
    return {
        "ok": isinstance(actor_at, bool) and isinstance(recipient_at, bool) and symmetric,
        "detail": "FRA/ENG war row 可读且对称" if symmetric else "FRA/ENG war row 不完整或不对称",
        "path": str(path),
        "actor_pair_at_war": actor_at,
        "recipient_pair_at_war": recipient_at,
        "actor_war_reference": actor_war,
        "recipient_war_reference": recipient_war,
        "reference_semantics": "opaque_pointer_text",
    }


def _build_binding(report: dict[str, Any], artifact: Path) -> tuple[dict[str, Any], bool]:
    binding = report.get("build_binding") if isinstance(report.get("build_binding"), dict) else {}
    session = report.get("session") if isinstance(report.get("session"), dict) else {}
    manifest = report.get("build_manifest") if isinstance(report.get("build_manifest"), dict) else {}
    install_hash = binding.get("installation_dll_sha256")
    manifest_hash = binding.get("build_manifest_dll_sha256") or manifest.get("dll_sha256")
    session_hash = session.get("dll_sha256")
    hash_equal = bool(install_hash and install_hash == manifest_hash == session_hash)
    source_checks: list[dict[str, Any]] = []
    # execution artifact 的兄弟文件（build-manifest、源文件和 DLL）位于其
    # 直接父目录；不能退到 work/runtime，否则会把所有 source 误报成缺失。
    parent = artifact.parent
    for item in manifest.get("sources", []) if isinstance(manifest.get("sources"), list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            source_checks.append({"ok": False, "detail": "manifest source 条目无效", "item": item})
            continue
        source = parent / item["name"]
        expected = item.get("sha256")
        if not source.is_file():
            source_checks.append({"ok": False, "name": item["name"], "detail": "运行时 source 不存在"})
            continue
        try:
            actual, size = _stream_hash(source)
            source_checks.append({"ok": actual == expected, "name": item["name"], "bytes": size, "expected": expected, "actual": actual})
        except (OSError, ValidationError) as exc:
            source_checks.append({"ok": False, "name": item["name"], "detail": str(exc)})
    dll_path = Path(manifest["dll"]) if isinstance(manifest.get("dll"), str) else parent / "eu4_bridge_diplomacy_observer_v22.dll"
    dll_check: dict[str, Any]
    if dll_path.is_file():
        try:
            actual, size = _stream_hash(dll_path)
            dll_check = {"ok": actual == manifest_hash, "path": str(dll_path), "bytes": size, "expected": manifest_hash, "actual": actual}
        except (OSError, ValidationError) as exc:
            dll_check = {"ok": False, "path": str(dll_path), "detail": str(exc)}
    else:
        dll_check = {"ok": False, "path": str(dll_path), "detail": "DLL 不存在"}
    source_ok = bool(source_checks) and all(item.get("ok") is True for item in source_checks)
    details = {
        "installation_dll_sha256": install_hash,
        "manifest_dll_sha256": manifest_hash,
        "session_dll_sha256": session_hash,
        "hashes_equal": hash_equal,
        "dll": dll_check,
        "sources": source_checks,
    }
    return details, hash_equal and dll_check.get("ok") is True and source_ok


def _validate(artifact: Path, native_slice: Path | None) -> dict[str, Any]:
    report_path = artifact / "report.json"
    report = _read_json(report_path)
    if not isinstance(report, dict):
        raise ValidationError("report.json 顶层不是对象")
    contract_report, contract_report_path = _contract_report(report)
    session_data = report.get("session") if isinstance(report.get("session"), dict) else {}
    session_id = session_data.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValidationError("report 缺少 session.session_id")
    request_id = report.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        execution = report.get("execution") if isinstance(report.get("execution"), dict) else {}
        request_id = execution.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise ValidationError("report 缺少 request_id")
    expected_date = _integer(report.get("expected_date_raw"))
    if expected_date is None:
        expected_date = _integer((contract_report.get("before") or {}).get("control", {}).get("date_raw"))
    if expected_date is None:
        raise ValidationError("report 缺少 expected_date_raw")
    if native_slice is None:
        metadata = report.get("native_events") if isinstance(report.get("native_events"), dict) else {}
        native_slice = Path(metadata.get("path")) if isinstance(metadata.get("path"), str) else artifact / "native-events-slice.jsonl"
    events, slice_meta = _load_events(native_slice, session_id)
    parameters = report.get("parameters") if isinstance(report.get("parameters"), dict) else contract_report.get("parameters", {})
    if not isinstance(parameters, dict):
        parameters = {}
    goal = parameters.get("war_goal") if isinstance(parameters.get("war_goal"), dict) else {}
    casus = parameters.get("casus_belli")
    province = _integer(goal.get("province_id"))
    beneficiary = goal.get("beneficiary")
    checks: dict[str, dict[str, Any]] = {}
    build_details, build_ok = _build_binding(report, artifact)
    checks["build_dll_and_sources"] = _check(build_ok, "DLL、session 和 build-manifest source 哈希绑定通过" if build_ok else "DLL/source 哈希绑定不完整", evidence=build_details)

    identity_report = contract_report if contract_report else report
    identity_ok = (identity_report.get("action_id") == ACTION and identity_report.get("family") == FAMILY and identity_report.get("actor") == ACTOR and identity_report.get("recipient") == RECIPIENT and identity_report.get("phase") == "initiate")
    checks["report_identity"] = _check(identity_ok, "report action/family/actor/recipient/phase 一致")
    params_ok = casus == "cb_core" and province is not None and province > 0 and beneficiary == ACTOR and parameters.get("call_allies") == []
    checks["parameter_identity"] = _check(params_ok, "请求参数与 Declare War payload 一致", casus_belli=casus, war_goal_province=province, war_goal_beneficiary=beneficiary, call_allies=parameters.get("call_allies"))

    submissions = [event for event in _event(events, "native_declare_war_submission_result") if _event_matches(event, session=session_id, request=request_id, date=expected_date)]
    executions = [event for event in _event(events, "native_declare_war_execution_result") if _event_matches(event, session=session_id, request=request_id, date=expected_date)]
    private_events = [event for event in _event(events, "native_declare_war_consequence_private") if _event_matches(event, session=session_id, request=request_id, date=expected_date)]
    submission = submissions[0] if len(submissions) == 1 else {}
    execution = executions[0] if len(executions) == 1 else {}
    private = private_events[0] if len(private_events) == 1 else {}
    contract_execute_count = contract_report.get("execute_call_count")
    checks["unique_exec3_request"] = _check(contract_execute_count == 1 and len(submissions) == 1 and identity_ok and params_ok, "单次 EXEC3 请求由 source execute_call_count、字段身份和唯一 native submission 共同绑定", submission_count=len(submissions), execute_call_count=contract_execute_count, protocol="EU4DIP_EXEC3", source_report=contract_report_path)
    sub_identity = bool(submission) and all(submission.get(key) == value for key, value in (("family", FAMILY), ("action_id", ACTION), ("actor", ACTOR), ("recipient", RECIPIENT), ("phase", "initiate"))) and submission.get("casus_belli") == casus and _integer(submission.get("war_goal_province")) == province and submission.get("war_goal_beneficiary") == beneficiary
    sub_flags = bool(submission) and submission.get("submitted") is True and submission.get("transport_verified") is True and submission.get("request_binding_verified") is True
    checks["submission_contract"] = _check(sub_identity and sub_flags, "唯一 submission 的身份、参数和 transport binding 通过", event=submission)

    exec_identity = bool(execution) and all(execution.get(key) == value for key, value in (("family", FAMILY), ("action_id", ACTION), ("actor", ACTOR), ("recipient", RECIPIENT), ("phase", "initiate"))) and execution.get("casus_belli") == casus and _integer(execution.get("war_goal_province")) == province and execution.get("war_goal_beneficiary") == beneficiary
    exec_flags = bool(execution) and execution.get("outcome") == "executed" and execution.get("execution_verified") is True and execution.get("request_binding_verified") is True
    checks["execution_contract"] = _check(exec_identity and exec_flags, "唯一 execution result 的身份、参数和 native 执行标志通过", event=execution)

    private_ok = bool(private) and private.get("private") is True and private.get("actor") == ACTOR and private.get("recipient") == RECIPIENT and private.get("war_after") is True and private.get("association_verified") is True and isinstance(private.get("native_war_reference"), str)
    checks["private_consequence"] = _check(private_ok, "private consequence 证明真实 FRA→ENG 战争关联；war reference 保持 opaque 文本", event={**private, "native_war_reference_semantics": "opaque_pointer_text"})

    lifecycle = [event for event in _event(events, "native_alliance_lifecycle") if event.get("kind") in {"serialization_begin", "clone", "wrapper", "destructor", "destructor_return"}]
    serial = [event for event in lifecycle if event.get("kind") == "serialization_begin" and _shape_is_valid(event.get("source"), expected_date)[0]]
    clones = [event for event in lifecycle if event.get("kind") == "clone" and _shape_is_valid(event.get("source"), expected_date)[0] and _shape_is_valid(event.get("target"), expected_date)[0]]
    transport = [event for event in _event(events, "native_alliance_transport_completed") if event.get("completed") is True and _shape_is_valid(event.get("source"), expected_date)[0] and _shape_is_valid(event.get("loaded"), expected_date)[0]]
    wrapper_clones = [event for event in _event(events, "native_alliance_wrapper_clone") if event.get("caller_return_matches") is True and _integer(event.get("caller_return_rva")) == CLONE_RETURN_RVA and _shape_is_valid(event.get("source"), expected_date)[0] and _shape_is_valid(event.get("target"), expected_date)[0]]
    transport_event = transport[0] if len(transport) == 1 else {}
    wrapper_event = wrapper_clones[0] if len(wrapper_clones) == 1 else {}
    serial_event = serial[0] if serial else {}
    checks["serializer_payload"] = _check(bool(serial) and _shapes_equal(serial_event.get("source"), transport_event.get("source"), expected_date), "serialization_begin source 与 transport source 的完整可见 payload 相等", count=len(serial))
    transport_ok = len(transport) == 1 and transport_event.get("loads_truncated") is False and _integer(transport_event.get("load_count")) == 1 and _integer(transport_event.get("matching_count")) == 1 and transport_event.get("header_equal") is True and transport_event.get("payload_equal") is True and transport_event.get("caller_verified") is True and _integer(transport_event.get("native_return_rva")) == TRANSPORT_RETURN_RVA and transport_event.get("peer_is_world_transport") is True and transport_event.get("peer_readable") is True
    checks["transport_load"] = _check(transport_ok, "transport completed 的 load/header/payload/return contract 通过", event=transport_event)
    clone_to_transport = any(_shapes_equal(event.get("target"), transport_event.get("source"), expected_date) for event in clones) if transport_event else False
    loaded_from_clone = any(_shapes_equal(event.get("source"), transport_event.get("loaded"), expected_date) for event in clones) if transport_event else False
    wrapper_chain = bool(wrapper_event) and _shapes_equal(wrapper_event.get("source"), transport_event.get("loaded"), expected_date) and _shapes_equal(wrapper_event.get("target"), execution.get("source", wrapper_event.get("target")), expected_date) if transport_event else False
    checks["clone_chain"] = _check(bool(clones) and clone_to_transport and loaded_from_clone and (not wrapper_clones or wrapper_chain), "clone source/target 与 transport source/loaded 通过完整 payload 关联", clone_count=len(clones), wrapper_clone_count=len(wrapper_clones))

    # 旧的 family-rich passive observer 白名单没有 Declare War，但主框架仍会
    # 写 diplomatic_command_observed。用 generic event 的 command/action/header/
    # sequence 与 wrapper clone、transport source 和 payload 绑定，不能把它
    # 当成缺失的 native_alliance_command_entry_observed。
    entries = [event for event in _event(events, "native_alliance_command_entry_observed") if event.get("action_id") == ACTION and event.get("actor_field") == ACTOR and event.get("recipient_field") == RECIPIENT]
    entry = entries[0] if len(entries) == 1 else {}
    entry_shape = entry.get("source") if isinstance(entry.get("source"), dict) else entry.get("action")
    entry_shape_ok = _shape_is_valid(entry_shape, expected_date)[0] if entry_shape else False
    generic_entries = [event for event in _event(events, "diplomatic_command_observed") if event.get("readable") is True and _integer(event.get("action_vtable_rva")) == VTABLE_RVA and _integer(event.get("protocol_sequence")) == _integer(submission.get("native_sequence"))]
    generic_entry = generic_entries[0] if len(generic_entries) == 1 else {}
    wrapper_target = wrapper_event.get("target") if isinstance(wrapper_event, dict) else None
    wrapper_source = wrapper_event.get("source") if isinstance(wrapper_event, dict) else None
    wrapper_target_payload = _payload(wrapper_target)
    wrapper_target_action = wrapper_target.get("action") if isinstance(wrapper_target, dict) else None
    wrapper_target_addr = wrapper_target_payload.get("addr") if isinstance(wrapper_target_payload, dict) else None
    wrapper_source_protocol_flags = wrapper_source.get("protocol_flags") if isinstance(wrapper_source, dict) else None
    generic_entry_binding = (
        len(generic_entries) == 1
        and generic_entry.get("forward_to_original") is True
        and generic_entry.get("command") == (wrapper_event.get("native_result") if isinstance(wrapper_event, dict) else None)
        and generic_entry.get("command") == (wrapper_target.get("addr") if isinstance(wrapper_target, dict) else None)
        and generic_entry.get("action") == wrapper_target_action
        and _integer(generic_entry.get("protocol_flags")) == _integer(wrapper_source_protocol_flags)
        and isinstance(wrapper_target_payload, dict)
        and _shape_is_valid(wrapper_target_payload, expected_date)[0]
    )
    rich_entry_ok = len(entries) == 1 and entry_shape_ok
    entry_proof_ok = rich_entry_ok or generic_entry_binding
    if rich_entry_ok:
        entry_detail = "family-rich native_alliance_command_entry_observed 已核对"
    elif generic_entry_binding:
        entry_detail = "generic diplomatic_command_observed 已按 command/action/header/sequence/payload 绑定到 consume target；旧 family-rich observer 白名单不覆盖 Declare War"
    else:
        entry_detail = "未找到可绑定的 Declare War passive entry；不会用无关 generic command 冒充"
    checks["command_entry"] = _check(entry_proof_ok, entry_detail, family_rich_count=len(entries), generic_count=len(generic_entries), generic_event=generic_entry, generic_binding=generic_entry_binding, family_rich_observer_coverage=False if not rich_entry_ok else True)
    checks["consume_binding"] = _check(exec_flags and entry_proof_ok, "execution request_binding_verified 与目标 entry 的 wrapper/action/header/sequence/payload 共同证明 consume 授权")
    checks["war_payload"] = _check(bool(transport_event) and transport_event.get("payload_equal") is True and all(_shape_is_valid(side, expected_date)[0] for side in (transport_event.get("source"), transport_event.get("loaded"))), "native payload_equal 与可读完整 War payload 同时通过；向量逐项比较由 native ledger 完成")

    war_id_semantics_ok = bool(execution) and ((execution.get("war_identity_verified") is False and execution.get("war_id") is None) or (execution.get("war_identity_verified") is True and _integer(execution.get("war_id")) is not None))
    stability_semantics_ok = bool(execution) and ((execution.get("stability_verified") is False and execution.get("stability_before_raw") is None and execution.get("stability_after_raw") is None) or (execution.get("stability_verified") is True and _integer(execution.get("stability_before_raw")) is not None and _integer(execution.get("stability_after_raw")) is not None))
    checks["opaque_auxiliary_fields"] = _check(war_id_semantics_ok and stability_semantics_ok, "war_id/stability 的 null 与 verified=false 语义一致；private pointer 不作整数 ID")
    transition_ok = bool(execution) and execution.get("war_before") is False and execution.get("war_after") is True and exec_flags
    checks["war_transition"] = _check(transition_ok, "native execution 证明 war_before=false → war_after=true")

    before_pair = (contract_report.get("before") or {}).get("war_state_pair") if isinstance(contract_report.get("before"), dict) else None
    after_pair = (report.get("after") or {}).get("war_state_pair") if isinstance(report.get("after"), dict) else None
    pair_summary_ok = isinstance(before_pair, dict) and before_pair.get("complete") is True and before_pair.get("pair_at_war") is False and isinstance(after_pair, dict) and after_pair.get("complete") is True and after_pair.get("pair_at_war") is True
    checks["war_state_pair_summary"] = _check(pair_summary_ok, "before/after war_state_pair 同时证明和平到交战" if pair_summary_ok else "缺少完整 before/after war_state_pair（当前 artifact 可能尚未完成 API after projection）")
    before_raw = _war_pair_from_snapshot(_find_raw_snapshot(contract_report, "before", "war_state"))
    after_raw = _war_pair_from_snapshot(_find_raw_snapshot(report, "after", "war_state"))
    private_reference = private.get("native_war_reference") if isinstance(private, dict) else None
    private_reference_matches = (
        isinstance(private_reference, str)
        and isinstance(after_raw.get("actor_war_reference"), str)
        and after_raw.get("actor_war_reference") == private_reference
        and after_raw.get("recipient_war_reference") == private_reference
    )
    raw_pair_ok = (
        before_raw.get("ok") is True
        and before_raw.get("actor_pair_at_war") is False
        and after_raw.get("ok") is True
        and after_raw.get("actor_pair_at_war") is True
        and isinstance(after_raw.get("actor_war_reference"), str)
        and isinstance(after_raw.get("recipient_war_reference"), str)
        and after_raw.get("actor_war_reference") == after_raw.get("recipient_war_reference")
        and private_reference_matches
    )
    checks["war_state_pair_raw"] = _check(raw_pair_ok, "before/after 原始 war_state snapshot 的 FRA↔ENG 双向条目与 private war reference 相同" if raw_pair_ok else "缺少或无法核对 before/after 原始 war_state snapshot 与 private war reference", before=before_raw, after=after_raw, private_reference=private_reference, private_reference_matches=private_reference_matches)

    destruction = [event for event in lifecycle if event.get("kind") == "destructor_return" and _shape_is_valid(event.get("source"), expected_date)[0]]
    checks["lifecycle_cleanup"] = _check(bool(destruction), "至少一个完整 payload 对象正常进入 destructor_return", count=len(destruction))

    result = {
        "schema": "declare_war_source_validation_v1",
        "status": "passed" if all(item.get("ok") is True for item in checks.values()) else "failed",
        "original_report_status": report.get("status"),
        "source_contract_report": contract_report_path,
        "artifact": str(artifact),
        "report_path": str(report_path),
        "request_id": request_id,
        "session_id": session_id,
        "identity": {"family": FAMILY, "action_id": ACTION, "actor": ACTOR, "recipient": RECIPIENT, "phase": "initiate", "date_raw": expected_date},
        "native_slice": slice_meta,
        "event_counts": {name: len(values) for name, values in events.items()},
        "checks": checks,
        "failed_checks": [name for name, item in checks.items() if item.get("ok") is not True],
        "limitations": [
            "native_war_reference、对象 addr/action 和 war_state.war 均按 opaque pointer text 记录，未转换为整数 war_id。",
            "War owned vectors 的逐项内容不由 JSON 事件公开；validator 使用 native payload_equal、完整 payload capture 和最终 request_binding_verified 证明 native ledger 比较，未伪造逐项 JSON。",
            "原 operator status 不作为来源链通过条件；after/probes 缺失会明确使对应检查失败。",
            "Declare War 未进入旧 native_alliance_command_entry_observed family-rich 白名单；resume 中的 generic diplomatic_command_observed 只有在 command/action/header/sequence/payload 全部绑定到 consume target 时才计为入口证明。",
        ],
    }
    return result


def _write_outputs(artifact: Path, result: dict[str, Any], output_dir: Path | None) -> tuple[Path, Path]:
    destination = output_dir or artifact
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "source-validation-001.json"
    md_path = destination / "source-validation-001.md"
    if json_path.exists() or md_path.exists():
        raise ValidationError(f"拒绝覆盖已有独立验证输出: {json_path} / {md_path}")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checks = result.get("checks", {})
    lines = [
        "# Declare War 原生来源独立核验",
        "",
        f"- 结果：**{result.get('status')}**；原 operator 状态：`{result.get('original_report_status')}`。",
        f"- 请求：`{result.get('request_id')}`；session：`{result.get('session_id')}`；日期 raw：`{result.get('identity', {}).get('date_raw')}`。",
        "- 参数身份：FRA → ENG，`declare_war`，`cb_core`，目标省份 177，受益方 FRA。",
        "",
        "## 检查",
        "",
    ]
    for name, item in checks.items():
        mark = "通过" if item.get("ok") else "失败"
        lines.append(f"- `{name}`：**{mark}**。{item.get('detail', '')}")
    lines.extend([
        "",
        "## 证据边界",
        "",
        "native submission/execution/private consequence 使用唯一 request/session/date 关联。serializer、transport load、clone、consume 由 payload_equal、完整 War payload 和最终 request_binding_verified 组合证明；不存在的 seed/entry 事件会报告为缺失，不会用 generic command 记录替代。",
        "",
        "`war_id`、`native_war_reference`、war_state 中的 `war` 以及 wrapper/action 地址都是 opaque pointer 文本。脚本不会将这些地址转换为整数 ID。`war_id=null` 且 `war_identity_verified=false`、稳定度字段为空且 `stability_verified=false` 是明确的未知辅助状态，不会被误报为数值结果。",
        "",
        "完整 JSON：`source-validation-001.json`。",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读核验 Declare War 原生来源链和 FRA↔ENG 战争后果")
    parser.add_argument("--execution-artifact", required=True, type=Path, help="包含 report.json 的 execution artifact 目录")
    parser.add_argument("--native-slice", type=Path, help="可选 native-events-slice.jsonl；默认使用 report.native_events.path")
    parser.add_argument("--output-dir", type=Path, help="可选独立输出目录；默认写回 execution artifact")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = _validate(args.execution_artifact.resolve(), args.native_slice.resolve() if args.native_slice else None)
        json_path, md_path = _write_outputs(args.execution_artifact.resolve(), result, args.output_dir.resolve() if args.output_dir else None)
    except (OSError, ValidationError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "json": str(json_path), "markdown": str(md_path), "failed_checks": result["failed_checks"]}, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
