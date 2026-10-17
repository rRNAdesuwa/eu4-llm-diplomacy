#!/usr/bin/env python3
"""Run one bounded Peace authority negative probe.

The operator discovers the FRA/ENG war through the public read-only
inspection interface, then publishes exactly one TEST_ONLY authority packet.
It never calls business execution, advances time, saves the game, or retries
an expired/unknown request.  ``native_rules_available`` and the three native
predicate values are reported separately from the no-authority interception;
this report is not a legal-command acceptance claim.
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

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import _copy_log_slice, _write_json  # noqa: E402
from work.run_improve_relations_execution import _new_artifact  # noqa: E402
from work.run_peace_empty_offer_queries import (  # noqa: E402
    _has_private_fields,
    _public_context_contract,
    _single_discovered_war_id,
)
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _public_probe_records,
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
_ACTION = "white_peace"
_PLAYER_SLOT = 189  # POR in the controlled observer fixture
_EXPECTED_REASON = "UNAUTHORIZED_FRA_PEACE_OFFER"
_REJECTION_EVENT = "native_alliance_execution_rejected"
_DISPATCH_EVENT = "native_peace_authority_test_dispatched"
_HANDLER_EVENT = "native_peace_handler_entry"
_WIRES = {
    ("transport", "white"): "TEST_ONLY FRA_PEACE_ENG_WHITE_WITHOUT_AUTHORITY\n",
    ("transport", "money"): "TEST_ONLY FRA_PEACE_ENG_MONEY_WITHOUT_AUTHORITY\n",
    ("transport", "province"): "TEST_ONLY FRA_PEACE_ENG_PROVINCE_WITHOUT_AUTHORITY\n",
    ("direct_entry", "white"): "TEST_ONLY FRA_PEACE_ENG_WHITE_DIRECT_WITHOUT_AUTHORITY\n",
    ("direct_entry", "money"): "TEST_ONLY FRA_PEACE_ENG_MONEY_DIRECT_WITHOUT_AUTHORITY\n",
    ("direct_entry", "province"): "TEST_ONLY FRA_PEACE_ENG_PROVINCE_DIRECT_WITHOUT_AUTHORITY\n",
    ("handler_entry", "white"): "TEST_ONLY FRA_PEACE_ENG_WHITE_HANDLER_WITHOUT_AUTHORITY\n",
    ("handler_entry", "money"): "TEST_ONLY FRA_PEACE_ENG_MONEY_HANDLER_WITHOUT_AUTHORITY\n",
    ("handler_entry", "province"): "TEST_ONLY FRA_PEACE_ENG_PROVINCE_HANDLER_WITHOUT_AUTHORITY\n",
}
_POLL_INTERVAL_SECONDS = 0.10
_MAX_POLL_SECONDS = 60.0
_MAX_POLL_READ_BYTES = 8 * 1024 * 1024
_POLL_READ_CHUNK_BYTES = 256 * 1024
_MAX_LOG_LINE_BYTES = 256 * 1024
_TEST_PREFLIGHT_REASONS = frozenset({
    "TEST_NATIVE_PREFLIGHT_FAILED",
    "TEST_PEACE_PREPARATION_FAILED",
    "TEST_PEACE_COUNTRY_UNAVAILABLE",
    "TEST_ALREADY_CONSUMED",
})


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


def _control_is_expected(value: object, expected_date_raw: int) -> bool:
    return value == {
        "date_raw": expected_date_raw,
        "paused_flag": 1,
        "player_slot": _PLAYER_SLOT,
    }


def _war_context_signature(value: object, actor: str = _ACTOR,
                           recipient: str = _RECIPIENT) -> list[dict[str, object]] | None:
    """Keep only public, stable context identity for before/after comparison."""

    if not _public_context_contract(value, actor, recipient):
        return None
    rows = value.get("war_contexts")
    if not isinstance(rows, list):
        return None
    result: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        result.append({
            "war_id": row.get("war_id"),
            "identity_scope": row.get("identity_scope"),
            "actor": row.get("actor"),
            "recipient": row.get("recipient"),
            "pair_at_war": row.get("pair_at_war"),
        })
    result.sort(key=lambda item: str(item.get("war_id")))
    return result


def _snapshot_stability(before: object, after: object) -> dict[str, bool]:
    """Compare the four bounded snapshots after removing pointer volatility."""

    if not isinstance(before, dict) or not isinstance(after, dict):
        return {
            "control_state_unchanged": False,
            "alliance_state_unchanged": False,
            "diplomats_unchanged": False,
            "war_state_unchanged": False,
        }
    output: dict[str, bool] = {}
    for kind in ("control_state", "alliance_state", "diplomats", "war_state"):
        left = before.get(kind)
        right = after.get(kind)
        left_snapshot = left.get("snapshot") if isinstance(left, dict) else None
        right_snapshot = right.get("snapshot") if isinstance(right, dict) else None
        if not isinstance(left_snapshot, dict) or not isinstance(right_snapshot, dict):
            output[f"{kind}_unchanged"] = False
            continue
        if kind == "control_state":
            output[f"{kind}_unchanged"] = _control_summary(left_snapshot) == _control_summary(
                right_snapshot)
        elif kind == "diplomats":
            try:
                output[f"{kind}_unchanged"] = (
                    _diplomat_semantics(left_snapshot)
                    == _diplomat_semantics(right_snapshot))
            except Exception:
                output[f"{kind}_unchanged"] = False
        else:
            try:
                output[f"{kind}_unchanged"] = (
                    _stable_summary(kind, left_snapshot)
                    == _stable_summary(kind, right_snapshot))
            except Exception:
                output[f"{kind}_unchanged"] = False
    return output


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


def _event_route(event: dict[str, object]) -> object:
    """Accept the established dispatch_route spelling and the new route alias."""

    return event.get("route", event.get("dispatch_route"))


def _transport_record_contract(
        events: list[dict[str, object]], dispatch: dict[str, object] | None,
        session_id: str) -> tuple[bool, dict[str, object] | None]:
    """Verify payload copying from the separate transport completion event."""

    if not isinstance(dispatch, dict):
        return False, None
    source_wrapper = dispatch.get("source_wrapper")
    source_action = dispatch.get("source_action")
    for event in events:
        if event.get("event") != "native_alliance_transport_completed":
            continue
        if event.get("session_id") != session_id:
            continue
        source = event.get("source")
        loaded = event.get("loaded")
        if not isinstance(source, dict) or not isinstance(loaded, dict):
            continue
        if source.get("addr") != source_wrapper or source.get("action") != source_action:
            continue
        source_payload = source.get("payload")
        loaded_payload = loaded.get("payload")
        source_peace = (
            source_payload.get("peace")
            if isinstance(source_payload, dict) else None)
        loaded_peace = (
            loaded_payload.get("peace")
            if isinstance(loaded_payload, dict) else None)
        source_term_count = (
            source_peace.get("term_count")
            if isinstance(source_peace, dict) else None)
        loaded_term_count = (
            loaded_peace.get("term_count")
            if isinstance(loaded_peace, dict) else None)
        contract = (
            event.get("header_equal") is True
            and event.get("payload_equal") is True
            and event.get("caller_verified") is True
            and event.get("completed") is True
            and isinstance(event.get("load_count"), int)
            and not isinstance(event.get("load_count"), bool)
            and event.get("load_count", 0) >= 1
            and isinstance(event.get("matching_count"), int)
            and not isinstance(event.get("matching_count"), bool)
            and event.get("matching_count", 0) >= 1
            and source_payload.get("family") == "peace"
            if isinstance(source_payload, dict) else False
        )
        contract = contract and (
            isinstance(loaded_payload, dict)
            and loaded_payload.get("family") == "peace"
            and isinstance(source_peace, dict)
            and isinstance(loaded_peace, dict)
            and source_peace.get("complete") is True
            and loaded_peace.get("complete") is True
            and isinstance(source_term_count, int)
            and not isinstance(source_term_count, bool)
            and isinstance(loaded_term_count, int)
            and not isinstance(loaded_term_count, bool)
            and source_term_count == loaded_term_count
        )
        observation = {
            "event": event.get("event"),
            "session_id": event.get("session_id"),
            "source_addr": source.get("addr"),
            "source_action": source.get("action"),
            "header_equal": event.get("header_equal"),
            "payload_equal": event.get("payload_equal"),
            "caller_verified": event.get("caller_verified"),
            "completed": event.get("completed"),
            "load_count": event.get("load_count"),
            "matching_count": event.get("matching_count"),
            "source_family": source_payload.get("family")
            if isinstance(source_payload, dict) else None,
            "loaded_family": loaded_payload.get("family")
            if isinstance(loaded_payload, dict) else None,
            "source_peace_complete": source_peace.get("complete")
            if isinstance(source_peace, dict) else None,
            "loaded_peace_complete": loaded_peace.get("complete")
            if isinstance(loaded_peace, dict) else None,
            "source_term_count": source_term_count,
            "loaded_term_count": loaded_term_count,
            "contract": contract,
        }
        if contract:
            return True, observation
    return False, None


def _authority_event_summary(events: list[dict[str, object]], session_id: str,
                             expected_date: int, route: str, term: str,
                             expected_war_id: str | None = None) -> dict[str, object]:
    session_events = [event for event in events if event.get("session_id") == session_id]
    dispatches = [event for event in session_events
                  if event.get("event") == _DISPATCH_EVENT]
    rejections = [event for event in session_events
                  if event.get("event") == _REJECTION_EVENT
                  and event.get("reason") == _EXPECTED_REASON]
    preflight_failures = [event for event in session_events
                          if event.get("event") == _REJECTION_EVENT
                          and event.get("reason") in _TEST_PREFLIGHT_REASONS]
    handler_entries = [event for event in session_events
                       if event.get("event") == _HANDLER_EVENT]
    business_events = [event for event in session_events
                       if event.get("event") in {
                           "native_peace_submission_result",
                           "native_peace_execution_result",
                           "native_alliance_submission_result",
                           "native_alliance_execution_result",
                       } or (isinstance(event.get("event"), str)
                             and ("submission" in event["event"]
                                  or "execution_result" in event["event"]))]
    dispatch = dispatches[0] if len(dispatches) == 1 else None
    predicate_fields = ("native_validity", "common_gate", "send_gate")
    native_predicates = {
        field: dispatch.get(field) if isinstance(dispatch, dict) else None
        for field in predicate_fields
    }
    native_rules_available = (
        isinstance(dispatch, dict)
        and all(type(native_predicates[field]) is bool for field in predicate_fields)
    )
    dispatcher_accepted = (
        dispatch.get("dispatcher_accepted") if isinstance(dispatch, dict) else None)
    source_wrapper = dispatch.get("source_wrapper") if isinstance(dispatch, dict) else None
    source_action = dispatch.get("source_action") if isinstance(dispatch, dict) else None
    transport_contract, transport_observation = _transport_record_contract(
        session_events, dispatch, session_id)
    dispatch_contract = (
        isinstance(dispatch, dict)
        and dispatch.get("term") == term
        and _event_route(dispatch) == route
        and dispatch.get("date_raw") == expected_date
        and dispatch.get("family") == "peace"
        and dispatch.get("war_context_complete") is True
        and (expected_war_id is None or dispatch.get("war_id") == expected_war_id)
        and isinstance(source_wrapper, str) and bool(source_wrapper)
        and isinstance(source_action, str) and bool(source_action)
        and dispatch.get("snapshot_complete") is True
        and dispatch.get("logical_copy_equal") is True
        and type(dispatcher_accepted) is bool
        and dispatch.get("authority_seed_created") is False
        and native_rules_available
        and (route != "transport" or transport_contract)
    )
    handler_entry = handler_entries[0] if len(handler_entries) == 1 else None
    handler_contract = (
        route != "handler_entry"
        or (
            isinstance(handler_entry, dict)
            and handler_entry.get("session_id") == session_id
            and handler_entry.get("action") == source_action
            and handler_entry.get("controlled_endpoint") is True
            and handler_entry.get("snapshot_complete") is True
            and type(handler_entry.get("state_raw")) is int
            and handler_entry.get("state_raw") == 0
            and handler_entry.get("allowed") is False
            and type(handler_entry.get("native_forward_count")) is int
            and handler_entry.get("native_forward_count") == 0
        )
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
        "native_rules_available": native_rules_available,
        "native_predicates": native_predicates,
        "transport_contract": transport_contract,
        "transport_observation": transport_observation,
        "handler_count": len(handler_entries),
        "handler_entry": handler_entry,
        "handler_contract": handler_contract,
        "rejection_count": len(rejections),
        "rejection_event_name": _REJECTION_EVENT,
        "rejection": rejections[0] if len(rejections) == 1 else None,
        "rejection_contract": rejection_contract,
        "preflight_failure_count": len(preflight_failures),
        "preflight_failure_reasons": [event.get("reason") for event in preflight_failures],
        "business_events": business_events,
        "no_authority_interception_established": (
            rejection_contract and handler_contract
            and not preflight_failures and not business_events),
        "complete": (
            dispatch_contract and handler_contract and rejection_contract
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
                    expected_date: int, route: str, term: str,
                    expected_war_id: str,
                    timeout_seconds: float) -> dict[str, object]:
    started = _utc_now()
    deadline = started + timedelta(seconds=timeout_seconds)
    handle = f"peace-authority-poll-{uuid.uuid4().hex}"
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
        summary = _authority_event_summary(
            seen, session_id, expected_date, route, term, expected_war_id)
        ready = summary.get("dispatch_contract") is True and summary.get(
            "rejection_contract") is True and summary.get(
                "handler_contract") is True
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
    summary = report.get("native_event_summary")
    lines = [
        "# Peace 授权负例运行证据",
        "",
        "本实验只发布一次 TEST_ONLY Peace authority packet。它不调用业务执行接口、不推进日期、不保存游戏。",
        "报告把原生规则可观测性与无授权拦截分开记录，因此状态不能解释为合法议和执行验收。",
        "",
        f"- 状态：`{report.get('status')}`",
        f"- term：`{report.get('term')}`",
        f"- route：`{report.get('route')}`",
        f"- war_id：`{report.get('war_id')}`",
        f"- native_rules_available：`{report.get('native_rules_available')}`",
        f"- no_authority_interception_established：`{report.get('no_authority_interception_established')}`",
        f"- native slice：`{report.get('native_events', {}).get('path') if isinstance(report.get('native_events'), dict) else None}`",
        "",
        "## 检查结果",
        "",
    ]
    if isinstance(checks, dict):
        lines.extend(f"- `{name}`：`{value}`" for name, value in checks.items())
    if isinstance(summary, dict):
        lines.extend([
            "",
            f"- 原生 predicate：`{summary.get('native_predicates')}`",
            f"- 原生拒绝事件：`{summary.get('rejection_event_name')}`",
        ])
        if report.get("route") == "handler_entry":
            handler = summary.get("handler_entry")
            lines.extend([
                f"- handler entry 合同：`{summary.get('handler_contract')}`",
                f"- handler event：`{handler}`",
            ])
    lines.extend([
        "",
        "native_validity、common_gate、send_gate 按事件原值保存；它们可以为 false，脚本不会把 false 改写成成功或失败以外的结论。",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--route", choices=("transport", "direct_entry", "handler_entry"),
                        default="transport")
    parser.add_argument("--term", choices=("white", "money", "province"), required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=_validate_timeout, default=30.0,
                        help="bounded native-event wait, 0 < value <= 60 seconds")
    args = parser.parse_args(argv)

    installation = args.installation.expanduser().resolve(strict=True)
    artifact = _new_artifact(installation.parent, "peace-authority-test")
    session = ObserverSession(installation, game_exe())
    log = session.directory / "control-probe.jsonl"
    request_path = session.directory / "diplomacy-authority-test.req"
    wire = _WIRES[(args.route, args.term)]
    report: dict[str, Any] = {
        "validator": Path(__file__).name,
        "version": 1,
        "status": "running",
        "mode": "native_peace_authority_negative_probe",
        "installation": str(installation),
        "artifact": str(artifact),
        "route": args.route,
        "term": args.term,
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
        "time_advance_call_count": 0,
        "save_call_count": 0,
        "authority_seed_created": False,
        "native_rules_available": None,
        "no_authority_interception_established": False,
        "checks": {},
    }
    log_start: int | None = None
    before: dict[str, dict[str, object]] | None = None
    after: dict[str, dict[str, object]] | None = None
    before_query: dict[str, object] | None = None
    after_query: dict[str, object] | None = None
    try:
        binding = _installation_binding(installation)
        report.update(binding)
        executable = game_exe().expanduser().resolve(strict=True)
        report["source"] = {
            "game_executable": str(executable),
            "bytes": executable.stat().st_size,
            "source_binding": "local_config.game_exe",
        }
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
        report["before"] = {
            "health": health_before,
            "probes": _public_probe_records(before),
            "control": _control_summary(before["control_state"]["snapshot"]),
        }
        if (health_before.get("status") != "ready"
                or health_before.get("complete") is not True
                or not _control_is_expected(report["before"]["control"], args.expected_date_raw)
                or not _snapshots_complete(before)):
            raise AuthorityTestError(
                "BASELINE_NOT_READY_POR_PAUSED_SNAPSHOTS",
                "before snapshots did not prove paused POR at the expected date")
        identity = report["preflight_identity"]
        if not (isinstance(identity, dict)
                and identity.get("exact_session") is True
                and identity.get("dll_matches_installation_and_build") is True):
            raise AuthorityTestError("SESSION_BUILD_PREFLIGHT_FAILED",
                                     "session/build binding failed")
        if not log.is_file():
            raise AuthorityTestError("NATIVE_LOG_UNAVAILABLE", str(log))

        # This first query initializes the public observer registry and obtains
        # the opaque war id.  The script never invents a query id or war id.
        with DurableJournal(artifact / "diplomacy.sqlite3",
                            session.experiment_id, session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            report["query_call_count"] = 1
            before_query = api.inspect_diplomatic_action(
                _ACTION, _ACTOR, _RECIPIENT, phase="initiate", parameters={})
            _write_json(artifact / "war-discovery.json", before_query)
            report["before_query"] = before_query
            war_id = _single_discovered_war_id(before_query, _ACTOR, _RECIPIENT)
            if war_id is None:
                raise AuthorityTestError(
                    "PEACE_WAR_DISCOVERY_INCOMPLETE",
                    "white_peace discovery did not return one complete public war context")
            report["war_id"] = war_id
            report["war_context_before"] = _war_context_signature(before_query)
            report["public_query_has_no_private_identifiers"] = not _has_private_fields(
                before_query)
            if report["public_query_has_no_private_identifiers"] is not True:
                raise AuthorityTestError("PUBLIC_QUERY_CONTAINS_PRIVATE_IDENTIFIER",
                                         "discovery projection exposed native-only data")

            log_start = log.stat().st_size
            report["log_start_offset"] = log_start
            report["request"] = _publish_once(request_path, wire.encode("ascii"))
            report["request_published"] = True
            report["request_publish_count"] = 1
            report["poll"] = _poll_authority(
                log, log_start, session.session_id, args.expected_date_raw,
                args.route, args.term, war_id, args.timeout_seconds)

            # A second read-only inspection confirms the same public war
            # context after the one TEST_ONLY packet; it never resubmits it.
            report["query_call_count"] += 1
            after_query = api.inspect_diplomatic_action(
                _ACTION, _ACTOR, _RECIPIENT, phase="initiate", parameters={})
            _write_json(artifact / "war-discovery-after.json", after_query)
            report["after_query"] = after_query
            report["war_context_after"] = _war_context_signature(after_query)

        after = _run_snapshots(session, artifact / "after-probes")
        report["health_after"] = session.health()
        report["after"] = {
            "health": report["health_after"],
            "probes": _public_probe_records(after),
            "control": _control_summary(after["control_state"]["snapshot"]),
        }
        stability = _snapshot_stability(before, after)
        report["snapshot_stability"] = stability
        report["checks"].update({
            "preflight_health_ready": health_before.get("status") == "ready"
            and health_before.get("complete") is True,
            "health_ready_after": report["health_after"].get("status") == "ready",
            "before_four_snapshots_complete": _snapshots_complete(before),
            "after_four_snapshots_complete": _snapshots_complete(after),
            "por_paused_same_date": (
                _control_is_expected(report["before"]["control"], args.expected_date_raw)
                and report["before"]["control"] == report["after"]["control"]),
            "four_snapshot_business_state_unchanged": all(stability.values()),
            "same_public_war_context": (
                report.get("war_context_before") is not None
                and report.get("war_context_before") == report.get("war_context_after")
                and report.get("war_id") == _single_discovered_war_id(
                    after_query, _ACTOR, _RECIPIENT)
            ),
            "after_public_query_has_no_private_identifiers": not _has_private_fields(
                after_query),
            "request_published_once": report["request_publish_count"] == 1,
            "request_wire_exact": report.get("request", {}).get("ascii") == wire,
            "no_business_execute_or_world_mutation_request": (
                report["execute_call_count"] == 0
                and report["business_submission"] is False
                and report["time_advance_call_count"] == 0
                and report["save_call_count"] == 0),
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
        if log_start is not None:
            report["native_events"] = _copy_log_slice(
                log, log_start, artifact / "native-events-slice.jsonl")
            native = report["native_events"]
            if isinstance(native, dict) and native.get("status") == "ok":
                try:
                    events = _read_events(artifact / "native-events-slice.jsonl")
                    summary = _authority_event_summary(
                        events, str(report.get("session", {}).get("session_id", "")),
                        args.expected_date_raw, args.route, args.term,
                        report.get("war_id"))
                    report["native_event_summary"] = summary
                    report["native_rules_available"] = summary.get(
                        "native_rules_available")
                    report["native_predicates"] = summary.get("native_predicates")
                    report["no_authority_interception_established"] = summary.get(
                        "no_authority_interception_established") is True
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
                "native_authority_dispatch_contract": summary.get(
                    "dispatch_contract") is True,
                "native_transport_contract": (
                    summary.get("transport_contract") is True
                    if args.route == "transport" else True),
                "native_handler_entry_contract": (
                    summary.get("handler_contract") is True
                    if args.route == "handler_entry" else True),
                "native_rules_available": summary.get(
                    "native_rules_available") is True,
                "no_authority_interception_established": summary.get(
                    "no_authority_interception_established") is True,
                "authority_seed_not_created": (
                    summary.get("dispatch", {}).get("authority_seed_created") is False
                    if isinstance(summary.get("dispatch"), dict) else False
                ),
                "no_native_preflight_failure": summary.get(
                    "preflight_failure_count") == 0,
                "no_business_events": not summary.get("business_events"),
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
        "native_rules_available": report.get("native_rules_available"),
        "no_authority_interception_established": report.get(
            "no_authority_interception_established"),
    }, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
