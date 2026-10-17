#!/usr/bin/env python3
"""Run one Declare War authority negative fixture.

The supplied installation must already contain the native Declare War
preflight and entry guard.  This operator sends one fixed TEST_ONLY packet,
never calls the business execution API, and records bounded before/after
snapshots plus the native rejection.  Run the two routes in separate fresh
installations because the native fixture consumes each route once.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
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
from work.run_alliance_execution import _copy_log_slice, _write_json  # noqa: E402
from work.run_improve_relations_execution import _new_artifact  # noqa: E402
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _snapshots_complete,
)
from work.validate_alliance_queries import _stable_summary  # noqa: E402
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _diplomat_semantics,
    _run_snapshots,
)


_ACTOR = "FRA"
_RECIPIENT = "ENG"
_PLAYER_SLOT = 189  # POR in the controlled experiment
_ACTION = "declare_war"
_EXPECTED_REASON = "UNAUTHORIZED_FRA_DECLARE_WAR"
_WIRES = {
    "transport": "TEST_ONLY FRA_DECLARE_WAR_ENG_WITHOUT_AUTHORITY\n",
    "direct_entry": "TEST_ONLY FRA_DECLARE_WAR_ENG_DIRECT_WITHOUT_AUTHORITY\n",
}
_POLL_INTERVAL_SECONDS = 0.10
_MAX_POLL_SECONDS = 60.0
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


def _war_pair_signature(snapshot: object) -> dict[str, object]:
    """Keep only the bounded FRA/ENG war association needed by this fixture."""

    if not isinstance(snapshot, dict):
        return {"current_raw_date": None, "countries": []}
    countries = snapshot.get("countries")
    selected: list[dict[str, object]] = []
    if isinstance(countries, list):
        for item in countries:
            if not isinstance(item, dict) or item.get("slot") not in (122, 46):
                continue
            pairs = item.get("pairs")
            normalized_pairs: list[dict[str, object]] = []
            if isinstance(pairs, list):
                for pair in pairs:
                    if isinstance(pair, dict):
                        normalized_pairs.append({
                            "slot": pair.get("slot"),
                            "war": pair.get("war"),
                        })
            selected.append({
                "slot": item.get("slot"),
                "pair_at_war": item.get("pair_at_war"),
                "pairs": normalized_pairs,
            })
    selected.sort(key=lambda item: int(item["slot"]) if isinstance(item.get("slot"), int) else -1)
    return {
        "current_raw_date": snapshot.get("current_raw_date"),
        "countries": selected,
    }


def _boundary_checks(records: object, expected_date: int) -> dict[str, bool]:
    if not isinstance(records, dict):
        return {"four_snapshots_complete": False}
    snapshots = {
        name: value.get("snapshot")
        for name, value in records.items()
        if isinstance(value, dict) and isinstance(value.get("snapshot"), dict)
    }
    control = snapshots.get("control_state")
    alliance = snapshots.get("alliance_state")
    diplomats = snapshots.get("diplomats")
    war = snapshots.get("war_state")
    checks: dict[str, bool] = {
        "four_snapshots_complete": _snapshots_complete(records),
        "control_por_paused_date": (
            isinstance(control, dict)
            and control.get("date_raw") == expected_date
            and control.get("player_slot") == _PLAYER_SLOT
            and control.get("paused_flag") == 1
        ),
        "alliance_por_date": (
            isinstance(alliance, dict)
            and alliance.get("date_raw") == expected_date
            and alliance.get("player") == "POR"
        ),
        "diplomats_date": (
            isinstance(diplomats, dict)
            and diplomats.get("current_raw_date") == expected_date
        ),
        "war_date": (
            isinstance(war, dict)
            and war.get("current_raw_date") == expected_date
        ),
        "war_fra_eng_slots": (
            isinstance(war, dict)
            and {item.get("slot") for item in war.get("countries", [])
                 if isinstance(item, dict)} == {122, 46}
        ),
    }
    return checks


def _public_snapshots(records: object) -> dict[str, dict[str, object]]:
    if not isinstance(records, dict):
        return {}
    return {
        str(name): {
            key: item.get(key)
            for key in (
                "status", "name", "script", "snapshot_path",
                "snapshot_completeness", "snapshot_sha256",
            )
        }
        for name, item in records.items()
        if isinstance(item, dict)
    }


def _read_events(path: Path) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    with path.open("rb") as stream:
        for raw in stream:
            if len(raw) > _MAX_LOG_LINE_BYTES:
                continue
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                events.append(value)
    return events


def _authority_event_summary(events: list[dict[str, object]], session_id: str,
                             expected_date: int, route: str) -> dict[str, object]:
    session_events = [event for event in events if event.get("session_id") == session_id]
    dispatches = [event for event in session_events
                  if event.get("event") == "native_alliance_authority_test_dispatched"]
    rejections = [event for event in session_events
                  if event.get("event") == "native_alliance_execution_rejected"
                  and event.get("reason") == _EXPECTED_REASON]
    preflight_failures = [event for event in session_events
                          if event.get("event") == "native_alliance_execution_rejected"
                          and event.get("reason") == "TEST_NATIVE_PREFLIGHT_FAILED"]
    business_events = [event for event in session_events
                       if event.get("event") in {
                           "native_declare_war_submission_result",
                           "native_declare_war_execution_result",
                       } or (isinstance(event.get("event"), str)
                             and "submission" in event["event"])]
    dispatch = dispatches[0] if len(dispatches) == 1 else None
    # The native fixture uses ``dispatched`` as a common completion flag.  The
    # transport branch obtains that flag from the dispatcher, while the direct
    # entry branch initializes it to true before calling the guarded entry.
    # Therefore direct_entry must validate a real boolean and the route/reject
    # evidence, rather than require the value to be false.
    dispatcher_accepted = (
        dispatch.get("dispatcher_accepted")
        if isinstance(dispatch, dict) else None
    )
    dispatcher_accepted_contract = (
        isinstance(dispatch, dict)
        and (
            dispatcher_accepted is True
            if route == "transport"
            else type(dispatcher_accepted) is bool
        )
    )
    dispatch_contract = (
        isinstance(dispatch, dict)
        and dispatch.get("action_id") == _ACTION
        and dispatch.get("actor") == _ACTOR
        and dispatch.get("recipient") == _RECIPIENT
        and dispatch.get("phase") == "initiate"
        and dispatch.get("date_raw") == expected_date
        and dispatch.get("dispatch_route") == route
        and dispatcher_accepted_contract
        and dispatch.get("authority_seed_created") is False
        and dispatch.get("casus_belli") == "cb_core"
        and dispatch.get("war_goal_province") == 177
        and dispatch.get("war_goal_beneficiary") == "FRA"
    )
    rejection_contract = (
        len(rejections) == 1
        and rejections[0].get("submitted") is False
    )
    return {
        "session_event_count": len(session_events),
        "dispatch_count": len(dispatches),
        "dispatch": dispatch,
        "dispatch_contract": dispatch_contract,
        "rejection_count": len(rejections),
        "rejection": rejections[0] if len(rejections) == 1 else None,
        "rejection_contract": rejection_contract,
        "preflight_failure_count": len(preflight_failures),
        "business_events": business_events,
        "complete": (
            dispatch_contract and rejection_contract
            and not preflight_failures and not business_events
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
    lines = (pending + chunk).split(b"\n")
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
                    expected_date: int, route: str,
                    timeout_seconds: float) -> dict[str, object]:
    started = _utc_now()
    deadline = started + timedelta(seconds=timeout_seconds)
    handle = f"declare-war-authority-poll-{uuid.uuid4().hex}"
    cursor = start_offset
    pending = b""
    total_read = 0
    poll_count = 0
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
            if event.get("session_id") == session_id:
                seen.append(event)
        summary = _authority_event_summary(seen, session_id, expected_date, route)
        ready = summary.get("dispatch_contract") is True and summary.get(
            "rejection_contract") is True
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
        "ready_before_deadline": ready,
        "timed_out": not ready and error is None and completed >= deadline,
        "error": error,
        "events": seen,
    }


def _publish_once(path: Path, payload: bytes) -> dict[str, object]:
    if path.exists():
        raise AuthorityTestError("REQUEST_TARGET_EXISTS", str(path))
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temporary, path)
    except FileExistsError as error:
        raise AuthorityTestError("REQUEST_TARGET_COLLISION", str(path)) from error
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
        "path": str(path),
        "bytes": len(payload),
        "ascii": payload.decode("ascii"),
        "published_once": True,
        "atomic_same_directory_rename": True,
    }


def _validate_timeout(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be a number") from error
    if not 0 < result <= _MAX_POLL_SECONDS:
        raise argparse.ArgumentTypeError("timeout must be >0 and <=60 seconds")
    return result


def _write_report_markdown(path: Path, report: dict[str, object]) -> None:
    checks = report.get("checks")
    lines = [
        "# Declare War 授权负例运行验收",
        "",
        "本实验只构造原生合法的 FRA→ENG 宣战包，然后从 transport 或 direct entry 入口验证授权门拒绝。实验不调用业务 execute，不创建 ledger seed。",
        "",
        f"- 状态：`{report.get('status')}`",
        f"- route：`{report.get('route')}`",
        f"- wire：`{report.get('request', {}).get('ascii') if isinstance(report.get('request'), dict) else None}`",
        f"- native slice：`{report.get('native_events', {}).get('path') if isinstance(report.get('native_events'), dict) else None}`",
        "",
        "## 检查结果",
        "",
    ]
    if isinstance(checks, dict):
        lines.extend(f"- `{name}`：`{value}`" for name, value in checks.items())
    lines.extend([
        "",
        "该负例只覆盖授权入口拦截、日期与战争关联不变、外交官状态不变；不代表宣战业务执行已经接入。",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--route", choices=tuple(_WIRES), default="transport")
    parser.add_argument("--timeout-seconds", type=_validate_timeout, default=30.0,
                        help="bounded native-event wait, 0 < value <= 60 (default: 30)")
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve(strict=True)
    artifact = _new_artifact(installation.parent, "declare-war-authority-test")
    log_path = installation.parent / "control-probe.jsonl"
    request_path = installation.parent / "diplomacy-authority-test.req"
    wire = _WIRES[args.route]
    report: dict[str, object] = {
        "validator": "run_declare_war_authority_test.py",
        "version": 1,
        "status": "running",
        "mode": "native_declare_war_authority_negative_only",
        "installation": str(installation),
        "artifact": str(artifact),
        "route": args.route,
        "actor": _ACTOR,
        "recipient": _RECIPIENT,
        "action_id": _ACTION,
        "expected_reason": _EXPECTED_REASON,
        "expected_date_raw": args.expected_date_raw,
        "request_path": str(request_path),
        "request_published": False,
        "request_publish_count": 0,
        "execute_call_count": 0,
        "business_submission": False,
        "authority_seed_created": False,
        "checks": {},
    }
    log_start_offset: int | None = None
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
        report["preflight_identity"] = {
            "exact_session": (
                session.session_id == installation_record.get("session_id")
                and session.record.get("session_id") == installation_record.get("session_id")
            ),
            "dll_matches_installation_and_build": (
                session.record.get("dll_sha256") == installation_record.get("declared_dll_sha256")
                and binding.get("build_binding", {}).get(
                    "installation_matches_build_manifest") is True
            ),
        }
        health_before = wait_runtime_ready(session, timeout=30.0, restore_minimized=False)
        report["health_before"] = health_before
        before = _run_snapshots(session, artifact / "before-probes")
        report["before_probes"] = _public_snapshots(before)
        report["before_control"] = _control_summary(
            before.get("control_state", {}).get("snapshot", {})
            if isinstance(before.get("control_state"), dict) else {}
        )
        baseline_checks = _boundary_checks(before, args.expected_date_raw)
        report["baseline_checks"] = baseline_checks
        identity = report["preflight_identity"]
        if not all(baseline_checks.values()):
            raise AuthorityTestError("BASELINE_NOT_READY_POR_PAUSED_SNAPSHOTS", "before snapshots failed")
        if not (
            health_before.get("status") == "ready"
            and health_before.get("complete") is True
            and isinstance(identity, dict)
            and identity.get("exact_session") is True
            and identity.get("dll_matches_installation_and_build") is True
        ):
            raise AuthorityTestError("SESSION_BUILD_PREFLIGHT_FAILED", "session/build binding failed")
        if not log_path.is_file():
            raise AuthorityTestError("NATIVE_LOG_UNAVAILABLE", str(log_path))
        log_start_offset = log_path.stat().st_size
        report["log_start_offset"] = log_start_offset
        payload = wire.encode("ascii")
        report["request"] = _publish_once(request_path, payload)
        report["request_published"] = True
        report["request_publish_count"] = 1
        report["poll"] = _poll_authority(
            log_path, log_start_offset, session.session_id,
            args.expected_date_raw, args.route, args.timeout_seconds)
        after = _run_snapshots(session, artifact / "after-probes")
        report["health_after"] = session.health()
        report["after_probes"] = _public_snapshots(after)
        report["after_control"] = _control_summary(
            after.get("control_state", {}).get("snapshot", {})
            if isinstance(after.get("control_state"), dict) else {}
        )
        report["war_pair_before"] = _war_pair_signature(
            before.get("war_state", {}).get("snapshot", {})
            if isinstance(before.get("war_state"), dict) else {}
        )
        report["war_pair_after"] = _war_pair_signature(
            after.get("war_state", {}).get("snapshot", {})
            if isinstance(after.get("war_state"), dict) else {}
        )
        before_war = before.get("war_state", {}).get("snapshot", {})
        after_war = after.get("war_state", {}).get("snapshot", {})
        before_diplomats = before.get("diplomats", {}).get("snapshot", {})
        after_diplomats = after.get("diplomats", {}).get("snapshot", {})
        report["checks"].update({
            "health_ready_before": health_before.get("status") == "ready"
            and health_before.get("complete") is True,
            "health_ready_after": report["health_after"].get("status") == "ready",
            "before_four_snapshots_complete": _snapshots_complete(before),
            "after_four_snapshots_complete": _snapshots_complete(after),
            "date_paused_unchanged": (
                report["before_control"] == report["after_control"]
                and report["after_control"].get("date_raw") == args.expected_date_raw
                and report["after_control"].get("player_slot") == _PLAYER_SLOT
                and report["after_control"].get("paused_flag") == 1
            ),
            "war_pair_unchanged": report["war_pair_before"] == report["war_pair_after"],
            "war_snapshot_stable": _stable_summary("war_state", before_war)
            == _stable_summary("war_state", after_war),
            "diplomat_semantics_unchanged": (
                _diplomat_semantics(before_diplomats)
                == _diplomat_semantics(after_diplomats)
            ),
            "request_published_once": report["request_publish_count"] == 1,
            "request_wire_exact": report.get("request", {}).get("ascii") == wire,
            "no_business_execute_request": (
                report["execute_call_count"] == 0
                and report["business_submission"] is False
            ),
        })
    except AuthorityTestError as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:  # keep failed artifacts reviewable
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_OPERATOR_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if log_start_offset is not None:
            report["native_events"] = _copy_log_slice(
                log_path, log_start_offset, artifact / "native-events-slice.jsonl")
            native = report["native_events"]
            if isinstance(native, dict) and native.get("status") == "ok":
                try:
                    events = _read_events(artifact / "native-events-slice.jsonl")
                    report["native_event_summary"] = _authority_event_summary(
                        events, str(report.get("session", {}).get("session_id", "")),
                        args.expected_date_raw, args.route)
                except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                    report["native_event_summary"] = {
                        "complete": False,
                        "error": {"type": type(error).__name__, "message": str(error)},
                    }
            else:
                report["native_event_summary"] = {"complete": False, "error": native}
        else:
            report["native_events"] = {
                "status": "not_started",
                "path": str(artifact / "native-events-slice.jsonl"),
                "bytes": 0,
            }
            report["native_event_summary"] = {"complete": False, "reason": "NO_LOG_OFFSET"}
        summary = report.get("native_event_summary", {})
        if isinstance(summary, dict):
            report.setdefault("checks", {}).update({
                "native_event_slice_complete": report.get("native_events", {}).get(
                    "complete") is True,
                "native_authority_dispatch_complete": summary.get(
                    "dispatch_contract") is True,
                "native_expected_rejection": summary.get(
                    "rejection_contract") is True,
                "no_native_preflight_failure": summary.get(
                    "preflight_failure_count") == 0,
                "no_business_events": not summary.get("business_events"),
                "authority_seed_not_created": (
                    summary.get("dispatch", {}).get("authority_seed_created") is False
                    if isinstance(summary.get("dispatch"), dict) else False
                ),
            })
        if report.get("status") == "running":
            report["status"] = "passed" if all(report.get("checks", {}).values()) else "failed"
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
