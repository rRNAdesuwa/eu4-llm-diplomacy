#!/usr/bin/env python3
"""Run the native Rival authority negative fixture exactly once.

The supplied installation must already contain the Rival entry guard from
``rival-authority.inc``.  This operator performs no Rival query and
creates no diplomacy journal request.  It takes bounded read-only snapshots,
atomically publishes one ``RIVAL_GUARD_TEST1`` request, waits for the native
three-kind direct/vtable gate fixture, and records the bounded log slice.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import ObserverSession  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import (  # noqa: E402
    _copy_log_slice,
    _write_json,
)
from work.run_improve_relations_execution import _new_artifact  # noqa: E402
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _diplomat_semantics,
    _run_snapshots,
)


_ACTOR = "FRA"
_PLAYER_SLOT = 189  # POR in the controlled experiment
_REQUEST_COMMAND = "RIVAL_GUARD_TEST1"
_AUTHORITY_REASON = "FRA_SUBMISSION_UNAUTHORIZED"
_RIVAL_KINDS = ("set_rival", "replace_rival", "remove_rival")
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_HANDLE_RE = re.compile(r"0x[0-9a-fA-F]+\Z")
_POLL_INTERVAL_SECONDS = 0.10
_MAX_POLL_READ_BYTES = 8 * 1024 * 1024
_POLL_READ_CHUNK_BYTES = 256 * 1024
_MAX_LOG_LINE_BYTES = 256 * 1024


class AuthorityTestError(RuntimeError):
    """A bounded operator failure with a stable report code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _public_probe_records(records: object) -> dict[str, dict[str, object]]:
    if not isinstance(records, dict):
        return {}
    return {
        str(name): {
            "status": item.get("status"),
            "name": item.get("name"),
            "script": item.get("script"),
            "snapshot_path": item.get("snapshot_path"),
            "snapshot_completeness": item.get("snapshot_completeness"),
            "snapshot_sha256": item.get("snapshot_sha256"),
        }
        for name, item in records.items()
        if isinstance(item, dict)
    }


def _snapshot_objects(records: object) -> dict[str, dict[str, object]]:
    if not isinstance(records, dict):
        return {}
    return {
        str(name): item
        for name, item in records.items()
        if isinstance(item, dict) and isinstance(item.get("snapshot"), dict)
    }


def _snapshot_comparison(before: object, after: object) -> dict[str, object]:
    before_items = _snapshot_objects(before)
    after_items = _snapshot_objects(after)
    names = sorted(set(before_items) | set(after_items))
    per_probe: dict[str, bool] = {}
    for name in names:
        left = before_items.get(name, {}).get("snapshot")
        right = after_items.get(name, {}).get("snapshot")
        per_probe[name] = left == right
    return {
        "probe_names": names,
        "per_probe_equal": per_probe,
        "all_equal": bool(names) and all(per_probe.values()),
        "diplomat_semantics_equal": _diplomat_semantics_equal(before_items, after_items),
    }


def _diplomat_semantics_equal(before: dict[str, dict[str, object]],
                              after: dict[str, dict[str, object]]) -> bool:
    left = before.get("diplomats", {}).get("snapshot")
    right = after.get("diplomats", {}).get("snapshot")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    try:
        return _diplomat_semantics(left) == _diplomat_semantics(right)
    except Exception:
        return False


def _snapshot_boundary_checks(records: object, expected_date: int) -> dict[str, bool]:
    snapshots = _snapshot_objects(records)
    control = snapshots.get("control_state", {}).get("snapshot")
    alliance = snapshots.get("alliance_state", {}).get("snapshot")
    diplomats = snapshots.get("diplomats", {}).get("snapshot")
    war = snapshots.get("war_state", {}).get("snapshot")
    return {
        "four_snapshots_complete": _snapshots_complete(records),
        "control_por_paused_date": (
            isinstance(control, dict)
            and control.get("player_slot") == _PLAYER_SLOT
            and control.get("paused_flag") == 1
            and control.get("date_raw") == expected_date
        ),
        "alliance_snapshot_date_player": (
            isinstance(alliance, dict)
            and alliance.get("date_raw") == expected_date
            and alliance.get("player") == "POR"
        ),
        "diplomat_snapshot_date": (
            isinstance(diplomats, dict)
            and diplomats.get("current_raw_date") == expected_date
        ),
        "war_snapshot_date": (
            isinstance(war, dict)
            and war.get("current_raw_date") == expected_date
        ),
    }


def _parse_event_lines(path: Path) -> tuple[list[dict[str, object]], dict[str, int]]:
    events: list[dict[str, object]] = []
    stats = {
        "line_count": 0,
        "json_line_count": 0,
        "invalid_line_count": 0,
        "oversized_line_count": 0,
    }
    with path.open("rb") as stream:
        for raw in stream:
            stats["line_count"] += 1
            if len(raw) > _MAX_LOG_LINE_BYTES:
                stats["oversized_line_count"] += 1
                continue
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                stats["invalid_line_count"] += 1
                continue
            if isinstance(value, dict):
                stats["json_line_count"] += 1
                events.append(value)
    return events, stats


def _authority_event_summary(path: Path, session_id: str,
                            expected_date: int) -> dict[str, object]:
    events, stats = _parse_event_lines(path)
    tests = [
        event for event in events
        if event.get("event") == "native_rival_authority_test"
        and event.get("session_id") == session_id
    ]
    entries = [
        event for event in events
        if event.get("event") == "native_rival_command_entry"
        and event.get("session_id") == session_id
    ]
    drops = [
        event for event in events
        if event.get("event") == "native_rival_command_entry_drop"
    ]
    business_events = [
        event for event in events
        if event.get("session_id") == session_id
        and isinstance(event.get("event"), str)
        and any(token in event["event"].casefold()
                for token in ("execute", "submission"))
    ]
    kind_counts = {kind: sum(event.get("kind") == kind for event in entries)
                   for kind in _RIVAL_KINDS}
    actor_handles = {
        event.get("actor") for event in entries
        if isinstance(event.get("actor"), str)
    }
    actor_handle_consistent = len(actor_handles) == 1
    entry_shape = all(
        event.get("scope") == "canonical"
        and event.get("canonical") is True
        and event.get("shape") is True
        and event.get("allowed") is False
        and event.get("reason") == _AUTHORITY_REASON
        and isinstance(event.get("actor"), str)
        and _HANDLE_RE.fullmatch(event["actor"]) is not None
        and isinstance(event.get("target"), str)
        and _HANDLE_RE.fullmatch(event["target"]) is not None
        for event in entries
    )
    entry_session_date = all(
        event.get("session_id") == session_id for event in entries
    )
    test = tests[0] if len(tests) == 1 else None
    before = test.get("before") if isinstance(test, dict) else None
    after = test.get("after") if isinstance(test, dict) else None
    test_before_after_equal = (
        isinstance(before, dict) and isinstance(after, dict) and before == after
    )
    test_contract = (
        isinstance(test, dict)
        and test.get("request") == _REQUEST_COMMAND
        and test.get("scope") == _ACTOR
        and test.get("date_raw") == expected_date
        and test.get("paused") is True
        and test.get("player") == "POR"
        and test.get("direct_calls") == 3
        and test.get("vtable_calls") == 3
        and test.get("blocked_calls") == 6
        and test.get("all_blocked") is True
        and test.get("state_unchanged") is True
        and test.get("business_result") == "blocked"
        and test.get("complete") is True
    )
    return {
        **stats,
        "session_id": session_id,
        "native_test_count": len(tests),
        "native_test": test,
        "command_entry_count": len(entries),
        "command_entries": entries,
        "command_kind_counts": kind_counts,
        "command_entries_contract": (
            len(entries) == 6
            and all(count == 2 for count in kind_counts.values())
            and entry_shape
            and actor_handle_consistent
            and entry_session_date
        ),
        "actor_handle_consistent": actor_handle_consistent,
        "native_test_contract": test_contract,
        "native_test_before_after_equal": test_before_after_equal,
        "drop_count": len(drops),
        "drop_events": drops,
        "business_events": business_events,
        "complete": (
            len(tests) == 1
            and test_contract
            and test_before_after_equal
            and len(entries) == 6
            and all(count == 2 for count in kind_counts.values())
            and entry_shape
            and not drops
        ),
    }


def _read_poll_chunk(log_path: Path, cursor: int, pending: bytes,
                     remaining: int) -> tuple[int, bytes, list[dict[str, object]], int]:
    if remaining <= 0:
        return cursor, pending, [], 0
    with log_path.open("rb") as stream:
        stream.seek(cursor)
        chunk = stream.read(min(_POLL_READ_CHUNK_BYTES, remaining))
        next_cursor = stream.tell()
    if not chunk:
        return next_cursor, pending, [], 0
    data = pending + chunk
    lines = data.split(b"\n")
    remainder = lines.pop()
    parsed: list[dict[str, object]] = []
    for raw in lines:
        if not raw or len(raw) > _MAX_LOG_LINE_BYTES:
            continue
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            parsed.append(value)
    return next_cursor, remainder, parsed, len(chunk)


def _poll_authority(log_path: Path, start_offset: int, session_id: str,
                    timeout_seconds: float) -> dict[str, object]:
    started = _utc_now()
    deadline = started + timedelta(seconds=timeout_seconds)
    handle = f"rival-authority-poll-{uuid.uuid4().hex}"
    cursor = start_offset
    pending = b""
    total_read = 0
    poll_count = 0
    invalid_or_partial = 0
    seen: list[dict[str, object]] = []
    ready = False
    error: dict[str, str] | None = None
    while _utc_now() < deadline:
        poll_count += 1
        try:
            cursor, pending, parsed, consumed = _read_poll_chunk(
                log_path, cursor, pending, _MAX_POLL_READ_BYTES - total_read)
        except OSError as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
            break
        total_read += consumed
        for event in parsed:
            if event.get("event") == "native_rival_command_entry_drop":
                seen.append(event)
            elif event.get("session_id") == session_id and event.get("event") in (
                    "native_rival_authority_test", "native_rival_command_entry"):
                seen.append(event)
        if seen:
            test_ok = any(
                event.get("event") == "native_rival_authority_test"
                and event.get("session_id") == session_id
                and event.get("complete") is True
                for event in seen
            )
            entry_count = sum(
                event.get("event") == "native_rival_command_entry"
                for event in seen
            )
            drop_seen = any(
                event.get("event") == "native_rival_command_entry_drop"
                for event in seen
            )
            ready = test_ok and entry_count >= 6 and not drop_seen
        if ready:
            break
        if total_read >= _MAX_POLL_READ_BYTES:
            error = {"type": "BoundedLogPoll", "message": "POLL_LOG_BOUND_EXCEEDED"}
            break
        remaining = max(0.0, (deadline - _utc_now()).total_seconds())
        if remaining > 0:
            time.sleep(min(_POLL_INTERVAL_SECONDS, remaining))
    completed = _utc_now()
    return {
        "handle": handle,
        "started_utc": _utc_text(started),
        "deadline_utc": _utc_text(deadline),
        "completed_utc": _utc_text(completed),
        "timeout_seconds": timeout_seconds,
        "poll_interval_seconds": _POLL_INTERVAL_SECONDS,
        "poll_count": poll_count,
        "start_offset": start_offset,
        "end_offset": cursor,
        "bytes_read": total_read,
        "pending_bytes": len(pending),
        "same_session_event_count": len(seen),
        "ready_before_deadline": ready,
        "timed_out": not ready and error is None and completed >= deadline,
        "error": error,
        "events": seen,
    }


def _publish_request_once(request_path: Path, payload: bytes) -> dict[str, object]:
    if request_path.exists():
        raise AuthorityTestError("REQUEST_TARGET_EXISTS", str(request_path))
    temporary = request_path.with_name(
        f".{request_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Same-directory rename is atomic.  os.rename does not replace an
        # existing destination on Windows, so a race still fails closed.
        os.rename(temporary, request_path)
    except FileExistsError as error:
        raise AuthorityTestError("REQUEST_TARGET_COLLISION", str(request_path)) from error
    except OSError as error:
        raise AuthorityTestError("REQUEST_PUBLISH_FAILED", str(error)) from error
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
    return {
        "path": str(request_path),
        "bytes": len(payload),
        "ascii": payload.decode("ascii"),
        "published_once": True,
        "atomic_same_directory_rename": True,
    }


def _write_report_markdown(path: Path, report: dict[str, object]) -> None:
    checks = report.get("checks")
    summary = report.get("native_event_summary")
    poll = report.get("poll")
    lines = [
        "# Rival 授权负例运行验收",
        "",
        "本报告验证 FRA 的 Rival 业务入口被授权门拦截。一次请求在原生层触发三种命令各一次 direct、各一次 vtable，共六次拒绝；本报告不创建 Rival 业务执行请求。",
        "",
        f"- 状态：`{report.get('status')}`",
        f"- artifact：`{report.get('artifact')}`",
        f"- session：`{report.get('session', {}).get('session_id') if isinstance(report.get('session'), dict) else None}`",
        f"- 请求：`{report.get('request', {}).get('ascii') if isinstance(report.get('request'), dict) else None}`",
        f"- 原生日志切片：`{report.get('native_events', {}).get('path') if isinstance(report.get('native_events'), dict) else None}`",
        "",
        "## 轮询和原生结果",
        "",
    ]
    if isinstance(poll, dict):
        lines.extend([
            f"轮询句柄为 `{poll.get('handle')}`，等待上限 `{poll.get('timeout_seconds')}` 秒，实际轮询 `{poll.get('poll_count')}` 次，读取增量 `{poll.get('bytes_read')}` 字节。",
            "",
        ])
    if isinstance(summary, dict):
        lines.extend([
            f"native authority test 数量：`{summary.get('native_test_count')}`；command entry 数量：`{summary.get('command_entry_count')}`；按 kind 计数：`{summary.get('command_kind_counts')}`。",
            f"原生结果 complete：`{summary.get('native_test_contract')}`；before/after 完全相等：`{summary.get('native_test_before_after_equal')}`；drop：`{summary.get('drop_count')}`。",
            "",
        ])
    lines.extend(["## 检查结果", ""])
    if isinstance(checks, dict):
        for name, value in checks.items():
            lines.append(f"- `{name}`：`{value}`")
    lines.extend([
        "",
        "该实验只证明 FRA 来源的 Rival Set/Replace/Remove 入口被授权门拒绝；它不证明 Rival 业务执行、关系变化、费用变化或保存重载。",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _validate_timeout(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be a number") from error
    if not 0 < result <= 60:
        raise argparse.ArgumentTypeError("timeout must be >0 and <=60 seconds")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=_validate_timeout, default=30.0,
                        help="bounded native-event wait, 0 < value <= 60 (default: 30)")
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve(strict=True)
    artifact = _new_artifact(installation.parent, "rival-authority-test")
    log_path = installation.parent / "control-probe.jsonl"
    request_path = installation.parent / "rival-authority-test.req"
    session: ObserverSession | None = None
    log_start_offset: int | None = None
    report: dict[str, object] = {
        "validator": "run_rival_authority_test.py",
        "version": 1,
        "status": "running",
        "mode": "native_rival_authority_negative_only",
        "installation": str(installation),
        "artifact": str(artifact),
        "actor": _ACTOR,
        "expected_date_raw": args.expected_date_raw,
        "timeout_seconds": args.timeout_seconds,
        "request_path": str(request_path),
        "request_published": False,
        "request_publish_count": 0,
        "execute_call_count": 0,
        "execution_requested": False,
        "business_submission": False,
        "queries_published": False,
        "checks": {},
    }
    try:
        binding = _installation_binding(installation)
        report.update(binding)
        executable = game_exe().expanduser().resolve(strict=True)
        report["source"] = {
            "game_executable": str(executable),
            "bytes": executable.stat().st_size,
            "source_binding": "local_config.game_exe",
        }
        session = ObserverSession(installation, executable)
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        installation_record = binding.get("installation", {})
        manifest_record = binding.get("build_manifest", {})
        source_manifest = manifest_record.get("sources") if isinstance(manifest_record, dict) else None
        report["preflight_identity"] = {
            "exact_session": (
                session.session_id == installation_record.get("session_id")
                and session.record.get("session_id") == installation_record.get("session_id")
            ),
            "dll_matches_installation_and_build": (
                session.record.get("dll_sha256") == installation_record.get("declared_dll_sha256")
                and binding.get("build_binding", {}).get("installation_matches_build_manifest") is True
            ),
            "source_manifest_present": isinstance(source_manifest, list) and bool(source_manifest),
            "experiment_id_matches_manifest": (
                installation_record.get("experiment_id") == manifest_record.get("experiment_id")
            ),
            "build_manifest_path": binding.get("build_manifest", {}).get("path"),
        }

        health_wait_started = _utc_now()
        report["health_wait"] = {
            "handle": f"rival-authority-health-{uuid.uuid4().hex}",
            "timeout_seconds": 30.0,
            "started_utc": _utc_text(health_wait_started),
        }
        health_before = wait_runtime_ready(
            session, timeout=30.0, restore_minimized=False)
        report["health_wait"].update({
            "completed_utc": _utc_text(_utc_now()),
            "status": health_before.get("status"),
        })
        report["health_before"] = health_before
        before_probes = _run_snapshots(session, artifact / "before-probes")
        before_checks = _snapshot_boundary_checks(before_probes, args.expected_date_raw)
        report["before_probes"] = _public_probe_records(before_probes)
        report["before_control"] = _control_summary(
            before_probes.get("control_state", {}).get("snapshot", {})
            if isinstance(before_probes.get("control_state"), dict) else {}
        )
        report["baseline_checks"] = before_checks
        identity_checks = report["preflight_identity"]
        if not all(before_checks.values()):
            raise AuthorityTestError("BASELINE_NOT_READY_POR_PAUSED_SNAPSHOTS", "before snapshots failed")
        if not (
                health_before.get("status") == "ready"
                and health_before.get("complete") is True
                and health_before.get("date_raw") == args.expected_date_raw
                and isinstance(identity_checks, dict)
                and identity_checks.get("exact_session") is True
                and identity_checks.get("dll_matches_installation_and_build") is True
                and identity_checks.get("source_manifest_present") is True
                and identity_checks.get("experiment_id_matches_manifest") is True):
            raise AuthorityTestError("SESSION_BUILD_SOURCE_PREFLIGHT_FAILED", "session/build/source binding failed")
        if not log_path.is_file():
            raise AuthorityTestError("NATIVE_LOG_UNAVAILABLE", str(log_path))
        log_start_offset = log_path.stat().st_size
        report["log_start_offset"] = log_start_offset
        payload = f"{_REQUEST_COMMAND} {session.session_id}\n".encode("ascii")
        if payload.decode("ascii") != f"{_REQUEST_COMMAND} {session.session_id}\n":
            raise AuthorityTestError("REQUEST_WIRE_NOT_ASCII_EXACT", "request wire mismatch")
        report["request"] = _publish_request_once(request_path, payload)
        report["request_published"] = True
        report["request_publish_count"] = 1
        report["poll"] = _poll_authority(
            log_path, log_start_offset, session.session_id, args.timeout_seconds)
        after_probes = _run_snapshots(session, artifact / "after-probes")
        health_after = session.health()
        report["health_after"] = health_after
        report["after_probes"] = _public_probe_records(after_probes)
        report["after_control"] = _control_summary(
            after_probes.get("control_state", {}).get("snapshot", {})
            if isinstance(after_probes.get("control_state"), dict) else {}
        )
        report["after_snapshot_checks"] = _snapshot_boundary_checks(
            after_probes, args.expected_date_raw)
        report["external_snapshot_comparison"] = _snapshot_comparison(
            before_probes, after_probes)
        report["checks"].update({
            "health_ready_before": health_before.get("status") == "ready"
            and health_before.get("complete") is True,
            "health_ready_after": health_after.get("status") == "ready"
            and health_after.get("complete") is True,
            "date_stable_after": health_after.get("date_raw") == args.expected_date_raw,
            "exact_session": identity_checks.get("exact_session") is True,
            "dll_source_manifest_bound": (
                identity_checks.get("dll_matches_installation_and_build") is True
                and identity_checks.get("source_manifest_present") is True
                and identity_checks.get("experiment_id_matches_manifest") is True
            ),
            "before_four_snapshots_complete": before_checks.get("four_snapshots_complete") is True,
            "after_four_snapshots_complete": report["after_snapshot_checks"].get(
                "four_snapshots_complete") is True,
            "request_published_once": report["request_publish_count"] == 1,
            "request_wire_exact": report.get("request", {}).get("ascii")
            == f"{_REQUEST_COMMAND} {session.session_id}\n",
            "no_business_execute_request": (
                report["execute_call_count"] == 0
                and report["execution_requested"] is False
                and report["business_submission"] is False
                and report["queries_published"] is False
            ),
            "external_snapshots_unchanged": report[
                "external_snapshot_comparison"].get("all_equal") is True,
            "diplomat_semantics_unchanged": report[
                "external_snapshot_comparison"].get("diplomat_semantics_equal") is True,
        })
    except AuthorityTestError as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_OPERATOR_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        slice_path = artifact / "native-events-slice.jsonl"
        if log_start_offset is not None:
            report["native_events"] = _copy_log_slice(
                log_path, log_start_offset, slice_path)
            if report["native_events"].get("status") == "ok":
                try:
                    report["native_event_summary"] = _authority_event_summary(
                        slice_path, str(report.get("session", {}).get("session_id", "")),
                        args.expected_date_raw)
                except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                    report["native_event_summary"] = {
                        "complete": False,
                        "error": {"type": type(error).__name__, "message": str(error)},
                    }
            else:
                report["native_event_summary"] = {"complete": False, "error": report["native_events"]}
        else:
            try:
                slice_path.open("xb").close()
                report["native_events"] = {
                    "status": "not_started", "path": str(slice_path), "bytes": 0,
                }
            except OSError as error:
                report["native_events"] = {
                    "status": "unknown", "path": str(slice_path),
                    "error": str(error),
                }
            report["native_event_summary"] = {"complete": False, "reason": "NO_LOG_OFFSET"}
        summary = report.get("native_event_summary", {})
        if isinstance(summary, dict):
            report.setdefault("checks", {}).update({
                "native_slice_complete": report.get("native_events", {}).get(
                    "complete") is True,
                "native_authority_test_complete": summary.get(
                    "native_test_contract") is True,
                "native_test_before_equals_after": summary.get(
                    "native_test_before_after_equal") is True,
                "six_command_entries_blocked": summary.get(
                    "command_entries_contract") is True,
                "no_command_entry_drop": summary.get("drop_count") == 0,
                "no_business_events_in_slice": not summary.get("business_events"),
            })
        if report.get("status") == "running":
            report["status"] = "passed" if all(report.get("checks", {}).values()) else "failed"
        elif report.get("status") == "failed":
            # A native failure or a preflight failure must remain failed even
            # if a later bounded log copy happens to contain partial evidence.
            report["status"] = "failed"
        _write_json(artifact / "report.json", report)
        _write_report_markdown(artifact / "report.md", report)

    print(json.dumps({
        "status": report["status"],
        "artifact": str(artifact),
        "native_slice": str(artifact / "native-events-slice.jsonl"),
        "request_published": report.get("request_published"),
    }, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
