"""Validation and public projection for Declare War participants.

The native observer owns candidate enumeration and acceptance evaluation.  This
module validates the bounded participant event contract, binds it to one query
and request, and projects only public country, rule and willingness values.
Native text is decoded with the explicitly configured bridge codec.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .declarewar_selection import (
    COUNTRY_TAG_RE,
    country_csv,
    normalize_participant_selection,
)
from .native_text import (
    DEFAULT_NATIVE_TEXT_CODEC,
    NativeTextError,
    decode_native_text_hex,
    validate_native_text_codec,
)


PARTICIPANT_EVENT = "native_declare_war_participant"
MAX_CANDIDATES = 64
MAX_REASONS = 32
MAX_TEXT_BYTES = 512
_INT32_MIN = -(2 ** 31)
_INT32_MAX = 2 ** 31 - 1
_HEX_RE = re.compile(r"^[0-9A-Fa-f]*$")

PARENT_FIELDS = frozenset({
    "called",
    "complete",
    "selection_applied",
    "selection_allowed",
    "action_unchanged",
    "candidate_count",
    "requested_call_allies_csv",
    "requested_promise_land_to_csv",
    "requested_co_belligerents_csv",
})
EVENT_FIELDS = frozenset({
    "event",
    "query_id",
    "session_id",
    "actor",
    "recipient",
    "date_raw",
    "index",
    "side",
    "country",
    "related_country",
    "join_reason_raw",
    "automatic",
    "selected",
    "promise_land",
    "promise_available",
    "legality_checked",
    "native_legality",
    "diagnostic_hex",
    "diagnostic_readable",
    "diagnostic_truncated",
    "score_available",
    "native_total_raw",
    "acceptance_threshold_raw",
    "reason_count",
    "reasons",
    "reasons_complete",
    "context_complete",
})
REASON_FIELDS = frozenset({
    "index", "value", "text_hex", "readable", "truncated",
})


def _is_int32(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)
            and _INT32_MIN <= value <= _INT32_MAX)


def _valid_tag(value: object) -> bool:
    return isinstance(value, str) and COUNTRY_TAG_RE.fullmatch(value) is not None


def _valid_hex(value: object) -> bool:
    return (isinstance(value, str) and len(value) % 2 == 0
            and len(value) <= MAX_TEXT_BYTES * 2
            and _HEX_RE.fullmatch(value) is not None)


def _parse_csv(value: object) -> list[str] | None:
    if value == "-":
        return []
    if not isinstance(value, str) or not value:
        return None
    tags = value.split(",")
    if len(tags) > 16 or any(not _valid_tag(tag) for tag in tags):
        return None
    if tags != sorted(tags) or len(set(tags)) != len(tags):
        return None
    return tags


def _selection_from_parent(native_participants: object) -> dict[str, list[str]] | None:
    if not isinstance(native_participants, dict):
        return None
    fields = {
        "call_allies": _parse_csv(native_participants.get(
            "requested_call_allies_csv")),
        "promise_land_to": _parse_csv(native_participants.get(
            "requested_promise_land_to_csv")),
        "co_belligerents": _parse_csv(native_participants.get(
            "requested_co_belligerents_csv")),
    }
    if any(value is None for value in fields.values()):
        return None
    return fields  # type: ignore[return-value]


def _valid_reason(reason: object, expected_index: int) -> bool:
    if not isinstance(reason, dict) or set(reason) != REASON_FIELDS:
        return False
    return (
        isinstance(reason.get("index"), int)
        and not isinstance(reason.get("index"), bool)
        and reason.get("index") == expected_index
        and _is_int32(reason.get("value"))
        and _valid_hex(reason.get("text_hex"))
        and isinstance(reason.get("readable"), bool)
        and isinstance(reason.get("truncated"), bool)
    )


def _valid_event(event: object, query_id: str, session_id: str,
                 actor: str, recipient: str, date_raw: int,
                 expected_index: int) -> bool:
    if not isinstance(event, dict):
        return False
    if any(event.get(key) != expected for key, expected in (
            ("event", PARTICIPANT_EVENT), ("query_id", query_id),
            ("session_id", session_id), ("actor", actor),
            ("recipient", recipient))):
        return False
    if (not _is_int32(event.get("date_raw"))
            or event.get("date_raw") != date_raw
            or isinstance(event.get("index"), bool)
            or not isinstance(event.get("index"), int)
            or event.get("index") != expected_index):
        return False
    if (event.get("side") not in ("attacker", "defender")
            or not _valid_tag(event.get("country"))
            or not _valid_tag(event.get("related_country"))
            or not _is_int32(event.get("join_reason_raw"))):
        return False
    for field in (
            "automatic", "selected", "promise_land", "promise_available",
            "legality_checked", "native_legality", "diagnostic_readable",
            "diagnostic_truncated", "score_available", "reasons_complete",
            "context_complete"):
        if not isinstance(event.get(field), bool):
            return False
    if (not _valid_hex(event.get("diagnostic_hex"))
            or not _is_int32(event.get("native_total_raw"))
            or event.get("acceptance_threshold_raw") != 1):
        return False
    reason_count = event.get("reason_count")
    reasons = event.get("reasons")
    if (isinstance(reason_count, bool) or not isinstance(reason_count, int)
            or not 0 <= reason_count <= MAX_REASONS
            or not isinstance(reasons, list)
            or len(reasons) != reason_count):
        return False
    if any(not _valid_reason(item, index)
           for index, item in enumerate(reasons)):
        return False
    return True


def _validate_parent(native_participants: object) -> bool:
    if not isinstance(native_participants, dict):
        return False
    if not PARENT_FIELDS.issubset(native_participants):
        return False
    for field in ("called", "complete", "selection_applied",
                  "selection_allowed", "action_unchanged"):
        if not isinstance(native_participants.get(field), bool):
            return False
    if (native_participants["called"] is not True
            or native_participants["action_unchanged"] is not True):
        return False
    count = native_participants.get("candidate_count")
    if isinstance(count, bool) or not isinstance(count, int) \
            or not 0 <= count <= MAX_CANDIDATES:
        return False
    return all(_parse_csv(native_participants.get(field)) is not None
               for field in (
                   "requested_call_allies_csv",
                   "requested_promise_land_to_csv",
                   "requested_co_belligerents_csv"))


def _selection_matches_events(selection: dict[str, list[str]],
                              events: list[dict]) -> bool:
    """Bind each requested list to its native side and row flags."""

    requested_allies = set(selection["call_allies"])
    requested_promises = set(selection["promise_land_to"])
    requested_co_belligerents = set(selection["co_belligerents"])
    attacker_seen: set[str] = set()
    defender_seen: set[str] = set()
    seen_rows: set[tuple[str, str]] = set()
    for event in events:
        side = event["side"]
        country = event["country"]
        row_key = (side, country)
        if row_key in seen_rows:
            return False
        seen_rows.add(row_key)
        if side == "attacker":
            attacker_seen.add(country)
            expected_selected = country in requested_allies
            expected_promise = country in requested_promises
        else:
            defender_seen.add(country)
            expected_selected = country in requested_co_belligerents
            expected_promise = False
        if event["selected"] is not expected_selected:
            return False
        if event["promise_land"] is not expected_promise:
            return False
    # Every requested country must have a row on the side whose list it
    # belongs to.  Other unselected native candidates are allowed.
    return (requested_allies <= attacker_seen
            and requested_promises <= attacker_seen
            and requested_co_belligerents <= defender_seen)


def validate_participants(
        native_participants: object,
        events: object,
        query_id: object,
        session_id: object,
        actor: object,
        recipient: object,
        date_raw: object,
        selection: Mapping[str, Any] | None = None) -> bool:
    """Strictly validate one bound participant query without raising.

    ``selection`` is the normalized public participant selection.  When it is
    omitted, the three native CSV request fields must all be ``-`` and no row
    may be selected or promised.
    """

    try:
        if (not _validate_parent(native_participants)
                or not isinstance(events, list)
                or len(events) > MAX_CANDIDATES
                or not isinstance(query_id, str) or not query_id
                or len(query_id) > 128
                or not isinstance(session_id, str) or not session_id
                or len(session_id) > 128
                or not _valid_tag(actor) or not _valid_tag(recipient)
                or not _is_int32(date_raw)):
            return False
        assert isinstance(native_participants, dict)
        assert isinstance(date_raw, int)
        parent_count = native_participants["candidate_count"]
        if parent_count != len(events):
            return False
        parsed_selection = _selection_from_parent(native_participants)
        if parsed_selection is None:
            return False
        if selection is None:
            expected_selection = {
                "call_allies": [], "promise_land_to": [],
                "co_belligerents": [],
            }
        else:
            if not isinstance(selection, Mapping):
                return False
            expected_selection = normalize_participant_selection(
                selection, actor=actor, recipient=recipient)
        expected_csv = {
            "requested_call_allies_csv": country_csv(
                expected_selection["call_allies"]),
            "requested_promise_land_to_csv": country_csv(
                expected_selection["promise_land_to"]),
            "requested_co_belligerents_csv": country_csv(
                expected_selection["co_belligerents"]),
        }
        if any(native_participants[field] != value
               for field, value in expected_csv.items()):
            return False
        requested = any(expected_selection.values())
        # Native marks the participant probe as applied even for discovery
        # (all three requested CSVs are ``-``).  For a concrete selection the
        # flag remains a strict request binding; an empty discovery may use
        # either the older false value or the current probe-applied true value.
        if requested and native_participants["selection_applied"] is not True:
            return False
        checked_events: list[dict] = []
        for index, event in enumerate(events):
            if not _valid_event(event, query_id, session_id, actor,
                                recipient, date_raw, index):
                return False
            assert isinstance(event, dict)
            checked_events.append(event)
        return _selection_matches_events(expected_selection, checked_events)
    except (TypeError, ValueError, KeyError, AssertionError):
        return False


def _project_text(text_hex: str, readable: bool, truncated: bool,
                  codec: str) -> tuple[str | None, bool]:
    if not readable or truncated:
        return None, False
    try:
        text = decode_native_text_hex(text_hex, codec, max_bytes=MAX_TEXT_BYTES)
    except NativeTextError:
        return None, False
    return text, True


def _project_reason(reason: dict, codec: str) -> dict:
    text, complete = _project_text(
        reason["text_hex"], reason["readable"], reason["truncated"], codec)
    return {
        "index": reason["index"],
        "value": reason["value"],
        "text": text,
        "readable": reason["readable"],
        "truncated": reason["truncated"],
        "complete": complete,
    }


def _project_event(event: dict, codec: str) -> dict:
    diagnostic, diagnostic_complete = _project_text(
        event["diagnostic_hex"], event["diagnostic_readable"],
        event["diagnostic_truncated"], codec)
    reasons = [_project_reason(item, codec) for item in event["reasons"]]
    willingness_complete = (
        event["score_available"] is True
        and event["reasons_complete"] is True
        and all(item["complete"] for item in reasons)
    )
    return {
        "index": event["index"],
        "side": event["side"],
        "country": event["country"],
        "related_country": event["related_country"],
        "join_reason_raw": event["join_reason_raw"],
        "automatic": event["automatic"],
        "selected": event["selected"],
        "promise_land": event["promise_land"],
        "promise_available": event["promise_available"],
        "legality_checked": event["legality_checked"],
        "native_legality": event["native_legality"],
        "diagnostic": {
            "text": diagnostic,
            "readable": event["diagnostic_readable"],
            "truncated": event["diagnostic_truncated"],
            "complete": diagnostic_complete,
        },
        "willingness": {
            "score_available": event["score_available"],
            "native_total_raw": event["native_total_raw"],
            "acceptance_threshold_raw": event["acceptance_threshold_raw"],
            "reason_count": event["reason_count"],
            "reasons": reasons,
            "reasons_complete": event["reasons_complete"],
            "complete": willingness_complete,
        },
        "context_complete": event["context_complete"],
        "complete": (
            event["context_complete"] is True
            and diagnostic_complete and willingness_complete
        ),
    }


def project_participants(
        native_participants: object, events: object,
        codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict | None:
    """Project a valid native participant query without private fields."""

    try:
        validate_native_text_codec(codec)
        if not _validate_parent(native_participants) \
                or not isinstance(events, list):
            return None
        assert isinstance(native_participants, dict)
        if len(events) > MAX_CANDIDATES:
            return None
        selection = _selection_from_parent(native_participants)
        if selection is None:
            return None
        # Derive the binding identity from the first row for this pure
        # projector.  Empty discovery is still structurally projectable.
        if events:
            first = events[0]
            if not isinstance(first, dict):
                return None
            query_id = first.get("query_id")
            session_id = first.get("session_id")
            actor = first.get("actor")
            recipient = first.get("recipient")
            date_raw = first.get("date_raw")
            if not validate_participants(
                    native_participants, events, query_id, session_id,
                    actor, recipient, date_raw, selection):
                return None
        else:
            if not validate_participants(
                    native_participants, events, "empty-query", "empty-session",
                    "FRA", "ENG", 0,
                    selection if any(selection.values()) else None):
                return None
        candidates = [_project_event(event, codec) for event in events]
        enumeration_complete = (
            native_participants["complete"] is True
            and native_participants["candidate_count"] == len(events)
        )
        legality_complete = all(
            event["context_complete"] is True for event in events)
        return {
            "source": "native_declare_war_participants",
            "called": native_participants["called"],
            "action_unchanged": native_participants["action_unchanged"],
            "selection": {
                "applied": native_participants["selection_applied"],
                "allowed": native_participants["selection_allowed"],
                "call_allies": selection["call_allies"],
                "promise_land_to": selection["promise_land_to"],
                "co_belligerents": selection["co_belligerents"],
            },
            "candidate_count": native_participants["candidate_count"],
            "candidates": candidates,
            "enumeration_complete": enumeration_complete,
            "legality_complete": legality_complete,
            "complete": enumeration_complete,
        }
    except (TypeError, ValueError, KeyError, AssertionError):
        return None


__all__ = [
    "PARTICIPANT_EVENT",
    "MAX_CANDIDATES",
    "MAX_REASONS",
    "MAX_TEXT_BYTES",
    "PARENT_FIELDS",
    "EVENT_FIELDS",
    "REASON_FIELDS",
    "validate_participants",
    "project_participants",
]
