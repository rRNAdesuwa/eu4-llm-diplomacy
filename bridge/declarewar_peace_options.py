"""Validate and project native Declare War peace-option declarations.

The native query exposes three bounded tables: the CB metadata records used
for disabled-term presentation and the two war-goal side declarations.  These
tables describe the peace terms declared by the CB/goal.  They do not evaluate
the current target, diplomatic cost, acceptance, or execution legality.  This
module therefore keeps the native completeness flags and marks the public
projection with ``selection_rules_evaluated=False``.

An auxiliary value is reduced by the native observer to a presence bit.  It is
part of the definition identity used by the native matcher; it is not a
boolean condition result.  Rows with an auxiliary value, and rows whose kind
is not yet mapped, remain in ``unmapped`` and require target evaluation.  A
disabled action is emitted only for a known kind whose auxiliary bit is false.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final


MAX_RECORDS: Final = 256

NATIVE_OPTION_FIELDS: Final[frozenset[str]] = frozenset({
    "called",
    "action_unchanged",
    "complete",
    "disabled",
    "attacker_declared",
    "defender_declared",
})
TABLE_FIELDS: Final[frozenset[str]] = frozenset({
    "available",
    "complete",
    "records",
})
RECORD_FIELDS: Final[frozenset[str]] = frozenset({
    "kind",
    "auxiliary_present",
})


# The tuple form is intentional: kind 3 is the native cede-province record,
# which also has the derived full-annexation public action.  Kinds 1 and 2
# share the force-vassalization public action.  This table is only a stable
# naming map; it is not a runtime legality table.
KIND_ACTION_IDS: Final[dict[int, tuple[str, ...]]] = {
    0: ("demand_ducats",),
    1: ("force_vassalization",),
    2: ("force_vassalization",),
    3: ("cede_province", "full_annexation"),
    4: ("revoke_core",),
    5: ("return_core",),
    7: ("war_reparations",),
    8: ("transfer_trade_power",),
    9: ("humiliate_rival",),
    10: ("show_strength",),
    11: ("concede_defeat",),
    14: ("annul_treaties",),
    15: ("release_nation",),
    18: ("grant_independence",),
    19: ("release_subject",),
    20: ("transfer_subject",),
    21: ("force_religion",),
    26: ("form_personal_union",),
}


def _is_bool(value: object) -> bool:
    return type(value) is bool


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_record(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != RECORD_FIELDS:
        return False
    kind = value.get("kind")
    return (
        _is_int(kind)
        and 0 <= kind <= 0xFFFF
        and _is_bool(value.get("auxiliary_present"))
    )


def _valid_table(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != TABLE_FIELDS:
        return False
    available = value.get("available")
    complete = value.get("complete")
    records = value.get("records")
    if (not _is_bool(available) or not _is_bool(complete)
            or not isinstance(records, list) or len(records) > MAX_RECORDS):
        return False
    if not all(_valid_record(record) for record in records):
        return False

    # A null native object is represented as unavailable/incomplete with no
    # rows.  A non-null object may be complete or a bounded partial read.
    if not available and (complete or records):
        return False
    if complete and not available:
        return False
    return True


def valid_native_peace_options(raw: object) -> bool:
    """Return whether a native peace-options object has a strict shape.

    The production query is a successful observer call, so ``called`` and
    ``action_unchanged`` must be true.  A partial table is still a valid
    observation: it keeps ``complete=False`` and is projected as incomplete
    rather than being turned into a runtime prohibition.
    """

    if not isinstance(raw, Mapping) or set(raw) != NATIVE_OPTION_FIELDS:
        return False
    if (raw.get("called") is not True
            or raw.get("action_unchanged") is not True
            or not _is_bool(raw.get("complete"))):
        return False
    if any(not _valid_table(raw.get(name))
           for name in ("disabled", "attacker_declared", "defender_declared")):
        return False
    expected_complete = all(
        raw[name]["complete"]
        for name in ("disabled", "attacker_declared", "defender_declared")
    )
    return raw["complete"] is expected_complete


def validate_native_peace_options(raw: object) -> bool:
    """Compatibility spelling for callers that use ``validate_*`` helpers."""

    return valid_native_peace_options(raw)


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _project_table(table: Mapping[str, object], *, disabled: bool) -> dict:
    records = table["records"]
    assert isinstance(records, list)
    projected_records: list[dict] = []
    unmapped: list[dict] = []
    action_ids: list[str] = []
    disabled_actions: list[str] = []

    for raw_record in records:
        assert isinstance(raw_record, Mapping)
        kind = raw_record["kind"]
        auxiliary_present = raw_record["auxiliary_present"]
        assert isinstance(kind, int) and not isinstance(kind, bool)
        assert isinstance(auxiliary_present, bool)
        mapped_ids = list(KIND_ACTION_IDS.get(kind, ()))
        projected_records.append({
            "kind": kind,
            "auxiliary_present": auxiliary_present,
            "action_ids": mapped_ids,
            "mapped": bool(mapped_ids),
        })

        if mapped_ids:
            action_ids.extend(mapped_ids)
            if disabled and not auxiliary_present:
                disabled_actions.extend(mapped_ids)
        if auxiliary_present or not mapped_ids:
            # Keep this raw-shaped so callers can reason about an unmapped
            # definition identity without receiving an object/pointer.
            unmapped.append({
                "kind": kind,
                "auxiliary_present": auxiliary_present,
            })

    result = {
        "available": table["available"],
        "complete": table["complete"],
        "records": projected_records,
        "unmapped": unmapped,
        "target_evaluation_required": (
            table["complete"] is not True or bool(unmapped)
            or (not disabled and bool(records))),
        "target_conditions_evaluated": False,
    }
    if disabled:
        result["disabled_actions"] = _ordered_unique(disabled_actions)
    else:
        result["declared_justified_actions"] = _ordered_unique(action_ids)
    return result


def project_native_peace_options(raw: object) -> dict | None:
    """Project a validated native object into the public declaration schema.

    ``None`` denotes a malformed native object.  A valid empty, unavailable,
    or partial table remains representable and keeps its completeness state.
    """

    if not valid_native_peace_options(raw):
        return None
    assert isinstance(raw, Mapping)
    return {
        "source": "native_declare_war_peace_options",
        "called": raw["called"],
        "action_unchanged": raw["action_unchanged"],
        "complete": raw["complete"],
        "selection_rules_evaluated": False,
        "disabled": _project_table(raw["disabled"], disabled=True),
        "attacker_declared": _project_table(
            raw["attacker_declared"], disabled=False),
        "defender_declared": _project_table(
            raw["defender_declared"], disabled=False),
    }


__all__ = [
    "KIND_ACTION_IDS",
    "MAX_RECORDS",
    "NATIVE_OPTION_FIELDS",
    "RECORD_FIELDS",
    "TABLE_FIELDS",
    "project_native_peace_options",
    "validate_native_peace_options",
    "valid_native_peace_options",
]
