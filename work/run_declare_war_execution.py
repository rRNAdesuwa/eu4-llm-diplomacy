#!/usr/bin/env python3
"""Execute one parameter-bound native Declare War request or read it back.

The operator accepts a CB, province, beneficiary and ally list, performs one
preflight query, publishes at most one unified ``DiplomacyTools`` request, and
records both native Declare War result events.  ``--resume-artifact`` only
reads the existing journal and current native state; it never publishes a
second business request.

The game must already be running in the requested installation.  This module
does not advance time, save, install, or restart the game.
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
from work.run_improve_relations_execution import _new_artifact  # noqa: E402
from work.run_royal_marriage_execution import (  # noqa: E402
    ExperimentStop,
    _installation_binding,
    _poll_royal_result,
    _public_probe_records,
    _snapshots_complete,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _read_json,
    _run_snapshots,
)


_ACTOR = "FRA"
_PLAYER_SLOT = 189  # POR in the controlled experiment
_DEFAULT_DATE_RAW = 56500920
_ACTION = "declare_war"
_FAMILY = "declare_war"
_QUERY_CAPABILITY = "native_declare_war_query"
_SUBMISSION_CAPABILITY = "native_declare_war_submission"
_TERMINAL_STATUSES = frozenset(
    ("accepted", "rejected", "executed", "invalidated", "expired", "conflict")
)
_TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_CB_RE = re.compile(r"[A-Za-z0-9_]{1,128}\Z")


def _selection_parameters(
    casus_belli: object,
    province_id: object,
    beneficiary: object,
    call_allies: object,
) -> dict[str, object]:
    """Validate the operator's flat arguments and return QUERY3 shape."""

    if not isinstance(casus_belli, str) or _CB_RE.fullmatch(casus_belli) is None:
        raise ExperimentStop("CASUS_BELLI_INVALID", "casus belli must be an ASCII identifier")
    if isinstance(province_id, bool) or not isinstance(province_id, int):
        raise ExperimentStop("PROVINCE_ID_INVALID", "province must be an integer")
    if province_id != -1 and not 1 <= province_id <= 2147483647:
        raise ExperimentStop("PROVINCE_ID_INVALID", "province must be -1 or a positive 32-bit id")
    if (not isinstance(beneficiary, str)
            or (beneficiary != "---" and _TAG_RE.fullmatch(beneficiary) is None)):
        raise ExperimentStop("BENEFICIARY_INVALID", "beneficiary must be --- or a country tag")
    if not isinstance(call_allies, list):
        raise ExperimentStop("CALL_ALLIES_INVALID", "call_allies must be a list")
    if len(call_allies) > 32 or any(
            not isinstance(tag, str) or _TAG_RE.fullmatch(tag) is None
            for tag in call_allies):
        raise ExperimentStop("CALL_ALLIES_INVALID", "call_allies contains an invalid country tag")
    if casus_belli == "no_casus_belli" and (province_id != -1 or beneficiary != "FRA"):
        raise ExperimentStop(
            "NO_CASUS_BELLI_CONTEXT_INVALID",
            "no_casus_belli requires province=-1 and beneficiary=FRA",
        )
    return {
        "casus_belli": casus_belli,
        "war_goal": {"province_id": province_id, "beneficiary": beneficiary},
        "call_allies": list(call_allies),
    }


def _query_declare_war(
    api: DiplomacyTools,
    recipient: str,
    parameters: dict[str, object],
    destination: Path,
) -> dict[str, object]:
    try:
        value = api.inspect_diplomatic_action(
            _ACTION, _ACTOR, recipient, phase="initiate", parameters=parameters
        )
        query = value if isinstance(value, dict) else {
            "status": "unknown", "error": "INSPECTION_NOT_OBJECT",
        }
    except Exception as error:  # the report must preserve a bounded failure
        query = {
            "status": "unknown",
            "error_type": type(error).__name__,
            "error": str(error),
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json(destination, query)
    return query


def _query_identity(query: object, recipient: str,
                    parameters: dict[str, object]) -> bool:
    if not isinstance(query, dict):
        return False
    if any(query.get(field) != expected for field, expected in (
            ("action_id", _ACTION), ("actor", _ACTOR),
            ("recipient", recipient), ("family", _FAMILY),
            ("phase", "initiate"))):
        return False
    selected = query.get("parameters")
    return isinstance(selected, dict) and selected.get("requested") == parameters


def _declare_war_query_complete(query: object,
                                parameters: dict[str, object]) -> bool:
    """Validate the selected Declare War coverage contract.

    The public projection currently leaves ``native_rule_components.complete``
    false when candidate enumeration remains a separately reported bounded
    operation.  The selected QUERY3 contract is complete when its explicit
    parameter, candidate, and full-rule fields are complete; requiring the
    aggregate projection bit would reject the real selected query even though
    its legality is available and its single match is proven.
    """

    if not isinstance(query, dict):
        return False
    session = query.get("session")
    visibility = query.get("visibility")
    legality = query.get("legality")
    selected = query.get("parameters")
    coverage = query.get("native_rule_components")
    if not isinstance(coverage, dict):
        coverage = query.get("rule_coverage")
    if (not isinstance(session, dict) or session.get("status") != "ready"
            or not isinstance(visibility, dict)
            or visibility.get("complete") is not True
            or not isinstance(legality, dict)
            or legality.get("complete") is not True
            or not isinstance(selected, dict)
            or selected.get("complete") is not True
            or not isinstance(coverage, dict)):
        return False
    if (query.get("parameter_context_complete") is not True
            or query.get("selection_requested") is not True
            or query.get("selection_matched") is not True
            or query.get("selection_match_count") != 1
            or query.get("full_rules_complete") is not True
            or coverage.get("full_rules_complete") is not True):
        return False
    if parameters.get("casus_belli") != "no_casus_belli":
        candidates = selected.get("candidates")
        if (query.get("candidate_context_complete") is not True
                or coverage.get("candidate_context_complete") is not True
                or query.get("candidate_enumeration_complete") is not True
                or query.get("candidate_cleanup_verified") is not True
                or query.get("candidate_capture_truncated") is True
                or not isinstance(candidates, list)):
            return False
        native_count = query.get("candidate_native_count")
        if type(native_count) is not int or native_count != len(candidates):
            return False
    return True


def _query_contract(query: object, recipient: str,
                    parameters: dict[str, object], *, require_available: bool) -> bool:
    """Check the selected QUERY3 contract without inventing war rules."""

    if (not _query_identity(query, recipient, parameters)
            or not _declare_war_query_complete(query, parameters)):
        return False
    selected = query.get("parameters") if isinstance(query, dict) else None
    legality = query.get("legality") if isinstance(query, dict) else None
    coverage = query.get("native_rule_components") if isinstance(query, dict) else None
    if not isinstance(coverage, dict):
        coverage = query.get("rule_coverage") if isinstance(query, dict) else None
    if (not isinstance(selected, dict) or selected.get("complete") is not True
            or query.get("parameter_context_complete") is not True
            or query.get("selection_requested") is not True
            or query.get("selection_matched") is not True
            or query.get("selection_match_count") != 1
            or not isinstance(legality, dict)
            or not isinstance(coverage, dict)):
        return False
    if require_available and legality.get("status") != "available":
        return False
    return True


def _war_state_pair(snapshot: object, recipient: str) -> dict[str, object]:
    """Project the independent bounded FRA/ENG war association probe.

    ``probe_war_pair.py`` currently covers the fixed FRA/ENG pair.  Its
    native ``war`` values are object handles, so they are retained as opaque
    observations and are never mislabeled as the execution event's integer
    ``war_id``.
    """

    countries = snapshot.get("countries") if isinstance(snapshot, dict) else None
    by_slot = {
        item.get("slot"): item
        for item in countries or []
        if isinstance(item, dict) and isinstance(item.get("slot"), int)
    }
    left = by_slot.get(122)
    right = by_slot.get(46)
    complete = (
        isinstance(countries, list)
        and isinstance(left, dict)
        and isinstance(right, dict)
        and isinstance(left.get("pairs"), list)
        and isinstance(right.get("pairs"), list)
        and snapshot.get("read_only") is True
    )
    left_at_war = (
        isinstance(left, dict)
        and left.get("pair_at_war") is True
    )
    right_at_war = (
        isinstance(right, dict)
        and right.get("pair_at_war") is True
    )
    handles: list[str] = []
    for row in (left, right):
        if not isinstance(row, dict):
            continue
        for pair in row.get("pairs", []):
            if isinstance(pair, dict) and isinstance(pair.get("war"), str):
                handles.append(pair["war"])
    return {
        "source": "probe_war_pair",
        "scope": "FRA_ENG",
        "recipient_supported": recipient == "ENG",
        "complete": complete,
        "pair_at_war": left_at_war and right_at_war,
        "symmetric_pair_flags": left_at_war == right_at_war,
        "war_handles": sorted(set(handles))[:16],
        "war_handle_count": len(set(handles)),
    }


def _result_public(result: object) -> dict[str, object] | None:
    if not isinstance(result, dict):
        return None
    value = result.get("result")
    return value if isinstance(value, dict) else None


def _native_result_auxiliary_contract(public: object) -> dict[str, bool]:
    """Validate nullable native identity/stability result fields.

    The native observer may be unable to map the newly-created war or read
    the stability values in the same frame.  In that case the corresponding
    verified flag is false and the value must remain ``null``; ``0`` is not a
    substitute for an unknown value.  A verified war identity is a
    non-negative integer, while verified stability values are signed
    integers.  These auxiliary fields never replace the authorization proof
    or the observed false-to-true war transition.
    """

    if not isinstance(public, dict):
        return {
            "war_identity_contract": False,
            "stability_contract": False,
            "war_result_pair": False,
        }
    war_verified = public.get("war_identity_verified")
    stability_verified = public.get("stability_verified")
    war_id = public.get("war_id")
    stability_before = public.get("stability_before_raw")
    stability_after = public.get("stability_after_raw")
    war_identity_contract = (
        type(war_verified) is bool
        and ((war_verified and type(war_id) is int and war_id >= 0)
             or (not war_verified and war_id is None))
    )
    stability_contract = (
        type(stability_verified) is bool
        and ((stability_verified and type(stability_before) is int
              and type(stability_after) is int)
             or (not stability_verified
                 and stability_before is None
                 and stability_after is None))
    )
    return {
        "war_identity_contract": war_identity_contract,
        "stability_contract": stability_contract,
        "war_result_pair": war_identity_contract and stability_contract,
    }


def _result_checks(
    final: object,
    expected_outcome: str,
    expected_date_raw: int,
    recipient: str,
    parameters: dict[str, object],
    before_war: dict[str, object],
    after_war: dict[str, object],
) -> dict[str, object]:
    public = _result_public(final)
    auxiliary = _native_result_auxiliary_contract(public)
    checks: dict[str, object] = {
        "status": isinstance(final, dict)
        and final.get("status") == expected_outcome
        and final.get("game_outcome") == expected_outcome,
        "binding": False,
        "war_transition": False,
        "native": False,
        "proof": False,
        "event": False,
        "war_identity_contract": auxiliary["war_identity_contract"],
        "stability_contract": auxiliary["stability_contract"],
        "war_result_pair": auxiliary["war_result_pair"],
        "all": False,
    }
    if public is None:
        checks["public_result"] = None
        return checks
    goal = parameters.get("war_goal", {})
    checks["binding"] = all(
        public.get(field) == expected
        for field, expected in (
            ("event", "native_declare_war_execution_result"),
            ("action_id", _ACTION), ("family", _FAMILY),
            ("actor", _ACTOR), ("recipient", recipient),
            ("phase", "initiate"), ("date_raw", expected_date_raw),
            ("casus_belli", parameters.get("casus_belli")),
            ("war_goal_province", goal.get("province_id")),
            ("war_goal_beneficiary", goal.get("beneficiary")),
        )
    )
    if expected_outcome == "executed":
        checks["native"] = (
            public.get("outcome") == "executed"
            and public.get("war_before") is False
            and public.get("war_after") is True
        )
        checks["proof"] = (
            public.get("execution_verified") is True
            and public.get("request_binding_verified") is True
        )
        checks["war_transition"] = (
            before_war.get("recipient_supported") is True
            and after_war.get("recipient_supported") is True
            and before_war.get("complete") is True
            and after_war.get("complete") is True
            and before_war.get("pair_at_war") is False
            and after_war.get("pair_at_war") is True
        )
        # A null pair with both verified flags false is a valid auxiliary
        # result.  Authorization proof and the symmetric war transition above
        # remain mandatory for an executed result.
        checks["war_identity_contract"] = auxiliary["war_identity_contract"]
        checks["stability_contract"] = auxiliary["stability_contract"]
        checks["war_result_pair"] = auxiliary["war_result_pair"]
    else:
        # Unknown is explicitly preserved as unknown.  It can never pass the
        # execution contract, even when the request was accepted by transport.
        checks["native"] = public.get("outcome") == "unknown"
        checks["proof"] = (
            public.get("execution_verified") is False
            and public.get("request_binding_verified") is False
        )
        checks["war_transition"] = public.get("war_after") is False
        checks["war_identity_contract"] = auxiliary["war_identity_contract"]
        checks["stability_contract"] = auxiliary["stability_contract"]
        checks["war_result_pair"] = auxiliary["war_result_pair"]
    checks["event"] = public.get("event") == "native_declare_war_execution_result"
    checks["all"] = expected_outcome == "executed" and all(
        checks[key] is True
        for key in ("status", "binding", "war_transition", "native",
                    "proof", "event", "war_result_pair")
    )
    checks["public_result"] = public
    return checks


def _event_records(path: Path, request_id: str, session_id: str) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    try:
        with path.open("rb") as stream:
            for raw in stream:
                if len(raw) > 256 * 1024:
                    continue
                try:
                    value = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    continue
                if (isinstance(value, dict)
                        and value.get("request_id") == request_id
                        and value.get("session_id") == session_id):
                    result.append(value)
                    if len(result) >= 32:
                        break
    except OSError:
        return []
    return result


def _event_checks(events: list[dict[str, object]], parameters: dict[str, object],
                  recipient: str) -> dict[str, bool]:
    goal = parameters.get("war_goal", {})
    submission = next(
        (item for item in events
         if item.get("event") == "native_declare_war_submission_result"), None)
    execution = next(
        (item for item in events
         if item.get("event") == "native_declare_war_execution_result"), None)
    def bound(item: dict[str, object] | None) -> bool:
        return isinstance(item, dict) and all(
            item.get(field) == expected
            for field, expected in (
                ("action_id", _ACTION), ("family", _FAMILY),
                ("actor", _ACTOR), ("recipient", recipient),
                ("phase", "initiate"),
                ("casus_belli", parameters.get("casus_belli")),
                ("war_goal_province", goal.get("province_id")),
                ("war_goal_beneficiary", goal.get("beneficiary")),
            )
        )
    return {
        "submission_event_present": bound(submission)
        and submission.get("submitted") is True,
        "submission_transport_verified": bound(submission)
        and submission.get("transport_verified") is True
        and submission.get("request_binding_verified") is True,
        "execution_event_present": bound(execution),
        "execution_event_bound": bound(execution)
        and execution.get("outcome") in ("executed", "unknown"),
    }


def _after_invariants(
    health: dict[str, object],
    control: dict[str, object],
    probes: dict[str, dict[str, object]],
    before_control: dict[str, object],
    before_query: object,
    after_query: object,
    expected_date_raw: int,
    recipient: str,
    parameters: dict[str, object],
    capabilities: set[str],
) -> dict[str, bool]:
    return {
        "health_ready": health.get("status") == "ready" and health.get("complete") is True,
        "health_date_matches_expected": health.get("date_raw") == expected_date_raw,
        "date_matches_expected": control.get("date_raw") == expected_date_raw,
        "date_same_as_before": control.get("date_raw") == before_control.get("date_raw"),
        "player_slot_is_por": control.get("player_slot") == _PLAYER_SLOT,
        "player_slot_same_as_before": control.get("player_slot") == before_control.get("player_slot"),
        "paused": control.get("paused_flag") == 1,
        "paused_same_as_before": control.get("paused_flag") == before_control.get("paused_flag"),
        "four_snapshots_complete": _snapshots_complete(probes),
        "declare_war_query_ack": _QUERY_CAPABILITY in capabilities,
        "query_identity_stable": (
            _query_identity(before_query, recipient, parameters)
            and _query_identity(after_query, recipient, parameters)
        ),
    }


def _read_source_parameters(report: dict[str, object]) -> dict[str, object]:
    parameters = report.get("parameters")
    if not isinstance(parameters, dict):
        raise ExperimentStop("RESUME_PARAMETERS_MISSING", "source report has no parameters")
    # Calling the bridge validator also keeps resume bound to the same public
    # parameter contract as a fresh execution.
    try:
        normalized = ObserverSession._normalize_declare_war_selection(parameters)
    except (TypeError, ValueError) as error:
        raise ExperimentStop("RESUME_PARAMETERS_INVALID", str(error)) from error
    if normalized is None:
        raise ExperimentStop("RESUME_PARAMETERS_INVALID", "Declare War requires QUERY3 selection")
    return parameters


def _source_result(report: dict[str, object]) -> dict[str, object] | None:
    candidates: list[object] = []
    for key in ("reopened_result", "final_result"):
        value = report.get(key)
        if isinstance(value, dict):
            candidates.append(value.get("result"))
    result_checks = report.get("result_checks")
    if isinstance(result_checks, dict):
        candidates.append(result_checks.get("public_result"))
    poll = report.get("poll")
    if isinstance(poll, dict) and isinstance(poll.get("final"), dict):
        candidates.append(poll["final"].get("result"))
    for value in candidates:
        if isinstance(value, dict):
            return value
    return None


def _resume_existing_artifact(
    resume_artifact: Path,
    explicit_installation: Path | None,
    expected_date_override: int | None,
) -> int:
    resume_artifact = resume_artifact.expanduser().resolve(strict=True)
    original = _read_json(resume_artifact / "report.json")
    if not isinstance(original, dict) or original.get("family") != _FAMILY:
        raise ExperimentStop("RESUME_REPORT_INVALID", "source is not a Declare War report")
    installation_record = original.get("installation")
    recorded_path = installation_record.get("path") if isinstance(installation_record, dict) else None
    installation = (
        explicit_installation.expanduser().resolve(strict=True)
        if explicit_installation is not None
        else Path(recorded_path).expanduser().resolve(strict=True)
        if isinstance(recorded_path, str) else None
    )
    recipient = original.get("recipient")
    request_id = original.get("request_id")
    expected_outcome = original.get("expected_outcome")
    expected_date_raw = expected_date_override if expected_date_override is not None else original.get(
        "expected_date_raw", _DEFAULT_DATE_RAW)
    if (installation is None or not isinstance(recipient, str)
            or _TAG_RE.fullmatch(recipient) is None or recipient == _ACTOR
            or not isinstance(request_id, str) or _REQUEST_ID_RE.fullmatch(request_id) is None
            or expected_outcome not in ("executed", "unknown")
            or not isinstance(expected_date_raw, int) or isinstance(expected_date_raw, bool)):
        raise ExperimentStop("RESUME_ARGUMENTS_INVALID", "source report lacks a valid Declare War request")
    parameters = _read_source_parameters(original)
    output = _new_artifact(resume_artifact.parent, "declare-war-resume")
    log_path = installation.parent / "control-probe.jsonl"
    native_meta = original.get("native_events")
    log_start = original.get("log_start_offset")
    if not isinstance(log_start, int) and isinstance(native_meta, dict):
        log_start = native_meta.get("start_offset")
    report: dict[str, object] = {
        "validator": "run_declare_war_execution.py",
        "version": 1,
        "status": "unknown",
        "mode": "resume_read_only",
        "resume_artifact": str(resume_artifact),
        "artifact": str(output),
        "action_id": _ACTION,
        "actor": _ACTOR,
        "recipient": recipient,
        "family": _FAMILY,
        "phase": "initiate",
        "parameters": parameters,
        "request_id": request_id,
        "expected_outcome": expected_outcome,
        "expected_date_raw": expected_date_raw,
        "execute_call_count": 0,
        "idempotency_call_count": 0,
        "auto_resubmit": False,
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
        health = wait_runtime_ready(session, restore_minimized=True)
        after_probes = _run_snapshots(session, output / "after" / "probes")
        after_control = _control_summary(after_probes["control_state"]["snapshot"])
        with DurableJournal(resume_artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            first = api.get_diplomatic_result(request_id)
            after_query = _query_declare_war(api, recipient, parameters, output / "after" / "query.json")
            final = api.get_diplomatic_result(request_id)
        with DurableJournal(resume_artifact / "diplomacy.sqlite3", session.experiment_id,
                            session.session_id, global_request_ids=True) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(request_id)
        before = original.get("before") if isinstance(original.get("before"), dict) else {}
        before_control = before.get("control") if isinstance(before.get("control"), dict) else {}
        before_query = before.get("query")
        before_war = before.get("war_state_pair") if isinstance(before.get("war_state_pair"), dict) else {}
        after_war = _war_state_pair(after_probes["war_state"]["snapshot"], recipient)
        after_health = session.health()
        capabilities = set(session.installation_capabilities())
        invariants = _after_invariants(after_health, after_control, after_probes,
                                       before_control, before_query, after_query,
                                       expected_date_raw, recipient, parameters, capabilities)
        result_checks = _result_checks(final, expected_outcome, expected_date_raw,
                                       recipient, parameters, before_war, after_war)
        public_result = result_checks.get("public_result")
        stable = _stable_result(final)
        reopened_stable = _stable_result(reopened_result)
        report.update({
            "source_report": {"path": str(resume_artifact), "status": original.get("status")},
            "first_result": first,
            "final_result": final,
            "reopened_result": reopened_result,
            "after": {
                "health": after_health, "control": after_control,
                "query": after_query, "war_state_pair": after_war,
                "probes": _public_probe_records(after_probes),
                "baseline": invariants,
            },
            "result_checks": result_checks,
            "persistence": {"stable_result": stable, "reopened_stable_result": reopened_stable,
                            "same_public_result": stable == reopened_stable},
        })
        if isinstance(public_result, dict):
            report["war_result"] = {
                "war_before": public_result.get("war_before"),
                "war_after": public_result.get("war_after"),
                "war_id": public_result.get("war_id"),
                "stability_before_raw": public_result.get("stability_before_raw"),
                "stability_after_raw": public_result.get("stability_after_raw"),
            }
        terminal = isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES
        checks = {
            "no_execute_submission": report["execute_call_count"] == 0,
            "no_auto_resubmission": report["idempotency_call_count"] == 0 and report["auto_resubmit"] is False,
            "health_ready": health.get("status") == "ready" and health.get("complete") is True,
            "date_matches_expected": after_control.get("date_raw") == expected_date_raw,
            "player_slot_is_por": after_control.get("player_slot") == _PLAYER_SLOT,
            "paused": after_control.get("paused_flag") == 1,
            "four_snapshots_after": _snapshots_complete(after_probes),
            "query_identity_stable": invariants["query_identity_stable"],
            "journal_survives_reopen": stable == reopened_stable,
            "build_dll_source_bound": report.get("build_binding", {}).get(
                "installation_matches_build_manifest") is True,
        }
        if terminal:
            checks["expected_terminal_result"] = result_checks.get("all") is True
            report["status"] = "passed" if all(checks.values()) else "failed"
        else:
            checks["unknown_or_nonterminal_preserved"] = True
            report["status"] = "pending" if all(checks.values()) else "failed"
        report["checks"] = checks
    except ExperimentStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"code": "UNEXPECTED_RESUME_ERROR", "type": type(error).__name__, "message": str(error)}
    finally:
        if isinstance(log_start, int) and log_start >= 0:
            report["native_events"] = _copy_log_slice(log_path, log_start, output / "native-events-slice.jsonl")
        _write_json(output / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(output)}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 3 if report["status"] == "pending" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path)
    parser.add_argument("--recipient")
    parser.add_argument("--request-id")
    parser.add_argument("--casus-belli", "--cb", dest="casus_belli")
    parser.add_argument("--province-id", "--province", dest="province_id", type=int)
    parser.add_argument("--beneficiary")
    parser.add_argument("--call-allies", "--call-ally", dest="call_allies", action="append", default=[])
    parser.add_argument("--expected-outcome", choices=("executed", "unknown"), default="executed")
    parser.add_argument("--expected-date-raw", type=int, default=None)
    parser.add_argument("--resume-artifact", type=Path)
    args = parser.parse_args(argv)
    if args.resume_artifact is not None:
        try:
            return _resume_existing_artifact(args.resume_artifact, args.installation, args.expected_date_raw)
        except ExperimentStop as error:
            print(json.dumps({"status": "failed", "error": {"code": error.code, "message": error.message}}, ensure_ascii=False))
            return 2
        except Exception as error:
            print(json.dumps({"status": "failed", "error": {"code": "UNEXPECTED_RESUME_ERROR", "type": type(error).__name__, "message": str(error)}}, ensure_ascii=False))
            return 2
    required = ("installation", "recipient", "request_id", "casus_belli", "province_id", "beneficiary")
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join("--" + name.replace("_", "-") for name in missing))
    if args.expected_date_raw is None:
        args.expected_date_raw = _DEFAULT_DATE_RAW
    if not isinstance(args.recipient, str) or _TAG_RE.fullmatch(args.recipient) is None or args.recipient == _ACTOR:
        parser.error("--recipient must be a country tag different from FRA")
    if not isinstance(args.request_id, str) or _REQUEST_ID_RE.fullmatch(args.request_id) is None:
        parser.error("--request-id must match [A-Za-z0-9_-]{1,64}")
    try:
        parameters = _selection_parameters(args.casus_belli, args.province_id, args.beneficiary, args.call_allies)
    except ExperimentStop as error:
        parser.error(error.message)
    installation = args.installation.expanduser().resolve()
    artifact = _new_artifact(installation.parent, "declare-war-execution")
    log_path = installation.parent / "control-probe.jsonl"
    log_start: int | None = None
    report: dict[str, object] = {
        "validator": "run_declare_war_execution.py", "version": 1, "status": "unknown",
        "mode": "execute", "artifact": str(artifact), "action_id": _ACTION,
        "actor": _ACTOR, "recipient": args.recipient, "family": _FAMILY, "phase": "initiate",
        "parameters": parameters, "request_id": args.request_id,
        "expected_outcome": args.expected_outcome, "expected_date_raw": args.expected_date_raw,
        "execute_call_count": 0, "idempotency_call_count": 0, "auto_resubmit": False,
        "checks": {},
    }
    try:
        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session"] = {"session_id": session.session_id, "experiment_id": session.experiment_id,
                              "pid": session.record.get("pid"), "dll_sha256": session.record.get("dll_sha256")}
        log_start = log_path.stat().st_size
        report["log_start_offset"] = log_start
        health_before = wait_runtime_ready(session, restore_minimized=True)
        if health_before.get("status") != "ready":
            raise ExperimentStop("SESSION_NOT_READY", json.dumps(health_before, ensure_ascii=False))
        journal_path = artifact / "diplomacy.sqlite3"
        with DurableJournal(journal_path, session.experiment_id, session.session_id, global_request_ids=True) as journal:
            api = DiplomacyTools(journal, session)
            before_probes = _run_snapshots(session, artifact / "before" / "probes")
            before_control = _control_summary(before_probes["control_state"]["snapshot"])
            before_query = _query_declare_war(api, args.recipient, parameters, artifact / "before" / "query.json")
            before_war = _war_state_pair(before_probes["war_state"]["snapshot"], args.recipient)
            capabilities = set(session.installation_capabilities())
            before_baseline = {
                "health_ready": health_before.get("status") == "ready" and health_before.get("complete") is True,
                "health_date_matches_expected": health_before.get("date_raw") == args.expected_date_raw,
                "date_matches_expected": before_control.get("date_raw") == args.expected_date_raw,
                "player_slot_is_por": before_control.get("player_slot") == _PLAYER_SLOT,
                "paused": before_control.get("paused_flag") == 1,
                "four_snapshots_complete": _snapshots_complete(before_probes),
                "query_complete": _query_contract(before_query, args.recipient, parameters, require_available=True),
                "query_capability": _QUERY_CAPABILITY in capabilities,
                "submission_capability": _SUBMISSION_CAPABILITY in capabilities,
                "war_state_pair_complete": before_war.get("complete") is True,
                "war_state_pair_at_peace": before_war.get("pair_at_war") is False if before_war.get("recipient_supported") else True,
            }
            report["before"] = {"health": health_before, "control": before_control, "query": before_query,
                                 "war_state_pair": before_war, "probes": _public_probe_records(before_probes),
                                 "baseline": before_baseline}
            if not all(before_baseline.values()):
                raise ExperimentStop("BASELINE_NOT_READY_FOR_DECLARE_WAR", json.dumps(before_baseline, ensure_ascii=False))
            preflight = api.get_diplomatic_result(args.request_id)
            report["request_preflight"] = preflight
            if isinstance(preflight, dict) and preflight.get("status") != "unknown":
                raise ExperimentStop("REQUEST_ID_NOT_UNIQUE", "request id already has a journal result; no request was sent")
            execution = api.execute_diplomatic_action(args.request_id, _ACTION, _ACTOR, args.recipient,
                                                      phase="initiate", parameters=parameters)
            report["execute_call_count"] = 1
            report["execution"] = execution
            if isinstance(execution, dict) and execution.get("submitted") is True:
                poll = _poll_royal_result(api, args.request_id)
            else:
                poll = {"calls": 1, "status_history": [execution.get("status")] if isinstance(execution, dict) else [],
                        "terminal": isinstance(execution, dict) and execution.get("status") in _TERMINAL_STATUSES,
                        "final": api.get_diplomatic_result(args.request_id)}
            final = poll.get("final")
            report["poll"] = poll
            after_query = _query_declare_war(api, args.recipient, parameters, artifact / "after" / "query.json")
            after_probes = _run_snapshots(session, artifact / "after" / "probes")
            after_control = _control_summary(after_probes["control_state"]["snapshot"])
            after_war = _war_state_pair(after_probes["war_state"]["snapshot"], args.recipient)
            after_health = session.health()
            report["after"] = {"health": after_health, "control": after_control, "query": after_query,
                                "war_state_pair": after_war, "probes": _public_probe_records(after_probes),
                                "baseline": _after_invariants(after_health, after_control, after_probes,
                                                               before_control, before_query, after_query,
                                                               args.expected_date_raw, args.recipient, parameters, capabilities)}
        with DurableJournal(journal_path, session.experiment_id, session.session_id, global_request_ids=True) as reopened:
            reopened_result = DiplomacyTools(reopened, session).get_diplomatic_result(args.request_id)
        report["reopened_result"] = reopened_result
        events_path = artifact / "native-events-slice.jsonl"
        if isinstance(log_start, int) and log_start >= 0:
            report["native_events"] = _copy_log_slice(log_path, log_start, events_path)
        report["result_checks"] = _result_checks(final, args.expected_outcome, args.expected_date_raw,
                                                  args.recipient, parameters, before_war, after_war)
        public_result = report["result_checks"].get("public_result")
        if isinstance(public_result, dict):
            report["war_result"] = {
                "war_before": public_result.get("war_before"),
                "war_after": public_result.get("war_after"),
                "war_id": public_result.get("war_id"),
                "stability_before_raw": public_result.get("stability_before_raw"),
                "stability_after_raw": public_result.get("stability_after_raw"),
            }
        report["native_event_checks"] = _event_checks(_event_records(events_path, args.request_id, session.session_id), parameters, args.recipient)
        stable = _stable_result(final)
        report["persistence"] = {"stable_result": stable, "reopened_stable_result": _stable_result(reopened_result),
                                  "same_public_result": stable == _stable_result(reopened_result)}
        result_checks = report["result_checks"]
        after_baseline = report["after"]["baseline"]
        event_checks = report["native_event_checks"]
        report["checks"] = {
            "submitted_true": isinstance(execution, dict) and execution.get("submitted") is True,
            "expected_terminal_result": isinstance(final, dict) and final.get("status") in _TERMINAL_STATUSES
            and result_checks.get("all") is True,
            "no_auto_resubmission": report["execute_call_count"] == 1 and report["idempotency_call_count"] == 0 and report["auto_resubmit"] is False,
            "journal_survives_reopen": stable == _stable_result(reopened_result),
            "after_invariants_hold": all(after_baseline.values()),
            "four_snapshots_before": report["before"]["baseline"]["four_snapshots_complete"],
            "four_snapshots_after": after_baseline["four_snapshots_complete"],
            "por_paused_date_identity": report["before"]["control"].get("player_slot") == _PLAYER_SLOT and after_baseline["player_slot_is_por"]
            and report["before"]["control"].get("paused_flag") == 1 and after_baseline["paused"]
            and report["before"]["control"].get("date_raw") == report["after"]["control"].get("date_raw") == args.expected_date_raw,
            "one_execute_call": report["execute_call_count"] == 1,
            "build_dll_source_bound": report.get("build_binding", {}).get("installation_matches_build_manifest") is True,
            "submission_event_verified": event_checks["submission_transport_verified"],
            "execution_event_verified": event_checks["execution_event_bound"],
        }
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except ExperimentStop as error:
        report["status"] = "failed"
        report["error"] = {"code": error.code, "message": error.message}
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"code": "UNEXPECTED_OPERATOR_ERROR", "type": type(error).__name__, "message": str(error)}
    finally:
        if isinstance(log_start, int) and log_start >= 0 and "native_events" not in report:
            report["native_events"] = _copy_log_slice(log_path, log_start, artifact / "native-events-slice.jsonl")
        events_path = artifact / "native-events-slice.jsonl"
        if events_path.is_file() and "native_event_checks" not in report:
            report["native_event_checks"] = _event_checks(
                _event_records(events_path, args.request_id,
                              report.get("session", {}).get("session_id", "")),
                parameters, args.recipient)
        _write_json(artifact / "report.json", report)
    print(json.dumps({"status": report["status"], "artifact": str(artifact)}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
