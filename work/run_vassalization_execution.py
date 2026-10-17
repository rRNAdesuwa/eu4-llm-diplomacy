"""Execute or resume one bounded Vassalization relation operation.

This operator supports Offer Vassalization (response-capable) and Cancel
Vassalization (one-sided execution).  It queries the native relationship before
the single submission, binds the expected native session date and request id,
reads the result without resubmitting, and preserves the bounded native log
slice.  Unknown or unavailable results never count as success.
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
from work.run_improve_relations_execution import (  # noqa: E402
    _new_artifact,
    _query_improve_pair,
)
from work.run_royal_marriage_execution import (  # noqa: E402
    ExperimentStop,
    _installation_binding,
    _poll_royal_result,
    _public_probe_records,
    _query_is_complete,
    _snapshots_complete,
)
from work.run_support_independence_execution import (  # noqa: E402
    _public_diplomat_snapshot,
)
from work.validate_alliance_reload import (  # noqa: E402
    _control_summary,
    _read_json,
    _run_snapshots,
)


_ACTOR = "FRA"
_PLAYER_SLOT = 189  # POR in the controlled experiment
_DEFAULT_DATE_RAW = 56500920
_ACTIONS = ("offer_vassalization", "cancel_vassalization")
_FAMILY = "vassalization"
_QUERY_CAPABILITY = "native_vassalization_query"
_SUBMISSION_CAPABILITY = "native_vassalization_submission"
_TERMINAL_STATUSES = frozenset(
    ("accepted", "rejected", "executed", "invalidated", "expired", "conflict")
)
_ACTION_OUTCOMES = {
    "offer_vassalization": frozenset(("accepted", "rejected")),
    "cancel_vassalization": frozenset(("executed",)),
}
_TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def _empty_result_checks() -> dict[str, object]:
    return {
        "status": False,
        "binding": False,
        "relation": False,
        "native": False,
        "proof": False,
        "event": False,
        "prestige": False,
        "all": False,
    }


def _query_vassalization_pair(
    api: DiplomacyTools, recipient: str, destination: Path
) -> dict[str, dict[str, object]]:
    """Inspect both Vassalization modes through the public API."""

    return _query_improve_pair(api, recipient, destination, _ACTIONS)


def _relation_state(query: object) -> dict[str, object]:
    if not isinstance(query, dict):
        return {
            "vassal_active": None,
            "actor_is_overlord": None,
            "actor_is_subject": None,
            "subject_type": None,
            "complete": False,
            "state_verified": None,
            "public_fields_complete": False,
            "source": "relationship_state",
        }
    relationship = query.get("relationship_state")
    active = (
        relationship.get("vassal_active")
        if isinstance(relationship, dict)
        else query.get("vassal_active")
    )
    actor_is_overlord = query.get("actor_is_overlord")
    actor_is_subject = query.get("actor_is_subject")
    subject_type = query.get("subject_type")
    state_verified = query.get("vassal_state_verified")
    if not isinstance(state_verified, bool) and isinstance(relationship, dict):
        state_verified = relationship.get("state_verified")
    public_fields_complete = (
        type(active) is bool
        and type(actor_is_overlord) is bool
        and type(actor_is_subject) is bool
        and (subject_type is None or isinstance(subject_type, str))
    )
    complete = (
        isinstance(relationship, dict)
        and relationship.get("complete") is True
        and type(active) is bool
    )
    return {
        "vassal_active": active if type(active) is bool else None,
        "actor_is_overlord": (
            actor_is_overlord if type(actor_is_overlord) is bool else None
        ),
        "actor_is_subject": (
            actor_is_subject if type(actor_is_subject) is bool else None
        ),
        "subject_type": subject_type if subject_type is None or isinstance(subject_type, str) else None,
        "complete": complete,
        "state_verified": state_verified if type(state_verified) is bool else None,
        "public_fields_complete": public_fields_complete,
        "source": "relationship_state",
    }


def _relation_pair(queries: object) -> dict[str, object]:
    if not isinstance(queries, dict):
        return {
            "vassal_active": None,
            "complete": False,
            "consistent": False,
            "roles_consistent": False,
            "public_fields_complete": False,
            "state_verified": None,
            "source": "relationship_state",
        }
    states = [_relation_state(queries.get(action_id)) for action_id in _ACTIONS]
    active_values = [state.get("vassal_active") for state in states]
    role_values = [
        (state.get("actor_is_overlord"), state.get("actor_is_subject"))
        for state in states
    ]
    subject_types = [state.get("subject_type") for state in states]
    complete = all(state.get("complete") is True for state in states)
    public_fields_complete = all(
        state.get("public_fields_complete") is True for state in states
    )
    consistent = (
        complete
        and active_values[0] is active_values[1]
        and active_values[0] is not None
    )
    roles_consistent = (
        public_fields_complete
        and role_values[0] == role_values[1]
    )
    subject_type_consistent = (
        public_fields_complete and subject_types[0] == subject_types[1]
    )
    verified = [state.get("state_verified") for state in states]
    return {
        "vassal_active": active_values[0] if consistent else None,
        "complete": complete,
        "consistent": consistent,
        "roles_consistent": roles_consistent,
        "subject_type_consistent": subject_type_consistent,
        "public_fields_complete": public_fields_complete,
        "state_verified": (
            verified[0] if verified[0] is verified[1] else None
        ),
        "source": "relationship_state",
        "by_action": dict(zip(_ACTIONS, states)),
    }


def _query_pair_complete(queries: object) -> bool:
    if not isinstance(queries, dict):
        return False
    return all(
        _query_is_complete(queries.get(action_id), action_id)
        and _relation_state(queries.get(action_id)).get("complete") is True
        and _relation_state(queries.get(action_id)).get("public_fields_complete") is True
        for action_id in _ACTIONS
    )


def _expected_before_after(
    action_id: str, expected_outcome: str
) -> tuple[bool, bool]:
    if action_id == "offer_vassalization":
        return False, expected_outcome == "accepted"
    return True, False


def _result_matches(
    action_id: str,
    expected_outcome: str,
    expected_date_raw: int,
    recipient: str,
    before_active: object,
    after_active: object,
    result: object,
) -> dict[str, object]:
    checks = _empty_result_checks()
    if (
        action_id not in _ACTION_OUTCOMES
        or expected_outcome not in _ACTION_OUTCOMES[action_id]
        or not isinstance(result, dict)
    ):
        return checks
    public = result.get("result")
    if not isinstance(public, dict):
        return checks

    expected_before, expected_after = _expected_before_after(
        action_id, expected_outcome
    )
    checks["status"] = (
        result.get("status") == expected_outcome
        and result.get("game_outcome") == expected_outcome
    )
    checks["binding"] = all(
        public.get(field) == expected
        for field, expected in (
            ("action_id", action_id),
            ("actor", _ACTOR),
            ("recipient", recipient),
            ("phase", "initiate"),
            ("date_raw", expected_date_raw),
            ("family", _FAMILY),
        )
    )
    checks["relation"] = (
        public.get("vassalization_before") is expected_before
        and public.get("vassalization_after") is expected_after
        and before_active is expected_before
        and after_active is expected_after
    )

    if action_id == "offer_vassalization":
        expected_state = 2 if expected_outcome == "accepted" else 1
        checks["native"] = (
            public.get("native_variant") == 1
            and public.get("native_state") == expected_state
            and public.get("outcome") == expected_outcome
        )
        checks["proof"] = (
            public.get("response_verified") is True
            and public.get("request_binding_verified") is True
        )
        checks["event"] = (
            public.get("event") == "native_diplomacy_relation_response_result"
        )
        checks["prestige"] = True
    else:
        checks["native"] = (
            public.get("native_variant") == 0
            and public.get("native_state") == 0
            and public.get("outcome") == "executed"
        )
        checks["proof"] = (
            public.get("execution_verified") is True
            and public.get("request_binding_verified") is True
        )
        checks["event"] = (
            public.get("event") == "native_diplomacy_relation_execution_result"
        )
        prestige_before = public.get("prestige_before_raw")
        prestige_after = public.get("prestige_after_raw")
        scale1000 = public.get("prestige_scale", public.get("scale1000"))
        prestige_delta = public.get("prestige_delta_raw")
        checks["prestige"] = (
            type(prestige_before) is int
            and type(prestige_after) is int
            and type(scale1000) is int
            and scale1000 == 1000
            and type(prestige_delta) is int
            and prestige_delta == prestige_after - prestige_before
        )
    checks["all"] = all(
        checks[key]
        for key in (
            "status",
            "binding",
            "relation",
            "native",
            "proof",
            "event",
            "prestige",
        )
    )
    checks["public_result"] = public
    return checks


def _baseline(
    health: dict[str, object],
    control: dict[str, object],
    probes: dict[str, dict[str, object]],
    queries: dict[str, dict[str, object]],
    relation: dict[str, object],
    expected_active: bool,
    expected_date_raw: int,
    capabilities: set[str] | list[str],
    *,
    require_submission_ack: bool,
) -> dict[str, object]:
    return {
        "health_ready": (
            health.get("status") == "ready"
            and health.get("complete") is True
        ),
        "health_date_matches_expected": (
            health.get("date_raw") == expected_date_raw
        ),
        "date_matches_expected": control.get("date_raw") == expected_date_raw,
        "player_slot_is_por": control.get("player_slot") == _PLAYER_SLOT,
        "paused": control.get("paused_flag") == 1,
        "four_snapshots_complete": _snapshots_complete(probes),
        "query_pair_complete": _query_pair_complete(queries),
        "query_relation_consistent": (
            relation.get("consistent") is True
            and relation.get("roles_consistent") is True
            and relation.get("subject_type_consistent") is True
            and relation.get("public_fields_complete") is True
        ),
        "relation_before_expected": (
            relation.get("vassal_active") is expected_active
        ),
        "vassalization_query_ack": _QUERY_CAPABILITY in capabilities,
        "vassalization_submission_ack": (
            not require_submission_ack
            or _SUBMISSION_CAPABILITY in capabilities
        ),
    }


def _query_identity_stable(
    before_queries: object, after_queries: object, recipient: str
) -> bool:
    """Check only query identity fields that must survive native effects."""

    if not isinstance(before_queries, dict) or not isinstance(after_queries, dict):
        return False
    expected_fields = {
        "actor": _ACTOR,
        "recipient": recipient,
        "family": _FAMILY,
        "phase": "initiate",
    }
    for action_id in _ACTIONS:
        before = before_queries.get(action_id)
        after = after_queries.get(action_id)
        if not isinstance(before, dict) or not isinstance(after, dict):
            return False
        if before.get("action_id") != action_id or after.get("action_id") != action_id:
            return False
        for field, expected in expected_fields.items():
            if before.get(field) != expected or after.get(field) != expected:
                return False
    return True


def _after_invariant_baseline(
    health: dict[str, object],
    control: dict[str, object],
    probes: dict[str, dict[str, object]],
    before_control: object,
    before_queries: object,
    after_queries: object,
    expected_date_raw: int,
    capabilities: set[str] | list[str],
    recipient: str,
) -> dict[str, object]:
    """Validate session identity without freezing native diplomatic effects.

    Diplomat assignments, envoy return state, native relationship state, and
    native legality/visibility may all change after a real action.  They are
    reported separately and checked against the native result contract.
    """

    before_control_dict = (
        before_control if isinstance(before_control, dict) else {}
    )
    return {
        "health_ready": (
            health.get("status") == "ready"
            and health.get("complete") is True
        ),
        "health_date_matches_expected": health.get("date_raw") == expected_date_raw,
        "date_matches_expected": control.get("date_raw") == expected_date_raw,
        "date_same_as_before": (
            control.get("date_raw") == before_control_dict.get("date_raw")
        ),
        "player_slot_is_por": control.get("player_slot") == _PLAYER_SLOT,
        "player_slot_same_as_before": (
            control.get("player_slot") == before_control_dict.get("player_slot")
        ),
        "paused": control.get("paused_flag") == 1,
        "paused_same_as_before": (
            control.get("paused_flag") == before_control_dict.get("paused_flag")
        ),
        "four_snapshots_complete": _snapshots_complete(probes),
        "vassalization_query_ack": _QUERY_CAPABILITY in capabilities,
        "query_identity_stable": _query_identity_stable(
            before_queries, after_queries, recipient
        ),
    }


def _after_change_policy() -> dict[str, object]:
    """Describe the intentionally narrow after-state acceptance boundary."""

    return {
        "required_invariants": [
            "health_ready",
            "health_date_matches_expected",
            "date_matches_expected",
            "date_same_as_before",
            "player_slot_is_por",
            "player_slot_same_as_before",
            "paused",
            "paused_same_as_before",
            "four_snapshots_complete",
            "vassalization_query_ack",
            "query_identity_stable",
        ],
        "identity_fields_compared": [
            "action_id",
            "actor",
            "recipient",
            "family",
            "phase",
        ],
        "allowed_changes": [
            "diplomat available_count and diplomacy entries, including envoy assignment or return",
            "vassalization relationship state and native legality/visibility after the result",
            "native response/execution consequence fields and native query completeness",
            "runtime health state_id and snapshot object addresses",
        ],
        "separate_result_checks": [
            "result_checks validates native event, request binding, native state, outcome, and relation transition",
            "persistence compares the public result before and after journal reopen",
        ],
    }


def _after_observations(
    after_queries: object, after_relation: dict[str, object]
) -> dict[str, object]:
    """Record native changes without treating them as session corruption."""

    return {
        "query_pair_complete": _query_pair_complete(after_queries),
        "query_relation_consistent": after_relation.get("consistent") is True,
        "query_relation": after_relation,
    }


def _resume_existing_artifact(
    resume_artifact: Path,
    explicit_installation: Path | None,
    expected_date_override: int | None,
) -> int:
    """Read an existing Vassalization artifact without executing anything."""

    resume_artifact = resume_artifact.expanduser().resolve(strict=True)
    original = _read_json(resume_artifact / "report.json")
    if not isinstance(original, dict):
        raise ExperimentStop("RESUME_REPORT_INVALID", "source report is not an object")
    installation_record = original.get("installation")
    recorded_path = (
        installation_record.get("path")
        if isinstance(installation_record, dict)
        else None
    )
    installation = (
        explicit_installation.expanduser().resolve(strict=True)
        if explicit_installation is not None
        else (
            Path(recorded_path).expanduser().resolve(strict=True)
            if isinstance(recorded_path, str)
            else None
        )
    )
    action_id = original.get("action_id")
    recipient = original.get("recipient")
    request_id = original.get("request_id")
    expected_outcome = original.get("expected_outcome")
    expected_date_raw = (
        expected_date_override
        if expected_date_override is not None
        else original.get("expected_date_raw", _DEFAULT_DATE_RAW)
    )
    if (
        installation is None
        or original.get("family") != _FAMILY
        or action_id not in _ACTIONS
        or not isinstance(recipient, str)
        or not _TAG_RE.fullmatch(recipient)
        or not isinstance(request_id, str)
        or not _REQUEST_ID_RE.fullmatch(request_id)
        or not isinstance(expected_outcome, str)
        or expected_outcome not in _ACTION_OUTCOMES.get(action_id, ())
        or not isinstance(expected_date_raw, int)
        or isinstance(expected_date_raw, bool)
    ):
        raise ExperimentStop(
            "RESUME_ARGUMENTS_INVALID",
            "source report lacks a valid Vassalization request",
        )

    output = _new_artifact(resume_artifact.parent, "vassalization-resume")
    log_path = installation.parent / "control-probe.jsonl"
    native_meta = original.get("native_events")
    log_start = original.get("log_start_offset")
    if not isinstance(log_start, int) and isinstance(native_meta, dict):
        log_start = native_meta.get("start_offset")
    report: dict[str, object] = {
        "validator": "run_vassalization_execution.py",
        "status": "unknown",
        "mode": "resume_read_only",
        "resume_artifact": str(resume_artifact),
        "artifact": str(output),
        "action_id": action_id,
        "actor": _ACTOR,
        "recipient": recipient,
        "family": _FAMILY,
        "phase": "initiate",
        "parameters": {},
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
        if isinstance(report.get("build_binding"), dict):
            report["build_binding"]["loaded_dll_sha256"] = session.record.get("dll_sha256")
        health = wait_runtime_ready(session, restore_minimized=True)
        after_probes = _run_snapshots(session, output / "after" / "probes")
        after_control = _control_summary(after_probes["control_state"]["snapshot"])
        after_health = session.health()
        with DurableJournal(
            resume_artifact / "diplomacy.sqlite3",
            session.experiment_id,
            session.session_id,
            global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            first = api.get_diplomatic_result(request_id)
            after_queries = _query_vassalization_pair(
                api, recipient, output / "after" / "queries.json"
            )
            final = api.get_diplomatic_result(request_id)
        with DurableJournal(
            resume_artifact / "diplomacy.sqlite3",
            session.experiment_id,
            session.session_id,
            global_request_ids=True,
        ) as reopened:
            reopened_result = DiplomacyTools(
                reopened, session
            ).get_diplomatic_result(request_id)
        before = (
            original.get("before")
            if isinstance(original.get("before"), dict)
            else {}
        )
        before_queries = (
            before.get("queries")
            if isinstance(before.get("queries"), dict)
            else {}
        )
        before_relation = (
            before.get("relation")
            if isinstance(before.get("relation"), dict)
            else _relation_pair(before_queries)
        )
        before_control = (
            before.get("control")
            if isinstance(before.get("control"), dict)
            else {}
        )
        capabilities = set(session.installation_capabilities())
        after_relation = _relation_pair(after_queries)
        after_baseline = _after_invariant_baseline(
            after_health,
            after_control,
            after_probes,
            before_control,
            before_queries,
            after_queries,
            expected_date_raw,
            capabilities,
            recipient,
        )
        after_observations = _after_observations(after_queries, after_relation)
        before_active = before_relation.get("vassal_active")
        after_active = after_relation.get("vassal_active")
        result_checks = _result_matches(
            action_id,
            expected_outcome,
            expected_date_raw,
            recipient,
            before_active,
            after_active,
            final,
        )
        stable = _stable_result(final)
        reopened_stable = _stable_result(reopened_result)
        terminal = (
            isinstance(final, dict)
            and final.get("status") in _TERMINAL_STATUSES
        )
        report.update({
            "source_report": {
                "path": str(resume_artifact),
                "status": original.get("status"),
            },
            "first_result": first,
            "final_result": final,
            "reopened_result": reopened_result,
            "after": {
                "health": after_health,
                "control": after_control,
                "queries": after_queries,
                "relation": after_relation,
                "diplomat": _public_diplomat_snapshot(after_probes),
                "probes": _public_probe_records(after_probes),
                "baseline": after_baseline,
                "observations": after_observations,
            },
            "after_change_policy": _after_change_policy(),
            "result_checks": result_checks,
            "persistence": {
                "stable_result": stable,
                "reopened_stable_result": reopened_stable,
                "same_public_result": stable == reopened_stable,
            },
        })
        checks = {
            "no_execute_submission": report["execute_call_count"] == 0,
            "no_auto_resubmission": (
                report["idempotency_call_count"] == 0
                and report["auto_resubmit"] is False
            ),
            "health_ready": (
                health.get("status") == "ready"
                and health.get("complete") is True
            ),
            "date_matches_expected": (
                after_control.get("date_raw") == expected_date_raw
            ),
            "date_same_as_before": after_baseline["date_same_as_before"],
            "player_slot_is_por": after_control.get("player_slot") == _PLAYER_SLOT,
            "player_slot_same_as_before": after_baseline[
                "player_slot_same_as_before"
            ],
            "paused": after_control.get("paused_flag") == 1,
            "paused_same_as_before": after_baseline["paused_same_as_before"],
            "four_snapshots_after": _snapshots_complete(after_probes),
            "vassalization_query_ack": after_baseline[
                "vassalization_query_ack"
            ],
            "query_identity_stable": after_baseline["query_identity_stable"],
            "journal_survives_reopen": stable == reopened_stable,
            "build_dll_source_bound": report.get("build_binding", {}).get(
                "installation_matches_build_manifest"
            ) is True,
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
    print(
        json.dumps(
            {"status": report["status"], "artifact": str(output)},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return (
        0 if report["status"] == "passed"
        else 3 if report["status"] == "pending"
        else 2
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path)
    parser.add_argument("--action-id", choices=_ACTIONS)
    parser.add_argument("--recipient")
    parser.add_argument("--request-id")
    parser.add_argument(
        "--expected-outcome",
        choices=("accepted", "rejected", "executed"),
    )
    parser.add_argument("--expected-date-raw", type=int, default=None)
    parser.add_argument("--resume-artifact", type=Path)
    args = parser.parse_args(argv)

    if args.resume_artifact is not None:
        try:
            return _resume_existing_artifact(
                args.resume_artifact,
                args.installation,
                args.expected_date_raw,
            )
        except ExperimentStop as error:
            print(
                json.dumps(
                    {"status": "failed", "error": {
                        "code": error.code, "message": error.message,
                    }},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return 2
        except Exception as error:
            print(
                json.dumps(
                    {"status": "failed", "error": {
                        "code": "UNEXPECTED_RESUME_ERROR",
                        "type": type(error).__name__,
                        "message": str(error),
                    }},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return 2

    required = (
        "installation",
        "action_id",
        "recipient",
        "request_id",
        "expected_outcome",
    )
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error(
            "missing required arguments: "
            + ", ".join("--" + name.replace("_", "-") for name in missing)
        )
    if args.expected_date_raw is None:
        args.expected_date_raw = _DEFAULT_DATE_RAW
    installation = args.installation.expanduser().resolve()
    artifact = _new_artifact(installation.parent, "vassalization-execution")
    log_path = installation.parent / "control-probe.jsonl"
    log_start: int | None = None
    report: dict[str, object] = {
        "validator": "run_vassalization_execution.py",
        "status": "unknown",
        "mode": "execute",
        "artifact": str(artifact),
        "action_id": args.action_id,
        "actor": _ACTOR,
        "recipient": args.recipient,
        "family": _FAMILY,
        "phase": "initiate",
        "parameters": {},
        "request_id": args.request_id,
        "expected_outcome": args.expected_outcome,
        "expected_date_raw": args.expected_date_raw,
        "execute_call_count": 0,
        "idempotency_call_count": 0,
        "auto_resubmit": False,
        "checks": {},
    }
    execution: object = None
    final: object = None
    try:
        if not isinstance(args.recipient, str) or not _TAG_RE.fullmatch(args.recipient):
            raise ExperimentStop(
                "RECIPIENT_TAG_INVALID",
                "recipient must match [A-Z0-9]{3}",
            )
        if (
            not isinstance(args.request_id, str)
            or not _REQUEST_ID_RE.fullmatch(args.request_id)
        ):
            raise ExperimentStop(
                "REQUEST_ID_INVALID",
                "request id must match [A-Za-z0-9_-]{1,64}",
            )
        if args.action_id not in _ACTION_OUTCOMES:
            raise ExperimentStop("ACTION_ID_INVALID", "unsupported Vassalization action")
        if args.expected_outcome not in _ACTION_OUTCOMES[args.action_id]:
            allowed = ",".join(sorted(_ACTION_OUTCOMES[args.action_id]))
            raise ExperimentStop(
                "VASSALIZATION_ACTION_OUTCOME_MISMATCH",
                f"{args.action_id} requires expected outcome in {{{allowed}}}",
            )
        if not isinstance(args.expected_date_raw, int) or isinstance(
            args.expected_date_raw, bool
        ):
            raise ExperimentStop(
                "EXPECTED_DATE_RAW_INVALID",
                "expected date must be an integer",
            )

        report.update(_installation_binding(installation))
        session = ObserverSession(installation, game_exe())
        report["session"] = {
            "session_id": session.session_id,
            "experiment_id": session.experiment_id,
            "pid": session.record.get("pid"),
            "dll_sha256": session.record.get("dll_sha256"),
        }
        if isinstance(report.get("build_binding"), dict):
            report["build_binding"]["loaded_dll_sha256"] = session.record.get(
                "dll_sha256"
            )
        log_start = log_path.stat().st_size
        report["log_start_offset"] = log_start
        health_before = wait_runtime_ready(session, restore_minimized=True)
        if health_before.get("status") != "ready":
            raise ExperimentStop(
                "SESSION_NOT_READY",
                json.dumps(health_before, ensure_ascii=False),
            )
        expected_before, expected_after = _expected_before_after(
            args.action_id, args.expected_outcome
        )
        journal_path = artifact / "diplomacy.sqlite3"
        with DurableJournal(
            journal_path,
            session.experiment_id,
            session.session_id,
            global_request_ids=True,
        ) as journal:
            api = DiplomacyTools(journal, session)
            before_probes = _run_snapshots(
                session, artifact / "before" / "probes"
            )
            before_control = _control_summary(
                before_probes["control_state"]["snapshot"]
            )
            before_diplomat = _public_diplomat_snapshot(before_probes)
            before_queries = _query_vassalization_pair(
                api, args.recipient, artifact / "before" / "queries.json"
            )
            before_relation = _relation_pair(before_queries)
            capabilities = sorted(session.installation_capabilities())
            before_baseline = _baseline(
                health_before,
                before_control,
                before_probes,
                before_queries,
                before_relation,
                expected_before,
                args.expected_date_raw,
                capabilities,
                require_submission_ack=True,
            )
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
                if _SUBMISSION_CAPABILITY not in capabilities:
                    raise ExperimentStop(
                        "NATIVE_VASSALIZATION_SUBMISSION_CAPABILITY_MISSING",
                        "installation does not advertise native_vassalization_submission; no request was sent",
                    )
                raise ExperimentStop(
                    "BASELINE_NOT_READY_FOR_EXPECTED_VASSALIZATION",
                    json.dumps(before_baseline, ensure_ascii=False),
                )

            request_preflight = api.get_diplomatic_result(args.request_id)
            report["request_preflight"] = request_preflight
            if (
                isinstance(request_preflight, dict)
                and request_preflight.get("status") != "unknown"
            ):
                raise ExperimentStop(
                    "REQUEST_ID_NOT_UNIQUE",
                    "request id already has a journal result; no request was sent",
                )

            execution = api.execute_diplomatic_action(
                args.request_id,
                args.action_id,
                _ACTOR,
                args.recipient,
                phase="initiate",
                parameters={},
            )
            report["execute_call_count"] = 1
            report["execution"] = execution
            if (
                isinstance(execution, dict)
                and execution.get("submitted") is True
            ):
                poll = _poll_royal_result(api, args.request_id)
            else:
                poll = {
                    "calls": 1,
                    "status_history": [
                        execution.get("status")
                    ] if isinstance(execution, dict) else [],
                    "terminal": (
                        isinstance(execution, dict)
                        and execution.get("status") in _TERMINAL_STATUSES
                    ),
                    "final": api.get_diplomatic_result(args.request_id),
                    "timeout_bound_seconds": _POLL_SECONDS,
                }
            final = poll.get("final")
            report["poll"] = poll

            after_queries = _query_vassalization_pair(
                api, args.recipient, artifact / "after" / "queries.json"
            )
            after_probes = _run_snapshots(
                session, artifact / "after" / "probes"
            )
            after_control = _control_summary(
                after_probes["control_state"]["snapshot"]
            )
            after_health = session.health()
            after_relation = _relation_pair(after_queries)
            after_baseline = _after_invariant_baseline(
                after_health,
                after_control,
                after_probes,
                before_control,
                before_queries,
                after_queries,
                args.expected_date_raw,
                set(capabilities),
                args.recipient,
            )
            after_observations = _after_observations(after_queries, after_relation)
            report["after_change_policy"] = _after_change_policy()
            report["after"] = {
                "health": after_health,
                "control": after_control,
                "queries": after_queries,
                "relation": after_relation,
                "diplomat": _public_diplomat_snapshot(after_probes),
                "probes": _public_probe_records(after_probes),
                "baseline": after_baseline,
                "observations": after_observations,
            }
        with DurableJournal(
            journal_path,
            session.experiment_id,
            session.session_id,
            global_request_ids=True,
        ) as reopened:
            reopened_result = DiplomacyTools(
                reopened, session
            ).get_diplomatic_result(args.request_id)
        report["reopened_result"] = reopened_result

        before_active = before_relation.get("vassal_active")
        after_active = after_relation.get("vassal_active")
        result_checks = _result_matches(
            args.action_id,
            args.expected_outcome,
            args.expected_date_raw,
            args.recipient,
            before_active,
            after_active,
            final,
        )
        report["result_checks"] = result_checks
        public_result = result_checks.get("public_result")
        if isinstance(public_result, dict) and args.action_id == "cancel_vassalization":
            prestige_scale = public_result.get(
                "prestige_scale", public_result.get("scale1000")
            )
            report["prestige_consequence"] = {
                "prestige_before_raw": public_result.get("prestige_before_raw"),
                "prestige_after_raw": public_result.get("prestige_after_raw"),
                "scale1000": prestige_scale,
                "prestige_delta_raw": public_result.get("prestige_delta_raw"),
            }
        stable = _stable_result(final)
        reopened_stable = _stable_result(reopened_result)
        report["persistence"] = {
            "stable_result": stable,
            "reopened_stable_result": reopened_stable,
            "same_public_result": stable == reopened_stable,
        }
        terminal = (
            isinstance(final, dict)
            and final.get("status") in _TERMINAL_STATUSES
        )
        after_baseline = report["after"]["baseline"]
        checks = {
            "submitted_true": (
                isinstance(execution, dict)
                and execution.get("submitted") is True
            ),
            "expected_terminal_result": (
                terminal and result_checks.get("all") is True
            ),
            "no_auto_resubmission": (
                report["execute_call_count"] == 1
                and report["idempotency_call_count"] == 0
                and report["auto_resubmit"] is False
            ),
            "journal_survives_reopen": stable == reopened_stable,
            "after_invariants_hold": all(after_baseline.values()),
            "native_relation_matches_query": (
                isinstance(public_result, dict)
                and public_result.get("vassalization_after")
                is after_active
            ),
            "cancel_prestige_consequence_present": (
                args.action_id != "cancel_vassalization"
                or result_checks.get("prestige") is True
            ),
            "four_snapshots_before": (
                report["before"]["baseline"]["four_snapshots_complete"]
            ),
            "four_snapshots_after": after_baseline["four_snapshots_complete"],
            "por_paused_date_identity": (
                before_control.get("player_slot") == _PLAYER_SLOT
                and after_baseline["player_slot_is_por"]
                and before_control.get("paused_flag") == 1
                and after_baseline["paused"]
                and before_control.get("date_raw")
                == after_control.get("date_raw")
                == args.expected_date_raw
            ),
            "one_execute_call": report["execute_call_count"] == 1,
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
            pending_checks = (
                "no_auto_resubmission",
                "journal_survives_reopen",
                "after_invariants_hold",
                "four_snapshots_before",
                "four_snapshots_after",
                "por_paused_date_identity",
                "build_dll_source_bound",
                "relation_evidence_is_public_relationship_state",
            )
            report["status"] = (
                "pending"
                if all(checks.get(key) is True for key in pending_checks)
                else "failed"
            )
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
                log_path,
                log_start,
                artifact / "native-events-slice.jsonl",
            )
        _write_json(artifact / "report.json", report)
    print(
        json.dumps(
            {"status": report["status"], "artifact": str(artifact)},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return (
        0 if report["status"] == "passed"
        else 3 if report["status"] == "pending"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
