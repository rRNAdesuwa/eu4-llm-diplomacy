"""Pure QUERY14 helpers for return-core and revoke-core peace terms.

Core terms are query-only in R57.  This module deliberately contains no
execution code and no game-specific candidate rule: the native query owns
candidate selection and legality.  The bridge only validates the request
copy, the bounded public event shape, and projects safe fields.
"""
from __future__ import annotations

import re
from typing import Callable

from .native_text import DEFAULT_NATIVE_TEXT_CODEC, NativeTextError, decode_native_text_hex


CORE_ACTION_IDS = frozenset(("return_core", "revoke_core"))
CORE_QUERY_CAPABILITY = "native_peace_core_terms_query"
CORE_QUERY_EVENT = "native_peace_core_offer_query"
CORE_QUERY_PROTOCOL = "EU4DIP_QUERY14"
MAX_CORE_PROVINCES = 16
MAX_CORE_CANDIDATES = 512
_WAR_ID_RE = re.compile(r"war_[0-9a-f]{16}_[0-9a-f]{8}\Z")
_TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
_NAME_HEX_RE = re.compile(r"(?:[0-9a-fA-F]{2}){0,512}\Z")


class CoreQueryError(ValueError):
    """Stable malformed-parameter error for the QUERY14 adapter."""


def _tag(value: object, *, allow_none: bool = False) -> bool:
    return allow_none and value is None or (
        isinstance(value, str) and _TAG_RE.fullmatch(value) is not None)


def _positive_int(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)
            and 1 <= value <= 2_147_483_647)


def _province_ids(value: object, *, allow_empty: bool) -> list[int] | None:
    if not isinstance(value, list) or len(value) > MAX_CORE_PROVINCES:
        return None
    if not allow_empty and not value:
        return None
    if any(not _positive_int(item) for item in value):
        return None
    if len(set(value)) != len(value):
        return None
    return list(value)


def _war_id(value: object) -> bool:
    return isinstance(value, str) and _WAR_ID_RE.fullmatch(value) is not None


def normalize_core_query_parameters(
        action_id: str, actor: str, recipient: str, phase: str,
        parameters: object) -> dict | None:
    """Normalize a public core query into the QUERY14 selection object.

    ``None`` means the caller supplied ``{}``; that form intentionally stays
    on the existing peace-war discovery path.  An explicit empty ``terms``
    array creates a QUERY14 candidate-discovery request.
    """

    if (action_id not in CORE_ACTION_IDS or phase != "initiate"
            or not _tag(actor) or not _tag(recipient) or actor == recipient):
        raise CoreQueryError("QUERY_PEACE_CORE_PARAMETERS_INVALID")
    if parameters == {}:
        return None
    if not isinstance(parameters, dict) or set(parameters) != {"peace_context"}:
        raise CoreQueryError("QUERY_PEACE_CORE_PARAMETERS_INVALID")
    context = parameters.get("peace_context")
    if not isinstance(context, dict) or set(context) not in (
            {"war_id", "terms"}, {"war_id", "direction", "terms"}):
        raise CoreQueryError("QUERY_PEACE_CORE_PARAMETERS_INVALID")
    direction = context.get("direction", "demand")
    if direction not in ("demand", "offer") or not _war_id(context.get("war_id")):
        raise CoreQueryError("QUERY_PEACE_CORE_PARAMETERS_INVALID")
    terms = context.get("terms")
    if not isinstance(terms, list) or len(terms) > 1:
        raise CoreQueryError("QUERY_PEACE_CORE_PARAMETERS_INVALID")
    if not terms:
        return {
            "action_id": action_id,
            "war_id": context["war_id"],
            "direction": direction,
            "province_ids": [],
            "core_owner": None,
            "discovery": True,
        }
    term = terms[0]
    if (not isinstance(term, dict)
            or set(term) != {"action_id", "province_ids", "core_owner"}
            or term.get("action_id") != action_id
            or not _tag(term.get("core_owner"))):
        raise CoreQueryError("QUERY_PEACE_CORE_PARAMETERS_INVALID")
    province_ids = _province_ids(term.get("province_ids"), allow_empty=False)
    if province_ids is None:
        raise CoreQueryError("QUERY_PEACE_CORE_PARAMETERS_INVALID")
    return {
        "action_id": action_id,
        "war_id": context["war_id"],
        "direction": direction,
        "province_ids": province_ids,
        "core_owner": term["core_owner"],
        "discovery": False,
    }


def build_query14_wire(creation_filetime: object, query_id: str,
                       actor: str, recipient: str, date_raw: object,
                       expiry: object, selection: dict) -> str:
    """Serialize one normalized QUERY14 request without private fields."""

    if (not isinstance(creation_filetime, int)
            or isinstance(creation_filetime, bool)
            or not isinstance(query_id, str) or not query_id
            or not isinstance(date_raw, int) or isinstance(date_raw, bool)
            or not isinstance(expiry, int) or isinstance(expiry, bool)
            or not isinstance(selection, dict)
            or selection.get("action_id") not in CORE_ACTION_IDS
            or not _tag(actor) or not _tag(recipient) or actor == recipient
            or not _war_id(selection.get("war_id"))
            or selection.get("direction") not in ("demand", "offer")):
        raise CoreQueryError("QUERY_PEACE_CORE_PARAMETERS_INVALID")
    province_ids = _province_ids(
        selection.get("province_ids"), allow_empty=True)
    owner = selection.get("core_owner")
    if province_ids is None or (province_ids and not _tag(owner)) \
            or (not province_ids and owner is not None):
        raise CoreQueryError("QUERY_PEACE_CORE_PARAMETERS_INVALID")
    ids_field = ",".join(str(value) for value in province_ids) or "-"
    owner_field = owner or "-"
    return (f"{CORE_QUERY_PROTOCOL} {creation_filetime:x} {query_id} "
            f"{selection['action_id']} {actor} {recipient} {date_raw} {expiry} "
            f"{selection['war_id']} {selection['direction']} {ids_field} "
            f"{owner_field}\n")


_CORE_REQUIRED_TERM_FIELDS = frozenset({
    "action_id", "candidate_count", "candidate_enumeration_complete",
    "candidates", "requested_core_owner", "requested_province_ids",
    "selection_requested", "requested_candidates_found",
    "selected_term_count", "parameters_matched", "selection_applied",
    "selection_records_complete", "action_copy_matched",
    "selection_delta_available", "selection_delta_raw",
})
_CORE_OPTIONAL_TERM_FIELDS = frozenset({
    "aggregate_before_raw", "aggregate_after_raw",
})
_CORE_CANDIDATE_FIELDS = frozenset({
    "province_id", "name", "name_readable", "core_owner", "province_owner",
    "selected", "record_complete",
})


def _bounded_raw(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)
            and -2_147_483_648 <= value <= 2_147_483_647)


def validate_native_core_offer_query(
        event: object, action_id: str, actor: str, recipient: str,
        phase: str, expected_date: object, expected_selection: dict,
        expected_query_id: str | None = None,
        expected_session_id: str | None = None,
        common_validator: Callable[[dict], bool] | None = None) -> bool:
    """Validate one complete native QUERY14 event.

    ``common_validator`` is supplied by ``ObserverSession`` to reuse the
    established empty-offer transport/war/evaluation contract on this same
    event.  No values are accepted from a second native event.
    """

    if (not isinstance(expected_selection, dict)
            or expected_selection.get("action_id") != action_id
            or action_id not in CORE_ACTION_IDS
            or not _tag(actor) or not _tag(recipient) or actor == recipient
            or phase != "initiate"
            or not _war_id(expected_selection.get("war_id"))
            or expected_selection.get("direction") not in ("demand", "offer")):
        return False
    expected_ids = _province_ids(
        expected_selection.get("province_ids"), allow_empty=True)
    expected_owner = expected_selection.get("core_owner")
    if (expected_ids is None
            or (expected_ids and not _tag(expected_owner))
            or (not expected_ids and expected_owner is not None)):
        return False
    if (not isinstance(event, dict)
            or event.get("event") != CORE_QUERY_EVENT
            or event.get("family") != "peace"
            or event.get("action_id") != action_id
            or event.get("actor") != actor
            or event.get("recipient") != recipient
            or event.get("phase") != phase
            or event.get("war_id") != expected_selection["war_id"]
            or event.get("direction") != expected_selection["direction"]
            or event.get("identity_scope") != "observer_session"
            or event.get("reasons_complete") is not False
            or event.get("submitted") is not False):
        return False
    actual_date = event.get("date_raw")
    if (not isinstance(actual_date, int) or isinstance(actual_date, bool)
            or not isinstance(expected_date, int)
            or isinstance(expected_date, bool)
            or actual_date != expected_date):
        return False
    for field, expected in (("query_id", expected_query_id),
                            ("session_id", expected_session_id)):
        value = event.get(field)
        if (not isinstance(value, str) or not value or len(value) > 128
                or (expected is not None and value != expected)):
            return False
    if common_validator is not None:
        common = dict(event)
        common["event"] = "native_peace_empty_offer_inspection"
        common["action_id"] = "white_peace"
        if not common_validator(common):
            return False
    native = event.get("native_core_terms")
    if not isinstance(native, dict):
        return False
    if not (_CORE_REQUIRED_TERM_FIELDS <= set(native)
            and set(native) <= (_CORE_REQUIRED_TERM_FIELDS
                                | _CORE_OPTIONAL_TERM_FIELDS)):
        return False
    if native.get("action_id") != action_id:
        return False
    bool_fields = (
        "candidate_enumeration_complete", "selection_requested",
        "requested_candidates_found", "parameters_matched", "selection_applied",
        "selection_records_complete", "action_copy_matched",
        "selection_delta_available")
    if any(not isinstance(native.get(field), bool) for field in bool_fields):
        return False
    candidate_count = native.get("candidate_count")
    candidates = native.get("candidates")
    if (not isinstance(candidate_count, int) or isinstance(candidate_count, bool)
            or not 0 <= candidate_count <= MAX_CORE_CANDIDATES
            or not isinstance(candidates, list)
            or len(candidates) != candidate_count):
        return False
    seen_candidates: set[tuple[int, str]] = set()
    for row in candidates:
        if not isinstance(row, dict) or set(row) != _CORE_CANDIDATE_FIELDS:
            return False
        province_id = row.get("province_id")
        candidate_key = (province_id, row.get("core_owner"))
        if (not _positive_int(province_id)
                or not isinstance(row.get("name"), str)
                or _NAME_HEX_RE.fullmatch(row["name"]) is None
                or not isinstance(row.get("name_readable"), bool)
                or not _tag(row.get("core_owner"))
                or not _tag(row.get("province_owner"))
                or not isinstance(row.get("selected"), bool)
                or not isinstance(row.get("record_complete"), bool)):
            return False
        if candidate_key in seen_candidates:
            return False
        seen_candidates.add(candidate_key)
    if native.get("candidate_enumeration_complete") is not True:
        return False
    requested_ids = native.get("requested_province_ids")
    if (not isinstance(requested_ids, list)
            or _province_ids(requested_ids, allow_empty=True) != expected_ids
            or native.get("requested_core_owner") != expected_owner):
        return False
    selected_count = native.get("selected_term_count")
    if (not isinstance(selected_count, int) or isinstance(selected_count, bool)
            or not 0 <= selected_count <= MAX_CORE_PROVINCES):
        return False
    if not native.get("action_copy_matched"):
        return False
    discovery = not expected_ids
    if discovery:
        if (native.get("selection_requested") is not False
                or native.get("requested_candidates_found") is not False
                or native.get("selected_term_count") != 0
                or native.get("parameters_matched") is not False
                or native.get("selection_applied") is not False
                or native.get("selection_records_complete") is not True):
            return False
        selected_rows = [row for row in candidates if row["selected"]]
        if selected_rows:
            return False
    else:
        if native.get("selection_requested") is not True:
            return False
        matched = native.get("parameters_matched") is True
        if native.get("requested_candidates_found") is not matched:
            return False
        if matched:
            if (native.get("selected_term_count") != len(expected_ids)
                    or native.get("selection_applied") is not True
                    or native.get("selection_records_complete") is not True):
                return False
            selected_rows = [row for row in candidates if row["selected"]]
            selected_map = {row["province_id"]: row for row in selected_rows}
            if (set(selected_map) != set(expected_ids)
                    or any(row.get("record_complete") is not True
                           for row in selected_rows)
                    or any(row.get("core_owner") != expected_owner
                           for row in selected_rows)):
                return False
        else:
            if (native.get("selected_term_count") != 0
                    or native.get("selection_applied") is not False
                    or native.get("selection_records_complete") is not True
                    or any(row["selected"] for row in candidates)):
                return False
    delta_available = native.get("selection_delta_available")
    delta_raw = native.get("selection_delta_raw")
    if delta_available:
        if discovery or not matched:
            return False
        if not _bounded_raw(delta_raw):
            return False
    elif delta_raw is not None:
        return False
    for field in _CORE_OPTIONAL_TERM_FIELDS:
        if field in native and native[field] is not None and not _bounded_raw(native[field]):
            return False
    return True


def project_native_core_terms(native: dict, codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict:
    """Return the bounded public ``native_core_terms`` projection."""

    result = {
        "action_id": native.get("action_id"),
        "candidate_count": native.get("candidate_count"),
        "candidate_enumeration_complete": (
            native.get("candidate_enumeration_complete") is True),
        "candidates": [],
        "requested_core_owner": native.get("requested_core_owner"),
        "requested_province_ids": list(native.get("requested_province_ids", [])),
        "selection_requested": native.get("selection_requested") is True,
        "requested_candidates_found": (
            native.get("requested_candidates_found") is True),
        "selected_term_count": native.get("selected_term_count"),
        "parameters_matched": native.get("parameters_matched") is True,
        "selection_applied": native.get("selection_applied") is True,
        "selection_records_complete": (
            native.get("selection_records_complete") is True),
        "action_copy_matched": native.get("action_copy_matched") is True,
        "selection_delta_available": (
            native.get("selection_delta_available") is True),
        "selection_delta_raw": native.get("selection_delta_raw"),
    }
    for field in _CORE_OPTIONAL_TERM_FIELDS:
        if field in native:
            result[field] = native[field]
    for row in native.get("candidates", []):
        # QUERY14 retains the native hex name in its private event, just as
        # the other province readers do.  Public names use the session codec.
        name = None
        if row.get("name_readable") is True:
            try:
                name = decode_native_text_hex(row.get("name"), codec)
            except NativeTextError:
                pass
        result["candidates"].append({
            "province_id": row.get("province_id"),
            "name": name,
            "name_readable": name is not None,
            "core_owner": row.get("core_owner"),
            "province_owner": row.get("province_owner"),
            "selected": row.get("selected") is True,
            "record_complete": row.get("record_complete") is True,
        })
    return result

