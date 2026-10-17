"""Execute or resume one bounded native Royal Marriage operation.

The game process and observer installation must already exist.  The operator
publishes exactly one request through ``execute_diplomatic_action`` in normal
mode and then uses one same-request call to verify idempotency.  A submission
timeout is recorded as unknown; ``--resume-artifact`` reads the existing
journal and only performs the idempotency call after a terminal result.
"""
from __future__ import annotations

import argparse
import json
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
from work.local_config import game_exe  # noqa: E402
from work.observer_runtime_ready import wait_runtime_ready  # noqa: E402
from work.run_alliance_execution import (  # noqa: E402
    _POLL_SECONDS,
    _copy_log_slice,
    _sha256_file,
    _stable_result,
    _write_json,
)
from work.validate_alliance_reload import (  # noqa: E402
    PROBE_SPECS,
    _control_summary,
    _diplomat_semantics,
    _read_json,
    _run_snapshots,
)


_ACTOR = "FRA"
_PLAYER_SLOT = 189  # POR in the controlled r3 experiment
_DEFAULT_DATE_RAW = 56459880
_ROYAL_ACTIONS = ("offer_royal_marriage", "break_royal_ties")
_TERMINAL_STATUSES = frozenset(
    ("accepted", "rejected", "executed", "invalidated", "expired", "conflict")
)
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_ACTION_OUTCOMES = {
    "offer_royal_marriage": frozenset(("accepted", "rejected")),
    "break_royal_ties": frozenset(("executed",)),
}


class ExperimentStop(RuntimeError):
    """An expected bounded operator stop with a stable report code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _installation_binding(installation: Path) -> dict[str, object]:
    """Return bounded installation and build-manifest provenance."""

    manifest_path = installation.parent / "build-manifest.json"
    installation_record = _read_json(installation)
    manifest_record = _read_json(manifest_path)
    if not isinstance(installation_record, dict) or not isinstance(manifest_record, dict):
        raise ExperimentStop("INSTALLATION_METADATA_INVALID", "installation or build manifest is not an object")
    installation_hash = _sha256_file(installation)
    manifest_hash = _sha256_file(manifest_path)
    declared_dll = installation_record.get("dll_sha256")
    built_dll = manifest_record.get("dll_sha256")
    session_dll = installation_record.get("dll_sha256")
    return {
        "installation": {
            **installation_hash,
            "declared_dll_sha256": declared_dll,
            "experiment_id": installation_record.get("experiment_id"),
            "session_id": installation_record.get("session_id"),
            "pid": installation_record.get("pid"),
        },
        "build_manifest": {
            **manifest_hash,
            "path": str(manifest_path),
            "experiment_id": manifest_record.get("experiment_id"),
            "version": manifest_record.get("version"),
            "dll": manifest_record.get("dll"),
            "dll_sha256": built_dll,
            "sources": manifest_record.get("sources"),
        },
        "build_binding": {
            "installation_dll_sha256": session_dll,
            "build_manifest_dll_sha256": built_dll,
            "installation_matches_build_manifest": (
                isinstance(session_dll, str)
                and isinstance(built_dll, str)
                and session_dll.lower() == built_dll.lower()
            ),
        },
    }


def _inspect_royal_pair(api: DiplomacyTools, recipient: str) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for action_id in _ROYAL_ACTIONS:
        try:
            inspected = api.inspect_diplomatic_action(
                action_id, _ACTOR, recipient, phase="initiate", parameters={}
            )
            result[action_id] = inspected if isinstance(inspected, dict) else {
                "status": "unknown", "error": "INSPECTION_NOT_OBJECT",
            }
        except Exception as error:
            result[action_id] = {
                "status": "unknown", "error_type": type(error).__name__,
                "error": str(error),
            }
    return result


def _query_royal_pair(api: DiplomacyTools, recipient: str, destination: Path) -> dict[str, dict[str, object]]:
    result = _inspect_royal_pair(api, recipient)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json(destination, result)
    return result


def _query_is_complete(inspection: object, action_id: str) -> bool:
    if not isinstance(inspection, dict) or inspection.get("action_id") != action_id:
        return False
    session = inspection.get("session")
    visibility = inspection.get("visibility")
    legality = inspection.get("legality")
    coverage = inspection.get("rule_coverage")
    if not isinstance(coverage, dict):
        coverage = inspection.get("native_rule_components")
    return (
        isinstance(session, dict) and session.get("status") == "ready"
        and isinstance(visibility, dict) and visibility.get("complete") is True
        and isinstance(legality, dict) and legality.get("complete") is True
        and isinstance(coverage, dict) and coverage.get("complete") is True
    )


def _break_selector_relation(inspection: object) -> dict[str, object]:
    visibility = inspection.get("visibility") if isinstance(inspection, dict) else None
    status = visibility.get("status") if isinstance(visibility, dict) else None
    coverage = inspection.get("rule_coverage") if isinstance(inspection, dict) else None
    if not isinstance(coverage, dict) and isinstance(inspection, dict):
        coverage = inspection.get("native_rule_components")
    selection = coverage.get("ui_action_selection") if isinstance(coverage, dict) else None
    relation = status == "visible" if status in ("visible", "hidden") else None
    return {
        "visibility_status": status,
        "visibility_complete": isinstance(visibility, dict) and visibility.get("complete") is True,
        "ui_action_selection": selection,
        "ui_action_selection_bool": isinstance(selection, bool),
        "royal_marriage": relation,
        "selector_consistent": (
            isinstance(selection, bool) and relation is not None and selection is relation
        ),
        "query_complete": _query_is_complete(inspection, "break_royal_ties"),
    }


def _single_side_acceptance_check(inspection: object) -> bool:
    acceptance = inspection.get("acceptance") if isinstance(inspection, dict) else None
    return (
        isinstance(acceptance, dict)
        and acceptance.get("applicability") == "not_applicable"
        and acceptance.get("complete") is True
    )


def _snapshots_complete(records: object) -> bool:
    if not isinstance(records, dict) or set(records) != {spec.name for spec in PROBE_SPECS}:
        return False
    return all(
        isinstance(item, dict)
        and isinstance(item.get("snapshot_completeness"), dict)
        and item["snapshot_completeness"].get("complete") is True
        for item in records.values()
    )


def _public_probe_records(records: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    return {
        name: {
            "status": item.get("status"),
            "snapshot_path": item.get("snapshot_path"),
            "snapshot_completeness": item.get("snapshot_completeness"),
            "snapshot_sha256": item.get("snapshot_sha256"),
        }
        for name, item in records.items()
    }


def _poll_royal_result(api: DiplomacyTools, request_id: str) -> dict[str, object]:
    """Poll one journal request for at most the shared 20-second bound."""

    deadline = time.monotonic() + _POLL_SECONDS
    calls = 0
    history: list[str] = []
    final: dict[str, object] | None = None
    while True:
        final = api.get_diplomatic_result(request_id)
        calls += 1
        status = final.get("status") if isinstance(final, dict) else None
        if isinstance(status, str) and (not history or history[-1] != status):
            history.append(status)
        if status in _TERMINAL_STATUSES or time.monotonic() >= deadline:
            break
        time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
    return {
        "calls": calls,
        "status_history": history,
        "terminal": isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES,
        "final": final,
        "timeout_bound_seconds": _POLL_SECONDS,
    }


def _expected_relation(action_id: str, expected_outcome: str, *, before: bool) -> bool:
    if action_id == "break_royal_ties":
        return before
    return False if before else expected_outcome == "accepted"


def _result_matches(action_id: str, expected_outcome: str,
                    result: object, before_relation: bool) -> dict[str, object]:
    if not isinstance(result, dict):
        return {"status": False, "relation": False, "proof": False, "event": None}
    public = result.get("result")
    if not isinstance(public, dict):
        return {"status": False, "relation": False, "proof": False, "event": None}
    status_ok = result.get("status") == expected_outcome and result.get("game_outcome") == expected_outcome
    if action_id == "offer_royal_marriage":
        event_ok = public.get("event") == "native_alliance_response_result"
        proof_ok = public.get("response_verified") is True and public.get("request_binding_verified") is True
        relation_ok = (
            public.get("family") == "royal_marriage"
            and public.get("royal_marriage_before") is before_relation
            and public.get("royal_marriage_after") is (expected_outcome == "accepted")
            and public.get("native_state") == (2 if expected_outcome == "accepted" else 1)
        )
    else:
        event_ok = public.get("event") == "native_alliance_execution_result"
        proof_ok = public.get("execution_verified") is True and public.get("request_binding_verified") is True
        relation_ok = (
            public.get("family") == "royal_marriage"
            and public.get("royal_marriage_before") is True
            and public.get("royal_marriage_after") is False
            and public.get("native_state") == 0
            and public.get("native_variant") == 0
        )
    return {"status": status_ok, "relation": relation_ok, "proof": proof_ok,
            "event": event_ok, "all": status_ok and relation_ok and proof_ok and event_ok}


def _resume_existing_artifact(resume_artifact: Path,
                              explicit_installation: Path | None,
                              expected_date_override: int | None) -> int:
    """Finish observation for an existing submission without publishing it."""

    resume_artifact = resume_artifact.expanduser().resolve(strict=True)
    original = _read_json(resume_artifact / "report.json")
    if not isinstance(original, dict):
        raise ExperimentStop("RESUME_REPORT_INVALID", "the source execution report is not an object")
    original_installation = original.get("installation")
    recorded_path = original_installation.get("path") if isinstance(original_installation, dict) else None
    installation = (explicit_installation.expanduser().resolve(strict=True)
                    if explicit_installation is not None
                    else Path(recorded_path).expanduser().resolve(strict=True)
                    if isinstance(recorded_path, str) else None)
    if installation is None:
        raise ExperimentStop("RESUME_INSTALLATION_MISSING", "source report has no installation path")
    action_id = original.get("action_id")
    recipient = original.get("recipient")
    request_id = original.get("request_id")
    expected_outcome = original.get("expected_outcome")
    expected_date_raw = (expected_date_override
                         if expected_date_override is not None
                         else original.get("expected_date_raw", _DEFAULT_DATE_RAW))
    if (action_id not in _ROYAL_ACTIONS or not isinstance(recipient, str)
            or not _TAG_RE.fullmatch(recipient) or not isinstance(request_id, str)
            or expected_outcome not in ("accepted", "rejected", "executed")
            or not isinstance(expected_date_raw, int) or isinstance(expected_date_raw, bool)):
        raise ExperimentStop("RESUME_ARGUMENTS_INVALID", "source report lacks a valid Royal request identity")

    output = resume_artifact.parent / ("royal-marriage-resume-" + uuid.uuid4().hex)
    output.mkdir(parents=True)
    log_path = installation.parent / "control-probe.jsonl"
    log_start = original.get("log_start_offset")
    report: dict[str, object] = {
        "validator": "run_royal_marriage_execution.py",
        "mode": "resume_read_only",
        "status": "unknown",
        "resume_artifact": str(resume_artifact),
        "artifact": str(output),
        "action_id": action_id,
        "recipient": recipient,
        "request_id": request_id,
        "expected_outcome": expected_outcome,
        "expected_date_raw": expected_date_raw,
        "execute_call_count": 0,
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
        after_health = session.health()
        with DurableJournal(resume_artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            first_result = api.get_diplomatic_result(request_id)
            after_queries = _query_royal_pair(api, recipient, output / "after" / "queries.json")
            # A second read lets a response already written during the
            # read-only queries reach the existing journal record.
            final = api.get_diplomatic_result(request_id)
            duplicate = None
            if isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES:
                # The journal returns this as an idempotent lookup.  It is
                # allowed only after a terminal result and cannot republish.
                duplicate = api.execute_diplomatic_action(
                    request_id, action_id, _ACTOR, recipient,
                    phase="initiate", parameters={},
                )
                report["idempotency_call_count"] = 1
        with DurableJournal(resume_artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(request_id)

        before = original.get("before") if isinstance(original.get("before"), dict) else {}
        before_control = before.get("control") if isinstance(before.get("control"), dict) else {}
        before_selector = before.get("break_selector") if isinstance(before.get("break_selector"), dict) else {}
        after_selector = _break_selector_relation(after_queries.get("break_royal_ties", {}))
        before_relation = before_selector.get("royal_marriage")
        if not isinstance(before_relation, bool):
            before_relation = _expected_relation(action_id, expected_outcome, before=True)
        public_result = final.get("result") if isinstance(final, dict) else None
        result_checks = _result_matches(action_id, expected_outcome, final, before_relation)
        stable = _stable_result(final)
        reopened_stable = _stable_result(reopened_result)
        after_baseline = {
            "health_before_snapshots_ready": (
                health.get("status") == "ready"
                and health.get("complete") is True
                and health.get("date_raw") == expected_date_raw
            ),
            "health_ready": after_health.get("status") == "ready" and after_health.get("complete") is True,
            "health_date_matches_expected": after_health.get("date_raw") == expected_date_raw,
            "date_matches_expected": after_control.get("date_raw") == expected_date_raw,
            "player_slot_is_por": after_control.get("player_slot") == _PLAYER_SLOT,
            "paused": after_control.get("paused_flag") == 1,
            "four_snapshots_complete": _snapshots_complete(after_probes),
            "offer_query_complete": _query_is_complete(after_queries.get("offer_royal_marriage"), "offer_royal_marriage"),
            "break_query_complete": _query_is_complete(after_queries.get("break_royal_ties"), "break_royal_ties"),
            "break_acceptance_not_applicable": _single_side_acceptance_check(after_queries.get("break_royal_ties")),
            "break_selector_consistent": after_selector.get("selector_consistent") is True,
            "date_same_as_before": after_control.get("date_raw") == before_control.get("date_raw"),
        }
        report["source_report"] = {
            "status": "ok",
            "original_status": original.get("status"),
            "original_report": str(resume_artifact / "report.json"),
        }
        report["after"] = {
            "health_before_snapshots": health,
            "health": after_health,
            "control": after_control,
            "queries": after_queries,
            "break_selector": after_selector,
            "probes": _public_probe_records(after_probes),
            "baseline": after_baseline,
        }
        report["result_reads"] = {
            "first": first_result,
            "final": final,
            "reopened": reopened_result,
            "terminal": isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES,
        }
        native_relation_available = (
            isinstance(public_result, dict)
            and isinstance(public_result.get("royal_marriage_after"), bool)
        )
        report["observations"] = {
            "result": result_checks,
            "native_relation_after": public_result.get("royal_marriage_after")
            if isinstance(public_result, dict) else None,
            "native_relation_available": native_relation_available,
            "break_selector_result_consistent": (
                public_result.get("royal_marriage_after") is after_selector.get("royal_marriage")
                if native_relation_available else None
            ),
        }
        checks = {
            "no_new_execute_submission": report["execute_call_count"] == 0,
            "after_baseline_unchanged": all(after_baseline.values()),
            "after_relation_selector_verified": after_selector.get("selector_consistent") is True,
            "native_relation_matches_selector": (
                not native_relation_available
                or report["observations"]["break_selector_result_consistent"] is True
            ),
            "journal_survives_reopen": stable == reopened_stable,
            "four_snapshots_after": after_baseline["four_snapshots_complete"],
            "por_paused_date_identity": (
                after_control.get("player_slot") == _PLAYER_SLOT
                and after_control.get("paused_flag") == 1
                and after_control.get("date_raw") == expected_date_raw
            ),
            "build_dll_source_bound": report.get("build_binding", {}).get(
                "installation_matches_build_manifest") is True,
        }
        terminal = isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES
        if terminal:
            checks["expected_terminal_result"] = result_checks.get("all") is True
            checks["terminal_idempotent"] = (
                isinstance(duplicate, dict)
                and duplicate.get("idempotent") is True
                and _stable_result(duplicate) == stable
            )
        else:
            checks["idempotency_deferred_while_nonterminal"] = report["idempotency_call_count"] == 0
        report["checks"] = checks
        if terminal:
            report["status"] = "passed" if all(checks.values()) else "failed"
        else:
            report["status"] = "pending" if all(checks.values()) else "failed"
    except ExperimentStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"code": "UNEXPECTED_RESUME_ERROR",
                            "type": type(error).__name__, "message": str(error)}
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
    parser.add_argument("--action-id", choices=_ROYAL_ACTIONS)
    parser.add_argument("--recipient", help="Three-letter uppercase country tag")
    parser.add_argument("--request-id")
    parser.add_argument("--expected-outcome", choices=("accepted", "rejected", "executed"))
    parser.add_argument("--expected-date-raw", type=int, default=None,
                        help=f"Native date (default: {_DEFAULT_DATE_RAW})")
    parser.add_argument("--resume-artifact", type=Path,
                        help="Resume an existing artifact using read-only get_result calls")
    args = parser.parse_args(argv)

    if args.resume_artifact is not None:
        try:
            return _resume_existing_artifact(
                args.resume_artifact,
                args.installation,
                args.expected_date_raw,
            )
        except ExperimentStop as error:
            print(json.dumps({"status": "failed", "error": {
                "code": error.code, "message": error.message}}, ensure_ascii=False), flush=True)
            return 2
        except Exception as error:
            print(json.dumps({"status": "failed", "error": {
                "code": "UNEXPECTED_RESUME_ERROR",
                "type": type(error).__name__, "message": str(error),
            }}, ensure_ascii=False), flush=True)
            return 2

    required = ("installation", "action_id", "recipient", "request_id", "expected_outcome")
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join("--" + name.replace("_", "-") for name in missing))
    if args.expected_date_raw is None:
        args.expected_date_raw = _DEFAULT_DATE_RAW

    installation = args.installation.expanduser().resolve()
    artifact = installation.parent / ("royal-marriage-execution-" + uuid.uuid4().hex)
    artifact.mkdir(parents=True)
    log_path = installation.parent / "control-probe.jsonl"
    report: dict[str, object] = {
        "status": "unknown",
        "action_id": args.action_id,
        "recipient": args.recipient,
        "request_id": args.request_id,
        "expected_outcome": args.expected_outcome,
        "expected_date_raw": args.expected_date_raw,
        "artifact": str(artifact),
        "checks": {},
        "execute_call_count": 0,
        "idempotency_call_count": 0,
    }
    log_start: int | None = None

    try:
        if not _TAG_RE.fullmatch(args.recipient):
            raise ExperimentStop("RECIPIENT_TAG_INVALID", "recipient must match [A-Z]{3}")
        if args.expected_outcome not in _ACTION_OUTCOMES[args.action_id]:
            raise ExperimentStop(
                "EXPECTED_OUTCOME_ACTION_MISMATCH",
                f"{args.action_id} cannot produce expected outcome {args.expected_outcome}",
            )
        if not isinstance(args.expected_date_raw, int) or isinstance(args.expected_date_raw, bool):
            raise ExperimentStop("EXPECTED_DATE_RAW_INVALID", "expected date must be an integer")
        report.update(_installation_binding(installation))
        record = _read_json(installation)
        if not isinstance(record, dict):
            raise ExperimentStop("INSTALLATION_METADATA_INVALID", "installation metadata is not an object")
        session = ObserverSession(installation, game_exe())
        report["session"] = {
            "session_id": session.session_id,
            "experiment_id": session.experiment_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        report["build_binding"] = {
            **(report.get("build_binding") if isinstance(report.get("build_binding"), dict) else {}),
            "loaded_dll_sha256": session.record.get("dll_sha256"),
        }
        log_start = log_path.stat().st_size
        report["log_start_offset"] = log_start
        health_before = wait_runtime_ready(session, restore_minimized=True)

        before_probes = _run_snapshots(session, artifact / "before" / "probes")
        before_control = _control_summary(before_probes["control_state"]["snapshot"])
        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            before_queries = _query_royal_pair(api, args.recipient, artifact / "before" / "queries.json")
            before_offer = before_queries.get("offer_royal_marriage", {})
            before_break = before_queries.get("break_royal_ties", {})
            before_selector = _break_selector_relation(before_break)
            before_baseline = {
                "health_ready": health_before.get("status") == "ready" and health_before.get("complete") is True,
                "health_date_matches_expected": health_before.get("date_raw") == args.expected_date_raw,
                "date_matches_expected": before_control.get("date_raw") == args.expected_date_raw,
                "player_slot_is_por": before_control.get("player_slot") == _PLAYER_SLOT,
                "paused": before_control.get("paused_flag") == 1,
                "four_snapshots_complete": _snapshots_complete(before_probes),
                "offer_query_complete": _query_is_complete(before_offer, "offer_royal_marriage"),
                "break_query_complete": _query_is_complete(before_break, "break_royal_ties"),
                "break_acceptance_not_applicable": _single_side_acceptance_check(before_break),
                "break_relation_matches_expected": (
                    before_selector.get("royal_marriage")
                    == _expected_relation(args.action_id, args.expected_outcome, before=True)
                ),
                "break_selector_consistent": before_selector.get("selector_consistent") is True,
                "royal_submission_capability": (
                    "native_royal_marriage_submission" in session.installation_capabilities()
                ),
            }
            report["before"] = {
                "health": health_before,
                "control": before_control,
                "queries": before_queries,
                "break_selector": before_selector,
                "probes": {
                    name: {
                        "status": item.get("status"),
                        "snapshot_path": item.get("snapshot_path"),
                        "snapshot_completeness": item.get("snapshot_completeness"),
                        "snapshot_sha256": item.get("snapshot_sha256"),
                    }
                    for name, item in before_probes.items()
                },
                "baseline": before_baseline,
            }
            if not all(before_baseline.values()):
                raise ExperimentStop("BASELINE_NOT_READY_POR_PAUSED", json.dumps(before_baseline, ensure_ascii=False))

            execution = api.execute_diplomatic_action(
                args.request_id, args.action_id, _ACTOR, args.recipient,
                phase="initiate", parameters={},
            )
            report["execute_call_count"] = 1
            report["execution"] = execution
            if execution.get("submitted") is True:
                poll = _poll_royal_result(api, args.request_id)
            else:
                poll = {
                    "calls": 1, "status_history": [execution.get("status")],
                    "terminal": execution.get("status") in _TERMINAL_STATUSES,
                    "final": api.get_diplomatic_result(args.request_id),
                    "timeout_bound_seconds": _POLL_SECONDS,
                }
            final = poll.get("final")
            report["poll"] = poll

            after_queries = _query_royal_pair(api, args.recipient, artifact / "after" / "queries.json")
            after_probes = _run_snapshots(session, artifact / "after" / "probes")
            after_control = _control_summary(after_probes["control_state"]["snapshot"])
            after_health = session.health()
            after_selector = _break_selector_relation(after_queries.get("break_royal_ties", {}))
            duplicate = api.execute_diplomatic_action(
                args.request_id, args.action_id, _ACTOR, args.recipient,
                phase="initiate", parameters={},
            )
            report["idempotency_call_count"] = 1
            report["duplicate"] = duplicate
            report["after"] = {
                "health": after_health,
                "control": after_control,
                "queries": after_queries,
                "break_selector": after_selector,
                "probes": {
                    name: {
                        "status": item.get("status"),
                        "snapshot_path": item.get("snapshot_path"),
                        "snapshot_completeness": item.get("snapshot_completeness"),
                        "snapshot_sha256": item.get("snapshot_sha256"),
                    }
                    for name, item in after_probes.items()
                },
            }
            after_baseline = {
                "health_ready": after_health.get("status") == "ready" and after_health.get("complete") is True,
                "health_date_matches_expected": after_health.get("date_raw") == args.expected_date_raw,
                "date_matches_expected": after_control.get("date_raw") == args.expected_date_raw,
                "player_slot_is_por": after_control.get("player_slot") == _PLAYER_SLOT,
                "paused": after_control.get("paused_flag") == 1,
                "four_snapshots_complete": _snapshots_complete(after_probes),
                "offer_query_complete": _query_is_complete(after_queries.get("offer_royal_marriage"), "offer_royal_marriage"),
                "break_query_complete": _query_is_complete(after_queries.get("break_royal_ties"), "break_royal_ties"),
                "break_acceptance_not_applicable": _single_side_acceptance_check(after_queries.get("break_royal_ties")),
                "break_selector_consistent": after_selector.get("selector_consistent") is True,
                "date_same_as_before": after_control.get("date_raw") == before_control.get("date_raw"),
            }
            report["after"]["baseline"] = after_baseline
            stable = _stable_result(final)
            reopened_result = None

        with DurableJournal(artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(args.request_id)
        report["reopened_result"] = reopened_result
        result_checks = _result_matches(
            args.action_id, args.expected_outcome, final,
            bool(before_selector.get("royal_marriage")),
        )
        after_relation = after_selector.get("royal_marriage")
        public_result = final.get("result") if isinstance(final, dict) else None
        report["observations"] = {
            "result": result_checks,
            "native_relation_after": public_result.get("royal_marriage_after")
            if isinstance(public_result, dict) else None,
            "break_selector_after": after_relation,
            "break_selector_result_consistent": (
                isinstance(public_result, dict)
                and public_result.get("royal_marriage_after") is after_relation
            ),
        }
        report["persistence"] = {
            "stable_result": stable,
            "reopened_stable_result": _stable_result(reopened_result),
            "same_public_result": stable == _stable_result(reopened_result),
        }
        report["checks"] = {
            "submitted_true": execution.get("submitted") is True,
            "expected_outcome_observed": result_checks.get("all") is True,
            "native_relation_after_verified": report["observations"]["break_selector_result_consistent"],
            "break_selector_before_independent": before_selector.get("selector_consistent") is True,
            "break_selector_after_independent": after_selector.get("selector_consistent") is True,
            "single_side_acceptance_not_applicable_before": before_baseline["break_acceptance_not_applicable"],
            "single_side_acceptance_not_applicable_after": after_baseline["break_acceptance_not_applicable"],
            "after_baseline_unchanged": all(after_baseline.values()),
            "duplicate_idempotent": (
                duplicate.get("idempotent") is True
                and _stable_result(duplicate) == stable
            ),
            "journal_survives_reopen": stable == _stable_result(reopened_result),
            "four_snapshots_before": before_baseline["four_snapshots_complete"],
            "four_snapshots_after": after_baseline["four_snapshots_complete"],
            "por_paused_date_identity": (
                before_control.get("player_slot") == _PLAYER_SLOT
                and after_control.get("player_slot") == _PLAYER_SLOT
                and before_control.get("paused_flag") == 1
                and after_control.get("paused_flag") == 1
                and before_control.get("date_raw") == after_control.get("date_raw") == args.expected_date_raw
            ),
            "one_execute_and_one_idempotency_call": (
                report["execute_call_count"] == 1 and report["idempotency_call_count"] == 1
            ),
            "build_dll_source_bound": report.get("build_binding", {}).get(
                "installation_matches_build_manifest") is True,
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except ExperimentStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"code": "UNEXPECTED_OPERATOR_ERROR",
                            "type": type(error).__name__, "message": str(error)}
    finally:
        if log_start is not None:
            report["native_events"] = _copy_log_slice(
                log_path, log_start, artifact / "native-events-slice.jsonl"
            )
        _write_json(artifact / "report.json", report)

    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
