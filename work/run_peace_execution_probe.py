#!/usr/bin/env python3
"""Run one bounded Peace execution negative probe.

The probe discovers the FRA--ENG war through the public inspection API and
publishes exactly one legal ``EU4PEACE_EXEC1`` request.  It is intentionally
limited to the new native negative path: the expected submission result is
``submitted=false`` with ``NATIVE_PEACE_COMMON_GATE_UNAVAILABLE``.  The
operator never calls the business execution API, advances time, saves, or
retries a request.  A missing result remains ``unknown``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
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

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from bridge.peace_execution import normalize_peace_execution_parameters  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import (  # noqa: E402
    _copy_log_slice,
    _sha256_file,
    _write_json,
)
from work.run_improve_relations_execution import _new_artifact  # noqa: E402
from work.run_peace_authority_test import (  # noqa: E402
    _snapshot_stability,
    _war_context_signature,
)
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
    _read_json,
    _run_snapshots,
)


_ACTOR = "FRA"
_RECIPIENT = "ENG"
_PLAYER_SLOT = 189  # POR in the controlled observer fixture
_DISCOVERY_ACTION = "white_peace"
_ACTIONS = ("white_peace", "demand_ducats", "cede_province")
_REQUEST_NAME = "diplomacy-peace-execute.req"
_WIRE_PREFIX = "EU4PEACE_EXEC1"
_EXPECTED_REASON = "NATIVE_PEACE_COMMON_GATE_UNAVAILABLE"
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_WAR_ID_RE = re.compile(r"war_[0-9a-f]{16}_[0-9a-f]{8}\Z")
_TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
_MAX_POLL_SECONDS = 15.0
_POLL_INTERVAL_SECONDS = 0.10
_EXPIRY_WINDOW_MS = 8_000
_MAX_POLL_READ_BYTES = 8 * 1024 * 1024
_POLL_READ_CHUNK_BYTES = 256 * 1024
_MAX_LOG_LINE_BYTES = 256 * 1024


class ProbeError(RuntimeError):
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


def _action_parameters(action_id: str, war_id: str) -> tuple[dict[str, object], int, list[int], str]:
    """Return one syntactically complete, stable negative-probe payload."""

    context: dict[str, object] = {
        "war_id": war_id,
        "direction": "demand",
        "terms": [],
    }
    if action_id == "white_peace":
        amount_raw = -1
        province_ids: list[int] = []
        beneficiary = "-"
    elif action_id == "demand_ducats":
        context["terms"] = [{
            "action_id": "demand_ducats",
            "amount": "10.0",
            "payer": _RECIPIENT,
            "claimant": _ACTOR,
        }]
        amount_raw = 10_000
        province_ids = []
        beneficiary = "-"
    elif action_id == "cede_province":
        context["terms"] = [{
            "action_id": "cede_province",
            "province_ids": [177],
            "beneficiary": _ACTOR,
        }]
        amount_raw = -1
        province_ids = [177]
        beneficiary = _ACTOR
    else:
        raise ProbeError("ACTION_INVALID", f"unsupported Peace action: {action_id}")
    return {"peace_context": context}, amount_raw, province_ids, beneficiary


def _normalized_wire_fields(action_id: str, war_id: str) -> tuple[dict[str, object], int, list[int], str]:
    parameters, amount_raw, province_ids, beneficiary = _action_parameters(action_id, war_id)
    try:
        normalized = normalize_peace_execution_parameters(
            action_id, _ACTOR, _RECIPIENT, "initiate", parameters)
    except (TypeError, ValueError) as error:
        raise ProbeError("PARAMETERS_INVALID", str(error)) from error
    return normalized, amount_raw, province_ids, beneficiary


def _build_wire(action_id: str, request_id: str, creation_filetime: int,
                expected_date_raw: int, war_id: str) -> tuple[str, dict[str, object]]:
    normalized, amount_raw, province_ids, beneficiary = _normalized_wire_fields(
        action_id, war_id)
    issued_at_ms = time.time_ns() // 1_000_000
    expiry_epoch_ms = issued_at_ms + _EXPIRY_WINDOW_MS
    province_field = ",".join(str(value) for value in province_ids) or "-"
    wire = " ".join((
        _WIRE_PREFIX,
        str(creation_filetime),
        request_id,
        action_id,
        _ACTOR,
        _RECIPIENT,
        str(expected_date_raw),
        str(expiry_epoch_ms),
        war_id,
        "demand",
        str(amount_raw),
        province_field,
        beneficiary,
    )) + "\n"
    try:
        wire_bytes = wire.encode("ascii")
    except UnicodeEncodeError as error:
        raise ProbeError("WIRE_NOT_ASCII", str(error)) from error
    if len(wire_bytes) > 512:
        raise ProbeError("WIRE_TOO_LARGE", str(len(wire_bytes)))
    return wire, {
        "normalized_parameters": normalized,
        "creation_filetime": creation_filetime,
        "issued_at_unix_ms": issued_at_ms,
        "expiry_epoch_ms": expiry_epoch_ms,
        "expiry_window_ms": _EXPIRY_WINDOW_MS,
        "action_id": action_id,
        "actor": _ACTOR,
        "recipient": _RECIPIENT,
        "date_raw": expected_date_raw,
        "war_id": war_id,
        "direction": "demand",
        "amount_raw": amount_raw,
        "province_ids": province_ids,
        "beneficiary": beneficiary,
        "wire_sha256": hashlib.sha256(wire_bytes).hexdigest(),
        "wire_bytes": len(wire_bytes),
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


def _poll_submission_result(log_path: Path, start_offset: int, session_id: str,
                            request_id: str, timeout_seconds: float = _MAX_POLL_SECONDS
                            ) -> dict[str, object]:
    started = _utc_now()
    deadline = started + timedelta(seconds=timeout_seconds)
    cursor = start_offset
    pending = b""
    total_read = 0
    poll_count = 0
    error: dict[str, str] | None = None
    event: dict[str, object] | None = None
    while _utc_now() < deadline:
        poll_count += 1
        try:
            cursor, pending, parsed, consumed = _read_poll_chunk(
                log_path, cursor, pending, _MAX_POLL_READ_BYTES - total_read)
        except OSError as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
            break
        total_read += consumed
        for candidate in parsed:
            if (candidate.get("event") == "native_peace_submission_result"
                    and candidate.get("session_id") == session_id
                    and candidate.get("request_id") == request_id):
                event = candidate
                break
        if event is not None:
            break
        if total_read >= _MAX_POLL_READ_BYTES:
            error = {"type": "BoundedLogPoll", "message": "POLL_LOG_BOUND_EXCEEDED"}
            break
        remaining = max(0.0, (deadline - _utc_now()).total_seconds())
        if remaining > 0:
            time.sleep(min(_POLL_INTERVAL_SECONDS, remaining))
    completed = _utc_now()
    return {
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
        "event_found": event is not None,
        "timed_out": event is None and error is None and completed >= deadline,
        "error": error,
        "event": event,
    }


def _submission_contract(event: object, fields: dict[str, object],
                         session_id: str, request_id: str) -> dict[str, object]:
    if not isinstance(event, dict):
        return {"observed": False, "valid": False, "reason": "EVENT_MISSING"}
    expected = {
        "event": "native_peace_submission_result",
        "family": "peace",
        "session_id": session_id,
        "request_id": request_id,
        "action_id": fields["action_id"],
        "actor": _ACTOR,
        "recipient": _RECIPIENT,
        "phase": "initiate",
        "date_raw": fields["date_raw"],
        "war_id": fields["war_id"],
        "direction": "demand",
        "amount_raw": fields["amount_raw"],
        "province_ids": fields["province_ids"],
        "beneficiary": fields["beneficiary"],
    }
    mismatches = {
        key: {"expected": value, "actual": event.get(key)}
        for key, value in expected.items() if event.get(key) != value
    }
    # Native emits the stable rejection field as `reason`; keep accepting a
    # reason_code only in the diagnostic record so a schema mistake is visible.
    reason = event.get("reason")
    submitted = event.get("submitted")
    contract = {
        "event_fields_match": not mismatches,
        "submitted_false": submitted is False,
        "reason_expected": reason == _EXPECTED_REASON,
        "transport_verified_false": event.get("transport_verified") is False,
        "request_binding_verified_false": event.get("request_binding_verified") is False,
        "reason": reason,
        "reason_code": event.get("reason_code"),
        "submitted": submitted,
        "transport_verified": event.get("transport_verified"),
        "request_binding_verified": event.get("request_binding_verified"),
        "mismatches": mismatches,
    }
    contract["valid"] = all((
        contract["event_fields_match"],
        contract["submitted_false"],
        contract["reason_expected"],
        contract["transport_verified_false"],
        contract["request_binding_verified_false"],
    ))
    contract["observed"] = True
    return contract


def _snapshot_stability_report(before: object, after: object) -> dict[str, bool]:
    """Retain the four semantic snapshot comparisons in the report."""

    return _snapshot_stability(before, after)


def _write_report_markdown(path: Path, report: dict[str, object]) -> None:
    checks = report.get("checks")
    lines = [
        "# Peace 执行负例探针",
        "",
        "本探针只发布一次 `EU4PEACE_EXEC1` 请求，验证原生 common gate 拒绝路径；不调用业务执行接口、不推进日期、不保存游戏。",
        "",
        f"- 状态：`{report.get('status')}`",
        f"- action：`{report.get('action_id')}`",
        f"- request_id：`{report.get('request_id')}`",
        f"- war_id：`{report.get('war_id')}`",
        f"- expected reason：`{report.get('expected_reason')}`",
        f"- native result state：`{report.get('result_state')}`",
        "",
        "## 检查结果",
        "",
    ]
    if isinstance(checks, dict):
        lines.extend(f"- `{name}`：`{value}`" for name, value in checks.items())
    lines.extend([
        "",
        "超时只表示本次没有取得绑定的 native_peace_submission_result，不代表请求成功或失败。",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _offline_contract_assertions() -> None:
    war_id = "war_0123456789abcdef_01234567"
    for action in _ACTIONS:
        wire, fields = _build_wire(action, "offline_probe_001", 123456789, 14450101, war_id)
        assert wire.startswith(_WIRE_PREFIX + " ")
        assert fields["expiry_epoch_ms"] - fields["issued_at_unix_ms"] == _EXPIRY_WINDOW_MS
        assert fields["amount_raw"] in (-1, 10_000)
    _, fields = _build_wire("white_peace", "offline_probe_002", 123, 1, war_id)
    event = {
        "event": "native_peace_submission_result",
        "family": "peace",
        "session_id": "1-2",
        "request_id": "offline_probe_002",
        "action_id": "white_peace",
        "actor": "FRA",
        "recipient": "ENG",
        "phase": "initiate",
        "date_raw": 1,
        "war_id": war_id,
        "direction": "demand",
        "amount_raw": -1,
        "province_ids": [],
        "beneficiary": "-",
        "submitted": False,
        "transport_verified": False,
        "request_binding_verified": False,
        "reason": _EXPECTED_REASON,
    }
    assert _submission_contract(event, fields, "1-2", "offline_probe_002")["valid"] is True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--action", choices=_ACTIONS, required=True)
    parser.add_argument("--request-id", required=True)
    args = parser.parse_args(argv)
    _offline_contract_assertions()

    if _REQUEST_ID_RE.fullmatch(args.request_id) is None:
        parser.error("--request-id must match [A-Za-z0-9_-]{1,64}")
    installation = args.installation.expanduser().resolve(strict=True)
    artifact = _new_artifact(installation.parent, "peace-execution-probe")
    session = ObserverSession(installation, game_exe())
    log = session.directory / "control-probe.jsonl"
    request_path = session.directory / _REQUEST_NAME
    report: dict[str, Any] = {
        "validator": Path(__file__).name,
        "version": 1,
        "status": "running",
        "mode": "native_rule_negative_probe",
        "installation": str(installation),
        "artifact": str(artifact),
        "action_id": args.action,
        "actor": _ACTOR,
        "recipient": _RECIPIENT,
        "phase": "initiate",
        "request_id": args.request_id,
        "expected_reason": _EXPECTED_REASON,
        "expected_date_raw": args.expected_date_raw,
        "request_path": str(request_path),
        "request_attempt_count": 0,
        "request_publish_count": 0,
        "request_published": False,
        "request_consumed": False,
        "execute_call_count": 0,
        "business_submission": False,
        "time_advance_call_count": 0,
        "save_call_count": 0,
        "result_state": "not_started",
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
        installation_record = _read_json(installation)
        manifest_record = _read_json(installation.parent / "build-manifest.json")
        if not isinstance(installation_record, dict):
            raise ProbeError("INSTALLATION_METADATA_INVALID", "installation metadata is not an object")
        if not isinstance(manifest_record, dict):
            raise ProbeError("BUILD_MANIFEST_INVALID", "build manifest is not an object")
        installation_creation = installation_record.get("creation_filetime")
        if (isinstance(installation_creation, bool)
                or not isinstance(installation_creation, int)
                or installation_creation < 0):
            raise ProbeError("INSTALLATION_CREATION_INVALID", "creation_filetime is missing or invalid")

        executable = game_exe().expanduser().resolve(strict=True)
        report["source"] = {
            "game_executable": str(executable),
            "bytes": executable.stat().st_size,
            "source_binding": "local_config.game_exe",
            "sha256": None,
            "sha256_note": "game executable is retained by path and size; installation/build hashes are recorded below",
        }
        report["source_hashes"] = {
            "game_executable_sha256": manifest_record.get("game_sha256"),
            "installation_json_sha256": binding.get("installation", {}).get("sha256"),
            "build_manifest_sha256": binding.get("build_manifest", {}).get("sha256"),
            "installed_dll_sha256": binding.get("build_binding", {}).get(
                "installation_dll_sha256"),
            "build_manifest_dll_sha256": binding.get("build_binding", {}).get(
                "build_manifest_dll_sha256"),
        }
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
            "creation_filetime": session.record.get("creation_filetime"),
        }
        report["preflight_identity"] = {
            "creation_matches_installation": (
                session.record.get("creation_filetime") == installation_creation),
            "session_matches_installation": (
                session.session_id == installation_record.get("session_id")),
            "dll_matches_installation_and_build": (
                session.record.get("dll_sha256") == binding.get(
                    "installation", {}).get("declared_dll_sha256")
                and binding.get("build_binding", {}).get(
                    "installation_matches_build_manifest") is True),
        }
        health_before = wait_runtime_ready(session, timeout=30.0, restore_minimized=False)
        before = _run_snapshots(session, artifact / "before" / "probes")
        report["health_before"] = health_before
        report["before"] = {
            "health": health_before,
            "probes": _public_probe_records(before),
            "control": _control_summary(before["control_state"]["snapshot"]),
        }
        identity = report["preflight_identity"]
        if (health_before.get("status") != "ready"
                or health_before.get("complete") is not True
                or not _control_is_expected(report["before"]["control"], args.expected_date_raw)
                or not _snapshots_complete(before)):
            raise ProbeError(
                "BASELINE_NOT_READY_POR_PAUSED_SNAPSHOTS",
                "before snapshots did not prove paused POR at the expected date")
        if not (isinstance(identity, dict)
                and identity.get("creation_matches_installation") is True
                and identity.get("session_matches_installation") is True
                and identity.get("dll_matches_installation_and_build") is True):
            raise ProbeError("SESSION_BUILD_PREFLIGHT_FAILED", "session/build binding failed")
        if not log.is_file():
            raise ProbeError("NATIVE_LOG_UNAVAILABLE", str(log))

        with DurableJournal(artifact / "diplomacy.sqlite3",
                            session.experiment_id, session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            before_query = api.inspect_diplomatic_action(
                _DISCOVERY_ACTION, _ACTOR, _RECIPIENT,
                phase="initiate", parameters={})
            _write_json(artifact / "war-discovery.json", before_query)
            report["before_query"] = before_query
            war_id = _single_discovered_war_id(
                before_query, _ACTOR, _RECIPIENT)
            if war_id is None or _WAR_ID_RE.fullmatch(war_id) is None:
                raise ProbeError(
                    "PEACE_WAR_DISCOVERY_INCOMPLETE",
                    "public white_peace inspection did not return one complete war id")
            report["war_id"] = war_id
            report["war_context_before"] = _war_context_signature(before_query)
            report["public_query_has_no_private_identifiers"] = not _has_private_fields(
                before_query)
            if report["public_query_has_no_private_identifiers"] is not True:
                raise ProbeError("PUBLIC_QUERY_CONTAINS_PRIVATE_IDENTIFIER",
                                 "discovery projection exposed native-only data")

            log_start = log.stat().st_size
            wire, fields = _build_wire(
                args.action, args.request_id, installation_creation,
                args.expected_date_raw, war_id)
            report["wire_fields"] = fields
            report["request_wire"] = {
                "ascii": wire,
                "bytes": fields["wire_bytes"],
                "sha256": fields["wire_sha256"],
            }
            report["request_attempt_count"] = 1
            publish_status = session._publish_atomic_request(
                wire, args.request_id, _REQUEST_NAME)
            report["request_publish_status"] = publish_status
            report["request_published"] = publish_status == "published"
            report["request_publish_count"] = 1 if report["request_published"] else 0
            if publish_status != "published":
                raise ProbeError(
                    "REQUEST_NOT_PUBLISHED",
                    f"native request channel returned {publish_status}")

            poll = _poll_submission_result(
                log, log_start, session.session_id, args.request_id)
            report["poll"] = poll
            event = poll.get("event")
            if event is None:
                report["result_state"] = "timeout" if poll.get("timed_out") else "unknown"
            else:
                report["result_state"] = "observed"
                report["native_submission_event"] = event
                report["submission_contract"] = _submission_contract(
                    event, fields, session.session_id, args.request_id)
            report["request_consumed"] = not request_path.exists()

            after_query = api.inspect_diplomatic_action(
                _DISCOVERY_ACTION, _ACTOR, _RECIPIENT,
                phase="initiate", parameters={})
            _write_json(artifact / "war-discovery-after.json", after_query)
            report["after_query"] = after_query
            report["war_context_after"] = _war_context_signature(after_query)

        after = _run_snapshots(session, artifact / "after" / "probes")
        health_after = session.health()
        report["health_after"] = health_after
        report["after"] = {
            "health": health_after,
            "probes": _public_probe_records(after),
            "control": _control_summary(after["control_state"]["snapshot"]),
        }
        stability = _snapshot_stability_report(before, after)
        report["snapshot_stability"] = stability
        submission = report.get("submission_contract")
        report["checks"] = {
            "preflight_health_ready": health_before.get("status") == "ready"
            and health_before.get("complete") is True,
            "session_creation_matches_installation": identity.get(
                "creation_matches_installation") is True,
            "session_matches_installation": identity.get(
                "session_matches_installation") is True,
            "dll_matches_installation_and_build": identity.get(
                "dll_matches_installation_and_build") is True,
            "before_four_snapshots_complete": _snapshots_complete(before),
            "before_por_paused_expected_date": _control_is_expected(
                report["before"]["control"], args.expected_date_raw),
            "public_war_discovery_contract": _public_context_contract(
                before_query, _ACTOR, _RECIPIENT),
            "public_war_discovery_one_war": (
                _single_discovered_war_id(before_query, _ACTOR, _RECIPIENT) == war_id),
            "public_query_has_no_private_identifiers": (
                report.get("public_query_has_no_private_identifiers") is True),
            "request_published_once": report["request_publish_count"] == 1,
            "request_wire_prefix": report.get("request_wire", {}).get(
                "ascii", "").startswith(_WIRE_PREFIX + " "),
            "request_wire_creation_matches_installation": fields.get(
                "creation_filetime") == installation_creation,
            "request_wire_expiry_exactly_eight_seconds": fields.get(
                "expiry_window_ms") == _EXPIRY_WINDOW_MS,
            "native_submission_result_observed": report["result_state"] == "observed",
            "native_submission_negative_contract": (
                isinstance(submission, dict) and submission.get("valid") is True),
            "request_consumed": report["request_consumed"],
            "after_four_snapshots_complete": _snapshots_complete(after),
            "por_paused_same_date": (
                _control_is_expected(report["after"]["control"], args.expected_date_raw)
                and report["before"]["control"] == report["after"]["control"]),
            "four_snapshot_business_state_unchanged": all(stability.values()),
            "same_public_war_context": (
                report.get("war_context_before") is not None
                and report.get("war_context_before") == report.get("war_context_after")
                and report.get("war_id") == _single_discovered_war_id(
                    after_query, _ACTOR, _RECIPIENT)),
            "after_public_query_has_no_private_identifiers": not _has_private_fields(
                after_query),
            "no_business_execute_or_world_mutation_request": (
                report["execute_call_count"] == 0
                and report["business_submission"] is False
                and report["time_advance_call_count"] == 0
                and report["save_call_count"] == 0),
        }
    except ProbeError as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:  # keep a reviewable artifact for unexpected errors
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
        else:
            report["native_events"] = {
                "status": "not_started",
                "path": str(artifact / "native-events-slice.jsonl"),
                "bytes": 0,
            }
        if report.get("status") == "running":
            if report.get("result_state") in ("timeout", "unknown"):
                report["status"] = "unknown"
            else:
                report["status"] = (
                    "passed" if all(report.get("checks", {}).values()) else "failed")
        _write_json(artifact / "report.json", report)
        _write_report_markdown(artifact / "report.md", report)

    print(json.dumps({
        "status": report["status"],
        "artifact": str(artifact),
        "native_slice": str(artifact / "native-events-slice.jsonl"),
        "request_published": report.get("request_published"),
        "request_consumed": report.get("request_consumed"),
        "result_state": report.get("result_state"),
    }, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 3 if report["status"] == "unknown" else 2


if __name__ == "__main__":
    raise SystemExit(main())
