"""Pure validation helpers for Declare War participant parameters.

The native QUERY19/EXEC4 adapter owns wire serialization and game-side
legality.  This module only validates the bounded public participant lists and
returns their canonical form for that adapter.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


COUNTRY_TAG_RE = re.compile(r"^[A-Z0-9]{3}$")
PARTICIPANT_FIELDS = (
    "call_allies",
    "promise_land_to",
    "co_belligerents",
)
MAX_PARTICIPANTS = 16


def _fail(code: str) -> None:
    """Raise a stable, machine-readable Declare War parameter error."""

    raise ValueError(code)


def _validate_main_party(value: object, code: str) -> str:
    if not isinstance(value, str) or COUNTRY_TAG_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _field_code(field: str, suffix: str = "INVALID") -> str:
    return f"DECLARE_WAR_{field.upper()}_{suffix}"


def _normalize_list(value: object, field: str,
                    forbidden: frozenset[str]) -> list[str]:
    """Validate one list and return unique, dictionary-sorted tags."""

    invalid_code = _field_code(field)
    if not isinstance(value, list):
        _fail(invalid_code)
    if len(value) > MAX_PARTICIPANTS:
        _fail(_field_code(field, "TOO_MANY"))

    seen: set[str] = set()
    result: list[str] = []
    for tag in value:
        if not isinstance(tag, str) or COUNTRY_TAG_RE.fullmatch(tag) is None:
            _fail(_field_code(field, "TAG_INVALID"))
        if tag in seen:
            _fail(_field_code(field, "DUPLICATE"))
        if tag in forbidden:
            _fail(_field_code(field, "MAIN_PARTY"))
        seen.add(tag)
        result.append(tag)
    result.sort()
    return result


def normalize_participant_selection(
        parameters: object, actor: str = "FRA",
        recipient: str | None = None) -> dict[str, list[str]]:
    """Normalize the three bounded participant lists.

    Missing participant fields default to empty lists.  Other parameter keys
    are intentionally ignored so this helper can be composed with the
    existing CB/war-goal payload.  The returned lists are sorted in canonical
    dictionary order and are newly allocated.
    """

    if not isinstance(parameters, Mapping):
        _fail("DECLARE_WAR_PARAMETERS_MUST_BE_OBJECT")
    actor_tag = _validate_main_party(actor, "DECLARE_WAR_ACTOR_INVALID")
    recipient_tag: str | None = None
    if recipient is not None:
        recipient_tag = _validate_main_party(recipient, "DECLARE_WAR_RECIPIENT_INVALID")
    forbidden = frozenset(
        tag for tag in (actor_tag, recipient_tag) if tag is not None)

    normalized = {
        field: _normalize_list(parameters.get(field, []), field, forbidden)
        for field in PARTICIPANT_FIELDS
    }

    promise = set(normalized["promise_land_to"])
    allies = set(normalized["call_allies"])
    if not promise.issubset(allies):
        _fail("DECLARE_WAR_PROMISE_LAND_TO_NOT_CALL_ALLY")

    co_belligerents = set(normalized["co_belligerents"])
    if co_belligerents.intersection(allies | promise):
        _fail("DECLARE_WAR_CO_BELLIGERENT_OVERLAP")
    return normalized


def country_csv(tags: Sequence[str]) -> str:
    """Serialize a canonical participant list; an empty list is ``-``."""

    if isinstance(tags, (str, bytes)) or not isinstance(tags, Sequence):
        _fail("DECLARE_WAR_PARTICIPANTS_INVALID")
    normalized = _normalize_list(list(tags), "participants", frozenset())
    return ",".join(normalized) if normalized else "-"


def participant_selection_requested(selection: Mapping[str, Any]) -> bool:
    """Return whether any participant category contains a selected country."""

    if not isinstance(selection, Mapping):
        _fail("DECLARE_WAR_PARTICIPANT_SELECTION_INVALID")
    selected = []
    for field in PARTICIPANT_FIELDS:
        value = selection.get(field, [])
        if not isinstance(value, list):
            _fail(_field_code(field))
        selected.append(bool(value))
    return any(selected)


# The explicit alias is useful to callers that want to validate without
# implying that the result carries native authorization.
validate_participant_selection = normalize_participant_selection


__all__ = [
    "COUNTRY_TAG_RE",
    "PARTICIPANT_FIELDS",
    "MAX_PARTICIPANTS",
    "normalize_participant_selection",
    "validate_participant_selection",
    "country_csv",
    "participant_selection_requested",
]
