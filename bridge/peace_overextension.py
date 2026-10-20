"""Strict validation and projection for the native Peace OE preview.

The native preview is a read-only calculation over the selected territorial
payload.  ``current_raw`` is the cached current value, while
``current_recomputed_raw`` is the independently recomputed value.  A complete
country row is trusted only when those values match and the native arithmetic
relations hold.  Partial rows retain their signed raw values for diagnosis;
they are never promoted to an available complete preview.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Final


MAX_COUNTRIES: Final = 64
MAX_PROVINCES_PER_COUNTRY: Final = 512
OVEREXTENSION_SCALE: Final = 1000
SCOPE: Final = "selected_territorial_preview"
_INT32_MIN = -(1 << 31)
_INT32_MAX = (1 << 31) - 1
_TAG_RE: Final = re.compile(r"[A-Z0-9]{3}\Z")

TOP_FIELDS: Final[frozenset[str]] = frozenset({
    "called", "complete", "scope", "unsupported_territorial_terms",
    "countries",
})
COUNTRY_FIELDS: Final[frozenset[str]] = frozenset({
    "country", "complete", "current_raw", "current_recomputed_raw",
    "cache_matches_recomputed", "gained_raw", "lost_raw", "delta_raw",
    "projected_raw", "scale", "gained_province_ids", "lost_province_ids",
})


def _is_bool(value: object) -> bool:
    return type(value) is bool


def _is_int32(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)
            and _INT32_MIN <= value <= _INT32_MAX)


def _is_tag(value: object) -> bool:
    return isinstance(value, str) and _TAG_RE.fullmatch(value) is not None


def _valid_province_ids(value: object) -> bool:
    if not isinstance(value, list) or len(value) > MAX_PROVINCES_PER_COUNTRY:
        return False
    seen: set[int] = set()
    for province_id in value:
        if (not _is_int32(province_id) or province_id <= 0
                or province_id in seen):
            return False
        seen.add(province_id)
    return True


def _valid_country_row(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != COUNTRY_FIELDS:
        return False
    if (not _is_tag(value.get("country"))
            or not _is_bool(value.get("complete"))
            or not _is_bool(value.get("cache_matches_recomputed"))
            or not _is_int32(value.get("scale"))
            or value.get("scale") != OVEREXTENSION_SCALE
            or not _valid_province_ids(value.get("gained_province_ids"))
            or not _valid_province_ids(value.get("lost_province_ids"))):
        return False
    if any(not _is_int32(value.get(field)) for field in (
            "current_raw", "current_recomputed_raw", "gained_raw",
            "lost_raw", "delta_raw", "projected_raw")):
        return False

    # Native raw values are retained even for partial records.  Only a row
    # marked complete may support arithmetic/availability claims.
    if value["complete"] is True:
        if value["cache_matches_recomputed"] is not True:
            return False
        if (value["current_raw"] < 0
                or value["projected_raw"] < 0
                or value["gained_raw"] < 0
                or value["lost_raw"] < 0):
            return False
        if value["delta_raw"] != value["projected_raw"] - value["current_raw"]:
            return False
    return True


def validate_native_overextension(value: object) -> bool:
    """Return whether a native overextension object has a strict shape."""

    if not isinstance(value, Mapping) or set(value) != TOP_FIELDS:
        return False
    for field in ("called", "complete", "unsupported_territorial_terms"):
        if not _is_bool(value.get(field)):
            return False
    if value.get("scope") != SCOPE:
        return False
    countries = value.get("countries")
    if not isinstance(countries, list) or len(countries) > MAX_COUNTRIES:
        return False
    if any(not _valid_country_row(row) for row in countries):
        return False
    tags = [row["country"] for row in countries]
    if len(tags) != len(set(tags)):
        return False

    # A complete native preview has no unsupported territorial family and all
    # country rows must have passed cache/arithmetic validation.  A partial
    # preview remains valid and retains its raw diagnostics.
    if value["complete"] is True:
        if (value["called"] is not True
                or value["unsupported_territorial_terms"] is not False
                or any(row["complete"] is not True for row in countries)):
            return False
    if value["called"] is False and countries:
        return False
    return True


def valid_native_overextension(value: object) -> bool:
    """Compatibility spelling for callers using ``valid_*`` helpers."""

    return validate_native_overextension(value)


def _fraction(raw: int) -> float:
    return raw / OVEREXTENSION_SCALE


def _percentage_points(raw: int) -> float:
    return raw * 100 / OVEREXTENSION_SCALE


def _project_value(raw: int) -> dict[str, object]:
    return {
        "raw": raw,
        "fraction": _fraction(raw),
        "percentage_points": _percentage_points(raw),
    }


def project_native_overextension(value: object) -> dict | None:
    """Project a valid native preview into bounded public values."""

    if not validate_native_overextension(value):
        return None
    assert isinstance(value, Mapping)
    countries: list[dict[str, object]] = []
    for row in value["countries"]:
        assert isinstance(row, Mapping)
        countries.append({
            "country": row["country"],
            "available": row["complete"],
            "complete": row["complete"],
            "current_raw": row["current_raw"],
            "current_recomputed_raw": row["current_recomputed_raw"],
            "cache_matches_recomputed": row["cache_matches_recomputed"],
            "gained_raw": row["gained_raw"],
            "lost_raw": row["lost_raw"],
            "delta_raw": row["delta_raw"],
            "projected_raw": row["projected_raw"],
            "scale": OVEREXTENSION_SCALE,
            "unit": "fraction",
            "current_fraction": _fraction(row["current_raw"]),
            "current_percentage_points": _percentage_points(
                row["current_raw"]),
            "gained_fraction": _fraction(row["gained_raw"]),
            "gained_percentage_points": _percentage_points(
                row["gained_raw"]),
            "lost_fraction": _fraction(row["lost_raw"]),
            "lost_percentage_points": _percentage_points(row["lost_raw"]),
            "delta_fraction": _fraction(row["delta_raw"]),
            "delta_percentage_points": _percentage_points(row["delta_raw"]),
            "projected_fraction": _fraction(row["projected_raw"]),
            "projected_percentage_points": _percentage_points(
                row["projected_raw"]),
            "gained_province_ids": list(row["gained_province_ids"]),
            "lost_province_ids": list(row["lost_province_ids"]),
        })
    return {
        "source": "native_peace_overextension",
        "available": value["called"],
        "scope": value["scope"],
        "complete": value["complete"],
        "unsupported_territorial_terms": value[
            "unsupported_territorial_terms"],
        "countries": countries,
    }


__all__ = [
    "COUNTRY_FIELDS",
    "MAX_COUNTRIES",
    "MAX_PROVINCES_PER_COUNTRY",
    "OVEREXTENSION_SCALE",
    "SCOPE",
    "TOP_FIELDS",
    "project_native_overextension",
    "validate_native_overextension",
    "valid_native_overextension",
]
