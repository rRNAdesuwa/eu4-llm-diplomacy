"""Prepare a fixed, test-only inbound Vassalization context.

The operator loads one reviewed script which normalizes FRA's owned-province
development and prepares the SAV relationship.  It publishes exactly one
native preparation request and waits for the matching native result.  The
script never creates a subject, submits a Vassalization offer, or chooses
FRA's later accept/reject response.  A later operator sends the actual
``TEST_ONLY VASSALIZATION_TO_FRA SAV`` proposal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.diplomacy import ObserverSession
from work.local_config import game_exe, user_data
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_execution import (
    ExperimentStop, _copy_log_slice, _sha256_file, _write_json,
)
from work.run_alliance_inbound_response import control_snapshot


_HEADER_PATH = ROOT / "work/native/vassal-inbound-test-context-script.h"
_MODIFIER_PATH = ROOT / "mod/llm_bridge/common/opinion_modifiers/llm_bridge_r35_test.txt"
_SCRIPT_NAME = "llm_vas_in.txt"
_REQUEST_NAME = "vassal-inbound-test-context.req"
_CONFIG_NAME = "vassal-inbound-test-context-script.path"
_REQUEST_PREFIX = "TEST_ONLY VASSAL_INBOUND_CONTEXT "
_SCRIPT_MARKER = "EU4VASSALIN"
_MAX_POLL_SECONDS = 60.0
_POLL_INTERVAL_SECONDS = 0.2
_MAX_EVENT_BYTES = 8 * 1024 * 1024
_HASH_MAX_BYTES = 8 * 1024 * 1024


def _hash_small(path: Path) -> dict:
    """Hash a small fixture or metadata file with the shared bounded helper."""

    return _sha256_file(path, maximum=_HASH_MAX_BYTES)


def _embedded_script_bytes() -> bytes:
    """Extract the exact ASCII literal compiled into the native include."""

    try:
        raw = _HEADER_PATH.read_bytes()
    except OSError as error:
        raise ExperimentStop("SCRIPT_HEADER_UNREADABLE", str(_HEADER_PATH)) from error
    if len(raw) > _HASH_MAX_BYTES:
        raise ExperimentStop("SCRIPT_HEADER_TOO_LARGE", str(_HEADER_PATH))
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise ExperimentStop("SCRIPT_HEADER_NOT_ASCII", str(error)) from error
    literal = re.search(
        rf'R"{re.escape(_SCRIPT_MARKER)}\((.*?)\){re.escape(_SCRIPT_MARKER)}"',
        text, re.DOTALL,
    )
    if literal is None:
        raise ExperimentStop("SCRIPT_LITERAL_NOT_FOUND", str(_HEADER_PATH))
    script = literal.group(1).encode("ascii")
    if not script:
        raise ExperimentStop("SCRIPT_LITERAL_EMPTY", str(_HEADER_PATH))
    if _SCRIPT_NAME.encode("ascii") in script:
        raise ExperimentStop("SCRIPT_LITERAL_CONTAINS_NATIVE_FILENAME", str(_HEADER_PATH))
    return script


def _write_exclusive(path: Path, content: bytes) -> dict:
    """Write one small fixture file without replacing an existing file."""

    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError as error:
        raise ExperimentStop("FIXTURE_FILE_EXISTS", str(path)) from error
    return _hash_small(path)


def _read_native_events(log: Path, start: int, pid: int,
                        timeout: float) -> tuple[dict | None, list[dict], int]:
    """Stream a bounded log suffix until this process's fixed event appears."""

    deadline = time.monotonic() + timeout
    cursor = start
    consumed = 0
    pending = b""
    seen: list[dict] = []
    while time.monotonic() < deadline:
        try:
            with log.open("rb") as stream:
                stream.seek(0, 2)
                size = stream.tell()
                if size < start:
                    return None, seen, consumed
                stream.seek(cursor)
                while consumed < _MAX_EVENT_BYTES:
                    chunk = stream.read(min(64 * 1024, _MAX_EVENT_BYTES - consumed))
                    if not chunk:
                        break
                    consumed += len(chunk)
                    cursor += len(chunk)
                    pending += chunk
                    end = pending.rfind(b"\n")
                    if end < 0:
                        continue
                    complete, pending = pending[:end + 1], pending[end + 1:]
                    for raw_line in complete.splitlines():
                        try:
                            event = json.loads(raw_line.decode("utf-8"))
                        except (UnicodeDecodeError, ValueError):
                            continue
                        if not isinstance(event, dict):
                            continue
                        name = event.get("event")
                        if name not in (
                                "native_vassal_inbound_context_result",
                                "native_vassal_inbound_context_failed"):
                            continue
                        if name == "native_vassal_inbound_context_result":
                            if event.get("pid") != pid:
                                continue
                        seen.append(event)
                        return event, seen, consumed
        except OSError:
            pass
        time.sleep(_POLL_INTERVAL_SECONDS)
    return None, seen, consumed


def _event_checks(event: dict | None, expected_date: int, pid: int) -> dict:
    result = event if isinstance(event, dict) else {}
    is_result = result.get("event") == "native_vassal_inbound_context_result"
    return {
        "native_event_found": isinstance(event, dict),
        "native_result_event": is_result,
        "native_event_pid": is_result and result.get("pid") == pid,
        "request_verified": is_result and result.get("request_verified") is True,
        "script_verified": is_result and result.get("script_verified") is True,
        "registration_verified": is_result and result.get("registration_verified") is True,
        "native_success": is_result and result.get("native_success") is True,
        "expected_date_matches": is_result and result.get("expected_date_raw") == expected_date,
        "current_date_matches": is_result and result.get("date_raw") == expected_date,
        "por_slot": is_result and result.get("player") == "POR"
        and result.get("player_slot") == 189,
        "paused": is_result and result.get("paused") is True,
        "fixed_evaluator": is_result and result.get("run_evaluator_rva") == "0xe4f040",
        "fixed_registration": is_result and result.get("run_registration_rva") == "0x1fc2558",
        "business_submission_false": is_result and result.get(
            "vassalization_business_submitted") is False,
        "response_decision_false": is_result and result.get(
            "response_decision_made") is False,
        "context_only": is_result and result.get(
            "business_result") == "context_preparation_only",
        "development_fixture_named": is_result and result.get(
            "development_fixture") == "FRA_every_owned_province_set_base_1",
        "development_operation_count": is_result and result.get(
            "expected_development_operations") == 60,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--expected-date-raw", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    args = parser.parse_args()
    if not 1.0 <= args.timeout_seconds <= _MAX_POLL_SECONDS:
        parser.error("--timeout-seconds must be between 1 and 60")

    installation = args.installation.expanduser().resolve(strict=True)
    directory = installation.parent
    artifact = directory / ("vassal-inbound-context-preparation-" + uuid.uuid4().hex)
    artifact.mkdir()
    log = directory / "control-probe.jsonl"
    log_start: int | None = None
    report: dict = {
        "status": "running",
        "mode": "test_only_vassalization_inbound_context_preparation",
        "expected_date_raw": args.expected_date_raw,
        "business_acceptance": False,
        "game_action": "context_only",
        "native_request_publish_count": 0,
        "native_run_count": 0,
        "resubmission_attempted": False,
        "response_decision_made": False,
        "vassalization_business_submitted": False,
        "checks": {},
    }
    event: dict | None = None
    try:
        report["installation"] = _hash_small(installation)
        source_files = {"script_header": _hash_small(_HEADER_PATH)}
        if _MODIFIER_PATH.is_file():
            source_files["modifier_source"] = _hash_small(_MODIFIER_PATH)
        report["source_files"] = source_files
        script = _embedded_script_bytes()
        effects = ["set_base_tax = 1", "set_base_production = 1",
                   "set_base_manpower = 1"]
        report["development_fixture"] = {
            "country": "FRA",
            "selector": "every_owned_province",
            "effects": effects,
            "target_value_each": 1,
            "expected_owned_province_count": 20,
            "expected_development_operations": 60,
            "development_delta_requires_save_or_native_readback": True,
        }
        report["relationship_fixture"] = {
            "countries": ["FRA", "SAV"],
            "create_alliance": True,
            "opinion_modifier": "r35_test_vassal_opinion",
            "opinion_value": 200,
            "bilateral": True,
            "subject_created": False,
            "response_decision_made": False,
        }
        report["fixture"] = {
            "script_name": _SCRIPT_NAME,
            "script_bytes": len(script),
            "script_ascii": script.isascii(),
            "script_sha256": hashlib.sha256(script).hexdigest(),
            "request_wire": f"{_REQUEST_PREFIX}{args.expected_date_raw}\n",
            "request_name": _REQUEST_NAME,
            "config_name": _CONFIG_NAME,
            "modifier": "r35_test_vassal_opinion",
            "modifier_is_explicit_fixture_only": True,
        }
        if len(_SCRIPT_NAME.encode("ascii")) >= 16:
            raise ExperimentStop("SCRIPT_FILENAME_TOO_LONG", _SCRIPT_NAME)

        session = ObserverSession(installation, game_exe())
        report["session_id"] = session.session_id
        report["pid"] = int(session.record["pid"])
        report["dll_sha256"] = session.record.get("dll_sha256")
        health = wait_runtime_ready(session, restore_minimized=True)
        before = control_snapshot(int(session.record["pid"]), artifact / "before-control.json")
        report["before"] = {"health": health, "control": before}
        baseline_ok = (
            health.get("status") == "ready"
            and health.get("date_raw") == args.expected_date_raw
            and before.get("player_slot") == 189
            and before.get("paused_flag") == 1
            and before.get("date_raw") == args.expected_date_raw
        )
        if not baseline_ok:
            raise ExperimentStop("BASELINE_NOT_READY_POR_PAUSED", json.dumps(before))

        destination = user_data().resolve() / _SCRIPT_NAME
        if not destination.parent.is_dir():
            raise ExperimentStop("USER_DATA_DIRECTORY_MISSING", str(destination.parent))
        if destination.exists():
            raise ExperimentStop("SCRIPT_DESTINATION_EXISTS", str(destination))
        destination_hash = _write_exclusive(destination, script)
        report["fixture"]["script_destination"] = destination_hash
        report["fixture"]["script_bytes_match_header"] = (
            destination_hash["sha256"] == report["fixture"]["script_sha256"]
            and destination_hash["bytes"] == len(script)
        )
        if not report["fixture"]["script_bytes_match_header"]:
            raise ExperimentStop("SCRIPT_DESTINATION_HASH_MISMATCH", str(destination))

        config_path = directory / _CONFIG_NAME
        config_bytes = (str(destination) + "\0").encode("utf-16le")
        report["fixture"]["script_path_config"] = _write_exclusive(config_path, config_bytes)

        try:
            log_start = log.stat().st_size
        except OSError as error:
            raise ExperimentStop("CONTROL_LOG_UNAVAILABLE", str(log)) from error
        request_path = directory / _REQUEST_NAME
        request_wire = f"{_REQUEST_PREFIX}{args.expected_date_raw}\n".encode("ascii")
        report["fixture"]["request"] = _write_exclusive(request_path, request_wire)
        report["request_log_start_offset"] = log_start
        report["native_request_publish_count"] = 1

        event, seen, consumed = _read_native_events(
            log, log_start, int(session.record["pid"]), args.timeout_seconds)
        report["native_event_count"] = len(seen)
        report["native_event_bytes_scanned"] = consumed
        report["native_event"] = event
        report["native_run_count"] = sum(
            item.get("event") == "native_vassal_inbound_context_result"
            for item in seen)
        if event is None:
            raise ExperimentStop("NATIVE_CONTEXT_RESULT_TIMEOUT", str(log))
        after = control_snapshot(int(session.record["pid"]), artifact / "after-control.json")
        report["after"] = after
        report["checks"] = _event_checks(
            event, args.expected_date_raw, int(session.record["pid"]))
        report["checks"].update({
            "baseline_ready": baseline_ok,
            "script_name_is_fixed": report["fixture"]["script_name"] == _SCRIPT_NAME,
            "script_filename_short": len(_SCRIPT_NAME.encode("ascii")) < 16,
            "script_bytes_match_header": report["fixture"]["script_bytes_match_header"],
            "one_native_event": len(seen) == 1,
            "one_native_run": report["native_run_count"] == 1,
            "same_por_paused_date": all(
                after.get(key) == before.get(key)
                for key in ("player_slot", "paused_flag", "date_raw")),
            "no_business_action": event.get("business_result") == "context_preparation_only",
            "no_response_decision": event.get("response_decision_made") is False,
        })
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
        if report["status"] != "passed":
            raise ExperimentStop("CONTEXT_PREPARATION_CHECK_FAILED",
                                 json.dumps(report["checks"], sort_keys=True))
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "type": type(error).__name__, "message": str(error),
            "code": getattr(error, "code", None),
        }
    finally:
        if log_start is not None:
            report["native_events"] = _copy_log_slice(
                log, log_start, artifact / "native-events.jsonl")
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
