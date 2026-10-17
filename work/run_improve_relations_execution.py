"""Execute or resume one bounded Improve Relations task operation.

Improve Relations is a one-sided diplomat task.  ``improve_relations`` starts
the task and ``stop_improving_relations`` stops it; neither action waits for a
recipient response.  The operator still uses the shared journal, native
session checks, four read-only snapshots, and bounded native result polling.

The native task result is only accepted when the public result and the native
``native_diplomacy_task_execution_result`` event agree on the family, task
transition, mode, state, request binding, and date.  An unavailable execution
adapter remains ``pending``/unaccepted rather than being reported as success.
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
from work.run_royal_marriage_execution import (  # noqa: E402
    ExperimentStop,
    _installation_binding,
    _poll_royal_result,
    _public_probe_records,
    _query_is_complete,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    PROBE_SPECS,
    _control_summary,
    _diplomat_semantics,
    _read_json,
    _run_snapshots,
)


_ACTOR = "FRA"
_PLAYER_SLOT = 189  # POR in the controlled experiment
_DEFAULT_DATE_RAW = 56459880
_ACTIONS = ("improve_relations", "stop_improving_relations")
_OUTCOMES = ("executed",)
_TERMINAL_STATUSES = frozenset(
    ("accepted", "rejected", "executed", "invalidated", "expired", "conflict")
)
_TAG_RE = re.compile(r"[A-Z]{3}\Z")
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_IMPROVE_SELECTOR = 11739  # 0x2ddb; native Improve Relations selector
_IMPROVE_FAMILY = "improve_relations"


def _new_artifact(parent: Path, prefix: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    for _ in range(32):
        candidate = parent / f"{prefix}-{uuid.uuid4().hex}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise ExperimentStop("ARTIFACT_DIRECTORY_COLLISION", str(parent))


def _query_improve_pair(api: DiplomacyTools, recipient: str,
                        destination: Path,
                        action_pair: tuple[str, str] | None = None
                        ) -> dict[str, dict[str, object]]:
    """Query a two-action task pair; the default remains Improve Relations."""

    actions = action_pair or _ACTIONS
    result: dict[str, dict[str, object]] = {}
    for action_id in actions:
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
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json(destination, result)
    return result


def _identity_text(value: object) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return hex(value).lower()
    if isinstance(value, str):
        return value.lower()
    return None


def _tag_from_identity(value: object) -> str | None:
    """Decode the low three bytes of a native country identity handle."""

    text = _identity_text(value)
    if text is None:
        return None
    try:
        number = int(text, 16)
        tag = (number & 0xFFFFFF).to_bytes(3, "little").decode("ascii")
    except (ValueError, OverflowError, UnicodeDecodeError):
        return None
    return tag if _TAG_RE.fullmatch(tag) else None


def _record_present(value: object) -> bool:
    if value is None or value is False or value == 0:
        return False
    if isinstance(value, str) and value.lower() in ("0", "0x0", "0x00"):
        return False
    return True


def _task_observation(snapshot: object, actor: str, recipient: str,
                      selector: int = _IMPROVE_SELECTOR,
                      family: str = _IMPROVE_FAMILY) -> dict[str, object]:
    """Find the active native task record for actor/recipient.

    The probe intentionally observes only the bounded FRA/ENG/POR country
    objects.  The recipient may be outside that set, so the recipient tag is
    also decoded from ``raw_recipient_88`` when its country object is absent.
    A missing or structurally incomplete probe yields ``task=None`` rather
    than silently treating the task as absent.
    """

    if not isinstance(snapshot, dict):
        return {"task": None, "evidence_complete": False, "matched_entries": []}
    countries = snapshot.get("countries")
    if not isinstance(countries, list):
        return {"task": None, "evidence_complete": False, "matched_entries": []}
    actor_country = next(
        (item for item in countries
         if isinstance(item, dict) and item.get("tag") == actor), None
    )
    recipient_country = next(
        (item for item in countries
         if isinstance(item, dict) and item.get("tag") == recipient), None
    )
    actor_handle = actor_country.get("handle") if isinstance(actor_country, dict) else None
    recipient_handle = recipient_country.get("handle") if isinstance(recipient_country, dict) else None
    if not isinstance(actor_country, dict) or not isinstance(actor_country.get("diplomacy_entries"), list):
        return {
            "task": None, "evidence_complete": False, "matched_entries": [],
            "actor_handle": actor_handle, "recipient_handle": recipient_handle,
        }

    matched: list[dict[str, object]] = []
    for country in countries:
        if not isinstance(country, dict):
            continue
        entries = country.get("diplomacy_entries")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            action_type = entry.get("raw_action_type_a8")
            try:
                action_matches = int(action_type) == selector
            except (TypeError, ValueError):
                action_matches = False
            if not action_matches:
                continue
            raw_actor = entry.get("raw_actor_80")
            actor_matches = (
                actor_handle is not None
                and _identity_text(raw_actor) == _identity_text(actor_handle)
            )
            if not actor_matches and _tag_from_identity(raw_actor) == actor:
                actor_matches = True
            raw_recipient = entry.get("raw_recipient_88")
            recipient_matches = (
                recipient_handle is not None
                and _identity_text(raw_recipient) == _identity_text(recipient_handle)
            )
            if not recipient_matches and _tag_from_identity(raw_recipient) == recipient:
                recipient_matches = True
            if not actor_matches or not recipient_matches:
                continue
            active_raw = entry.get("active_raw_18")
            try:
                active = int(active_raw) == 2
            except (TypeError, ValueError):
                active = False
            matched.append({
                "countrytag": country.get("tag"),
                "active": active and _record_present(entry.get("record")),
                "record_present": _record_present(entry.get("record")),
                "entry": entry,
            })
    return {
        "task": any(item.get("active") is True for item in matched),
        "evidence_complete": True,
        "matched_entries": matched,
        "actor_handle": actor_handle,
        "recipient_handle": recipient_handle,
        "recipient_identity_source": "snapshot_handle" if recipient_handle is not None else "entry_low_24_bits",
        "selector": selector,
        "family": family,
    }


def _diplomat_evidence(probes: dict[str, dict[str, object]],
                       recipient: str,
                       selector: int = _IMPROVE_SELECTOR,
                       family: str = _IMPROVE_FAMILY) -> dict[str, object]:
    item = probes.get("diplomats", {})
    snapshot = item.get("snapshot") if isinstance(item, dict) else None
    try:
        semantics = _diplomat_semantics(snapshot) if isinstance(snapshot, dict) else None
        semantics_error = None
    except Exception as error:
        semantics = None
        semantics_error = {"type": type(error).__name__, "message": str(error)}
    task = _task_observation(snapshot, _ACTOR, recipient, selector, family)
    return {
        "snapshot": snapshot,
        "snapshot_path": item.get("snapshot_path") if isinstance(item, dict) else None,
        "snapshot_completeness": item.get("snapshot_completeness") if isinstance(item, dict) else None,
        "semantics": semantics,
        "semantics_error": semantics_error,
        "task": task,
    }


def _query_baseline(query: object, action_id: str) -> dict[str, object]:
    legality = query.get("legality") if isinstance(query, dict) else None
    return {
        "query_complete": _query_is_complete(query, action_id),
        "action_id_matches": isinstance(query, dict) and query.get("action_id") == action_id,
        "session_ready": (
            isinstance(query, dict) and isinstance(query.get("session"), dict)
            and query["session"].get("status") == "ready"
        ),
        "legality_complete": isinstance(legality, dict) and legality.get("complete") is True,
        "legality_available": isinstance(legality, dict) and legality.get("status") == "available",
    }


def _snapshot_baseline(health: dict[str, object], control: dict[str, object],
                       probes: dict[str, dict[str, object]],
                       diplomat: dict[str, object], queries: dict[str, dict[str, object]],
                       action_id: str, expected_task: bool,
                       expected_date_raw: int,
                       require_selected_available: bool = True) -> dict[str, object]:
    query = _query_baseline(queries.get(action_id), action_id)
    task_evidence = diplomat.get("task") if isinstance(diplomat, dict) else None
    task = task_evidence.get("task") if isinstance(task_evidence, dict) else None
    return {
        "health_ready": health.get("status") == "ready" and health.get("complete") is True,
        "health_date_matches_expected": health.get("date_raw") == expected_date_raw,
        "date_matches_expected": control.get("date_raw") == expected_date_raw,
        "player_slot_is_por": control.get("player_slot") == _PLAYER_SLOT,
        "paused": control.get("paused_flag") == 1,
        "four_snapshots_complete": _snapshots_complete(probes),
        "diplomat_snapshot_complete": (
            isinstance(diplomat.get("snapshot_completeness"), dict)
            and diplomat["snapshot_completeness"].get("complete") is True
        ),
        "diplomat_semantics_complete": diplomat.get("semantics") is not None,
        "task_evidence_complete": diplomat.get("task", {}).get("evidence_complete") is True,
        "task_matches_expected": task is expected_task,
        "selected_query_complete": query["query_complete"],
        "selected_query_legality_available": (
            query["legality_available"] if require_selected_available else True
        ),
        "selected_query_legality_complete": query["legality_complete"],
    }


def _query_task_transition(queries: object, expected_task: bool,
                           action_pair: tuple[str, str] | None = None) -> bool:
    if not isinstance(queries, dict):
        return False
    start_action, stop_action = action_pair or _ACTIONS
    start = queries.get(start_action)
    stop = queries.get(stop_action)
    start_legality = start.get("legality") if isinstance(start, dict) else None
    stop_legality = stop.get("legality") if isinstance(stop, dict) else None
    if not isinstance(start_legality, dict) or not isinstance(stop_legality, dict):
        return False
    start_visibility = start.get("visibility") if isinstance(start, dict) else None
    stop_visibility = stop.get("visibility") if isinstance(stop, dict) else None
    if not isinstance(start_visibility, dict) or not isinstance(stop_visibility, dict):
        return False
    # Task selection and send legality are distinct.  After recall, Start is
    # visible while a returning diplomat can still make it unavailable.
    return (
        _query_is_complete(start, start_action)
        and _query_is_complete(stop, stop_action)
        and start_visibility.get("status") == ("hidden" if expected_task else "visible")
        and stop_visibility.get("status") == ("visible" if expected_task else "hidden")
        and start_legality.get("status") in (
            ("unavailable",) if expected_task else ("available", "unavailable"))
        and (stop_legality.get("status") == "available") is expected_task
    )


def _result_matches(action_id: str, recipient: str, expected_outcome: str,
                    expected_date_raw: int, before_task: object,
                    after_task: object, result: object,
                    family: str = _IMPROVE_FAMILY,
                    action_pair: tuple[str, str] | None = None
                    ) -> dict[str, object]:
    if not isinstance(result, dict):
        return {"status": False, "binding": False, "task": False,
                "native": False, "proof": False, "event": False, "all": False}
    public = result.get("result")
    if not isinstance(public, dict):
        return {"status": False, "binding": False, "task": False,
                "native": False, "proof": False, "event": False, "all": False}
    status_ok = (
        result.get("status") == expected_outcome
        and result.get("game_outcome") == expected_outcome
    )
    binding_ok = all(public.get(field) == expected for field, expected in (
        ("action_id", action_id), ("actor", _ACTOR),
        ("recipient", recipient), ("phase", "initiate"),
        ("date_raw", expected_date_raw),
    ))
    start_action = (action_pair or _ACTIONS)[0]
    expected_after = action_id == start_action
    task_ok = (
        public.get("family") == family
        and public.get("task_before") is before_task
        and public.get("task_after") is after_task
        and before_task is (not expected_after)
        and after_task is expected_after
    )
    native_ok = (
        public.get("native_state") == 0
        and public.get("native_variant") == (1 if action_id == start_action else 0)
    )
    proof_ok = (
        public.get("execution_verified") is True
        and public.get("request_binding_verified") is True
    )
    event_ok = public.get("event") == "native_diplomacy_task_execution_result"
    return {
        "status": status_ok,
        "binding": binding_ok,
        "task": task_ok,
        "native": native_ok,
        "proof": proof_ok,
        "event": event_ok,
        "all": status_ok and binding_ok and task_ok and native_ok and proof_ok and event_ok,
        "public_result": public,
    }


def _unsupported_execution(execution: object, final: object) -> bool:
    """Recognize an unimplemented adapter without turning it into success."""

    values: list[object] = [execution, final]
    for value in values:
        if not isinstance(value, dict):
            continue
        reason = value.get("reason")
        if isinstance(reason, dict) and reason.get("code") in (
                "EXECUTION_ADAPTER_UNIMPLEMENTED",
                "NATIVE_IMPROVE_RELATIONS_SUBMISSION_UNAVAILABLE",
                "NATIVE_SPY_NETWORK_SUBMISSION_UNAVAILABLE",
                "NATIVE_TASK_EXECUTION_UNIMPLEMENTED"):
            return True
        if value.get("submitted") is False and value.get("status") in (
                "invalidated", "unknown"):
            return True
    return False


def _poll_task_result(api: DiplomacyTools, request_id: str) -> dict[str, object]:
    # Reuse the same bounded polling implementation used by the Royal operator.
    return _poll_royal_result(api, request_id)


def _public_before_after(probes: dict[str, dict[str, object]],
                         diplomat: dict[str, object],
                         task_expected: bool | None = None) -> dict[str, object]:
    result = {
        "probes": _public_probe_records(probes),
        "diplomats_snapshot": diplomat.get("snapshot"),
        "diplomat_semantics": diplomat.get("semantics"),
        "diplomat_snapshot_path": diplomat.get("snapshot_path"),
        "diplomat_snapshot_completeness": diplomat.get("snapshot_completeness"),
        "task": diplomat.get("task"),
    }
    if task_expected is not None:
        result["expected_task"] = task_expected
    return result


def _status_for_report(report: dict[str, object], final: object,
                       result_checks: dict[str, object],
                       execution: object | None) -> str:
    checks = report.get("checks")
    result_dependent = frozenset({
        "submitted_true", "task_before_expected", "task_after_expected",
        "task_transition", "query_task_transition",
        "expected_terminal_result", "duplicate_idempotent",
    })
    if not isinstance(checks, dict) or not all(
            value is True for key, value in checks.items()
            if key not in result_dependent):
        return "failed"
    if isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES:
        if result_checks.get("all") is True and checks.get("duplicate_idempotent") is True:
            return "passed"
        if _unsupported_execution(execution, final):
            return "pending"
        return "failed"
    return "pending"


def _resume_existing_artifact(resume_artifact: Path,
                              explicit_installation: Path | None,
                              expected_date_override: int | None) -> int:
    """Read an existing request journal and finish observation without execute."""

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
        raise ExperimentStop("RESUME_ARGUMENTS_INVALID", "source report lacks a valid Improve request")

    output = _new_artifact(resume_artifact.parent, "improve-relations-resume")
    log_path = installation.parent / "control-probe.jsonl"
    log_start = original.get("log_start_offset")
    if not isinstance(log_start, int):
        native_meta = original.get("native_events")
        log_start = native_meta.get("start_offset") if isinstance(native_meta, dict) else None
    report: dict[str, object] = {
        "status": "unknown", "mode": "resume_read_only",
        "resume_artifact": str(resume_artifact), "artifact": str(output),
        "action_id": action_id, "actor": _ACTOR, "recipient": recipient,
        "phase": "initiate", "parameters": {}, "request_id": request_id,
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
        report["build_binding"]["loaded_dll_sha256"] = session.record.get("dll_sha256")
        health_before = wait_runtime_ready(session, restore_minimized=True)
        after_probes = _run_snapshots(session, output / "after" / "probes")
        after_diplomat = _diplomat_evidence(after_probes, recipient)
        after_control = _control_summary(after_probes["control_state"]["snapshot"])
        after_health = session.health()
        with DurableJournal(resume_artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            first = api.get_diplomatic_result(request_id)
            after_queries = _query_improve_pair(api, recipient, output / "after" / "queries.json")
            final = api.get_diplomatic_result(request_id)
            duplicate = None
            if isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES:
                duplicate = api.execute_diplomatic_action(
                    request_id, action_id, _ACTOR, recipient,
                    phase="initiate", parameters={},
                )
                report["idempotency_call_count"] = 1
        with DurableJournal(resume_artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(request_id)

        before = original.get("before") if isinstance(original.get("before"), dict) else {}
        before_task_record = before.get("task") if isinstance(before.get("task"), dict) else {}
        before_task = before_task_record.get("task")
        expected_before = action_id == "stop_improving_relations"
        expected_after = not expected_before
        after_task = after_diplomat["task"].get("task") if isinstance(after_diplomat.get("task"), dict) else None
        after_baseline = _snapshot_baseline(
            after_health, after_control, after_probes, after_diplomat,
            after_queries, action_id, expected_after, expected_date_raw,
            require_selected_available=False,
        )
        report["before_source"] = before
        report["after"] = {
            "health_before_snapshots": health_before, "health": after_health,
            "control": after_control, "queries": after_queries,
            **_public_before_after(after_probes, after_diplomat, expected_after),
            "query_task_transition": _query_task_transition(after_queries, expected_after),
            "baseline": after_baseline,
        }
        report["result_reads"] = {
            "first": first, "final": final, "reopened": reopened_result,
            "terminal": isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES,
        }
        result_checks = _result_matches(
            action_id, recipient, expected_outcome, expected_date_raw,
            before_task, after_task, final,
        )
        stable = _stable_result(final)
        reopened_stable = _stable_result(reopened_result)
        report["observations"] = {
            "result": result_checks,
            "task_before": before_task, "task_after": after_task,
            "stop_allows_diplomat_returning": action_id == "stop_improving_relations",
        }
        report["persistence"] = {
            "stable_result": stable, "reopened_stable_result": reopened_stable,
            "same_public_result": stable == reopened_stable,
        }
        report["duplicate"] = duplicate
        terminal = isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES
        report["checks"] = {
            "no_new_execute_submission": report["execute_call_count"] == 0,
            "task_before_source_expected": before_task is expected_before,
            "task_after_expected": after_task is expected_after,
            "query_task_transition": report["after"]["query_task_transition"],
            "after_baseline_unchanged": all(after_baseline.values()),
            "four_snapshots_after": after_baseline["four_snapshots_complete"],
            "por_paused_date_identity": (
                after_control.get("player_slot") == _PLAYER_SLOT
                and after_control.get("paused_flag") == 1
                and after_control.get("date_raw") == expected_date_raw
            ),
            "journal_survives_reopen": stable == reopened_stable,
            "build_dll_source_bound": report.get("build_binding", {}).get(
                "installation_matches_build_manifest") is True,
        }
        if terminal:
            report["checks"]["expected_terminal_result"] = result_checks.get("all") is True
            report["checks"]["duplicate_idempotent"] = (
                isinstance(duplicate, dict) and duplicate.get("idempotent") is True
                and _stable_result(duplicate) == stable
            )
        else:
            report["checks"]["idempotency_deferred_while_nonterminal"] = (
                report["idempotency_call_count"] == 0
            )
        report["status"] = _status_for_report(report, final, result_checks, None)
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
                        help="Resume an existing artifact without publishing a new request")
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
        except Exception as error:
            print(json.dumps({"status": "failed", "error": {
                "code": "UNEXPECTED_RESUME_ERROR", "type": type(error).__name__,
                "message": str(error),
            }}, ensure_ascii=False), flush=True)
            return 2

    required = ("installation", "action_id", "recipient", "request_id", "expected_outcome")
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join(
            "--" + name.replace("_", "-") for name in missing))
    if args.expected_date_raw is None:
        args.expected_date_raw = _DEFAULT_DATE_RAW

    installation = args.installation.expanduser().resolve(strict=True)
    artifact = _new_artifact(installation.parent, "improve-relations-execution")
    log_path = installation.parent / "control-probe.jsonl"
    report: dict[str, object] = {
        "status": "unknown", "mode": "execute", "artifact": str(artifact),
        "action_id": args.action_id, "actor": _ACTOR, "recipient": args.recipient,
        "phase": "initiate", "parameters": {}, "request_id": args.request_id,
        "expected_outcome": args.expected_outcome,
        "expected_date_raw": args.expected_date_raw,
        "execute_call_count": 0, "idempotency_call_count": 0, "checks": {},
    }
    log_start: int | None = None
    execution: object | None = None
    final: object = None
    result_checks: dict[str, object] = {"all": False}

    try:
        if not _TAG_RE.fullmatch(args.recipient):
            raise ExperimentStop("RECIPIENT_TAG_INVALID", "recipient must match [A-Z]{3}")
        if not _REQUEST_ID_RE.fullmatch(args.request_id):
            raise ExperimentStop("REQUEST_ID_INVALID", "request id must match [A-Za-z0-9_-]{1,64}")
        if args.expected_outcome != "executed":
            raise ExperimentStop(
                "EXPECTED_OUTCOME_ACTION_MISMATCH",
                "Improve Relations is a one-sided task and can only finish as executed",
            )
        if not isinstance(args.expected_date_raw, int) or isinstance(args.expected_date_raw, bool):
            raise ExperimentStop("EXPECTED_DATE_RAW_INVALID", "expected date must be an integer")

        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session"] = {
            "session_id": session.session_id, "experiment_id": session.experiment_id,
            "pid": session.record.get("pid"), "dll_sha256": session.record.get("dll_sha256"),
        }
        report["build_binding"]["loaded_dll_sha256"] = session.record.get("dll_sha256")
        log_start = log_path.stat().st_size
        report["log_start_offset"] = log_start
        health_before = wait_runtime_ready(session, restore_minimized=True)
        capabilities = sorted(session.installation_capabilities())
        report["preflight"] = {"health": health_before, "capabilities": capabilities}
        if health_before.get("status") != "ready":
            raise ExperimentStop("SESSION_NOT_READY", json.dumps(health_before, ensure_ascii=False))

        expected_before = args.action_id == "stop_improving_relations"
        expected_after = not expected_before
        journal_path = artifact / "diplomacy.sqlite3"
        with DurableJournal(journal_path, session.experiment_id, session.session_id,
                            global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            before_probes = _run_snapshots(session, artifact / "before" / "probes")
            before_diplomat = _diplomat_evidence(before_probes, args.recipient)
            before_control = _control_summary(before_probes["control_state"]["snapshot"])
            before_queries = _query_improve_pair(
                api, args.recipient, artifact / "before" / "queries.json")
            before_baseline = _snapshot_baseline(
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
                poll = _poll_task_result(api, args.request_id)
            else:
                poll = {
                    "calls": 1, "status_history": [execution.get("status")]
                    if isinstance(execution, dict) else [],
                    "terminal": isinstance(execution, dict)
                    and execution.get("status") in _TERMINAL_STATUSES,
                    "final": api.get_diplomatic_result(args.request_id),
                    "timeout_bound_seconds": _POLL_SECONDS,
                }
            final = poll.get("final")
            report["poll"] = poll

            after_queries = _query_improve_pair(
                api, args.recipient, artifact / "after" / "queries.json")
            after_probes = _run_snapshots(session, artifact / "after" / "probes")
            after_diplomat = _diplomat_evidence(after_probes, args.recipient)
            after_control = _control_summary(after_probes["control_state"]["snapshot"])
            after_health = session.health()
            after_baseline = _snapshot_baseline(
                after_health, after_control, after_probes, after_diplomat,
                after_queries, args.action_id, expected_after, args.expected_date_raw,
                require_selected_available=False,
            )
            report["after"] = {
                "health": after_health, "control": after_control,
                "queries": after_queries,
                **_public_before_after(after_probes, after_diplomat, expected_after),
                "query_task_transition": _query_task_transition(after_queries, expected_after),
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
        )
        report["observations"] = {
            "result": result_checks,
            "task_before": before_task, "task_after": after_task,
            "native_state_expected": 0,
            "native_variant_expected": 1 if args.action_id == "improve_relations" else 0,
            "stop_allows_diplomat_returning": args.action_id == "stop_improving_relations",
        }
        report["persistence"] = {
            "stable_result": stable,
            "reopened_stable_result": reopened_stable,
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
            "before_four_snapshots": report["before"]["baseline"]["four_snapshots_complete"],
            "after_four_snapshots": report["after"]["baseline"]["four_snapshots_complete"],
            "before_diplomat_snapshot_complete": report["before"]["baseline"]["diplomat_snapshot_complete"],
            "after_diplomat_snapshot_complete": report["after"]["baseline"]["diplomat_snapshot_complete"],
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
        if log_start is not None:
            report["native_events"] = _copy_log_slice(
                log_path, log_start, artifact / "native-events-slice.jsonl"
            )
        _write_json(artifact / "report.json", report)

    print(json.dumps({"status": report["status"], "artifact": str(artifact)},
                     ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 3 if report["status"] == "pending" else 2


if __name__ == "__main__":
    raise SystemExit(main())
