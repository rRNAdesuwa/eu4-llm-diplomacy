#!/usr/bin/env python3
"""Validate a saved Peace response after a fresh read-only reload.

The source execution and save-observer reports are immutable evidence.  This
validator starts no process, publishes no request, advances no date, and
does not save the game.  It reads the already running observer installation,
captures the four bounded probes, verifies the saved file hash, and checks
the new process's native pending-recovery summary.  The historical public
incoming catalog is deliberately not used to decide whether a pending offer
is active.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import ObserverSession  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_peace_inbound_response import _war_pair_summary  # noqa: E402
from work.run_royal_marriage_execution import (  # noqa: E402
    _installation_binding,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _hash_file,
    _read_json,
    _run_snapshots,
    _write_json,
)


_ACTOR = "ENG"
_RECIPIENT = "FRA"
_FAMILY = "peace"
_ACTION = "peace_offer"
_PLAYER_SLOT = 189  # POR in the controlled experiment
_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_EVENT_LOG_BYTES = 10 * 1024 * 1024
_MAX_SAVE_BYTES = 256 * 1024 * 1024
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


class ReloadValidationError(RuntimeError):
    """A bounded validation failure with a stable diagnostic code."""


def _resolve_report(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.is_dir():
        resolved = (resolved / "report.json").resolve(strict=True)
    if not resolved.is_file():
        raise ReloadValidationError(f"REPORT_NOT_FILE:{resolved}")
    return resolved


def _all_true(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and all(item is True for item in value.values())


def _output_paths(requested: Path) -> tuple[Path, Path]:
    """Return an untouched report path and a fresh evidence directory."""

    target = requested.expanduser().resolve()
    if target.exists():
        raise ReloadValidationError(f"OUTPUT_ALREADY_EXISTS:{target}")
    if target.suffix.casefold() == ".json":
        report_path = target
        evidence = target.parent / f"{target.stem}-evidence"
    else:
        evidence = target
        report_path = target / "report.json"
    if evidence.exists() or report_path.exists():
        raise ReloadValidationError(f"OUTPUT_ALREADY_EXISTS:{report_path}")
    evidence.mkdir(parents=True, exist_ok=False)
    return report_path, evidence


def _source_probe_set(payload: dict[str, object], phase: str) -> dict[str, dict[str, object]]:
    section = payload.get(phase)
    records = section.get("probes") if isinstance(section, dict) else None
    if not isinstance(records, dict):
        return {}
    result: dict[str, dict[str, object]] = {}
    for name, record in records.items():
        if not isinstance(record, dict):
            continue
        item = dict(record)
        path = item.get("snapshot_path")
        if isinstance(path, str):
            snapshot_path = Path(path)
            if snapshot_path.is_file():
                try:
                    snapshot = _read_json(snapshot_path, maximum=_MAX_METADATA_BYTES)
                except ReloadValidationError:
                    snapshot = None
                if isinstance(snapshot, dict):
                    item["snapshot"] = snapshot
        result[str(name)] = item
    return result


def _source_probe_contract(payload: dict[str, object]) -> dict[str, object]:
    before = _source_probe_set(payload, "before")
    after = _source_probe_set(payload, "after")
    before_report = payload.get("before")
    after_report = payload.get("after")
    before_complete = (
        isinstance(before_report, dict)
        and isinstance(before_report.get("probes"), dict)
        and _snapshots_complete(before_report["probes"])
    )
    after_complete = (
        isinstance(after_report, dict)
        and isinstance(after_report.get("probes"), dict)
        and _snapshots_complete(after_report["probes"])
    )
    return {
        "before": before,
        "after": after,
        "before_complete": before_complete,
        "after_complete": after_complete,
        "four_probe_names": set(after) == {"alliance_state", "control_state", "diplomats", "war_state"},
    }


def _source_contract(payload: dict[str, object]) -> dict[str, object]:
    native = payload.get("native_response")
    response_event = native.get("response_event") if isinstance(native, dict) else None
    result = payload.get("result")
    checks = payload.get("checks")
    decision = payload.get("decision")
    expected_after = decision == "reject"
    # The explicit decision is the only source for the expected war transition.
    checks_out: dict[str, bool] = {
        "status_passed": payload.get("status") == "passed",
        "checks_passed": _all_true(checks),
        "action_family": payload.get("action_id") == _ACTION
        and payload.get("family") == _FAMILY,
        "actor_recipient": payload.get("actor") == _ACTOR
        and payload.get("recipient") == _RECIPIENT,
        "decision_supported": decision in ("accept", "reject"),
        "result_object": isinstance(result, dict),
        "native_response_contract": isinstance(native, dict)
        and native.get("contract") is True
        and native.get("full_payload") is True
        and native.get("response_verified") is True
        and native.get("request_binding_verified") is True
        and native.get("handler_forwarded") is True
        and native.get("handler_consumed") is True
        and native.get("pending_removed") is True,
        "response_binding": isinstance(response_event, dict)
        and response_event.get("event") == "native_peace_inbound_response_result"
        and response_event.get("family") == _FAMILY
        and response_event.get("action_id") == _ACTION
        and response_event.get("actor") == _ACTOR
        and response_event.get("recipient") == _RECIPIENT
        and response_event.get("phase") == decision
        and response_event.get("request_id") == payload.get("request_id")
        and response_event.get("session_id") == (
            payload.get("session", {}).get("session_id")
            if isinstance(payload.get("session"), dict) else None
        )
        and response_event.get("war_before") is True
        and response_event.get("war_after") is (expected_after if decision in ("accept", "reject") else None),
    }
    return {
        "checks": checks_out,
        "all": all(checks_out.values()),
        "decision": decision,
        "expected_pair_at_war_after": False if decision == "accept" else True if decision == "reject" else None,
        "source_session_id": payload.get("session", {}).get("session_id")
        if isinstance(payload.get("session"), dict) else None,
        "source_date_raw": (
            payload.get("after", {}).get("control", {}).get("date_raw")
            if isinstance(payload.get("after"), dict)
            and isinstance(payload["after"].get("control"), dict) else None
        ),
        "native_response": native,
    }


def _save_contract(save_report: dict[str, object]) -> dict[str, object]:
    save = save_report.get("save")
    reported_hash = save.get("sha256") if isinstance(save, dict) else None
    save_path = save.get("path") if isinstance(save, dict) else None
    name = save_report.get("name")
    checks = {
        "report_success": save_report.get("status") == "success",
        "save_object": isinstance(save, dict),
        "name_is_eu4_basename": isinstance(name, str)
        and Path(name).name == name and name.casefold().endswith(".eu4"),
        "reported_hash_valid": isinstance(reported_hash, str)
        and _SHA256_RE.fullmatch(reported_hash) is not None,
        "reported_path_valid": isinstance(save_path, str)
        and Path(save_path).is_file(),
    }
    current = None
    if checks["reported_path_valid"]:
        current = _hash_file(Path(str(save_path)), maximum=_MAX_SAVE_BYTES)
    actual_hash = current.get("sha256") if isinstance(current, dict) else None
    checks["actual_hash_matches_report"] = (
        checks["reported_hash_valid"] is True
        and actual_hash is not None
        and str(actual_hash).casefold() == str(reported_hash).casefold()
    )
    return {
        "checks": checks,
        "all": all(checks.values()),
        "name": name,
        "reported": {"path": save_path, "sha256": reported_hash},
        "actual": current,
    }


def _source_map(value: object) -> dict[str, str] | None:
    if not isinstance(value, list) or len(value) != 61:
        return None
    result: dict[str, str] = {}
    for item in value:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        digest = item.get("sha256")
        if not isinstance(name, str) or not isinstance(digest, str):
            return None
        if _SHA256_RE.fullmatch(digest) is None or name in result:
            return None
        result[name] = digest.casefold()
    return result if len(result) == 61 else None


def _binding_contract(source: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    source_manifest = source.get("build_manifest")
    current_manifest = current.get("build_manifest")
    source_map = _source_map(source_manifest.get("sources") if isinstance(source_manifest, dict) else None)
    current_map = _source_map(current_manifest.get("sources") if isinstance(current_manifest, dict) else None)
    source_build = source.get("build_binding")
    current_build = current.get("build_binding")
    source_dll = source.get("session", {}).get("dll_sha256") if isinstance(source.get("session"), dict) else None
    current_installation = current.get("installation")
    current_dll = (
        current_installation.get("declared_dll_sha256")
        if isinstance(current_installation, dict)
        else None
    )
    if not isinstance(current_dll, str) and isinstance(current_build, dict):
        current_dll = current_build.get("installation_dll_sha256")
    checks = {
        "source_has_61_sources": source_map is not None,
        "reload_has_61_sources": current_map is not None,
        "source_reload_source_hashes_equal": source_map is not None and source_map == current_map,
        "source_build_matches_dll": isinstance(source_build, dict)
        and source_build.get("installation_matches_build_manifest") is True,
        "reload_build_matches_dll": isinstance(current_build, dict)
        and current_build.get("installation_matches_build_manifest") is True,
        "dll_sha256_equal": isinstance(source_dll, str)
        and isinstance(current_dll, str)
        and source_dll.casefold() == current_dll.casefold(),
    }
    return {
        "checks": checks,
        "all": all(checks.values()),
        "source_dll_sha256": source_dll,
        "reload_dll_sha256": current_dll,
        "source_source_count": len(source_map) if source_map is not None else None,
        "reload_source_count": len(current_map) if current_map is not None else None,
    }


def _stream_recovery_log(path: Path, session_id: str, expected_date: int,
                         output: Path) -> dict[str, object]:
    """Read only the bounded native recovery records from the fresh process."""

    if not path.is_file():
        raise ReloadValidationError(f"RECOVERY_LOG_MISSING:{path}")
    size = path.stat().st_size
    if size > _MAX_EVENT_LOG_BYTES:
        raise ReloadValidationError(f"RECOVERY_LOG_TOO_LARGE:{path}:{size}")
    digest = hashlib.sha256()
    installed = False
    installed_index = -1
    scan_events: list[dict[str, object]] = []
    restored_target: list[dict[str, object]] = []
    current_events = 0
    invalid_lines = 0
    line_count = 0
    selected: list[dict[str, object]] = []
    with path.open("rb") as stream:
        for index, raw in enumerate(stream):
            line_count += 1
            digest.update(raw)
            if len(raw) > 256 * 1024:
                invalid_lines += 1
                continue
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                invalid_lines += 1
                continue
            if not isinstance(event, dict):
                continue
            event_session = event.get("session_id")
            if event.get("event") == "diplomacy_observer_installed" and event_session == session_id:
                installed = True
                installed_index = index
                selected.append({"event": event, "line": index})
            if event_session == session_id:
                current_events += 1
            if index <= installed_index:
                continue
            event_name = event.get("event")
            if event_name == "native_diplomacy_saved_pending_scan_complete":
                scan_events.append(event)
                selected.append({"event": event, "line": index})
            elif (
                event_name == "native_diplomacy_inbound_pending_restored"
                and event_session == session_id
                and event.get("action_id") == _ACTION
                and event.get("family") == _FAMILY
                and event.get("actor") == _ACTOR
                and event.get("recipient") == _RECIPIENT
            ):
                restored_target.append(event)
                selected.append({"event": event, "line": index})
    scan = scan_events[-1] if scan_events else None
    scan_checks = {
        "observer_install_matches_session": installed,
        "scan_event_present": isinstance(scan, dict),
        "scan_date_matches": isinstance(scan, dict) and scan.get("date_raw") == expected_date,
        "queue_readable": isinstance(scan, dict) and scan.get("queue_readable") is True,
        "list_integrity": isinstance(scan, dict) and scan.get("list_integrity") is True,
        "queue_unchanged": isinstance(scan, dict) and scan.get("native_queue_unchanged") is True,
        "native_queue_empty": isinstance(scan, dict) and scan.get("native_queue_count") == 0,
        "restored_count_empty": isinstance(scan, dict) and scan.get("restored_count") == 0,
        "target_not_restored": not restored_target,
    }
    selected_path = output / "native-recovery-events.json"
    _write_json(selected_path, {
        "session_id": session_id,
        "log": {"path": str(path), "bytes": size, "sha256": digest.hexdigest(),
                "line_count": line_count, "invalid_line_count": invalid_lines,
                "bounded": True},
        "selected": selected,
        "scan": scan,
        "target_restored_events": restored_target,
    })
    return {
        "checks": scan_checks,
        "all": all(scan_checks.values()),
        "log": {"path": str(path), "bytes": size, "sha256": digest.hexdigest(),
                "line_count": line_count, "invalid_line_count": invalid_lines,
                "current_session_event_count": current_events, "bounded": True},
        "scan": scan,
        "target_restored_events": restored_target,
        "selected_path": str(selected_path),
    }


def _war_contract(source: dict[str, object], current_probes: object,
                  expected_after: bool) -> dict[str, object]:
    source_probes = _source_probe_contract(source)
    before = _war_pair_summary(source_probes["before"])
    after = _war_pair_summary(source_probes["after"])
    current = _war_pair_summary(current_probes)
    checks = {
        "source_before_complete": before.get("complete") is True,
        "source_after_complete": after.get("complete") is True,
        "reload_complete": current.get("complete") is True,
        "source_before_at_war": before.get("pair_at_war") is True,
        "source_after_matches_decision": after.get("pair_at_war") is expected_after,
        "reload_matches_decision": current.get("pair_at_war") is expected_after,
        "source_reload_war_match": after.get("pair_at_war") == current.get("pair_at_war"),
    }
    return {"checks": checks, "all": all(checks.values()),
            "source_before": before, "source_after": after, "reload": current}


def _control_contract(source: dict[str, object], save_report: dict[str, object],
                      health: dict[str, object], current_control: dict[str, object],
                      probes: object) -> dict[str, object]:
    source_after = source.get("after") if isinstance(source.get("after"), dict) else {}
    source_control = source_after.get("control") if isinstance(source_after, dict) else {}
    save_probe = save_report.get("probe_after") if isinstance(save_report, dict) else {}
    save_signature = save_probe.get("signature") if isinstance(save_probe, dict) else {}
    expected_date = source_control.get("date_raw") if isinstance(source_control, dict) else None
    checks = {
        "source_date_integer": type(expected_date) is int,
        "health_ready": health.get("status") == "ready" and health.get("complete") is True,
        "health_date_matches_source": health.get("date_raw") == expected_date,
        "control_date_matches_source": current_control.get("date_raw") == expected_date,
        "save_probe_date_matches_source": save_signature.get("date_raw") == expected_date,
        "por_player_slot": current_control.get("player_slot") == _PLAYER_SLOT,
        "paused": current_control.get("paused_flag") == 1,
        "four_reload_probes_complete": _snapshots_complete(probes),
    }
    return {"checks": checks, "all": all(checks.values()),
            "source_control": source_control, "save_signature": save_signature,
            "reload_control": current_control}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True,
                        help="新进程 installation.json")
    parser.add_argument("--execution-report", type=Path, required=True,
                        help="已完成 Peace 入站响应 report.json 或其目录")
    parser.add_argument("--save-report", type=Path, required=True,
                        help="对应 save-observer-report-*.json")
    parser.add_argument("--output", type=Path, required=True,
                        help="新的报告文件路径，或新的报告目录")
    args = parser.parse_args(argv)

    report_path: Path | None = None
    evidence: Path | None = None
    report: dict[str, object] = {
        "validator": "validate_peace_inbound_reload.py",
        "version": 1,
        "status": "running",
        "mode": "read_only_peace_inbound_reload",
        "installation": str(args.installation),
        "execution_report": str(args.execution_report),
        "save_report": str(args.save_report),
        "business_submission": False,
        "advance_requested": False,
        "save_requested": False,
        "restart_requested": False,
        "installation_requested": False,
        "checks": {},
    }
    try:
        report_path, evidence = _output_paths(args.output)
        installation = args.installation.expanduser().resolve(strict=True)
        execution_path = _resolve_report(args.execution_report)
        save_report_path = _resolve_report(args.save_report)
        execution = _read_json(execution_path, maximum=_MAX_METADATA_BYTES)
        save_report = _read_json(save_report_path, maximum=_MAX_METADATA_BYTES)
        if not isinstance(execution, dict):
            raise ReloadValidationError("EXECUTION_REPORT_NOT_OBJECT")
        if not isinstance(save_report, dict):
            raise ReloadValidationError("SAVE_REPORT_NOT_OBJECT")

        source = _source_contract(execution)
        source_probes = _source_probe_contract(execution)
        save = _save_contract(save_report)
        report["source"] = {
            "path": str(execution_path),
            "sha256": _hash_file(execution_path, maximum=_MAX_METADATA_BYTES),
            "summary": source,
            "probe_contract": {key: source_probes[key] for key in
                                ("before_complete", "after_complete", "four_probe_names")},
        }
        report["save"] = {
            "path": str(save_report_path),
            "sha256": _hash_file(save_report_path, maximum=_MAX_METADATA_BYTES),
            "summary": save,
        }
        if not source["all"]:
            raise ReloadValidationError("SOURCE_RESPONSE_CONTRACT_FAILED")
        if not save["all"]:
            raise ReloadValidationError("SAVE_REPORT_OR_HASH_CONTRACT_FAILED")
        if evidence is None:
            raise ReloadValidationError("EVIDENCE_PATH_MISSING")

        installation = installation.resolve(strict=True)
        current_binding = _installation_binding(installation)
        report["reload_binding"] = current_binding
        report["build_binding"] = _binding_contract(execution, current_binding)

        session = ObserverSession(installation, game_exe())
        source_session_id = source.get("source_session_id")
        report["session"] = {
            "experiment_id": session.experiment_id,
            "session_id": session.session_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
            "source_session_id": source_session_id,
            "new_process": isinstance(source_session_id, str)
            and session.session_id != source_session_id,
        }
        health = wait_runtime_ready(session, restore_minimized=False)
        probes = _run_snapshots(session, evidence / "probes")
        current_control_snapshot = probes.get("control_state", {}).get("snapshot")
        current_control = _control_summary(current_control_snapshot) \
            if isinstance(current_control_snapshot, dict) else {}
        report["after"] = {
            "health": health,
            "control": current_control,
            "snapshots": {
                name: {key: item.get(key) for key in
                       ("status", "snapshot_path", "snapshot_completeness", "snapshot_sha256")}
                for name, item in probes.items()
            },
        }
        expected_after = source.get("expected_pair_at_war_after") is True
        war = _war_contract(execution, probes, expected_after)
        control = _control_contract(execution, save_report, health, current_control, probes)
        recovery = _stream_recovery_log(
            installation.parent / "control-probe.jsonl",
            session.session_id,
            int(control["source_control"].get("date_raw")),
            evidence,
        )
        binding = report["build_binding"]
        checks = {
            "source_response_contract": source["all"],
            "save_hash_contract": save["all"],
            "new_process_identity": report["session"].get("new_process") is True,
            "same_immutable_dll_and_61_sources": isinstance(binding, dict)
            and binding.get("all") is True,
            "control_boundary": control["all"],
            "war_state_matches_decision": war["all"],
            "native_recovery_summary_and_empty_current_queue": recovery["all"],
            "no_business_replay": report["business_submission"] is False
            and report["advance_requested"] is False
            and report["save_requested"] is False
            and report["restart_requested"] is False
            and report["installation_requested"] is False,
        }
        report["comparisons"] = {
            "control": control,
            "war": war,
            "recovery": recovery,
            "decision": source.get("decision"),
            "historical_catalog_ignored": True,
        }
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except ReloadValidationError as error:
        report["status"] = "failed"
        report["error"] = {"code": str(error)}
    except Exception as error:  # preserve a bounded diagnostic, never replay work
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_PEACE_INBOUND_RELOAD_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if report_path is not None:
            _write_json(report_path, report)
    print(json.dumps({"status": report["status"], "report": str(report_path)
                      if report_path is not None else None}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
