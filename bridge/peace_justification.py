"""Validation and public projection for native peace-term justification.

The native query reports one bounded row for each term that it inspected.  A
row's ``justified`` value is the result of the native term predicate; this
module only validates and exposes that result.  It deliberately does not
reimplement peace rules, diplomatic-power costs, or game legality.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Final


MAX_TERM_COUNT: Final = 512
MAX_BUCKET: Final = 39
_MAX_UINT32: Final = (1 << 32) - 1
_TAG_RE: Final = re.compile(r"[A-Z0-9]{3}\Z")

TOP_FIELDS: Final[frozenset[str]] = frozenset({
    "called", "complete", "direction", "term_count", "unsupported_count",
    "terms",
})
TERM_FIELDS: Final[frozenset[str]] = frozenset({
    "index", "type_id", "bucket", "selected", "applicable", "evaluated",
    "justified", "province_id", "object_country", "complete",
})

# These pairs are the native (type_id, bucket) descriptors used by the peace
# payload query.  A cede-province row can be part of a full-annexation offer;
# the raw contract has no aggregate marker, so it is intentionally projected
# as the underlying cede_province family.
NATIVE_TERM_ACTIONS: Final[dict[tuple[int, int], str]] = {
    (0x2D2B, 0): "demand_ducats",
    (0x2D25, 3): "cede_province",
    (0x30A0, 7): "war_reparations",
    (0x2E07, 8): "transfer_trade_power",
    (0x2D27, 0x13): "release_subject",
    (0x35F0, 0x14): "transfer_subject",
    (0x30A3, 9): "humiliate_rival",
    (0x2F20, 10): "show_strength",
    (0x2D29, 21): "force_religion",
    (0x2D28, 0x0F): "release_nation",
    (0x2D2C, 1): "force_vassalization",
    (0x3C05, 2): "force_vassalization",
    (0x2D2A, 0x1A): "form_personal_union",
    (0x2E4A, 0x12): "grant_independence",
    (0x2D2D, 0x0B): "concede_defeat",
    (0x2D2E, 0x0E): "annul_treaties",
    (0x2E00, 5): "return_core",
    (0x2D26, 4): "revoke_core",
}


def _is_bool(value: object) -> bool:
    return type(value) is bool


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_tag(value: object) -> bool:
    return isinstance(value, str) and _TAG_RE.fullmatch(value) is not None


def _valid_term_row(value: object, term_count: int,
                    seen_indices: set[int]) -> bool:
    if not isinstance(value, Mapping) or set(value) != TERM_FIELDS:
        return False

    index = value.get("index")
    type_id = value.get("type_id")
    bucket = value.get("bucket")
    if (not _is_int(index) or not 0 <= index < MAX_TERM_COUNT
            or index >= term_count or index in seen_indices):
        return False
    if not _is_int(type_id) or not 0 <= type_id <= _MAX_UINT32:
        return False
    if not _is_int(bucket) or not 0 <= bucket <= MAX_BUCKET:
        return False
    for field in ("selected", "applicable", "evaluated", "complete"):
        if not _is_bool(value.get(field)):
            return False

    justified = value.get("justified")
    if value["evaluated"] is True:
        if not _is_bool(justified):
            return False
    elif justified is not None:
        return False
    if value["complete"] is True and value["evaluated"] is not True:
        return False

    province_id = value.get("province_id")
    if (province_id is not None
            and (not _is_int(province_id) or province_id <= 0)):
        return False
    object_country = value.get("object_country")
    if object_country is not None and not _is_tag(object_country):
        return False

    seen_indices.add(index)
    return True


def validate_native_justification(raw: object) -> bool:
    """Return whether *raw* satisfies the native justification contract."""

    if not isinstance(raw, Mapping) or set(raw) != TOP_FIELDS:
        return False
    if not _is_bool(raw.get("called")) or not _is_bool(raw.get("complete")):
        return False
    if raw.get("direction") not in ("demand", "offer"):
        return False

    term_count = raw.get("term_count")
    unsupported_count = raw.get("unsupported_count")
    if (not _is_int(term_count) or not 0 <= term_count <= MAX_TERM_COUNT
            or not _is_int(unsupported_count)
            or not 0 <= unsupported_count <= MAX_TERM_COUNT
            or unsupported_count > term_count):
        return False
    terms = raw.get("terms")
    if not isinstance(terms, list):
        return False
    if len(terms) + unsupported_count != term_count:
        return False

    seen_indices: set[int] = set()
    if any(not _valid_term_row(row, term_count, seen_indices)
           for row in terms):
        return False

    # A complete query is a complete observation of every native term slot.
    # No game-rule conclusion is inferred from this flag.
    if raw["complete"] is True:
        if (raw["called"] is not True or unsupported_count != 0
                or any(row["complete"] is not True
                       or row["evaluated"] is not True for row in terms)):
            return False
    return True


def _term_status(action_id: str | None, row: Mapping[str, object]) -> str:
    """Translate an observed native predicate result to public status."""

    if action_id is None or row["evaluated"] is not True:
        return "unknown"
    return "justified" if row["justified"] is True else "unjustified"


def _selected_terms_status(terms: list[dict[str, object]]) -> str:
    """Aggregate selected observations; this is not peace legality."""

    selected = [term for term in terms if term["selected"] is True]
    if not selected:
        return "not_applicable"
    statuses = {term["status"] for term in selected}
    if "unjustified" in statuses:
        return "unjustified"
    if "unknown" in statuses:
        return "unknown"
    return "justified"


def project_native_justification(raw: object) -> dict | None:
    """Project a valid native query into stable public term observations."""

    if not validate_native_justification(raw):
        return None
    assert isinstance(raw, Mapping)
    public_terms: list[dict[str, object]] = []
    for row in raw["terms"]:
        assert isinstance(row, Mapping)
        action_id = NATIVE_TERM_ACTIONS.get((row["type_id"], row["bucket"]))
        public_terms.append({
            "term_index": row["index"],
            "action_id": action_id,
            "selected": row["selected"],
            "province_id": row["province_id"],
            "object_country": row["object_country"],
            "status": _term_status(action_id, row),
            "source": "native_rule",
            "complete": row["complete"],
        })

    return {
        "source": "native_peace_justification",
        "called": raw["called"],
        "complete": raw["complete"],
        "direction": raw["direction"],
        "term_count": raw["term_count"],
        "unsupported_count": raw["unsupported_count"],
        "terms": public_terms,
        "selected_terms_status": _selected_terms_status(public_terms),
    }


__all__ = [
    "MAX_TERM_COUNT",
    "NATIVE_TERM_ACTIONS",
    "TERM_FIELDS",
    "TOP_FIELDS",
    "project_native_justification",
    "validate_native_justification",
]
