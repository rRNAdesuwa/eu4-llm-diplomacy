"""Validation and safe projection for native Declare War force counts.

The native dialog reports one bounded aggregate for each side.  This module
keeps the contract independent from the observer/session adapter: it validates
country identity, arithmetic and completeness, then hides all numeric force
values when the native unit proof is unavailable.
"""

from __future__ import annotations

import re
from typing import Any


COUNTRY_TAG_RE = re.compile(r"^[A-Z0-9]{3}$")
UNIT = "men"
MAX_COUNTRIES_PER_SIDE = 128
_INT32_MAX = 2 ** 31 - 1

_TOP_LEVEL_FIELDS = frozenset({
    "called", "action_unchanged", "unit", "units_verified", "complete",
    "attackers", "defenders",
})
_SIDE_FIELDS = frozenset({
    "countries", "infantry_raw", "cavalry_raw", "artillery_raw",
    "deployed_total_raw", "reserve_manpower_raw", "deployed_complete",
    "reserve_complete", "scope_complete",
})


def _valid_nonnegative_int32(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)
            and 0 <= value <= _INT32_MAX)


def _valid_country_list(value: object) -> bool:
    if not isinstance(value, list) or len(value) > MAX_COUNTRIES_PER_SIDE:
        return False
    if any(not isinstance(tag, str)
           or COUNTRY_TAG_RE.fullmatch(tag) is None for tag in value):
        return False
    return len(set(value)) == len(value)


def _valid_side(value: object) -> bool:
    if not isinstance(value, dict) or not _SIDE_FIELDS.issubset(value):
        return False
    countries = value["countries"]
    if not _valid_country_list(countries):
        return False
    for field in (
            "infantry_raw", "cavalry_raw", "artillery_raw",
            "deployed_total_raw", "reserve_manpower_raw"):
        if not _valid_nonnegative_int32(value[field]):
            return False
    if value["deployed_total_raw"] != (
            value["infantry_raw"] + value["cavalry_raw"]
            + value["artillery_raw"]):
        return False
    return all(isinstance(value[field], bool) for field in (
        "deployed_complete", "reserve_complete", "scope_complete"))


def valid_declare_war_forces(value: object) -> bool:
    """Validate one native force aggregate without raising."""

    if not isinstance(value, dict) or not _TOP_LEVEL_FIELDS.issubset(value):
        return False
    if (value["unit"] != UNIT
            or not isinstance(value["called"], bool)
            or not isinstance(value["action_unchanged"], bool)
            or not isinstance(value["units_verified"], bool)
            or not isinstance(value["complete"], bool)):
        return False
    # A force result is usable only when the native helper was actually called
    # for the unchanged action.  An incomplete result can still be projected
    # safely when units_verified is false.
    if value["called"] is not True or value["action_unchanged"] is not True:
        return False
    attackers = value["attackers"]
    defenders = value["defenders"]
    if not _valid_side(attackers) or not _valid_side(defenders):
        return False
    if set(attackers["countries"]).intersection(defenders["countries"]):
        return False
    if value["complete"] and (
            value["units_verified"] is not True
            or any(not side[field]
                   for side in (attackers, defenders)
                   for field in ("deployed_complete", "reserve_complete",
                                 "scope_complete"))):
        return False
    return True


def _public_side(side: dict[str, Any], units_verified: bool) -> dict[str, Any]:
    numeric = units_verified
    deployed_complete = numeric and side["deployed_complete"]
    reserve_complete = numeric and side["reserve_complete"]
    return {
        "countries": sorted(side["countries"]),
        "deployed": {
            "infantry": side["infantry_raw"] if numeric else None,
            "cavalry": side["cavalry_raw"] if numeric else None,
            "artillery": side["artillery_raw"] if numeric else None,
            "total": side["deployed_total_raw"] if numeric else None,
            "unit": UNIT if numeric else None,
            "complete": deployed_complete,
        },
        "reserve_manpower": {
            "amount": side["reserve_manpower_raw"] if numeric else None,
            "unit": UNIT if numeric else None,
            "complete": reserve_complete,
        },
        "scope_complete": side["scope_complete"],
    }


def project_declare_war_forces(value: object) -> dict | None:
    """Project verified public force counts without native/private fields."""

    if not valid_declare_war_forces(value):
        return None
    assert isinstance(value, dict)
    attackers = value["attackers"]
    defenders = value["defenders"]
    assert isinstance(attackers, dict) and isinstance(defenders, dict)
    units_verified = value["units_verified"] is True
    return {
        "source": "native_declare_war_dialog",
        "complete": value["complete"],
        "attackers": _public_side(attackers, units_verified),
        "defenders": _public_side(defenders, units_verified),
    }


__all__ = [
    "COUNTRY_TAG_RE",
    "UNIT",
    "MAX_COUNTRIES_PER_SIDE",
    "valid_declare_war_forces",
    "project_declare_war_forces",
]
