"""Prepare one fixed, operator-controlled religion-war context.

The native side invokes one of two reviewed scripts (the default ENG scenario
uses ``llm_rel56.txt``; the LEI scenario uses ``llm_rel56b.txt``) after
receiving its fixed request.  This operator verifies a paused POR boundary,
proves that FRA and the selected opponent are at peace, writes the selected
script and UTF-16LE path registration, publishes exactly one atomic request,
and records the bounded native event.
It does not switch the player, advance time, save, or submit a peace action.
The native script result and the observed ENG--FRA war transition are kept as
separate checks; script success alone is never treated as war creation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from work.local_config import game_exe, user_data  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import (  # noqa: E402
    ExperimentStop, _copy_log_slice, _sha256_file, _write_json,
)
from work.run_alliance_inbound_response import control_snapshot  # noqa: E402
from work.run_peace_context_queries import _public_context_contract  # noqa: E402


EXPECTED_DATE_RAW = 56549088
PLAYER_TAG = "POR"
PLAYER_SLOT = 189
WAR_ACTOR = "FRA"
HEADER_PATH = ROOT / "work/native/religion-war-context-script.h"
REQUEST_NAME = "religion-war-context.req"
CONFIG_NAME = "religion-war-context-script.path"
SCENARIOS = {
    "ENG": {
        "recipient": "ENG",
        "script_name": "llm_rel56.txt",
        "script_marker": "EU4REL56",
        "request_wire": b"TEST_ONLY RELIGION_WAR 56549088\n",
    },
    "LEI": {
        "recipient": "LEI",
        "script_name": "llm_rel56b.txt",
        "script_marker": "EU4REL56B",
        "request_wire": b"TEST_ONLY RELIGION_SMALL_WAR 56549088\n",
    },
}
MAX_POLL_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.2
MAX_EVENT_BYTES = 8 * 1024 * 1024
HASH_MAX_BYTES = 8 * 1024 * 1024


def _hash_small(path: Path) -> dict:
    """Hash one bounded fixture or metadata file."""

    return _sha256_file(path, maximum=HASH_MAX_BYTES)


def _embedded_script_bytes(scenario: dict[str, object]) -> bytes:
    """Extract the exact ASCII script literal compiled into the native header."""

    try:
        raw = HEADER_PATH.read_bytes()
    except OSError as error:
        raise ExperimentStop("SCRIPT_HEADER_UNREADABLE", str(HEADER_PATH)) from error
    if len(raw) > HASH_MAX_BYTES:
        raise ExperimentStop("SCRIPT_HEADER_TOO_LARGE", str(HEADER_PATH))
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise ExperimentStop("SCRIPT_HEADER_NOT_ASCII", str(HEADER_PATH)) from error
    marker = scenario["script_marker"]
    script_name = scenario["script_name"]
    literal = re.search(
        rf'R"{re.escape(str(marker))}\((.*?)\){re.escape(str(marker))}"',
        text, re.DOTALL,
    )
    if literal is None:
        raise ExperimentStop("SCRIPT_LITERAL_NOT_FOUND", str(HEADER_PATH))
    script = literal.group(1).encode("ascii")
    if not script:
        raise ExperimentStop("SCRIPT_LITERAL_EMPTY", str(HEADER_PATH))
    if str(script_name).encode("ascii") in script:
        raise ExperimentStop("SCRIPT_LITERAL_CONTAINS_NATIVE_FILENAME", str(HEADER_PATH))
    return script


def _write_exclusive(path: Path, content: bytes) -> dict:
    """Write one small fixture without replacing an existing file."""

    try:
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise ExperimentStop("FIXTURE_FILE_EXISTS", str(path)) from error
    return _hash_small(path)


def _publish_atomic(path: Path, content: bytes) -> dict:
    """Publish one request by hard-linking a fully written same-directory file."""

    if path.exists():
        raise ExperimentStop("REQUEST_ALREADY_PRESENT", str(path))
    metadata = {
        "path": str(path),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "published": False,
    }
    pending = path.with_name(f".{path.name}.{uuid.uuid4().hex}.pending")
    try:
        with pending.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(pending, path)
        except FileExistsError as error:
            raise ExperimentStop("REQUEST_ALREADY_PRESENT", str(path)) from error
        metadata["published"] = True
    finally:
        pending.unlink(missing_ok=True)
    # The native tick may consume and delete the request immediately after the
    # hard-link publication, so hash the exact bytes before publishing rather
    # than reopening a possibly already-consumed request path.
    return metadata


def _read_native_event(log: Path, start: int, pid: int,
                       timeout: float) -> tuple[dict | None, list[dict], int]:
    """Stream a bounded log suffix until this process's fixed result appears."""

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
                while consumed < MAX_EVENT_BYTES:
                    chunk = stream.read(min(64 * 1024, MAX_EVENT_BYTES - consumed))
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
                        if event.get("event") != "native_religion_war_context_result":
                            continue
                        if event.get("pid") != pid:
                            continue
                        seen.append(event)
                        return event, seen, consumed
        except OSError:
            pass
        time.sleep(POLL_INTERVAL_SECONDS)
    return None, seen, consumed


def _query_pair(api: DiplomacyTools, recipient: str) -> dict:
    """Inspect the public ENG--FRA war context without submitting peace."""

    return api.inspect_diplomatic_action(
        "white_peace", WAR_ACTOR, recipient,
        phase="initiate", parameters={},
    )


def _pair_at_war(value: object, recipient: str) -> bool:
    if not isinstance(value, dict):
        return False
    rows = value.get("war_contexts")
    if not isinstance(rows, list):
        return False
    return any(
        isinstance(row, dict)
        and row.get("pair_at_war") is True
        and row.get("actor") == WAR_ACTOR
        and row.get("recipient") == recipient
        for row in rows
    )


def _pair_query_record(value: object, recipient: str) -> dict:
    return {
        "query": value,
        "contract_complete": _public_context_contract(
            value, "white_peace", recipient),
        "pair_at_war": _pair_at_war(value, recipient),
    }


def _event_checks(event: dict | None, pid: int,
                  scenario: dict[str, object]) -> dict:
    result = event if isinstance(event, dict) else {}
    is_result = result.get("event") == "native_religion_war_context_result"
    return {
        "native_event_found": isinstance(event, dict),
        "native_result_event": is_result,
        "native_event_pid": is_result and result.get("pid") == pid,
        "date_matches_fixed_contract": is_result and result.get(
            "date_raw") == EXPECTED_DATE_RAW,
        "player_is_por": is_result and result.get("player") == PLAYER_TAG,
        "paused": is_result and result.get("paused") is True,
        "request_verified": is_result and result.get("request_verified") is True,
        "script_verified": is_result and result.get("script_verified") is True,
        "registration_verified": is_result and result.get(
            "registration_verified") is True,
        "native_success": is_result and result.get("native_success") is True,
        "mode_fixed": is_result and result.get(
            "mode") == "operator_prepared_war_context",
        "opponent_matches": is_result and result.get(
            "opponent") == scenario["recipient"],
        "script_name_fixed": is_result and result.get(
            "script_name") == scenario["script_name"],
        "peace_submission_false": is_result and result.get(
            "peace_proposal_submitted") is False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="path for the bounded JSON report")
    parser.add_argument("--recipient", choices=tuple(SCENARIOS), default="ENG",
                        help="fixed native scenario opponent (default: ENG)")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    args = parser.parse_args()
    if not 1.0 <= args.timeout_seconds <= MAX_POLL_SECONDS:
        parser.error("--timeout-seconds must be between 1 and 60")

    installation = args.installation.expanduser().resolve(strict=True)
    output = args.output.expanduser().resolve()
    if output.exists():
        parser.error(f"--output already exists: {output}")
    scenario = SCENARIOS[args.recipient]
    recipient = str(scenario["recipient"])
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = output.parent / f"{output.stem}-evidence-{uuid.uuid4().hex}"
    evidence.mkdir()
    log = installation.parent / "control-probe.jsonl"
    log_start: int | None = None
    report: dict = {
        "status": "running",
        "mode": "operator_prepared_war_context",
        "expected_date_raw": EXPECTED_DATE_RAW,
        "player": PLAYER_TAG,
        "scenario": args.recipient,
        "war_pair": {"actor": WAR_ACTOR, "recipient": recipient},
        "game_action": "operator_prepared_war_context_only",
        "business_submission": False,
        "advance_call_count": 0,
        "save_call_count": 0,
        "peace_submission_call_count": 0,
        "native_request_publish_count": 0,
        "native_run_count": 0,
        "checks": {},
        "output": str(output),
        "evidence_directory": str(evidence),
    }
    event: dict | None = None
    try:
        report["installation"] = _hash_small(installation)
        report["source_files"] = {"script_header": _hash_small(HEADER_PATH)}
        script = _embedded_script_bytes(scenario)
        script_name = str(scenario["script_name"])
        request_wire = bytes(scenario["request_wire"])
        script_marker = str(scenario["script_marker"])
        if len(script_name.encode("ascii")) >= 16:
            raise ExperimentStop("SCRIPT_FILENAME_TOO_LONG", script_name)
        report["fixture"] = {
            "script_name": script_name,
            "script_marker": script_marker,
            "script_bytes": len(script),
            "script_ascii": script.isascii(),
            "script_sha256": hashlib.sha256(script).hexdigest(),
            "request_name": REQUEST_NAME,
            "config_name": CONFIG_NAME,
            "request_wire": request_wire.decode("ascii"),
            "request_is_fixed": request_wire == (
                b"TEST_ONLY RELIGION_WAR 56549088\n"
                if args.recipient == "ENG"
                else b"TEST_ONLY RELIGION_SMALL_WAR 56549088\n"),
        }

        session = ObserverSession(installation, game_exe())
        report["session_id"] = session.session_id
        report["pid"] = int(session.record["pid"])
        report["dll_sha256"] = session.record.get("dll_sha256")
        health = wait_runtime_ready(session, restore_minimized=True)
        before_control = control_snapshot(
            int(session.record["pid"]), evidence / "before-control.json")
        report["before"] = {"health": health, "control": before_control}
        baseline_ok = (
            health.get("status") == "ready"
            and health.get("date_raw") == EXPECTED_DATE_RAW
            and before_control.get("player_slot") == PLAYER_SLOT
            and before_control.get("paused_flag") == 1
            and before_control.get("date_raw") == EXPECTED_DATE_RAW
        )
        if not baseline_ok:
            raise ExperimentStop(
                "BASELINE_NOT_READY_POR_PAUSED", json.dumps(report["before"], ensure_ascii=False))

        destination = user_data().resolve() / script_name
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

        config_path = installation.parent / CONFIG_NAME
        config_bytes = (str(destination) + "\0").encode("utf-16le")
        report["fixture"]["script_path_config"] = _write_exclusive(
            config_path, config_bytes)

        try:
            log_start = log.stat().st_size
        except OSError as error:
            raise ExperimentStop("CONTROL_LOG_UNAVAILABLE", str(log)) from error

        with DurableJournal(evidence / "diplomacy.sqlite3",
                            session.experiment_id, session.session_id) as journal:
            api = DiplomacyTools(journal, session)
            before_query = _pair_query_record(_query_pair(api, recipient), recipient)
            report["before"]["peace"] = before_query
            report["query_call_count"] = 1
            if not before_query["contract_complete"]:
                raise ExperimentStop("PEACE_CONTEXT_QUERY_INCOMPLETE",
                                      json.dumps(before_query, ensure_ascii=False))
            if before_query["pair_at_war"]:
                raise ExperimentStop(
                    "SELECTED_PAIR_NOT_AT_PEACE",
                    f"FRA-{recipient} precondition requires no active war",
                )

            request_path = installation.parent / REQUEST_NAME
            report["fixture"]["request"] = _publish_atomic(
                request_path, request_wire)
            report["request_log_start_offset"] = log_start
            report["native_request_publish_count"] = 1

            event, seen, consumed = _read_native_event(
                log, log_start, int(session.record["pid"]), args.timeout_seconds)
            report["native_event_count"] = len(seen)
            report["native_event_bytes_scanned"] = consumed
            report["native_event"] = event
            report["native_run_count"] = sum(
                item.get("event") == "native_religion_war_context_result"
                for item in seen)

            after_query = _pair_query_record(_query_pair(api, recipient), recipient)
            report["query_call_count"] = 2
            report["after"] = {"peace": after_query}

        if event is None:
            raise ExperimentStop("NATIVE_CONTEXT_RESULT_TIMEOUT", str(log))
        after_health = session.health()
        after_control = control_snapshot(
            int(session.record["pid"]), evidence / "after-control.json")
        report["after"].update({"health": after_health, "control": after_control})
        report["checks"] = _event_checks(
            event, int(session.record["pid"]), scenario)
        report["checks"].update({
            "baseline_ready": baseline_ok,
            "script_name_is_fixed": report["fixture"]["script_name"] == script_name,
            "script_bytes_match_header": report["fixture"]["script_bytes_match_header"],
            "request_wire_is_fixed": report["fixture"]["request_is_fixed"],
            "one_native_event": report["native_event_count"] == 1,
            "one_native_run": report["native_run_count"] == 1,
            "before_selected_pair_at_peace": report["before"]["peace"]["pair_at_war"] is False,
            "after_selected_pair_at_war": report["after"]["peace"]["pair_at_war"] is True,
            "war_transition_proven": (
                report["before"]["peace"]["pair_at_war"] is False
                and report["after"]["peace"]["pair_at_war"] is True
            ),
            "after_peace_context_complete": report["after"]["peace"]["contract_complete"] is True,
            "same_por_paused_date": all(
                after_control.get(key) == before_control.get(key)
                for key in ("player_slot", "paused_flag", "date_raw")),
            "health_ready_after": after_health.get("status") == "ready",
            "no_business_action": report["business_submission"] is False,
            "no_advance": report["advance_call_count"] == 0,
            "no_save": report["save_call_count"] == 0,
            "no_peace_submission": report["peace_submission_call_count"] == 0
            and event.get("peace_proposal_submitted") is False,
        })
        report["war_transition"] = {
            "before_pair_at_war": report["before"]["peace"]["pair_at_war"],
            "after_pair_at_war": report["after"]["peace"]["pair_at_war"],
            "native_success_is_not_transition_proof": True,
            "transition_proven": report["checks"]["war_transition_proven"],
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
        if report["status"] != "passed":
            raise ExperimentStop("WAR_CONTEXT_CHECK_FAILED",
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
                log, log_start, evidence / "native-events.jsonl")
        _write_json(output, report)
    print(json.dumps({"status": report["status"], "report": str(output),
                      "evidence": str(evidence)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
