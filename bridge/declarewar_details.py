"""Validation and public projection for native Declare War dialog text.

The native observer returns each dialog string as a bounded hex payload.  The
payload is only decoded with the codec selected by the installation; this
module never infers an encoding from the bytes or from the resulting text.
"""

from __future__ import annotations

import re
from typing import Final

from bridge.native_text import (
    DEFAULT_NATIVE_TEXT_CODEC,
    NativeTextError,
    decode_native_text_hex,
    validate_native_text_codec,
)


DETAIL_KEYS: Final[frozenset[str]] = frozenset({
    "called",
    "action_unchanged",
    "complete",
    "casus_belli_name",
    "casus_belli_description",
    "war_goal_name",
    "war_goal_description",
    "disabled_peace_terms_description",
    "declaration_description",
})
RECORD_KEYS: Final[frozenset[str]] = frozenset({
    "applicable",
    "called",
    "return_verified",
    "text_hex",
    "readable",
    "truncated",
})
FIELD_MAX_BYTES: Final[dict[str, int]] = {
    "casus_belli_name": 512,
    "casus_belli_description": 2048,
    "war_goal_name": 512,
    "war_goal_description": 2048,
    "disabled_peace_terms_description": 4096,
    "declaration_description": 8192,
}
_HEX_RE = re.compile(r"[0-9A-Fa-f]*\Z")
_GOAL_FIELDS = frozenset(("war_goal_name", "war_goal_description"))


def _is_bool(value: object) -> bool:
    return isinstance(value, bool)


def _valid_record(field: str, value: object) -> bool:
    if not isinstance(value, dict) or set(value) != RECORD_KEYS:
        return False
    if any(not _is_bool(value[key]) for key in (
            "applicable", "called", "return_verified", "readable", "truncated")):
        return False
    text_hex = value["text_hex"]
    if (not isinstance(text_hex, str) or len(text_hex) % 2
            or _HEX_RE.fullmatch(text_hex) is None
            or len(text_hex) // 2 > FIELD_MAX_BYTES[field]):
        return False
    if not value["applicable"]:
        # Only the two war-goal records may be explicitly inapplicable.  An
        # inapplicable record has a fixed empty, unreadable sentinel shape.
        if field not in _GOAL_FIELDS:
            return False
        if (value["called"] or value["return_verified"]
                or value["readable"] or value["truncated"]
                or text_hex != ""):
            return False
    return True


def valid_declare_war_details(raw: object) -> bool:
    """Return whether one native Declare War details object is well formed.

    ``complete`` is derived from the applicable records and must agree with
    the native summary.  A canonical no-CB query is represented by both war
    goal records using the explicit inapplicable sentinel.
    """

    if not isinstance(raw, dict) or set(raw) != DETAIL_KEYS:
        return False
    if (raw["called"] is not True
            or raw["action_unchanged"] is not True
            or not _is_bool(raw["complete"])):
        return False
    records = {
        field: raw[field]
        for field in FIELD_MAX_BYTES
    }
    if any(not _valid_record(field, record)
           for field, record in records.items()):
        return False
    goal_applicable = records["war_goal_name"]["applicable"]
    if records["war_goal_description"]["applicable"] != goal_applicable:
        return False
    if (not goal_applicable
            and any(records[field]["applicable"] is not False
                    for field in _GOAL_FIELDS)):
        return False
    complete = all(
        record["called"] and record["return_verified"]
        and record["readable"] and not record["truncated"]
        for record in records.values()
        if record["applicable"]
    )
    return raw["complete"] is complete


def _decoded_record(record: dict, max_bytes: int, codec: str) -> tuple[str | None, bool]:
    if (not record["applicable"] or record["called"] is not True
            or record["return_verified"] is not True
            or record["readable"] is not True
            or record["truncated"] is True):
        return None, False
    try:
        text = decode_native_text_hex(
            record["text_hex"], codec, max_bytes=max_bytes)
    except NativeTextError:
        return None, False
    return text, True


def project_declare_war_details(
        raw: object,
        codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict | None:
    """Project a valid native details object into its public dialog schema.

    Shape failures return ``None``.  A configured codec is validated even when
    a field is inapplicable; malformed text payloads remain safe as ``None``
    and make only their containing completeness checks false.
    """

    if not valid_declare_war_details(raw):
        return None
    validate_native_text_codec(codec)
    assert isinstance(raw, dict)

    decoded: dict[str, tuple[str | None, bool]] = {
        field: _decoded_record(raw[field], FIELD_MAX_BYTES[field], codec)
        for field in FIELD_MAX_BYTES
    }
    casus_complete = (
        decoded["casus_belli_name"][1]
        and decoded["casus_belli_description"][1])
    goal_applicable = raw["war_goal_name"]["applicable"]
    goal_complete = (
        True if not goal_applicable else
        decoded["war_goal_name"][1]
        and decoded["war_goal_description"][1])
    peace_complete = decoded["disabled_peace_terms_description"][1]
    description_complete = decoded["declaration_description"][1]
    decoded_complete = (
        casus_complete and goal_complete and peace_complete
        and description_complete)
    return {
        "source": "native_declare_war_dialog",
        "complete": raw["complete"] is True and decoded_complete,
        "casus_belli": {
            "name": decoded["casus_belli_name"][0],
            "description": decoded["casus_belli_description"][0],
            "complete": casus_complete,
        },
        "war_goal": {
            "applicable": goal_applicable,
            "name": decoded["war_goal_name"][0],
            "description": decoded["war_goal_description"][0],
            "complete": goal_complete,
        },
        "peace_conditions": {
            "disabled_terms_description": decoded[
                "disabled_peace_terms_description"][0],
            "complete": peace_complete,
        },
        "description": decoded["declaration_description"][0],
        "description_complete": description_complete,
    }


__all__ = [
    "DETAIL_KEYS",
    "FIELD_MAX_BYTES",
    "RECORD_KEYS",
    "project_declare_war_details",
    "valid_declare_war_details",
]
