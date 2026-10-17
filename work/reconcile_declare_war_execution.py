"""Reconcile one failed Declare War request from an existing native event slice.

This tool never publishes a request and never talks to the game.  It validates
the raw submission/consequence events through the production bridge readers,
then optionally repairs the exact invalidated journal row caused by the known
double receipt projection bug.  The original runtime report is left untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402


REQUEST_FAILURE = "NATIVE_DECLARE_WAR_SUBMISSION_RECEIPT_INVALID"
SUBMISSION_EVENT = "native_declare_war_submission_result"
EXECUTION_EVENT = "native_declare_war_execution_result"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _event_sha256(event: dict[str, Any]) -> str:
    encoded = json.dumps(
        event, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_bound_events(path: Path, request_id: str, session_id: str) -> tuple[dict, int, dict, int]:
    submission: dict | None = None
    execution: dict | None = None
    submission_line = 0
    execution_line = 0
    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            if len(raw_line) > 1_048_576:
                continue
            try:
                event = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue
            if (not isinstance(event, dict)
                    or event.get("request_id") != request_id
                    or event.get("session_id") != session_id):
                continue
            kind = event.get("event")
            if kind == SUBMISSION_EVENT:
                if submission is not None:
                    raise ValueError("multiple bound Declare War submission events")
                submission = event
                submission_line = line_number
            elif kind == EXECUTION_EVENT:
                if execution is not None:
                    raise ValueError("multiple bound Declare War execution events")
                execution = event
                execution_line = line_number
    if submission is None or execution is None:
        raise ValueError("bound submission and execution events are both required")
    return submission, submission_line, execution, execution_line


def _record_summary(record: Any) -> dict[str, Any]:
    result = record.result if isinstance(record.result, dict) else None
    reason = result.get("reason") if isinstance(result, dict) else None
    return {
        "status": record.status,
        "submitted": record.submitted_at is not None,
        "submission_id_present": record.submission_id is not None,
        "reason_code": reason.get("code") if isinstance(reason, dict) else None,
        "native_receipt_present": record.native_receipt is not None,
        "result_outcome": (
            (result.get("game_outcome", result.get("native_outcome"))
             if isinstance(result, dict) else None)
        ),
    }


def reconcile(artifact: Path, request_id: str, *, apply: bool,
              output: Path | None = None) -> dict[str, Any]:
    report_path = artifact / "report.json"
    events_path = artifact / "native-events-slice.jsonl"
    journal_path = artifact / "diplomacy.sqlite3"
    if not artifact.is_dir() or not report_path.is_file() \
            or not events_path.is_file() or not journal_path.is_file():
        raise FileNotFoundError("artifact must contain report.json, native-events-slice.jsonl and diplomacy.sqlite3")

    with report_path.open(encoding="utf-8") as stream:
        runtime_report = json.load(stream)
    session_info = runtime_report.get("session")
    if not isinstance(session_info, dict):
        raise ValueError("runtime report has no session identity")
    experiment_id = session_info.get("experiment_id")
    session_id = session_info.get("session_id")
    if (not isinstance(experiment_id, str) or not isinstance(session_id, str)
            or not experiment_id or not session_id):
        raise ValueError("runtime report session identity is incomplete")

    events_sha256 = _sha256_file(events_path)
    submission, submission_line, execution, execution_line = _read_bound_events(
        events_path, request_id, session_id)

    journal = DurableJournal(journal_path, experiment_id, session_id)
    try:
        before_record = journal.get_request(request_id)
        if before_record.status not in {"invalidated", "executed"}:
            raise ValueError(
                f"reconciliation requires invalidated or already reconciled status, got {before_record.status!r}"
            )
        if before_record.submission_id is None:
            raise ValueError("reconciliation requires the original submission claim")
        result_json = before_record.result
        reason = result_json.get("reason") if isinstance(result_json, dict) else None
        if (before_record.status == "invalidated"
                and (not isinstance(reason, dict)
                     or reason.get("code") != REQUEST_FAILURE
                     or result_json.get("submitted") is not False)):
            raise ValueError("journal row is not the known receipt-projection failure")
        payload = before_record.payload
        if (not isinstance(payload, dict)
                or payload.get("action_id") != "declare_war"
                or payload.get("actor") != "FRA"
                or payload.get("phase") != "initiate"):
            raise ValueError("journal payload is outside Declare War reconciliation scope")
        parameters = payload.get("parameters")
        date_raw = execution.get("date_raw")
        if not isinstance(parameters, dict):
            raise ValueError("journal Declare War parameters are missing")

        reduced_receipt = ObserverSession._public_native_declare_war_submission_receipt(
            submission, request_id, "FRA", payload.get("recipient"),
            "initiate", date_raw, parameters)
        public_result = ObserverSession._public_native_declare_war_execution_result(
            execution, request_id, session_id, "FRA", payload.get("recipient"),
            "initiate", date_raw, parameters)
        if reduced_receipt is None or public_result is None:
            raise ValueError("production Declare War reader rejected the bound native events")

        before = _record_summary(before_record)
        after_record = before_record
        changed = False
        if apply:
            after_record = journal.reconcile_declare_war_executed(
                request_id,
                public_result,
                reduced_receipt,
                expected_reason_code=REQUEST_FAILURE,
                expected_payload=payload,
                evidence_content={
                    "source_artifact": str(artifact),
                    "source_events_file": str(events_path),
                    "source_events_sha256": events_sha256,
                    "submission_line": submission_line,
                    "execution_line": execution_line,
                    "submission_event_sha256": _event_sha256(submission),
                    "execution_event_sha256": _event_sha256(execution),
                    "reconciled_from": "invalidated",
                },
                event_id="native-declare-war-reconcile:" + request_id,
            )
            changed = before_record.status != after_record.status

        return {
            "tool": "reconcile_declare_war_execution",
            "version": 1,
            "applied": changed,
            "game_write_performed": False,
            "request_id": request_id,
            "experiment_id": experiment_id,
            "session_id": session_id,
            "artifact": str(artifact),
            "journal": str(journal_path),
            "source_events": {
                "path": str(events_path),
                "sha256": events_sha256,
                "submission_line": submission_line,
                "execution_line": execution_line,
                "submission_event_sha256": _event_sha256(submission),
                "execution_event_sha256": _event_sha256(execution),
            },
            "before": before,
            "native_receipt": {
                "submitted": reduced_receipt["submitted"],
                "transport_verified": reduced_receipt["transport_verified"],
                "request_binding_verified": reduced_receipt["request_binding_verified"],
            },
            "native_result": {
                "native_outcome": public_result["native_outcome"],
                "execution_verified": public_result["execution_verified"],
                "request_binding_verified": public_result["request_binding_verified"],
                "war_before": public_result["war_before"],
                "war_after": public_result["war_after"],
                "war_id": public_result["war_id"],
                "war_identity_verified": public_result["war_identity_verified"],
                "stability_before_raw": public_result["stability_before_raw"],
                "stability_after_raw": public_result["stability_after_raw"],
                "stability_verified": public_result["stability_verified"],
            },
            "after": _record_summary(after_record),
        }
    finally:
        journal.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--apply", action="store_true",
                        help="write only the validated reconciliation to the same journal")
    parser.add_argument("--output", type=Path,
                        help="new readback JSON path; never overwrites an existing file")
    args = parser.parse_args()
    output = args.output or (args.artifact / "declare-war-reconciliation-readback.json")
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {output}")
    result = reconcile(args.artifact, args.request_id, apply=args.apply, output=output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({
        "output": str(output),
        "applied": result["applied"],
        "before": result["before"],
        "after": result["after"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
