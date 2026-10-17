"""Execute or observe one bounded native Guarantee relation operation.

Guarantee is a one-sided relation operation.  proclaim_guarantee changes the
relation from inactive to active and revoke_guarantee changes it from active
to inactive.  The relation state in relationship_state and the native
relation result are the business evidence; diplomat task records are not used
to infer whether a Guarantee remains active.

The process and observer installation must already exist.  Normal mode sends
one request, polls for at most the shared twenty-second bound, performs one
same-request idempotency call after a terminal result, and reopens the SQLite
journal.  --resume-artifact only reads an existing request and never
publishes it again.
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
_ACTIONS = ("proclaim_guarantee", "revoke_guarantee")
_TERMINAL_STATUSES = frozenset(
    ("accepted", "rejected", "executed", "invalidated", "expired", "conflict")
)
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def _query_guarantee_pair(
    api: DiplomacyTools, recipient: str, destination: Path | None = None
) -> dict[str, dict[str, object]]:
    """Inspect both Guarantee actions through the public unified API."""

    result: dict[str, dict[str, object]] = {}
    for action_id in _ACTIONS:
        try:
            inspected = api.inspect_diplomatic_action(
                action_id, _ACTOR, recipient, phase="initiate", parameters={}
            )
            result[action_id] = inspected if isinstance(inspected, dict) else {
                "status": "unknown",
                "error": "INSPECTION_NOT_OBJECT",
            }
        except Exception as error:
            result[action_id] = {
                "status": "unknown",
                "error_type": type(error).__name__,
                "error": str(error),
            }
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        _write_json(destination, result)
    return result


def _relation_state(query: object) -> dict[str, object]:
    """Extract only the verified public Guarantee relation state."""

    relationship = query.get("relationship_state") if isinstance(query, dict) else None
    active = relationship.get("guarantee_active") if isinstance(relationship, dict) else None
    complete = relationship.get("complete") if isinstance(relationship, dict) else False
    return {
        "guarantee_active": active if type(active) is bool else None,
        "complete": complete is True and type(active) is bool,
        "source": "relationship_state",
    }


def _relation_pair(queries: object) -> dict[str, object]:
    if not isinstance(queries, dict):
        return {
            "proclaim": _relation_state(None),
            "revoke": _relation_state(None),
            "guarantee_active": None,
            "complete": False,
            "consistent": False,
        }
    proclaim = _relation_state(queries.get("proclaim_guarantee"))
    revoke = _relation_state(queries.get("revoke_guarantee"))
    values = (proclaim.get("guarantee_active"), revoke.get("guarantee_active"))
    complete = proclaim.get("complete") is True and revoke.get("complete") is True
    consistent = complete and values[0] is values[1]
    return {
        "proclaim": proclaim,
        "revoke": revoke,
        "guarantee_active": values[0] if consistent else None,
        "complete": complete,
        "consistent": consistent,
        "source": "relationship_state",
    }


def _query_pair_complete(queries: object) -> bool:
    if not isinstance(queries, dict):
        return False
    return all(
        _query_is_complete(queries.get(action_id), action_id)
        and _relation_state(queries.get(action_id)).get("complete") is True
        for action_id in _ACTIONS
    )


def _public_diplomat_snapshot(probes: dict[str, dict[str, object]]) -> dict[str, object]:
    item = probes.get("diplomats", {})
    snapshot = item.get("snapshot") if isinstance(item, dict) else None
    try:
        semantics = _diplomat_semantics(snapshot) if isinstance(snapshot, dict) else None
        error = None
    except Exception as exc:
        semantics = None
        error = {"type": type(exc).__name__, "message": str(exc)}
    return {
        "snapshot": snapshot,
        "semantics": semantics,
        "semantics_error": error,
        "snapshot_path": item.get("snapshot_path") if isinstance(item, dict) else None,
        "snapshot_completeness": item.get("snapshot_completeness")
        if isinstance(item, dict) else None,
    }


def _result_matches(
    action_id: str,
    expected_outcome: str,
    expected_date_raw: int,
    recipient: str,
    before_relation: object,
    after_relation: object,
    result: object,
) -> dict[str, object]:
    """Check the public result without consulting diplomat task observations."""

    if not isinstance(result, dict):
        return {"status": False, "binding": False, "relation": False,
                "native": False, "proof": False, "event": False, "all": False}
    public = result.get("result")
    if not isinstance(public, dict):
        return {"status": False, "binding": False, "relation": False,
                "native": False, "proof": False, "event": False, "all": False}
    status_ok = (
        result.get("status") == expected_outcome
        and result.get("game_outcome") == expected_outcome
    )
    binding_ok = all(
        public.get(field) == expected
        for field, expected in (
            ("action_id", action_id),
            ("actor", _ACTOR),
            ("recipient", recipient),
            ("phase", "initiate"),
            ("date_raw", expected_date_raw),
            ("family", "guarantee"),
        )
    )
    expected_before = action_id == "revoke_guarantee"
    expected_after = action_id == "proclaim_guarantee"
    relation_ok = (
        public.get("guarantee_before") is expected_before
        and public.get("guarantee_after") is expected_after
        and before_relation is expected_before
        and after_relation is expected_after
    )
    native_ok = (
        public.get("native_state") == 0
        and public.get("native_variant") == (1 if action_id == "proclaim_guarantee" else 0)
        and public.get("outcome") == expected_outcome
    )
    proof_ok = (
        public.get("execution_verified") is True
        and public.get("request_binding_verified") is True
    )
    event_ok = public.get("event") == "native_diplomacy_relation_execution_result"
    return {
        "status": status_ok,
        "binding": binding_ok,
        "relation": relation_ok,
        "native": native_ok,
        "proof": proof_ok,
        "event": event_ok,
        "all": status_ok and binding_ok and relation_ok and native_ok and proof_ok and event_ok,
        "public_result": public,
    }


def _resume_existing_artifact(
    resume_artifact: Path,
    explicit_installation: Path | None,
    expected_date_override: int | None,
) -> int:
    """Read an existing Guarantee journal without publishing a request."""

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
    expected_outcome = original.get("expected_outcome")
    expected_date_raw = (
        expected_date_override if expected_date_override is not None
        else original.get("expected_date_raw", _DEFAULT_DATE_RAW)
    )
    if (
        installation is None
        or action_id not in _ACTIONS
        or not isinstance(recipient, str)
        or not _TAG_RE.fullmatch(recipient)
        or not isinstance(request_id, str)
        or not _REQUEST_ID_RE.fullmatch(request_id)
        or expected_outcome not in ("executed", "accepted", "rejected")
        or not isinstance(expected_date_raw, int)
        or isinstance(expected_date_raw, bool)
    ):
        raise ExperimentStop("RESUME_ARGUMENTS_INVALID", "source report lacks a valid Guarantee request")

    output = _new_artifact(resume_artifact.parent, "guarantee-resume")
    log_path = installation.parent / "control-probe.jsonl"
    native_meta = original.get("native_events")
    log_start = original.get("log_start_offset")
    if not isinstance(log_start, int) and isinstance(native_meta, dict):
        log_start = native_meta.get("start_offset")
    report: dict[str, object] = {
        "validator": "run_guarantee_execution.py",
        "status": "unknown",
        "mode": "resume_read_only",
        "resume_artifact": str(resume_artifact),
        "artifact": str(output),
        "action_id": action_id,
        "actor": _ACTOR,
        "recipient": recipient,
        "family": "guarantee",
        "phase": "initiate",
        "parameters": {},
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
        after_diplomat = _public_diplomat_snapshot(after_probes)
        after_health = session.health()
        with DurableJournal(
            resume_artifact / "diplomacy.sqlite3",
            session.experiment_id,
            session.session_id,
            global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            first = api.get_diplomatic_result(request_id)
            after_queries = _query_guarantee_pair(
                api, recipient, output / "after" / "queries.json"
            )
            final = api.get_diplomatic_result(request_id)
        with DurableJournal(
            resume_artifact / "diplomacy.sqlite3",
            session.experiment_id,
            session.session_id,
            global_request_ids=True,
        ) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(request_id)

        before = original.get("before") if isinstance(original.get("before"), dict) else {}
        before_relation = (
            before.get("relation", {}).get("guarantee_active")
            if isinstance(before.get("relation"), dict) else None
        )
        after_relation = _relation_pair(after_queries)
        result_checks = _result_matches(
            action_id, expected_outcome, expected_date_raw, recipient,
            before_relation, after_relation.get("guarantee_active"), final,
        )
        stable = _stable_result(final)
        reopened_stable = _stable_result(reopened_result)
        terminal = isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES
        checks = {
            "no_new_execute_submission": report["execute_call_count"] == 0,
            "health_ready": health.get("status") == "ready" and health.get("complete") is True,
            "date_matches_expected": after_control.get("date_raw") == expected_date_raw,
            "player_slot_is_por": after_control.get("player_slot") == _PLAYER_SLOT,
            "paused": after_control.get("paused_flag") == 1,
            "four_snapshots_after": _snapshots_complete(after_probes),
            "query_pair_complete": _query_pair_complete(after_queries),
            "query_relation_consistent": after_relation.get("consistent") is True,
            "journal_survives_reopen": stable == reopened_stable,
            "build_dll_source_bound": report.get("build_binding", {}).get(
                "installation_matches_build_manifest"
            ) is True,
        }
        report.update({
            "source_report": {"path": str(resume_artifact), "status": original.get("status")},
            "first_result": first,
            "final_result": final,
            "reopened_result": reopened_result,
            "after": {
                "health": after_health,
                "control": after_control,
                "queries": after_queries,
                "relation": after_relation,
                "diplomat": after_diplomat,
                "probes": _public_probe_records(after_probes),
            },
            "result_checks": result_checks,
        })
        if terminal:
            checks["expected_terminal_result"] = result_checks.get("all") is True
            report["status"] = "passed" if all(checks.values()) else "failed"
        else:
            checks["nonterminal_is_pending"] = True
            report["status"] = "pending" if all(checks.values()) else "failed"
        report["checks"] = checks
    except ExperimentStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_RESUME_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if isinstance(log_start, int) and log_start >= 0:
            report["native_events"] = _copy_log_slice(
                log_path, log_start, output / "native-events-slice.jsonl"
            )
        _write_json(output / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(output)}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 3 if report["status"] == "pending" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path)
    parser.add_argument("--action-id", choices=_ACTIONS)
    parser.add_argument("--recipient")
    parser.add_argument("--request-id")
    parser.add_argument("--expected-outcome", choices=("accepted", "rejected", "executed"))
    parser.add_argument("--expected-date-raw", type=int, default=None)
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
                "type": type(error).__name__,
                "message": str(error),
            }}, ensure_ascii=False), flush=True)
            return 2

    required = ("installation", "action_id", "recipient", "request_id", "expected_outcome")
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join(
            "--" + name.replace("_", "-") for name in missing
        ))
    if args.expected_date_raw is None:
        args.expected_date_raw = _DEFAULT_DATE_RAW
    installation = args.installation.expanduser().resolve()
    artifact = _new_artifact(installation.parent, "guarantee-execution")
    log_path = installation.parent / "control-probe.jsonl"
    log_start: int | None = None
    report: dict[str, object] = {
        "validator": "run_guarantee_execution.py",
        "status": "unknown",
        "mode": "execute",
        "artifact": str(artifact),
        "action_id": args.action_id,
        "actor": _ACTOR,
        "recipient": args.recipient,
        "family": "guarantee",
        "phase": "initiate",
        "parameters": {},
        "request_id": args.request_id,
        "expected_outcome": args.expected_outcome,
        "expected_date_raw": args.expected_date_raw,
        "execute_call_count": 0,
        "idempotency_call_count": 0,
        "checks": {},
    }
    execution: object = None
    final: object = None
    duplicate: object = None
    try:
        if not _TAG_RE.fullmatch(args.recipient):
            raise ExperimentStop("RECIPIENT_TAG_INVALID", "recipient must match [A-Z]{3}")
        if not _REQUEST_ID_RE.fullmatch(args.request_id):
            raise ExperimentStop("REQUEST_ID_INVALID", "request id must match [A-Za-z0-9_-]{1,64}")
        if args.expected_outcome != "executed":
            raise ExperimentStop(
                "GUARANTEE_SINGLE_SIDED_OUTCOME",
                "Guarantee is a one-sided relation operation and expects executed",
            )
        if not isinstance(args.expected_date_raw, int) or isinstance(args.expected_date_raw, bool):
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

        expected_before = args.action_id == "revoke_guarantee"
        journal_path = artifact / "diplomacy.sqlite3"
        with DurableJournal(
            journal_path, session.experiment_id, session.session_id, global_request_ids=True
        ) as journal:
            api = DiplomacyTools(journal, session)
            before_probes = _run_snapshots(session, artifact / "before" / "probes")
            before_control = _control_summary(before_probes["control_state"]["snapshot"])
            before_diplomat = _public_diplomat_snapshot(before_probes)
            before_queries = _query_guarantee_pair(
                api, args.recipient, artifact / "before" / "queries.json"
            )
            before_relation = _relation_pair(before_queries)
            capabilities = sorted(session.installation_capabilities())
            before_baseline = {
                "health_ready": health_before.get("status") == "ready"
                and health_before.get("complete") is True,
                "health_date_matches_expected": health_before.get("date_raw") == args.expected_date_raw,
                "date_matches_expected": before_control.get("date_raw") == args.expected_date_raw,
                "player_slot_is_por": before_control.get("player_slot") == _PLAYER_SLOT,
                "paused": before_control.get("paused_flag") == 1,
                "four_snapshots_complete": _snapshots_complete(before_probes),
                "query_pair_complete": _query_pair_complete(before_queries),
                "query_relation_consistent": before_relation.get("consistent") is True,
                "relation_before_expected": before_relation.get("guarantee_active") is expected_before,
                "guarantee_submission_ack": "native_guarantee_submission" in capabilities,
                "guarantee_query_ack": "native_guarantee_query" in capabilities,
            }
            report["before"] = {
                "health": health_before,
                "control": before_control,
                "queries": before_queries,
                "relation": before_relation,
                "diplomat": before_diplomat,
                "probes": _public_probe_records(before_probes),
                "baseline": before_baseline,
                "capabilities": capabilities,
            }
            if not all(before_baseline.values()):
                raise ExperimentStop(
                    "BASELINE_NOT_READY_FOR_EXPECTED_RELATION",
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
                    "status_history": [execution.get("status")]
                    if isinstance(execution, dict) else [],
                    "terminal": isinstance(execution, dict)
                    and execution.get("status") in _TERMINAL_STATUSES,
                    "final": api.get_diplomatic_result(args.request_id),
                    "timeout_bound_seconds": _POLL_SECONDS,
                }
            final = poll.get("final")
            report["poll"] = poll

            after_queries = _query_guarantee_pair(
                api, args.recipient, artifact / "after" / "queries.json"
            )
            after_probes = _run_snapshots(session, artifact / "after" / "probes")
            after_control = _control_summary(after_probes["control_state"]["snapshot"])
            after_diplomat = _public_diplomat_snapshot(after_probes)
            after_health = session.health()
            after_relation = _relation_pair(after_queries)
            report["after"] = {
                "health": after_health,
                "control": after_control,
                "queries": after_queries,
                "relation": after_relation,
                "diplomat": after_diplomat,
                "probes": _public_probe_records(after_probes),
                "baseline": {
                    "health_ready": after_health.get("status") == "ready"
                    and after_health.get("complete") is True,
                    "health_date_matches_expected": after_health.get("date_raw") == args.expected_date_raw,
                    "date_matches_expected": after_control.get("date_raw") == args.expected_date_raw,
                    "player_slot_is_por": after_control.get("player_slot") == _PLAYER_SLOT,
                    "paused": after_control.get("paused_flag") == 1,
                    "four_snapshots_complete": _snapshots_complete(after_probes),
                    "query_pair_complete": _query_pair_complete(after_queries),
                    "query_relation_consistent": after_relation.get("consistent") is True,
                    "date_same_as_before": after_control.get("date_raw") == before_control.get("date_raw"),
                },
            }
            if isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES:
                duplicate = api.execute_diplomatic_action(
                    args.request_id, args.action_id, _ACTOR, args.recipient,
                    phase="initiate", parameters={},
                )
                report["idempotency_call_count"] = 1
            report["duplicate"] = duplicate

        with DurableJournal(
            journal_path, session.experiment_id, session.session_id, global_request_ids=True
        ) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(args.request_id)
        report["reopened_result"] = reopened_result

        before_relation_value = before_relation.get("guarantee_active")
        after_relation_value = after_relation.get("guarantee_active")
        result_checks = _result_matches(
            args.action_id, args.expected_outcome, args.expected_date_raw,
            args.recipient, before_relation_value, after_relation_value, final,
        )
        report["result_checks"] = result_checks
        stable = _stable_result(final)
        reopened_stable = _stable_result(reopened_result)
        after_baseline = report["after"]["baseline"]
        report["persistence"] = {
            "stable_result": stable,
            "reopened_stable_result": reopened_stable,
            "same_public_result": stable == reopened_stable,
        }
        terminal = isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES
        checks = {
            "submitted_true": isinstance(execution, dict) and execution.get("submitted") is True,
            "expected_terminal_result": terminal and result_checks.get("all") is True,
            "duplicate_idempotent": (
                isinstance(duplicate, dict)
                and duplicate.get("idempotent") is True
                and _stable_result(duplicate) == stable
            ) if terminal else False,
            "journal_survives_reopen": stable == reopened_stable,
            "after_baseline_unchanged": all(after_baseline.values()),
            "native_relation_matches_query": (
                isinstance(result_checks.get("public_result"), dict)
                and result_checks["public_result"].get("guarantee_after")
                is after_relation_value
            ),
            "four_snapshots_before": report["before"]["baseline"]["four_snapshots_complete"],
            "four_snapshots_after": after_baseline["four_snapshots_complete"],
            "por_paused_date_identity": (
                before_control.get("player_slot") == _PLAYER_SLOT
                and after_baseline["player_slot_is_por"]
                and before_control.get("paused_flag") == 1
                and after_baseline["paused"]
                and before_control.get("date_raw") == after_control.get("date_raw")
                == args.expected_date_raw
            ),
            "one_execute_and_one_idempotency_call": (
                report["execute_call_count"] == 1
                and report["idempotency_call_count"] == (1 if terminal else 0)
            ),
            "build_dll_source_bound": report.get("build_binding", {}).get(
                "installation_matches_build_manifest"
            ) is True,
            "relation_evidence_is_public_relationship_state": (
                before_relation.get("source") == "relationship_state"
                and after_relation.get("source") == "relationship_state"
            ),
        }
        report["checks"] = checks
        if terminal:
            report["status"] = "passed" if all(checks.values()) else "failed"
        else:
            report["status"] = "pending" if all(
                value for key, value in checks.items()
                if key in (
                    "journal_survives_reopen", "after_baseline_unchanged",
                    "four_snapshots_before", "four_snapshots_after",
                    "por_paused_date_identity", "build_dll_source_bound",
                    "relation_evidence_is_public_relationship_state",
                )
            ) else "failed"
    except ExperimentStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {
            "code": "UNEXPECTED_OPERATOR_ERROR",
            "type": type(error).__name__,
            "message": str(error),
        }
    finally:
        if isinstance(log_start, int) and log_start >= 0:
            report["native_events"] = _copy_log_slice(
                log_path, log_start, artifact / "native-events-slice.jsonl"
            )
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 3 if report["status"] == "pending" else 2


if __name__ == "__main__":
    raise SystemExit(main())
