"""Capture read-only live whole-war scores on selected white-peace queries.

The runner follows the R70 selection contract: QUERY1 discovers the sole
opaque ``war_id`` from the public ``white_peace`` context, then the same id is
passed back in an empty ``peace_context``.  The forward case goes through the
public :class:`DiplomacyTools` facade.  By default the second case uses the
operator-only recipient-scope path (BUR -> FRA in the default fixture), so it
does not turn a private reverse observation into public authority.  Use
``--reverse-scope public`` to capture a second public direction instead.

No execution, save, time advance, or game launch is performed.  Native log
evidence is copied through a bounded slice and the live-score event is
validated independently of the Python public projection.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.diplomacy import DiplomacyTools, ObserverSession
from bridge.war_score import (
    EVENT as LIVE_SCORE_EVENT,
    FAILED_EVENTS as LIVE_SCORE_FAILED_EVENTS,
    project_live_war_score,
    validate_live_war_score_event,
)
from work.local_config import game_exe
from work.observer_runtime_ready import wait_runtime_ready
from work.run_alliance_inbound_response import control_snapshot
from work.run_peace_consequence_queries import (
    _copy_bounded_slice,
    _read_slice_events,
    _write_json,
)


ACTION_ID = "white_peace"
PEACE_EMPTY_OFFER_QUERY = "native_peace_empty_offer_query"
PEACE_EMPTY_OFFER_EVENT = "native_peace_empty_offer_inspection"
PEACE_EXECUTION_INSPECTION_QUERY = "native_peace_execution_inspection"
PEACE_SUBMISSION_ADAPTER = "native_peace_submission"
PEACE_OFFER_EVALUATION_QUERY = "native_peace_offer_evaluation_query"
PEACE_WRAPPER_RULE_QUERY = "native_peace_wrapper_rule_query"
LIVE_SCORE_QUERY = "native_live_war_score_query"
WAR_ID = re.compile(r"war_[0-9a-f]{16}_[0-9a-f]{8}\Z")
TAG = re.compile(r"[A-Z0-9]{3}\Z")
FORBIDDEN_PUBLIC_KEYS = frozenset({
    "pid", "session_id", "creation_filetime", "native_war_reference",
    "native_reference", "module_base", "vtable_rva", "dll_sha256",
})

# This is the R70 proof used to choose the id.  It is metadata only; the
# current installation is always queried afresh and the id is never guessed
# from this historical artifact.
R70_SELECTION_SOURCE = (
    "work/runtime/r70-country-money-queries-20261020-005/report.json")
R70_REFERENCE_WAR_ID = "war_69f0cafa8352f574_00000001"


def _has_private_fields(value: object) -> bool:
    if isinstance(value, dict):
        return bool(FORBIDDEN_PUBLIC_KEYS.intersection(value)) or any(
            _has_private_fields(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_private_fields(item) for item in value)
    return False


def _public_discovery_contract(value: object, actor: str,
                               recipient: str) -> bool:
    if not isinstance(value, dict) or _has_private_fields(value):
        return False
    required = {
        "family": "peace", "action_id": ACTION_ID, "actor": actor,
        "recipient": recipient, "phase": "initiate",
        "context_discovery": True, "query_complete": True,
        "war_context_enumeration_complete": True,
        "native_offer_inspected": False,
    }
    if any(value.get(key) != expected for key, expected in required.items()):
        return False
    support = value.get("interface_support")
    if (not isinstance(support, dict)
            or support.get("query") != "native_peace_context_inspection"):
        return False
    wars = value.get("war_contexts")
    if not isinstance(wars, list) or len(wars) > 32:
        return False
    for row in wars:
        if not isinstance(row, dict):
            return False
        if any(row.get(key) != expected for key, expected in (
                ("identity_scope", "observer_session"),
                ("actor", actor), ("recipient", recipient),
                ("pair_at_war", True), ("actor_war_role", None),
                ("recipient_war_role", None),
                ("actor_is_war_leader", None),
                ("recipient_is_war_leader", None),
                ("roles_verified", False), ("leaders_verified", False),
                ("context_complete", False))):
            return False
        if (not isinstance(row.get("war_id"), str)
                or WAR_ID.fullmatch(row["war_id"]) is None):
            return False
    return True


def _discovered_war_id(value: object, actor: str, recipient: str) -> str | None:
    if not _public_discovery_contract(value, actor, recipient):
        return None
    wars = value["war_contexts"]
    if len(wars) != 1:
        return None
    return wars[0]["war_id"]


def _public_selected_contract(value: object, actor: str, recipient: str,
                              war_id: str, direction: str) -> bool:
    if not isinstance(value, dict) or _has_private_fields(value):
        return False
    if any(value.get(key) != expected for key, expected in (
            ("family", "peace"), ("action_id", ACTION_ID),
            ("actor", actor), ("recipient", recipient),
            ("phase", "initiate"), ("selected_war_id", war_id),
            ("identity_scope", "observer_session"),
            ("query_complete", True), ("native_offer_inspected", True),
            ("pair_at_war", True), ("unique_shared_war", True),
            ("offer_constructed", True), ("action_constructed", True),
            ("participant_copy_verified", True),
            ("offer_identity_verified", True), ("object_unchanged", True),
            ("cleanup_verified", True), ("validity_called", True),
            ("common_gate_checked", True),
            ("initiation_gate_checked", True),
            ("reasons_complete", False), ("submitted", False))):
        return False
    support = value.get("interface_support")
    if not isinstance(support, dict):
        return False
    query = support.get("query")
    if query == PEACE_EMPTY_OFFER_EVENT:
        pass
    elif query == PEACE_EXECUTION_INSPECTION_QUERY:
        # The selected peace query may be served by the native execution
        # inspection once the submission adapter is installed.  This is a
        # separate, explicitly acknowledged public branch; do not accept an
        # arbitrary query name merely because it returned a score.
        if (support.get("complete") is not True
                or support.get("execute") != PEACE_SUBMISSION_ADAPTER):
            return False
    else:
        return False
    context = value.get("peace_context")
    if (not isinstance(context, dict)
            or context.get("war_id") != war_id
            or context.get("direction", "demand") != direction
            or context.get("terms") != []
            or context.get("complete") is not False):
        return False
    if any(type(value.get(field)) is not bool for field in (
            "native_validity", "common_action_gate", "initiation_gate")):
        return False
    # The selected public result must carry the complete war-score projection
    # at the facade's public ``war_context.war_score`` path.  The nested
    # peace_context copy is checked separately by the consumer; it cannot
    # substitute for the public alias here.
    direct_context = value.get("war_context")
    if (not isinstance(direct_context, dict)
            or direct_context.get("war_id") != war_id
            or not isinstance(direct_context.get("war_score"), dict)):
        return False
    return _score_complete_contract(direct_context["war_score"])


def _all_case_checks_true(cases: object) -> bool:
    """Require every check emitted for every applicable case to pass."""

    if not isinstance(cases, list) or not cases:
        return False
    for case in cases:
        if not isinstance(case, dict):
            return False
        checks = case.get("checks")
        if not isinstance(checks, dict) or not checks:
            return False
        if any(value is not True for value in checks.values()):
            return False
    return True


def _matching_parent(events: list[dict[str, Any]], *, actor: str,
                     recipient: str, war_id: str, direction: str
                     ) -> list[dict[str, Any]]:
    return [event for event in events
            if event.get("event") == PEACE_EMPTY_OFFER_EVENT
            and event.get("family") == "peace"
            and event.get("action_id") == ACTION_ID
            and event.get("actor") == actor
            and event.get("recipient") == recipient
            and event.get("phase") == "initiate"
            and event.get("war_id") == war_id
            and event.get("direction", "demand") == direction]


def _matching_live_score(events: list[dict[str, Any]], *, query_id: str,
                         session_id: str, actor: str, recipient: str,
                         date_raw: int, war_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event in events:
        if event.get("event") not in {
                LIVE_SCORE_EVENT, *LIVE_SCORE_FAILED_EVENTS}:
            continue
        if validate_live_war_score_event(
                event, query_id=query_id, session_id=session_id,
                action_id=ACTION_ID, actor=actor, recipient=recipient,
                phase="initiate", date_raw=date_raw, war_id=war_id):
            result.append(event)
    return result


def _score_shape(value: object) -> bool:
    """Check that the public projection carries real whole-war fields."""

    if not isinstance(value, dict) or value.get("mode") != "whole_war":
        return False
    if value.get("status") not in ("available", "partial", "truncated", "failed", "unknown"):
        return False
    if type(value.get("scale_verified")) is not bool:
        return False
    total = value.get("total")
    maximum = value.get("max_score")
    overview = value.get("overview_goal_cap")
    goal = value.get("goal")
    tooltip = value.get("tooltip")
    if not all(isinstance(item, dict) for item in (
            total, maximum, overview, goal, tooltip)):
        return False
    if not isinstance(goal.get("cumulative"), dict):
        return False
    if not all(field in item for item in (total, maximum, overview)
               for field in ("raw", "value", "unit", "scale", "scale_verified")):
        return False
    if total.get("unit") != "war_score_point":
        return False
    if tooltip.get("text_truncated") not in (True, False):
        return False
    if tooltip.get("complete") not in (True, False):
        return False
    if goal.get("available") not in (True, False):
        return False
    if goal.get("presence_verified") not in (True, False):
        return False
    # An unavailable goal is a native observation.  It is not replaced with
    # zero; the object remains present and its availability flag is explicit.
    return True


def _score_complete_contract(value: object) -> bool:
    """Require the actual score/tooltip/goal payload, rather than a stub."""

    if not _score_shape(value) or not isinstance(value, dict):
        return False
    if value.get("complete") is not True or value.get("verified") is not True:
        return False
    total = value.get("total")
    goal = value.get("goal")
    tooltip = value.get("tooltip")
    if (not isinstance(total, dict) or type(total.get("raw")) is not int
            or total.get("value") is None or total.get("scale") != 1
            or total.get("scale_verified") is not True):
        return False
    if (not isinstance(goal, dict) or goal.get("available") is not True
            or goal.get("presence_verified") is not True
            or goal.get("complete") is not True
            or not isinstance(goal.get("cumulative"), dict)
            or type(goal["cumulative"].get("raw")) is not int):
        return False
    return (isinstance(tooltip, dict)
            and tooltip.get("complete") is True
            and tooltip.get("text_decoded") is True
            and isinstance(tooltip.get("text"), str))


def _score_from_result(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    context = value.get("peace_context")
    if not isinstance(context, dict):
        context = value.get("war_context")
    if not isinstance(context, dict):
        return None
    score_context = context.get("war_context") if "war_context" in context else context
    if not isinstance(score_context, dict):
        return None
    score = score_context.get("war_score")
    return score if isinstance(score, dict) else None


def _score_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"status": "missing", "mode": None, "shape_valid": False}
    result: dict[str, Any] = {
        "status": value.get("status"), "mode": value.get("mode"),
        "perspective": value.get("perspective"),
        "shape_valid": _score_shape(value),
        "complete_contract": _score_complete_contract(value),
        "scale_verified": value.get("scale_verified"),
        "complete": value.get("complete"),
        "verified": value.get("verified"),
    }
    for key in ("total", "max_score", "overview_goal_cap", "goal", "tooltip"):
        if key in value:
            result[key] = value[key]
    return result


def _required_empty_offer_capabilities(session: ObserverSession) -> frozenset[str]:
    capabilities = session.installation_capabilities()
    required = {PEACE_EMPTY_OFFER_QUERY}
    if PEACE_OFFER_EVALUATION_QUERY in capabilities:
        required.add(PEACE_OFFER_EVALUATION_QUERY)
    if PEACE_WRAPPER_RULE_QUERY in capabilities:
        required.add(PEACE_WRAPPER_RULE_QUERY)
    return frozenset(required)


def _catalog_selected_query(catalog: object) -> dict[str, Any] | None:
    if not isinstance(catalog, dict) or not isinstance(catalog.get("actions"), list):
        return None
    for action in catalog["actions"]:
        if not isinstance(action, dict) or action.get("action_id") != ACTION_ID:
            continue
        phase = action.get("phases", {}).get("initiate")
        if not isinstance(phase, dict):
            return None
        return {key: phase.get(key) for key in (
            "query", "reason_code", "selected_query",
            "selected_query_reason_code", "selected_query_protocol",
            "selected_query_protocol_reason_code") if key in phase}
    return None


def _run() -> tuple[bool, dict[str, Any]]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--actor", default="FRA")
    parser.add_argument("--recipient", default="BUR")
    parser.add_argument("--war-id", default=None)
    parser.add_argument("--direction", choices=("demand", "offer"), default="demand")
    parser.add_argument("--reverse-direction", choices=("demand", "offer"), default="demand")
    parser.add_argument("--reverse-scope", choices=("private", "public"), default="private")
    parser.add_argument("--expected-date-raw", type=int, default=None)
    args = parser.parse_args()

    if (TAG.fullmatch(args.actor) is None or TAG.fullmatch(args.recipient) is None
            or args.actor == args.recipient):
        parser.error("--actor and --recipient must be different three-character country tags")
    if args.war_id is not None and WAR_ID.fullmatch(args.war_id) is None:
        parser.error("--war-id has an invalid opaque war id")

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {
        "validator": Path(__file__).name,
        "installation": str(args.installation.expanduser().resolve()),
        "output": str(output),
        "status": "running",
        "action_id": ACTION_ID,
        "phase": "initiate",
        "actor": args.actor,
        "recipient": args.recipient,
        "direction": args.direction,
        "reverse_direction": args.reverse_direction,
        "reverse_scope": args.reverse_scope,
        "expected_date_raw": args.expected_date_raw,
        "business_submission": False,
        "execute_call_count": 0,
        "save_call_count": 0,
        "time_advance_call_count": 0,
        "selection_contract": {
            "source_report": R70_SELECTION_SOURCE,
            "reference_war_id": R70_REFERENCE_WAR_ID,
            "discovery_call": "inspect_diplomatic_action(white_peace, actor, recipient, parameters={})",
            "selected_call": "inspect_diplomatic_action(white_peace, actor, recipient, parameters={peace_context: {war_id, direction, terms: []}})",
        },
        "cases": [],
        "checks": {},
    }
    session: ObserverSession | None = None
    log: Path | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    try:
        installation = args.installation.expanduser().resolve(strict=True)
        session = ObserverSession(installation, game_exe())
        log = session.directory / "control-probe.jsonl"
        health = wait_runtime_ready(session, restore_minimized=False)
        if health.get("status") != "ready":
            raise RuntimeError("LIVE_WAR_SCORE_QUERY_SESSION_UNREADY")
        report["session"] = {
            "session_id": session.session_id,
            "experiment_id": session.experiment_id,
        }
        report["health_before"] = health
        report["capabilities"] = sorted(session.installation_capabilities())
        if LIVE_SCORE_QUERY not in session.installation_capabilities():
            report["capability_observation"] = {
                "native_live_war_score_query": False,
                "reason": "NATIVE_LIVE_WAR_SCORE_QUERY_CAPABILITY_MISSING",
            }
        else:
            report["capability_observation"] = {
                "native_live_war_score_query": True,
            }
        before = control_snapshot(int(session.record["pid"]), output / "control-before.json")
        report["before"] = before
        if before.get("paused_flag") != 1:
            raise RuntimeError("LIVE_WAR_SCORE_QUERY_REQUIRES_PAUSED_SESSION")
        if args.expected_date_raw is not None and before.get("date_raw") != args.expected_date_raw:
            raise RuntimeError("LIVE_WAR_SCORE_QUERY_DATE_MISMATCH")

        api = DiplomacyTools(None, session)
        catalog = api.list_diplomatic_actions()
        _write_json(output / "catalog.json", catalog)
        report["catalog_selected_query"] = _catalog_selected_query(catalog)

        # QUERY1 discovery is the only source of the current opaque id.
        discovery_dir = output / "cases" / "war_discovery"
        discovery_dir.mkdir(parents=True)
        discovery_offset = log.stat().st_size
        discovery = api.inspect_diplomatic_action(
            ACTION_ID, args.actor, args.recipient, phase="initiate", parameters={})
        discovery_slice = _copy_bounded_slice(
            log, discovery_offset, discovery_dir / "native.jsonl")
        discovery_events = _read_slice_events(discovery_dir / "native.jsonl")
        discovery_matches = [event for event in discovery_events
                             if event.get("event") == "native_peace_context_inspection"
                             and event.get("family") == "peace"
                             and event.get("action_id") == ACTION_ID
                             and event.get("actor") == args.actor
                             and event.get("recipient") == args.recipient]
        discovery_event = discovery_matches[-1] if len(discovery_matches) == 1 else None
        discovered_id = _discovered_war_id(discovery, args.actor, args.recipient)
        if discovered_id is None:
            raise RuntimeError("LIVE_WAR_SCORE_DISCOVERY_CONTRACT_INVALID")
        if args.war_id is not None and args.war_id != discovered_id:
            raise RuntimeError("LIVE_WAR_SCORE_WAR_ID_NOT_IN_CURRENT_DISCOVERY")
        war_id = discovered_id
        report["war_id"] = war_id
        _write_json(discovery_dir / "public.json", discovery)
        _write_json(discovery_dir / "native-events.json", {
            "discovery": discovery_event,
        })
        discovery_query_id = (
            discovery_event.get("query_id") if isinstance(discovery_event, dict) else None)
        discovery_valid = (
            isinstance(discovery_event, dict)
            and ObserverSession._valid_native_peace_context_inspection(
                discovery_event, ACTION_ID, args.actor, args.recipient, "initiate",
                before["date_raw"], discovery_query_id, session.session_id))
        report["discovery"] = {
            "public_path": str((discovery_dir / "public.json").resolve()),
            "native_path": str((discovery_dir / "native.jsonl").resolve()),
            "native_slice": discovery_slice,
            "native_event_count": len(discovery_matches),
            "public_war_id": discovered_id,
            "query_id": discovery_query_id,
            "checks": {
                "public_contract": _public_discovery_contract(
                    discovery, args.actor, args.recipient),
                "native_identity_contract": discovery_valid,
                "one_shared_war_id": discovered_id is not None,
            },
        }

        # Public FRA -> BUR selected query.  The log offset is taken directly
        # before the actual facade call, so no other event can be mistaken for
        # this query.
        forward_dir = output / "cases" / "selected_forward"
        forward_dir.mkdir(parents=True)
        forward_offset = log.stat().st_size
        forward_parameters = {
            "peace_context": {
                "war_id": war_id, "direction": args.direction, "terms": [],
            },
        }
        forward_public = api.inspect_diplomatic_action(
            ACTION_ID, args.actor, args.recipient, phase="initiate",
            parameters=forward_parameters)
        forward_slice = _copy_bounded_slice(
            log, forward_offset, forward_dir / "native.jsonl")
        forward_events = _read_slice_events(forward_dir / "native.jsonl")
        forward_parents = _matching_parent(
            forward_events, actor=args.actor, recipient=args.recipient,
            war_id=war_id, direction=args.direction)
        forward_parent = forward_parents[-1] if len(forward_parents) == 1 else None
        forward_query_id = (
            forward_parent.get("query_id")
            if isinstance(forward_parent, dict) else None)
        forward_live = (
            _matching_live_score(
                forward_events, query_id=forward_query_id,
                session_id=session.session_id, actor=args.actor,
                recipient=args.recipient, date_raw=before["date_raw"],
                war_id=war_id)
            if isinstance(forward_query_id, str) else [])
        forward_live_event = forward_live[-1] if len(forward_live) == 1 else None
        forward_projected = (
            project_live_war_score(
                forward_live_event, codec=session.native_text_codec,
                query_id=forward_query_id, session_id=session.session_id,
                action_id=ACTION_ID, actor=args.actor, recipient=args.recipient,
                phase="initiate", date_raw=before["date_raw"], war_id=war_id)
            if isinstance(forward_live_event, dict) else None)
        forward_public_score = _score_from_result(forward_public)
        forward_public_context = (
            forward_public.get("war_context")
            if isinstance(forward_public, dict) else None)
        forward_nested_score = (
            forward_public_context.get("war_score")
            if isinstance(forward_public_context, dict) else None)
        _write_json(forward_dir / "public.json", forward_public)
        _write_json(forward_dir / "native-events.json", {
            "parent": forward_parent, "live_war_score": forward_live_event,
        })
        forward_case = {
            "name": "selected_forward", "scope": "public",
            "actor": args.actor, "recipient": args.recipient,
            "direction": args.direction, "war_id": war_id,
            "parameters": forward_parameters,
            "call": "DiplomacyTools.inspect_diplomatic_action",
            "selected_query": (
                forward_public.get("interface_support", {}).get("query")
                if isinstance(forward_public, dict)
                and isinstance(forward_public.get("interface_support"), dict) else None),
            "query_id": forward_query_id,
            "native_slice": forward_slice,
            "native_event_count": len(forward_parents),
            "live_score_event_count": len(forward_live),
            "public_path": str((forward_dir / "public.json").resolve()),
            "native_events_path": str((forward_dir / "native-events.json").resolve()),
            "score": _score_summary(forward_projected),
            "checks": {
                "public_selected_contract": _public_selected_contract(
                    forward_public, args.actor, args.recipient, war_id, args.direction),
                "native_parent_identity": (
                    isinstance(forward_parent, dict)
                    and ObserverSession._valid_native_peace_empty_offer_inspection(
                        forward_parent, ACTION_ID, args.actor, args.recipient,
                        "initiate", before["date_raw"], war_id,
                        forward_query_id, session.session_id,
                        expected_direction=args.direction)),
                "one_live_score_event": len(forward_live) == 1,
                "live_score_event_identity": isinstance(forward_live_event, dict),
                "whole_war_score_shape": _score_shape(forward_projected),
                "whole_war_score_complete": _score_complete_contract(
                    forward_projected),
                "public_score_consumed": (
                    isinstance(forward_projected, dict)
                    and forward_public_score == forward_projected
                    and forward_nested_score == forward_projected),
                "public_projection_without_private_fields": (
                    not _has_private_fields(forward_public)),
            },
        }
        report["cases"].append(forward_case)

        if args.reverse_scope == "private":
            reverse_actor, reverse_recipient = args.recipient, args.actor
            reverse_dir = output / "cases" / "selected_reverse_private"
            reverse_dir.mkdir(parents=True)
            reverse_offset = log.stat().st_size
            reverse_result = session.inspect_alliance(
                ACTION_ID, reverse_actor, reverse_recipient, "initiate",
                _required_empty_offer_capabilities(session),
                allow_recipient_scope=True,
                inspection_event=PEACE_EMPTY_OFFER_EVENT,
                peace_war_id=war_id, peace_direction=args.reverse_direction)
            reverse_slice = _copy_bounded_slice(
                log, reverse_offset, reverse_dir / "native.jsonl")
            reverse_events = _read_slice_events(reverse_dir / "native.jsonl")
            reverse_parents = _matching_parent(
                reverse_events, actor=reverse_actor, recipient=reverse_recipient,
                war_id=war_id, direction=args.reverse_direction)
            reverse_parent = reverse_parents[-1] if len(reverse_parents) == 1 else None
            reverse_query_id = (
                reverse_parent.get("query_id")
                if isinstance(reverse_parent, dict) else None)
            reverse_live = (
                _matching_live_score(
                    reverse_events, query_id=reverse_query_id,
                    session_id=session.session_id, actor=reverse_actor,
                    recipient=reverse_recipient, date_raw=before["date_raw"],
                    war_id=war_id)
                if isinstance(reverse_query_id, str) else [])
            reverse_live_event = reverse_live[-1] if len(reverse_live) == 1 else None
            reverse_projected = (
                project_live_war_score(
                    reverse_live_event, codec=session.native_text_codec,
                    query_id=reverse_query_id, session_id=session.session_id,
                    action_id=ACTION_ID, actor=reverse_actor,
                    recipient=reverse_recipient, phase="initiate",
                    date_raw=before["date_raw"], war_id=war_id)
                if isinstance(reverse_live_event, dict) else None)
            reverse_private_score = _score_from_result(reverse_result)
            reverse_war_context = (
                reverse_result.get("peace_context", {}).get("war_context")
                if isinstance(reverse_result, dict)
                and isinstance(reverse_result.get("peace_context"), dict) else None)
            _write_json(reverse_dir / "private.json", reverse_result)
            _write_json(reverse_dir / "native-events.json", {
                "parent": reverse_parent, "live_war_score": reverse_live_event,
            })
            if isinstance(reverse_war_context, dict):
                _write_json(reverse_dir / "war-context-projection.json", {
                    "war_context": reverse_war_context,
                    "scope": "operator_private_reverse_score_projection",
                })
            reverse_case = {
                "name": "selected_reverse_private", "scope": "private_reverse",
                "actor": reverse_actor, "recipient": reverse_recipient,
                "direction": args.reverse_direction, "war_id": war_id,
                "call": "ObserverSession.inspect_alliance(allow_recipient_scope=True)",
                "query_id": reverse_query_id,
                "native_slice": reverse_slice,
                "native_event_count": len(reverse_parents),
                "live_score_event_count": len(reverse_live),
                "private_path": str((reverse_dir / "private.json").resolve()),
                "native_events_path": str((reverse_dir / "native-events.json").resolve()),
                "score": _score_summary(reverse_projected),
                "checks": {
                    "private_reverse_scope_used": (
                        isinstance(reverse_result, dict)
                        and reverse_result.get("actor") == reverse_actor
                        and reverse_result.get("recipient") == reverse_recipient),
                    "native_parent_identity": (
                        isinstance(reverse_parent, dict)
                        and ObserverSession._valid_native_peace_empty_offer_inspection(
                            reverse_parent, ACTION_ID, reverse_actor,
                            reverse_recipient, "initiate", before["date_raw"],
                            war_id, reverse_query_id, session.session_id,
                            expected_direction=args.reverse_direction)),
                    "one_live_score_event": len(reverse_live) == 1,
                    "live_score_event_identity": isinstance(reverse_live_event, dict),
                    "whole_war_score_shape": _score_shape(reverse_projected),
                    "whole_war_score_complete": _score_complete_contract(
                        reverse_projected),
                    "private_score_consumed": (
                        isinstance(reverse_projected, dict)
                        and reverse_private_score == reverse_projected),
                    "operator_projection_pointer_free": (
                        isinstance(reverse_war_context, dict)
                        and not _has_private_fields(reverse_war_context)),
                },
            }
        else:
            reverse_actor, reverse_recipient = args.actor, args.recipient
            reverse_dir = output / "cases" / "selected_reverse_public"
            reverse_dir.mkdir(parents=True)
            reverse_offset = log.stat().st_size
            reverse_parameters = {
                "peace_context": {
                    "war_id": war_id, "direction": args.reverse_direction,
                    "terms": [],
                },
            }
            reverse_result = api.inspect_diplomatic_action(
                ACTION_ID, reverse_actor, reverse_recipient, phase="initiate",
                parameters=reverse_parameters)
            reverse_slice = _copy_bounded_slice(
                log, reverse_offset, reverse_dir / "native.jsonl")
            reverse_events = _read_slice_events(reverse_dir / "native.jsonl")
            reverse_parents = _matching_parent(
                reverse_events, actor=reverse_actor, recipient=reverse_recipient,
                war_id=war_id, direction=args.reverse_direction)
            reverse_parent = reverse_parents[-1] if len(reverse_parents) == 1 else None
            reverse_query_id = (
                reverse_parent.get("query_id")
                if isinstance(reverse_parent, dict) else None)
            reverse_live = (
                _matching_live_score(
                    reverse_events, query_id=reverse_query_id,
                    session_id=session.session_id, actor=reverse_actor,
                    recipient=reverse_recipient, date_raw=before["date_raw"],
                    war_id=war_id)
                if isinstance(reverse_query_id, str) else [])
            reverse_live_event = reverse_live[-1] if len(reverse_live) == 1 else None
            reverse_projected = (
                project_live_war_score(
                    reverse_live_event, codec=session.native_text_codec,
                    query_id=reverse_query_id, session_id=session.session_id,
                    action_id=ACTION_ID, actor=reverse_actor,
                    recipient=reverse_recipient, phase="initiate",
                    date_raw=before["date_raw"], war_id=war_id)
                if isinstance(reverse_live_event, dict) else None)
            reverse_public_score = _score_from_result(reverse_result)
            reverse_public_context = (
                reverse_result.get("war_context")
                if isinstance(reverse_result, dict) else None)
            reverse_nested_score = (
                reverse_public_context.get("war_score")
                if isinstance(reverse_public_context, dict) else None)
            _write_json(reverse_dir / "public.json", reverse_result)
            _write_json(reverse_dir / "native-events.json", {
                "parent": reverse_parent, "live_war_score": reverse_live_event,
            })
            reverse_case = {
                "name": "selected_reverse_public", "scope": "public_direction",
                "actor": reverse_actor, "recipient": reverse_recipient,
                "direction": args.reverse_direction, "war_id": war_id,
                "parameters": reverse_parameters,
                "call": "DiplomacyTools.inspect_diplomatic_action",
                "query_id": reverse_query_id,
                "native_slice": reverse_slice,
                "native_event_count": len(reverse_parents),
                "live_score_event_count": len(reverse_live),
                "public_path": str((reverse_dir / "public.json").resolve()),
                "native_events_path": str((reverse_dir / "native-events.json").resolve()),
                "score": _score_summary(reverse_projected),
                "checks": {
                    "public_selected_contract": _public_selected_contract(
                        reverse_result, reverse_actor, reverse_recipient,
                        war_id, args.reverse_direction),
                    "native_parent_identity": (
                        isinstance(reverse_parent, dict)
                        and ObserverSession._valid_native_peace_empty_offer_inspection(
                            reverse_parent, ACTION_ID, reverse_actor,
                            reverse_recipient, "initiate", before["date_raw"],
                            war_id, reverse_query_id, session.session_id,
                            expected_direction=args.reverse_direction)),
                    "one_live_score_event": len(reverse_live) == 1,
                    "live_score_event_identity": isinstance(reverse_live_event, dict),
                    "whole_war_score_shape": _score_shape(reverse_projected),
                    "whole_war_score_complete": _score_complete_contract(
                        reverse_projected),
                    "public_score_consumed": (
                        isinstance(reverse_projected, dict)
                        and reverse_public_score == reverse_projected
                        and reverse_nested_score == reverse_projected),
                    "public_projection_without_private_fields": (
                        not _has_private_fields(reverse_result)),
                },
            }
        report["cases"].append(reverse_case)

        after = control_snapshot(int(session.record["pid"]), output / "control-after.json")
        report["after"] = after
        report["checks"] = {
            "catalog_selected_query": (
                isinstance(report.get("catalog_selected_query"), dict)
                and report["catalog_selected_query"].get("selected_query")
                == PEACE_EMPTY_OFFER_EVENT),
            "discovery_public_contract": report["discovery"]["checks"]["public_contract"],
            "discovery_native_identity": report["discovery"]["checks"]["native_identity_contract"],
            "one_shared_war_id": report["discovery"]["checks"]["one_shared_war_id"],
            "selected_query_is_native": all(
                row["checks"].get("native_parent_identity") is True
                for row in report["cases"]),
            "live_score_identity_for_both_directions": all(
                row["checks"].get("live_score_event_identity") is True
                and row["checks"].get("one_live_score_event") is True
                for row in report["cases"]),
            "whole_war_total_tooltip_goal_projection": all(
                row["checks"].get("whole_war_score_complete") is True
                for row in report["cases"]),
            "public_projection_consumed": all(
                row["checks"].get("public_score_consumed") is True
                or row["checks"].get("private_score_consumed") is True
                for row in report["cases"]),
            "public_selected_contract_for_public_cases": all(
                row["checks"].get("public_selected_contract") is True
                for row in report["cases"]
                if row.get("scope") in {"public", "public_direction"}),
            "all_applicable_case_checks": _all_case_checks_true(
                report["cases"]),
            "control_unchanged": (
                isinstance(before, dict) and isinstance(after, dict)
                and all(before.get(key) == after.get(key)
                        for key in ("date_raw", "paused_flag", "player_slot"))),
            "no_business_submission": (
                report["execute_call_count"] == 0
                and report["business_submission"] is False
                and report["save_call_count"] == 0
                and report["time_advance_call_count"] == 0),
        }
        report["status"] = (
            "passed" if all(report["checks"].values()) else "incomplete")
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        if before is not None and session is not None:
            try:
                after = control_snapshot(
                    int(session.record["pid"]), output / "control-after.json")
                report["after"] = after
            except Exception as after_error:
                report["after_error"] = {
                    "type": type(after_error).__name__,
                    "message": str(after_error),
                }
    finally:
        _write_json(output / "report.json", report)
    print(json.dumps({
        "status": report["status"], "war_id": report.get("war_id"),
        "checks": report.get("checks", {}),
        "output": str(output),
    }, ensure_ascii=False))
    return report["status"] == "passed", report


def main() -> int:
    passed, report = _run()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
