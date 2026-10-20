"""Bounded public projection for the optional live war-score query.

The native observer emits this record before the selected peace inspection.
This module validates only the public, pointer-free envelope and keeps the
war-score observation optional: an installation without the exact ACK does
not change the existing peace-query contract.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .native_text import (DEFAULT_NATIVE_TEXT_CODEC, InvalidNativeText,
                          decode_native_text_hex, validate_native_text_codec)


QUERY_CAPABILITY = "native_live_war_score_query"
EVENT = "native_live_war_score_inspection"
FAILED_EVENTS = frozenset({
    "native_live_war_score_inspection_failed",
    "native_live_war_score_query_failed",
})
FAMILY = "war_score"
ACTION_ID = "live_war_score"
MAX_WAR_ID_LENGTH = 29
MAX_QUERY_ID_LENGTH = 128
MAX_SESSION_ID_LENGTH = 128
MAX_TOOLTIP_HEX_LENGTH = 16385
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1

_TAG = re.compile(r"[A-Z0-9]{3}\Z")
_WAR_ID = re.compile(r"[A-Za-z0-9_.:-]{1,29}\Z")
_CODE = re.compile(r"[A-Z0-9_]{1,96}\Z")
_MODE_NAMES = {"whole_war": 0, "separate": 1}
_PUBLIC_UNIT = "war_score_point"


def _is_bool(value: object) -> bool:
    return type(value) is bool


def _is_int32(value: object, *, allow_none: bool = False) -> bool:
    if value is None and allow_none:
        return True
    return type(value) is int and INT32_MIN <= value <= INT32_MAX


def _is_bounded_text(value: object, limit: int) -> bool:
    return isinstance(value, str) and 0 < len(value) <= limit


def _is_optional_scale(value: object) -> bool:
    return value is None or (type(value) is int and 1 <= value <= 1_000_000)


def _identity_matches(event: Mapping[str, Any], *, query_id: str | None,
                      session_id: str | None, action_id: str | None,
                      actor: str | None, recipient: str | None,
                      phase: str | None, date_raw: object,
                      war_id: str | None) -> bool:
    if event.get("family") != FAMILY:
        return False
    actual_query = event.get("query_id")
    actual_session = event.get("session_id")
    if (not _is_bounded_text(actual_query, MAX_QUERY_ID_LENGTH)
            or not _is_bounded_text(actual_session, MAX_SESSION_ID_LENGTH)):
        return False
    if query_id is not None and actual_query != query_id:
        return False
    if session_id is not None and actual_session != session_id:
        return False
    actual_action = event.get("action_id")
    if not _is_bounded_text(actual_action, 80):
        return False
    # The shared peace query has two compatible producers in the field: the
    # parent action is carried through by the in-place helper, while the
    # standalone contract names the auxiliary query ``live_war_score``.
    # query/session/date/war/party binding remains exact, so this spelling
    # compatibility cannot attach another query's result.
    if (action_id is not None
            and actual_action not in (action_id, ACTION_ID)):
        return False
    actual_actor = event.get("actor")
    actual_recipient = event.get("recipient")
    if (not isinstance(actual_actor, str) or _TAG.fullmatch(actual_actor) is None
            or not isinstance(actual_recipient, str)
            or _TAG.fullmatch(actual_recipient) is None
            or actual_actor == actual_recipient):
        return False
    if actor is not None and actual_actor != actor:
        return False
    if recipient is not None and actual_recipient != recipient:
        return False
    actual_phase = event.get("phase")
    # The producer calls this an inspection with phase=query.  The selected
    # peace action itself remains phase=initiate, so accept both spellings
    # while still rejecting arbitrary cross-protocol phases.
    if actual_phase not in ("query", "initiate"):
        return False
    if phase is not None and actual_phase not in (phase, "query"):
        return False
    actual_date = event.get("date_raw")
    if not _is_int32(actual_date):
        return False
    if date_raw is not None and actual_date != date_raw:
        return False
    context = event.get("war_context")
    nested_war_id = context.get("war_id") if isinstance(context, Mapping) else None
    actual_war_id = event.get("war_id", nested_war_id)
    if (not isinstance(actual_war_id, str)
            or _WAR_ID.fullmatch(actual_war_id) is None):
        return False
    if nested_war_id is not None and nested_war_id != actual_war_id:
        return False
    if war_id is not None and actual_war_id != war_id:
        return False
    return True


def _validate_tooltip(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    required = {
        "requested", "text_hex", "text_readable", "text_truncated",
        "text_size", "string_capacity", "codec", "complete",
    }
    if not required <= set(value):
        return False
    if (not _is_bool(value.get("requested"))
            or not _is_bool(value.get("text_readable"))
            or not _is_bool(value.get("text_truncated"))
            or not _is_bool(value.get("complete"))):
        return False
    encoded = value.get("text_hex")
    if (not isinstance(encoded, str) or len(encoded) > MAX_TOOLTIP_HEX_LENGTH
            or len(encoded) % 2 or re.fullmatch(r"[0-9a-fA-F]*", encoded) is None):
        return False
    text_size = value.get("text_size")
    capacity = value.get("string_capacity")
    if (type(text_size) is not int or not 0 <= text_size <= 8192
            or type(capacity) is not int or not 0 <= capacity <= 131072
            or text_size > capacity):
        return False
    codec = value.get("codec")
    if not isinstance(codec, str) or len(codec) > 64:
        return False
    if value.get("text_readable") is True and not value.get("requested") is True:
        return False
    if value.get("text_readable") is True and value.get("text_hex") == "":
        # An empty tooltip is a valid native string, but it is still fully
        # readable only when its bounded metadata says it is complete.
        if value.get("text_size") != 0:
            return False
    return True


def _validate_score(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    required = {
        "mode", "mode_raw", "perspective", "total_raw", "total_available",
        "total_unit", "total_scale", "max_score_raw", "overview_goal_cap_raw",
        "goal", "daily", "scale_verified", "complete", "verified",
    }
    if not required <= set(value):
        return False
    mode = value.get("mode")
    mode_raw = value.get("mode_raw")
    if (not isinstance(mode, str) or mode not in _MODE_NAMES
            or type(mode_raw) is not int or mode_raw != _MODE_NAMES[mode]):
        return False
    if value.get("perspective") not in ("actor", "recipient"):
        return False
    total_available = value.get("total_available")
    if not _is_bool(total_available):
        return False
    if total_available and not _is_int32(value.get("total_raw")):
        return False
    if not total_available and value.get("total_raw") is not None:
        return False
    if not isinstance(value.get("total_unit"), str) or len(value["total_unit"]) > 80:
        return False
    if not _is_optional_scale(value.get("total_scale")):
        return False
    for field in ("max_score_raw", "overview_goal_cap_raw"):
        if not _is_int32(value.get(field), allow_none=True):
            return False
    for field in ("max_score_scale", "overview_goal_cap_scale"):
        if field in value and not _is_optional_scale(value.get(field)):
            return False
    goal = value.get("goal")
    if not isinstance(goal, Mapping):
        return False
    goal_required = {
        "available", "cumulative_raw", "cumulative_unit", "cumulative_scale",
        "presence_verified",
    }
    if not goal_required <= set(goal):
        return False
    goal_available = goal.get("available")
    if not _is_bool(goal_available):
        return False
    if goal_available and not _is_int32(goal.get("cumulative_raw")):
        return False
    if not goal_available and goal.get("cumulative_raw") is not None:
        return False
    if (not isinstance(goal.get("cumulative_unit"), str)
            or len(goal["cumulative_unit"]) > 80
            or not _is_optional_scale(goal.get("cumulative_scale"))
            or not _is_bool(goal.get("presence_verified"))):
        return False
    daily = value.get("daily")
    if not isinstance(daily, Mapping):
        return False
    for field in ("available",):
        if field in daily and not _is_bool(daily.get(field)):
            return False
    if "score_raw" in daily and not _is_int32(daily.get("score_raw"), allow_none=True):
        return False
    if not _is_bool(value.get("scale_verified")):
        return False
    if not _is_bool(value.get("complete")) or not _is_bool(value.get("verified")):
        return False
    if value.get("scale_verified") is True:
        if value.get("total_scale") != 1:
            return False
        if value.get("max_score_scale", 1) != 1:
            return False
        if value.get("overview_goal_cap_scale", 1000) != 1000:
            return False
        if goal.get("cumulative_scale") != 1000:
            return False
    return True


def _validate_verification(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    fields = (
        "actor_handle_valid", "recipient_handle_valid",
        "pair_reference_sets_equal", "war_id_bound_to_pair",
        "side_vectors_verified", "score_perspective_verified",
        "goal_direction_verified", "complete", "verified",
    )
    return all(_is_bool(value.get(field)) for field in fields)


def validate_live_war_score_event(
        event: object, *, query_id: str | None = None,
        session_id: str | None = None, action_id: str | None = None,
        actor: str | None = None, recipient: str | None = None,
        phase: str | None = None, date_raw: object = None,
        war_id: str | None = None) -> bool:
    """Validate one auxiliary event and its selected-peace identity binding."""

    if not isinstance(event, Mapping):
        return False
    if not _identity_matches(event, query_id=query_id, session_id=session_id,
                             action_id=action_id, actor=actor, recipient=recipient,
                             phase=phase, date_raw=date_raw, war_id=war_id):
        return False
    name = event.get("event")
    if name in FAILED_EVENTS:
        code = event.get("error_code", event.get("error"))
        return (isinstance(code, str) and _CODE.fullmatch(code) is not None
                and event.get("complete") is False
                and event.get("verified") is False)
    if name != EVENT:
        return False
    if not _validate_score(event.get("score")):
        return False
    if not _validate_tooltip(event.get("tooltip")):
        return False
    if not _validate_verification(event.get("verification")):
        return False
    error = event.get("error")
    if error is not None and (
            not isinstance(error, str) or _CODE.fullmatch(error) is None):
        return False
    return True


def _raw_value(raw: object, scale: object, available: bool) -> float | int | None:
    if not available or not _is_int32(raw) or type(scale) is not int or scale <= 0:
        return None
    value = raw / scale
    return int(value) if scale == 1 else value


def _metric(raw: object, scale: int | None, available: bool) -> dict[str, Any]:
    return {
        "raw": raw if available and _is_int32(raw) else None,
        "value": _raw_value(raw, scale, available),
        "unit": _PUBLIC_UNIT,
        "scale": scale,
        "scale_verified": scale is not None,
    }


def _decode_tooltip(value: Mapping[str, Any], codec: str) -> tuple[str | None, bool]:
    if value.get("text_readable") is not True:
        return None, False
    try:
        text = decode_native_text_hex(
            value["text_hex"], codec, max_bytes=8192, max_bytes_limit=8192)
    except (InvalidNativeText, KeyError, TypeError, ValueError):
        return None, False
    return text, True


def unknown_war_score(reason: str = "NATIVE_LIVE_WAR_SCORE_EVENT_MISSING") -> dict[str, Any]:
    """Return an explicit unknown value without manufacturing zero scores."""

    return {
        "status": "unknown", "mode": None, "perspective": None,
        "total": _metric(None, None, False),
        "max_score": _metric(None, None, False),
        "overview_goal_cap": _metric(None, None, False),
        "goal": {"available": None, "presence_verified": False,
                  "cumulative": _metric(None, None, False), "complete": False},
        "tooltip": {"text": None, "text_decoded": False,
                     "text_truncated": False, "complete": False},
        "scale_verified": False, "complete": False, "verified": False,
        "error": reason, "source": "war_score_query",
    }


def project_live_war_score(
        event: object, *, codec: str = DEFAULT_NATIVE_TEXT_CODEC,
        query_id: str | None = None, session_id: str | None = None,
        action_id: str | None = None, actor: str | None = None,
        recipient: str | None = None, phase: str | None = None,
        date_raw: object = None, war_id: str | None = None) -> dict[str, Any] | None:
    """Project a validated event, preserving unknown/failed/truncated layers."""

    selected_codec = validate_native_text_codec(codec)
    if not validate_live_war_score_event(
            event, query_id=query_id, session_id=session_id, action_id=action_id,
            actor=actor, recipient=recipient, phase=phase, date_raw=date_raw,
            war_id=war_id):
        return None
    assert isinstance(event, Mapping)
    if event.get("event") in FAILED_EVENTS:
        return unknown_war_score(str(event.get("error_code", event.get("error")))) | {
            "status": "failed",
        }
    score = event["score"]
    goal = score["goal"]
    tooltip = event["tooltip"]
    scale_verified = score["scale_verified"] is True
    total_scale = score.get("total_scale")
    max_scale = score.get("max_score_scale", 1 if scale_verified else None)
    overview_scale = score.get(
        "overview_goal_cap_scale", 1000 if scale_verified else None)
    goal_scale = goal.get("cumulative_scale")
    total_available = score["total_available"] is True
    max_available = score.get("max_score_raw") is not None
    overview_available = score.get("overview_goal_cap_raw") is not None
    goal_available = goal["available"] is True
    tooltip_text, tooltip_decoded = _decode_tooltip(tooltip, selected_codec)
    tooltip_complete = (tooltip.get("complete") is True
                        and tooltip.get("text_truncated") is False
                        and tooltip_decoded)
    verification = event["verification"]
    complete = (
        score["complete"] is True and score["verified"] is True
        and verification["complete"] is True and verification["verified"] is True
        and scale_verified and total_scale == 1 and max_scale == 1
        and overview_scale == 1000 and goal_scale == 1000
        and goal["presence_verified"] is True and tooltip_complete
        and total_available and max_available and overview_available
    )
    if event.get("error") is not None:
        status = "failed"
    elif tooltip.get("text_truncated") is True:
        status = "truncated"
    elif complete:
        status = "available"
    elif (score["complete"] is True or score["verified"] is True
          or total_available or goal_available):
        status = "partial"
    else:
        status = "unknown"
    result = {
        "status": status,
        "mode": score["mode"],
        "perspective": score["perspective"],
        "total": _metric(score.get("total_raw"), total_scale, total_available),
        "max_score": _metric(score.get("max_score_raw"), max_scale, max_available),
        "overview_goal_cap": _metric(
            score.get("overview_goal_cap_raw"), overview_scale, overview_available),
        "goal": {
            "available": goal_available,
            "presence_verified": goal["presence_verified"],
            "cumulative": _metric(
                goal.get("cumulative_raw"), goal_scale, goal_available),
            "complete": goal_available and goal["presence_verified"] is True,
        },
        "tooltip": {
            "text": tooltip_text,
            "text_decoded": tooltip_decoded,
            "text_truncated": tooltip["text_truncated"],
            "complete": tooltip_complete,
        },
        "scale_verified": scale_verified,
        "complete": complete,
        "verified": score["verified"] is True and verification["verified"] is True,
        "error": event.get("error"),
        "source": "war_score_query",
    }
    return result


def attach_live_war_score(
        result: object, event: object | None, *, enabled: bool,
        query_id: str, session_id: str, action_id: str, actor: str,
        recipient: str, phase: str, date_raw: object, war_id: str,
        codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> object:
    """Attach the score under the public selected peace context only."""

    if not enabled or not isinstance(result, dict):
        return result
    score = (project_live_war_score(
        event, codec=codec, query_id=query_id, session_id=session_id,
        action_id=action_id, actor=actor, recipient=recipient, phase=phase,
        date_raw=date_raw, war_id=war_id)
        if event is not None else unknown_war_score())
    if score is None:
        score = unknown_war_score("NATIVE_LIVE_WAR_SCORE_EVENT_INVALID")
    context = result.get("peace_context")
    if isinstance(context, dict):
        context["war_context"] = {"war_id": war_id, "war_score": score}
    else:
        # A few legacy selected-query producers retain the generic
        # native_alliance_inspection envelope.  Keep the auxiliary result at
        # the same public war_context path without widening their other
        # semantic fields.
        result["war_context"] = {"war_id": war_id, "war_score": score}
    return result


__all__ = [
    "ACTION_ID", "QUERY_CAPABILITY", "EVENT", "FAILED_EVENTS", "FAMILY",
    "attach_live_war_score", "project_live_war_score",
    "unknown_war_score", "validate_live_war_score_event",
]
