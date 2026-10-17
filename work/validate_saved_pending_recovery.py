#!/usr/bin/env python3
"""Independently validate a saved native pending Vassalization recovery.

The validator consumes bounded preparation, save-observer, advance and
response artifacts.  It streams the two JSONL evidence files, compares the
original native payload with the restored payload, and verifies the later FRA
decision.  It never starts a game, sends a proposal or response, advances,
saves, or rewrites an existing artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from work.validate_alliance_reload import _hash_file, _read_json, _write_json  # noqa: E402


_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_EVENT_LOG_BYTES = 10 * 1024 * 1024
_MAX_SAVE_BYTES = 256 * 1024 * 1024
_ACTOR = "SAV"
_RECIPIENT = "FRA"
_FAMILY = "vassalization"
_ACTION = "offer_vassalization"
_TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
_OPAQUE_RE = re.compile(r"[0-9a-f]{32}\Z")
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
_PAYLOAD_FIELDS = (
    "actor", "mirror", "recipient", "date28", "date2c", "envoy30",
    "state34", "variant38", "proposal3c", "token3c",
)
_PRIVATE_PUBLIC_FIELDS = (
    "native_proposal_id", "token3c", "date28", "date2c", "envoy30",
    "proposal3c", "session_id", "native_address", "RVA", "rva",
)


class RecoveryValidationError(RuntimeError):
    """A bounded evidence validation failure."""


def _resolve_json(path: Path) -> Path:
    path = path.expanduser().resolve(strict=True)
    if path.is_dir():
        path = (path / "report.json").resolve(strict=True)
    if not path.is_file():
        raise RecoveryValidationError(f"REPORT_NOT_FILE:{path}")
    return path


def _new_output(parent: Path, requested: Path | None) -> Path:
    if requested is not None:
        output = requested.expanduser().resolve()
        if output.exists():
            raise RecoveryValidationError(f"OUTPUT_ALREADY_EXISTS:{output}")
        output.mkdir(parents=True)
        return output
    parent = parent.expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    for _ in range(32):
        output = parent / f"saved-pending-recovery-validation-{uuid.uuid4().hex}"
        try:
            output.mkdir()
            return output
        except FileExistsError:
            continue
    raise RecoveryValidationError("OUTPUT_DIRECTORY_COLLISION")


def _stream_events(path: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Read a bounded JSONL file line by line; never load it as one string."""

    path = path.expanduser().resolve(strict=True)
    size = path.stat().st_size
    if size > _MAX_EVENT_LOG_BYTES:
        raise RecoveryValidationError(f"EVENT_LOG_TOO_LARGE:{path}:{size}")
    events: list[dict[str, object]] = []
    line_count = 0
    invalid_count = 0
    oversized_count = 0
    total = 0
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for raw in stream:
                total += len(raw)
                digest.update(raw)
                line_count += 1
                if len(raw) > 256 * 1024:
                    oversized_count += 1
                    continue
                try:
                    value = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    invalid_count += 1
                    continue
                if isinstance(value, dict):
                    events.append(value)
    except OSError as error:
        raise RecoveryValidationError(f"EVENT_LOG_READ_FAILED:{path}:{type(error).__name__}") from error
    return events, {
        "path": str(path), "bytes": total, "sha256": digest.hexdigest(),
        "line_count": line_count, "json_object_count": len(events),
        "invalid_line_count": invalid_count, "oversized_line_count": oversized_count,
        "bounded": True,
    }


def _event_path(report: dict[str, object], fallback: Path | None = None) -> Path:
    native = report.get("native_events")
    path = native.get("path") if isinstance(native, dict) else None
    if isinstance(path, str) and Path(path).is_file():
        return Path(path)
    if fallback is not None:
        candidate = fallback / "native-events.jsonl"
        if candidate.is_file():
            return candidate
    raise RecoveryValidationError("NATIVE_EVENT_SLICE_NOT_FOUND")


def _find_one(events: list[dict[str, object]], predicate, label: str) -> dict[str, object]:
    matches = [event for event in events if predicate(event)]
    if len(matches) != 1:
        raise RecoveryValidationError(f"{label}_COUNT:{len(matches)}")
    return matches[0]


def _save_evidence(path: Path) -> dict[str, object]:
    data = _read_json(path, maximum=_MAX_METADATA_BYTES)
    if not isinstance(data, dict):
        raise RecoveryValidationError(f"SAVE_REPORT_NOT_OBJECT:{path}")
    save = data.get("save")
    if not isinstance(save, dict):
        raise RecoveryValidationError(f"SAVE_REPORT_ENTRY_MISSING:{path}")
    reported = save.get("sha256")
    result: dict[str, object] = {
        "report_path": str(path),
        "status": data.get("status"),
        "name": data.get("name"),
        "session": data.get("session"),
        "reported_save": {
            "path": save.get("path"),
            "sha256": reported,
            "bytes": save.get("inspection", {}).get("file_size")
            if isinstance(save.get("inspection"), dict) else None,
        },
        "reported_hash_valid": isinstance(reported, str) and _SHA256_RE.fullmatch(reported) is not None,
    }
    save_path = save.get("path")
    if isinstance(save_path, str) and Path(save_path).is_file():
        current = _hash_file(Path(save_path), maximum=_MAX_SAVE_BYTES)
        result["current_hash"] = current
        result["current_hash_matches_report"] = (
            result["reported_hash_valid"] is True
            and current.get("sha256", "").casefold() == str(reported).casefold()
        )
    else:
        result["current_hash"] = None
        result["current_hash_matches_report"] = None
    return result


def _public_proposal_check(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {"object": False, "opaque_id": False, "safe_fields": False}
    proposal_id = value.get("proposal_id")
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    leaked = [field for field in _PRIVATE_PUBLIC_FIELDS if field in value]
    return {
        "object": True,
        "opaque_id": isinstance(proposal_id, str) and _OPAQUE_RE.fullmatch(proposal_id) is not None,
        "safe_fields": not leaked,
        "leaked_fields": leaked,
        "source": value.get("source"),
        "serialized_bytes": len(serialized.encode("utf-8")),
    }


def _payload_compare(source: dict[str, object], restored: dict[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for field in _PAYLOAD_FIELDS:
        fields[field] = {
            "source": source.get(field),
            "restored": restored.get(field),
            "match": source.get(field) == restored.get(field),
        }
    return {"fields": fields, "all_match": all(item["match"] for item in fields.values())}


def _find_advance_report(root: Path) -> Path:
    reports = sorted(root.glob("advance-context-*/report.json"))
    if len(reports) != 1:
        raise RecoveryValidationError(f"ADVANCE_REPORT_COUNT:{len(reports)}")
    return reports[0]


def _response_public_result(response: dict[str, object]) -> dict[str, object] | None:
    value = response.get("native_response_event")
    if isinstance(value, dict):
        return value
    poll = response.get("poll")
    final = poll.get("final") if isinstance(poll, dict) else None
    result = final.get("result") if isinstance(final, dict) else None
    return result if isinstance(result, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-preparation", type=Path, required=True,
                        help="E阶段 vassalization-inbound-preparation report 或目录")
    parser.add_argument("--source-save-report", type=Path, required=True,
                        help="E阶段保存 pending 的 save-observer report")
    parser.add_argument("--recovery-artifact", type=Path, required=True,
                        help="F阶段新进程 artifact 根目录")
    parser.add_argument("--response-artifact", type=Path, required=True,
                        help="F阶段最终 accept response report 或目录")
    parser.add_argument("--advance-artifact", type=Path,
                        help="可选 advance report；省略时从 recovery-artifact 唯一匹配")
    parser.add_argument("--output-dir", type=Path,
                        help="新输出目录；必须尚不存在")
    args = parser.parse_args(argv)

    recovery_root = args.recovery_artifact.expanduser().resolve()
    output: Path | None = None
    report: dict[str, object] = {
        "validator": "validate_saved_pending_recovery.py",
        "version": 1,
        "status": "running",
        "mode": "read_only_saved_native_pending_recovery_validation",
        "source_preparation": str(args.source_preparation),
        "source_save_report": str(args.source_save_report),
        "recovery_artifact": str(recovery_root),
        "response_artifact": str(args.response_artifact),
        "checks": {},
        "execution_requested": False,
        "business_submission": False,
        "advance_requested": False,
        "save_requested": False,
        "restart_requested": False,
        "installation_requested": False,
    }
    try:
        source_path = _resolve_json(args.source_preparation)
        source_report = _read_json(source_path, maximum=_MAX_METADATA_BYTES)
        if not isinstance(source_report, dict):
            raise RecoveryValidationError("SOURCE_PREPARATION_NOT_OBJECT")
        source_save_path = _resolve_json(args.source_save_report)
        source_save_report = _read_json(source_save_path, maximum=_MAX_METADATA_BYTES)
        if not isinstance(source_save_report, dict):
            raise RecoveryValidationError("SOURCE_SAVE_REPORT_NOT_OBJECT")
        response_path = _resolve_json(args.response_artifact)
        response_report = _read_json(response_path, maximum=_MAX_METADATA_BYTES)
        if not isinstance(response_report, dict):
            raise RecoveryValidationError("RESPONSE_REPORT_NOT_OBJECT")
        advance_path = (
            _resolve_json(args.advance_artifact)
            if args.advance_artifact is not None else _find_advance_report(recovery_root)
        )
        advance_report = _read_json(advance_path, maximum=_MAX_METADATA_BYTES)
        if not isinstance(advance_report, dict):
            raise RecoveryValidationError("ADVANCE_REPORT_NOT_OBJECT")
        output = _new_output(recovery_root, args.output_dir)
        report["artifact"] = str(output)

        source_native_path = _event_path(source_report, source_path.parent)
        recovery_log = recovery_root / "control-probe.jsonl"
        if not recovery_log.is_file():
            raise RecoveryValidationError("RECOVERY_CONTROL_LOG_MISSING")
        response_native_path = _event_path(response_report, response_path.parent)
        source_events, source_log_meta = _stream_events(source_native_path)
        recovery_events, recovery_log_meta = _stream_events(recovery_log)
        response_events, response_log_meta = _stream_events(response_native_path)

        source_session = source_report.get("session_id")
        source_event = _find_one(
            source_events,
            lambda event: event.get("event") == "native_alliance_inbound_offer"
            and event.get("action_id") == _ACTION
            and event.get("family") == _FAMILY
            and event.get("actor") == _ACTOR
            and event.get("mirror") == _ACTOR
            and event.get("recipient") == _RECIPIENT
            and event.get("new_entry") is True,
            "SOURCE_ORIGINAL_OFFER",
        )
        restored_event = _find_one(
            recovery_events,
            lambda event: event.get("event") == "native_diplomacy_inbound_pending_restored"
            and event.get("action_id") == _ACTION
            and event.get("family") == _FAMILY
            and event.get("actor") == _ACTOR
            and event.get("mirror") == _ACTOR
            and event.get("recipient") == _RECIPIENT,
            "RESTORED_EVENT",
        )
        restored_session = restored_event.get("session_id")
        response_event = _find_one(
            response_events,
            lambda event: event.get("event") == "native_diplomacy_relation_response_result"
            and event.get("request_id") == response_report.get("request_id")
            and event.get("action_id") == _ACTION
            and event.get("family") == _FAMILY
            and event.get("actor") == _ACTOR
            and event.get("recipient") == _RECIPIENT
            and event.get("phase") == "accept",
            "ACCEPT_RESPONSE_EVENT",
        )
        holds = [event for event in recovery_events
                 if event.get("event") == "native_diplomacy_inbound_ai_choice_held"
                 and event.get("session_id") == restored_session
                 and event.get("proposal_id") == restored_event.get("proposal_id")
                 and event.get("action_id") == _ACTION
                 and event.get("token3c") == restored_event.get("token3c")]
        saved_scans = [event for event in recovery_events
                       if event.get("event") == "native_diplomacy_saved_pending_scan_complete"
                       and event.get("queue_readable") is True
                       and event.get("list_integrity") is True]
        test_submissions = [event for event in recovery_events
                            if event.get("event") == "native_alliance_inbound_test_submitted"
                            and event.get("session_id") == restored_session]
        new_offers = [event for event in recovery_events
                      if event.get("event") == "native_alliance_inbound_offer"
                      and event.get("session_id") == restored_session
                      and event.get("action_id") == _ACTION]
        save_source = _save_evidence(source_save_path)
        recovery_save_paths = sorted(recovery_root.glob("save-observer-report-*.json"))
        recovery_save = _save_evidence(recovery_save_paths[-1]) if recovery_save_paths else None
        source_payload_compare = _payload_compare(source_event, restored_event)
        response_public = _response_public_result(response_report)
        proposal_checks = {
            "source": _public_proposal_check(source_report.get("proposal")),
            "recovered": _public_proposal_check(response_report.get("proposal")),
            "observed_in_response": _public_proposal_check(
                (response_report.get("inspection") or {}).get("observed_inbound_proposal")
                if isinstance(response_report.get("inspection"), dict) else None
            ),
        }
        selector = response_report.get("selector")
        selector_roles = {
            "actor": selector.get("actor") if isinstance(selector, dict) else None,
            "recipient": selector.get("recipient") if isinstance(selector, dict) else None,
            "actor_is_overlord": selector.get("actor_is_overlord") if isinstance(selector, dict) else None,
            "actor_is_subject": selector.get("actor_is_subject") if isinstance(selector, dict) else None,
            "subject_type": selector.get("subject_type") if isinstance(selector, dict) else None,
        }
        report["source_event"] = source_event
        report["restored_event"] = restored_event
        report["response_event"] = response_event
        report["payload_comparison"] = source_payload_compare
        report["saved_pending_scan_events"] = saved_scans
        report["hold_events"] = holds
        report["response_public"] = response_public
        report["public_proposals"] = proposal_checks
        report["selector_roles"] = selector_roles
        report["source_log"] = source_log_meta
        report["recovery_log"] = recovery_log_meta
        report["response_log"] = response_log_meta
        report["save_source"] = save_source
        report["save_recovery"] = recovery_save
        report["advance"] = {
            "path": str(advance_path),
            "status": advance_report.get("status"),
            "before": advance_report.get("before", {}).get("control")
            if isinstance(advance_report.get("before"), dict) else None,
            "after": advance_report.get("after", {}).get("control")
            if isinstance(advance_report.get("after"), dict) else None,
        }
        source_event_date = source_event.get("date_raw", source_event.get("date28"))

        checks: dict[str, bool] = {
            "source_preparation_passed": source_report.get("status") == "passed",
            "source_family_and_direction": source_report.get("family") == _FAMILY
            and source_report.get("action_id") == _ACTION
            and source_report.get("actor") == _ACTOR
            and source_report.get("recipient") == _RECIPIENT,
            "source_original_offer_complete": (
                source_event.get("new_entry") is True
                and source_event.get("call_redirected") is True
                and source_event.get("pending_source") == "native_executor_pending_block"
            ),
            "saved_pending_report_success": source_save_report.get("status") == "success",
            "source_save_hash_recorded": save_source.get("reported_hash_valid") is True,
            "recovery_session_new": isinstance(source_session, str)
            and isinstance(restored_session, str)
            and source_session != restored_session,
            "restored_session_matches_response": restored_session == response_event.get("session_id")
            and restored_session == response_report.get("session_id"),
            "restored_event_contract": (
                restored_event.get("pending_source") == "native_saved_pending_queue"
                and restored_event.get("source_verified") is True
                and restored_event.get("queue_readable") is True
                and restored_event.get("list_integrity") is True
                and restored_event.get("payload_readable") is True
                and restored_event.get("decision_country_verified") is True
                and restored_event.get("decision_country") == _RECIPIENT
                and restored_event.get("saved_queue_restored") is True
                and restored_event.get("native_queue_membership_verified") is True
                and restored_event.get("new_entry") is False
                and restored_event.get("call_redirected") is False
                and restored_event.get("state34") == 0
                and restored_event.get("variant38") == 1
                and restored_event.get("extra60") == 0
                and restored_event.get("phase") == "initiate"
                and type(restored_event.get("proposal_id")) is int
                and restored_event.get("proposal_id") > 0
            ),
            "restored_queue_count_one": restored_event.get("queue_after_count") == 1,
            "saved_pending_scan_complete": bool(saved_scans),
            "payload_fields_preserved": source_payload_compare["all_match"],
            "restored_date_is_later_than_source": (
                isinstance(source_event_date, int)
                and isinstance(restored_event.get("date_raw"), int)
                and restored_event.get("date_raw") > source_event_date
            ),
            "cross_day_hold_observed": any(
                isinstance(event.get("date_raw"), int)
                and event.get("date_raw") > restored_event.get("date_raw")
                for event in holds
            ),
            "advance_completed_paused": (
                advance_report.get("status") == "completed"
                and isinstance(advance_report.get("after"), dict)
                and advance_report["after"].get("control", {}).get("paused_flag") == 1
            ),
            "accept_response_contract": (
                response_report.get("status") == "passed"
                and response_event.get("native_state") == 2
                and response_event.get("native_variant") == 1
                and response_event.get("pending_removed") is True
                and response_event.get("vassalization_before") is False
                and response_event.get("vassalization_after") is True
                and response_event.get("response_verified") is True
                and response_event.get("request_binding_verified") is True
            ),
            "fra_is_subject": (
                selector_roles == {
                    "actor": "FRA", "recipient": "SAV",
                    "actor_is_overlord": False, "actor_is_subject": True,
                    "subject_type": "vassal",
                }
            ),
            "no_retest_source_or_second_offer": response_report.get("test_source") is False
            and not test_submissions and not new_offers,
            "public_opaque_and_safe": all(
                item.get("object") is True
                and item.get("opaque_id") is True
                and item.get("safe_fields") is True
                for item in proposal_checks.values()
            ) and response_report.get("proposal", {}).get("source") == "saved_native_pending",
            "save_recovery_report_present": (
                isinstance(recovery_save, dict)
                and recovery_save.get("reported_hash_valid") is True
            ),
            "no_business_replay": not report["business_submission"]
            and not report["execution_requested"]
            and not report["advance_requested"]
            and not report["save_requested"]
            and not report["restart_requested"]
            and not report["installation_requested"],
        }
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
    except RecoveryValidationError as error:
        report["status"] = "failed"
        report["error"] = {"code": str(error)}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"code": "UNEXPECTED_SAVED_PENDING_RECOVERY_ERROR",
                            "type": type(error).__name__, "message": str(error)}
    finally:
        if output is None:
            try:
                output = _new_output(recovery_root, args.output_dir)
                report["artifact"] = str(output)
            except Exception:
                output = None
        if output is not None:
            _write_json(output / "report.json", report)
            lines = [
                "# 保存队列恢复独立验收",
                "",
                f"状态：`{report.get('status')}`",
                f"原始提议：`{source_path if 'source_path' in locals() else args.source_preparation}`",
                f"恢复进程：`{recovery_root}`",
                "",
            ]
            checks = report.get("checks")
            if isinstance(checks, dict):
                lines.append("## 检查结果")
                lines.extend(f"- `{key}`：`{'PASS' if value is True else 'FAIL'}`"
                             for key, value in checks.items())
            (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "artifact": report.get("artifact")}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
