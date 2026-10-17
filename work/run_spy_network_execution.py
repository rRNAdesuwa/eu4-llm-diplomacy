"""Execute or resume one bounded Build Spy Network task operation.

Build Spy Network is a one-sided diplomat task.  The start and stop actions
share selector ``13176`` and differ by native mode ``1`` and ``0``.  This
operator reuses the Improve Relations task observation and the shared
session/journal helpers while binding every result to the Spy family.
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
    _copy_log_slice,
    _stable_result,
    _write_json,
)
from work.run_improve_relations_execution import (  # noqa: E402
    _diplomat_evidence,
    _new_artifact,
    _query_baseline,
    _query_improve_pair,
    _query_task_transition,
    _result_matches,
    _snapshot_baseline,
    _status_for_report,
)
from work.run_royal_marriage_execution import (  # noqa: E402
    ExperimentStop,
    _installation_binding,
    _poll_royal_result,
    _public_probe_records,
    _query_is_complete,
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
_DEFAULT_DATE_RAW = 56459880
_ACTIONS = ("build_spy_network", "stop_building_spy_network")
_OUTCOMES = ("executed",)
_TERMINAL_STATUSES = frozenset(
    ("accepted", "rejected", "executed", "invalidated", "expired", "conflict")
)
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_SPY_SELECTOR = 13176
_SPY_FAMILY = "spy_network"


def _query_spy_pair(api: DiplomacyTools, recipient: str,
                    destination: Path) -> dict[str, dict[str, object]]:
    return _query_improve_pair(api, recipient, destination, _ACTIONS)


def _task_evidence(probes: dict[str, dict[str, object]], recipient: str) -> dict[str, object]:
    return _diplomat_evidence(
        probes, recipient, selector=_SPY_SELECTOR, family=_SPY_FAMILY
    )


def _public_before_after(probes: dict[str, dict[str, object]],
                         diplomat: dict[str, object],
                         expected_task: bool) -> dict[str, object]:
    return {
        "probes": _public_probe_records(probes),
        "diplomats_snapshot": diplomat.get("snapshot"),
        "diplomat_semantics": diplomat.get("semantics"),
        "diplomat_snapshot_path": diplomat.get("snapshot_path"),
        "diplomat_snapshot_completeness": diplomat.get("snapshot_completeness"),
        "task": diplomat.get("task"),
        "expected_task": expected_task,
    }


def _baseline(health: dict[str, object], control: dict[str, object],
              probes: dict[str, dict[str, object]], diplomat: dict[str, object],
              queries: dict[str, dict[str, object]], action_id: str,
              expected_task: bool, expected_date_raw: int,
              require_selected_available: bool = True) -> dict[str, object]:
    baseline = _snapshot_baseline(
        health, control, probes, diplomat, queries, action_id,
        expected_task, expected_date_raw, require_selected_available,
    )
    task = diplomat.get("task") if isinstance(diplomat, dict) else None
    baseline["task_selector_13176"] = (
        isinstance(task, dict) and task.get("selector") == _SPY_SELECTOR
    )
    baseline["task_family_spy_network"] = (
        isinstance(task, dict)
        and task.get("family", _SPY_FAMILY) == _SPY_FAMILY
    )
    return baseline


def _task_query_transition(queries: object, expected_task: bool) -> bool:
    return _query_task_transition(queries, expected_task, _ACTIONS)


def _resume_existing_artifact(resume_artifact: Path,
                              explicit_installation: Path | None,
                              expected_date_override: int | None) -> int:
    """Observe an existing Spy request without publishing or replaying it."""

    resume_artifact = resume_artifact.expanduser().resolve(strict=True)
    original = _read_json(resume_artifact / "report.json")
    if not isinstance(original, dict):
        raise ExperimentStop("RESUME_REPORT_INVALID", "source report is not an object")
    installation_record = original.get("installation")
    recorded_path = installation_record.get("path") if isinstance(installation_record, dict) else None
    installation = (
        explicit_installation.expanduser().resolve(strict=True)
        if explicit_installation is not None else
        Path(recorded_path).expanduser().resolve(strict=True)
        if isinstance(recorded_path, str) else None
    )
    action_id = original.get("action_id")
    recipient = original.get("recipient")
    request_id = original.get("request_id")
    expected_outcome = original.get("expected_outcome")
    expected_date_raw = (
        expected_date_override if expected_date_override is not None
        else original.get("expected_date_raw", _DEFAULT_DATE_RAW)
    )
    if (installation is None or action_id not in _ACTIONS
            or not isinstance(recipient, str) or not _TAG_RE.fullmatch(recipient)
            or not isinstance(request_id, str) or not _REQUEST_ID_RE.fullmatch(request_id)
            or expected_outcome not in _OUTCOMES
            or not isinstance(expected_date_raw, int) or isinstance(expected_date_raw, bool)):
        raise ExperimentStop("RESUME_ARGUMENTS_INVALID", "source report lacks a valid Spy request")

    output = _new_artifact(resume_artifact.parent, "spy-network-resume")
    log_path = installation.parent / "control-probe.jsonl"
    native_meta = original.get("native_events")
    log_start = (
        native_meta.get("start_offset") if isinstance(native_meta, dict) else
        original.get("log_start_offset")
    )
    report: dict[str, object] = {
        "status": "unknown", "mode": "resume_read_only",
        "resume_artifact": str(resume_artifact), "artifact": str(output),
        "action_id": action_id, "actor": _ACTOR, "recipient": recipient,
        "family": _SPY_FAMILY, "selector": _SPY_SELECTOR, "phase": "initiate",
        "parameters": {}, "request_id": request_id,
        "expected_outcome": expected_outcome, "expected_date_raw": expected_date_raw,
        "execute_call_count": 0, "idempotency_call_count": 0, "checks": {},
    }
    try:
        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session"] = {
            "session_id": session.session_id, "experiment_id": session.experiment_id,
            "pid": session.record.get("pid"), "dll_sha256": session.record.get("dll_sha256"),
        }
        if isinstance(report.get("build_binding"), dict):
            report["build_binding"]["loaded_dll_sha256"] = session.record.get("dll_sha256")
        health = wait_runtime_ready(session, restore_minimized=True)
        probes = _run_snapshots(session, output / "after" / "probes")
        diplomat = _task_evidence(probes, recipient)
        control = _control_summary(probes["control_state"]["snapshot"])
        with DurableJournal(resume_artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            first = api.get_diplomatic_result(request_id)
            queries = _query_spy_pair(api, recipient, output / "after" / "queries.json")
            final = api.get_diplomatic_result(request_id)
        with DurableJournal(resume_artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(request_id)

        before = original.get("before") if isinstance(original.get("before"), dict) else {}
        before_task_record = before.get("task") if isinstance(before.get("task"), dict) else {}
        before_task = before_task_record.get("task")
        expected_before = action_id == _ACTIONS[1]
        expected_after = not expected_before
        task_record = diplomat.get("task") if isinstance(diplomat, dict) else None
        after_task = task_record.get("task") if isinstance(task_record, dict) else None
        after_baseline = _baseline(
            health, control, probes, diplomat, queries, action_id,
            expected_after, expected_date_raw, require_selected_available=False,
        )
        result_checks = _result_matches(
            action_id, recipient, expected_outcome, expected_date_raw,
            before_task, after_task, final, family=_SPY_FAMILY, action_pair=_ACTIONS,
        )
        stable = _stable_result(final)
        reopened_stable = _stable_result(reopened_result)
        terminal = isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES
        report["before_source"] = before
        report["after"] = {
            "health": health, "control": control, "queries": queries,
            **_public_before_after(probes, diplomat, expected_after),
            "query_task_transition": _task_query_transition(queries, expected_after),
            "baseline": after_baseline,
        }
        report["result_reads"] = {
            "first": first, "final": final, "reopened": reopened_result,
            "terminal": terminal,
        }
        report["observations"] = {
            "result": result_checks, "task_before": before_task,
            "task_after": after_task, "native_selector": _SPY_SELECTOR,
        }
        report["persistence"] = {
            "stable_result": stable, "reopened_stable_result": reopened_stable,
            "same_public_result": stable == reopened_stable,
        }
        report["checks"] = {
            "no_new_execute_submission": report["execute_call_count"] == 0,
            "task_before_source_expected": before_task is expected_before,
            "task_after_expected": after_task is expected_after,
            "query_task_transition": report["after"]["query_task_transition"],
            "after_baseline_unchanged": all(after_baseline.values()),
            "four_snapshots_after": after_baseline["four_snapshots_complete"],
            "por_paused_date_identity": (
                control.get("player_slot") == _PLAYER_SLOT
                and control.get("paused_flag") == 1
                and control.get("date_raw") == expected_date_raw
            ),
            "journal_survives_reopen": stable == reopened_stable,
            "build_dll_source_bound": report.get("build_binding", {}).get(
                "installation_matches_build_manifest") is True,
        }
        if terminal:
            report["checks"]["expected_terminal_result"] = result_checks.get("all") is True
        else:
            report["checks"]["nonterminal_read_only"] = True
        if terminal:
            report["status"] = (
                "passed" if result_checks.get("all") is True
                and all(report["checks"].values()) else "failed"
            )
        else:
            report["status"] = (
                "pending" if all(report["checks"].values()) else "failed"
            )
    except ExperimentStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_RESUME_ERROR", "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if isinstance(log_start, int) and log_start >= 0:
            report["native_events"] = _copy_log_slice(
                log_path, log_start, output / "native-events-slice.jsonl"
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
    parser.add_argument("--expected-outcome", choices=_OUTCOMES)
    parser.add_argument("--expected-date-raw", type=int, default=None,
                        help=f"Native date (default: {_DEFAULT_DATE_RAW})")
    parser.add_argument("--resume-artifact", type=Path,
                        help="Read an existing request without execute or replay")
    args = parser.parse_args(argv)

    if args.resume_artifact is not None:
        try:
            return _resume_existing_artifact(
                args.resume_artifact, args.installation, args.expected_date_raw,
            )
        except ExperimentStop as error:
            print(json.dumps({"status": "failed", "error": {
                "code": error.code, "message": error.message}}, ensure_ascii=False), flush=True)
            return 2

    required = ("installation", "action_id", "recipient", "request_id", "expected_outcome")
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join(
            "--" + name.replace("_", "-") for name in missing
        ))
    if args.expected_date_raw is None:
        args.expected_date_raw = _DEFAULT_DATE_RAW
    if args.expected_outcome != "executed":
        parser.error("Spy Network is a one-sided task and requires --expected-outcome executed")

    installation = args.installation.expanduser().resolve(strict=True)
    artifact = _new_artifact(installation.parent, "spy-network-execution")
    log_path = installation.parent / "control-probe.jsonl"
    report: dict[str, object] = {
        "status": "unknown", "mode": "execute", "artifact": str(artifact),
        "action_id": args.action_id, "actor": _ACTOR, "recipient": args.recipient,
        "family": _SPY_FAMILY, "selector": _SPY_SELECTOR, "phase": "initiate",
        "parameters": {}, "request_id": args.request_id,
        "expected_outcome": args.expected_outcome, "expected_date_raw": args.expected_date_raw,
        "execute_call_count": 0, "idempotency_call_count": 0, "checks": {},
    }
    log_start: int | None = None
    execution: object | None = None
    final: object = None
    try:
        if not isinstance(args.recipient, str) or not _TAG_RE.fullmatch(args.recipient):
            raise ExperimentStop("RECIPIENT_TAG_INVALID", "recipient must match [A-Z]{3}")
        if not isinstance(args.request_id, str) or not _REQUEST_ID_RE.fullmatch(args.request_id):
            raise ExperimentStop("REQUEST_ID_INVALID", "request id must match [A-Za-z0-9_-]{1,64}")
        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session"] = {
            "session_id": session.session_id, "experiment_id": session.experiment_id,
            "pid": session.record.get("pid"), "dll_sha256": session.record.get("dll_sha256"),
        }
        if isinstance(report.get("build_binding"), dict):
            report["build_binding"]["loaded_dll_sha256"] = session.record.get("dll_sha256")
        log_start = log_path.stat().st_size
        report["log_start_offset"] = log_start
        health_before = wait_runtime_ready(session, restore_minimized=True)
        report["preflight"] = {
            "health": health_before,
            "capabilities": sorted(session.installation_capabilities()),
        }
        if health_before.get("status") != "ready":
            raise ExperimentStop("SESSION_NOT_READY", json.dumps(health_before, ensure_ascii=False))

        expected_before = args.action_id == _ACTIONS[1]
        expected_after = not expected_before
        journal_path = artifact / "diplomacy.sqlite3"
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            before_probes = _run_snapshots(session, artifact / "before" / "probes")
            before_diplomat = _task_evidence(before_probes, args.recipient)
            before_control = _control_summary(before_probes["control_state"]["snapshot"])
            before_queries = _query_spy_pair(
                api, args.recipient, artifact / "before" / "queries.json"
            )
            before_baseline = _baseline(
                health_before, before_control, before_probes, before_diplomat,
                before_queries, args.action_id, expected_before, args.expected_date_raw,
            )
            report["before"] = {
                "health": health_before, "control": before_control,
                "queries": before_queries,
                **_public_before_after(before_probes, before_diplomat, expected_before),
                "baseline": before_baseline,
            }
            if not all(before_baseline.values()):
                raise ExperimentStop(
                    "BASELINE_NOT_READY_FOR_EXPECTED_TASK",
                    json.dumps(before_baseline, ensure_ascii=False),
                )

            execution = api.execute_diplomatic_action(
                args.request_id, args.action_id, _ACTOR, args.recipient,
                phase="initiate", parameters={},
            )
            report["execute_call_count"] = 1
            report["execution"] = execution
            if isinstance(execution, dict) and execution.get("submitted") is True:
                poll = _poll_royal_result(api, args.request_id)
            else:
                poll = {
                    "calls": 1,
                    "status_history": [execution.get("status")] if isinstance(execution, dict) else [],
                    "terminal": isinstance(execution, dict)
                    and execution.get("status") in _TERMINAL_STATUSES,
                    "final": api.get_diplomatic_result(args.request_id),
                }
            final = poll.get("final")
            report["poll"] = poll

            after_queries = _query_spy_pair(
                api, args.recipient, artifact / "after" / "queries.json"
            )
            after_probes = _run_snapshots(session, artifact / "after" / "probes")
            after_diplomat = _task_evidence(after_probes, args.recipient)
            after_control = _control_summary(after_probes["control_state"]["snapshot"])
            after_health = session.health()
            after_baseline = _baseline(
                after_health, after_control, after_probes, after_diplomat,
                after_queries, args.action_id, expected_after, args.expected_date_raw,
                require_selected_available=False,
            )
            report["after"] = {
                "health": after_health, "control": after_control,
                "queries": after_queries,
                **_public_before_after(after_probes, after_diplomat, expected_after),
                "query_task_transition": _task_query_transition(after_queries, expected_after),
                "baseline": after_baseline,
            }

            duplicate = None
            if isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES:
                duplicate = api.execute_diplomatic_action(
                    args.request_id, args.action_id, _ACTOR, args.recipient,
                    phase="initiate", parameters={},
                )
                report["idempotency_call_count"] = 1
            report["duplicate"] = duplicate
            stable = _stable_result(final)

        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(args.request_id)
        report["reopened_result"] = reopened_result
        reopened_stable = _stable_result(reopened_result)
        before_task = report["before"]["task"].get("task")
        after_task = report["after"]["task"].get("task")
        result_checks = _result_matches(
            args.action_id, args.recipient, args.expected_outcome,
            args.expected_date_raw, before_task, after_task, final,
            family=_SPY_FAMILY, action_pair=_ACTIONS,
        )
        report["observations"] = {
            "result": result_checks, "task_before": before_task,
            "task_after": after_task, "native_selector": _SPY_SELECTOR,
            "native_state_expected": 0,
            "native_mode_expected": 1 if args.action_id == _ACTIONS[0] else 0,
        }
        report["persistence"] = {
            "stable_result": stable, "reopened_stable_result": reopened_stable,
            "same_public_result": stable == reopened_stable,
        }
        terminal = isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES
        report["checks"] = {
            "submitted_true": isinstance(execution, dict) and execution.get("submitted") is True,
            "one_execute_call": report["execute_call_count"] == 1,
            "task_before_expected": before_task is expected_before,
            "task_after_expected": after_task is expected_after,
            "task_transition": before_task is expected_before and after_task is expected_after,
            "query_task_transition": report["after"]["query_task_transition"],
            "selector_13176": (
                report["before"]["task"].get("selector") == _SPY_SELECTOR
                and report["after"]["task"].get("selector") == _SPY_SELECTOR
            ),
            "family_spy_network": (
                report["before"]["task"].get("family", _SPY_FAMILY) == _SPY_FAMILY
                and report["after"]["task"].get("family", _SPY_FAMILY) == _SPY_FAMILY
            ),
            "before_four_snapshots": report["before"]["baseline"]["four_snapshots_complete"],
            "after_four_snapshots": report["after"]["baseline"]["four_snapshots_complete"],
            "after_baseline_unchanged": all(report["after"]["baseline"].values()),
            "por_paused_date_identity": (
                report["before"]["control"].get("player_slot") == _PLAYER_SLOT
                and report["after"]["control"].get("player_slot") == _PLAYER_SLOT
                and report["before"]["control"].get("paused_flag") == 1
                and report["after"]["control"].get("paused_flag") == 1
                and report["before"]["control"].get("date_raw")
                == report["after"]["control"].get("date_raw") == args.expected_date_raw
            ),
            "journal_survives_reopen": stable == reopened_stable,
            "build_dll_source_bound": report.get("build_binding", {}).get(
                "installation_matches_build_manifest") is True,
        }
        if terminal:
            report["checks"]["expected_terminal_result"] = result_checks.get("all") is True
            report["checks"]["duplicate_idempotent"] = (
                isinstance(report.get("duplicate"), dict)
                and report["duplicate"].get("idempotent") is True
                and _stable_result(report["duplicate"]) == stable
            )
        else:
            report["checks"]["idempotency_deferred_while_nonterminal"] = (
                report["idempotency_call_count"] == 0
            )
        report["status"] = _status_for_report(report, final, result_checks, execution)
    except ExperimentStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_OPERATOR_ERROR", "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if isinstance(log_start, int) and log_start >= 0:
            report["native_events"] = _copy_log_slice(
                log_path, log_start, artifact / "native-events-slice.jsonl"
            )
        _write_json(artifact / "report.json", report)

    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 3 if report["status"] == "pending" else 2


if __name__ == "__main__":
    raise SystemExit(main())
