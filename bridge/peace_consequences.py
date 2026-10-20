"""Validation and public projection for native peace consequences.

The native observer reports several previews together.  This module keeps the
raw contract strict at the bridge boundary and exposes only semantic values:
the diplomatic power country/value, the aggressive-expansion preview, the
coalition candidates, and per-country/per-province territorial costs.  The
coalition row's ``current_value`` is retained for compatibility.  The
object-level ``current_value_semantics_verified`` marker controls whether the
projection may expose it as the current aggressive-expansion modifier; it is
never presented as a total opinion value.

An absent ``native_consequences`` member remains a legacy-compatible event.
When the member is present, malformed records return ``None`` from the
projector and fail the validator.  A well-shaped native partial observation is
projected with ``complete: false`` and is never promoted to a complete result.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any
from .peace_overextension import (
    validate_native_overextension, project_native_overextension,
)
from .peace_justification import (
    validate_native_justification, project_native_justification,
)

from .native_text import (
    DEFAULT_NATIVE_TEXT_CODEC,
    InvalidNativeText,
    decode_native_text_hex,
)


_TAG_RE = re.compile(r"[A-Z0-9]{3}\Z")
_MAX_COALITION_COUNTRIES = 256
_MAX_NATIVE_COALITION_COUNT = 4096
_MAX_TERRITORIAL_ROWS = 256
_MAX_TERRITORIAL_PROVINCES = 512
_MAX_TEXT_HEX = 16384 * 2
_SIGNED_NATIVE_MIN = -(1 << 63)
_SIGNED_NATIVE_MAX = (1 << 63) - 1
_OVEREXTENSION_UNIT = "fraction"

_TOP_KEYS = frozenset({
    "called", "offer_identity_verified", "complete",
    "diplomatic_power", "aggressive_expansion", "coalition", "territorial",
})
_DIPLOMATIC_KEYS = frozenset({"country", "available", "value", "unit"})
_AE_KEYS = frozenset({
    "available", "maximum_raw", "scale", "native_text_hex",
    "text_readable", "text_truncated", "coalition_possible",
})
_COALITION_KEYS = frozenset({
    "available", "complete", "native_count", "countries",
    "current_value_semantics_verified",
})
_COALITION_ROW_KEYS = frozenset({
    "tag", "aggressive_expansion_delta", "current_value",
})
_TERRITORIAL_KEYS = frozenset({
    "country", "called", "complete", "truncated",
    "administrative_power", "overextension_added_raw", "scale", "provinces",
})
_PROVINCE_KEYS = frozenset({
    "province_id", "administrative_power", "already_core", "adds_overextension",
    "overextension_added_raw",
})


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_tag(value: object) -> bool:
    return isinstance(value, str) and _TAG_RE.fullmatch(value) is not None


def _is_bool(value: object) -> bool:
    return type(value) is bool


def _is_signed_native_int(value: object) -> bool:
    return (_is_int(value)
            and _SIGNED_NATIVE_MIN <= value <= _SIGNED_NATIVE_MAX)


def _is_hex(value: object) -> bool:
    return (isinstance(value, str) and len(value) <= _MAX_TEXT_HEX
            and len(value) % 2 == 0
            and re.fullmatch(r"[0-9A-Fa-f]*", value) is not None)


def _valid_diplomatic_power(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != _DIPLOMATIC_KEYS:
        return False
    return (_is_tag(value.get("country"))
            and _is_bool(value.get("available"))
            and _is_int(value.get("value")) and value["value"] >= 0
            and value.get("unit") == "power_points")


def _valid_aggressive_expansion(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != _AE_KEYS:
        return False
    if (not _is_bool(value.get("available"))
            or not _is_int(value.get("maximum_raw"))
            or value["maximum_raw"] < 0
            or value.get("scale") != 1000
            or not _is_hex(value.get("native_text_hex"))
            or not _is_bool(value.get("text_readable"))
            or not _is_bool(value.get("text_truncated"))
            or not _is_bool(value.get("coalition_possible"))):
        return False
    return True


def _valid_coalition(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != _COALITION_KEYS:
        return False
    countries = value.get("countries")
    count = value.get("native_count")
    if (not _is_bool(value.get("available"))
            or not _is_bool(value.get("complete"))
            or not _is_bool(value.get("current_value_semantics_verified"))
            or not _is_int(count)
            or not 0 <= count <= _MAX_NATIVE_COALITION_COUNT
            or not isinstance(countries, list)
            or len(countries) > _MAX_COALITION_COUNTRIES
            or len(countries) > count):
        return False
    # ``native_count`` is the pre-filter native vector length.  The public
    # country rows are a filtered view and therefore need not have the same
    # length.  Captured overflow remains bounded but cannot claim availability
    # or completeness because the public list is necessarily truncated.
    if count > _MAX_COALITION_COUNTRIES and (
            value["available"] is True or value["complete"] is True):
        return False
    seen: set[str] = set()
    for row in countries:
        if not isinstance(row, Mapping) or set(row) != _COALITION_ROW_KEYS:
            return False
        tag = row.get("tag")
        if (not _is_tag(tag) or tag in seen
                or not _is_signed_native_int(
                    row.get("aggressive_expansion_delta"))
                or not _is_signed_native_int(row.get("current_value"))):
            return False
        seen.add(tag)
    if value.get("complete") is True and not value.get("available"):
        # An unavailable list may still be complete (the native query can
        # prove that it has no entries), so do not require availability here.
        pass
    return True


def _valid_territorial_row(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != _TERRITORIAL_KEYS:
        return False
    provinces = value.get("provinces")
    if (not _is_tag(value.get("country"))
            or not _is_bool(value.get("called"))
            or not _is_bool(value.get("complete"))
            or not _is_bool(value.get("truncated"))
            or not _is_int(value.get("administrative_power"))
            or value["administrative_power"] < 0
            or not _is_int(value.get("overextension_added_raw"))
            or value["overextension_added_raw"] < 0
            or value.get("scale") != 1000
            or not isinstance(provinces, list)
            or len(provinces) > _MAX_TERRITORIAL_PROVINCES):
        return False
    seen: set[int] = set()
    for province in provinces:
        if not isinstance(province, Mapping) or set(province) != _PROVINCE_KEYS:
            return False
        province_id = province.get("province_id")
        if (not _is_int(province_id) or province_id <= 0
                or province_id in seen
                or not _is_int(province.get("administrative_power"))
                or province["administrative_power"] < 0
                or not _is_bool(province.get("already_core"))
                or not _is_bool(province.get("adds_overextension"))
                or not _is_int(province.get("overextension_added_raw"))
                or province["overextension_added_raw"] < 0):
            return False
        seen.add(province_id)
    if value.get("complete") is True and (
            value.get("called") is not True or value.get("truncated") is True):
        return False
    return True


def validate_native_consequences(value: object) -> bool:
    """Return whether a present native consequences object is complete in shape.

    The validator does not infer diplomacy roles or game rules.  Those remain
    native observations.  It does enforce every value/array relation needed to
    safely project the record and rejects the corrected opaque coalition field
    if a producer attempts to label it as verified AE.
    """

    if (not isinstance(value, Mapping) or not _TOP_KEYS.issubset(value)
            or set(value) - _TOP_KEYS - {"overextension", "justification"}):
        return False
    if ("overextension" in value
            and not validate_native_overextension(value["overextension"])):
        return False
    if ("justification" in value
            and not validate_native_justification(value["justification"])):
        return False
    if (not _is_bool(value.get("called"))
            or not _is_bool(value.get("offer_identity_verified"))
            or not _is_bool(value.get("complete"))
            or not _valid_diplomatic_power(value.get("diplomatic_power"))
            or not _valid_aggressive_expansion(value.get("aggressive_expansion"))
            or not _valid_coalition(value.get("coalition"))):
        return False
    territorial = value.get("territorial")
    if (not isinstance(territorial, list)
            or len(territorial) > _MAX_TERRITORIAL_ROWS
            or not all(_valid_territorial_row(row) for row in territorial)):
        return False
    countries = [row["country"] for row in territorial]
    if len(countries) != len(set(countries)):
        return False
    if value["complete"] is True:
        if value["called"] is not True or value["offer_identity_verified"] is not True:
            return False
        if value["coalition"]["complete"] is not True:
            return False
        if any(row["complete"] is not True for row in territorial):
            return False
        if ("overextension" in value
                and value["overextension"]["complete"] is not True):
            return False
        if ("justification" in value
                and value["justification"]["complete"] is not True):
            return False
    return True


def project_native_consequences(
        value: object, codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict[str, Any] | None:
    """Project a valid native record without exposing raw text hex."""

    if not validate_native_consequences(value):
        return None
    native = value
    ae = native["aggressive_expansion"]
    text: str | None = None
    if ae["text_readable"]:
        try:
            text = decode_native_text_hex(
                ae["native_text_hex"], codec=codec, max_bytes=16384,
                max_bytes_limit=16384)
        except (InvalidNativeText, ValueError):
            return None
    coalition = native["coalition"]

    def _project_overextension(raw: int, scale: int) -> dict[str, Any]:
        # The native field is a fixed-point fraction.  Keep its raw form for
        # consumers that need the exact wire value, while exposing both the
        # fraction and the UI-facing percentage-point reading explicitly.
        return {
            "overextension_added_raw": raw,
            "scale": scale,
            "overextension_unit": _OVEREXTENSION_UNIT,
            "overextension_added_fraction": raw / scale,
            "overextension_added_percentage_points": raw * 100 / scale,
        }

    projected = {
        "source": "native_peace_consequences",
        "complete": native["complete"],
        "diplomatic_power": dict(native["diplomatic_power"]),
        "aggressive_expansion": {
            "available": ae["available"],
            "maximum_raw": ae["maximum_raw"],
            "scale": ae["scale"],
            "maximum": (ae["maximum_raw"] / ae["scale"]
                         if ae["available"] else None),
            "text": text,
            "text_readable": ae["text_readable"],
            "text_truncated": ae["text_truncated"],
            "coalition_possible": ae["coalition_possible"],
        },
        "coalition": {
            "available": coalition["available"],
            "complete": coalition["complete"],
            "native_count": coalition["native_count"],
            "current_value_semantics_verified": coalition[
                "current_value_semantics_verified"],
            "countries": [
                {
                    "tag": row["tag"],
                    "aggressive_expansion_delta": row["aggressive_expansion_delta"],
                    "current_value": row["current_value"],
                    "current_aggressive_expansion_modifier": (
                        row["current_value"]
                        if coalition["current_value_semantics_verified"]
                        else None),
                }
                for row in coalition["countries"]
            ],
        },
        "territorial": [
            {
                "country": row["country"],
                "called": row["called"],
                "complete": row["complete"],
                "truncated": row["truncated"],
                "administrative_power": row["administrative_power"],
                **_project_overextension(
                    row["overextension_added_raw"], row["scale"]),
                "provinces": [
                    {
                        **dict(province),
                        **_project_overextension(
                            province["overextension_added_raw"], row["scale"]),
                    }
                    for province in row["provinces"]
                ],
            }
            for row in native["territorial"]
        ],
    }
    if "overextension" in native:
        projected["overextension"] = project_native_overextension(native["overextension"])
    if "justification" in native:
        projected["justification"] = project_native_justification(native["justification"])
    return projected


_DIRECT_SELECTION_RECORDS = (
    "native_money", "native_provinces", "native_reparations",
    "native_trade_power", "native_concede_defeat", "native_annul_treaties",
    "native_humiliate_rival", "native_show_strength",
    "native_force_religion", "native_return_core", "native_revoke_core",
    "native_annexation",
)
_NESTED_SELECTION_RECORDS = (
    "native_core_terms", "native_subject_terms", "native_country_terms",
)


def _selection_records(event: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return native records that explicitly describe a requested selection.

    ``native_consequences`` is an observation of the constructed offer and is
    deliberately not used to infer whether the requested terms were copied.
    The per-family selection records are the authority for that distinction.
    Money is the one legacy record without ``selection_requested``; its
    requested amount and match flag identify an explicit money selection.
    """

    records: list[Mapping[str, Any]] = []

    for key in _DIRECT_SELECTION_RECORDS:
        record = event.get(key)
        if not isinstance(record, Mapping):
            continue
        requested = record.get("selection_requested")
        if requested is True:
            records.append(record)
        elif (key == "native_money"
              and "parameters_matched" in record
              and ("requested_amount_raw" in record
                   or "action_amount_raw" in record)):
            # QUERY5/QUERY7 predate the explicit selection_requested flag.
            records.append(record)

    for key in _NESTED_SELECTION_RECORDS:
        nested = event.get(key)
        if not isinstance(nested, Mapping):
            continue
        # Single-family QUERY14/16 records put their selection flags directly
        # on native_*_terms; combined queries put one record under each action.
        if nested.get("selection_requested") is True:
            records.append(nested)
        for record in nested.values():
            if isinstance(record, Mapping) and record.get("selection_requested") is True:
                records.append(record)

    return records


def _requested_terms_applied(event: Mapping[str, Any]) -> bool | None:
    """Classify whether native records copied the requested terms.

    No explicit selection record means that the event is a white/legacy
    observation and is treated as applied.  Once a record says a selection was
    requested, every such record must report ``parameters_matched`` true.  A
    missing match flag is an observation gap rather than success.
    """

    records = _selection_records(event)
    if not records:
        return True
    states: list[bool | None] = []
    for record in records:
        matched = record.get("parameters_matched")
        if "parameters_matched" not in record and record.get("action_id") == "full_annexation":
            matched = record.get("selection_applied")
        states.append(matched if type(matched) is bool else None)
    if any(state is False for state in states):
        return False
    if all(state is True for state in states):
        return True
    return None


def project_event_consequences(
        event: object,
        codec: str = DEFAULT_NATIVE_TEXT_CODEC) -> dict[str, Any] | None:
    """Project consequences together with request-application semantics.

    ``project_native_consequences`` remains the raw native projector.  This
    event-level wrapper prevents an unmatched requested term from being
    mistaken for a complete zero-cost offer: native values are retained for
    diagnosis, while availability and completeness are withdrawn.
    """

    if not isinstance(event, Mapping) or "native_consequences" not in event:
        return None
    projected = project_native_consequences(event["native_consequences"], codec)
    if projected is None:
        return None

    # A freshly constructed offer keeps its zero-valued gold object in the
    # native selected vector even for White Peace. The query's explicit null
    # native_money record means no money selection/setter was requested. Keep
    # that native bit for diagnosis, but aggregate only effective public terms.
    justification = projected.get("justification")
    if (isinstance(justification, dict) and "native_money" in event
            and event["native_money"] is None):
        terms = [dict(row) for row in justification.get("terms", [])]
        for row in terms:
            if row.get("action_id") == "demand_ducats":
                row["native_selected"] = row.get("selected") is True
                row["selected"] = False
                row["selection_reason_code"] = "NATIVE_ZERO_DEFAULT_MONEY_TERM"
        selected = [row for row in terms if row.get("selected") is True]
        statuses = {row.get("status") for row in selected}
        justification = dict(justification)
        justification["terms"] = terms
        justification["selected_terms_status"] = (
            "not_applicable" if not selected else "unjustified" if "unjustified" in statuses
            else "unknown" if "unknown" in statuses else "justified")
        projected["justification"] = justification

    applied = _requested_terms_applied(event)
    projected["scope"] = "constructed_offer"
    projected["requested_terms_applied"] = applied
    projected["reason_code"] = None

    # An unconfirmed selection cannot support a complete consequences claim.
    if applied is not True:
        projected["complete"] = False
        if isinstance(projected.get("justification"), dict):
            justification = dict(projected["justification"])
            justification["selected_terms_status"] = "unknown"
            justification["complete"] = False
            justification["requested_terms_applied"] = applied
            justification["reason_code"] = "NATIVE_PEACE_REQUESTED_TERMS_NOT_APPLIED"
            projected["justification"] = justification

    if applied is False:
        projected["reason_code"] = "NATIVE_PEACE_REQUESTED_TERMS_NOT_APPLIED"

        diplomatic = dict(projected["diplomatic_power"])
        diplomatic["available"] = False
        projected["diplomatic_power"] = diplomatic

        aggressive_expansion = dict(projected["aggressive_expansion"])
        aggressive_expansion["available"] = False
        aggressive_expansion["maximum"] = None
        projected["aggressive_expansion"] = aggressive_expansion

        coalition = dict(projected["coalition"])
        coalition["available"] = False
        coalition["complete"] = False
        projected["coalition"] = coalition

        territorial = []
        for row in projected["territorial"]:
            updated = dict(row)
            updated["complete"] = False
            updated["provinces"] = [dict(province)
                                    for province in row["provinces"]]
            territorial.append(updated)
        projected["territorial"] = territorial
        if isinstance(projected.get("overextension"), dict):
            change = dict(projected["overextension"])
            change["available"] = False
            change["complete"] = False
            change["countries"] = [
                {**row, "available": False, "complete": False}
                for row in change["countries"]]
            projected["overextension"] = change

    return projected


__all__ = [
    "project_event_consequences",
    "project_native_consequences",
    "validate_native_consequences",
]
