"""Advance an installed diplomacy observer through a long date range.

The operator is deliberately narrower than a game automation framework.  It
uses the already installed native 35/5/1-day controller, publishes at most one
fixed control request for each segment, and waits for the matching
``control_advance_complete`` event before it considers the next segment.  A
published request whose result is not yet known is retained as an ambiguous
pending operation; it is never replayed automatically.

Normal use::

    python -B work/advance_diplomacy_context.py \
        --installation work/runtime/.../installation.json \
        --expected-date-raw 56462016 --target-date-raw 56462856

If a process is interrupted after a request was published, use ``--resume``
with the original artifact.  Resume only observes the existing log from the
recorded offset and never creates another ``game-control.request`` file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import ObserverSession  # noqa: E402
from work.local_config import get_value  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.validate_alliance_queries import PROBE_SPECS, _run_probe  # noqa: E402


RAW_PER_DAY = 24
SEGMENT_DAYS = (35, 5, 1)
PLAYER_SLOT = 189  # POR in the controlled experiment.
SEGMENT_DEADLINE_SECONDS = 140.0
POLL_SECONDS = 1.0
HEALTH_INTERVAL_SECONDS = 5.0
NO_HEARTBEAT_SECONDS = 30.0
PROGRESS_INTERVAL_SECONDS = 20.0
MAX_EVENT_LINE_BYTES = 64 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_EVENT_SLICE_BYTES = 8 * 1024 * 1024
TERMINAL_SEGMENT_STATUSES = frozenset(("observed", "target_not_reached"))


class ContextStop(RuntimeError):
    """A bounded, reportable operator stop."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_json(path: Path, value: object) -> None:
    """Atomically write one small operator metadata file.

    The temporary name is unique.  The destination belongs to this operator's
    fresh artifact, so replacing it cannot overwrite an older experiment.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2,
                      sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json_bounded(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_REPORT_BYTES:
            raise ContextStop("REPORT_TOO_LARGE", str(path))
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except ContextStop:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContextStop("REPORT_READ_FAILED", f"{path}: {error}") from error
    if not isinstance(value, dict):
        raise ContextStop("REPORT_NOT_OBJECT", str(path))
    return value


def _new_artifact(parent: Path, prefix: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    for _ in range(64):
        candidate = parent / f"{prefix}-{uuid.uuid4().hex}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise ContextStop("ARTIFACT_DIRECTORY_COLLISION", str(parent))


def _int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _plan_segments(expected_date_raw: int, target_date_raw: int) -> list[dict[str, Any]]:
    """Split an exact raw-date interval into native 35/5/1-day requests."""

    if not isinstance(expected_date_raw, int) or isinstance(expected_date_raw, bool):
        raise ContextStop("DATE_NOT_INTEGER", "expected-date-raw must be an integer")
    if not isinstance(target_date_raw, int) or isinstance(target_date_raw, bool):
        raise ContextStop("DATE_NOT_INTEGER", "target-date-raw must be an integer")
    delta = target_date_raw - expected_date_raw
    if delta < 0:
        raise ContextStop("TARGET_BEFORE_EXPECTED", "target-date-raw precedes expected-date-raw")
    if delta % RAW_PER_DAY != 0:
        raise ContextStop("DATE_INTERVAL_NOT_DAY_ALIGNED",
                          "target-date-raw - expected-date-raw must be divisible by 24")
    remaining = delta // RAW_PER_DAY
    if remaining > 36500:
        raise ContextStop("DATE_INTERVAL_TOO_LARGE", "refusing an interval longer than 100 years")
    segments: list[dict[str, Any]] = []
    start = expected_date_raw
    index = 1
    for days in SEGMENT_DAYS:
        while remaining >= days:
            target = start + days * RAW_PER_DAY
            segments.append({
                "index": index,
                "days": days,
                "start_date_raw": start,
                "target_date_raw": target,
                "request": f"TEST_ONLY advance_{days}_days\n",
                "request_token": uuid.uuid4().hex,
                "status": "planned",
                "request_intent_recorded": False,
                "request_published": False,
                "completion_observed": False,
                "published_request": False,
                "log_start_offset": None,
                "log_end_offset": None,
                "events_path": None,
                "state_path": None,
            })
            start = target
            remaining -= days
            index += 1
    if start != target_date_raw or remaining != 0:
        raise ContextStop("SEGMENT_PLANNING_FAILED", "native day segment planning did not reach target")
    return segments


def _sha256_bounded(path: Path, maximum: int = MAX_EVENT_SLICE_BYTES) -> dict[str, Any]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                return {"path": str(path), "bytes": total, "sha256": None,
                        "truncated": True}
            digest.update(chunk)
    return {"path": str(path), "bytes": total, "sha256": digest.hexdigest(),
            "truncated": False}


def _context_snapshots(session: ObserverSession, destination: Path) -> dict[str, Any]:
    """Capture the four reviewed context probes once at a boundary."""

    destination.mkdir(parents=True, exist_ok=True)
    probes: dict[str, Any] = {}
    control: dict[str, Any] | None = None
    for spec in PROBE_SPECS:
        path = destination / f"{spec.name}.json"
        try:
            raw = _run_probe(spec, session.record["pid"], path)
            snapshot = raw.get("snapshot") if isinstance(raw, dict) else None
            if spec.name == "control_state" and isinstance(snapshot, dict):
                control = {
                    "date_raw": snapshot.get("date_raw"),
                    "paused_flag": snapshot.get("paused_flag"),
                    "player_slot": snapshot.get("player_slot"),
                }
            probes[spec.name] = {
                "status": raw.get("status"),
                "name": raw.get("name"),
                "snapshot_path": str(path),
                "snapshot_completeness": raw.get("snapshot_completeness"),
                "snapshot_sha256": _sha256_bounded(path, MAX_REPORT_BYTES),
            }
        except Exception as error:  # retain boundary evidence even on one failed probe
            probes[spec.name] = {
                "status": "unknown",
                "snapshot_path": str(path),
                "error_type": type(error).__name__,
                "error": str(error),
            }
    complete = all(
        isinstance(item, dict)
        and item.get("status") == "ok"
        and isinstance(item.get("snapshot_completeness"), dict)
        and item["snapshot_completeness"].get("complete") is True
        for item in probes.values()
    ) and len(probes) == len(PROBE_SPECS)
    return {"probes": probes, "control": control, "complete": complete,
            "captured_at": _utc_now()}


def _baseline_ok(boundary: dict[str, Any], expected_date_raw: int) -> bool:
    control = boundary.get("control") if isinstance(boundary, dict) else None
    return bool(
        boundary.get("complete") is True
        and isinstance(control, dict)
        and control.get("date_raw") == expected_date_raw
        and control.get("paused_flag") == 1
        and control.get("player_slot") == PLAYER_SLOT
    )


def _end_context_ok(boundary: dict[str, Any], target_date_raw: int) -> bool:
    control = boundary.get("control") if isinstance(boundary, dict) else None
    return bool(
        boundary.get("complete") is True
        and isinstance(control, dict)
        and control.get("date_raw") == target_date_raw
        and control.get("paused_flag") == 1
        and control.get("player_slot") == PLAYER_SLOT
    )


def _set_segment_state(seg: dict[str, Any], state_path: Path) -> None:
    """Persist the replay-prevention state independently of report.json."""

    state = {
        "updated_at": _utc_now(),
        "index": seg.get("index"),
        "start_date_raw": seg.get("start_date_raw"),
        "target_date_raw": seg.get("target_date_raw"),
        "days": seg.get("days"),
        "request_token": seg.get("request_token"),
        "request": seg.get("request"),
        "log_start_offset": seg.get("log_start_offset"),
        "request_intent_recorded": seg.get("request_intent_recorded") is True,
        "request_published": seg.get("request_published") is True,
        "published_request": seg.get("published_request") is True,
        "publication_state": seg.get("publication_state"),
        "status": seg.get("status"),
        "completion_observed": seg.get("completion_observed") is True,
        "completion": seg.get("completion"),
        "completion_kind": seg.get("completion_kind"),
        "terminal": seg.get("terminal") is True,
        "terminal_reason": seg.get("terminal_reason"),
        "terminal_date_raw": seg.get("terminal_date_raw"),
        "terminal_paused": seg.get("terminal_paused"),
        "terminal_ready": seg.get("terminal_ready"),
        "log_end_offset": seg.get("log_end_offset"),
        "error": seg.get("error"),
    }
    _write_json(state_path, state)


def _persist_report(report_path: Path, report: dict[str, Any]) -> None:
    report["updated_at"] = _utc_now()
    _write_json(report_path, report)


def _publish_control_request(session: ObserverSession, seg: dict[str, Any],
                             report: dict[str, Any], report_path: Path,
                             state_path: Path) -> None:
    """Record intent before the atomic hardlink publication.

    If the process stops between intent and hardlink, resume treats the
    segment as ambiguous and only observes its log offset.  This conservative
    ordering is what prevents an accidental duplicate advance.
    """

    request = session.directory / "game-control.request"
    pending = session.directory / f"control-pending-{uuid.uuid4().hex}"
    if request.exists():
        raise ContextStop("REQUEST_ALREADY_PRESENT", str(request))
    seg["request_intent_recorded"] = True
    seg["publication_state"] = "intent_recorded"
    _set_segment_state(seg, state_path)
    _persist_report(report_path, report)
    try:
        with pending.open("xb") as stream:
            stream.write(str(seg["request"]).encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
        health = session.health()
        if (health.get("status") != "ready"
                or health.get("date_raw") != seg.get("start_date_raw")):
            raise ContextStop("SESSION_NOT_READY_BEFORE_PUBLICATION",
                              json.dumps(health, ensure_ascii=False, sort_keys=True))
        try:
            os.link(pending, request)
        except FileExistsError as error:
            raise ContextStop("REQUEST_ALREADY_PRESENT", str(request)) from error
        seg["request_published"] = True
        seg["published_request"] = True
        seg["publication_state"] = "published"
        report["published_request_count"] = int(report.get("published_request_count", 0)) + 1
        _set_segment_state(seg, state_path)
        _persist_report(report_path, report)
    finally:
        pending.unlink(missing_ok=True)


def _completion_exact(event: object, target_date_raw: int) -> bool:
    return _completion_kind(event, target_date_raw) == "reached"


def _completion_kind(event: object, target_date_raw: int) -> str | None:
    """Classify one native terminal control event without inferring execution.

    ``reached=false`` with the same target and a successful pause is an
    explicit native termination at the controller deadline.  It is terminal
    evidence for the submitted request, but it is not a successful date
    advance and must never trigger a replay.
    """

    if not isinstance(event, dict):
        return None
    if event.get("target_raw") != target_date_raw:
        return None
    if event.get("paused_command_success") is not True:
        return None
    date_raw = _int(event.get("date_raw"))
    if event.get("reached") is True and date_raw == target_date_raw:
        return "reached"
    if event.get("reached") is False and date_raw is not None:
        return "target_not_reached"
    return None


def _event_is_popup(event: object) -> bool:
    return isinstance(event, dict) and (
        event.get("event") in {"popup_confirmation_begin", "popup_detected", "pause_popup_detected"}
        or (isinstance(event.get("event"), str)
            and "popup" in event["event"].lower()
            and event["event"] != "popup_confirmation_callbacks_returned")
    )


def _poll_segment(session: ObserverSession, seg: dict[str, Any],
                  evidence_dir: Path, state_path: Path,
                  report: dict[str, Any], report_path: Path,
                  *, publish: bool,
                  timeout_seconds: float = SEGMENT_DEADLINE_SECONDS,
                  on_progress: Callable[[dict[str, Any]], None] | None = None
                  ) -> dict[str, Any]:
    """Publish (normal mode) or observe (resume mode) one segment."""

    log = session.directory / "control-probe.jsonl"
    if not log.is_file():
        raise ContextStop("CONTROL_LOG_NOT_FOUND", str(log))
    offset = _int(seg.get("log_start_offset"))
    if offset is None:
        offset = log.stat().st_size
        seg["log_start_offset"] = offset
    if log.stat().st_size < offset:
        raise ContextStop("CONTROL_LOG_OFFSET_MOVED_BACKWARD", str(log))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    events_path = evidence_dir / "native-events-slice.jsonl"
    seg["events_path"] = str(events_path)
    seg["state_path"] = str(state_path)
    if publish:
        _publish_control_request(session, seg, report, report_path, state_path)
    seg["status"] = "observing"
    _set_segment_state(seg, state_path)
    _persist_report(report_path, report)
    print(json.dumps({"segment": seg.get("index"), "days": seg.get("days"),
                      "state": "published" if publish else "resuming",
                      "target_date_raw": seg.get("target_date_raw"),
                      "output": str(evidence_dir)}, ensure_ascii=False), flush=True)

    completion: dict[str, Any] | None = None
    last_health: dict[str, Any] | None = None
    last_heartbeat: dict[str, Any] | None = None
    last_date_raw: int | None = None
    last_date_change = time.monotonic()
    last_heartbeat_clock = time.monotonic()
    last_health_clock = 0.0
    last_progress_clock = time.monotonic()
    line_count = 0
    malformed_lines = 0
    popup_event: dict[str, Any] | None = None
    stop_reason: str | None = None
    deadline = time.monotonic() + max(1.0, min(float(timeout_seconds), SEGMENT_DEADLINE_SECONDS))
    source: Any = None
    try:
        with log.open("rb") as source, events_path.open("ab") as evidence:
            source.seek(offset)
            while time.monotonic() < deadline:
                while True:
                    position = source.tell()
                    raw = source.readline(MAX_EVENT_LINE_BYTES + 1)
                    if not raw:
                        break
                    if len(raw) > MAX_EVENT_LINE_BYTES:
                        raise ContextStop("NATIVE_EVENT_EXCEEDS_BOUNDED_LINE", str(log))
                    if not raw.endswith(b"\n"):
                        source.seek(position)
                        break
                    evidence.write(raw)
                    line_count += 1
                    try:
                        event = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        malformed_lines += 1
                        continue
                    name = event.get("event") if isinstance(event, dict) else None
                    if name == "diplomacy_observer_health" and event.get("session_id") == session.session_id:
                        last_heartbeat = event
                        last_heartbeat_clock = time.monotonic()
                        observed_date = _int(event.get("date_raw"))
                        if observed_date is not None:
                            if last_date_raw != observed_date:
                                last_date_raw = observed_date
                                last_date_change = time.monotonic()
                    if _event_is_popup(event):
                        popup_event = event if isinstance(event, dict) else {"event": name}
                        stop_reason = "POPUP_DETECTED"
                    if name == "control_advance_complete" and isinstance(event, dict):
                        completion = event
                        # This is the unambiguous terminal signal for this
                        # segment; do not consume later unrelated events.
                        break
                evidence.flush()
                seg["log_end_offset"] = source.tell()
                seg["line_count"] = line_count
                seg["malformed_lines"] = malformed_lines
                if completion is not None or stop_reason == "POPUP_DETECTED":
                    break
                now = time.monotonic()
                if now >= last_health_clock + HEALTH_INTERVAL_SECONDS:
                    last_health_clock = now
                    last_health = session.health()
                    seg["last_health"] = last_health
                    if last_health.get("status") == "ready":
                        last_heartbeat_clock = now
                        health_date = _int(last_health.get("date_raw"))
                        if health_date is not None:
                            if last_date_raw != health_date:
                                last_date_raw = health_date
                                last_date_change = now
                            seg["last_heartbeat_date_raw"] = health_date
                    else:
                        reasons = last_health.get("reasons")
                        seg["health_unready_reasons"] = reasons
                if now - last_heartbeat_clock > NO_HEARTBEAT_SECONDS:
                    stop_reason = "SESSION_HEARTBEAT_OR_DATE_STALLED"
                    break
                if last_date_raw is not None and now - last_date_change > NO_HEARTBEAT_SECONDS:
                    stop_reason = "SESSION_DATE_STALLED"
                    break
                if now - last_progress_clock >= PROGRESS_INTERVAL_SECONDS:
                    last_progress_clock = now
                    print(json.dumps({
                        "segment": seg.get("index"), "state": "waiting",
                        "target_date_raw": seg.get("target_date_raw"),
                        "last_heartbeat_date_raw": last_date_raw,
                        "elapsed_seconds": round(now - (deadline - max(1.0, min(float(timeout_seconds), SEGMENT_DEADLINE_SECONDS))), 1),
                    }, ensure_ascii=False), flush=True)
                _set_segment_state(seg, state_path)
                _persist_report(report_path, report)
                if on_progress is not None:
                    on_progress(seg)
                time.sleep(min(POLL_SECONDS, max(0.0, deadline - time.monotonic())))
    except KeyboardInterrupt:
        stop_reason = "INTERRUPTED_WITH_REQUEST_STATE_PRESERVED"
        raise
    finally:
        if source is not None:
            try:
                seg["log_end_offset"] = source.tell()
            except (OSError, ValueError):
                pass
        seg["line_count"] = line_count
        seg["malformed_lines"] = malformed_lines
        if last_heartbeat is not None:
            seg["last_heartbeat"] = last_heartbeat
        if popup_event is not None:
            seg["popup_event"] = popup_event
        if completion is not None:
            seg["completion"] = completion
            seg["completion_observed"] = True
            completion_kind = _completion_kind(completion, int(seg["target_date_raw"]))
            seg["completion_kind"] = completion_kind
            if completion_kind == "reached":
                seg["status"] = "completion_observed"
            elif completion_kind == "target_not_reached":
                seg["status"] = "target_not_reached"
                seg["terminal"] = True
                seg["terminal_reason"] = "TARGET_DATE_NOT_REACHED"
                seg["terminal_date_raw"] = _int(completion.get("date_raw"))
                seg["terminal_paused"] = completion.get("paused_command_success") is True
            else:
                seg["status"] = "completion_unreached_or_wrong_target"
        elif stop_reason is not None:
            seg["status"] = "request_pending_confirmation" if seg.get("request_intent_recorded") else "stopped"
            seg["stop_reason"] = stop_reason
        else:
            seg["status"] = "request_pending_confirmation"
            seg["stop_reason"] = "SEGMENT_DEADLINE_EXPIRED"
        if last_health is not None:
            seg["last_health"] = last_health
        _set_segment_state(seg, state_path)
        _persist_report(report_path, report)

    seg["events_sha256"] = _sha256_bounded(events_path)
    completion_kind = (_completion_kind(completion, int(seg["target_date_raw"]))
                       if completion is not None else None)
    if completion is not None and completion_kind in ("reached", "target_not_reached"):
        # The periodic health record can lag the immediate completion event
        # by one day. Wait for its date without replaying the control request.
        completion_date = (int(seg["target_date_raw"]) if completion_kind == "reached"
                           else int(seg["terminal_date_raw"]))
        seg["health_after_completion"] = _completion_health(session, completion_date)
        health_after = seg["health_after_completion"]
        seg["completion_ready"] = (
            isinstance(health_after, dict)
            and health_after.get("status") == "ready"
            and health_after.get("date_raw") == (
                seg.get("target_date_raw") if completion_kind == "reached"
                else seg.get("terminal_date_raw")
            )
        )
        if completion_kind == "target_not_reached":
            seg["terminal_ready"] = seg["completion_ready"]
            seg["status"] = "target_not_reached"
        elif seg["completion_ready"]:
            seg["status"] = "observed"
        else:
            seg["status"] = "completion_observed_session_not_ready"
    _set_segment_state(seg, state_path)
    _persist_report(report_path, report)
    print(json.dumps({"segment": seg.get("index"), "state": seg.get("status"),
                      "target_date_raw": seg.get("target_date_raw"),
                      "log_end_offset": seg.get("log_end_offset"),
                      "request_republished": False if not publish else None},
                     ensure_ascii=False), flush=True)
    return seg


def _completion_health(session: ObserverSession, expected_date: int,
                       timeout: float = 3.0) -> dict[str, Any]:
    """Wait for the paused completion date to reach the health heartbeat.

    The controller logs completion immediately; the periodic heartbeat can
    still describe the previous day. These reads never publish a request.
    """
    deadline = time.monotonic() + timeout
    health = wait_runtime_ready(session, timeout=timeout)
    while (health.get("status") != "ready" or health.get("date_raw") != expected_date):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(POLL_SECONDS, remaining))
        health = session.health()
    return health


def _report_skeleton(installation: Path, session: ObserverSession,
                     expected: int, target: int, artifact: Path) -> dict[str, Any]:
    ack = session._installation_ack() or {}
    return {
        "operator": "advance_diplomacy_context",
        "operator_version": 1,
        "mode": "execute",
        "artifact": str(artifact),
        "installation": str(installation),
        "session_id": session.session_id,
        "pid": session.record.get("pid"),
        "dll_sha256": session.record.get("dll_sha256"),
        "experiment_id": session.experiment_id,
        "expected_date_raw": expected,
        "target_date_raw": target,
        "player_slot": PLAYER_SLOT,
        "segment_days": list(SEGMENT_DAYS),
        "control_request_name": "game-control.request",
        "control_log": str(session.directory / "control-probe.jsonl"),
        "authority_enabled": ack.get("authority_lock_enabled") is True,
        "status": "initializing",
        "published_request_count": 0,
        "resume_republished_request": False,
        "segments": [],
        "started_at": _utc_now(),
    }


def _capture_after(session: ObserverSession, report: dict[str, Any],
                   artifact: Path, target: int, report_path: Path) -> None:
    if report.get("after") is not None:
        return
    try:
        after = _context_snapshots(session, artifact / "after")
        report["after"] = after
        report["after_context_ok"] = _end_context_ok(after, target)
    except Exception as error:
        report["after"] = {"complete": False, "error_type": type(error).__name__,
                            "error": str(error)}
        report["after_context_ok"] = False
    _persist_report(report_path, report)


def _record_terminal_summary(report: dict[str, Any], seg: dict[str, Any]) -> None:
    """Promote the native terminal date/pause facts for human callers."""

    if seg.get("status") != "target_not_reached":
        return
    report["terminal_segment_index"] = seg.get("index")
    report["terminal_target_date_raw"] = seg.get("target_date_raw")
    report["terminal_date_raw"] = seg.get("terminal_date_raw")
    report["terminal_paused_command_success"] = seg.get("terminal_paused") is True
    report["terminal_completion"] = seg.get("completion")


def _run_normal(args: argparse.Namespace) -> int:
    installation = args.installation.expanduser().resolve(strict=True)
    if args.expected_date_raw is None or args.target_date_raw is None:
        raise ContextStop("DATES_REQUIRED", "normal mode requires expected and target raw dates")
    expected = args.expected_date_raw
    target = args.target_date_raw
    segments = _plan_segments(expected, target)
    session = ObserverSession(installation, Path(get_value("EU4_GAME_ROOT")) / "eu4.exe")
    artifact = _new_artifact(installation.parent, "advance-context")
    report_path = artifact / "report.json"
    report = _report_skeleton(installation, session, expected, target, artifact)
    report["segments"] = segments
    for seg in segments:
        segdir = artifact / "segments" / f"segment-{int(seg['index']):03d}"
        seg["state_path"] = str(segdir / "state.json")
        seg["events_path"] = str(segdir / "native-events-slice.jsonl")
    _persist_report(report_path, report)
    started_request = False
    try:
        health = wait_runtime_ready(session, restore_minimized=True)
        report["health_before"] = health
        if health.get("status") != "ready" or health.get("date_raw") != expected:
            raise ContextStop("OBSERVER_NOT_READY_AT_EXPECTED_DATE", json.dumps(health, ensure_ascii=False))
        before = _context_snapshots(session, artifact / "before")
        report["before"] = before
        _persist_report(report_path, report)
        if not _baseline_ok(before, expected):
            raise ContextStop("BASELINE_NOT_COMPLETE_PAUSED_POR", json.dumps(before, ensure_ascii=False))
        if not segments:
            report["status"] = "completed"
            _capture_after(session, report, artifact, target, report_path)
        else:
            for seg in segments:
                segdir = artifact / "segments" / f"segment-{int(seg['index']):03d}"
                segdir.mkdir(parents=True, exist_ok=True)
                try:
                    _poll_segment(session, seg, segdir, segdir / "state.json",
                                  report, report_path, publish=True,
                                  timeout_seconds=args.segment_timeout_seconds)
                    started_request = started_request or seg.get("request_published") is True
                    _record_terminal_summary(report, seg)
                except KeyboardInterrupt:
                    report["status"] = "interrupted_request_state_preserved"
                    report["error_code"] = "INTERRUPTED_WITH_REQUEST_STATE_PRESERVED"
                    raise
                if seg.get("status") not in TERMINAL_SEGMENT_STATUSES:
                    report["status"] = "request_pending_confirmation" if seg.get("request_intent_recorded") else "stopped"
                    report["error_code"] = seg.get("stop_reason") or seg.get("status")
                    break
                if seg.get("status") == "target_not_reached":
                    report["status"] = "target_not_reached"
                    report["error_code"] = "TARGET_DATE_NOT_REACHED"
                    break
            else:
                report["status"] = "completed"
    except KeyboardInterrupt:
        report["status"] = "interrupted_request_state_preserved"
        report["error_code"] = "INTERRUPTED_WITH_REQUEST_STATE_PRESERVED"
    except ContextStop as error:
        request_started = started_request or any(
            isinstance(item, dict) and (
                item.get("request_intent_recorded") is True
                or item.get("request_published") is True
            ) for item in report.get("segments", [])
        )
        report["status"] = "request_pending_confirmation" if request_started else "stopped"
        report["error_code"] = error.code
        report["error"] = error.message
    except Exception as error:
        request_started = started_request or any(
            isinstance(item, dict) and (
                item.get("request_intent_recorded") is True
                or item.get("request_published") is True
            ) for item in report.get("segments", [])
        )
        report["status"] = "request_pending_confirmation" if request_started else "stopped"
        report["error_code"] = type(error).__name__
        report["error"] = str(error)
    finally:
        # A boundary snapshot is captured once on every run that passed the
        # baseline, including an interrupted/ambiguous request.  It is never
        # used to infer that an unobserved request did not execute.
        if report.get("before") is not None:
            _capture_after(session, report, artifact, target, report_path)
        report["finished_at"] = _utc_now()
        report["events_sha256"] = {
            str(seg.get("index")): _sha256_bounded(Path(seg["events_path"]))
            for seg in report.get("segments", [])
            if isinstance(seg, dict) and isinstance(seg.get("events_path"), str)
            and Path(seg["events_path"]).is_file()
        }
        _persist_report(report_path, report)
    print(json.dumps({"status": report.get("status"), "artifact": str(artifact),
                      "published_request_count": report.get("published_request_count", 0)},
                     ensure_ascii=False), flush=True)
    return 0 if report.get("status") == "completed" and report.get("after_context_ok") is True else 2


def _resume_source(path: Path) -> tuple[Path, dict[str, Any]]:
    source = path.expanduser().resolve(strict=True)
    report_path = source / "report.json" if source.is_dir() else source
    if report_path.name != "report.json":
        raise ContextStop("RESUME_REPORT_REQUIRED", str(report_path))
    report = _read_json_bounded(report_path)
    return report_path.parent, report


def _merge_state(seg: dict[str, Any], artifact: Path) -> dict[str, Any]:
    merged = dict(seg)
    state_text = seg.get("state_path")
    if isinstance(state_text, str):
        state_path = Path(state_text)
    else:
        state_path = artifact / "segments" / f"segment-{int(seg.get('index', 0)):03d}" / "state.json"
    if state_path.is_file():
        try:
            state = _read_json_bounded(state_path)
        except ContextStop:
            state = {}
        for key in ("request_intent_recorded", "request_published", "published_request",
                    "publication_state", "status", "completion_observed", "completion",
                    "completion_kind", "terminal", "terminal_reason",
                    "terminal_date_raw", "terminal_paused", "terminal_ready",
                    "log_start_offset", "log_end_offset", "error"):
            if key in state:
                merged[key] = state[key]
        merged["state_path"] = str(state_path)
    return merged


def _run_resume(args: argparse.Namespace) -> int:
    source_artifact, original = _resume_source(args.resume)
    installation = args.installation.expanduser().resolve(strict=True)
    expected = args.expected_date_raw if args.expected_date_raw is not None else _int(original.get("expected_date_raw"))
    target = args.target_date_raw if args.target_date_raw is not None else _int(original.get("target_date_raw"))
    if expected is None or target is None:
        raise ContextStop("RESUME_DATES_MISSING", "resume report lacks expected/target raw dates")
    if original.get("installation") and Path(str(original["installation"])).resolve() != installation:
        raise ContextStop("RESUME_INSTALLATION_MISMATCH", str(installation))
    session = ObserverSession(installation, Path(get_value("EU4_GAME_ROOT")) / "eu4.exe")
    artifact = _new_artifact(source_artifact.parent, "advance-context-resume")
    report_path = artifact / "report.json"
    report: dict[str, Any] = {
        "operator": "advance_diplomacy_context",
        "operator_version": 1,
        "mode": "resume_read_only",
        "artifact": str(artifact),
        "resume_artifact": str(source_artifact),
        "resume_report": str(source_artifact / "report.json"),
        "installation": str(installation),
        "session_id": session.session_id,
        "expected_date_raw": expected,
        "target_date_raw": target,
        "request_republished": False,
        "published_request_count": 0,
        "status": "initializing",
        "started_at": _utc_now(),
    }
    _persist_report(report_path, report)
    try:
        if original.get("session_id") != session.session_id:
            raise ContextStop("RESUME_SESSION_MISMATCH", session.session_id)
        segments = original.get("segments")
        if not isinstance(segments, list):
            raise ContextStop("RESUME_SEGMENTS_MISSING", str(source_artifact))
        merged_segments = [_merge_state(item, source_artifact)
                           for item in segments if isinstance(item, dict)]
        pending: dict[str, Any] | None = None
        for item in merged_segments:
            if (item.get("status") in TERMINAL_SEGMENT_STATUSES
                    and item.get("completion_observed") is True):
                continue
            if item.get("request_intent_recorded") is True or item.get("request_published") is True:
                pending = item
                break
            if item.get("status") not in {"planned", "observed", "completed"}:
                pending = item
                break
        if pending is None:
            if any(item.get("status") == "target_not_reached"
                   for item in merged_segments):
                report["status"] = "target_not_reached_terminal"
            elif all(item.get("status") == "observed" for item in merged_segments):
                report["status"] = "already_complete"
            else:
                report["status"] = "no_submitted_segment_to_resume"
            report["source_segments"] = merged_segments
        else:
            offset = _int(pending.get("log_start_offset"))
            if offset is None:
                raise ContextStop("RESUME_LOG_OFFSET_MISSING", str(pending.get("index")))
            pending["state_path"] = str(artifact / "segment" / "state.json")
            segdir = artifact / "segment"
            segdir.mkdir(parents=True, exist_ok=True)
            # The resume copy has no publication fields of its own.  Its
            # source segment remains the authoritative request state.
            pending["request_published"] = bool(pending.get("request_published") is True)
            pending["request_intent_recorded"] = bool(pending.get("request_intent_recorded") is True)
            report["source_segment"] = pending
            report["source_segments"] = merged_segments
            _persist_report(report_path, report)
            _poll_segment(session, pending, segdir, segdir / "state.json",
                          report, report_path, publish=False,
                          timeout_seconds=args.segment_timeout_seconds)
            report["source_segment_after"] = pending
            _record_terminal_summary(report, pending)
            if pending.get("status") == "observed":
                report["status"] = "confirmed_segment"
            elif pending.get("status") == "target_not_reached":
                report["status"] = "target_not_reached_terminal"
            else:
                report["status"] = "request_pending_confirmation"
            report["request_republished"] = False
    except KeyboardInterrupt:
        report["status"] = "interrupted_read_only"
        report["error_code"] = "INTERRUPTED_READ_ONLY"
    except ContextStop as error:
        report["status"] = "resume_unverified"
        report["error_code"] = error.code
        report["error"] = error.message
    except Exception as error:
        report["status"] = "resume_unverified"
        report["error_code"] = type(error).__name__
        report["error"] = str(error)
    finally:
        report["finished_at"] = _utc_now()
        _persist_report(report_path, report)
    print(json.dumps({"status": report.get("status"), "artifact": str(artifact),
                      "request_republished": False}, ensure_ascii=False), flush=True)
    return 0 if report.get("status") in {"confirmed_segment", "already_complete"} else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True,
                        help="existing observer installation.json")
    parser.add_argument("--expected-date-raw", type=int,
                        help="raw date at the paused baseline; required in normal mode")
    parser.add_argument("--target-date-raw", type=int,
                        help="exact raw date to reach; required in normal mode")
    parser.add_argument("--resume", type=Path,
                        help="existing advance-context artifact or report.json; read-only")
    parser.add_argument("--segment-timeout-seconds", type=float,
                        default=SEGMENT_DEADLINE_SECONDS,
                        help="bounded wait per segment, default 140 seconds")
    args = parser.parse_args()
    if args.segment_timeout_seconds <= 0 or args.segment_timeout_seconds > SEGMENT_DEADLINE_SECONDS:
        parser.error("--segment-timeout-seconds must be in (0, 140]")
    try:
        return _run_resume(args) if args.resume is not None else _run_normal(args)
    except ContextStop as error:
        print(json.dumps({"status": "stopped", "error_code": error.code,
                          "error": error.message}, ensure_ascii=False), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
