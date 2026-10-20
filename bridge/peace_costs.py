"""Projection of native peace-special cost observations.

The native observer reports raw values even when the selected-term rule is
unavailable.  This module deliberately projects only those raw comparison
values; it does not infer a public unit or turn an unverified scale into a
verified one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_SPECIAL_FIELDS = {
    "humiliate_rival": "native_humiliate_rival",
    "show_strength": "native_show_strength",
    "force_religion": "native_force_religion",
}

_COST_FIELDS = (
    "base_or_existing_raw",
    "selected_delta_raw",
    "total_raw",
    "limit_raw",
)


def _is_int(value: object) -> bool:
    """Return true for native integer values, excluding JSON booleans."""

    return isinstance(value, int) and not isinstance(value, bool)


def project_special_cost_comparisons(
    event: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Project a verified native raw cost comparison.

    ``None`` means that the event is outside this helper's scope or that its
    native observation is incomplete or inconsistent.  A rule-unavailable
    selected term is still projectable when its cost observation is complete;
    ``rule_available`` is intentionally not used as a gate here.
    """

    if not isinstance(event, Mapping):
        return None
    action_id = event.get("action_id")
    if not isinstance(action_id, str):
        return None
    native_field = _SPECIAL_FIELDS.get(action_id)
    if native_field is None:
        return None
    native = event.get(native_field)
    if not isinstance(native, Mapping):
        return None

    # These flags describe the observation itself.  Do not project a partial
    # observation and do not synthesize missing raw fields as zero.
    for field in (
        "cost_observation_attempted",
        "cost_readable",
        "cost_transaction_restored",
        "cost_payload_unchanged",
    ):
        if native.get(field) is not True:
            return None
    for field in _COST_FIELDS:
        if not _is_int(native.get(field)):
            return None

    country = native.get("country")
    beneficiary = native.get("beneficiary")
    unit = native.get("unit_scale")
    scale_verified = native.get("unit_scale_verified")
    if (not isinstance(country, str) or not country
            or not isinstance(beneficiary, str) or not beneficiary
            or not isinstance(unit, str) or not unit
            or not isinstance(scale_verified, bool)):
        return None

    existing = native["base_or_existing_raw"]
    selected_delta = native["selected_delta_raw"]
    total = native["total_raw"]
    limit = native["limit_raw"]
    if total != existing + selected_delta:
        return None

    return {
        "action_id": action_id,
        "country": country,
        "beneficiary": beneficiary,
        "existing_raw": existing,
        "selected_delta_raw": selected_delta,
        "total_raw": total,
        "limit_raw": limit,
        "within_limit": total <= limit,
        "source": "native_rule",
        "unit": unit,
        "scale_verified": scale_verified,
    }


__all__ = ["project_special_cost_comparisons"]
