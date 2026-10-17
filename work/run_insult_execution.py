"""Execute or resume one bounded, one-sided Insult operation.

``send_insult`` uses empty parameters and the native selector ``-1``.
``scornful_insult`` requires one explicit nonnegative ``--insult-id``.
The operator records native before/after insult state, opinion modifier and
prestige fields, performs one same-request idempotency read after a terminal
result, and verifies the DurableJournal result after SQLite reopen.  It does
not advance the game, save, install a module, or replay a nonterminal request.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession  # noqa: E402
from bridge.diplomacy_journal import DurableJournal  # noqa: E402
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import (  # noqa: E402
    _POLL_SECONDS,
    _copy_log_slice,
    _stable_result,
    _write_json,
)
from work.run_improve_relations_execution import _new_artifact  # noqa: E402
from work.run_insult_queries import (  # noqa: E402
    _query_insult_set,
    _query_set_summary,
)
from work.run_royal_marriage_execution import (  # noqa: E402
    ExperimentStop,
    _installation_binding,
    _poll_royal_result,
    _public_probe_records,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _diplomat_semantics,
    _read_json,
    _run_snapshots,
)


_ACTOR = "FRA"
_PLAYER_SLOT = 189
_DEFAULT_DATE_RAW = 56463768
_ACTIONS = ("send_insult", "scornful_insult")
_FAMILY = "insult"
_TERMINAL_STATUSES = frozenset(
    ("accepted", "rejected", "executed", "invalidated", "expired", "conflict")
)
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_EFFECT_FIELDS = (
    "opinion_modifier_before_raw", "opinion_modifier_after_raw",
    "prestige_before_raw", "prestige_after_raw",
)
_SUBMISSION_EVENT = "native_alliance_submission_result"
_EXECUTION_EVENT = "native_diplomacy_insult_execution_result"


def _empty_result_checks() -> dict[str, object]:
    return {
        "status": False, "binding": False, "transition": False,
        "native": False, "effects": False, "proof": False,
        "event": False, "all": False,
    }


def _strict_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _selected_id(action_id: str, insult_id: int | None) -> int:
    return -1 if action_id == "send_insult" else int(insult_id)


def _query_active(summary: object, action_id: str, selected_id: int) -> object:
    if not isinstance(summary, dict):
        return None
    shape = summary.get("send") if action_id == "send_insult" else summary.get("scornful")
    return shape.get("insult_active") if isinstance(shape, dict) else None


def _action_query_complete(summary: object, action_id: str) -> bool:
    """Return completeness for the action being executed, not its sibling."""

    if not isinstance(summary, dict):
        return False
    shape = summary.get("send" if action_id == "send_insult" else "scornful")
    return isinstance(shape, dict) and shape.get("complete") is True


def _scan_submission_log(path: Path | None, request_id: str,
                         action_id: str, recipient: str,
                         expected_date_raw: int) -> dict[str, object]:
    """Read bounded JSONL evidence for this request from a copied log slice."""

    result: dict[str, object] = {
        "available": False,
        "path": str(path) if path is not None else None,
        "submission_event": None,
        "execution_event": None,
        "submitted": None,
        "status": "unknown",
    }
    if path is None or not path.is_file():
        return result
    result["available"] = True
    try:
        with path.open("rb") as handle:
            for raw_line in handle:
                if len(raw_line) > 4 * 1024 * 1024:
                    continue
                try:
                    event = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(event, dict):
                    continue
                if (
                    event.get("request_id") != request_id
                    or event.get("action_id") != action_id
                    or event.get("recipient") != recipient
                    or event.get("date_raw") != expected_date_raw
                ):
                    continue
                event_name = event.get("event")
                if event_name == _SUBMISSION_EVENT:
                    result["submission_event"] = event
                elif event_name == _EXECUTION_EVENT:
                    result["execution_event"] = event
    except OSError as error:
        result["status"] = "unknown"
        result["error"] = str(error)
        return result
    submission = result.get("submission_event")
    if isinstance(submission, dict) and type(submission.get("submitted")) is bool:
        result["submitted"] = submission["submitted"]
        result["status"] = "submitted" if submission["submitted"] else "not_submitted"
    return result


def _read_journal_submission(path: Path, report: dict[str, object]) -> dict[str, object]:
    """Read the request receipt without changing the existing journal record."""

    result: dict[str, object] = {
        "available": False,
        "submitted": None,
        "status": "unknown",
        "request": None,
    }
    session = report.get("session")
    request_id = report.get("request_id")
    if (
        not path.is_file()
        or not isinstance(session, dict)
        or not isinstance(session.get("experiment_id"), str)
        or not isinstance(session.get("session_id"), str)
        or not isinstance(request_id, str)
    ):
        return result
    try:
        with DurableJournal(
            path, session["experiment_id"], session["session_id"],
            global_request_ids=True,
        ) as journal:
            record = journal.get_request(request_id)
        result["available"] = True
        result["request"] = {
            "status": record.status,
            "submitted_at": record.submitted_at,
            "native_receipt": record.native_receipt,
            "result": record.result,
        }
        receipt = record.native_receipt
        if isinstance(receipt, dict) and type(receipt.get("submitted")) is bool:
            result["submitted"] = receipt["submitted"]
        elif record.submitted_at is not None:
            # A durable submitted timestamp is evidence of the hand-off even
            # when an old journal did not persist the receipt body.
            result["submitted"] = True
        if result["submitted"] is True:
            result["status"] = "submitted"
        elif result["submitted"] is False:
            result["status"] = "not_submitted"
    except Exception as error:
        result["error"] = {
            "type": type(error).__name__, "message": str(error),
        }
    return result


def _submission_observation(report: dict[str, object], native_meta: object,
                            artifact: Path, action_id: str,
                            recipient: str, expected_date_raw: int) -> dict[str, object]:
    """Combine native JSONL and SQLite evidence after any API exception."""

    log_path = None
    if isinstance(native_meta, dict) and isinstance(native_meta.get("path"), str):
        log_path = Path(native_meta["path"])
    log_evidence = _scan_submission_log(
        log_path, str(report.get("request_id")), action_id, recipient,
        expected_date_raw,
    )
    journal_evidence = _read_journal_submission(artifact / "diplomacy.sqlite3", report)
    values = [
        source.get("submitted")
        for source in (log_evidence, journal_evidence)
        if type(source.get("submitted")) is bool
    ]
    submitted: bool | None
    if True in values:
        submitted = True
    elif False in values:
        submitted = False
    else:
        submitted = None
    return {
        "submitted": submitted,
        "status": (
            "submitted" if submitted is True
            else "not_submitted" if submitted is False
            else "unknown"
        ),
        "source": "native_events_slice_or_durable_journal",
        "native_log": log_evidence,
        "durable_journal": journal_evidence,
    }


def _result_matches(action_id: str, recipient: str, expected_date_raw: int,
                    insult_id: int, before_summary: object,
                    after_summary: object, result: object) -> dict[str, object]:
    checks = _empty_result_checks()
    if action_id not in _ACTIONS or not isinstance(result, dict):
        return checks
    public = result.get("result")
    if not isinstance(public, dict):
        return checks
    expected_id = _selected_id(action_id, insult_id)
    checks["status"] = (
        result.get("status") == "executed"
        and result.get("game_outcome") == "executed"
    )
    checks["binding"] = all(public.get(field) == expected for field, expected in (
        ("action_id", action_id), ("actor", _ACTOR),
        ("recipient", recipient), ("phase", "initiate"),
        ("date_raw", expected_date_raw), ("family", _FAMILY),
        ("insult_id", expected_id),
    ))
    checks["transition"] = (
        public.get("insult_before") is False
        and public.get("insult_after") is True
        and _query_active(before_summary, action_id, expected_id) is False
        and _query_active(after_summary, action_id, expected_id) is True
    )
    checks["native"] = (
        _strict_int(public.get("native_state"))
        and public.get("native_state") == 0
        and _strict_int(public.get("native_variant"))
        and public.get("native_variant") == 1
        and public.get("outcome") == "executed"
    )
    checks["effects"] = all(_strict_int(public.get(field)) for field in _EFFECT_FIELDS)
    checks["proof"] = (
        public.get("execution_verified") is True
        and public.get("request_binding_verified") is True
    )
    checks["event"] = public.get("event") == (
        "native_diplomacy_insult_execution_result"
    )
    checks["all"] = all(checks[key] for key in (
        "status", "binding", "transition", "native", "effects", "proof", "event"
    ))
    checks["public_result"] = public
    return checks


def _diplomat_record(probes: dict[str, dict[str, object]]) -> dict[str, object]:
    item = probes.get("diplomats", {})
    snapshot = item.get("snapshot") if isinstance(item, dict) else None
    try:
        semantics = _diplomat_semantics(snapshot) if isinstance(snapshot, dict) else None
        semantics_error = None
    except Exception as error:
        semantics = None
        semantics_error = {"type": type(error).__name__, "message": str(error)}
    return {
        "snapshot": snapshot,
        "semantics": semantics,
        "semantics_error": semantics_error,
        "snapshot_path": item.get("snapshot_path") if isinstance(item, dict) else None,
        "snapshot_completeness": (
            item.get("snapshot_completeness") if isinstance(item, dict) else None
        ),
    }


def _baseline(health: dict[str, object], control: dict[str, object],
              probes: dict[str, dict[str, object]],
              summary: dict[str, object], expected_date_raw: int,
              capabilities: set[str] | list[str],
              *, action_id: str = "send_insult", expected_active: bool,
              require_submission_ack: bool) -> dict[str, object]:
    action_shape = summary.get("send" if action_id == "send_insult" else "scornful")
    if not isinstance(action_shape, dict):
        action_shape = {}
    return {
        "health_ready": health.get("status") == "ready"
        and health.get("complete") is True,
        "health_date_matches_expected": health.get("date_raw") == expected_date_raw,
        "date_matches_expected": control.get("date_raw") == expected_date_raw,
        "player_slot_is_por": control.get("player_slot") == _PLAYER_SLOT,
        "paused": control.get("paused_flag") == 1,
        "four_snapshots_complete": _snapshots_complete(probes),
        "query_set_complete": action_shape.get("complete") is True,
        "insult_active_matches_expected": (
            action_shape.get("insult_active") is expected_active
        ),
        "native_insult_query_ack": "native_insult_query" in capabilities,
        "native_insult_submission_ack": (
            not require_submission_ack
            or "native_insult_submission" in capabilities
        ),
    }


def _parameters_for(action_id: str, insult_id: int) -> dict[str, int]:
    return {} if action_id == "send_insult" else {"insult_id": insult_id}


def _resume_existing_artifact(resume_artifact: Path,
                              explicit_installation: Path | None,
                              expected_date_override: int | None) -> int:
    """Read an existing Insult journal without publishing a new request."""

    resume_artifact = resume_artifact.expanduser().resolve(strict=True)
    original = _read_json(resume_artifact / "report.json")
    if not isinstance(original, dict):
        raise ExperimentStop("RESUME_REPORT_INVALID", "source report is not an object")
    installation_record = original.get("installation")
    recorded_path = (
        installation_record.get("path")
        if isinstance(installation_record, dict) else None
    )
    installation = (
        explicit_installation.expanduser().resolve(strict=True)
        if explicit_installation is not None else
        Path(recorded_path).expanduser().resolve(strict=True)
        if isinstance(recorded_path, str) else None
    )
    action_id = original.get("action_id")
    recipient = original.get("recipient")
    request_id = original.get("request_id")
    expected_date_raw = (
        expected_date_override if expected_date_override is not None
        else original.get("expected_date_raw", _DEFAULT_DATE_RAW)
    )
    insult_id = original.get("insult_id")
    selected_query_id = insult_id if action_id == "scornful_insult" else None
    if action_id == "send_insult":
        valid_id = insult_id == -1
    else:
        valid_id = _strict_int(insult_id) and 0 <= insult_id <= 2147483647
    if (
        installation is None or action_id not in _ACTIONS
        or not isinstance(recipient, str) or not _TAG_RE.fullmatch(recipient)
        or not isinstance(request_id, str) or not _REQUEST_ID_RE.fullmatch(request_id)
        or not _strict_int(expected_date_raw) or not valid_id
    ):
        raise ExperimentStop("RESUME_ARGUMENTS_INVALID", "source report lacks a valid Insult request")

    output = _new_artifact(resume_artifact.parent, "insult-resume")
    log_path = installation.parent / "control-probe.jsonl"
    native_meta = original.get("native_events")
    log_start = native_meta.get("start_offset") if isinstance(native_meta, dict) else None
    report: dict[str, object] = {
        "validator": "run_insult_execution.py",
        "status": "unknown",
        "mode": "resume_read_only",
        "resume_artifact": str(resume_artifact),
        "artifact": str(output),
        "action_id": action_id,
        "actor": _ACTOR,
        "recipient": recipient,
        "family": _FAMILY,
        "phase": "initiate",
        "insult_id": insult_id,
        "parameters": _parameters_for(action_id, insult_id),
        "request_id": request_id,
        "expected_outcome": "executed",
        "expected_date_raw": expected_date_raw,
        "execute_call_count": 0,
        "execute_call_started": False,
        "idempotency_call_count": 0,
        "checks": {},
    }
    try:
        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session"] = {
            "session_id": session.session_id,
            "experiment_id": session.experiment_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        if isinstance(report.get("build_binding"), dict):
            report["build_binding"]["loaded_dll_sha256"] = session.record.get("dll_sha256")
        health = wait_runtime_ready(session, restore_minimized=True)
        after_probes = _run_snapshots(session, output / "after" / "probes")
        after_control = _control_summary(after_probes["control_state"]["snapshot"])
        with DurableJournal(
            resume_artifact / "diplomacy.sqlite3", session.experiment_id,
            session.session_id, global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            first_result = api.get_diplomatic_result(request_id)
            after_queries = _query_insult_set(
                api, recipient, output / "after" / "queries", selected_query_id
            )
            final = api.get_diplomatic_result(request_id)
        with DurableJournal(
            resume_artifact / "diplomacy.sqlite3", session.experiment_id,
            session.session_id, global_request_ids=True,
        ) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(request_id)
        before = original.get("before") if isinstance(original.get("before"), dict) else {}
        before_summary = before.get("query_summary") if isinstance(before.get("query_summary"), dict) else {}
        after_summary = _query_set_summary(after_queries, selected_query_id)
        result_checks = _result_matches(
            action_id, recipient, expected_date_raw, insult_id,
            before_summary, after_summary, final,
        )
        stable = _stable_result(final)
        reopened_stable = _stable_result(reopened_result)
        terminal = isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES
        report.update({
            "source_report": {"path": str(resume_artifact), "status": original.get("status")},
            "first_result": first_result,
            "final_result": final,
            "reopened_result": reopened_result,
            "after": {
                "health": session.health(),
                "control": after_control,
                "queries": after_queries,
                "query_summary": after_summary,
                "diplomat": _diplomat_record(after_probes),
                "probes": _public_probe_records(after_probes),
            },
            "result_checks": result_checks,
            "persistence": {
                "stable_result": stable,
                "reopened_stable_result": reopened_stable,
                "same_public_result": stable == reopened_stable,
            },
        })
        checks = {
            "no_new_execute_submission": report["execute_call_count"] == 0,
            "health_ready": health.get("status") == "ready" and health.get("complete") is True,
            "date_matches_expected": after_control.get("date_raw") == expected_date_raw,
            "player_slot_is_por": after_control.get("player_slot") == _PLAYER_SLOT,
            "paused": after_control.get("paused_flag") == 1,
            "four_snapshots_after": _snapshots_complete(after_probes),
            "query_set_complete": _action_query_complete(after_summary, action_id),
            "journal_survives_reopen": stable == reopened_stable,
            "build_dll_source_bound": report.get("build_binding", {}).get(
                "installation_matches_build_manifest") is True,
        }
        if terminal:
            checks["expected_terminal_result"] = result_checks.get("all") is True
            report["status"] = "passed" if all(checks.values()) else "failed"
        else:
            report["status"] = "pending" if all(checks.values()) else "failed"
        report["checks"] = checks
    except ExperimentStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"code": "UNEXPECTED_RESUME_ERROR",
                            "type": type(error).__name__, "message": str(error)}
    finally:
        native_meta = None
        if _strict_int(log_start) and log_start >= 0:
            native_meta = _copy_log_slice(
                log_path, log_start, output / "native-events-slice.jsonl"
            )
            report["native_events"] = native_meta
        report["submission_observation"] = _submission_observation(
            report, native_meta, resume_artifact / "diplomacy.sqlite3",
            action_id, recipient, expected_date_raw,
        )
        _write_json(output / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(output)},
                     ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 3 if report["status"] == "pending" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path)
    parser.add_argument("--action-id", choices=_ACTIONS)
    parser.add_argument("--recipient")
    parser.add_argument("--request-id")
    parser.add_argument("--expected-outcome", choices=("executed",), default="executed")
    parser.add_argument("--expected-date-raw", type=int, default=None)
    parser.add_argument("--insult-id", type=int)
    parser.add_argument("--resume-artifact", type=Path)
    args = parser.parse_args(argv)

    if args.resume_artifact is not None:
        try:
            return _resume_existing_artifact(
                args.resume_artifact, args.installation, args.expected_date_raw
            )
        except ExperimentStop as error:
            print(json.dumps({"status": "failed", "error": {
                "code": error.code, "message": error.message,
            }}, ensure_ascii=False), flush=True)
            return 2
        except Exception as error:
            print(json.dumps({"status": "failed", "error": {
                "code": "UNEXPECTED_RESUME_ERROR",
                "type": type(error).__name__, "message": str(error),
            }}, ensure_ascii=False), flush=True)
            return 2

    required = ("installation", "action_id", "recipient", "request_id")
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join(
            "--" + name.replace("_", "-") for name in missing
        ))
    if args.expected_date_raw is None:
        args.expected_date_raw = _DEFAULT_DATE_RAW
    installation = args.installation.expanduser().resolve()
    artifact = _new_artifact(installation.parent, "insult-execution")
    log_path = installation.parent / "control-probe.jsonl"
    log_start: int | None = None
    insult_id = -1 if args.action_id == "send_insult" else args.insult_id
    selected_query_id = args.insult_id if args.action_id == "scornful_insult" else None
    parameters = {} if args.action_id == "send_insult" else {"insult_id": insult_id}
    report: dict[str, object] = {
        "validator": "run_insult_execution.py",
        "status": "unknown",
        "mode": "execute",
        "artifact": str(artifact),
        "action_id": args.action_id,
        "actor": _ACTOR,
        "recipient": args.recipient,
        "family": _FAMILY,
        "phase": "initiate",
        "insult_id": insult_id,
        "parameters": parameters,
        "request_id": args.request_id,
        "expected_outcome": args.expected_outcome,
        "expected_date_raw": args.expected_date_raw,
        "execute_call_count": 0,
        "execute_call_started": False,
        "idempotency_call_count": 0,
        "checks": {},
    }
    execution: object = None
    final: object = None
    duplicate: object = None
    before_summary: dict[str, object] = {}
    after_summary: dict[str, object] = {}
    try:
        if not isinstance(args.recipient, str) or not _TAG_RE.fullmatch(args.recipient):
            raise ExperimentStop("RECIPIENT_TAG_INVALID", "recipient must match [A-Z]{3}")
        if args.recipient == _ACTOR:
            raise ExperimentStop("RECIPIENT_TAG_INVALID", "recipient must differ from FRA")
        if not isinstance(args.request_id, str) or not _REQUEST_ID_RE.fullmatch(args.request_id):
            raise ExperimentStop("REQUEST_ID_INVALID", "request id must match [A-Za-z0-9_-]{1,64}")
        if args.action_id == "send_insult" and args.insult_id is not None:
            raise ExperimentStop("SEND_INSULT_PARAMETERS_UNSUPPORTED",
                                 "send_insult uses empty parameters and insult_id=-1")
        if args.action_id == "scornful_insult" and (
                not _strict_int(args.insult_id)
                or not 0 <= args.insult_id <= 2147483647):
            raise ExperimentStop("SCORNFUL_INSULT_ID_REQUIRED",
                                 "scornful_insult requires --insult-id in 0..INT32_MAX")
        if not _strict_int(args.expected_date_raw):
            raise ExperimentStop("EXPECTED_DATE_RAW_INVALID", "expected date must be an integer")

        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session"] = {
            "session_id": session.session_id,
            "experiment_id": session.experiment_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        if isinstance(report.get("build_binding"), dict):
            report["build_binding"]["loaded_dll_sha256"] = session.record.get("dll_sha256")
        log_start = log_path.stat().st_size
        report["log_start_offset"] = log_start
        health_before = wait_runtime_ready(session, restore_minimized=True)
        if health_before.get("status") != "ready":
            raise ExperimentStop("SESSION_NOT_READY", json.dumps(health_before, ensure_ascii=False))
        journal_path = artifact / "diplomacy.sqlite3"
        with DurableJournal(
            journal_path, session.experiment_id, session.session_id,
            global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            before_probes = _run_snapshots(session, artifact / "before" / "probes")
            before_control = _control_summary(before_probes["control_state"]["snapshot"])
            before_queries = _query_insult_set(
                api, args.recipient, artifact / "before" / "queries", selected_query_id
            )
            before_summary = _query_set_summary(before_queries, selected_query_id)
            capabilities = sorted(session.installation_capabilities())
            before_baseline = _baseline(
                health_before, before_control, before_probes, before_summary,
                args.expected_date_raw, capabilities, expected_active=False,
                require_submission_ack=True, action_id=args.action_id,
            )
            report["before"] = {
                "health": health_before,
                "control": before_control,
                "queries": before_queries,
                "query_summary": before_summary,
                "diplomat": _diplomat_record(before_probes),
                "probes": _public_probe_records(before_probes),
                "baseline": before_baseline,
                "capabilities": capabilities,
            }
            if not all(before_baseline.values()):
                raise ExperimentStop(
                    "BASELINE_NOT_READY_FOR_EXPECTED_INSULT",
                    json.dumps(before_baseline, ensure_ascii=False),
                )
            # Record the attempted native call before entering the bridge.
            # The bridge may submit successfully and then raise while
            # decoding its receipt, so this counter must never depend on the
            # call returning normally.
            report["execute_call_count"] = 1
            report["execute_call_started"] = True
            execution = api.execute_diplomatic_action(
                args.request_id, args.action_id, _ACTOR, args.recipient,
                phase="initiate", parameters=parameters,
            )
            report["execution"] = execution
            if isinstance(execution, dict) and execution.get("submitted") is True:
                poll = _poll_royal_result(api, args.request_id)
            else:
                poll = {
                    "calls": 1,
                    "status_history": [execution.get("status")]
                    if isinstance(execution, dict) else [],
                    "terminal": isinstance(execution, dict)
                    and execution.get("status") in _TERMINAL_STATUSES,
                    "final": execution,
                    "timeout_bound_seconds": _POLL_SECONDS,
                }
            final = poll.get("final")
            report["poll"] = poll
            after_queries = _query_insult_set(
                api, args.recipient, artifact / "after" / "queries", selected_query_id
            )
            after_summary = _query_set_summary(after_queries, selected_query_id)
            after_probes = _run_snapshots(session, artifact / "after" / "probes")
            after_control = _control_summary(after_probes["control_state"]["snapshot"])
            after_health = session.health()
            after_baseline = _baseline(
                after_health, after_control, after_probes, after_summary,
                args.expected_date_raw, capabilities, expected_active=True,
                require_submission_ack=False, action_id=args.action_id,
            )
            after_baseline["date_same_as_before"] = (
                after_control.get("date_raw") == before_control.get("date_raw")
            )
            report["after"] = {
                "health": after_health,
                "control": after_control,
                "queries": after_queries,
                "query_summary": after_summary,
                "diplomat": _diplomat_record(after_probes),
                "probes": _public_probe_records(after_probes),
                "baseline": after_baseline,
            }
            if isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES:
                duplicate = api.execute_diplomatic_action(
                    args.request_id, args.action_id, _ACTOR, args.recipient,
                    phase="initiate", parameters=parameters,
                )
                report["idempotency_call_count"] = 1
            report["duplicate"] = duplicate
        with DurableJournal(
            journal_path, session.experiment_id, session.session_id,
            global_request_ids=True,
        ) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(
                args.request_id
            )
        report["reopened_result"] = reopened_result
        result_checks = _result_matches(
            args.action_id, args.recipient, args.expected_date_raw, insult_id,
            before_summary, after_summary, final,
        )
        report["result_checks"] = result_checks
        stable = _stable_result(final)
        reopened_stable = _stable_result(reopened_result)
        report["persistence"] = {
            "stable_result": stable,
            "reopened_stable_result": reopened_stable,
            "same_public_result": stable == reopened_stable,
        }
        terminal = isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES
        after_baseline = report["after"]["baseline"]
        checks = {
            "submitted_true": isinstance(execution, dict)
            and execution.get("submitted") is True,
            "expected_terminal_result": terminal and result_checks.get("all") is True,
            "duplicate_idempotent": (
                isinstance(duplicate, dict)
                and duplicate.get("idempotent") is True
                and _stable_result(duplicate) == stable
            ) if terminal else False,
            "journal_survives_reopen": stable == reopened_stable,
            "after_baseline_unchanged": all(after_baseline.values()),
            "native_effects_are_complete": all(
                _strict_int(result_checks.get("public_result", {}).get(field))
                for field in _EFFECT_FIELDS
            ) if isinstance(result_checks.get("public_result"), dict) else False,
            "four_snapshots_before": report["before"]["baseline"]["four_snapshots_complete"],
            "four_snapshots_after": after_baseline["four_snapshots_complete"],
            "por_paused_date_identity": (
                report["before"]["control"].get("player_slot") == _PLAYER_SLOT
                and after_baseline["player_slot_is_por"]
                and report["before"]["control"].get("paused_flag") == 1
                and after_baseline["paused"]
                and report["before"]["control"].get("date_raw")
                == after_control.get("date_raw") == args.expected_date_raw
            ),
            "one_execute_and_one_idempotency_call": (
                report["execute_call_count"] == 1
                and report["idempotency_call_count"] == (1 if terminal else 0)
            ),
            "build_dll_source_bound": report.get("build_binding", {}).get(
                "installation_matches_build_manifest") is True,
            "insult_query_evidence_is_family_specific": (
                before_summary.get("send", {}).get("family") == _FAMILY
                and after_summary.get("send", {}).get("family") == _FAMILY
                and before_summary.get("scornful", {}).get("family") == _FAMILY
                and after_summary.get("scornful", {}).get("family") == _FAMILY
            ),
        }
        report["checks"] = checks
        if terminal:
            report["status"] = "passed" if all(checks.values()) else "failed"
        else:
            pending_keys = (
                "journal_survives_reopen", "after_baseline_unchanged",
                "four_snapshots_before", "four_snapshots_after",
                "por_paused_date_identity", "build_dll_source_bound",
                "insult_query_evidence_is_family_specific",
            )
            report["status"] = "pending" if all(checks[key] for key in pending_keys) else "failed"
    except ExperimentStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"code": "UNEXPECTED_OPERATOR_ERROR",
                            "type": type(error).__name__, "message": str(error)}
    finally:
        native_meta = None
        if _strict_int(log_start) and log_start >= 0:
            native_meta = _copy_log_slice(
                log_path, log_start, artifact / "native-events-slice.jsonl"
            )
            report["native_events"] = native_meta
        report["submission_observation"] = _submission_observation(
            report, native_meta, artifact, args.action_id, args.recipient,
            args.expected_date_raw,
        )
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 3 if report["status"] == "pending" else 2


if __name__ == "__main__":
    raise SystemExit(main())
