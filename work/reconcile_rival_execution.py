"""只读回收一次已被消费端误判的 Rival 原生执行结果。

脚本读取既有执行 artifact 的 ``report.json``、有界 native 日志切片和
SQLite journal。脚本不创建执行请求、不调用游戏进程、不重发 native wire。
只有以下条件全部成立时，脚本才通过 journal 的受限审计接口把同一请求从
``invalidated`` 修正为 ``executed``：

* submission receipt 和 execution result 都精确绑定原 session/request/action；
* receipt 使用实际字段 ``native_origin``、``native_flags``、
  ``native_sequence``，并通过 Rival validator；
* execution result 通过状态、数量、外交点数和关系转换校验；
* journal 原记录的 invalidation code 精确为
  ``NATIVE_RIVAL_SUBMISSION_RESULT_INVALID``。

原 invalidation evidence 不会被删除；回收过程追加一条独立
``native_rival_reconciliation`` evidence。重复运行只会读取同一已执行记录，
不会追加提交或重复证据。

示例::

    python work/reconcile_rival_execution.py \
        --artifact work/runtime/diplomacy-query-20261016-r34-rival-f-mature/\
        rival-execution-aef36c01513746ebb7b025d64c64f657
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from work.run_alliance_execution import _write_json  # noqa: E402
from work.run_improve_relations_execution import _new_artifact  # noqa: E402


_MAX_METADATA_BYTES = 8 * 1024 * 1024
_MAX_LOG_LINE_BYTES = 256 * 1024
_ACTOR = "FRA"
_FAMILY = "rival"
_PHASE = "initiate"
_EXPECTED_REASON = "NATIVE_RIVAL_SUBMISSION_RESULT_INVALID"
_RECONCILE_EVENT_PREFIX = "native-rival-reconcile:"


class ReconcileStop(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _read_json(path: Path) -> object:
    if not path.is_file():
        raise ReconcileStop("FILE_MISSING", str(path))
    if path.stat().st_size > _MAX_METADATA_BYTES:
        raise ReconcileStop("METADATA_TOO_LARGE", str(path))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReconcileStop("JSON_READ_FAILED", f"{path}:{type(error).__name__}") from error


def _sha256_bounded(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_METADATA_BYTES:
                    raise ReconcileStop("NATIVE_SLICE_TOO_LARGE", str(path))
                digest.update(chunk)
    except OSError as error:
        raise ReconcileStop("NATIVE_SLICE_READ_FAILED", str(error)) from error
    return digest.hexdigest(), total


def _read_native_events(
    path: Path,
    *,
    request_id: str,
    session_id: str,
    action_id: str,
    recipient: str,
    date_raw: int,
) -> dict[str, object]:
    """Read only the bounded slice and reject same-request cross-family events."""

    if not path.is_file():
        raise ReconcileStop("NATIVE_SLICE_MISSING", str(path))
    if path.stat().st_size > _MAX_METADATA_BYTES:
        raise ReconcileStop("NATIVE_SLICE_TOO_LARGE", str(path))
    events: dict[str, list[dict[str, object]]] = {
        "native_rival_submission_result": [],
        "native_rival_execution_result": [],
    }
    mismatches: list[dict[str, object]] = []
    line_count = 0
    with path.open("rb") as stream:
        for raw_line in stream:
            line_count += 1
            if len(raw_line) > _MAX_LOG_LINE_BYTES:
                raise ReconcileStop("NATIVE_EVENT_LINE_TOO_LARGE", str(line_count))
            try:
                event = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(event, dict):
                continue
            event_name = event.get("event")
            if event_name not in events or event.get("request_id") != request_id:
                continue
            expected = {
                "session_id": session_id,
                "action_id": action_id,
                "family": _FAMILY,
                "actor": _ACTOR,
                "recipient": recipient,
                "phase": _PHASE,
                "date_raw": date_raw,
            }
            if any(event.get(key) != value for key, value in expected.items()):
                mismatches.append({
                    "event": event_name,
                    "session_id": event.get("session_id"),
                    "action_id": event.get("action_id"),
                    "family": event.get("family"),
                    "actor": event.get("actor"),
                    "recipient": event.get("recipient"),
                    "phase": event.get("phase"),
                    "date_raw": event.get("date_raw"),
                })
                continue
            events[event_name].append(event)
    if mismatches:
        raise ReconcileStop("NATIVE_EVENT_BINDING_MISMATCH", json.dumps(mismatches, ensure_ascii=False))
    return {
        "line_count": line_count,
        "submission_count": len(events["native_rival_submission_result"]),
        "execution_count": len(events["native_rival_execution_result"]),
        "submission": events["native_rival_submission_result"],
        "execution": events["native_rival_execution_result"],
    }


def _safe_record(record: object) -> dict[str, object]:
    payload = getattr(record, "payload", None)
    result = getattr(record, "result", None)
    receipt = getattr(record, "native_receipt", None)
    return {
        "request_id": getattr(record, "request_id", None),
        "status": getattr(record, "status", None),
        "submitted": getattr(record, "submitted_at", None) is not None,
        "payload": payload,
        "result": result,
        "native_receipt": receipt,
        "evidence_count": getattr(record, "evidence_count", None),
        "last_evidence_type": getattr(record, "last_evidence_type", None),
        "last_evidence_layer": getattr(record, "last_evidence_layer", None),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True,
                        help="原始 Rival 执行 artifact 目录；不会改写其中 report/events")
    parser.add_argument("--output", type=Path,
                        help="可选的新 readback 输出目录，必须尚不存在")
    args = parser.parse_args(argv)

    source_artifact = args.artifact.expanduser().resolve(strict=True)
    output = (
        args.output.expanduser().resolve()
        if args.output is not None
        else _new_artifact(source_artifact.parent, "rival-reconcile")
    )
    if args.output is not None:
        output.mkdir(parents=True, exist_ok=False)
    report: dict[str, object] = {
        "status": "running",
        "mode": "read_only_native_rival_reconcile",
        "source_artifact": str(source_artifact),
        "artifact": str(output),
        "execute_call_count": 0,
        "native_publish_count": 0,
        "resubmission_count": 0,
        "source_report_unchanged": True,
        "checks": {},
    }
    try:
        source_report_path = source_artifact / "report.json"
        source_report = _read_json(source_report_path)
        if not isinstance(source_report, dict):
            raise ReconcileStop("SOURCE_REPORT_INVALID", "report is not an object")
        report["source_report"] = {
            "path": str(source_report_path),
            "status": source_report.get("status"),
            "sha256": _sha256_bounded(source_report_path)[0],
        }
        request_id = source_report.get("request_id")
        action_id = source_report.get("action_id")
        recipient = source_report.get("recipient")
        expected_date = source_report.get("expected_date_raw")
        session_info = source_report.get("session")
        if (
            source_report.get("status") != "invalidated"
            or not isinstance(request_id, str)
            or not isinstance(action_id, str)
            or action_id not in ("set_rival", "remove_rival")
            or not isinstance(recipient, str)
            or not isinstance(expected_date, int)
            or isinstance(expected_date, bool)
            or not isinstance(session_info, dict)
            or not isinstance(session_info.get("experiment_id"), str)
            or not isinstance(session_info.get("session_id"), str)
        ):
            raise ReconcileStop("SOURCE_REQUEST_NOT_RECONCILABLE", "source report is not the expected invalidated Rival request")
        session_id = session_info["session_id"]
        experiment_id = session_info["experiment_id"]
        report["request_id"] = request_id
        report["action_id"] = action_id
        report["recipient"] = recipient
        private_meta = source_report.get("private_native_slice")
        slice_path = source_artifact / "native-events-slice.jsonl"
        recorded_slice_sha = None
        if isinstance(private_meta, dict):
            recorded_slice_sha = private_meta.get("sha256")
            candidate = private_meta.get("path")
            if isinstance(candidate, str):
                candidate_path = Path(candidate).expanduser().resolve()
                try:
                    candidate_path.relative_to(source_artifact)
                except ValueError as error:
                    raise ReconcileStop("NATIVE_SLICE_OUTSIDE_ARTIFACT", candidate) from error
                slice_path = candidate_path
        actual_slice_sha, slice_bytes = _sha256_bounded(slice_path)
        if not isinstance(recorded_slice_sha, str) or actual_slice_sha != recorded_slice_sha:
            raise ReconcileStop("NATIVE_SLICE_HASH_MISMATCH", str(slice_path))
        report["native_slice"] = {
            "path": str(slice_path),
            "bytes": slice_bytes,
            "sha256": actual_slice_sha,
            "private": True,
        }
        native = _read_native_events(
            slice_path,
            request_id=request_id,
            session_id=session_id,
            action_id=action_id,
            recipient=recipient,
            date_raw=expected_date,
        )
        if native["submission_count"] != 1 or native["execution_count"] != 1:
            raise ReconcileStop("NATIVE_EVENT_CARDINALITY_INVALID", json.dumps({
                "submission_count": native["submission_count"],
                "execution_count": native["execution_count"],
            }))
        raw_submission = native["submission"][0]
        raw_execution = native["execution"][0]
        if not ObserverSession._valid_native_rival_submission_result(
                raw_submission, request_id, session_id, _ACTOR, recipient,
                _PHASE, expected_date, action_id):
            raise ReconcileStop("NATIVE_RIVAL_SUBMISSION_INVALID", "actual receipt failed strict Rival validation")
        receipt = ObserverSession._public_native_rival_submission_receipt(
            raw_submission, request_id, _ACTOR, recipient, _PHASE,
            expected_date, action_id)
        result = ObserverSession._public_native_rival_execution_result(
            raw_execution, request_id, session_id, _ACTOR, recipient,
            _PHASE, expected_date, action_id)
        if receipt is None or result is None or result.get("status") != "executed":
            raise ReconcileStop("NATIVE_RIVAL_EXECUTION_INVALID", "actual execution failed strict Rival validation")
        report["native_events"] = {
            "submission_private_fields_present": sorted(
                key for key in ("native_origin", "native_flags", "native_sequence")
                if key in raw_submission
            ),
            "submission": receipt,
            "execution": result,
        }

        journal_path = source_artifact / "diplomacy.sqlite3"
        if not journal_path.is_file():
            raise ReconcileStop("JOURNAL_MISSING", str(journal_path))
        payload_expected = {
            "action_id": action_id,
            "actor": _ACTOR,
            "recipient": recipient,
            "phase": _PHASE,
            "parameters": {},
        }
        with DurableJournal(
            journal_path, experiment_id, session_id, global_request_ids=True
        ) as journal:
            before_record = journal.get_request(request_id)
            if before_record.payload != payload_expected:
                raise ReconcileStop("JOURNAL_PAYLOAD_MISMATCH", "durable request differs from source binding")
            if before_record.status not in ("invalidated", "executed"):
                raise ReconcileStop("JOURNAL_STATUS_NOT_RECONCILABLE", before_record.status)
            prior_evidence = journal.list_evidence_for_record(before_record)
            prior_types = [item.evidence_type for item in prior_evidence]
            reconcile_content = {
                "source_artifact": str(source_artifact),
                "native_slice_sha256": actual_slice_sha,
                "original_status": before_record.status,
                "original_reason_code": _EXPECTED_REASON,
                "native_receipt": receipt,
                "native_response": result,
            }
            reconciled = journal.reconcile_executed(
                request_id,
                result,
                receipt,
                expected_reason_code=_EXPECTED_REASON,
                expected_payload=payload_expected,
                evidence_content=reconcile_content,
                event_id=_RECONCILE_EVENT_PREFIX + request_id,
            )
            after_record = journal.get_request(request_id)
            evidence = journal.list_evidence_for_record(after_record)
        report["journal"] = {
            "path": str(journal_path),
            "before": _safe_record(before_record),
            "after": _safe_record(after_record),
            "prior_evidence_types": prior_types,
            "evidence_types": [item.evidence_type for item in evidence],
        }
        report["checks"] = {
            "source_report_was_invalidated": source_report.get("status") == "invalidated",
            "native_receipt_strictly_valid": True,
            "native_execution_strictly_valid": True,
            "native_private_header_fields_present": sorted(
                key for key in ("native_origin", "native_flags", "native_sequence")
                if key in raw_submission
            ) == ["native_flags", "native_origin", "native_sequence"],
            "old_failure_evidence_preserved": "native_submission_failure" in prior_types,
            "reconciliation_evidence_added": (
                "native_rival_reconciliation" in [item.evidence_type for item in evidence]
            ),
            "journal_now_executed": after_record.status == "executed",
            "no_execute_or_publish": (
                report["execute_call_count"] == 0
                and report["native_publish_count"] == 0
                and report["resubmission_count"] == 0
            ),
        }
        report["status"] = "passed" if all(
            value is True for value in report["checks"].values()
        ) else "failed"
    except ReconcileStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_RECONCILE_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    _write_json(output / "readback-report.json", report)
    print(json.dumps({
        "status": report["status"],
        "artifact": str(output),
        "request_id": report.get("request_id", None),
        "execute_call_count": report["execute_call_count"],
        "native_publish_count": report["native_publish_count"],
    }, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
