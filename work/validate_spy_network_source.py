#!/usr/bin/env python3
"""Read-only source-chain validation for a Spy Network execution artifact.

The existing Improve validator supplies the common request, transport, clone,
pointer, and result checks.  This wrapper runs those checks with Spy constants,
then adds the Spy diplomat transition and the native action+30 post-entry
mutation evidence.  Event JSONL is streamed and bounded at 10 MiB.
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
START_ACTION = "build_spy_network"
STOP_ACTION = "stop_building_spy_network"
FAMILY = "spy_network"
ACTOR = "FRA"
RECIPIENT = "SAV"
PHASE = "initiate"
SELECTOR = 13176
VTABLE_RVA = 0x1C7CC48
EXPECTED_COUNTRIES = ("FRA", "ENG", "POR")
TAG_RE = common.TAG_RE


def _configure_common() -> None:
    """Configure the imported common validator in this process only."""

    common.START_ACTION = START_ACTION
    common.STOP_ACTION = STOP_ACTION
    common.SUPPORTED_ACTIONS = frozenset((START_ACTION, STOP_ACTION))
    common.FAMILY = FAMILY
    common.ACTOR = ACTOR
    common.RECIPIENT = RECIPIENT
    common.PHASE = PHASE
    common.EXPECTED_VARIANT = 1
    common.EXPECTED_STATE = 0
    common.EXPECTED_EXTRA60 = 0
    common.EXPECTED_DISCRIMINATOR = 357
    common.EXPECTED_VTABLE_RVA = VTABLE_RVA
    common.IMPROVE_SELECTOR = SELECTOR


def _event_path(artifact: Path) -> Path:
    for name in ("native-events-slice.jsonl", "native-events.jsonl"):
        path = artifact / name
        if path.exists():
            return path
    raise FileNotFoundError(f"no native event JSONL under {artifact}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _extra_events(path: Path, names: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Stream only extra events that the common validator does not retain."""

    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"refusing to scan event file over 10 MiB: {path}")
    result: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            value = json.loads(raw_line.decode("utf-8"))
            if isinstance(value, dict) and value.get("event") in names:
                item = dict(value)
                item["_line"] = line_number
                result[str(value["event"])].append(item)
    return dict(result)


def _session(report: dict[str, Any]) -> str:
    return common._session_id(report)


def _country_map(snapshot: Any) -> dict[str, dict[str, Any]]:
    return common._country_map(snapshot)


def _tag(value: Any) -> str | None:
    number = as_int(value)
    if number is None:
        return None
    try:
        tag = (number & 0xFFFFFF).to_bytes(3, "little").decode("ascii")
    except (OverflowError, UnicodeDecodeError):
        return None
    return tag if TAG_RE.fullmatch(tag) else None


def _spy_entries(country: Any) -> list[dict[str, Any]]:
    if not isinstance(country, dict) or not isinstance(country.get("entries"), list):
        return []
    entries: list[dict[str, Any]] = []
    for value in country["entries"]:
        if not isinstance(value, dict):
            continue
        if as_int(value.get("raw_action_type_a8")) != SELECTOR:
            continue
        if _tag(value.get("raw_actor_80")) != ACTOR:
            continue
        if _tag(value.get("raw_recipient_88")) != RECIPIENT:
            continue
        if as_int(value.get("active_raw_18")) == 0:
            continue
        entries.append(value)
    return entries


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


def _core_payload_equal(left: Any, right: Any, expected_variant: int) -> bool:
    """Compare the serialized action while allowing the engine's envoy write."""

    left_payload = common._payload(left)
    right_payload = common._payload(right)
    return (
        common._payload_valid(left, expected_variant)
        and common._payload_valid(right, expected_variant)
        and left_payload.get("family") == right_payload.get("family") == FAMILY
        and same_int(left_payload.get("extra60"), right_payload.get("extra60"))
        and all(
            same_int(left_payload.get(field), right_payload.get(field))
            for field in common.PAYLOAD_FIELDS
            if field != "envoy30"
        )
    )


def _diplomat_checks(report: dict[str, Any], post_envoy: Any) -> tuple[dict[str, bool], dict[str, Any]]:
    action = str(report.get("action_id", ""))
    is_start = action == START_ACTION
    before = _country_map(report.get("before"))
    after = _country_map(report.get("after"))
    fra_before = before.get(ACTOR, {})
    fra_after = after.get(ACTOR, {})
    before_tasks = _spy_entries(fra_before)
    after_tasks = _spy_entries(fra_after)
    before_work = [value for value in before_tasks if as_int(value.get("active_raw_18")) == 2]
    after_work = [value for value in after_tasks if as_int(value.get("active_raw_18")) == 2]
    after_returning = [value for value in after_tasks if as_int(value.get("active_raw_18")) == 1]
    before_keys = {_entry_projection(value) for value in before_tasks}
    added = [value for value in after_tasks if _entry_projection(value) not in before_keys]
    target_before = [
        value for value in before_work
        if _tag(value.get("raw_actor_80")) == ACTOR
        and _tag(value.get("raw_recipient_88")) == RECIPIENT
    ]
    target_after_work = [
        value for value in after_work
        if _tag(value.get("raw_actor_80")) == ACTOR
        and _tag(value.get("raw_recipient_88")) == RECIPIENT
    ]
    target_after_returning = [
        value for value in after_returning
        if _tag(value.get("raw_actor_80")) == ACTOR
        and _tag(value.get("raw_recipient_88")) == RECIPIENT
    ]
    available_before = as_int(fra_before.get("available_count"))
    available_after = as_int(fra_after.get("available_count"))
    if is_start:
        task_transition = (
            len(target_before) == 0
            and len(target_after_work) == 1
            and available_before == 1
            and available_after == 0
        )
        envoy_matches = bool(target_after_work) and same_int(
            post_envoy, target_after_work[0].get("raw_id_44")
        )
        new_task = target_after_work[0] if len(target_after_work) == 1 else None
    else:
        task_transition = (
            len(target_before) == 1
            and len(target_after_work) == 0
            and len(target_after_returning) == 1
            and available_before == 0
            and available_after == 0
        )
        envoy_matches = bool(target_before) and same_int(
            post_envoy, target_before[0].get("raw_id_44")
        )
        new_task = target_after_returning[0] if len(target_after_returning) == 1 else None
    checks = {
        "countries_complete": all(tag in before and tag in after for tag in EXPECTED_COUNTRIES),
        "task_transition_expected": task_transition,
        "fra_available_expected": (
            (available_before == 1 and available_after == 0)
            if is_start else (available_before == 0 and available_after == 0)
        ),
        "start_task_absent_before_or_stop_task_present": (
            len(target_before) == 0 if is_start else len(target_before) == 1
        ),
        "start_new_task_or_stop_returning": (
            len(target_after_work) == 1 if is_start else len(target_after_returning) == 1
        ),
        "task_type_13176": bool(new_task)
        and same_int(new_task.get("raw_action_type_a8"), SELECTOR),
        "task_actor_recipient": bool(new_task)
        and _tag(new_task.get("raw_actor_80")) == ACTOR
        and _tag(new_task.get("raw_recipient_88")) == RECIPIENT,
        "engine_envoy_matches_relevant_slot": envoy_matches,
        "eng_por_unchanged": before.get("ENG") == after.get("ENG")
        and before.get("POR") == after.get("POR"),
        "snapshot_date_same": same_int(
            report.get("before", {}).get("control", {}).get("date_raw"),
            report.get("after", {}).get("control", {}).get("date_raw"),
        ),
    }
    detail = {
        "before_available": {tag: before.get(tag, {}).get("available_count") for tag in EXPECTED_COUNTRIES},
        "after_available": {tag: after.get(tag, {}).get("available_count") for tag in EXPECTED_COUNTRIES},
        "action_id": action,
        "before_spy_tasks": [_entry_projection(value) for value in before_tasks],
        "after_spy_tasks": [_entry_projection(value) for value in after_tasks],
        "before_target_work": target_before[0] if len(target_before) == 1 else None,
        "after_target_work": target_after_work[0] if len(target_after_work) == 1 else None,
        "after_target_returning": target_after_returning[0] if len(target_after_returning) == 1 else None,
        "new_task": new_task,
        "added_tasks": [_entry_projection(value) for value in added],
        "eng_por_equal": checks["eng_por_unchanged"],
    }
    return checks, detail


def _window_checks(report: dict[str, Any], artifact: Path, event_path: Path, event_data: dict[str, Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    metadata = report.get("native_events")
    metadata = metadata if isinstance(metadata, dict) else {}
    actual = _record(event_path)
    checks = {
        "event_jsonl_complete": not event_data["malformed_lines"] and not event_data["non_object_lines"],
        "event_sha256_matches_report": metadata.get("sha256") == actual["sha256"],
        "event_bytes_matches_report": same_int(metadata.get("bytes"), actual["size_bytes"]),
        "event_window_offsets_valid": (
            as_int(metadata.get("start_offset")) is not None
            and as_int(metadata.get("end_offset")) is not None
            and as_int(metadata.get("end_offset")) >= as_int(metadata.get("start_offset"))
        ),
        "event_status_complete": metadata.get("status") == "ok" and metadata.get("complete") is True,
        "event_path_is_artifact_local": event_path.parent.resolve() == artifact.resolve(),
    }
    detail = {
        "source_metadata": {
            key: metadata.get(key)
            for key in ("path", "start_offset", "end_offset", "bytes", "sha256", "complete", "status")
        },
        "actual_file": actual,
        "line_count": event_data["line_count"],
        "counts": event_data["counts"],
        "checks": checks,
    }
    return checks, detail


def _post_entry_mutation(
    event_data: dict[str, Any],
    extra: dict[str, list[dict[str, Any]]],
    report: dict[str, Any],
    chain: dict[str, Any],
) -> tuple[dict[str, bool], dict[str, Any], Any]:
    action = str(report.get("action_id", ""))
    is_start = action == START_ACTION
    expected_variant = 1 if is_start else 0
    session = _session(report)
    entries = common._session_events(event_data, "native_alliance_command_entry_observed", session)
    entry = entries[0] if len(entries) == 1 else {}
    entry_line = as_int(entry.get("_line"))
    entry_callback = as_int(entry.get("callback_sequence"))
    entry_source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    entry_payload = common._payload(entry_source)
    mutations: list[dict[str, Any]] = []
    for value in extra.get("native_alliance_lifecycle", []):
        source = value.get("source")
        payload = common._payload(source)
        sequence = as_int(value.get("sequence"))
        line = as_int(value.get("_line"))
        if (
            entry_line is not None
            and entry_callback is not None
            and line is not None
            and sequence is not None
            and line > entry_line
            and sequence > entry_callback
            and common._payload_valid(source, expected_variant)
            and not same_int(payload.get("envoy30"), entry_payload.get("envoy30"))
            and _core_payload_equal(source, entry_source, expected_variant)
        ):
            mutations.append(value)
    post_envoy = (
        common._payload(mutations[0].get("source")).get("envoy30")
        if mutations else entry_payload.get("envoy30") if not is_start else None
    )
    checks = {
        "post_entry_action30_mutation_observed": bool(mutations) if is_start else True,
        "post_entry_mutation_core_family_preserved": (
            bool(mutations) and all(
                _core_payload_equal(value.get("source"), entry_source, expected_variant)
                for value in mutations
            )
        ) if is_start else True,
    }
    if not is_start:
        checks["stop_pre_entry_action30_id_present"] = (
            as_int(entry_payload.get("envoy30")) is not None
            and as_int(entry_payload.get("envoy30")) >= 0
        )
        checks["stop_no_post_entry_action30_rewrite"] = not mutations
    detail = {
        "event_lines": [value.get("_line") for value in mutations],
        "sequences": [value.get("sequence") for value in mutations],
        "kinds": [value.get("kind") for value in mutations],
        "pre_entry_envoy30": entry_payload.get("envoy30"),
        "post_entry_envoy30": [
            common._payload(value.get("source")).get("envoy30") for value in mutations
        ],
        "entry_line": entry_line,
        "entry_callback_sequence": entry_callback,
        "interpretation": (
            "native action+30 writes the envoy id after the Start command entry"
            if is_start else
            "Stop carries the existing action+30 envoy id through the native packet; no rewrite was observed"
        ),
    }
    return checks, detail, post_envoy


def _negative_validation(artifact: Path) -> dict[str, Any]:
    report = common._bounded_json(artifact / "report.json")
    path = _event_path(artifact)
    selected = {
        "native_alliance_authority_test_dispatched",
        "native_alliance_execution_rejected",
        "native_alliance_command_entry_observed",
        "native_alliance_submission_result",
        "native_diplomacy_task_execution_result",
    }
    extra = _extra_events(path, selected)
    session = str(report.get("session_id", ""))
    dispatches = [value for value in extra.get("native_alliance_authority_test_dispatched", [])
                  if str(value.get("session_id", "")) == session]
    rejections = [value for value in extra.get("native_alliance_execution_rejected", [])
                  if str(value.get("session_id", "")) == session]
    entries = [value for value in extra.get("native_alliance_command_entry_observed", [])
               if str(value.get("session_id", "")) == session]
    submissions = [value for value in extra.get("native_alliance_submission_result", [])
                   if str(value.get("session_id", "")) == session]
    results = [value for value in extra.get("native_diplomacy_task_execution_result", [])
               if str(value.get("session_id", "")) == session]
    dispatch = dispatches[0] if len(dispatches) == 1 else {}
    rejection = rejections[0] if len(rejections) == 1 else {}
    entry = entries[0] if len(entries) == 1 else {}
    payload = common._payload(entry.get("source"))
    action = str(report.get("action_id", ""))
    expected_route = "direct_entry" if action == START_ACTION else "transport"
    expected_accepted = False if expected_route == "direct_entry" else True
    checks = {
        "one_direct_dispatch": len(dispatches) == 1,
        "route_recorded": dispatch.get("dispatch_route") == expected_route,
        "dispatcher_route_acceptance_expected": dispatch.get("dispatcher_accepted") is expected_accepted,
        "no_authority_seed": dispatch.get("authority_seed_created") is False,
        "spy_packet_identity": (
            action in (START_ACTION, STOP_ACTION)
            and dispatch.get("action_id") == action
            and dispatch.get("actor") == ACTOR
            and dispatch.get("recipient") == RECIPIENT
            and dispatch.get("phase") == PHASE
            and same_int(dispatch.get("variant38"), 1 if action == START_ACTION else 0)
            and same_int(dispatch.get("state34"), 0)
        ),
        "entry_family_spy_network": (
            len(entries) == 1
            and common._payload_valid(
                entry.get("source"), 1 if action == START_ACTION else 0
            )
            and payload.get("family") == FAMILY
            and same_int(payload.get("extra60"), 0)
        ),
        "one_rejection": len(rejections) == 1,
        "rejection_reason_is_unauthorized_spy": rejection.get("reason") == "UNAUTHORIZED_FRA_SPY_TASK",
        "rejection_not_submitted": rejection.get("submitted") is False,
        "no_authorized_submission": len(submissions) == 0,
        "no_task_result": len(results) == 0,
        "native_ai_self_choice_false": report.get("native_ai_self_choice_evidence") is False,
        "blocked_without_state_change": all(
            report.get("checks", {}).get(key) is True
            for key in ("blocked_at_command_entry", "diplomat_availability_unchanged",
                        "diplomat_tasks_unchanged", "por_paused_same_date")
        ),
    }
    checks["negative_validation_passed"] = all(checks.values())
    return {
        "status": "passed" if checks["negative_validation_passed"] else "failed",
        "artifact": _record(artifact / "report.json"),
        "event_file": _record(path),
        "session_id": session,
        "action_id": action,
        "checks": checks,
        "dispatch": {
            "line": dispatch.get("_line"),
            "action_id": dispatch.get("action_id"),
            "actor": dispatch.get("actor"),
            "recipient": dispatch.get("recipient"),
            "variant38": dispatch.get("variant38"),
            "state34": dispatch.get("state34"),
            "dispatch_route": dispatch.get("dispatch_route"),
            "dispatcher_accepted": dispatch.get("dispatcher_accepted"),
            "authority_seed_created": dispatch.get("authority_seed_created"),
        },
        "rejection": {
            "line": rejection.get("_line"),
            "reason": rejection.get("reason"),
            "submitted": rejection.get("submitted"),
        },
        "authorized_chain_counts": {
            "command_entries": len(entries),
            "submissions": len(submissions),
            "task_results": len(results),
        },
    }


def build_report(
    artifact: Path,
    negative_artifacts: list[Path] | None = None,
) -> dict[str, Any]:
    _configure_common()
    source_report = common._bounded_json(artifact / "report.json")
    event_path = _event_path(artifact)
    event_data = common._stream_events(event_path)
    checks, chain = common._build_chain_checks(source_report, event_data)
    extra = _extra_events(event_path, {"diplomatic_command_observed", "native_alliance_lifecycle"})
    command_events = [
        value for value in extra.get("diplomatic_command_observed", [])
        if str(value.get("session_id", "")) == _session(source_report)
    ]
    entry_events = common._session_events(
        event_data, "native_alliance_command_entry_observed", _session(source_report)
    )
    entry = entry_events[0] if len(entry_events) == 1 else {}
    command_binding = len(command_events) == 1 and (
        same_int(command_events[0].get("command"), entry.get("command"))
        and same_int(command_events[0].get("action"), entry.get("action"))
        and same_int(command_events[0].get("action_vtable_rva"), VTABLE_RVA)
    )
    action = str(source_report.get("action_id", ""))
    expected_variant = 1 if action == START_ACTION else 0
    checks["source_report_family_spy_network"] = source_report.get("family") == FAMILY
    checks["source_report_selector_13176"] = same_int(source_report.get("selector"), SELECTOR)
    checks["native_mode_expected"] = same_int(
        source_report.get("observations", {}).get("native_mode_expected"),
        expected_variant,
    )
    checks["diplomatic_command_vtable_bound"] = command_binding
    checks["pre_entry_full_payload_equal"] = checks.get(
        "request_semantic_key_bound_through_chain", False
    ) and checks.get("payload_family_extra60_state_variant_consistent", False)
    mutation_checks, mutation_detail, post_envoy = _post_entry_mutation(
        event_data, extra, source_report, chain
    )
    checks.update(mutation_checks)
    diplomat_checks, diplomat_detail = _diplomat_checks(source_report, post_envoy)
    checks.update({f"diplomat_{key}": value for key, value in diplomat_checks.items()})
    window_checks, window_detail = _window_checks(
        source_report, artifact, event_path, event_data
    )
    checks.update(window_checks)
    checks["positive_validation_passed"] = all(checks.values())
    positive = {
        "status": "passed" if checks["positive_validation_passed"] else "failed",
        "checks": checks,
        "request": chain.get("request", {}),
        "native_mode": source_report.get("observations", {}).get("native_mode_expected"),
        "chain": chain,
        "command_event": {
            "line": command_events[0].get("_line") if len(command_events) == 1 else None,
            "event_sequence": command_events[0].get("event_sequence") if len(command_events) == 1 else None,
            "action_vtable_rva": command_events[0].get("action_vtable_rva") if len(command_events) == 1 else None,
        },
        "pre_entry_payload_equality": {
            "full_payload_check": checks["pre_entry_full_payload_equal"],
            "family": FAMILY,
            "extra60": 0,
            "state34": 0,
            "variant38": expected_variant,
        },
        "post_entry_engine_mutation": mutation_detail,
        "diplomat_observation": diplomat_detail,
        "event_window": window_detail,
        "observed_report_status": source_report.get("status"),
    }
    result: dict[str, Any] = {
        "schema_version": 1,
        "validator": "validate_spy_network_source.py",
        "status": positive["status"],
        "artifact": _record(artifact / "report.json"),
        "positive": positive,
    }
    if negative_artifacts:
        negatives = []
        for negative_artifact in negative_artifacts:
            negative = _negative_validation(negative_artifact)
            negatives.append({"artifact_path": str(negative_artifact), **negative})
        result["negatives"] = negatives
        if len(negatives) == 1:
            result["negative"] = negatives[0]
        result["status"] = (
            "passed"
            if positive["status"] == "passed"
            and all(item["status"] == "passed" for item in negatives)
            else "failed"
        )
    return result


def _failed(checks: dict[str, Any]) -> list[str]:
    return [name for name, value in checks.items() if value is False]


def markdown_report(value: dict[str, Any]) -> str:
    positive = value["positive"]
    request = positive["request"]
    mutation = positive["post_entry_engine_mutation"]
    diplomat = positive["diplomat_observation"]
    action = request.get("action_id")
    variant = positive["pre_entry_payload_equality"].get("variant38")
    if action == START_ACTION:
        boundary_text = (
            f"入口后 lifecycle sequence={mutation.get('sequences')} 观察到 envoy30 "
            f"从 {mutation.get('pre_entry_envoy30')} 变为 {mutation.get('post_entry_envoy30')}。"
            "该变化与新外交官槽位 raw_id_44 对应，核心字段保持一致，属于引擎在入口后的 action+30 写入。"
        )
    else:
        boundary_text = (
            f"Stop 入口 payload 的 variant38={variant}、envoy30={mutation.get('pre_entry_envoy30')}；"
            "入口后的 lifecycle 记录没有再次改写 action+30，现有外交官槽位保持用于返程状态。"
        )
    if action == START_ACTION:
        task_text = (
            f"FRA→SAV type=13176 活动任务：{len(diplomat.get('before_spy_tasks', []))} → "
            f"{len(diplomat.get('after_spy_tasks', []))}。"
        )
    else:
        before_task = diplomat.get("before_target_work") or {}
        after_task = diplomat.get("after_target_returning") or {}
        task_text = (
            "FRA→SAV type=13176 的 raw18 状态："
            f"{before_task.get('active_raw_18')} → {after_task.get('active_raw_18')}（工作转返程）。"
        )
    lines = [
        "# Spy Network 原生来源核验",
        "",
        f"结论：{value['status'].upper()}。",
        "",
        f"核验对象：{action}，FRA→SAV，family=spy_network，selector=13176。",
        f"request_id：{request.get('request_id')}；正向链路：{positive['status']}。",
        f"失败检查：{', '.join(_failed(positive['checks'])) or '无'}。",
        "",
        "## 原生时间边界",
        "",
        "入口前的 command source、wrapper clone source/target、transport source/loaded "
        "完整 payload 相等，且 family、extra60、state34、variant38 分别为 "
        f"spy_network、0、0、{variant}。",
        boundary_text,
        "",
        "## 外交官快照",
        "",
        f"FRA 可用外交官：{diplomat.get('before_available', {}).get('FRA')} → "
        f"{diplomat.get('after_available', {}).get('FRA')}。",
        task_text + " ENG/POR 保持相等："
        f"{diplomat.get('eng_por_equal')}。",
    ]
    negatives = value.get("negatives")
    if not isinstance(negatives, list):
        negative = value.get("negative")
        negatives = [negative] if isinstance(negative, dict) else []
    for index, negative in enumerate(negatives, 1):
        lines.extend([
            "",
            f"## 未授权负例 {index}",
            "",
            f"负例：{negative.get('status')}；失败检查："
            f"{', '.join(_failed(negative.get('checks', {}))) or '无'}。",
            f"route={negative.get('dispatch', {}).get('dispatch_route')}；"
            f"mode/variant={negative.get('dispatch', {}).get('variant38')}；"
            f"reason={negative.get('rejection', {}).get('reason')}；"
            f"authorized submission/task result="
            f"{negative.get('authorized_chain_counts', {}).get('submissions')}/"
            f"{negative.get('authorized_chain_counts', {}).get('task_results')}。",
        ])
    window = positive["event_window"]
    lines.extend([
        "",
        "## 事件窗口",
        "",
        f"文件：{window['actual_file']['path']}",
        f"byte offset：{window['source_metadata'].get('start_offset')}.."
        f"{window['source_metadata'].get('end_offset')}；"
        f"JSONL 行数：{window.get('line_count')}。",
    ])
    return "\n".join(lines) + "\n"


def _fresh_output_dir(artifact: Path) -> Path:
    return artifact.parent / f"spy-network-source-validation-{uuid.uuid4().hex}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--negative-artifact", action="append", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main(argv: list[str] | None = None) -> int:
    args = parse_args()
    artifact = args.artifact.resolve()
    negatives = [path.resolve() for path in (args.negative_artifact or [])]
    output_dir = args.output_dir.resolve() if args.output_dir else _fresh_output_dir(artifact)
    output_dir.mkdir(parents=True, exist_ok=False)
    value = build_report(artifact, negatives)
    (output_dir / "validation.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
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
